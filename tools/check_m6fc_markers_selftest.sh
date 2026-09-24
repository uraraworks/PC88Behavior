#!/usr/bin/env bash
# tools/check_m6fc_markers.py の検出力自己検査。画面は全て合成データ
# （固有の秘密本文 SECRET_BODY_xxx を含む）で、公式ROM・公式ディスクの
# 実データは一切使わない。
#
# 検査項目:
#   1. `ZQ`+タグ+数値の行が行順・タグ・数値とも正しく抽出される
#      （負数・複数数値を含む）。
#   2. `ZQ`で始まるが形式に合わない行は malformed_marker_rows にだけ
#      数えられ、本文は出ない。
#   3. 小文字 `zq` で始まる行は目印として数えられない（打鍵のエコー対策）。
#   4. 典型的なエコー行（`10 print chr$(90);chr$(81);"ok"`）が目印と
#      数えられない。
#   5. --name で指定した名前の出現回数が大文字小文字を区別して正しい。
#   6. 標準出力・標準エラーのどこにも秘密本文(SECRET_BODY_1等)が出ない。
#   7. 陰性対照: 本文を漏らす壊れた変異体を作ると、上の6番の漏れ検査が
#      それを検出できる(＝検査に検出力がある)こと。
#
# 使い方: tools/check_m6fc_markers_selftest.sh

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO/tools/check_m6fc_markers.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

REPORT="$WORK/report.txt"
{
  printf '# 合成測定報告\n'
  printf '[測定終了時のテキスト画面]\n'
  printf '   0| 10 print chr$(90);chr$(81);"ok"\n'
  printf '   1| ZQbt\n'
  printf '   2| ZQrb 0\n'
  printf '   3| ZQer -1 23\n'
  printf '   4| zqbt\n'
  printf '   5| ZQx\n'
  printf '   6| ZQabSECRET_BODY_1\n'
  printf '   7| this line has QZ7A and QZ7A and qz7a and SECRET_BODY_2\n'
  printf '   8| ZQok   \n'
  printf '\n'
} > "$REPORT"

python3 "$CHECK" --report "$REPORT" --name QZ7A --name SECRETBODY3 \
  >"$WORK/out.json" 2>"$WORK/stderr.txt"
py_rc=$?
out="$(cat "$WORK/out.json")"

if [ "$py_rc" -ne 0 ]; then
  ng "正常な合成レポートでrc=0にならない(rc=$py_rc): $(cat "$WORK/stderr.txt")"
else
  ok "正常な合成レポートでrc=0"
fi

# --- 1・3・4: markers 配列 ------------------------------------------------
marker_check="$(python3 - "$WORK/out.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
markers=d["markers"]
expected=[
    {"row":1,"tag":"bt","numbers":[]},
    {"row":2,"tag":"rb","numbers":[0]},
    {"row":3,"tag":"er","numbers":[-1,23]},
    {"row":8,"tag":"ok","numbers":[]},
]
print("match" if markers==expected else "mismatch:"+json.dumps(markers))
PY
)"
if [ "$marker_check" = "match" ]; then
  ok "markers配列が行順・タグ・数値(負数含む)とも一致し、小文字zqとエコー行は含まれない"
else
  ng "markers配列が期待と一致しない: $marker_check"
fi

# --- 2: malformed_marker_rows --------------------------------------------
malformed="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["malformed_marker_rows"])' "$WORK/out.json")"
if [ "$malformed" = "2" ]; then
  ok "malformed_marker_rows=2(ZQx・ZQabSECRET_BODY_1)"
else
  ng "malformed_marker_rowsが2でない(実際:$malformed)"
fi

# --- 5: name_counts --------------------------------------------------------
name_check="$(python3 - "$WORK/out.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
counts=d["name_counts"]
print("match" if counts=={"QZ7A":2,"SECRETBODY3":0} else "mismatch:"+json.dumps(counts))
PY
)"
if [ "$name_check" = "match" ]; then
  ok "name_countsが大文字小文字を区別して正しい(QZ7A=2, SECRETBODY3=0)"
else
  ng "name_countsが期待と一致しない: $name_check"
fi

# --- 6: 本文が漏れない -----------------------------------------------------
leaked=0
for secret in SECRET_BODY_1 SECRET_BODY_2; do
  if grep -q "$secret" "$WORK/out.json"; then leaked=1; fi
  if grep -q "$secret" "$WORK/stderr.txt"; then leaked=1; fi
done
if [ "$leaked" -eq 0 ]; then
  ok "標準出力・標準エラーのどこにも秘密本文が出ていない"
else
  ng "秘密本文が標準出力または標準エラーに漏れた"
fi

# --- 引数不正・画面節なし --------------------------------------------------
python3 "$CHECK" --report "$WORK/nonexistent.txt" >/dev/null 2>"$WORK/noreport.err"
rc_noreport=$?
if [ "$rc_noreport" -eq 2 ] && [ ! -s "$WORK/noreport.err" -o "$(cat "$WORK/noreport.err")" != "" ]; then
  ok "存在しないレポートをrc=2で拒否した"
else
  ng "存在しないレポートの拒否がrc=2でない(rc=$rc_noreport)"
fi

printf '# 見出しなし\nただのテキスト\n' > "$WORK/no_header.txt"
python3 "$CHECK" --report "$WORK/no_header.txt" >/dev/null 2>"$WORK/noheader.err"
rc_noheader=$?
if [ "$rc_noheader" -eq 2 ]; then
  ok "画面節の見出しが無いレポートをrc=2で拒否した"
else
  ng "画面節が無いレポートの拒否がrc=2でない(rc=$rc_noheader)"
fi

python3 "$CHECK" --report "$REPORT" --name 'bad name!' >/dev/null 2>"$WORK/badname.err"
rc_badname=$?
if [ "$rc_badname" -eq 2 ]; then
  ok "--name の英数字以外指定をrc=2で拒否した"
else
  ng "--name不正の拒否がrc=2でない(rc=$rc_badname)"
fi

# --- 7. 陰性対照: 本文を漏らす変異体は漏れ検査で検出される -----------------
MUTANT="$WORK/mutant_check.py"
sed 's/DEBUG_LEAK_MALFORMED_FOR_SELFTEST = False/DEBUG_LEAK_MALFORMED_FOR_SELFTEST = True/' \
  "$CHECK" > "$MUTANT"
# import先(check_l3_screen_output)を見つけられるよう、元のtools/を優先パスにする。
PYTHONPATH="$REPO/tools" python3 "$MUTANT" --report "$REPORT" --name QZ7A \
  >"$WORK/mutant.out" 2>"$WORK/mutant.err"
mutant_leaked=0
for secret in SECRET_BODY_1; do
  if grep -q "$secret" "$WORK/mutant.out" "$WORK/mutant.err" 2>/dev/null; then
    mutant_leaked=1
  fi
done
if [ "$mutant_leaked" -eq 1 ]; then
  ok "陰性対照: 本文を漏らす変異体では実際に本文が漏れ、漏れ検査に検出力があることを確認した"
else
  ng "陰性対照: 変異体でも本文が漏れなかった(検査の検出力を確認できない)"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"
