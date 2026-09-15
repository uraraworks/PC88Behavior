#!/usr/bin/env bash
# tools/l4_program_selftest.sh — M7段階5a: プログラムモード（行の入力・
# 保存・LIST・NEW）の自己検査。**公式ROMは要らない**
# （tools/l4_basic_selftest.sh と同じ理由: 比較対象が無い）。
#
# 検査:
#   1. l4-program.md 第2節の観測例(A1-A5,A9-A12)を、`NEW`→行番号つきの行
#      →`LIST` という打鍵列で再現し、`LIST`の出力が仕様書の表と一致する
#      ことを確かめる。
#   2. 第1節: 行番号つきの行を打った直後は「無出力」（`Ok`もそれ以外の
#      行も出ない）ことを、その行の直後の行にOkが出ていないことで
#      確かめる。
#   3. 第3節: 同一行番号の置き換え(replaced)・行番号だけの行の削除
#      (deleted)・LISTの行番号順の並び(sorted)。
#   4. `NEW`直後の`LIST`は0行（`Ok`だけが直後に出る）こと。
#   5. 直接モードの`PRINT`が引き続き動くこと（軽い回帰、本体は
#      tools/l4_basic_selftest.shが担当）。
#
# 実装方針: 打鍵列とVRAMの行の対応（NEWLINE/Okの有無で変わる行送り）を
# シェル側の文字列補間で組み立てると引用符の混入(A10の`"abc"`等)で
# 壊れやすいため、テストケースの定義・レイアウト計算・照合まで1本の
# pythonスクリプト（本ファイル末尾のヒアドキュメント、ケース定義は
# JSONリテラルではなくpythonのリストとして直接書く）に閉じ込める。
#
# 使い方: tools/l4_program_selftest.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
BUILD="$REPO/src/build_main_rom.py"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi
make -s -C "$REPO/tools/harness/frontend" || exit 1

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say "0. 通常ビルド"
ROM="$WORK/rom_normal"
python3 "$BUILD" "$ROM" >"$WORK/build.txt" 2>&1
if [ $? -ne 0 ]; then
  echo "NG: build_main_rom.py が失敗" >&2
  cat "$WORK/build.txt" >&2
  exit 1
fi

say "1-5. プログラムモードの検査（詳細はpython本体のコメント参照）"
python3 - "$FRONTEND" "$CORE" "$ROM" "$WORK" << 'PYEOF'
import sys, subprocess, pathlib

frontend, core, rom, work = sys.argv[1:5]
work = pathlib.Path(work)
STRIDE = 120
BOOT_ROW = 2   # l4_basic_selftest.sh と同じ規約(バナー行0・最初のOk行1の次)
FAILED = False


def fail(msg):
    global FAILED
    FAILED = True
    print(f"NG: {msg}")


# ---------------------------------------------------------------------
# steps: [{"kind": "num"} | {"kind": "cmd", "out": N, "texts": [...]}]
#   "num"  = 行番号つきの行（無出力、第1節）
#   "cmd"  = 直接モードの行（NEW/LIST/PRINT等）。out=出力行数、
#            texts=各出力行の期待文字列(先頭len(text)文字だけ比較)。
# 戻り値: (checks, ok_absence_rows)
#   checks: [(row, expected_text)]
#   ok_absence_rows: 行番号つきの行の直後で「Okが出ていないこと」を
#     確かめる行番号のリスト
# ---------------------------------------------------------------------
def layout(steps):
    row = BOOT_ROW
    checks = []
    ok_absence_rows = []
    for st in steps:
        if st["kind"] == "num":
            ok_absence_rows.append(row + 1)
            row = row + 1
        else:
            n = st["out"]
            for i, text in enumerate(st.get("texts", [])):
                checks.append((row + 1 + i, text))
            row = row + 2 + n
    return checks, ok_absence_rows


def run(label, typed, steps):
    steps_checks, ok_absence_rows = layout(steps)
    dump = work / f"{label}.vram.bin"
    out = work / f"{label}.stdout.txt"
    err = work / f"{label}.stderr.txt"
    proc = subprocess.run(
        [frontend, "--core", core, "--rom-dir", rom, "--frames", "4000",
         "--type", typed, "--type-at", "60",
         "--vram-dump", str(dump), "--vram-dump-at", "3900"],
        stdout=open(out, "wb"), stderr=open(err, "wb"))
    if proc.returncode != 0:
        fail(f"q88measure({label})が失敗")
        print(err.read_text(errors="replace"))
        return
    data = dump.read_bytes()

    def row_text(r, n):
        base = r * STRIDE
        return data[base:base + n].decode("ascii", errors="replace")

    for row, text in steps_checks:
        got = row_text(row, len(text))
        if got != text:
            fail(f"{label} row{row} got={got!r} exp={text!r}")
    for row in ok_absence_rows:
        got = row_text(row, 2)
        if got == "Ok":
            fail(f"{label} row{row}に無いはずのOkが出た(行番号つきの行は無出力のはず)")


