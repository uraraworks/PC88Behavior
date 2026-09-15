#!/usr/bin/env bash
# tools/l4_basic_selftest.sh — M7段階3b: BASICの核(直接モードのPRINT)の
# 自己検査。**公式ROMは要らない**（自作main ROMだけで完結する。
# tools/l3_main_selftest.shと同じ二層方針は不要——公式測定との比較対象が
# 無いため）。
#
# 検査:
#   1. 字句解析: L4_TOKEN_TABLE(tokens.asm、190語。資料1「予約語」由来のv2、
#      docs/notes/l4-keywords-extraction.md)の全項目が、項目自身の
#      語のバイト列を入力として与えたとき正しいトークンに変換される
#      （LEX_SELFTEST。--enable-l4-selftestを立てたビルドで起動時に走らせ、
#      結果(SELFTEST_TOTAL/PASS/FAILIX)をmem-write-logで読む。画面へは
#      一切出さない自己完結の検査）。
#   2. 直接モードのPRINT: 整数(正・負・0・式)・文字列・区切り記号(;と,)・
#      複数文(:)・?略記の出力が、docs/spec/l4-basic.md の書式規則から
#      機械的に作った期待値と一致する。大半は `PRINT1` 等スペース無しで
#      打鍵する（文法上スペースは必須ではないため意味は変わらず、
#      検査対象を絞れる）。
#   2b. M7段階3b追記2（docs/spec/l3-main.md 第9節末尾の追記）: SPACEキーの
#      エコー前進が実装されたため、`PRINT 1`のようにSPACEを挟んだ実際の
#      打鍵も検査する。エコー行では`1`がPRINTの直後ではなく1桁空けた
#      位置に出て（第9節の観測どおり）、行バッファにも0x20が積まれる
#      設計（interp.asmのSKIP_SPACESが読み飛ばす）により、実行結果
#      （出力行のPRINT書式）はスペース無しの場合と変わらないことを
#      確かめる。
#   3. 構文の誤り: 未認識の語(XYZ)で、出力の行が1行だけ・文言が
#      errors.tsv(l4-basic.md第6.1節から生成)の番号2と一致し、その次に
#      Okが出る。
#   4. 故障注入: (a)数値前置空白を消した変種、(b)ゾーン幅を変えた変種、
#      (c)トークン表の1エントリの語長を壊した変種、(d)SPACEのエコー
#      前進を無効化した変種(3c)、それぞれが正常時と異なる結果になる
#      ことを確かめる。
#   5. 既存の tools/l3_main_selftest.sh(検査1〜18)・tools/conform_l4.sh
#      (自作ROM側の照合)が引き続きOKであること(打鍵エコーを壊していない)。
#
# 使い方: tools/l4_basic_selftest.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
BUILD="$REPO/src/build_main_rom.py"
ERRORS_TSV="$REPO/src/l4_basic/errors.tsv"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
fail() { echo "NG: $1" >&2; FAILED=1; }

FAILED=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi
make -s -C "$REPO/tools/harness/frontend" || exit 1

if [ ! -f "$ERRORS_TSV" ]; then
  echo "エラー: $ERRORS_TSV が無い。先に src/l4_basic/make_error_table.py を実行すること" >&2
  exit 1
fi
SYNTAX_ERROR_MSG="$(awk -F'\t' '$1=="2"{print $2}' "$ERRORS_TSV")"
if [ -z "$SYNTAX_ERROR_MSG" ]; then
  echo "エラー: errors.tsvに番号2の項が無い" >&2; exit 1
fi
OVERFLOW_MSG="$(awk -F'\t' '$1=="6"{print $2}' "$ERRORS_TSV")"
if [ -z "$OVERFLOW_MSG" ]; then
  echo "エラー: errors.tsvに番号6の項が無い" >&2; exit 1
fi
MISSING_OPERAND_MSG="$(awk -F'\t' '$1=="22"{print $2}' "$ERRORS_TSV")"
if [ -z "$MISSING_OPERAND_MSG" ]; then
  echo "エラー: errors.tsvに番号22の項が無い" >&2; exit 1
