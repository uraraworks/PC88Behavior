#!/usr/bin/env bash
# 合成ログで分岐位置・run長抽出と、それぞれの故障注入検出を確認する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANALYZER="$REPO/tools/analyze_error_exchange_shape.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; fail=1; }

generate() {
  python3 - "$1" "$2" "$3" <<'PY'
import sys
path, side, fault = sys.argv[1:]
rows = []
seq = 0

def add(clock, cpu, kind, port, value, pc):
    global seq
    seq += 1
    rows.append((seq, clock, 770, cpu, kind, port, value, pc))

# 交換#3形式の合成要求。値はselftest入力だけに存在し、解析出力には出さない。
request = [0x02, 0x01, 0x00, 0x33, 0x44, 0x06, 0x12, 0x60]
for pos, value in enumerate(request):
    add(10 + pos, "main", "OUT", "00FD", value, "37F4" if pos % 2 == 0 else "3811")

# 共通FDC 2件: SEEK、SENSE INTERRUPT STATUS。
for offset, value in enumerate((0x0F, 0x01, 0x00)):
    add(20 + offset, "sub", "OUT", "00FB", value, "0100")
if side == "mixed" and fault == "divergence":
    for offset, value in enumerate((0x07, 0x01)):
        add(30 + offset, "sub", "OUT", "00FB", value, "0100")
else:
    add(30, "sub", "OUT", "00FB", 0x08, "0100")
    add(31, "sub", "IN", "00FB", 0x21, "0100")
    add(32, "sub", "IN", "00FB", 0x00, "0100")

# 3件目でSENSE DRIVE STATUS対READ DATAへ分岐する。
if side == "official":
    add(40, "sub", "OUT", "00FB", 0x04, "0100")
    add(41, "sub", "OUT", "00FB", 0x01, "0100")
    add(42, "sub", "IN", "00FB", 0x21, "0100")
    response_len = 2 if fault == "run_length" else 1
else:
    params = (0x01, 0x00, 0x00, 0x01, 0x01, 0x00, 0x01, 0x00)
    add(40, "sub", "OUT", "00FB", 0x06, "0100")
    for offset, value in enumerate(params, 1):
        add(40 + offset, "sub", "OUT", "00FB", value, "0100")
    for offset, value in enumerate((0x41, 0x01, 0, 0, 0, 0, 0), 9):
        add(40 + offset, "sub", "IN", "00FB", value, "0100")
    response_len = 256

for pos in range(response_len):
    add(100 + pos, "main", "IN", "00FC", 0xA5, "3863" if pos % 2 == 0 else "3880")
for pos, value in enumerate((0x55, 0xAA)):
    add(500 + pos, "main", "OUT", "00FD", value, "37F4" if pos == 0 else "3811")
for pos in range(3):
    add(510 + pos, "main", "IN", "00FC", 0x5A, "3863")

rows.sort(key=lambda row: (row[1], row[0]))
with open(path, "w", encoding="utf-8") as fp:
    fp.write("# 合成ログ（公式データ不使用）\n")
    for row in rows:
        seq, clock, frame, cpu, kind, port, value, pc = row
        fp.write(f"{seq:6d} {clock:7d} {frame:6d} {cpu} {kind:<4} {port} {value:02X} {pc}\n")
PY
}

generate "$WORK/official.txt" official base
generate "$WORK/mixed.txt" mixed base
generate "$WORK/mixed.divergence.txt" mixed divergence
generate "$WORK/official.run-length.txt" official run_length

if python3 "$ANALYZER" --official "$WORK/official.txt" --mixed "$WORK/mixed.txt" \
     --label 合成基準 --out "$WORK/base.out" \
   && grep -q 'FDCコマンド種別の一致prefix: 2件' "$WORK/base.out" \
   && grep -q '分岐直前の共通要求: main→sub 長さ=8、固定8バイト要求' "$WORK/base.out" \
   && grep -q '公式の分岐後応答run: sub→main 長さ=1' "$WORK/base.out" \
   && grep -q '同じ軸で混成が行う応答run: sub→main 長さ=256' "$WORK/base.out"; then
  ok "基準入力から分岐位置・共通要求・公式/混成応答run長を抽出"
else
  ng "基準入力の構造抽出が期待と異なる"
fi

# 故障注入1: mixedの共通2件目を別コマンドへ変え、分岐を1件早める。
if cmp -s "$WORK/mixed.txt" "$WORK/mixed.divergence.txt"; then
  ng "分岐位置の故障注入が入力を変えていない（注入側の故障）"
elif python3 "$ANALYZER" --official "$WORK/official.txt" \
       --mixed "$WORK/mixed.divergence.txt" --label 合成基準 --out "$WORK/divergence.out" \
     && grep -q 'FDCコマンド種別の一致prefix: 1件' "$WORK/divergence.out" \
     && ! cmp -s "$WORK/base.out" "$WORK/divergence.out"; then
  ok "故障注入でFDC分岐位置が2件prefixから1件prefixへ変わることを検出"
else
  ng "故障注入したFDC分岐位置の変化を検出できない"
fi

# 故障注入2: officialの応答runへ1イベント加え、長さ1を2へ変える。
if cmp -s "$WORK/official.txt" "$WORK/official.run-length.txt"; then
  ng "run長の故障注入が入力を変えていない（注入側の故障）"
elif python3 "$ANALYZER" --official "$WORK/official.run-length.txt" \
       --mixed "$WORK/mixed.txt" --label 合成基準 --out "$WORK/run-length.out" \
     && grep -q '公式の分岐後応答run: sub→main 長さ=2' "$WORK/run-length.out" \
     && ! cmp -s "$WORK/base.out" "$WORK/run-length.out"; then
  ok "故障注入で公式応答run長が1から2へ変わることを検出"
else
  ng "故障注入した公式応答run長の変化を検出できない"
fi

if grep -Eq 'A5|5A|0x|\$F[BCD]|value=' "$WORK/base.out"; then
  ng "解析出力へ合成値またはデータポート値表現が漏れた"
else
  ok "解析出力に交換/FDCの生値を含めない"
fi

exit "$fail"