# ---------------------------------------------------------------------
# 第2節: A1-A5,A9-A12の観測例。NEW→行番号つきの行→LISTで再現する。
# ---------------------------------------------------------------------
LIST_CASES = [
    ("case_a1", "10 print 1", "10 PRINT 1"),
    ("case_a2", "10print1", "10 PRINT1"),
    ("case_a3", "10 print  1", "10 PRINT  1"),
    ("case_a4", "10 ?1", "10 PRINT 1"),
    ("case_a5", "10 print 1:print 2", "10 PRINT 1:PRINT 2"),
    ("case_a9", "65529 print 1", "65529 PRINT 1"),
    ("case_a10", '10 print "abc"', '10 PRINT "abc"'),
    ("case_a11", "10 print 1.5", "10 PRINT 1.5"),
    ("case_a12", "10 print 1234567890123#", "10 PRINT 1234567890123#"),
]
for label, line, expect in LIST_CASES:
    typed = f"NEW\\n{line}\\nLIST\\n"
    steps = [
        {"kind": "cmd", "out": 0},
        {"kind": "num"},
        {"kind": "cmd", "out": 1, "texts": [expect]},
    ]
    run(label, typed, steps)

# ---------------------------------------------------------------------
# 第1節: 行番号つきの行の直後は無出力(単独でも明示的に確かめる)。
# ---------------------------------------------------------------------
run("case_num_no_output", "NEW\\n10 print 1\\n",
    [{"kind": "cmd", "out": 0}, {"kind": "num"}])

# ---------------------------------------------------------------------
# 第3.1節: 同じ行番号を打ち直すと置き換わる(replaced)。
# ---------------------------------------------------------------------
run("case_replaced", "NEW\\n10 print 1\\n10 print 2\\nLIST\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": ["10 PRINT 2"]},
])

# ---------------------------------------------------------------------
# 第3.2節: 行番号だけを打つと削除される(deleted)。
# ---------------------------------------------------------------------
run("case_deleted", "NEW\\n10 print 1\\n20 print 2\\n10\\nLIST\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": ["20 PRINT 2"]},
])

# ---------------------------------------------------------------------
# 第3.3節: 打った順ではなく行番号順に並ぶ(sorted)。
# ---------------------------------------------------------------------
run("case_sorted", "NEW\\n20 print 2\\n10 print 1\\nLIST\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 2, "texts": ["10 PRINT 1", "20 PRINT 2"]},
])

# ---------------------------------------------------------------------
# 4. NEW直後のLISTは0行(Okだけが直後に出る)。
# ---------------------------------------------------------------------
run("case_new_then_empty_list", "NEW\\nLIST\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "cmd", "out": 0},
])

# ---------------------------------------------------------------------
# 5. 直接モードPRINTの軽い回帰(本体はtools/l4_basic_selftest.sh)。
# ---------------------------------------------------------------------
run("case_print_regress", "PRINT1\\n",
    [{"kind": "cmd", "out": 1, "texts": [" 1 "]}])

# =======================================================================
# M7段階5b: RUNとプログラムの実行(docs/spec/l4-program.md 第3版・cd6bc19
# 第4節)。数値の書式は l4-basic.md 第2節(前置1桁+数字+後置空白1)を
# そのまま使う(expect_num)。RUN自身も直接モードの行なので、出力は
# 「run行のエコー→実行結果の出力→Ok」という直接モードの並びになる
# (第4.1節)。
# =======================================================================
def expect_num(n):
    if n < 0:
        return "-" + str(-n) + " "
    return " " + str(n) + " "


# 4.1節: 行番号順の実行(B1)。
run("case_b1_in_order", "NEW\\n10 print 1\\n20 print 2\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 2, "texts": [expect_num(1), expect_num(2)]},
])

# 4.1節: GOTO(B6)。
run("case_b6_goto", "NEW\\n10 goto 30\\n20 print 1\\n30 print 2\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(2)]},
])

