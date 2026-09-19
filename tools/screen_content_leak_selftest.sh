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

# --- i. tools/l4_vram_probe.py 差分モード(M7器具4)が本文を漏らさないこと ---
# フィクスチャ: 押す前の写しの文字域に秘密の文字列(SECRETLEAKB)を置き、
# 押した後にその一部の文字を変える(=前が空白でないセルの変化)。さらに
# 別の既知の空白セルへ既知の1文字を置く(=前が空白のセルの変化、陽性対照)。
SECRET_B="SECRETLEAKB"
KNOWN_CHAR_HEX="41"  # 'A'

L4_DIFF_BEFORE="$WORK/l4_diff_before.bin"
L4_DIFF_AFTER="$WORK/l4_diff_after.bin"
python3 - "$L4_DIFF_BEFORE" "$L4_DIFF_AFTER" "$SECRET_B" "$KNOWN_CHAR_HEX" <<'PYEOF'
import sys
before_path, after_path, secret, known_hex = sys.argv[1:5]
secret = secret.encode("ascii")
known_byte = int(known_hex, 16)
ROWS, COLS, STRIDE, ATTR = 25, 80, 120, 40

before = bytearray(b" " * (ROWS * STRIDE))  # 文字域も属性域も既定は空白(0x20)
after = bytearray(before)

# 秘密文字列(前が空白でない)を row=7 col=0 に置き、押した後は末尾1文字だけ変える
row_secret, col_secret = 7, 0
for i, b in enumerate(secret):
    before[row_secret * STRIDE + col_secret + i] = b
    after[row_secret * STRIDE + col_secret + i] = b
after[row_secret * STRIDE + col_secret + len(secret) - 1] = 0x99

# 既知の空白セル(row=12, col=33)に既知の1文字を置く(前が空白, 陽性対照)
row_known, col_known = 12, 33
after[row_known * STRIDE + col_known] = known_byte

# 属性域の既知セル(row=2, 属性内位置5)を変える(ハードウェア設定値として出してよい)
row_attr, pos_attr = 2, 5
before[row_attr * STRIDE + COLS + pos_attr] = 0x00
after[row_attr * STRIDE + COLS + pos_attr] = 0x07

with open(before_path, "wb") as f:
    f.write(bytes(before))
with open(after_path, "wb") as f:
    f.write(bytes(after))
PYEOF

python3 "$L4_PROBE" --diff-before "$L4_DIFF_BEFORE" --diff-after "$L4_DIFF_AFTER" --json \
  > "$WORK/i_diff.out" 2> "$WORK/i_diff.err"
DIFF_RC=$?

if [[ $DIFF_RC -ne 0 ]]; then
  fail "i0. tools/l4_vram_probe.py --diff-* の実行が失敗した (rc=$DIFF_RC)"
else
  pass "i0. tools/l4_vram_probe.py --diff-* は合成入力に対して正常終了する"
fi

# 陽性対照: 既知の空白セル(row0=12,col0=33)の既知文字コードが正しく出る
EXPECT_ADDR_KNOWN=$(python3 -c "print('%04X' % (0xF3C8 + 12*120 + 33))")
if grep -q '"row0": 12' "$WORK/i_diff.out" && grep -q '"col0": 33' "$WORK/i_diff.out" \
   && grep -q "\"addr\": \"$EXPECT_ADDR_KNOWN\"" "$WORK/i_diff.out" \
   && grep -q "\"char_after\": \"$KNOWN_CHAR_HEX\"" "$WORK/i_diff.out"; then
  pass "i1. 差分モード(陽性対照): 空白だった既知セル(12,33,$EXPECT_ADDR_KNOWN)の文字コードを正しく返す"
else
  fail "i1. 差分モード: 空白だった既知セルの検出が期待と異なる"
fi

# 本文漏れ検査: 秘密文字列がどの表現でもどの出力にも出ない。
# 前が空白でなかったセルの前後の値(生バイト・16進)も出ない。
SECRET_B_HEX_LOWER="$(printf '%s' "$SECRET_B" | xxd -p | tr -d '\n')"
SECRET_B_HEX_UPPER="$(printf '%s' "$SECRET_B_HEX_LOWER" | tr 'a-f' 'A-F')"
DIFF_LEAK_FOUND=0
for needle in "$SECRET_B" "$SECRET_B_HEX_LOWER" "$SECRET_B_HEX_UPPER" '"before": "42"' '"after": "99"'; do
  if grep -qF "$needle" "$WORK/i_diff.out" "$WORK/i_diff.err"; then
    DIFF_LEAK_FOUND=1
  fi
done
if [[ $DIFF_LEAK_FOUND -eq 0 ]]; then
  pass "i2. 差分モードはどの表現でも秘密文字列・前が空白でないセルの前後値を出さない"
