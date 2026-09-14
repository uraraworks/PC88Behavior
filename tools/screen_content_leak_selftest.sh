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

# --- f. tools/l4_vram_probe.py (M7器具3) が画面本文を漏らさないこと -------
# フィクスチャは全て自作の合成データ。写しには「秘密の文字列」を複数の
# 表現（生バイト・16進表記・10進表記・1バイトずつ）で埋め込み、目印以外の
# 行の内容としてどの表現でも道具の出力へ現れないことを確認する。
L4_PROBE="$SCRIPT_DIR/l4_vram_probe.py"
SECRET="SECRETLEAK"
SECRET_HEX_LOWER="$(printf '%s' "$SECRET" | xxd -p | tr -d '\n')"
SECRET_HEX_UPPER="$(printf '%s' "$SECRET_HEX_LOWER" | tr 'a-f' 'A-F')"

L4_DUMP="$WORK/l4_dump.bin"
python3 - "$L4_DUMP" "$SECRET" <<'PYEOF'
import sys
out_path, secret = sys.argv[1], sys.argv[2].encode("ascii")
ROWS, COLS, STRIDE, ATTR = 25, 80, 120, 40
buf = bytearray(b"." * (ROWS * STRIDE))

def put(row, col, data):
    for i, b in enumerate(data):
        buf[row * STRIDE + col + i] = b

# 目印 Q7Z: 行3桁10、それ以外の全行には秘密文字列を埋め込む
# (=目印を含まない行のほうが多い状態にする)。
MARKER = b"Q7Z"
put(3, 10, MARKER)
for r in range(ROWS):
    if r == 3:
        continue
    # 生バイトそのまま
    put(r, 0, secret)
    # 1バイトずつ離した表現も混ぜる(結合検出を回避しても漏れないか確認)
    for i, b in enumerate(secret):
        buf[r * STRIDE + 20 + i * 2] = b
# 属性域は全行同じ値にしておく(属性の一致判定に無関係な要因を混ぜない)
for r in range(ROWS):
    for i in range(ATTR):
        buf[r * STRIDE + COLS + i] = 0xAA

with open(out_path, "wb") as f:
    f.write(bytes(buf))
PYEOF

L4_MWL="$WORK/l4_mwl.txt"
{
  printf '# PC88Behavior 範囲指定メモリ書き込み記録\n'
  printf 'range     : F3C8-FF7F\n\n'
  printf '# seq    frame    pc   addr  value\n'
  # 秘密文字列をそのまま連続番地に書く事象を1本混ぜる(値としてログへ入る)。
  seq=1
  addr=0xF500
  for ch in $(printf '%s' "$SECRET" | fold -w1); do
    hex=$(printf '%02X' "'$ch")
    printf '%6d %7d  1000  %04X   %s\n' "$seq" 0 "$addr" "$hex"
    seq=$((seq+1)); addr=$((addr+1))
  done
  printf '# 取りこぼし: 0件 / 総イベント数: %d件\n' "$((seq-1))"
} > "$L4_MWL"

L4_IOLOG="$WORK/l4_io.txt"
{
  printf '# main\n'
  printf '# seq  clock  frame  cpu  kind  port  value  pc\n'
  printf '1  1  0  main  OUT  0050  01  1000\n'
} > "$L4_IOLOG"

python3 "$L4_PROBE" --vram-dump "$L4_DUMP" --marker Q7Z \
  --mem-write-log "$L4_MWL" --iolog "$L4_IOLOG" --json \
  > "$WORK/f_probe.out" 2> "$WORK/f_probe.err"
PROBE_RC=$?

if [[ $PROBE_RC -ne 0 ]]; then
  fail "f0. tools/l4_vram_probe.py の実行が失敗した (rc=$PROBE_RC)"
else
  pass "f0. tools/l4_vram_probe.py は合成入力に対して正常終了する"
fi

LEAK_FOUND=0
for needle in "$SECRET" "$SECRET_HEX_LOWER" "$SECRET_HEX_UPPER"; do
  if grep -qF "$needle" "$WORK/f_probe.out" "$WORK/f_probe.err"; then
    LEAK_FOUND=1
  fi
done
if [[ $LEAK_FOUND -eq 0 ]]; then
  pass "f1. tools/l4_vram_probe.py はどの表現でも秘密の文字列(=画面本文)を出さない"
else
  fail "f1. tools/l4_vram_probe.py の出力へ秘密の文字列が漏れた"
fi

# 目印の検出(陽性対照、0始まり): 行頭(row0=0,col0=0)・行末に目印3文字が
# ちょうど収まる位置(row0=5,col0=77)・行またぎ(row0=10,col0=79)の3条件。
# addr = 0xF3C8 + row0*120 + col0 (LOCATE x,y と同じ0始まり)。
L4_DUMP_ORIGIN="$WORK/l4_dump_origin.bin"
python3 - "$L4_DUMP_ORIGIN" <<'PYEOF'
import sys
out_path = sys.argv[1]
ROWS, COLS, STRIDE, ATTR = 25, 80, 120, 40
buf = bytearray(b"." * (ROWS * STRIDE))
MARKER = b"Q7Z"

