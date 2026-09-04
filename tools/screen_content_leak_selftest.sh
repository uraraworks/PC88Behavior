#!/usr/bin/env bash
# tools/screen_content_leak_selftest.sh
#
# tools/check_l3_screen_output.py・tools/check_l3_entry_screen.py が
# 画面本文を一切標準出力・標準エラーに出さないことを検査する。
# CLAUDE.md / docs/notes の方針どおり、検査器を信用してよいのは
# わざと壊して検出できることを確かめた後だけ（tools/redact_iolog_selftest.sh・
# tools/stage_disk_by_digest_selftest.sh の作法を踏襲）。
#
# フィクスチャは全て自作の合成データ。公式ROM・公式ディスクは不要かつ
# 未使用。フィクスチャの本文には特徴的な合成文字列（実データと混同
# しようがない文字列）を埋め込み、それが出力に現れないことを確認する。
#
# 使い方: tools/screen_content_leak_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCREEN_OUTPUT="$SCRIPT_DIR/check_l3_screen_output.py"
ENTRY_SCREEN="$SCRIPT_DIR/check_l3_entry_screen.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

CANARY="ZQCANARY7F3D1A9E"

# --- フィクスチャ（合成。実データ不使用）------------------------------
# check_l3_screen_output.py 用: 「測定終了時のテキスト画面」節にカナリア
# 文字列を含む行を混ぜる。
REPORT_A="$WORK/report_a.txt"
{
  printf '# 合成測定報告A\n'
  printf '[測定終了時のテキスト画面]\n'
  printf '   0| %s START\n' "$CANARY"
  printf '   4| %s END\n' "$CANARY"
  printf '\n'
} > "$REPORT_A"

REPORT_B="$WORK/report_b.txt"
{
  printf '# 合成測定報告B\n'
  printf '[測定終了時のテキスト画面]\n'
  printf '   0| %s STOP\n' "$CANARY"
  printf '   4| %s END\n' "$CANARY"
  printf '\n'
} > "$REPORT_B"

expected_stats="$(python3 "$SCREEN_OUTPUT" --report "$REPORT_A")"
exp_lines="$(printf '%s\n' "$expected_stats" | awk -F= '$1=="line_count"{print $2}')"
exp_chars="$(printf '%s\n' "$expected_stats" | awk -F= '$1=="char_count"{print $2}')"
exp_sha="$(printf '%s\n' "$expected_stats" | awk -F= '$1=="sha256"{print $2}')"
EXPECTED_TSV="$WORK/expected.tsv"
printf 'scenA\t%s\t%s\t%s\n' "$exp_lines" "$exp_chars" "$exp_sha" > "$EXPECTED_TSV"

# check_l3_entry_screen.py 用: --scenario drive1 が判定に使う "files 1" と
# 一覧・直後の "ok" を含みつつ、本文にはカナリア文字列も混ぜておく。
# reached_output_success() は「全体で12行以上、files直後にOkが1つ以上先に
# 現れる」ことを要求するので、埋め草の行を足して行数条件を満たす。
ENTRY_REPORT="$WORK/entry_report.txt"
{
  printf '# 合成測定報告(entry) %s\n' "$CANARY"
  printf '[測定終了時のテキスト画面]\n'
  printf '   0| files 1\n'
  printf '   1| %s.D88\n' "$CANARY"
  printf '   2| filler-a\n'
  printf '   3| filler-b\n'
  printf '   4| filler-c\n'
  printf '   5| filler-d\n'
  printf '   6| filler-e\n'
  printf '   7| filler-f\n'
  printf '   8| filler-g\n'
  printf '   9| filler-h\n'
  printf '  10| filler-i\n'
  printf '  11| ok\n'
  printf '\n'
} > "$ENTRY_REPORT"

# --- a. check_l3_screen_output.py の各モードでカナリアが出ないこと -------
python3 "$SCREEN_OUTPUT" --report "$REPORT_A" \
  > "$WORK/a_plain.out" 2> "$WORK/a_plain.err"
python3 "$SCREEN_OUTPUT" --report "$REPORT_A" --expected "$EXPECTED_TSV" --scenario scenA \
  > "$WORK/a_expected.out" 2> "$WORK/a_expected.err"
python3 "$SCREEN_OUTPUT" --report "$REPORT_A" --compare-report "$REPORT_B" \
  > "$WORK/a_compare.out" 2> "$WORK/a_compare.err"