# 4.1節: 空のプログラムのRUN(B12)は0行のまま。
run("case_b12_empty_run", "NEW\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "cmd", "out": 0},
])

# 4.1節: RUNへの行番号指定(C9、starts_at_line)。
run("case_c9_run_lineno", "NEW\\n10 print 1\\n20 print 2\\nRUN 20\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(2)]},
])

# 4.2節: FORの回数(B2既定STEP+1・B3 STEP3)。
run("case_b2_for_default_step", "NEW\\n10 for i=1 to 3\\n20 print i\\n30 next\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 3, "texts": [expect_num(1), expect_num(2), expect_num(3)]},
])
run("case_b3_for_step3", "NEW\\n10 for i=1 to 10 step 3\\n20 print i\\n30 next\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 4, "texts": [expect_num(1), expect_num(4), expect_num(7), expect_num(10)]},
])

# 4.2節: 開始が終了を最初から超えていれば本体を1回も実行しない(B4)。
run("case_b4_for_skipped", "NEW\\n10 for i=3 to 1\\n20 print i\\n30 next i\\n40 print 9\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(9)]},
])

# 4.2節: ループ後の制御変数は終了値を1回超えた値のまま(C1、after_loop_4)。
# ループ前の既存値はFORの初期化で上書きされる(C11)。
run("case_c1_after_loop", "NEW\\n10 for i=1 to 3\\n20 next\\n30 print i\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(4)]},
])
run("case_c11_for_overwrites_existing", "NEW\\n10 i=10\\n20 for i=1 to 3\\n30 next\\n40 print i\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(4)]},
])

# 4.2a節: FORの入れ子とNEXTへの変数名(C2、nested_ok)。
run("case_c2_nested_for", "NEW\\n10 for i=1 to 2\\n20 for j=1 to 2\\n30 print i*10+j;\\n40 next j\\n50 next i\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [
        expect_num(11) + expect_num(12) + expect_num(21) + expect_num(22)
    ]},
])

# 4.3節: GOSUB〜RETURN(B5、gosub_returns)。
run("case_b5_gosub", "NEW\\n10 gosub 100\\n20 print 2\\n30 end\\n100 print 1\\n110 return\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 2, "texts": [expect_num(1), expect_num(2)]},
])

# 4.3節: GOSUBの入れ子(C10、nested_gosub_ok)。
run("case_c10_nested_gosub", "NEW\\n10 gosub 30\\n20 end\\n30 gosub 50\\n40 return\\n50 print 5\\n60 return\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(5)]},
])

# 4.4節: 変数への代入・参照(B7・B8)。
run("case_b7_var_assign", "NEW\\n10 a=5\\n20 print a*2\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(10)]},
])

# 4.4a節: 変数名は少なくとも3文字目まで区別する(C3、more_significant)。
run("case_c3_varname_distinct", "NEW\\n10 abc=1\\n20 abd=2\\n30 print abc\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(1)]},
])

# 4.4b節: 整数変数(%)への代入は半分を絶対値の大きい側へ丸める
# (C4・C5・C12、rounds_half_away)。
run("case_c4_percent_round", "NEW\\n10 a%=5/2\\n20 print a%\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(3)]},
])
run("case_c5_percent_round_neg", "NEW\\n10 a%=-5/2\\n20 print a%\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(-3)]},
])
run("case_c12_percent_round_half", "NEW\\n10 a=1\\n20 a%=a+0.5\\n30 print a%\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(2)]},
])

# M7段階4b-3: 4.4c節、倍精度変数(#)への代入と精度(C6/C7)。単精度どうしの
# 演算結果(1/3)を#変数へ代入すると単精度の丸め誤差が倍精度の桁数のまま
# 出る(C6)。倍精度どうしの演算(1#/3)を代入すると乱れない(C7)。
run("case_c6_double_var_single_calc", "NEW\\n10 a#=1/3\\n20 print a#\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [" .3333333432674408 "]},
])

run("case_c7_double_var_double_calc", "NEW\\n10 a#=1#/3\\n20 print a#\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [" .3333333333333333 "]},
])

# 4.4d節: 文字列変数の基本動作(C8、string_ok)。
run("case_c8_string_var", 'NEW\\n10 a$="12"\\n20 print a$\\nRUN\\n', [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": ["12"]},
])

# 4.5節: STOPはそこで止まり、以降の行は実行しない(B9)。文言は
# errors.asmに無い独自の"Break"(仕様書に無い判断、run.asmヘッダ参照)
# +" in "+行番号。
run("case_b9_stop", "NEW\\n10 print 1\\n20 stop\\n30 print 2\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 2, "texts": [expect_num(1), "Break in 20"]},
])