else
  fail "i2. 差分モードの出力へ秘密文字列または前後値が漏れた"
fi

# 前が空白でなかったセルは was_blank=false のみで検出されること
if grep -q '"row0": 7' "$WORK/i_diff.out" && grep -q '"was_blank": false' "$WORK/i_diff.out"; then
  pass "i3. 前が空白でなかったセル(row0=7)は was_blank=false のみで報告される"
else
  fail "i3. 前が空白でなかったセルの報告形式が期待と異なる"
fi

# 属性域の変化は前後の値ごと出てよい(ハードウェア設定値)
if grep -q '"row0": 2' "$WORK/i_diff.out" && grep -q '"pos0": 5' "$WORK/i_diff.out" \
   && grep -q '"before": "00"' "$WORK/i_diff.out" && grep -q '"after": "07"' "$WORK/i_diff.out"; then
  pass "i4. 属性域の変化(row0=2,pos0=5)は前後の値ごと正しく報告される"
else
  fail "i4. 属性域の変化の報告が期待と異なる"
fi

# --- j. 陰性対照: 差分モードの故障注入(同じ環境変数)で本文が漏れる版に
# すると i2 相当の検査が実際に落ちること(検出力の確認)
if Q88MEASURE_FAULT_LEAK_VRAM_PROBE=1 python3 "$L4_PROBE" \
     --diff-before "$L4_DIFF_BEFORE" --diff-after "$L4_DIFF_AFTER" --json \
     > "$WORK/j_diff_leak.out" 2> "$WORK/j_diff_leak.err"; then
  :
fi
JDIFF_LEAK_FOUND=0
for needle in '"before": "42"' '"after": "99"'; do
  if grep -qF "$needle" "$WORK/j_diff_leak.out" "$WORK/j_diff_leak.err"; then
    JDIFF_LEAK_FOUND=1
  fi
done
if [[ $JDIFF_LEAK_FOUND -eq 1 ]]; then
  pass "j. 陰性対照: 差分モードの故障注入版では前が空白でないセルの前後値が実際に検出される(検出力あり)"
else
  fail "j. 陰性対照: 差分モードの故障注入版でも前後値が検出されなかった(検査に検出力が無い)"
fi

# --- l. --count-only-rows (M7器具4追補、l4-s1b Q2 SHIFT対応) -------------
# フィクスチャ: row0=19(想定のファンクションキー表示行)の、押す前が空白
# だったセルに秘密の文字コードを置き、それ以外の行(row0=3)にも別の既知の
# 空白セルを置く。--count-only-rows 19 を指定すると、19行目は文字コードも
# 位置も出ず件数だけになり、他の行(3)は従来どおり出ることを確認する。
SECRET_ROW_CHAR_HEX="7A"  # 'z' 相当。row0=19に置く「秘密」
KNOWN_ROW3_CHAR_HEX="42"  # 'B' 相当。row0=3(対象外)に置く既知値

L4_CO_BEFORE="$WORK/l4_co_before.bin"
L4_CO_AFTER="$WORK/l4_co_after.bin"
python3 - "$L4_CO_BEFORE" "$L4_CO_AFTER" "$SECRET_ROW_CHAR_HEX" "$KNOWN_ROW3_CHAR_HEX" <<'PYEOF'
import sys
before_path, after_path, row19_hex, row3_hex = sys.argv[1:5]
ROWS, COLS, STRIDE, ATTR = 25, 80, 120, 40
before = bytearray(b" " * (ROWS * STRIDE))
after = bytearray(before)

# row0=19(count-only対象): 押す前が空白だったセルに秘密の文字コードが乗る
after[19 * STRIDE + 40] = int(row19_hex, 16)
# もう1セル、row0=19の別位置にも変化を足す(件数>=2にするため)
after[19 * STRIDE + 41] = int(row19_hex, 16)
# row0=19の属性域にも1件変化を足す
before[19 * STRIDE + COLS + 2] = 0x00
after[19 * STRIDE + COLS + 2] = 0x07

# row0=3(count-only対象外): 従来どおり出てよい
after[3 * STRIDE + 10] = int(row3_hex, 16)

with open(before_path, "wb") as f:
    f.write(bytes(before))
with open(after_path, "wb") as f:
    f.write(bytes(after))
PYEOF

python3 "$L4_PROBE" --diff-before "$L4_CO_BEFORE" --diff-after "$L4_CO_AFTER" \
  --count-only-rows 19 --json \
  > "$WORK/l_co.out" 2> "$WORK/l_co.err"
L_CO_RC=$?

if [[ $L_CO_RC -ne 0 ]]; then
  fail "l0. --count-only-rows 指定時の実行が失敗した (rc=$L_CO_RC)"
else
  pass "l0. --count-only-rows 指定時は正常終了する"
fi

