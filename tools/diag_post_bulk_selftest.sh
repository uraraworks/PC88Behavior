#!/usr/bin/env bash
# tools/diag_post_bulk_selftest.sh — tools/diag_post_bulk.py の selftest
# （公式環境不要。合成フィクスチャのみ）。
#
# この比較器は「バルク終端（最後の sub OUT $FC）以降だけを突き合わせる」もので、
# 既存の diag_l3_mixed が見ている区間（バルクより手前）とは別の場所を見る。
# **検出力を確認してから結論に使う。**
#
# 検査すること:
#   1. 同一の合成ログ同士では「分岐なし」と報告すること（false positive 無し）
#   2. 陽性対照: バルク終端**以降**だけを変えたログでは分岐を検出すること
#   3. 陽性対照: バルク終端**より手前**だけを変えたログでは分岐を検出しないこと
#      （この比較器の守備範囲を外れることの確認。ここを取り違えると
#        「手前の違い」を「後ろの分岐」と誤読する）

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1
say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }
overall_rc=0
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

gen() {  # $1=出力 $2=手前の追加イベント数 $3=終端後の追加イベント数 $4=終端後のポート(既定0031)
  python3 - "$1" "$2" "$3" "${4:-0031}" <<'EOF'
import sys
path, pre, post = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
post_port = sys.argv[4]
rows=[]; seq=[0]
def ev(cpu,kind,port):
    seq[0]+=1
    rows.append(f"{seq[0]:>6} {seq[0]:>6}      0  {cpu:<4}  {kind:<4}  {port}   00   0100")
for _ in range(pre): ev("main","IN","00FE")      # バルク手前
for _ in range(3):   ev("sub","OUT","00FC")      # バルク本体
for _ in range(post): ev("main","OUT",post_port)  # バルク終端以降
ev("main","IN","00FE")
with open(path,"w") as f:
    f.write("# diag_post_bulk_selftest の合成フィクスチャ(公式データ不使用)\n")
    f.write("core      : (テスト用ダミー)\nframes    : 1\n\n")
    f.write("# main\n# seq    clock   frame  cpu   kind  port  value  pc\n")
    f.write("\n".join(rows)+"\n")
EOF
}

say "同一のログ同士では分岐なしと報告すること"
gen "$WORK/a.iolog.txt" 5 4
gen "$WORK/a2.iolog.txt" 5 4
out="$(python3 tools/diag_post_bulk.py "$WORK/a.iolog.txt" "$WORK/a2.iolog.txt" 2>&1)"
if echo "$out" | grep -q "構造的に一致"; then
  ok "同一ログでは分岐を報告しない（false positive 無し）"
else
  ng "同一ログなのに分岐を報告した"; echo "$out" | sed 's/^/  /'; overall_rc=1
fi

# 注意: この比較器は**連続する同一キーを畳み込む**ので、「同じ種類の
# イベントが何回続いたか」の違いは意図的に検出しない（ポーリング回数の
# 揺れを分岐と取り違えないため）。したがって陽性対照は**キーそのもの**
# （cpu/kind/port）を変える壊し方にしないと空振りする——最初は件数だけを
# 変えた対照を書いてしまい、まさに空振りした。
say "陽性対照: バルク終端以降のイベント種別を変えると分岐を検出すること"
gen "$WORK/b.iolog.txt" 5 4 "0040"
out="$(python3 tools/diag_post_bulk.py "$WORK/a.iolog.txt" "$WORK/b.iolog.txt" 2>&1)"
if echo "$out" | grep -q "最初の構造的分岐"; then
  ok "終端以降の違いを検出した"
else
  ng "終端以降を変えたのに検出しなかった（検出力が無い）"; echo "$out" | sed 's/^/  /'; overall_rc=1
fi

say "陽性対照: バルク終端より手前を変えても分岐を検出しないこと（守備範囲の確認）"
gen "$WORK/c.iolog.txt" 40 4
out="$(python3 tools/diag_post_bulk.py "$WORK/a.iolog.txt" "$WORK/c.iolog.txt" 2>&1)"
if echo "$out" | grep -q "構造的に一致"; then
  ok "手前の違いは（意図どおり）この比較器の対象外"
else
  ng "手前の違いを終端以降の分岐として報告した（区間の取り方が誤っている）"
  echo "$out" | sed 's/^/  /'; overall_rc=1
fi

echo
if [ "$overall_rc" -eq 0 ]; then echo "diag_post_bulk_selftest: OK（全項目）"
else echo "diag_post_bulk_selftest: 失敗あり"; fi
exit "$overall_rc"