# 4.5節: 実行中の構文の誤り(B10)。文言はl4-basic.md第7.1節(errors.asm)
# +" in "+行番号(仕様書に無い判断、run.asmヘッダ参照)。
run("case_b10_runtime_error", "NEW\\n10 print 1+\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": ["Missing operand in 10"]},
])

# =======================================================================
# M7段階5c: IF〜THEN〜ELSE・比較・AND/OR/NOT・配列・CONT・^ \ MOD・
# READ/DATA/RESTORE・REM・1行複数文の残り(docs/spec/l4-program.md
# 第7版第4.7〜4.12節・第6節)。
# =======================================================================

# 4.7節: IF〜THEN〜ELSE(D1・D2・D6・D13・D15、branch_ok)。
run("case_d1_if_then_true", "NEW\\n10 if 1<2 then print 1\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(1)]},
])
run("case_d2_if_then_else", "NEW\\n10 if 2<1 then print 1 else print 2\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(2)]},
])
run("case_d6_if_then_lineno", "NEW\\n10 a=3\\n20 if a>2 then 40\\n30 print 1\\n40 print 2\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(2)]},
])
run("case_d13_if_nonzero_true", "NEW\\n10 if 1 then print 5\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(5)]},
])
run("case_d15_if_and_compound", "NEW\\n10 if 1<2 and 3<4 then print 8\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(8)]},
])

# 4.8節: 比較演算の値(D3-D5、true_is_minus1)。
run("case_d3_lt_true", "NEW\\n10 print 1<2\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(-1)]},
])
run("case_d4_lt_false", "NEW\\n10 print 2<1\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(0)]},
])
run("case_d5_eq_true", "NEW\\n10 print 1=1\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(-1)]},
])

# 4.9節: AND/OR/NOTはビットごと(D7・D8、bitwise)。
run("case_d7_and_or", "NEW\\n10 print 3 and 5\\n20 print 3 or 5\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 2, "texts": [expect_num(1), expect_num(7)]},
])
run("case_d8_not", "NEW\\n10 print not 0\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(-1)]},
])

# 4.10節: 配列(D9・D10、array_ok)。宣言あり/なしのどちらでも使える。
run("case_d9_dim_array", "NEW\\n10 dim a(3)\\n20 a(2)=7\\n30 print a(2)\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(7)]},
])
run("case_d10_array_no_dim", "NEW\\n10 a(5)=1\\n20 print a(5)\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(1)]},
])
# D11: 宣言なし配列の範囲外添字は誤り(出力1行、文言は書かない)。
run("case_d11_array_out_of_range", "NEW\\n10 a(11)=1\\n20 print 1\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1},
])

# M7段階5c-2b追記: 配列代入の右辺が同じ配列の別要素を読む形
# (`a(j)=a(j+1)`)の回帰検査。tests/programs/p03_bubble_sort.bas の
# swap文`t=a(j):a(j)=a(j+1):a(j+1)=t`で発覚した不具合(ARRAY_ASSIGN_STMTが
# 右辺式の評価後に左辺アドレスを求めていたため、右辺のARRAY_READが
# RUN_ARRAY_IDX/RUN_ARRAY_NAMEを上書きし、左辺の添字が右辺の添字に
# 化けて誤った要素へ書いていた)。修正: 右辺を評価する前に左辺の
# アドレスを確定させる(run.asm ARRAY_ASSIGN_STMT参照)。
run("case_array_assign_rhs_reads_same_array", "NEW\\n10 dim a(2)\\n20 a(1)=5\\n30 a(2)=3\\n40 a(1)=a(2)\\n50 print a(1);a(2)\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(3) + expect_num(3)]},
])

# 4.11節: CONT(D12、cont_resumes)。STOPで止まった次の行から再開する。
run("case_d12_cont", "NEW\\n10 print 1\\n20 stop\\n30 print 2\\nRUN\\nCONT\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 2, "texts": [expect_num(1), "Break in 20"]},
    {"kind": "cmd", "out": 1, "texts": [expect_num(2)]},
])

# 4.12節: 演算子^・\・MOD(D14)。
run("case_d14_pow_intdiv_mod", "NEW\\n10 print 2^3\\n20 print 7\\2\\n30 print 7 mod 2\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 3, "texts": [expect_num(8), expect_num(3), expect_num(1)]},
])