# 秘密(row19の文字コード)がどの表現でも出ないこと
L_LEAK_FOUND=0
for needle in "\"char_after\": \"$SECRET_ROW_CHAR_HEX\"" '"row0": 19, "col0"'; do
  if grep -qF "$needle" "$WORK/l_co.out" "$WORK/l_co.err"; then
    L_LEAK_FOUND=1
  fi
done
if [[ $L_LEAK_FOUND -eq 0 ]]; then
  pass "l1. count-only-rows指定行(19)の文字コード・位置がどちらも出ない"
else
  fail "l1. count-only-rows指定行(19)の文字コードまたは位置が漏れた"
fi

# 件数だけは出ること(文字域2件・属性域1件)
if grep -q '"row0": 19' "$WORK/l_co.out" && grep -q '"char_change_count": 2' "$WORK/l_co.out" \
   && grep -q '"attr_change_count": 1' "$WORK/l_co.out"; then
  pass "l2. count-only-rows指定行(19)の件数(文字2・属性1)は正しく出る"
else
  fail "l2. count-only-rows指定行(19)の件数が期待と異なる"
fi

# 指定していない行(3)は従来どおり文字コード・位置が出ること
if grep -q '"row0": 3' "$WORK/l_co.out" && grep -q '"col0": 10' "$WORK/l_co.out" \
   && grep -q "\"char_after\": \"$KNOWN_ROW3_CHAR_HEX\"" "$WORK/l_co.out"; then
  pass "l3. count-only-rows未指定の行(3)は従来どおり文字コード・位置が出る"
else
  fail "l3. count-only-rows未指定の行(3)の出力が期待と異なる"
fi

# --- l4. 指定しない場合(既定)は、row0=19であっても前が空白だったセルの
# 文字コードがこれまでどおり出ること(既定動作の回帰確認)
python3 "$L4_PROBE" --diff-before "$L4_CO_BEFORE" --diff-after "$L4_CO_AFTER" --json \
  > "$WORK/l4_default.out" 2> "$WORK/l4_default.err"
if grep -q '"row0": 19' "$WORK/l4_default.out" \
   && grep -q "\"char_after\": \"$SECRET_ROW_CHAR_HEX\"" "$WORK/l4_default.out"; then
  pass "l4. --count-only-rows未指定なら従来どおりrow19の文字コードも出る(回帰確認)"
else
  fail "l4. --count-only-rows未指定時の既定動作が変わってしまった"
fi

# --- m. 陰性対照: --count-only-rows の指定を無視する故障注入をすると、
# l1相当の漏れ検査が実際に落ちること(検出力の確認)
if Q88MEASURE_FAULT_IGNORE_COUNT_ONLY_ROWS=1 python3 "$L4_PROBE" \
     --diff-before "$L4_CO_BEFORE" --diff-after "$L4_CO_AFTER" \
     --count-only-rows 19 --json \
     > "$WORK/m_ignore.out" 2> "$WORK/m_ignore.err"; then
  :
fi
if grep -qF "\"char_after\": \"$SECRET_ROW_CHAR_HEX\"" "$WORK/m_ignore.out" "$WORK/m_ignore.err"; then
  pass "m. 陰性対照: --count-only-rows を無視する故障注入版では実際に文字コードが漏れる(検出力あり)"
else
  fail "m. 陰性対照: --count-only-rows を無視する故障注入版でも漏れが検出されなかった(検査に検出力が無い)"
fi

# --- k. 変化なし: 同じ写しどうしを比較すると変化件数0を返す
if python3 "$L4_PROBE" --diff-before "$L4_DIFF_BEFORE" --diff-after "$L4_DIFF_BEFORE" --json \
     > "$WORK/k_diff_same.out" 2> "$WORK/k_diff_same.err" \
   && grep -q '"char_change_count": 0' "$WORK/k_diff_same.out" \
   && grep -q '"attr_change_count": 0' "$WORK/k_diff_same.out"; then
  pass "k. 差分モード: 同じ写しどうしの比較は変化件数0を返す"
else
  fail "k. 差分モード: 同じ写しどうしの比較が変化件数0にならない"
fi

# --- n. --attr-only-rows (M7器具5、l4-s1e Q1向け追加A) が本文を漏らさないこと
# フィクスチャ: row0=8の文字域に秘密文字列を置き、属性域は既知パターン
# (0x1E)にする。--attr-only-rows 8 が属性域だけを返し、文字域(秘密)が
# どこにも現れないことを確認する。
SECRET_N="SECRETLEAKN"
SECRET_N_HEX_LOWER="$(printf '%s' "$SECRET_N" | xxd -p | tr -d '\n')"
SECRET_N_HEX_UPPER="$(printf '%s' "$SECRET_N_HEX_LOWER" | tr 'a-f' 'A-F')"
KNOWN_ATTR_HEX="1E"

