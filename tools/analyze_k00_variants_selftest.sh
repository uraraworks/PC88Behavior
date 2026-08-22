#!/usr/bin/env bash
# analyze_k00_variants.pyの合成ログ自己検査。公式ROM・ディスクは使わない。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANALYZE="$REPO/tools/analyze_k00_variants.py"
WORK_K00="$(mktemp -d)"
trap 'rm -rf "$WORK_K00"' EXIT
overall_rc=0

gen() { # 出力先、B列故障注入(0/1)
  python3 - "$1" "$2" <<'PYEOF'
import sys
path, inject = sys.argv[1], sys.argv[2] == "1"
rows = []
seq = 0

def ev(kind, port, value):
    global seq
    seq += 1
    rows.append(f"{seq:6d} {seq:7d} {seq:6d}  sub  {kind:<4}  {port}   {value:02X}   0100")

def recv(value):
    ev("IN", "00FC", value)

def simple(value):
    recv(value)
    ev("OUT", "00FD", 0x7E)

# K00列A。続くFBはSPECIFYのコマンド語である。
recv(0x10)
ev("OUT", "00FF", 0x0D); ev("OUT", "00FF", 0x0C)
ev("OUT", "00F8", 0x5A); ev("OUT", "00F8", 0xA5)
ev("OUT", "00FB", 0x03); ev("OUT", "00FB", 0); ev("OUT", "00FB", 0)

# 完走READ DATAを1件置く（データ値は全て架空）。
ev("OUT", "00FB", 0x06)
for _ in range(8): ev("OUT", "00FB", 0)
for _ in range(263): ev("IN", "00FB", 0xCC)

# K01〜K05を出して記号割当を固定し、K05の直後に2回目のK00を置く。
for value in (0x20, 0x30, 0x40, 0x50, 0x60):
    simple(value)

recv(0x10)
ev("OUT", "00FF", 0x0D); ev("OUT", "00FF", 0x0C)
ev("OUT", "00FF", 0x81); ev("OUT", "00FF", 0x08)
ev("OUT", "00FF", 0x0A); ev("OUT", "00FF", 0x0C)
ev("OUT", "00FF", 0x0E); ev("OUT", "00FF", 0x09)
ev("OUT", "00FC", 0x5A)
# 故障注入では終端ポートだけを変え、既知A/Bのどちらでもなくする。
ev("OUT", "00FB" if inject else "00FD", 0x04 if inject else 0x7E)

with open(path, "w", encoding="utf-8") as f:
    f.write("# 合成フィクスチャ（公式データ不使用）\n")
    f.write("core : dummy\nframes : 1\n\n")
    f.write("# sub\n# seq clock frame cpu kind port value pc\n")
    f.write("\n".join(rows) + "\n")
PYEOF
}

healthy="$WORK_K00/healthy.iolog.txt"
broken="$WORK_K00/broken.iolog.txt"
healthy_out="$WORK_K00/healthy.txt"
broken_out="$WORK_K00/broken.txt"
gen "$healthy" 0
gen "$broken" 1

python3 "$ANALYZE" --iolog "$healthy" --label 合成 --out "$healthy_out" >/dev/null
if grep -q 'K00標本数: 2' "$healthy_out" \
   && grep -q '| 合成 | A | 1 |' "$healthy_out" \
   && grep -q '| 合成 | B | 2 |' "$healthy_out" \
   && grep -q '直前run（K05ならB、それ以外=A）: 例外0件' "$healthy_out" \
   && grep -q '未知の終端列: 0件' "$healthy_out"; then
  echo '  OK   無傷: A/Bと履歴状態を期待どおり分類'
else
  echo '  NG   無傷フィクスチャを正しく分類できない'
  overall_rc=1
fi

# データポートへ置いたダミー生値が成果物へ漏れていないことを独立に見る。
if grep -Eq '(^|[^0-9A-F])(5A|A5|7E|CC)([^0-9A-F]|$)' "$healthy_out"; then
  echo '  NG   データポートの生値が解析出力へ混入'
  overall_rc=1
else
  echo '  OK   データポート値は解析出力に非混入'
fi

python3 "$ANALYZE" --iolog "$broken" --label 注入 --out "$broken_out" >/dev/null
if grep -q '未知の終端列: 1件' "$broken_out" \
   && grep -q '| 注入 | 未知 | 2 |' "$broken_out"; then
  echo '  OK   故障注入: B列終端破壊を「未知」1件として検出（陽性対照）'
else
  echo '  NG   故障注入が症状として検出されない'
  overall_rc=1
fi

if [[ "$overall_rc" -eq 0 ]]; then
  echo 'analyze_k00_variants selftest: OK（無傷合格・注入不合格を確認）'
else
  echo 'analyze_k00_variants selftest: 失敗あり'
fi
exit "$overall_rc"
