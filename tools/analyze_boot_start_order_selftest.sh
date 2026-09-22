#!/usr/bin/env bash
# 起動直後順序解析器の合成入力検査。公式ROM・公式ディスクは使わない。
# 正常入力、順序を壊した陰性対照、値列／無視行の漏えいを検査する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANALYZE="$REPO/tools/analyze_boot_start_order.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FAIL=0

ok() { printf 'OK  - %s\n' "$1"; }
ng() { printf 'NG  - %s\n' "$1" >&2; FAIL=1; }

python3 - "$WORK" <<'PY'
from pathlib import Path
import sys

work = Path(sys.argv[1])

def make(path: Path, broken: bool) -> None:
    rows = []
    def add(clock, cpu, kind, port, pc):
        rows.append((len(rows) + 1, clock, cpu, kind, port, pc))

    add(10, "main", "OUT", 0xFD, 0x37F4)       # main送信#1
    add(12, "sub",  "IN",  0xFC, 0x1111)       # 起動専用受信
    add(20, "sub",  "OUT", 0xF8, 0x2222)
    add(21, "sub",  "OUT", 0xF8, 0x2223)
    for i in range(7):
        add(30 + i * 4, "sub", "OUT", 0xFB, 0x3000 + i)
        add(31 + i * 4, "sub", "IN",  0xFB, 0x3100 + i)
    # $FE/$FFが初期化窓の終端。陰性対照は第2送信を完了前へ移す。
    add(59, "sub", "IN", 0xFE, 0x4444)
    add(40 if broken else 70, "main", "OUT", 0xFD, 0x3811)
    add(71, "sub",  "OUT", 0xFD, 0x5555)
    add(72, "main", "IN",  0xFC, 0x3863)

    rows.sort(key=lambda row: row[1])
    with path.open("w", encoding="utf-8") as fp:
        fp.write("# VALUE_COLUMN_CANARY_A5E91C（合成・画面本文ではない）\n")
        for seq, clock, cpu, kind, port, pc in rows:
            fp.write(f"{seq:6d} {clock:7d} {1:6d}  {cpu:<4}  {kind:<4}  "
                     f"{port:04X}   A5   {pc:04X}\n")

make(work / "ok.iolog.txt", False)
make(work / "broken.iolog.txt", True)
PY

if python3 "$ANALYZE" --iolog "$WORK/ok.iolog.txt" \
    >"$WORK/ok.out" 2>"$WORK/ok.err" \
    && grep -q '入力1: 判定=OK' "$WORK/ok.out"; then
  ok "正常入力の順序と7 batchを受理"
else
  ng "正常入力を受理できない"
fi

if python3 "$ANALYZE" --iolog "$WORK/broken.iolog.txt" \
    >"$WORK/broken.out" 2>"$WORK/broken.err"; then
  ng "陰性対照: 初期化完了前の第2送信を通した"
elif grep -q '入力1: 判定=NG' "$WORK/broken.out"; then
  ok "陰性対照: 順序破壊をNGとして検出"
else
  ng "陰性対照が判定NGを報告しない"
fi

if grep -E -q 'VALUE_COLUMN_CANARY_A5E91C|(^|[^0-9A-F])A5([^0-9A-F]|$)' \
    "$WORK/ok.out" "$WORK/ok.err" "$WORK/broken.out" "$WORK/broken.err"; then
  ng "値列または無視行が標準出力／標準エラーへ漏れた"
else
  ok "値列・画面本文に相当する入力を標準出力／標準エラーへ出さない"
fi

if python3 "$ANALYZE" \
    --iolog "$REPO/measurements/m6g-d0-boot-run1.iolog.txt.gz" \
    --iolog "$REPO/measurements/m6g-d0-boot-run2.iolog.txt.gz" \
    >"$WORK/real.out" 2>"$WORK/real.err" \
    && [ "$(grep -c '判定=OK' "$WORK/real.out")" -eq 2 ]; then
  ok "伏せ済みm6g run1/run2で同じ順序命題を再現"
else
  ng "伏せ済みm6g run1/run2の再検証に失敗"
fi

if [ "$FAIL" -eq 0 ]; then
  echo "analyze_boot_start_order_selftest: rc=0"
else
  echo "analyze_boot_start_order_selftest: rc=1" >&2
fi
exit "$FAIL"