L4_ATTR_DUMP="$WORK/l4_attr_dump.bin"
python3 - "$L4_ATTR_DUMP" "$SECRET_N" "$KNOWN_ATTR_HEX" <<'PYEOF'
import sys
out_path, secret, attr_hex = sys.argv[1], sys.argv[2].encode("ascii"), sys.argv[3]
ROWS, COLS, STRIDE, ATTR = 25, 80, 120, 40
buf = bytearray(b" " * (ROWS * STRIDE))
row = 8
for i, b in enumerate(secret):
    buf[row * STRIDE + i] = b
attr_byte = int(attr_hex, 16)
for i in range(ATTR):
    buf[row * STRIDE + COLS + i] = attr_byte
# 対象外の行(row0=9)にも別の秘密を置き、範囲指定が効いていることを確認する
for i, b in enumerate(secret):
    buf[9 * STRIDE + i] = b
with open(out_path, "wb") as f:
    f.write(bytes(buf))
PYEOF

python3 "$L4_PROBE" --vram-dump "$L4_ATTR_DUMP" --attr-only-rows 8 --json \
  > "$WORK/n_attr.out" 2> "$WORK/n_attr.err"
N_RC=$?

if [[ $N_RC -ne 0 ]]; then
  fail "n0. --attr-only-rows の実行が失敗した (rc=$N_RC)"
else
  pass "n0. --attr-only-rows は合成入力に対して正常終了する"
fi

N_LEAK_FOUND=0
for needle in "$SECRET_N" "$SECRET_N_HEX_LOWER" "$SECRET_N_HEX_UPPER"; do
  if grep -qF "$needle" "$WORK/n_attr.out" "$WORK/n_attr.err"; then
    N_LEAK_FOUND=1
  fi
done
if [[ $N_LEAK_FOUND -eq 0 ]]; then
  pass "n1. --attr-only-rows はどの表現でも秘密の文字列(=画面本文)を出さない"
else
  fail "n1. --attr-only-rows の出力へ秘密の文字列が漏れた"
fi

# 陽性対照: 指定行(8)の属性域が既知パターンで正しく返る
EXPECT_ATTR_ALL="$(python3 -c "print('$KNOWN_ATTR_HEX'*40)")"
if grep -q '"row0": 8' "$WORK/n_attr.out" && grep -qF "\"attr_hex\": \"$EXPECT_ATTR_ALL\"" "$WORK/n_attr.out"; then
  pass "n2. --attr-only-rows(陽性対照): 指定行(8)の属性域(全40バイト$KNOWN_ATTR_HEX)を正しく返す"
else
  fail "n2. --attr-only-rows: 指定行の属性域が期待と異なる"
fi

# 対象外の行(9)が attr_only セクションに現れないこと(範囲指定が効いている。
# 全体のJSONには従来モード〔analyze_dumpのnon_marker_rows〕が全行を
# 列挙するため、attr_only セクションだけを取り出して確認する)。
N_ATTR_ROWS9="$(python3 -c "
import json
d = json.load(open('$WORK/n_attr.out'))
rows = [e['row0'] for e in d['attr_only'][0]['attr_rows']]
print(9 in rows)
")"
if [[ "$N_ATTR_ROWS9" == "False" ]]; then
  pass "n3. --attr-only-rows: 指定していない行(9)はattr_onlyセクションに現れない"
else
  fail "n3. --attr-only-rows: 指定していない行(9)がattr_onlyセクションに現れた"
fi

# --- o. 陰性対照: --attr-only-rows の故障注入(文字域を混ぜる)で
# 実際に秘密文字列が検出されること(検出力の確認)
if Q88MEASURE_FAULT_LEAK_VRAM_PROBE=1 python3 "$L4_PROBE" \
     --vram-dump "$L4_ATTR_DUMP" --attr-only-rows 8 --json \
     > "$WORK/o_attr_leak.out" 2> "$WORK/o_attr_leak.err"; then
  :
fi
O_LEAK_FOUND=0
for needle in "$SECRET_N" "$SECRET_N_HEX_LOWER" "$SECRET_N_HEX_UPPER"; do
  if grep -qF "$needle" "$WORK/o_attr_leak.out" "$WORK/o_attr_leak.err"; then
    O_LEAK_FOUND=1
  fi
done
if [[ $O_LEAK_FOUND -eq 1 ]]; then
  pass "o. 陰性対照: --attr-only-rows の故障注入版では実際に秘密文字列が検出される(検出力あり)"
else
  fail "o. 陰性対照: --attr-only-rows の故障注入版でも秘密文字列が検出されなかった(検査に検出力が無い)"
fi

