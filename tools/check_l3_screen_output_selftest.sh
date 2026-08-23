#!/usr/bin/env bash
# check_l3_screen_output.py の検出力自己検査。画面は全て合成データ。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO/tools/check_l3_screen_output.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

make_report() {
  local path="$1" first="$2" second="$3" extra="${4:-}"
  {
    printf '# 合成測定報告\n'
    printf '[測定終了時のテキスト画面]\n'
    printf '   0| %s\n' "$first"
    printf '   4| %s\n' "$second"
    if [ -n "$extra" ]; then
      printf '   9| %s\n' "$extra"
    fi
    printf '\n'
  } > "$path"
}

make_report "$WORK/base.txt" ALPHA OMEGA
make_report "$WORK/one-char.txt" ALPHX OMEGA
make_report "$WORK/one-line.txt" ALPHA OMEGA EXTRA

base_stats="$(python3 "$CHECK" --report "$WORK/base.txt")" || {
  ng "基準画面を署名化できない"
  exit "$rc"
}
base_lines="$(printf '%s\n' "$base_stats" | awk -F= '$1=="line_count"{print $2}')"
base_chars="$(printf '%s\n' "$base_stats" | awk -F= '$1=="char_count"{print $2}')"
base_sha="$(printf '%s\n' "$base_stats" | awk -F= '$1=="sha256"{print $2}')"
printf 'base\t%s\t%s\t%s\n' "$base_lines" "$base_chars" "$base_sha" \
  > "$WORK/expected.tsv"

if python3 "$CHECK" --report "$WORK/base.txt" --expected "$WORK/expected.tsv" \
     --scenario base > "$WORK/base.out" \
   && grep -q '^screen_expectation=match$' "$WORK/base.out"; then
  ok "正しいハッシュ・行数・文字数を一致判定"
else
  ng "正しい期待値を一致判定できない"
fi

if python3 "$CHECK" --report "$WORK/base.txt" --compare-report "$WORK/one-char.txt" \
     > "$WORK/one-char.out"; then
  ng "1文字違う画面が一致してしまった"
elif grep -q '^screen_compare=mismatch$' "$WORK/one-char.out" \
  && grep -q '^first_content_mismatch_row=0$' "$WORK/one-char.out" \
  && grep -q '^first_content_mismatch_column=4$' "$WORK/one-char.out" \
  && grep -q '^first_content_mismatch_kind=same_length_replacement$' "$WORK/one-char.out"; then
  ok "1文字差を本文なしで位置・置換差として検出"
else
  ng "1文字差の位置・分類が不正"
fi

if python3 "$CHECK" --report "$WORK/base.txt" --compare-report "$WORK/one-line.txt" \
     > "$WORK/one-line.out"; then
  ng "1行多い画面が一致してしまった"
elif grep -q '^screen_compare=mismatch$' "$WORK/one-line.out" \
  && grep -q '^target_only_line_count=1$' "$WORK/one-line.out" \
  && grep -q '^first_target_only_row=9$' "$WORK/one-line.out"; then
  ok "1行追加を本文なしで位置・target側のみとして検出"
else
  ng "1行追加差の位置・分類が不正"
fi

if grep -qE 'ALPHA|ALPHX|OMEGA|EXTRA' "$WORK/one-char.out" "$WORK/one-line.out"; then
  ng "比較結果へ画面本文が漏れた"
else
  ok "比較結果に画面本文を出力しない"
fi

exit "$rc"