# 6.1節: READ/DATA(G1-G4、read_ok)。
run("case_g1_read_multi", "NEW\\n10 read a,b\\n20 print a+b\\n30 data 3,4\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(7)]},
])
run("case_g2_read_in_loop", "NEW\\n10 for i=1 to 3\\n20 read a\\n30 print a;\\n40 next\\n50 data 5,6,7\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(5) + expect_num(6) + expect_num(7)]},
])
run("case_g4_read_string", "NEW\\n10 read a$\\n20 print a$\\n30 data 12\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": ["12"]},
])

# 6.2節: RESTORE(G3、restore_ok)。
run("case_g3_restore", "NEW\\n10 read a\\n20 restore\\n30 read b\\n40 print a;b\\n50 data 8,9\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(8) + expect_num(8)]},
])

# 6.3節: DATA切れは誤り(G8、出力1行・文言は書かない)。
run("case_g8_out_of_data", "NEW\\n10 read a\\n20 print a\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1},
])

# 6.4節: THENの後の代入(G5、then_assign_ok)。
run("case_g5_then_assign", "NEW\\n10 if 1 then a=5\\n20 print a\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(5)]},
])

# 6.5節: 配列の添字0(G6、index0_ok)。
run("case_g6_array_index0", "NEW\\n10 dim a(3)\\n20 a(0)=7\\n30 print a(0)\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(7)]},
])

# 6.6節: ':'で1行に複数の文(G7、multi_ok)。
run("case_g7_multi_stmt", "NEW\\n10 a=1:b=2:print a+b\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(3)]},
])

# 6.7節: REMと'(G9・G10、rem_ok)。
run("case_g9_rem", "NEW\\n10 print 1:rem 9\\n20 print 2\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 2, "texts": [expect_num(1), expect_num(2)]},
])
run("case_g10_quote_rem", "NEW\\n10 ' 9\\n20 print 3\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(3)]},
])

# 6.8節: IFと同じ行の残り(G11・G12)。真なら':'以降も実行
# (rest_runs_when_true)、偽なら':'以降も含め同じ行の残り全てを飛ばす
# (rest_skipped_when_false)。
run("case_g11_if_true_rest_runs", "NEW\\n10 a=2:if a=2 then print 1:print 2\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "cmd", "out": 2, "texts": [expect_num(1), expect_num(2)]},
])
run("case_g12_if_false_rest_skipped", "NEW\\n10 if 0 then print 1:print 2\\n20 print 3\\nRUN\\n", [
    {"kind": "cmd", "out": 0},
    {"kind": "num"},
    {"kind": "num"},
    {"kind": "cmd", "out": 1, "texts": [expect_num(3)]},
])

# =======================================================================
# M7段階5c-2a: INPUT(第4.13節)・文字列関数(第4.14節)・CLS(第5.1節)。
# CLSは画面を消しカーソルを絶対行0へ戻すため、行入力の`run()`/`layout()`
# (相対行の積み上げが前提)とは別立てのヘルパで確かめる。打鍵計画は
# l4_program_typeplan.pyのP1〜P8と同じ形("new"→"cls"→各行→"cls"→"run"、
# INPUTがあれば続けて入力値)を流用する。1文字あたり8フレーム
# (l4-s5a以来の前例)、余裕はいずれも既存の300フレームに合わせた。
# =======================================================================
def run_m7_5c2a(label, lines, checks, input_value=None):
    """lines: プログラムの各行(行番号込み)。checks: [(絶対行, 期待文字列)]
    (絶対行0='Ok'〔1回目のcls〕・1='run'・2以降が出力、l4_program_
    typeplan.pyのsegment1/2と同じ並び)。input_valueがあればRUN後に
    プロンプトを待たず追加で打鍵する(l4-s5eのE1/E2と同じ考え方)。"""
    prog = "new\ncls\n" + "\n".join(lines) + "\ncls\n"
    type_at = 700
    seg1_end = type_at + 8 * len(prog)
    dump1 = seg1_end + 300
    seg2 = "run\n"
    line_end2 = dump1 + 8 * len(seg2)
    segs = [(type_at, prog), (dump1, seg2)]
    dump_final = line_end2 + 300
    if input_value is not None:
        dump_prompt = line_end2 + 300
        seg3 = input_value + "\n"
        line_end3 = dump_prompt + 8 * len(seg3)
        dump_final = line_end3 + 300
        segs.append((dump_prompt, seg3))
    total = dump_final + 200
    dump = work / f"{label}.vram.bin"
    out = work / f"{label}.stdout.txt"
    err = work / f"{label}.stderr.txt"
    args = [frontend, "--core", core, "--rom-dir", rom, "--frames", str(total)]
    for at, text in segs:
        args += ["--type-at", str(at), "--type", text]
    args += ["--vram-dump", str(dump), "--vram-dump-at", str(dump_final)]
    proc = subprocess.run(args, stdout=open(out, "wb"), stderr=open(err, "wb"))
    if proc.returncode != 0:
        fail(f"q88measure({label})が失敗")
        print(err.read_text(errors="replace"))
        return
    data = dump.read_bytes()

    def row_text(r, n):
        base = r * STRIDE
        return data[base:base + n].decode("ascii", errors="replace")

    for row, text in checks:
        got = row_text(row, len(text))
        if got != text:
            fail(f"{label} row{row} got={got!r} exp={text!r}")