# --- p. --nonblank-summary-rows (M7器具6、l4-s1e Q3向け追加B) が
# 本文を漏らさないこと。
# フィクスチャ: row0=11の文字域に、col0=15,30,45の3か所だけ非空白セルを
# 秘密の文字コードで置く(値は 'q'=0x71 相当。実データと混同しない値)。
# --nonblank-summary-rows 11 が件数3・位置範囲(15,45)だけを返し、文字
# コードも各セルの個別位置も出ないことを確認する。
SECRET_P_CHAR_HEX="71"  # 'q' 相当。個別セルの値としては出てはいけない

L4_NB_DUMP="$WORK/l4_nb_dump.bin"
python3 - "$L4_NB_DUMP" "$SECRET_P_CHAR_HEX" <<'PYEOF'
import sys
out_path, char_hex = sys.argv[1], sys.argv[2]
ROWS, COLS, STRIDE, ATTR = 25, 80, 120, 40
buf = bytearray(b" " * (ROWS * STRIDE))
row = 11
b = int(char_hex, 16)
for col in (15, 30, 45):
    buf[row * STRIDE + col] = b
# 対象外の行(row0=12)にも非空白セルを置き、範囲指定が効いていることを確認する
buf[12 * STRIDE + 0] = b
with open(out_path, "wb") as f:
    f.write(bytes(buf))
PYEOF

python3 "$L4_PROBE" --vram-dump "$L4_NB_DUMP" --nonblank-summary-rows 11 --json \
  > "$WORK/p_nb.out" 2> "$WORK/p_nb.err"
P_RC=$?

if [[ $P_RC -ne 0 ]]; then
  fail "p0. --nonblank-summary-rows の実行が失敗した (rc=$P_RC)"
else
  pass "p0. --nonblank-summary-rows は合成入力に対して正常終了する"
fi

# 本文漏れ検査: 文字コードそのもの・個別セルのcol0(15,30,45)が出ない。
P_LEAK_FOUND=0
for needle in "\"char\": \"$SECRET_P_CHAR_HEX\"" '"col0": 15' '"col0": 30' '"col0": 45'; do
  if grep -qF "$needle" "$WORK/p_nb.out" "$WORK/p_nb.err"; then
    P_LEAK_FOUND=1
  fi
done
if [[ $P_LEAK_FOUND -eq 0 ]]; then
  pass "p1. --nonblank-summary-rows は文字コード・個別セル位置を出さない"
else
  fail "p1. --nonblank-summary-rows の出力へ文字コードまたは個別セル位置が漏れた"
fi

# 陽性対照: 指定行(11)の件数3・位置範囲(min=15,max=45)を正しく返す
if grep -q '"row0": 11' "$WORK/p_nb.out" && grep -q '"nonblank_count": 3' "$WORK/p_nb.out" \
   && grep -q '"min_col0": 15' "$WORK/p_nb.out" && grep -q '"max_col0": 45' "$WORK/p_nb.out"; then
  pass "p2. --nonblank-summary-rows(陽性対照): 指定行(11)の件数3・位置範囲(15,45)を正しく返す"
else
  fail "p2. --nonblank-summary-rows: 指定行の件数・位置範囲が期待と異なる"
fi

# 対象外の行(12)が nonblank_summary セクションに現れないこと
# (attr_onlyと同じ理由でセクションを絞って確認する)。
P_NB_ROWS12="$(python3 -c "
import json
d = json.load(open('$WORK/p_nb.out'))
rows = [e['row0'] for e in d['nonblank_summary'][0]['nonblank_summary']]
print(12 in rows)
")"
if [[ "$P_NB_ROWS12" == "False" ]]; then
  pass "p3. --nonblank-summary-rows: 指定していない行(12)はnonblank_summaryセクションに現れない"
else
  fail "p3. --nonblank-summary-rows: 指定していない行(12)がnonblank_summaryセクションに現れた"
fi

# --- q. 陰性対照: --nonblank-summary-rows の故障注入(個別セル位置・文字
# コードを混ぜる)で実際に検出されること(検出力の確認)
if Q88MEASURE_FAULT_LEAK_VRAM_PROBE=1 python3 "$L4_PROBE" \
     --vram-dump "$L4_NB_DUMP" --nonblank-summary-rows 11 --json \
     > "$WORK/q_nb_leak.out" 2> "$WORK/q_nb_leak.err"; then
  :
fi
Q_LEAK_FOUND=0
for needle in "\"char\": \"$SECRET_P_CHAR_HEX\"" '"col0": 15'; do
  if grep -qF "$needle" "$WORK/q_nb_leak.out" "$WORK/q_nb_leak.err"; then
    Q_LEAK_FOUND=1
  fi
done
if [[ $Q_LEAK_FOUND -eq 1 ]]; then
  pass "q. 陰性対照: --nonblank-summary-rows の故障注入版では実際に個別位置・文字コードが検出される(検出力あり)"