fi
DIVZERO_MSG="$(awk -F'\t' '$1=="11"{print $2}' "$ERRORS_TSV")"
if [ -z "$DIVZERO_MSG" ]; then
  echo "エラー: errors.tsvに番号11の項が無い" >&2; exit 1
fi

# -----------------------------------------------------------------------
say "1. 通常ビルド（PRINT実行用。--enable-l4-selftestは付けない。"
say "   起動時サイクル数がl3_main_selftest.shのL1タイミング検査を"
say "   壊すため既定offにしてある）"
NORMAL_ROM="$WORK/rom_normal"
python3 "$BUILD" "$NORMAL_ROM" >"$WORK/build_normal.txt" 2>&1 || { fail "build_main_rom.py(通常)が失敗"; cat "$WORK/build_normal.txt" >&2; }
cat "$WORK/build_normal.txt"

# -----------------------------------------------------------------------
say "2. 字句解析の自己検査（LEX_SELFTEST、--enable-l4-selftest版ビルド）"
SELFTEST_ROM="$WORK/rom_selftest"
python3 "$BUILD" "$SELFTEST_ROM" --enable-l4-selftest >"$WORK/build_selftest.txt" 2>&1 || { fail "build_main_rom.py(selftest)が失敗"; cat "$WORK/build_selftest.txt" >&2; }

read_lex_selftest() {
  # $1=rom-dir $2=out memlog path -> 標準出力に "TOTAL PASS FAILIX"（10進）
  local romdir="$1" memlog="$2"
  "$FRONTEND" --core "$CORE" --rom-dir "$romdir" --frames 90 \
      --mem-write-log "$memlog" --mem-write-range E880-E8A0 \
      >"$WORK/lex.stdout.txt" 2>"$WORK/lex.stderr.txt"
  if [ $? -ne 0 ]; then fail "q88measure(lex selftest)が失敗"; cat "$WORK/lex.stderr.txt" >&2; echo "0 0 256"; return; fi
  python3 - "$memlog" << 'PYEOF'
import re, sys
last = {}
for line in open(sys.argv[1]):
    m = re.match(r'\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})', line)
    if m:
        last[m.group(4).upper()] = m.group(5)
total = int(last.get("E893", "00"), 16)
passed = int(last.get("E891", "00"), 16)
failix = int(last.get("E892", "FF"), 16)
print(total, passed, failix)
PYEOF
}

read -r LEX_TOTAL LEX_PASS LEX_FAILIX <<< "$(read_lex_selftest "$SELFTEST_ROM" "$WORK/lex_normal.memlog.txt")"
echo "LEX_SELFTEST: total=$LEX_TOTAL pass=$LEX_PASS failix=$LEX_FAILIX"
KEYWORDS_TOTAL="$(grep -vc '^#' "$REPO/src/l4_basic/keywords.tsv" | tr -d ' ')"
if [ "$LEX_TOTAL" = "$KEYWORDS_TOTAL" ] && [ "$LEX_PASS" = "$KEYWORDS_TOTAL" ] && [ "$LEX_FAILIX" = "255" ]; then
  echo "OK: 表の全語(${KEYWORDS_TOTAL}語)が正しいトークンに変換された(不一致0件)"
else
  fail "LEX_SELFTEST: total=$LEX_TOTAL pass=$LEX_PASS failix=${LEX_FAILIX} (期待 total=pass=$KEYWORDS_TOTAL, failix=255=無し)"
fi

# -----------------------------------------------------------------------
say "3. 直接モードPRINTの書式（通常ビルド、--typeで打鍵）"
# 打った行は row0=2(バナー行0・最初のOk行1の次)、出力行はrow0=3、
# Okはrow0=4という並びになる(docs/spec/l4-basic.md 第1節の相対+1/+2)。
# STRIDE=120, COLS=80はl3-main.md 第1〜2節。
STRIDE=120
ROW_OUTPUT=3
ROW_OK=4