# 4.13節E1: INPUT単一変数(21*2=42)。
run_m7_5c2a("case_e1_input_single", ["10 input a", "20 print a*2"], [
    (0, "Ok"), (1, "run"), (2, "? 21"), (3, expect_num(42)), (4, "Ok"),
], input_value="21")

# 4.13節E2: INPUT複数変数(','区切り、3+4=7)。
run_m7_5c2a("case_e2_input_multi", ["10 input a,b", "20 print a+b"], [
    (0, "Ok"), (1, "run"), (2, "? 3,4"), (3, expect_num(7)), (4, "Ok"),
], input_value="3,4")

# 4.14節E3-E10: 文字列関数一式・'+'連結。
run_m7_5c2a("case_e3_e10_string_funcs", [
    '10 a$="hello"', '20 b$="world"',
    '30 print mid$(a$,2,3)', '40 print len(a$)',
    '50 print left$(a$,3)', '60 print right$(a$,3)',
    '70 c$=a$+b$', '80 print c$', '90 print str$(len(c$))',
    '100 print val("12")+1', '110 print asc("1")',
], [
    (0, "Ok"), (1, "run"),
    (2, "ell"), (3, expect_num(5)), (4, "hel"), (5, "llo"),
    (6, "helloworld"), (7, " 10"), (8, expect_num(13)), (9, expect_num(49)),
    (10, "Ok"),
])

# 5.1節F10: プログラム中のCLS(消去後に残るのはOk相当と、消去前に出した
# 値の代わりに'7'だけになる、消去後の絶対行0)。
run_m7_5c2a("case_f10_program_cls", ["10 cls", "20 print 7"], [
    (0, expect_num(7)), (1, "Ok"),
])

# M7段階5c-2b追記: 数値PRINTの行端折り返し回避(第5.3節、l4-s5f
# `locate 78,5:print 12`の観測「その行には変化が現れず、次の行に
# まとまって現れた」を、`RUN`中のPRINTでも再現する回帰検査(`LOCATE`文
# 自体はまだ未実装のため、`;`区切りの連続PRINTで桁78付近まで押し進める
# 形で近づける)。tests/programs/p04_fibonacci.bas で、80桁境界をまたぐ
# 数値が桁の途中で裂けて次の行へ続く不具合(PRINT_CHARの1文字ごとの
# 折り返しをそのまま使っていたため)が見つかった。修正: PRINT_VALUEが
# 印字前にフィールド全幅を求め、収まらなければ丸ごと次行へ送る
# (PRINT_FIELD_WRAP_CHECK、interp.asm)。
#
# `print 1;`のフィールド幅は3(空白1+数字1+空白1)。26回続けると桁78まで
# 進み(3*26=78、80桁ちょうどには収まる)、残りは桁78-79の2桁だけになる。
# 続けて`print 100`(フィールド幅5)を打つと収まらないため、絶対行2の
# 桁78-79は空白のまま、絶対行3の先頭からフィールド全体が現れるはず。
run_m7_5c2a("case_h1_print_no_split_at_edge",
    ["10 for i=1 to 26", "20 print 1;", "30 next i", "40 print 100"], [
    (0, "Ok"), (1, "run"),
    (2, (" 1 " * 26) + "  "),
    (3, " 100 "),
    (4, "Ok"),
])

print()
if FAILED:
    print("l4_program_selftest(python本体): NG")
    sys.exit(1)
print("l4_program_selftest(python本体): OK")
sys.exit(0)
PYEOF
RC=$?

echo
if [ "$RC" -eq 0 ]; then
  echo "l4_program_selftest: OK"
else
  echo "l4_program_selftest: NG"
fi
exit "$RC"