else
  fail "q. 陰性対照: --nonblank-summary-rows の故障注入版でも検出されなかった(検査に検出力が無い)"
fi

# --- r. 0件の扱い: 非空白セルが無い行は nonblank_count=0, min/max=null
L4_NB_EMPTY="$WORK/l4_nb_empty.bin"
python3 -c "
open('$L4_NB_EMPTY','wb').write(bytes([0x20]*3000))
"
python3 "$L4_PROBE" --vram-dump "$L4_NB_EMPTY" --nonblank-summary-rows 0 --json \
  > "$WORK/r_nb_empty.out" 2> "$WORK/r_nb_empty.err"
if grep -q '"nonblank_count": 0' "$WORK/r_nb_empty.out" \
   && grep -q '"min_col0": null' "$WORK/r_nb_empty.out" \
   && grep -q '"max_col0": null' "$WORK/r_nb_empty.out"; then
  pass "r. --nonblank-summary-rows: 非空白セルが無い行は件数0・位置範囲nullを返す"
else
  fail "r. --nonblank-summary-rows: 非空白セルが無い行の扱いが期待と異なる"
fi

# --- s. --row-signature (M7器具その7、l4-c2向け追加C) が本文を漏らさず、
# 件数・SHA-256だけで一致/不一致を判定できること -----------------------
# フィクスチャ: row0=6の文字域にエラー文言相当の秘密文字列を置いた写しを
# 2つ用意する。s1は完全に同じ内容の複製(決定論性・一致確認用)、s2は
# 1バイトだけ違える(不一致確認用)。row0=7には別の秘密を置き、対象外の
# 行として現れないことを確認する。
SECRET_S="SYNTAX ERRORXYZQ"
SECRET_S_HEX_LOWER="$(printf '%s' "$SECRET_S" | xxd -p | tr -d '\n')"
SECRET_S_HEX_UPPER="$(printf '%s' "$SECRET_S_HEX_LOWER" | tr 'a-f' 'A-F')"

make_row_sig_dump() {
  # $1=出力パス $2=row6に置く文字列 $3=row6末尾1バイトの16進(空なら変更なし)
  python3 - "$1" "$2" "$3" "$SECRET_S" <<'PYEOF'
import sys
out_path, row6_text, row6_last_hex, secret_other = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].encode("ascii")
ROWS, COLS, STRIDE, ATTR = 25, 80, 120, 40
buf = bytearray(b" " * (ROWS * STRIDE))
text = row6_text.encode("ascii")
row = 6
for i, b in enumerate(text):
    buf[row * STRIDE + 2 + i] = b
if row6_last_hex:
    buf[row * STRIDE + 2 + len(text) - 1] = int(row6_last_hex, 16)
# 対象外の行(row0=7)にも別の秘密を置く(範囲指定が効いているか確認用)
for i, b in enumerate(secret_other):
    buf[7 * STRIDE + i] = b
with open(out_path, "wb") as f:
    f.write(bytes(buf))
PYEOF
}

L4_RS_A="$WORK/l4_rowsig_a.bin"
L4_RS_A_COPY="$WORK/l4_rowsig_a_copy.bin"
L4_RS_B="$WORK/l4_rowsig_b.bin"
make_row_sig_dump "$L4_RS_A" "$SECRET_S" ""
make_row_sig_dump "$L4_RS_A_COPY" "$SECRET_S" ""
make_row_sig_dump "$L4_RS_B" "$SECRET_S" "5A"  # 末尾1バイトだけ 'Z'(0x5A)に差し替え

python3 "$L4_PROBE" --vram-dump "$L4_RS_A" --row-signature 6 --json \
  > "$WORK/s_a.out" 2> "$WORK/s_a.err"
S_RC=$?
python3 "$L4_PROBE" --vram-dump "$L4_RS_A_COPY" --row-signature 6 --json \
  > "$WORK/s_a_copy.out" 2> "$WORK/s_a_copy.err"
python3 "$L4_PROBE" --vram-dump "$L4_RS_B" --row-signature 6 --json \
  > "$WORK/s_b.out" 2> "$WORK/s_b.err"

if [[ $S_RC -ne 0 ]]; then
  fail "s0. --row-signature の実行が失敗した (rc=$S_RC)"
else
  pass "s0. --row-signature は合成入力に対して正常終了する"
fi

# 本文漏れ検査: どの写しの出力にも秘密文字列(生・16進大小)が現れないこと
S_LEAK_FOUND=0
for f in "$WORK/s_a.out" "$WORK/s_a.err" "$WORK/s_a_copy.out" "$WORK/s_a_copy.err" \
         "$WORK/s_b.out" "$WORK/s_b.err"; do
  for needle in "$SECRET_S" "$SECRET_S_HEX_LOWER" "$SECRET_S_HEX_UPPER"; do
    if grep -qF "$needle" "$f"; then
      S_LEAK_FOUND=1
    fi
  done