if grep -qF "$CANARY" \
     "$WORK/a_plain.out" "$WORK/a_plain.err" \
     "$WORK/a_expected.out" "$WORK/a_expected.err" \
     "$WORK/a_compare.out" "$WORK/a_compare.err"; then
  fail "a. check_l3_screen_output.py の出力へ画面本文(カナリア)が漏れた"
else
  pass "a. check_l3_screen_output.py はどのモードでも画面本文を出さない"
fi

# --- b. check_l3_entry_screen.py でもカナリアが出ないこと ----------------
python3 "$ENTRY_SCREEN" --report "$ENTRY_REPORT" --scenario drive1 \
  > "$WORK/b_entry.out" 2> "$WORK/b_entry.err"

if grep -qF "$CANARY" "$WORK/b_entry.out" "$WORK/b_entry.err"; then
  fail "b. check_l3_entry_screen.py の出力へ画面本文(カナリア)が漏れた"
else
  pass "b. check_l3_entry_screen.py は完了判定(真偽)を本文なしで返す"
fi

# --- c. 一致／不一致の判定そのものが正しく働くこと ------------------------
if python3 "$SCREEN_OUTPUT" --report "$REPORT_A" --expected "$EXPECTED_TSV" --scenario scenA \
     > /dev/null 2>&1; then
  pass "c1. 同一画面どうしは一致(rc=0)と判定される"
else
  fail "c1. 同一画面どうしが一致と判定されない"
fi

if python3 "$SCREEN_OUTPUT" --report "$REPORT_A" --compare-report "$REPORT_B" \
     > /dev/null 2>&1; then
  fail "c2. 内容が違う画面どうしが一致(rc=0)してしまった"
else
  pass "c2. 内容が違う画面どうしは不一致(rc!=0)と判定される"
fi

if python3 "$ENTRY_SCREEN" --report "$ENTRY_REPORT" --scenario drive1 > /dev/null 2>&1; then
  pass "c3. 完了条件を満たす画面はreached(rc=0)と判定される"
else
  fail "c3. 完了条件を満たす画面がreachedと判定されない"
fi

# --- d. 陰性対照: わざと本文を出力する壊れた版を作り、a.の検査が落ちること --
BROKEN_SCREEN_OUTPUT="$WORK/broken_check_l3_screen_output.py"
cp "$SCREEN_OUTPUT" "$BROKEN_SCREEN_OUTPUT"
# print_signature() の直後に、行本文を丸ごと標準エラーへ書き出す1行を注入する。
python3 - "$BROKEN_SCREEN_OUTPUT" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
needle = "def read_screen(path: Path) -> list[tuple[int, str]]:"
assert needle in text, "注入対象の関数定義が見つからない"
injected = (
    "def _debug_dump_rows(rows):\n"
    "    import sys as _sys\n"
    "    for _row, _body in rows:\n"
    "        print(f'DEBUG row {_row}: {_body}', file=_sys.stderr)\n\n\n"
    + needle
)
text = text.replace(needle, injected, 1)
text = text.replace(
    "        rows = read_screen(args.report)\n",
    "        rows = read_screen(args.report)\n        _debug_dump_rows(rows)\n",
    1,
)
open(path, "w", encoding="utf-8").write(text)
PYEOF

python3 "$BROKEN_SCREEN_OUTPUT" --report "$REPORT_A" \
  > "$WORK/broken.out" 2> "$WORK/broken.err"

if grep -qF "$CANARY" "$WORK/broken.out" "$WORK/broken.err"; then
  pass "d. 陰性対照: 本文を出す壊れた版では検査(a.相当)が正しく落ちる（検出力あり）"
else
  fail "d. 陰性対照: 壊れた版でもカナリアが検出されなかった（検査に検出力が無い）"
fi

# 壊れた版は $WORK 配下の一時コピーのみで、tools/ の実体は変更していない。
if [[ -f "$SCREEN_OUTPUT" ]] && ! diff -q "$SCREEN_OUTPUT" "$BROKEN_SCREEN_OUTPUT" > /dev/null 2>&1; then
  pass "e. 壊れた版は一時コピーのみで、tools/check_l3_screen_output.py 本体は無傷"
else
  fail "e. tools/check_l3_screen_output.py 本体が変更されているか、比較に失敗した"
fi

exit "$FAIL"
