#!/usr/bin/env bash
# 合成ログだけで順序判定、逆順故障、非共通clock故障を検査する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; fail=1; }

python3 - "$WORK" <<'PY'
from pathlib import Path
import sys

work = Path(sys.argv[1])

def generate(path, side, reverse=False):
    rows = []
    seq = 0
    def add(clock, cpu, kind, port, value, pc):
        nonlocal seq
        seq += 1
        rows.append((seq, clock, 1, cpu, kind, port, value, pc))

    # 共通54コマンド。SPECIFYは3 OUT、結果なし。
    for command in range(54):
        base = 10 + command * 3
        add(base, "sub", "OUT", "00FB", 0x03, "0100")
        add(base + 1, "sub", "OUT", "00FB", 0xDF, "0100")
        add(base + 2, "sub", "OUT", "00FB", 0x02, "0100")
    add(180, "sub", "IN", "00FE", 0, "0100")

    # 交換run 0..35は共通、36が5対6の分岐。
    for run in range(37):
        request = run % 2 == 0
        length = 1
        if run == 36:
            length = 5 if side == "official" else 6
        base = 1000 if run == 36 else 200 + run * 20
        for pos in range(length):
            if request:
                add(base + pos, "main", "OUT", "00FD", pos,
                    "37F4" if pos + 1 < length else "3811")
            else:
                add(base + pos, "main", "IN", "00FC", pos, "3863")

    axis = 1000
    if side == "official":
        branch = axis - 50 if reverse else axis + 10
        add(branch, "sub", "OUT", "00FB", 0x04, "0100")
        add(branch + 1, "sub", "OUT", "00FB", 0x00, "0100")
        add(branch + 2, "sub", "IN", "00FB", 0x20, "0100")
    else:
        branch = axis - 50
        add(branch, "sub", "OUT", "00FB", 0x46, "0100")
        for offset in range(1, 9):
            add(branch + offset, "sub", "OUT", "00FB", offset, "0100")
        for offset in range(9, 16):
            add(branch + offset, "sub", "IN", "00FB", 0, "0100")

    rows.sort(key=lambda row: (row[1], row[0]))
    with path.open("w", encoding="utf-8") as fp:
        fp.write("# 合成ログ（公式データ不使用）\n")
        for row in rows:
            seq, clock, frame, cpu, kind, port, value, pc = row
            fp.write(f"{seq:6d} {clock:7d} {frame:6d} {cpu} {kind:<4} "
                     f"{port} {value:02X} {pc}\n")

generate(work / "official.txt", "official")
generate(work / "official.reverse.txt", "official", reverse=True)
generate(work / "mixed.txt", "mixed")

# CPU別clockへ壊した入力: sub先頭clockをmain先頭clockと重複させる。
lines = (work / "mixed.txt").read_text(encoding="utf-8").splitlines()
main_clock = next(line.split()[1] for line in lines
                  if len(line.split()) >= 4 and line.split()[3] == "main")
for pos, line in enumerate(lines):
    cols = line.split()
    if len(cols) >= 6 and cols[3] == "sub" and cols[5] == "00FE":
        cols[1] = main_clock
        lines[pos] = " ".join(cols)
        break
(work / "mixed.split-clock.txt").write_text("\n".join(lines) + "\n",
                                             encoding="utf-8")
PY

ANALYZER="$REPO/tools/analyze_no_disk_branch_order.py"
if python3 "$ANALYZER" --official "$WORK/official.txt" --mixed "$WORK/mixed.txt" \
     --out "$WORK/base.json" >"$WORK/base.stdout" \
   && grep -q 'official: order=exchange_first' "$WORK/base.stdout" \
   && grep -q 'mixed: order=fdc_first' "$WORK/base.stdout" \
   && grep -q 'mixed_read_data: exchange_run=-2 phase=after_run_before_next_request received=1/1' "$WORK/base.stdout" \
   && grep -q '"unique_across_streams": true' "$WORK/base.json"; then
  ok "FDC 55件目と交換+0を独立軸で順序付け、混成READの直前runを対応付け"
else
  ng "基準入力の順序またはrun対応が期待と異なる"
fi

# 公式FDCだけ交換+0の後から前へ移し、順序が反転したことを検出する。
if python3 "$ANALYZER" --official "$WORK/official.reverse.txt" \
     --mixed "$WORK/mixed.txt" --out "$WORK/reverse.json" >"$WORK/reverse.stdout" \
   && grep -q 'official: order=fdc_first' "$WORK/reverse.stdout" \
   && ! cmp -s "$WORK/base.json" "$WORK/reverse.json"; then
  ok "順序を逆にする故障注入をexchange_first→fdc_firstとして検出"
else
  ng "逆順故障を検出できない"
fi

if python3 "$ANALYZER" --official "$WORK/official.txt" \
     --mixed "$WORK/mixed.split-clock.txt" --out "$WORK/split.json" \
     >"$WORK/split.stdout" 2>"$WORK/split.stderr"; then
  ng "CPU別clock故障を誤って受理した"
elif grep -q '共通時計でない' "$WORK/split.stderr"; then
  ok "main/subで重複する別clock故障を共通clock検査が拒否"
else
  ng "CPU別clock故障の失敗理由が期待と異なる"
fi

if grep -Eiq '"pc"|"value"|0x[0-9a-f]|00F[BCD]' "$WORK/base.json"; then
  ng "結果JSONへ生値またはPC/データポート表現が漏れた"
else
  ok "結果JSONは値列・PC・絶対clockを保存しない"
fi

exit "$fail"