done
if [[ $S_LEAK_FOUND -eq 0 ]]; then
  pass "s1. --row-signature はどの表現でも秘密の文字列(=画面本文)を出さない"
else
  fail "s1. --row-signature の出力へ秘密の文字列が漏れた"
fi

# 決定論性(陽性対照): 完全に同じ内容の2つの写しは row_sha256 が一致する
SHA_A="$(python3 -c "
import json
print(json.load(open('$WORK/s_a.out'))['row_signature'][0]['row_signatures'][0]['row_sha256'])
")"
SHA_A_COPY="$(python3 -c "
import json
print(json.load(open('$WORK/s_a_copy.out'))['row_signature'][0]['row_signatures'][0]['row_sha256'])
")"
SHA_B="$(python3 -c "
import json
print(json.load(open('$WORK/s_b.out'))['row_signature'][0]['row_signatures'][0]['row_sha256'])
")"

if [[ -n "$SHA_A" && "$SHA_A" == "$SHA_A_COPY" ]]; then
  pass "s2. --row-signature(陽性対照): 同じ内容の2写しは row_sha256 が一致する"
else
  fail "s2. --row-signature: 同じ内容の2写しで row_sha256 が一致しない"
fi

# 1バイト違えば不一致になること
if [[ -n "$SHA_B" && "$SHA_A" != "$SHA_B" ]]; then
  pass "s3. --row-signature: 1バイト違う写しは row_sha256 が不一致になる"
else
  fail "s3. --row-signature: 1バイト違う写しで row_sha256 が一致してしまった"
fi

# 対象外の行(7)が row_signature セクションに現れないこと
S_ROWS7="$(python3 -c "
import json
d = json.load(open('$WORK/s_a.out'))
rows = [e['row0'] for e in d['row_signature'][0]['row_signatures']]
print(7 in rows)
")"
if [[ "$S_ROWS7" == "False" ]]; then
  pass "s4. --row-signature: 指定していない行(7)はrow_signatureセクションに現れない"
else
  fail "s4. --row-signature: 指定していない行(7)がrow_signatureセクションに現れた"
fi

# 件数(nonblank_count)が期待どおり出ること(SECRET_S のうち空白でない文字数分)
EXPECT_NONBLANK="$(python3 -c "print(sum(1 for c in '$SECRET_S' if c != ' '))")"
if grep -q "\"row0\": 6" "$WORK/s_a.out" && grep -q "\"nonblank_count\": $EXPECT_NONBLANK" "$WORK/s_a.out"; then
  pass "s5. --row-signature(陽性対照): 指定行(6)の非空白セル件数($EXPECT_NONBLANK)を正しく返す"
else
  fail "s5. --row-signature: 指定行の非空白セル件数が期待と異なる"
fi

# --- t. 陰性対照: --row-signature の故障注入(文字域を混ぜる)で実際に
# 秘密文字列が検出されること(検出力の確認)
if Q88MEASURE_FAULT_LEAK_ROW_SIGNATURE=1 python3 "$L4_PROBE" \
     --vram-dump "$L4_RS_A" --row-signature 6 --json \
     > "$WORK/t_leak.out" 2> "$WORK/t_leak.err"; then
  :
fi
T_LEAK_FOUND=0
for needle in "$SECRET_S" "$SECRET_S_HEX_LOWER" "$SECRET_S_HEX_UPPER"; do
  if grep -qF "$needle" "$WORK/t_leak.out" "$WORK/t_leak.err"; then
    T_LEAK_FOUND=1
  fi
done
if [[ $T_LEAK_FOUND -eq 1 ]]; then
  pass "t. 陰性対照: --row-signature の故障注入版では実際に秘密文字列が検出される(検出力あり)"
else
  fail "t. 陰性対照: --row-signature の故障注入版でも秘密文字列が検出されなかった(検査に検出力が無い)"
fi

# --- u. q88measure 本体(--out無し実行)が画面本文を標準出力・標準エラーへ
# 出さないこと（l4-s1h 事故、disclosure-2026-09-19.md の対処）。
# a.〜t. は check_l3_*.py・l4_vram_probe.py という「後段の読み手」の
# 検出力だったが、事故の実体は「そもそも q88measure 自身が --out 無しで
# 走ると画面本文を作業端末（標準出力）へ書いていた」ことなので、
# ここだけは自作ROMで q88measure を実際に走らせて確かめる
# （公式ROM・公式ディスクは使わない。make_test_rom.py の合成ROMのみ）。
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
U_VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
U_CORE="$(ls "$U_VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [[ -z "$U_CORE" ]]; then
  fail "u0. コアが無い(vendor/quasi88-libretro)。先に tools/setup_harness.sh を実行すること"