def put(row0, col0, data):
    # 文字域の平坦インデックス(row0*COLS+col0)基準でバイトを置く。
    # 行をまたぐ場合、物理バッファでは属性域(40バイト)を挟むため、
    # 1バイトごとに物理オフセットへ変換してから書く。
    flat_idx = row0 * COLS + col0
    for i, b in enumerate(data):
        r, c = divmod(flat_idx + i, COLS)
        buf[r * STRIDE + c] = b

put(0, 0, MARKER)    # 行頭
put(5, 77, MARKER)   # 行末(3文字がちょうど収まる最後の位置)
put(10, 79, MARKER)  # 行またぎ(row0=10の末尾からrow0=11の先頭へ)

with open(out_path, "wb") as f:
    f.write(bytes(buf))
PYEOF

python3 "$L4_PROBE" --vram-dump "$L4_DUMP_ORIGIN" --marker Q7Z --json \
  > "$WORK/f2_origin.out" 2> "$WORK/f2_origin.err"

EXPECT_ADDR_HEAD=$(python3 -c "print('%04X' % (0xF3C8 + 0*120 + 0))")
EXPECT_ADDR_TAIL=$(python3 -c "print('%04X' % (0xF3C8 + 5*120 + 77))")
EXPECT_ADDR_SPAN=$(python3 -c "print('%04X' % (0xF3C8 + 10*120 + 79))")

f2_check() {
  local out="$1"
  grep -q '"row0": 0' "$out" && grep -q '"col0": 0' "$out" \
    && grep -q "\"addr\": \"$EXPECT_ADDR_HEAD\"" "$out" \
    && grep -q '"row0": 5' "$out" && grep -q '"col0": 77' "$out" \
    && grep -q "\"addr\": \"$EXPECT_ADDR_TAIL\"" "$out" \
    && grep -q '"row0": 10' "$out" && grep -q '"col0": 79' "$out" \
    && grep -q "\"addr\": \"$EXPECT_ADDR_SPAN\"" "$out" \
    && grep -q '"spans_row_boundary": true' "$out"
}

if f2_check "$WORK/f2_origin.out"; then
  pass "f2. 目印の検出(陽性対照,0始まり): 行頭(0,0,$EXPECT_ADDR_HEAD)・行末(5,77,$EXPECT_ADDR_TAIL)・行またぎ(10,79,$EXPECT_ADDR_SPAN)を正しく返す"
else
  fail "f2. 目印の検出(0始まり)が既知位置と一致しない"
fi

# --- f2n. 陰性対照: 起点を取り違えた故障注入(+1)を入れると f2 の判定がNGになること
Q88MEASURE_FAULT_OFFSET_ORIGIN_VRAM_PROBE=1 python3 "$L4_PROBE" \
  --vram-dump "$L4_DUMP_ORIGIN" --marker Q7Z --json \
  > "$WORK/f2n_origin.out" 2> "$WORK/f2n_origin.err"

if f2_check "$WORK/f2n_origin.out"; then
  fail "f2n. 陰性対照: 起点+1の故障注入版でもf2の判定が通ってしまう(検出力が無い)"
else
  pass "f2n. 陰性対照: 起点+1の故障注入版ではf2の判定が実際にNGになる(検出力あり)"
fi

# --- g. 陰性対照: 故障注入で本文/値を漏らす版にすると、この検査(f1)が落ちること
if Q88MEASURE_FAULT_LEAK_VRAM_PROBE=1 python3 "$L4_PROBE" \
     --vram-dump "$L4_DUMP" --marker Q7Z --mem-write-log "$L4_MWL" --json \
     > "$WORK/g_leak.out" 2> "$WORK/g_leak.err"; then
  :
fi
GLEAK_FOUND=0
for needle in "$SECRET" "$SECRET_HEX_LOWER" "$SECRET_HEX_UPPER"; do
  if grep -qF "$needle" "$WORK/g_leak.out" "$WORK/g_leak.err"; then
    GLEAK_FOUND=1
  fi
done
if [[ $GLEAK_FOUND -eq 1 ]]; then
  pass "g. 陰性対照: 故障注入(環境変数)で漏らす版では実際に秘密文字列が検出される(検出力あり)"
else
  fail "g. 陰性対照: 故障注入版でも秘密文字列が検出されなかった(検査に検出力が無い)"
fi

# --- h. 目印0件の扱い: 目印を含まない写しに対して occurrence_count=0 を返す
L4_DUMP_NOMARK="$WORK/l4_dump_nomark.bin"
python3 -c "
open('$L4_DUMP_NOMARK','wb').write(bytes([0xAA]*3000))
"
python3 "$L4_PROBE" --vram-dump "$L4_DUMP_NOMARK" --marker Q7Z --json \
  > "$WORK/h_nomark.out" 2> "$WORK/h_nomark.err"
if grep -q '"occurrence_count": 0' "$WORK/h_nomark.out"; then
  pass "h. 目印0件の写しに対して occurrence_count=0 を返す"
else
  fail "h. 目印0件のときの扱いが期待と異なる"
fi

exit "$FAIL"