# 数値の書式(l4-basic.md 第2節): 前置1桁(正/0は空白、負は'-') + 数字 +
# 後置空白1。文字列(第3節): 前後空白なし。ゾーン(第4節): ','は次の14刻み
# 境界まで空白で埋める。これらの規則から期待文字列を機械的に組み立てる
# （手で画面相当の文字列を書き写さない）。
expect_num() {
  python3 - "$1" << 'PYEOF'
import sys
n = int(sys.argv[1])
if n < 0:
    print("-" + str(-n) + " ", end="")
else:
    print(" " + str(n) + " ", end="")
PYEOF
}
expect_zone_pad() {
  # $1=現在桁 -> 埋める空白の個数(次の14刻み境界まで、境界上でも1ゾーン進む)
  python3 - "$1" << 'PYEOF'
import sys
col = int(sys.argv[1])
target = ((col // 14) + 1) * 14
print(target - col, end="")
PYEOF
}

check_row() {
  # $1=label $2=typed $3=期待する出力行の文字列(先頭からlen(expected)文字分だけ比較)
  local label="$1" typed="$2" expected="$3"
  local dump="$WORK/${label}.vram.bin"
  "$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 600 --type "$typed" --type-at 60 \
      --vram-dump "$dump" --vram-dump-at 560 \
      >"$WORK/${label}.stdout.txt" 2>"$WORK/${label}.stderr.txt"
  if [ $? -ne 0 ]; then fail "q88measure($label)が失敗"; cat "$WORK/${label}.stderr.txt" >&2; return; fi
  python3 - "$dump" "$expected" "$label" "$STRIDE" "$ROW_OUTPUT" "$ROW_OK" << 'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
expected = sys.argv[2]
label = sys.argv[3]
stride = int(sys.argv[4])
row_out = int(sys.argv[5])
row_ok = int(sys.argv[6])

def row_text(row, n):
    base = row * stride
    return data[base:base+n].decode("ascii", errors="replace")

got = row_text(row_out, len(expected))
ok_txt = row_text(row_ok, 2)
result_ok = (got == expected) and (ok_txt == "Ok")
if result_ok:
    print(f"OK: {label} 出力行='{got}' Ok行='{ok_txt}'")
else:
    print(f"NG: {label} 出力行='{got}'(期待'{expected}') Ok行='{ok_txt}'(期待'Ok')")
    sys.exit(1)
PYEOF
  [ $? -ne 0 ] && fail "PRINT書式($label)"
}

check_row case_p1     'PRINT1\n'       "$(expect_num 1)"
check_row case_pm5    'PRINT-5\n'      "$(expect_num -5)"
check_row case_p0     'PRINT0\n'       "$(expect_num 0)"
check_row case_semi   'PRINT1;2\n'     "$(expect_num 1)$(expect_num 2)"
check_row case_str    'PRINT"q7z"\n'   "q7z"
check_row case_expr   'PRINT2*(3+4)\n' "$(expect_num 14)"
check_row case_pm32768 'PRINT-32768\n' "$(expect_num -32768)"
check_row case_colon  'PRINT"a";:PRINT"b"\n' "ab"
check_row case_q      '?7\n'           "$(expect_num 7)"

# ','はゾーン境界まで空白で埋める(第4節)。"a"(1文字、col=1で区切り)の後、
# 次のゾーン境界(14)まで埋めてから"b"を出す。
ZONE_PAD_AFTER_A="$(expect_zone_pad 1)"
check_row case_comma  'PRINT"a","b"\n' "a$(python3 -c "print(' '*$ZONE_PAD_AFTER_A, end='')")b"

# 構文の誤り(第5節・第6.1節): 出力の行が1行、文言はerrors.tsvの番号2、
# その次にOk。
check_row case_err    'XYZ\n'          "$SYNTAX_ERROR_MSG"

# -----------------------------------------------------------------------
say "3d. 誤りの形とメッセージの対応(第6.1.1節、errors.tsvの文言から機械的に)"
# 演算子の後に被演算子が無い → Missing operand(22)
check_row case_err_missing1 'PRINT 1+\n'  "$MISSING_OPERAND_MSG"
check_row case_err_missing2 'PRINT 2*\n'  "$MISSING_OPERAND_MSG"
# 閉じない括弧・知らない語 → Syntax error(2)(第6.1.1節の資料の記載どおり)
check_row case_err_paren    'PRINT (1+2\n' "$SYNTAX_ERROR_MSG"
check_row case_err_word     'PRINTX 1\n'   "$SYNTAX_ERROR_MSG"
# 定数・式の結果が-32768〜32767を超える場合は、M7段階4a-2(単精度の組み込み)
# 以降はOverflowにならず単精度へ「昇格」する(l4-basic.md 第5.2節、
# promote群P1〜P3、実測40000/60000/-32769。第9節に記録した測定>資料の
# 食い違いのとおり、旧第6.1.1節の資料の記載どおりのOverflow扱いは廃止)。
# 検査名も"ovfl"から昇格を表す"promote"へ改めた。単精度の値は整数と同じ
# 前置1桁・後置空白1で出る(第5.3節)ため、expect_num()をそのまま使える。
check_row case_promote_const 'PRINT 40000\n'        "$(expect_num 40000)"
check_row case_promote_sum   'PRINT 30000+30000\n'  "$(expect_num 60000)"
check_row case_promote_sub   'PRINT -32768-1\n'     "$(expect_num -32769)"

# -----------------------------------------------------------------------
say "3e. 単精度浮動小数点PRINT(l4-basic.md 第5節、M7段階4a-2)"
# 第5節の観測例をそのまま期待値として使う(仕様書の表から書き写す。
# 数値そのものは自作ROMの出力であって画面本文ではないため禁止事項7の
# 対象外——l4-basic.md冒頭「画面本文」の取り扱い節と同じ位置づけ)。
check_row case_fp_frac        'PRINT 1/3\n'        " .333333 "
check_row case_fp_leadingdot  'PRINT .5\n'         " .5 "
check_row case_fp_neg         'PRINT -.5\n'        "-.5 "
check_row case_fp_bang        'PRINT 12345.678!\n' " 12345.7 "
check_row case_fp_large_exp   'PRINT 1234567\n'    " 1.23457E+06 "
check_row case_fp_exp         'PRINT 1e10\n'       " 1E+10 "
check_row case_fp_exp_neg     'PRINT -1.5e+20\n'   "-1.5E+20 "
check_row case_fp_small_fixed 'PRINT 1.5e-6\n'     " .0000015 "
check_row case_fp_small_exp   'PRINT 1e-8\n'       " 1E-08 "
check_row case_fp_div_real    'PRINT 7/2\n'        " 3.5 "
check_row case_fp_digits7     'PRINT 9999999\n'    " 1E+07 "
check_row case_fp_tie         'PRINT -34281.25\n'  "-34281.3 "

# -----------------------------------------------------------------------
say "3f. 範囲外・0除算(l4-basic.md 第5.6節): 出力2行・Okが相対+3"
# 文言は第7.1節のマニュアル一覧(Overflow=6, Division by zero=11)。
# 1行目(空行)の扱いは仕様書に無い判断(interp.asmヘッダコメント参照、
# 実際の画面表示の文言・中身そのものは未確認、第10節5)。
ROW_OK_RUNTIME=5
check_runtime_err() {
  local label="$1" typed="$2" expected_msg="$3"
  local dump="$WORK/${label}.vram.bin"
  "$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 600 --type "$typed" --type-at 60 \
      --vram-dump "$dump" --vram-dump-at 560 \
      >"$WORK/${label}.stdout.txt" 2>"$WORK/${label}.stderr.txt"
  if [ $? -ne 0 ]; then fail "q88measure($label)が失敗"; cat "$WORK/${label}.stderr.txt" >&2; return; fi
  python3 - "$dump" "$expected_msg" "$label" "$STRIDE" "$ROW_OUTPUT" "$ROW_OK_RUNTIME" << 'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
expected_msg = sys.argv[2]
label = sys.argv[3]
stride = int(sys.argv[4])
row_blank = int(sys.argv[5])
row_msg = row_blank + 1
row_ok = int(sys.argv[6])

def row_text(row, n):
    base = row * stride
    return data[base:base+n].decode("ascii", errors="replace")

got_blank = row_text(row_blank, len(expected_msg)).rstrip(" ")
got_msg = row_text(row_msg, len(expected_msg))
ok_txt = row_text(row_ok, 2)
result_ok = (got_blank == "") and (got_msg == expected_msg) and (ok_txt == "Ok")
if result_ok:
    print(f"OK: {label} 1行目=空 2行目='{got_msg}' Ok行='{ok_txt}'")
else:
    print(f"NG: {label} 1行目='{got_blank}' 2行目='{got_msg}'(期待'{expected_msg}') Ok行='{ok_txt}'(期待'Ok')")
    sys.exit(1)
PYEOF
  [ $? -ne 0 ] && fail "範囲外/0除算($label)"
}
check_runtime_err case_fp_overflow 'PRINT 1e38*10\n' "$OVERFLOW_MSG"
check_runtime_err case_fp_divzero  'PRINT 1/0\n'     "$DIVZERO_MSG"

# -----------------------------------------------------------------------
say "3g. 倍精度定数は段階4bまで未実装のため暫定的にSyntax error(仕様書に無い判断)"
check_row case_fp_double_pending 'PRINT 1#\n' "$SYNTAX_ERROR_MSG"

# -----------------------------------------------------------------------
say "3b. PRINT 1（実際にSPACEキーを打鍵）: エコーの1桁前進と実行結果"
# docs/spec/l3-main.md 第9節末尾の追記＋keyboard.asmの選択（0x20を書いて
# 進む・行バッファにも積む）により、打った行のエコーは"print 1"
# （printの直後に0x20、その次に"1"。英字は第7節の既定どおり小文字の
# ままエコーされる）になる一方、interp.asmのSKIP_SPACESがその0x20を
# 読み飛ばすため、実行結果(出力行)はスペース無しのcase_p1と変わらない
# はず。
check_row_with_echo() {
  # $1=label $2=typed $3=期待するエコー行(row2)の文字列 $4=期待する出力行(row3)
  local label="$1" typed="$2" expected_echo="$3" expected_out="$4"
  local dump="$WORK/${label}.vram.bin"
  "$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 600 --type "$typed" --type-at 60 \
      --vram-dump "$dump" --vram-dump-at 560 \
      >"$WORK/${label}.stdout.txt" 2>"$WORK/${label}.stderr.txt"
  if [ $? -ne 0 ]; then fail "q88measure($label)が失敗"; cat "$WORK/${label}.stderr.txt" >&2; return; fi
  python3 - "$dump" "$expected_echo" "$expected_out" "$label" "$STRIDE" << 'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
expected_echo = sys.argv[2]
expected_out = sys.argv[3]
label = sys.argv[4]
stride = int(sys.argv[5])

def row_text(row, n):
    base = row * stride
    return data[base:base + n].decode("ascii", errors="replace")

ROW_ECHO = 2  # 打った行のエコー(l4_basic_selftest.sh冒頭コメント参照)
got_echo = row_text(ROW_ECHO, len(expected_echo))
got_out = row_text(3, len(expected_out))
if got_echo == expected_echo and got_out == expected_out:
    print(f"OK: {label} エコー行='{got_echo}' 出力行='{got_out}'")
else:
    print(f"NG: {label} エコー行='{got_echo}'(期待'{expected_echo}') 出力行='{got_out}'(期待'{expected_out}')")
    sys.exit(1)
PYEOF
  [ $? -ne 0 ] && fail "PRINT書式+エコー($label)"
}
# l3-main.md 第7節: 無修飾の英字キーは既定で小文字になる（--typeは
# シフト無しでASCIIを送る）。TRY_MATCH_PRINT側は大文字小文字を区別せず
# 照合するため実行結果には影響しないが、エコー行はそのまま打った小文字
# "print"になる。
check_row_with_echo case_p1_space 'print 1\n' "print 1" "$(expect_num 1)"

say "3c. 故障注入（SPACEのエコー前進を無効化。検査3bのエコーが変わることを確かめる）"
L3SPACEFAULT_ROM="$WORK/rom_l3spacefault"
python3 "$BUILD" "$L3SPACEFAULT_ROM" --inject-l3-space-fault >"$WORK/build_l3spacefault.txt" 2>&1 || { fail "build_main_rom.py(l3spacefault)が失敗"; cat "$WORK/build_l3spacefault.txt" >&2; }
"$FRONTEND" --core "$CORE" --rom-dir "$L3SPACEFAULT_ROM" --frames 600 --type 'print 1\n' --type-at 60 \
    --vram-dump "$WORK/l3spacefault.vram.bin" --vram-dump-at 560 \
    >"$WORK/l3spacefault.stdout.txt" 2>"$WORK/l3spacefault.stderr.txt"
if [ $? -ne 0 ]; then fail "q88measure(l3spacefault)が失敗"; cat "$WORK/l3spacefault.stderr.txt" >&2; fi
python3 - "$WORK/l3spacefault.vram.bin" "$STRIDE" << 'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
stride = int(sys.argv[2])
got_echo = data[2*stride:2*stride+7].decode("ascii", errors="replace")
expect_normal = "print 1"
if got_echo != expect_normal:
    print(f"OK(検出力): SPACE故障注入がかかるとエコー行='{got_echo}'(期待'{expect_normal}'と不一致)になり、検査3bと区別できた")
    sys.exit(0)
print(f"NG(検出力不足): 故障注入してもエコー行='{got_echo}'のままで検査3bと区別できない")
sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "SPACE故障注入(l4)の検出力"

# -----------------------------------------------------------------------
say "4. 故障注入"

say "4a. 数値の前置空白を消した変種（正常時と出力行が変わることを確かめる）"
SIGNFAULT_ROM="$WORK/rom_signfault"
python3 "$BUILD" "$SIGNFAULT_ROM" --inject-l4-sign-space-fault >"$WORK/build_signfault.txt" 2>&1 || { fail "build_main_rom.py(signfault)が失敗"; cat "$WORK/build_signfault.txt" >&2; }
"$FRONTEND" --core "$CORE" --rom-dir "$SIGNFAULT_ROM" --frames 600 --type 'PRINT1\n' --type-at 60 \
    --vram-dump "$WORK/signfault.vram.bin" --vram-dump-at 560 \
    >"$WORK/signfault.stdout.txt" 2>"$WORK/signfault.stderr.txt"
if [ $? -ne 0 ]; then fail "q88measure(signfault)が失敗"; cat "$WORK/signfault.stderr.txt" >&2; fi
python3 - "$WORK/signfault.vram.bin" "$STRIDE" "$ROW_OUTPUT" << 'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
stride = int(sys.argv[2]); row = int(sys.argv[3])
got = data[row*stride:row*stride+3].decode("ascii", errors="replace")
expect_normal = " 1 "
if got != expect_normal:
    print(f"OK(検出力): 前置空白の故障注入で出力行='{got}'(正常時'{expect_normal}'と不一致)になり区別できた")
    sys.exit(0)
print(f"NG(検出力不足): 故障注入しても出力行='{got}'のままで正常時と区別できない")
sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "前置空白の故障注入の検出力"

say "4b. ゾーン幅を変えた変種（正常時のゾーン境界(14)と違う位置になることを確かめる）"
ZONEFAULT_ROM="$WORK/rom_zonefault"
python3 "$BUILD" "$ZONEFAULT_ROM" --inject-l4-zone-width-fault >"$WORK/build_zonefault.txt" 2>&1 || { fail "build_main_rom.py(zonefault)が失敗"; cat "$WORK/build_zonefault.txt" >&2; }
"$FRONTEND" --core "$CORE" --rom-dir "$ZONEFAULT_ROM" --frames 600 --type 'PRINT"a","b"\n' --type-at 60 \
    --vram-dump "$WORK/zonefault.vram.bin" --vram-dump-at 560 \
    >"$WORK/zonefault.stdout.txt" 2>"$WORK/zonefault.stderr.txt"
if [ $? -ne 0 ]; then fail "q88measure(zonefault)が失敗"; cat "$WORK/zonefault.stderr.txt" >&2; fi
python3 - "$WORK/zonefault.vram.bin" "$STRIDE" "$ROW_OUTPUT" << 'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
stride = int(sys.argv[2]); row = int(sys.argv[3])
segment = data[row*stride:row*stride+20].decode("ascii", errors="replace")
b_pos = segment.find("b")
if b_pos != 14 and b_pos != -1:
    print(f"OK(検出力): ゾーン幅の故障注入で'b'の位置={b_pos}(正常時14と不一致)になり区別できた")
    sys.exit(0)
print(f"NG(検出力不足): 故障注入しても'b'の位置={b_pos}のままで正常時(14)と区別できない")
sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "ゾーン幅の故障注入の検出力"

say "4c. トークン表(ABS)の語長を壊した変種（LEX_SELFTESTが不一致を検出することを確かめる）"
TOKENFAULT_ROM="$WORK/rom_tokenfault"
python3 "$BUILD" "$TOKENFAULT_ROM" --inject-l4-token-fault --enable-l4-selftest >"$WORK/build_tokenfault.txt" 2>&1 || { fail "build_main_rom.py(tokenfault)が失敗"; cat "$WORK/build_tokenfault.txt" >&2; }
read -r TF_TOTAL TF_PASS TF_FAILIX <<< "$(read_lex_selftest "$TOKENFAULT_ROM" "$WORK/lex_tokenfault.memlog.txt")"
echo "LEX_SELFTEST(tokenfault): total=$TF_TOTAL pass=$TF_PASS failix=$TF_FAILIX"
if [ "$TF_TOTAL" != "$KEYWORDS_TOTAL" ] || [ "$TF_PASS" != "$KEYWORDS_TOTAL" ] || [ "$TF_FAILIX" != "255" ]; then
  echo "OK(検出力): トークン表の故障注入でtotal=$TF_TOTAL pass=$TF_PASS failix=$TF_FAILIX(正常時と不一致)になり区別できた"
else
  fail "トークン表の故障注入の検出力不足(正常時と同じ結果のまま)"
fi

say "4d. Missing operandの判定を外した変種（'PRINT 1+'がSyntax errorに化けることを確かめる）"
MISSINGOPFAULT_ROM="$WORK/rom_missingopfault"
python3 "$BUILD" "$MISSINGOPFAULT_ROM" --inject-l4-missing-operand-fault >"$WORK/build_missingopfault.txt" 2>&1 || { fail "build_main_rom.py(missingopfault)が失敗"; cat "$WORK/build_missingopfault.txt" >&2; }
"$FRONTEND" --core "$CORE" --rom-dir "$MISSINGOPFAULT_ROM" --frames 600 --type 'PRINT 1+\n' --type-at 60 \
    --vram-dump "$WORK/missingopfault.vram.bin" --vram-dump-at 560 \
    >"$WORK/missingopfault.stdout.txt" 2>"$WORK/missingopfault.stderr.txt"
if [ $? -ne 0 ]; then fail "q88measure(missingopfault)が失敗"; cat "$WORK/missingopfault.stderr.txt" >&2; fi
python3 - "$WORK/missingopfault.vram.bin" "$STRIDE" "$ROW_OUTPUT" "$MISSING_OPERAND_MSG" << 'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
stride = int(sys.argv[2]); row = int(sys.argv[3])
expect_normal = sys.argv[4]
got = data[row*stride:row*stride+len(expect_normal)].decode("ascii", errors="replace")
if got != expect_normal:
    print(f"OK(検出力): Missing operandの判定を外した故障注入で出力行='{got}'(正常時'{expect_normal}'と不一致)になり区別できた")
    sys.exit(0)
print(f"NG(検出力不足): 故障注入しても出力行='{got}'のままで正常時と区別できない")
sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "Missing operand判定の故障注入の検出力"

# -----------------------------------------------------------------------
say "5. 既存の自己検査が引き続きOKであること"

say "5a. tools/l3_main_selftest.sh（検査1〜18）"
if bash "$REPO/tools/l3_main_selftest.sh" >"$WORK/l3_main_selftest.txt" 2>&1; then
  echo "OK: tools/l3_main_selftest.sh はrc=0"
else
  fail "tools/l3_main_selftest.sh がNG"
  tail -40 "$WORK/l3_main_selftest.txt" >&2
fi

say "5b. tools/conform_l4.sh（自作ROM側の照合）"
if bash "$REPO/tools/conform_l4.sh" >"$WORK/conform_l4.txt" 2>&1; then
  echo "OK: tools/conform_l4.sh はrc=0"
else
  fail "tools/conform_l4.sh がNG"
  tail -40 "$WORK/conform_l4.txt" >&2
fi

# -----------------------------------------------------------------------
echo
if [ "$FAILED" -eq 0 ]; then
  echo "l4_basic_selftest: OK"
  exit 0
else
  echo "l4_basic_selftest: NG"
  exit 1
fi
