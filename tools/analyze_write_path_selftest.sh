#!/usr/bin/env bash
# tools/analyze_write_path_selftest.sh — tools/analyze_write_path.py の
# selftest（公式環境不要。合成フィクスチャのみ）。
#
# なぜ要るか: この解析器は「書き込み系コマンドのデータフェーズはOUT」と
# いう性質でフェーズを切る。既存の analyze_exchange14_read_rules.py の
# commands() はここを前提にしていないためWRITE系を解析できず（データ部の
# 1バイト目を次のコマンド語と読み違える）、新しく書いた。**新しく書いた
# パーサの検出力を確認しないまま仕様書へ結論を書かない。**
#
# 検査すること:
#   1. WRITE DATA(データ部OUT) と READ DATA(データ部IN) を混ぜた合成ログで、
#      コマンド件数・データ部バイト数・結果バイト数が期待どおりに出ること
#   2. 陽性対照: データ部を255バイトに削った合成ログでは 255 と報告される
#      （256を決め打ちで返しているのではないことの確認）
#   3. 陽性対照: 伏せ字ログでは「解析不可」と言うこと（黙って0件にしない）
#
# 値は扱わない。合成フィクスチャの値も意味を持たないダミーである。

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }
overall_rc=0

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

gen() {   # $1 = 出力先, $2 = WRITE のデータ部バイト数, $3 = 伏せ字にするか(0/1)
  python3 - "$1" "$2" "$3" <<'EOF'
import sys
path, ndata, masked = sys.argv[1], int(sys.argv[2]), sys.argv[3] == "1"
rows = []
seq = [0]
def ev(kind, port, value):
    seq[0] += 1
    v = "--" if masked and port in ("00FB",) else f"{value & 0xFF:02X}"
    rows.append(f"{seq[0]:>6} {seq[0]:>6}      0  sub   {kind:<4}  {port}   {v}   0100")
# SPECIFY: コマンド語+2パラメータ、結果なし
ev("OUT", "00FB", 0x03); ev("OUT", "00FB", 0x00); ev("OUT", "00FB", 0x00)
# WRITE DATA: コマンド語+8パラメータ、データ部(OUT) ndata、結果7(IN)
ev("OUT", "00FB", 0x45)
for k in range(8): ev("OUT", "00FB", k)
for k in range(ndata): ev("OUT", "00FB", (k * 7) & 0xFF)
for k in range(7): ev("IN", "00FB", k)
# READ DATA: コマンド語+8パラメータ、データ+結果はすべてIN(263)
ev("OUT", "00FB", 0x46)
for k in range(8): ev("OUT", "00FB", k)
for k in range(263): ev("IN", "00FB", (k * 3) & 0xFF)
with open(path, "w") as f:
    f.write("# tools/analyze_write_path_selftest.sh の合成フィクスチャ(公式データ不使用)\n")
    f.write("core      : (テスト用ダミー)\nframes    : 1\n\n")
    f.write("# main\n# seq    clock   frame  cpu   kind  port  value  pc\n\n")
    f.write("# sub\n# seq    clock   frame  cpu   kind  port  value  pc\n")
    f.write("\n".join(rows) + "\n")
EOF
}

say "合成ログ(WRITE データ部256 + READ)を正しく分解できること"
gen "$WORK/ok.iolog.txt" 256 0
out="$(python3 tools/analyze_write_path.py "$WORK/ok.iolog.txt" --label 合成 2>&1)"
echo "$out" | sed 's/^/  /'
if echo "$out" | grep -q "FDCコマンド 3 件" \
   && echo "$out" | grep -q "WRITE DATA.*結果バイト数: 7×1.*データ部バイト数: 256×1回" \
   && echo "$out" | grep -q "READ DATA.*結果バイト数: 263×1"; then
  ok "コマンド件数・データ部256・結果7・READ側263を正しく報告した"
else
  ng "合成ログの分解結果が期待と違う"
  overall_rc=1
fi

say "陽性対照: データ部を255に削ると255と報告されること（256の決め打ちでない）"
gen "$WORK/short.iolog.txt" 255 0
out="$(python3 tools/analyze_write_path.py "$WORK/short.iolog.txt" --label 合成255 2>&1)"
if echo "$out" | grep -q "データ部バイト数: 255×1回"; then
  ok "陽性対照: データ部を実際に数えている（255と報告された）"
else
  ng "陽性対照: データ部の長さを数えていない可能性がある"
  echo "$out" | sed 's/^/  /'
  overall_rc=1
fi

say "陽性対照: 伏せ字ログでは解析不可と言うこと（黙って0件にしない）"
gen "$WORK/masked.iolog.txt" 256 1
out="$(python3 tools/analyze_write_path.py "$WORK/masked.iolog.txt" --label 伏せ字 2>&1)"
if echo "$out" | grep -q "解析不可"; then
  ok "陽性対照: 伏せ字ログを解析不可として報告した"
else
  ng "陽性対照: 伏せ字ログを黙って解析してしまった"
  echo "$out" | sed 's/^/  /'
  overall_rc=1
fi

say "書き込みストリームのハッシュ器(tools/hash_write_stream.py)"
gen "$WORK/h1.iolog.txt" 256 0
gen "$WORK/h2.iolog.txt" 256 0
gen "$WORK/h3.iolog.txt" 255 0
h1="$(python3 tools/hash_write_stream.py "$WORK/h1.iolog.txt" | awk -F'\t' '$1=="sha256"{print $2}')"
h2="$(python3 tools/hash_write_stream.py "$WORK/h2.iolog.txt" | awk -F'\t' '$1=="sha256"{print $2}')"
h3="$(python3 tools/hash_write_stream.py "$WORK/h3.iolog.txt" | awk -F'\t' '$1=="sha256"{print $2}')"
if [ -n "$h1" ] && [ "$h1" = "$h2" ]; then
  ok "同じ内容の合成ログからは同じSHA-256が出る（決定論性）"
else
  ng "同じ内容なのにSHA-256が違う（またはハッシュが空）"
  overall_rc=1
fi
if [ -n "$h3" ] && [ "$h1" != "$h3" ]; then
  ok "陽性対照: データ部を1バイト減らすとSHA-256が変わる"
else
  ng "陽性対照: 中身を変えてもSHA-256が変わらない（検出力が無い）"
  overall_rc=1
fi
# 書き込みが1件も無いログでは判定不能(rc=2)であること
python3 - "$WORK/nowrite.iolog.txt" <<'EOF'
import sys
rows=["# tools/analyze_write_path_selftest.sh の合成フィクスチャ(書き込み無し)",
      "core      : (テスト用ダミー)","frames    : 1","",
      "# main","# seq    clock   frame  cpu   kind  port  value  pc","",
      "# sub","# seq    clock   frame  cpu   kind  port  value  pc",
      "     1      1      0  sub   OUT   00FB   03   0100",
      "     2      2      0  sub   OUT   00FB   00   0101",
      "     3      3      0  sub   OUT   00FB   00   0102"]
open(sys.argv[1],"w").write("\n".join(rows)+"\n")
EOF
python3 tools/hash_write_stream.py "$WORK/nowrite.iolog.txt" >/dev/null 2>&1
if [ "$?" -eq 2 ]; then
  ok "書き込みが1件も無いログは判定不能(rc=2)として報告される"
else
  ng "書き込み0件なのに判定不能にならなかった（黙って合格に化ける）"
  overall_rc=1
fi

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "analyze_write_path_selftest: OK（全項目）"
else
  echo "analyze_write_path_selftest: 失敗あり"
fi
exit "$overall_rc"