else
  make -s -C "$REPO/tools/harness/frontend"
  Q88MEASURE="$REPO/tools/harness/frontend/q88measure"
  U_ROMDIR="$WORK/u_rom"
  mkdir -p "$U_ROMDIR"
  python3 "$REPO/tools/harness/make_test_rom.py" "$U_ROMDIR" > /dev/null

  # 画面節の見出し。write_screen() が出す側にしか現れない
  # （write_screen_redacted_notice() は見出し自体を出さない設計）。
  SCREEN_HEADER="測定終了時のテキスト画面"

  # u1. 陽性対照: --out ありのファイル側は従来どおり write_screen() の
  # 本物の画面節（見出し行つき）が書かれていること。ここが崩れると
  # check_l3_screen_output.py・check_l3_entry_screen.py が読めなくなる。
  "$Q88MEASURE" --core "$U_CORE" --rom-dir "$U_ROMDIR" --frames 8 \
    --out "$WORK/u_out_report.txt" --expect-exec 0x0000 \
    > "$WORK/u_out.stdout.txt" 2> "$WORK/u_out.stderr.txt"
  U_OUT_RC=$?
  if [[ $U_OUT_RC -ne 0 ]]; then
    fail "u1. q88measure(--out あり)の実行が失敗した (rc=$U_OUT_RC)"
  elif grep -qF "$SCREEN_HEADER" "$WORK/u_out_report.txt"; then
    pass "u1. --out のファイルには従来どおり画面節の見出しが入っている(既存ツールの前提を維持)"
  else
    fail "u1. --out のファイルに画面節の見出しが見当たらない(既存ツールが読めなくなる)"
  fi

  # u2. 本題: --out 無しで実行したときの標準出力・標準エラーのどちらにも、
  # 画面節の見出し（および行データ）が1つも現れないこと。見出し自体も
  # write_screen_redacted_notice() では出さない設計なので、見出しの有無が
  # そのまま「本物のwrite_screen()が呼ばれたか」の判定になる。
  "$Q88MEASURE" --core "$U_CORE" --rom-dir "$U_ROMDIR" --frames 8 \
    --expect-exec 0x0000 \
    > "$WORK/u2.stdout.txt" 2> "$WORK/u2.stderr.txt"
  U2_RC=$?
  if [[ $U2_RC -ne 0 ]]; then
    fail "u2. q88measure(--out 無し)の実行が失敗した (rc=$U2_RC)"
  elif grep -qF "$SCREEN_HEADER" "$WORK/u2.stdout.txt" "$WORK/u2.stderr.txt"; then
    fail "u2. --out 無しの標準出力・標準エラーへ画面節(見出しまたは行データ)が漏れた"
  else
    pass "u2. --out 無しでも標準出力・標準エラーへ画面節(見出し・行データとも)は出ない"
  fi

  # u3. --dump-text も同じ経路(標準エラー)なので同様に漏れないこと。
  "$Q88MEASURE" --core "$U_CORE" --rom-dir "$U_ROMDIR" --frames 8 \
    --dump-text --out "$WORK/u3_out_report.txt" --expect-exec 0x0000 \
    > "$WORK/u3.stdout.txt" 2> "$WORK/u3.stderr.txt"
  U3_RC=$?
  if [[ $U3_RC -ne 0 ]]; then
    fail "u3. q88measure(--dump-text)の実行が失敗した (rc=$U3_RC)"
  elif grep -qF "$SCREEN_HEADER" "$WORK/u3.stdout.txt" "$WORK/u3.stderr.txt"; then
    fail "u3. --dump-text の標準出力・標準エラーへ画面節が漏れた"
  else
    pass "u3. --dump-text でも標準出力・標準エラーへ画面節は出ない(--outのファイル側は別途u1.相当で健全)"
  fi

  # u4. 陰性対照: Q88MEASURE_FAULT_SHOW_SCREEN_ON_STDOUT で修正前の挙動
  # （--out 無しでも標準出力に画面節が出る）を再現し、u2. 相当の判定が
  # 実際に落ちる(検出力を持つ)ことを確認する。
  Q88MEASURE_FAULT_SHOW_SCREEN_ON_STDOUT=1 "$Q88MEASURE" \
    --core "$U_CORE" --rom-dir "$U_ROMDIR" --frames 8 --expect-exec 0x0000 \
    > "$WORK/u4.stdout.txt" 2> "$WORK/u4.stderr.txt"
  if grep -qF "$SCREEN_HEADER" "$WORK/u4.stdout.txt" "$WORK/u4.stderr.txt"; then
    pass "u4. 陰性対照: 故障注入版(修正前相当)ではu2.相当の判定が正しく落ちる(検出力あり)"
  else
    fail "u4. 陰性対照: 故障注入版でも画面節が検出されなかった(検査に検出力が無い)"
  fi
fi

exit "$FAIL"
