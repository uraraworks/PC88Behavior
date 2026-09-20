#!/usr/bin/env bash
# tools/conform_l4.sh — l4-c1b「打鍵エコー適合の場面固定」・
# l4-c2c「直接モードPRINT適合の場面固定」・
# l4-c3「直接モードPRINT浮動小数点適合の場面固定」・
# l4-c5「代表プログラム集の適合場面固定」のランナー。
#
# 事前登録: docs/notes/l4-c1b-echo-conformance-scene-preregistration.md
# （打鍵エコー、11腕）・
# docs/notes/l4-c2c-print-conformance-scene-preregistration.md
# （直接モードPRINT、P1〜P5の16腕）・
# docs/notes/l4-c3-float-print-conformance-scene-preregistration.md
# （直接モードPRINT浮動小数点、FS単精度17腕・FD倍精度8腕、計25腕）・
# docs/notes/l4-c5-representative-programs-conformance-scene-
# preregistration.md（`2837926`）＋追補1（`ebe29dc`）＋追補2（`89b503e`）
# ＋追補3（`f0172d0`）（代表プログラム集、P1〜P8の8腕。1群のみ）。
# l4-c3は自作main ROM側の浮動小数点実装が段階4a/4bで進行中のため、群
# (FS/FD)ごとにexpected_l4_float.tsvの見出しコメントで実装状態
# (not_implemented_yet/implemented)を管理し、未実装の群は自作側の判定
# から除外する(公式側の期待値固定は実装状況と独立に先に行う)。l4-c5も
# 同じ作法で、expected_l4_programs.tsvの見出しコメント
# (# group programs selfmade=<status>) 1本だけで群(1群)の実装状態を
# 管理する。
# tools/conform_l3.sh と同じ二層方針: 公式ROM(PC88_REF_ROM_DIR)が要る本体と、
# 公式環境が無くても回る自作main ROM側の照合を分ける。ただし l4-c1 の結果
# （相対座標・文字コード・属性域が公式/自作間で一致する）を踏まえ、
# **自作ROM側の照合は公式環境の有無に関わらず常に、コミット済みの
# tests/conformance/expected_l4_echo.tsv・expected_l4_print.tsv とだけ
# 照合して回る**設計にする（公式環境が無い環境でも第三者がこのテストを
# 回せる。M8）。
#
# 期待値は tests/conformance/expected_l4_echo.tsv・expected_l4_print.tsv に
# 置くが、値そのもの（文字コード・属性・セル位置の並び）は一切コミット
# しない。件数とSHA-256のみ（CLAUDE.md禁止事項4）。正規化とハッシュ化は
# tools/l4_echo_conform_record.py（打鍵エコー用）・
# tools/l4_print_conform_record.py（PRINT用）が
# tools/l4_vram_probe.py の diff_vram_dumps/attr_rows を import して使う。
# 二重実装しない。
#
# 判定名は各事前登録どおり conform / not_conform / gate_failed の3つだけ。
#
# 使い方:
#   tools/conform_l4.sh                       # 自作ROM側の照合のみ（SKIP注記つき）
#   PC88_REF_ROM_DIR=/path/to/rom tools/conform_l4.sh   # 公式側の再導出も行う

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
RECORD="$REPO/tools/l4_echo_conform_record.py"
PRINT_RECORD="$REPO/tools/l4_print_conform_record.py"
PROGRAM_RECORD="$REPO/tools/l4_program_conform_record.py"
PROGRAM_RUN="$REPO/tools/l4_program_run.sh"
PROBE="$REPO/tools/l4_vram_probe.py"
BUILD_MAIN="$REPO/src/build_main_rom.py"
EXPECTED="$REPO/tests/conformance/expected_l4_echo.tsv"
EXPECTED_PRINT="$REPO/tests/conformance/expected_l4_print.tsv"
EXPECTED_FLOAT="$REPO/tests/conformance/expected_l4_float.tsv"
EXPECTED_PROGRAMS="$REPO/tests/conformance/expected_l4_programs.tsv"
EXPECTED_ARITH="$REPO/tests/conformance/expected_l4_arith.tsv"
EXPECTED_TRANS="$REPO/tests/conformance/expected_l4_trans.tsv"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }
na()  { printf '  \033[33m--\033[0m   %s\n' "$1"; }

if [ ! -f "$EXPECTED" ]; then
  echo "エラー: 期待値ファイルが無い: $EXPECTED" >&2
  exit 2
fi
if [ ! -f "$EXPECTED_PRINT" ]; then
  echo "エラー: 期待値ファイルが無い: $EXPECTED_PRINT" >&2
  exit 2
fi
if [ ! -f "$EXPECTED_FLOAT" ]; then
  echo "エラー: 期待値ファイルが無い: $EXPECTED_FLOAT" >&2
  exit 2
fi
if [ ! -f "$EXPECTED_PROGRAMS" ]; then
  echo "エラー: 期待値ファイルが無い: $EXPECTED_PROGRAMS" >&2
  exit 2
fi
if [ ! -f "$EXPECTED_ARITH" ]; then
  echo "エラー: 期待値ファイルが無い: $EXPECTED_ARITH" >&2
  exit 2
fi
if [ ! -f "$EXPECTED_TRANS" ]; then
  echo "エラー: 期待値ファイルが無い: $EXPECTED_TRANS" >&2
  exit 2
fi

# -----------------------------------------------------------------------
# l4-c3 浮動小数点PRINT場面: 群(FS=単精度/FD=倍精度)ごとの自作側の実装
# 状態を expected_l4_float.tsv の見出しコメント
# (# group <NAME> selfmade=<status>) から読む。値は出さない。
# status は not_implemented_yet | implemented の2値のみ扱う。
# -----------------------------------------------------------------------
float_group_status() {
  local group="$1"
  awk -v g="$group" '
    /^# group / {
      if ($3 == g) {
        split($4, kv, "=")
        print kv[2]
        exit
      }
    }
  ' "$EXPECTED_FLOAT"
}

# 腕id(例: FS3, FD1)からその群(FS/FD)を取り出す。
float_arm_group() {
  local arm="$1"
  case "$arm" in
    FS*) echo "FS" ;;
    FD*) echo "FD" ;;
    *) echo "" ;;
  esac
}

# -----------------------------------------------------------------------
# l4-c5 代表プログラム集の適合場面: 群(1群のみ、"programs")の自作側の
# 実装状態を expected_l4_programs.tsv の見出しコメント
# (# group programs selfmade=<status>) から読む。float_group_status と
# 同じ作法(値は出さない)。
# -----------------------------------------------------------------------
program_group_status() {
  awk '
    /^# group / {
      if ($3 == "programs") {
        split($4, kv, "=")
        print kv[2]
        exit
      }
    }
  ' "$EXPECTED_PROGRAMS"
}

# -----------------------------------------------------------------------
# l4-c7 直接モードPRINT整数四則演算(cdbl丸め)適合の場面: 群(1群のみ、
# "arith")の自作側の実装状態を expected_l4_arith.tsv の見出しコメント
# (# group arith selfmade=<status>) から読む。program_group_status と
# 同じ作法(値は出さない)。
# -----------------------------------------------------------------------
arith_group_status() {
  awk '
    /^# group / {
      if ($3 == "arith") {
        split($4, kv, "=")
        print kv[2]
        exit
      }
    }
  ' "$EXPECTED_ARITH"
}

# -----------------------------------------------------------------------
# l4-c8 超越関数(SIN/COS/TAN/ATN/EXP/LOG/SQR)適合の場面: 群(関数ごとに
# 7群、sin/cos/tan/atn/exp/log/sqr)の自作側の実装状態を
# expected_l4_trans.tsv の見出しコメント(# group <NAME> selfmade=<status>)
# から読む。float_group_status/float_arm_group と同じ作法(l4-c3のFS/FD
# の7群版)。
# -----------------------------------------------------------------------
trans_group_status() {
  local group="$1"
  awk -v g="$group" '
    /^# group / {
      if ($3 == g) {
        split($4, kv, "=")
        print kv[2]
        exit
      }
    }
  ' "$EXPECTED_TRANS"
}

# 腕id(例: SIN3, ATN12, SQR2)からその群(sin/cos/tan/atn/exp/log/sqr)を
# 取り出す。
trans_arm_group() {
  local arm="$1"
  case "$arm" in
    SIN*) echo "sin" ;;
    COS*) echo "cos" ;;
    TAN*) echo "tan" ;;
    ATN*) echo "atn" ;;
    EXP*) echo "exp" ;;
    LOG*) echo "log" ;;
    SQR*) echo "sqr" ;;
    *) echo "" ;;
  esac
}

if [ -n "${PC88_CONFORM_WORK_DIR:-}" ]; then
  WORK="$PC88_CONFORM_WORK_DIR"
  mkdir -p "$WORK"
  echo "  [注記] 作業ディレクトリを保持する: PC88_CONFORM_WORK_DIR が設定されている"
else
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT
fi

overall_rc=0

# -----------------------------------------------------------------------
# 腕の定義（docs/notes/l4-c1b-echo-conformance-scene-preregistration.md
# 「腕」節と完全に同一。11腕）。
#
# 呼び出し前に FRAMES/BEFORE/AFTER/ARM_ARGS を設定する。
# -----------------------------------------------------------------------
ARM_NAMES=(E1 E2 E3_shift_Q E3_shift_A E3_caps_Q E3_caps_A E3_kana_Q E3_kana_A E3_grph_Q E3_grph_A E4)

# tools/harness/frontend/main.c の vram_dump_path_for(): --vram-dump が
# 2件以上あると、実際に書き出すファイル名は「拡張子の直前に .f%06u を
# 差し込んだ」ものになる（1件だけなら指定パスそのまま）。ここでは
# --vram-dump を常に2件(前後)指定するので、必ず差し込まれる側を使う。
vram_out_path() {
  local base="$1" frame="$2"
  local stem="${base%.bin}"
  printf '%s.f%06d.bin' "$stem" "$frame"
}

arm_params() {
  local arm="$1"
  # 起動settle(--type-at 300 --type '\n')は --type 系の腕(E1/E2/E4)だけに
  # 使う。tools/harness/frontend/main.c は --key-matrix と --type の併用を
  # 引数エラーにする(同じkey_scanを2つの経路で書き換えると処理順に依存して
  # 不安定になるため、2026-09-15 cf677dc で禁止された)。E3(--key-matrix)は
  # 起動settleを使わずに直接キー行列を叩く(公式ROM実測で、SHIFT×Qが1セル
  # だけ変化する既知の形と一致することを確認済み)。
  case "$arm" in
    E1)
      FRAMES=952; BEFORE=690; AFTER=752
      ARM_ARGS=(--type-at 300 --type '\n' --type-at 700 --type 'ab12')
      ;;
    E2)
      FRAMES=976; BEFORE=690; AFTER=776
      ARM_ARGS=(--type-at 300 --type '\n' --type-at 700 --type '":(),.;')
      ;;
    E3_shift_Q)
      FRAMES=900; BEFORE=690; AFTER=724
      ARM_ARGS=(--key-matrix 0x08:6:700:30 --key-matrix 0x04:1:710:4)
      ;;
    E3_shift_A)
      FRAMES=900; BEFORE=690; AFTER=724
      ARM_ARGS=(--key-matrix 0x08:6:700:30 --key-matrix 0x02:1:710:4)
      ;;
    E3_caps_Q)
      FRAMES=900; BEFORE=690; AFTER=724
      ARM_ARGS=(--key-matrix 0x0A:7:700:30 --key-matrix 0x04:1:710:4)
      ;;
    E3_caps_A)
      FRAMES=900; BEFORE=690; AFTER=724
      ARM_ARGS=(--key-matrix 0x0A:7:700:30 --key-matrix 0x02:1:710:4)
      ;;
    E3_kana_Q)
      FRAMES=900; BEFORE=690; AFTER=724
      ARM_ARGS=(--key-matrix 0x08:5:700:30 --key-matrix 0x04:1:710:4)
      ;;
    E3_kana_A)
      FRAMES=900; BEFORE=690; AFTER=724
      ARM_ARGS=(--key-matrix 0x08:5:700:30 --key-matrix 0x02:1:710:4)
      ;;
    E3_grph_Q)
      FRAMES=900; BEFORE=690; AFTER=724
      ARM_ARGS=(--key-matrix 0x08:4:700:30 --key-matrix 0x04:1:710:4)
      ;;
    E3_grph_A)
      FRAMES=900; BEFORE=690; AFTER=724
      ARM_ARGS=(--key-matrix 0x08:4:700:30 --key-matrix 0x02:1:710:4)
      ;;
    E4)
      FRAMES=1600; BEFORE=690; AFTER=1400
      local eighty_five
      eighty_five="$(printf 'a%.0s' $(seq 1 85))"
      ARM_ARGS=(--type-at 300 --type '\n' --type-at 700 --type "$eighty_five")
      ;;
    *)
      return 2
      ;;
  esac
}

# -----------------------------------------------------------------------
# l4-c2c 直接モードPRINT適合の場面（16腕、P1〜P5）。
# 事前登録: docs/notes/l4-c2c-print-conformance-scene-preregistration.md
# 「腕」節・「条件・フレーム」節と完全に同一（変更しない）。
#
# フレーム式: line_end = 700 + 8*(打鍵文字列の長さ。末尾の\nを含む)、
# dump = line_end + 20、run = dump + 200。打鍵前の写しは常に690
# （--type-at 700 の10フレーム前、打鍵エコー場面と同じ間隔）。
# -----------------------------------------------------------------------
PRINT_ARM_NAMES=(
  P1_1 P1_0 P1_m5 P1_32767 P1_m32768
  P2_expr1 P2_expr2 P2_neg
  P3_str P3_semi_num P3_semi_str P3_comma_str P3_comma_num
  P4_semi P4_comma
  P5_q
)

print_arm_params() {
  local arm="$1" cmd
  case "$arm" in
    P1_1)         cmd='print 1' ;;
    P1_0)         cmd='print 0' ;;
    P1_m5)        cmd='print -5' ;;
    P1_32767)     cmd='print 32767' ;;
    P1_m32768)    cmd='print -32768' ;;
    P2_expr1)     cmd='print 2*(3+4)' ;;
    P2_expr2)     cmd='print 1+2*3' ;;
    P2_neg)       cmd='print -(4)' ;;
    P3_str)       cmd='print "q7z"' ;;
    P3_semi_num)  cmd='print 1;2' ;;
    P3_semi_str)  cmd='print "a";"b"' ;;
    P3_comma_str) cmd='print "a","b"' ;;
    P3_comma_num) cmd='print 1,2' ;;
    P4_semi)      cmd='print "a";:print "b"' ;;
    P4_comma)     cmd='print "a",:print "b"' ;;
    P5_q)         cmd='? 7' ;;
    *)
      return 2
      ;;
  esac
  # 末尾の\n(Enter)も1文字として数える(事前登録「条件・フレーム」節)。
  local n=${#cmd}
  local line_end=$(( 700 + 8 * (n + 1) ))
  PRINT_DUMP=$(( line_end + 20 ))
  PRINT_RUN=$(( PRINT_DUMP + 200 ))
  PRINT_BEFORE=690
  PRINT_ARM_ARGS=(--type-at 300 --type '\n' --type-at 700 --type "${cmd}\\n")
}

# -----------------------------------------------------------------------
# l4-c3 直接モードPRINT浮動小数点適合の場面（FS単精度17腕・FD倍精度8腕、
# 計25腕）。事前登録: docs/notes/l4-c3-float-print-conformance-scene-
# preregistration.md「腕」節・「条件・フレーム」節と完全に同一
# （変更しない）。記録の正規化・書式はPRINT場面(print_arm_params/
# run_print_arm_once/PRINT_RECORD)と全く同じため、専用のrunnerは作らず
# print_arm_paramsと同じ変数(PRINT_DUMP/PRINT_RUN/PRINT_BEFORE/
# PRINT_ARM_ARGS)を使い回す(float_arm_paramsを呼んだ直後に
# run_print_arm_onceをそのまま呼べる)。
#
# フレーム式: line_end = 700 + 8*(打鍵文字列の長さ。末尾の\nを含む)、
# dump = line_end + 300（l4-s4d追補以降の全腕一律延長を踏襲）、
# run = dump + 200。打鍵前の写しは690。
# -----------------------------------------------------------------------
FLOAT_ARM_NAMES=(
  FS1 FS2 FS3 FS4 FS5 FS6 FS7 FS8 FS9 FS10 FS11 FS12 FS13 FS14 FS15 FS16 FS17
  FD1 FD2 FD3 FD4 FD5 FD6 FD7 FD8
)

float_arm_params() {
  local arm="$1" cmd
  case "$arm" in
    FS1)  cmd='print 1.5' ;;
    FS2)  cmd='print .5' ;;
    FS3)  cmd='print -.5' ;;
    FS4)  cmd='print 1/3' ;;
    FS5)  cmd='print 2/3' ;;
    FS6)  cmd='print 9999999' ;;
    FS7)  cmd='print 1e10' ;;
    FS8)  cmd='print -1.5e+20' ;;
    FS9)  cmd='print .001' ;;
    FS10) cmd='print 1e-7' ;;
    FS11) cmd='print 1e-8' ;;
    FS12) cmd='print 40000' ;;
    FS13) cmd='print 30000+30000' ;;
    FS14) cmd='print -32768-1' ;;
    FS15) cmd='print 7/2' ;;
    FS16) cmd='print 1234567' ;;
    FS17) cmd='print 1.23456e-3' ;;
    FD1)  cmd='print 1#/3' ;;
    FD2)  cmd='print 1d16' ;;
    FD3)  cmd='print 1234567890123456#' ;;
    FD4)  cmd='print 1#/30' ;;
    FD5)  cmd='print 1.23456789012345d-3' ;;
    FD6)  cmd='print 1d-16' ;;
    FD7)  cmd='print 1.5d-15' ;;
    FD8)  cmd='print 12345678' ;;
    *)
      return 2
      ;;
  esac
  local n=${#cmd}
  local line_end=$(( 700 + 8 * (n + 1) ))
  PRINT_DUMP=$(( line_end + 300 ))
  PRINT_RUN=$(( PRINT_DUMP + 200 ))
  PRINT_BEFORE=690
  PRINT_ARM_ARGS=(--type-at 300 --type '\n' --type-at 700 --type "${cmd}\\n")
}

# -----------------------------------------------------------------------
# l4-c7 直接モードPRINT整数四則演算(cdbl丸め)適合の場面（40腕、1群
# "arith"のみ）。事前登録: docs/notes/
# l4-c7-integer-arithmetic-rounding-conformance-preregistration.md。
# 腕・打鍵文字列・フレーム値は docs/notes/
# l4-s7b-integer-only-rounding-preregistration.md「腕」節の表と完全に
# 同一(そこで既に機械的に導出済みの値をそのまま使う。二重に計算し
# 直さない)。写し(前)は全腕690固定、写し(後)・走行フレームは腕ごとに
# 個別の値を直接埋め込む(l4-c3のように打鍵文字列長から機械的に導出する
# 式ではなく、l4-s7bの表(line_end=700+8*打鍵文字数(\n込み)、
# dump=line_end+20、run=dump+200)で既に確定した値そのもの)。
# 記録・照合はPRINT場面と全く同じ(run_print_arm_once/PRINT_RECORDを
# そのまま使い回す)。
# -----------------------------------------------------------------------
ARITH_ARM_NAMES=(
  K1 K2 K3 K4 K5 K6 K7 K8
  L1 L2 L3 L4 L5 L6 L7 L8
  M1 M2 M3 M4 M5 M6 M7 M8 M9 M10 M11 M12 M13 M14 M15 M16
  N1 N2 N3 N4 N5 N6 N7 N8
)

arith_arm_params() {
  local arm="$1" cmd dump run
  case "$arm" in
    K1)  cmd='print cdbl(15777217!+1000000!)'; dump=968; run=1168 ;;
    K2)  cmd='print cdbl(15777147!+1000074!)'; dump=968; run=1168 ;;
    K3)  cmd='print cdbl(15777077!+1000148!)'; dump=968; run=1168 ;;
    K4)  cmd='print cdbl(15777007!+1000222!)'; dump=968; run=1168 ;;
    K5)  cmd='print cdbl(15777182!+1000037!)'; dump=968; run=1168 ;;
    K6)  cmd='print cdbl(15777112!+1000111!)'; dump=968; run=1168 ;;
    K7)  cmd='print cdbl(15777042!+1000185!)'; dump=968; run=1168 ;;
    K8)  cmd='print cdbl(1000000!+2000000!)'; dump=960; run=1160 ;;
    L1)  cmd='print cdbl(15777217!-(-1000000!))'; dump=992; run=1192 ;;
    L2)  cmd='print cdbl(15777147!-(-1000074!))'; dump=992; run=1192 ;;
    L3)  cmd='print cdbl(15777077!-(-1000148!))'; dump=992; run=1192 ;;
    L4)  cmd='print cdbl(15777007!-(-1000222!))'; dump=992; run=1192 ;;
    L5)  cmd='print cdbl(15777182!-(-1000037!))'; dump=992; run=1192 ;;
    L6)  cmd='print cdbl(15777112!-(-1000111!))'; dump=992; run=1192 ;;
    L7)  cmd='print cdbl(15777042!-(-1000185!))'; dump=992; run=1192 ;;
    L8)  cmd='print cdbl(3000000!-(-1000000!))'; dump=984; run=1184 ;;
    M1)  cmd='print cdbl(2259!*9807!)'; dump=912; run=1112 ;;
    M2)  cmd='print cdbl(2259!*8771!)'; dump=912; run=1112 ;;
    M3)  cmd='print cdbl(2259!*7439!)'; dump=912; run=1112 ;;
    M4)  cmd='print cdbl(2259!*8253!)'; dump=912; run=1112 ;;
    M5)  cmd='print cdbl(2259!*15010!)'; dump=920; run=1120 ;;
    M6)  cmd='print cdbl(153!*290175!)'; dump=920; run=1120 ;;
    M7)  cmd='print cdbl(153!*430259!)'; dump=920; run=1120 ;;
    M8)  cmd='print cdbl(2259!*150091!)'; dump=928; run=1128 ;;
    M9)  cmd='print cdbl(2259!*40025!)'; dump=920; run=1120 ;;
    M10) cmd='print cdbl(153!*710427!)'; dump=920; run=1120 ;;
    M11) cmd='print cdbl(2259!*100061!)'; dump=928; run=1128 ;;
    M12) cmd='print cdbl(6662!*950571!)'; dump=928; run=1128 ;;
    M13) cmd='print cdbl(6662!*680409!)'; dump=928; run=1128 ;;
    M14) cmd='print cdbl(100061!*230139!)'; dump=944; run=1144 ;;
    M15) cmd='print cdbl(1000!*2000!)'; dump=912; run=1112 ;;
    M16) cmd='print cdbl(999!*999!)'; dump=896; run=1096 ;;
    N1)  cmd='print cdbl(881!/1397!)'; dump=904; run=1104 ;;
    N2)  cmd='print cdbl(181!/1393!)'; dump=904; run=1104 ;;
    N3)  cmd='print cdbl(1387!/1399!)'; dump=912; run=1112 ;;
    N4)  cmd='print cdbl(287!/1395!)'; dump=904; run=1104 ;;
    N5)  cmd='print cdbl(784!/611!)'; dump=896; run=1096 ;;
    N6)  cmd='print cdbl(514!/402!)'; dump=896; run=1096 ;;
    N7)  cmd='print cdbl(52!/167!)'; dump=888; run=1088 ;;
    N8)  cmd='print cdbl(1000!/4!)'; dump=888; run=1088 ;;
    *)
      return 2
      ;;
  esac
  PRINT_DUMP=$dump
  PRINT_RUN=$run
  PRINT_BEFORE=690
  PRINT_ARM_ARGS=(--type-at 300 --type '\n' --type-at 700 --type "${cmd}\\n")
}

# -----------------------------------------------------------------------
# l4-c8 超越関数(SIN/COS/TAN/ATN/EXP/LOG/SQR)の単精度適合場面（59腕、
# 7群: sin5・cos5・tan5・atn12・exp14・log14・sqr4）。事前登録: docs/notes/
# l4-c8-transcendental-conformance-scene-preregistration.md。
#
# SIN/COS/TAN(5腕ずつ)は docs/notes/l4-s6g-away-rounding-transcendentals-
# preregistration.md「腕」節のZ01〜Z15と完全に同一(away丸め、35腕中の
# SIN/COS/TAN15腕、100%一致で確定済み)。
# ATN/EXP/LOG(12/14/14腕)は docs/notes/l4-s6h-atn-exp-log-more-arms-
# preregistration.md「腕」節のH03〜H42と完全に同一(away丸めで確定済み。
# H01`atn(1)`・H02`atn(-1)`は l4-s6h が確認した未解決の既知差=分岐境界
# `|x|=1`のため除外)。腕idはZ/Hの番号のままでは関数の判別が付かない
# ため、trans_arm_group()が接頭辞で群を判定できるよう関数名接頭辞
# (SIN/COS/TAN/ATN/EXP/LOG)+通し番号へ付け替えた(打鍵文字列・写し(後)・
# 走行フレームの値そのものは変更しない)。
# SQR(4腕)は docs/notes/l4-s6a-transcendental-functions-preregistration.md
# 「腕」節のS1〜S4と完全に同一(単精度・無理数入力・l4-s6aで
# predicted_matchが確認済みの4腕。S5は倍精度引数`#`、S7は`sqr(-1)`の
# エラー系のため除外)。SQR群は既にsrc/l4_basic配下(拡張ROMバンク0)に
# 実装済み(`a3fb09e`)のため、見出しコメントはselfmade=implementedで
# 始める。2026-09-20追記: SIN/COS/TANも拡張ROMバンク0
# (EXT_BANK0_SIN_ENTRY/COS_ENTRY/TAN_ENTRY、第4.16a節)に実装したため、
# tests/conformance/expected_l4_trans.tsvのsin/cos/tan群もselfmade=
# implementedへ切り替えた。2026-09-20さらに追記: ATN/EXP/LOGも拡張ROM
# バンク0(EXT_BANK0_ATN_ENTRY/EXP_ENTRY/LOG_ENTRY、第4.16b節、`l4-s6h`
# で確定したround-half-away丸め)に実装したため、atn/exp/log群も
# selfmade=implementedへ切り替えた(全7群がimplementedになった)。
#
# 写し(前)は全腕690固定。写し(後)・走行フレームは腕ごとに
# l4-s6g/l4-s6h/l4-s6aの表の値をそのまま埋め込む(line_end=700+8*
# 打鍵文字数(\n込み)・dump=line_end+20・run=dump+200で既に導出済みの
# 値を再計算し直さない。l4-c7のARITH場面と同じ方針)。
# -----------------------------------------------------------------------
TRANS_ARM_NAMES=(
  SIN1 SIN2 SIN3 SIN4 SIN5
  COS1 COS2 COS3 COS4 COS5
  TAN1 TAN2 TAN3 TAN4 TAN5
  ATN1 ATN2 ATN3 ATN4 ATN5 ATN6 ATN7 ATN8 ATN9 ATN10 ATN11 ATN12
  EXP1 EXP2 EXP3 EXP4 EXP5 EXP6 EXP7 EXP8 EXP9 EXP10 EXP11 EXP12 EXP13 EXP14
  LOG1 LOG2 LOG3 LOG4 LOG5 LOG6 LOG7 LOG8 LOG9 LOG10 LOG11 LOG12 LOG13 LOG14
  SQR1 SQR2 SQR3 SQR4
)

trans_arm_params() {
  local arm="$1" cmd dump run
  case "$arm" in
    # SIN(l4-s6g Z01〜Z05)
    SIN1) cmd='print cdbl(sin(3))';     dump=872; run=1072 ;;
    SIN2) cmd='print cdbl(sin(6))';     dump=872; run=1072 ;;
    SIN3) cmd='print cdbl(sin(162))';   dump=888; run=1088 ;;
    SIN4) cmd='print cdbl(sin(168))';   dump=888; run=1088 ;;
    SIN5) cmd='print cdbl(sin(10124))'; dump=904; run=1104 ;;
    # COS(l4-s6g Z06〜Z10)
    COS1) cmd='print cdbl(cos(24))';    dump=880; run=1080 ;;
    COS2) cmd='print cdbl(cos(28))';    dump=880; run=1080 ;;
    COS3) cmd='print cdbl(cos(132))';   dump=888; run=1088 ;;
    COS4) cmd='print cdbl(cos(145))';   dump=888; run=1088 ;;
    COS5) cmd='print cdbl(cos(12605))'; dump=904; run=1104 ;;
    # TAN(l4-s6g Z11〜Z15)
    TAN1) cmd='print cdbl(tan(3))';     dump=872; run=1072 ;;
    TAN2) cmd='print cdbl(tan(6))';     dump=872; run=1072 ;;
    TAN3) cmd='print cdbl(tan(140))';   dump=888; run=1088 ;;
    TAN4) cmd='print cdbl(tan(162))';   dump=888; run=1088 ;;
    TAN5) cmd='print cdbl(tan(11356))'; dump=904; run=1104 ;;
    # ATN(l4-s6h H03〜H14。H01/H02=atn(1)/atn(-1)は既知未解決差のため除外)
    ATN1)  cmd='print cdbl(atn(33))';   dump=880; run=1080 ;;
    ATN2)  cmd='print cdbl(atn(-33))';  dump=888; run=1088 ;;
    ATN3)  cmd='print cdbl(atn(215))';  dump=888; run=1088 ;;
    ATN4)  cmd='print cdbl(atn(-215))'; dump=896; run=1096 ;;
    ATN5)  cmd='print cdbl(atn(1.6))';  dump=888; run=1088 ;;
    ATN6)  cmd='print cdbl(atn(0.27))'; dump=896; run=1096 ;;
    ATN7)  cmd='print cdbl(atn(0.83))'; dump=896; run=1096 ;;
    ATN8)  cmd='print cdbl(atn(3.3))';  dump=888; run=1088 ;;
    ATN9)  cmd='print cdbl(atn(7.2))';  dump=888; run=1088 ;;
    # ATN10(atn(0.42))は自作ROM側でcell_count不一致(17 vs 期待16)になる
    #既知の残存差(2026-09-20判明、docs/spec/l4-program.md 第8節参照)。
    # 直接注入(バンクルーチン単体、FIN経由しない)でtools/l4_mbf_oracle_
    # v10_m9.py atn_implと照合すると一致するが、実際に「0.42」をFINで
    # 解釈した値(MBF_OPAを実測)をatn_implへ渡すと一致しない——原因は
    # ATNの計算そのものではなく、FINの十進小数解釈またはCDBL/PRINTの
    # 桁生成側にある可能性が高い(いずれも本節の対象外の既存モジュール)。
    # dump/runを大きくしても解消しない(タイミングの問題ではないことを
    # 確認済み)ため、既定値のまま残す。
    ATN10) cmd='print cdbl(atn(0.42))'; dump=896; run=1096 ;;
    ATN11) cmd='print cdbl(atn(2))';    dump=872; run=1072 ;;
    ATN12) cmd='print cdbl(atn(0.5))';  dump=888; run=1088 ;;
    # EXP(l4-s6h H15〜H28)
    EXP1)  cmd='print cdbl(exp(4))';   dump=872; run=1072 ;;
    EXP2)  cmd='print cdbl(exp(-5))';  dump=880; run=1080 ;;
    EXP3)  cmd='print cdbl(exp(18))';  dump=880; run=1080 ;;
    EXP4)  cmd='print cdbl(exp(-12))'; dump=888; run=1088 ;;
    EXP5)  cmd='print cdbl(exp(35))';  dump=880; run=1080 ;;
    # EXP6/EXP8/EXP10はdump=888(他のEXP腕と同じ既定値)だと自作ROM側で
    # G8(写しが早すぎた)になった(2026-09-20。ATN10と同じ理由——絶対値の
    # 大きい負の引数ほどexp(x)が極端に小さくなり、CDBL全16桁展開の表示
    # 〔MBF_FOUTの内部スケーリング〕により多くのフレームを要するとみられる。
    # l4_atnexplog_bank_conform.pyのバイト照合〔2000件不一致0〕は
    # 通過済みのため値そのものの誤りではない)。
    EXP6)  cmd='print cdbl(exp(-22))'; dump=1400; run=1600 ;;
    EXP7)  cmd='print cdbl(exp(54))';  dump=880; run=1080 ;;
    EXP8)  cmd='print cdbl(exp(-35))'; dump=1400; run=1600 ;;
    EXP9)  cmd='print cdbl(exp(70))';  dump=880; run=1080 ;;
    EXP10) cmd='print cdbl(exp(-48))'; dump=1400; run=1600 ;;
    EXP11) cmd='print cdbl(exp(23))';  dump=880; run=1080 ;;
    EXP12) cmd='print cdbl(exp(-7))';  dump=880; run=1080 ;;
    EXP13) cmd='print cdbl(exp(1))';   dump=872; run=1072 ;;
    EXP14) cmd='print cdbl(exp(-1))';  dump=880; run=1080 ;;
    # LOG(l4-s6h H29〜H42)
    LOG1)  cmd='print cdbl(log(2))';   dump=872; run=1072 ;;
    LOG2)  cmd='print cdbl(log(4))';   dump=872; run=1072 ;;
    LOG3)  cmd='print cdbl(log(6))';   dump=872; run=1072 ;;
    LOG4)  cmd='print cdbl(log(9))';   dump=872; run=1072 ;;
    LOG5)  cmd='print cdbl(log(18))';  dump=880; run=1080 ;;
    LOG6)  cmd='print cdbl(log(26))';  dump=880; run=1080 ;;
    LOG7)  cmd='print cdbl(log(36))';  dump=880; run=1080 ;;
    LOG8)  cmd='print cdbl(log(45))';  dump=880; run=1080 ;;
    LOG9)  cmd='print cdbl(log(58))';  dump=880; run=1080 ;;
    LOG10) cmd='print cdbl(log(65))';  dump=880; run=1080 ;;
    LOG11) cmd='print cdbl(log(72))';  dump=880; run=1080 ;;
    LOG12) cmd='print cdbl(log(90))';  dump=880; run=1080 ;;
    LOG13) cmd='print cdbl(log(1.5))'; dump=888; run=1088 ;;
    LOG14) cmd='print cdbl(log(5))';   dump=872; run=1072 ;;
    # SQR(l4-s6a S1〜S4。単精度・実装済み。cdblは使わない=l4-s6a原型のまま)
    SQR1) cmd='print sqr(2)';      dump=824; run=1024 ;;
    SQR2) cmd='print sqr(3)';      dump=824; run=1024 ;;
    SQR3) cmd='print sqr(.5)';     dump=832; run=1032 ;;
    SQR4) cmd='print sqr(123456)'; dump=864; run=1064 ;;
    *)
      return 2
      ;;
  esac
  PRINT_DUMP=$dump
  PRINT_RUN=$run
  PRINT_BEFORE=690
  PRINT_ARM_ARGS=(--type-at 300 --type '\n' --type-at 700 --type "${cmd}\\n")
}

# -----------------------------------------------------------------------
# l4-c5 代表プログラム集の適合場面（P1〜P8の8腕、1群"programs"のみ）。
# 事前登録 docs/notes/l4-c5-representative-programs-conformance-scene-
# preregistration.md（`2837926`）「腕」節＋追補1〜3（`ebe29dc`・
# `89b503e`・`f0172d0`）と完全に同一（変更しない）。
#
# 腕の入力は tools/l4_program_typeplan.py が組み立てる打鍵計画
# （new→cls→各行→G9確認→cls→前の写し→run→(P8のみ入力値)→後の写し）を
# tools/l4_program_run.sh がそのまま実行する。二重実装しない
# （フレーム式の計算はtypeplan.py側にだけ存在する）。
# -----------------------------------------------------------------------
PROGRAM_ARM_NAMES=(P1 P2 P3 P4 P5 P6 P7 P8)

# 腕idから tests/programs/*.bas のパスを返す。
program_arm_bas() {
  local arm="$1"
  case "$arm" in
    P1) echo "$REPO/tests/programs/p01_kuku.bas" ;;
    P2) echo "$REPO/tests/programs/p02_primes.bas" ;;
    P3) echo "$REPO/tests/programs/p03_bubble_sort.bas" ;;
    P4) echo "$REPO/tests/programs/p04_fibonacci.bas" ;;
    P5) echo "$REPO/tests/programs/p05_factorial.bas" ;;
    P6) echo "$REPO/tests/programs/p06_strings.bas" ;;
    P7) echo "$REPO/tests/programs/p07_gosub_subroutine.bas" ;;
    P8) echo "$REPO/tests/programs/p08_input_calc.bas" ;;
    *) return 2 ;;
  esac
}

# 腕idからINPUTに打つ値を返す（P8のみ。tests/programs/README.md記載の
# 固定値5,3）。P1〜P7は空文字列。
program_arm_input() {
  local arm="$1"
  case "$arm" in
    P8) echo "5,3" ;;
    *) echo "" ;;
  esac
}

# -----------------------------------------------------------------------
# PROGRAM場面の1腕を1回走らせ、正規化した記録・関門G9/G10の判定を返す。
# G2(打てない文字警告0)は tools/l4_program_run.sh 側で確認済み(rc!=0で
# 検出)。q88measureの起動時クラッシュ(既知欠陥、tools/lib_l3_measure.sh
# のrun_q88measure_retryと同じ理由)に備え、l4_program_run.sh自体を
# 呼び出し単位で再試行する。
#
# $1 = ROMディレクトリ、$2 = 出力プレフィックス、$3 = .basパス、
# $4 = INPUT値（無ければ空文字列）
#
# 出力(TSV、1行): status<TAB>cell_count<TAB>ok_relative_row<TAB>sha256<TAB>g9_ok<TAB>g10_ok
# （g9_ok/g10_okは"1"(真)/"0"(偽)。cell_count等がstatus!=okならNA、
# g10_okはstatus!=okならNA。値そのもの・画面本文は一切出さない）
# -----------------------------------------------------------------------
run_program_arm_once() {
  local romdir="$1" prefix="$2" bas="$3" input="$4"
  local attempt=1 run_out="" rc=1

  while [ "$attempt" -le "$Q88_MEASURE_ATTEMPTS" ]; do
    if [ -n "$input" ]; then
      run_out="$(bash "$PROGRAM_RUN" --bas "$bas" --rom-dir "$romdir" --out-prefix "$prefix" --input "$input" 2>"$prefix.run.err.txt")"
    else
      run_out="$(bash "$PROGRAM_RUN" --bas "$bas" --rom-dir "$romdir" --out-prefix "$prefix" 2>"$prefix.run.err.txt")"
    fi
    rc=$?
    if [ "$rc" -eq 0 ]; then
      if [ "$attempt" -gt 1 ]; then
        echo "  [注記] ${prefix}: q88measureの起動時クラッシュのため${attempt}回目で成功した(既知欠陥。docs/notes/m7az-write-conformance.md)" >&2
      fi
      break
    fi
    echo "  [注記] ${prefix}: l4_program_run.shがrc=${rc}で失敗した(${attempt}/${Q88_MEASURE_ATTEMPTS}回目)" >&2
    attempt=$((attempt + 1))
  done

  if [ "$rc" -ne 0 ]; then
    echo "gate_failed	NA	NA	NA	NA	NA"
    return 1
  fi

  local untyp g9_path before_path after_path plan_path
  untyp="$(printf '%s\n' "$run_out" | sed -n '1s/.*untypable_warning=\([0-9]\).*/\1/p')"
  g9_path="$(printf '%s\n' "$run_out" | awk -F= '/^g9=/{print $2}')"
  before_path="$(printf '%s\n' "$run_out" | awk -F= '/^before=/{print $2}')"
  after_path="$(printf '%s\n' "$run_out" | awk -F= '/^after=/{print $2}')"
  plan_path="$(printf '%s\n' "$run_out" | awk -F= '/^plan=/{print $2}')"

  if [ "$untyp" != "0" ] || [ -z "$g9_path" ] || [ -z "$before_path" ] || [ -z "$after_path" ] || [ -z "$plan_path" ]; then
    echo "gate_failed	NA	NA	NA	NA	NA"
    return 1
  fi

  local num_lines g9_ok
  num_lines="$(python3 -c "import json; print(json.load(open('$plan_path'))['num_lines'])" 2>/dev/null)"
  if [ -z "$num_lines" ]; then
    echo "gate_failed	NA	NA	NA	NA	NA"
    return 1
  fi
  g9_ok="$(python3 -c "
import sys
sys.path.insert(0, '$REPO/tools')
import l4_program_typeplan as tp
r = tp.check_keystroke_arrival('$g9_path', $num_lines)
print('1' if r['arrived'] else '0')
" 2>/dev/null)"
  [ -n "$g9_ok" ] || g9_ok="0"

  local rec status cell ok_rel sha g10_ok
  rec="$(python3 "$PROGRAM_RECORD" --before "$before_path" --after "$after_path" 2>/dev/null)"
  status="$(printf '%s' "$rec" | cut -f1)"
  cell="$(printf '%s' "$rec" | cut -f2)"
  ok_rel="$(printf '%s' "$rec" | cut -f3)"
  sha="$(printf '%s' "$rec" | cut -f4)"

  g10_ok="NA"
  if [ "$status" = "ok" ]; then
    g10_ok="$(python3 -c "
import sys
sys.path.insert(0, '$REPO/tools')
import l4_program_typeplan as tp
r = tp.check_output_fits_screen($ok_rel)
print('1' if r['fits'] else '0')
" 2>/dev/null)"
    [ -n "$g10_ok" ] || g10_ok="0"
  fi

  echo "${status}	${cell}	${ok_rel}	${sha}	${g9_ok}	${g10_ok}"
  [ "$status" = "ok" ]
}

# 記録(cell_count/ok_relative_row/sha256、PRINT場面と同一書式)を期待値
# と照合する。PROGRAM場面の記録行は先頭に status 列が付くため、
# check_print_record_against_expected をそのまま使わず専用関数にする。
check_program_record_against_expected() {
  local arm="$1" expected="$2" actual_line="$3"
  local e_count e_ok e_sha a_count a_ok a_sha row
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$expected")"
  if [ -z "$row" ]; then
    echo "gate_failed"
    return
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_ok="$(printf '%s' "$row" | cut -f3)"
  e_sha="$(printf '%s' "$row" | cut -f4)"
  a_count="$(printf '%s' "$actual_line" | cut -f2)"
  a_ok="$(printf '%s' "$actual_line" | cut -f3)"
  a_sha="$(printf '%s' "$actual_line" | cut -f4)"
  if [ "$a_count" != "$e_count" ] || [ "$a_ok" != "$e_ok" ]; then
    echo "not_conform(件数不一致)"
  elif [ "$a_sha" != "$e_sha" ]; then
    echo "not_conform(sha256不一致)"
  else
    echo "conform"
  fi
}

# -----------------------------------------------------------------------
# PRINT場面の1腕を1回走らせ、正規化した記録(TSV: cell_count/
# ok_relative_row/sha256)を返す。G2(打てない文字警告0)もここで確認する。
#
# $1 = ROMディレクトリ、$2 = 出力プレフィックス、残りはARM_ARGS
# -----------------------------------------------------------------------
run_print_arm_once() {
  local romdir="$1" prefix="$2"; shift 2
  local core
  core="$(find_l3_core)"
  if [ -z "$core" ]; then
    echo "エラー: コアが無い。tools/setup_harness.sh を先に実行すること" >&2
    return 1
  fi
  local before_out after_out
  before_out="$(vram_out_path "$prefix.before.bin" "$PRINT_BEFORE")"
  after_out="$(vram_out_path "$prefix.after.bin" "$PRINT_DUMP")"
  run_q88measure_retry "$prefix.iolog.txt" "$prefix.stdout.txt" "$prefix.stderr.txt" \
      --core "$core" --rom-dir "$romdir" --frames "$PRINT_RUN" \
      --vram-dump "$prefix.before.bin" --vram-dump-at "$PRINT_BEFORE" \
      --vram-dump "$prefix.after.bin" --vram-dump-at "$PRINT_DUMP" \
      "$@" || return 1
  if grep -qi 'untypable\|打てない' "$prefix.stderr.txt" 2>/dev/null; then
    echo "エラー: 打てない文字の警告が出た（G2違反）: $prefix" >&2
    return 3
  fi
  if [ ! -f "$before_out" ] || [ ! -f "$after_out" ]; then
    echo "エラー: VRAM写しが書き出されなかった: $before_out / $after_out" >&2
    return 1
  fi
  python3 "$PRINT_RECORD" --before "$before_out" --after "$after_out" \
      --count-only-rows 19
}

# -----------------------------------------------------------------------
# 1腕を1回走らせ、正規化した記録(TSV: cell_count/nonblank_count/
# attr_row_count/sha256)を返す。G2(打てない文字警告0)もここで確認する。
#
# $1 = ROMディレクトリ、$2 = 出力プレフィックス、残りはARM_ARGS
# -----------------------------------------------------------------------
run_arm_once() {
  local romdir="$1" prefix="$2"; shift 2
  local core frontend
  core="$(find_l3_core)"
  frontend="$REPO/tools/harness/frontend/q88measure"
  if [ -z "$core" ]; then
    echo "エラー: コアが無い。tools/setup_harness.sh を先に実行すること" >&2
    return 1
  fi
  local before_out after_out
  before_out="$(vram_out_path "$prefix.before.bin" "$BEFORE")"
  after_out="$(vram_out_path "$prefix.after.bin" "$AFTER")"
  run_q88measure_retry "$prefix.iolog.txt" "$prefix.stdout.txt" "$prefix.stderr.txt" \
      --core "$core" --rom-dir "$romdir" --frames "$FRAMES" \
      --vram-dump "$prefix.before.bin" --vram-dump-at "$BEFORE" \
      --vram-dump "$prefix.after.bin" --vram-dump-at "$AFTER" \
      "$@" || return 1
  if grep -qi 'untypable\|打てない' "$prefix.stderr.txt" 2>/dev/null; then
    echo "エラー: 打てない文字の警告が出た（G2違反）: $prefix" >&2
    return 3
  fi
  if [ ! -f "$before_out" ] || [ ! -f "$after_out" ]; then
    echo "エラー: VRAM写しが書き出されなかった: $before_out / $after_out" >&2
    return 1
  fi
  python3 "$RECORD" --before "$before_out" --after "$after_out" \
      --count-only-rows 19
}

# G4用: 何も打たない走(起動settleのみ)で、全行(row19含む)の変化が0件か
# どうかを確認する。既存tools/l4_vram_probe.pyのCLIをそのまま使う。
run_negative_control() {
  local romdir="$1" prefix="$2"
  local core before_out after_out
  core="$(find_l3_core)"
  before_out="$(vram_out_path "$prefix.before.bin" 690)"
  after_out="$(vram_out_path "$prefix.after.bin" 752)"
  # E1と同じ余裕(frames=952)を使う。frames=afterぴったりだと写しが
  # 書き出されない(dumpは指定フレームに達する直前のretro_run()呼び出しの
  # 直前で行われるため、frames==afterでは間に合わないことがある)。
  run_q88measure_retry "$prefix.iolog.txt" "$prefix.stdout.txt" "$prefix.stderr.txt" \
      --core "$core" --rom-dir "$romdir" --frames 952 \
      --vram-dump "$prefix.before.bin" --vram-dump-at 690 \
      --vram-dump "$prefix.after.bin" --vram-dump-at 752 \
      --type-at 300 --type '\n' || return 1
  python3 "$PROBE" --diff-before "$before_out" --diff-after "$after_out" \
      --count-only-rows 19 --json
}

# -----------------------------------------------------------------------
# 検出力の自己検査（公式環境が無くても常に実行する）。
#
# a. 自作main ROM記録を1バイト変える → SHA-256が変わりnot_conformになる
# b. 期待値の1行(件数/SHA-256)を壊す → 正しい記録との照合で検出できる
# -----------------------------------------------------------------------
say "検出力の自己検査（記録・期待値をわざと壊して検出できるか）"

selftest_rc=0
mkdir -p "$WORK/selftest"

python3 - "$WORK/selftest" <<'PYEOF'
import sys
out = sys.argv[1]
data_before = bytearray(3000)
for r in range(25):
    for c in range(80):
        data_before[r * 120 + c] = 0x20
data_after = bytearray(data_before)
codes = [0x61, 0x62, 0x31, 0x32]
for i, ch in enumerate(codes):
    data_after[4 * 120 + i] = ch
with open(out + "/before.bin", "wb") as f:
    f.write(bytes(data_before))
with open(out + "/after.bin", "wb") as f:
    f.write(bytes(data_after))
# 1バイトだけ違う対照(属性域の1バイトを変える)
data_after2 = bytearray(data_after)
data_after2[4 * 120 + 80] = 0x01
with open(out + "/after_bad.bin", "wb") as f:
    f.write(bytes(data_after2))
PYEOF

good_line="$(python3 "$RECORD" --before "$WORK/selftest/before.bin" --after "$WORK/selftest/after.bin" --count-only-rows 19)"
bad_line="$(python3 "$RECORD" --before "$WORK/selftest/before.bin" --after "$WORK/selftest/after_bad.bin" --count-only-rows 19)"
good_sha="$(printf '%s' "$good_line" | cut -f4)"
bad_sha="$(printf '%s' "$bad_line" | cut -f4)"
if [ "$good_sha" != "$bad_sha" ]; then
  ok "自己検査a: 記録の属性1バイトを変えるとSHA-256が変わる(検出力あり)"
else
  ng "自己検査a: 記録の属性1バイトを変えてもSHA-256が変わらなかった"
  selftest_rc=1
fi

exp_good="$WORK/selftest/expected_good.tsv"
{
  echo "# selftest"
  printf 'selftest_arm\t%s\n' "$good_line"
} > "$exp_good"

check_record_against_expected() {
  # $1=arm名 $2=期待値TSV $3=実測record行 -> echo conform/not_conform
  local arm="$1" expected="$2" actual_line="$3"
  local e_count e_nonblank e_attr e_sha a_count a_nonblank a_attr a_sha row
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$expected")"
  if [ -z "$row" ]; then
    echo "gate_failed"
    return
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_nonblank="$(printf '%s' "$row" | cut -f3)"
  e_attr="$(printf '%s' "$row" | cut -f4)"
  e_sha="$(printf '%s' "$row" | cut -f5)"
  a_count="$(printf '%s' "$actual_line" | cut -f1)"
  a_nonblank="$(printf '%s' "$actual_line" | cut -f2)"
  a_attr="$(printf '%s' "$actual_line" | cut -f3)"
  a_sha="$(printf '%s' "$actual_line" | cut -f4)"
  if [ "$a_count" != "$e_count" ] || [ "$a_nonblank" != "$e_nonblank" ] || [ "$a_attr" != "$e_attr" ]; then
    echo "not_conform(件数不一致)"
  elif [ "$a_sha" != "$e_sha" ]; then
    echo "not_conform(sha256不一致)"
  else
    echo "conform"
  fi
}

verdict_b_self="$(check_record_against_expected selftest_arm "$exp_good" "$good_line")"
verdict_b_bad="$(check_record_against_expected selftest_arm "$exp_good" "$bad_line")"
if [ "$verdict_b_self" = "conform" ] && [ "${verdict_b_bad#not_conform}" != "$verdict_b_bad" ]; then
  ok "自己検査b1: 正しい記録は期待値と conform、壊した記録は not_conform"
else
  ng "自己検査b1: 正しい記録(${verdict_b_self})/壊した記録(${verdict_b_bad})の判定がおかしい"
  selftest_rc=1
fi

# 期待値の1行(件数)を壊す
exp_bad_count="$WORK/selftest/expected_bad_count.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next} {$2=$2+1; print}' "$exp_good" > "$exp_bad_count"
verdict_c="$(check_record_against_expected selftest_arm "$exp_bad_count" "$good_line")"
if [ "${verdict_c#not_conform}" != "$verdict_c" ]; then
  ok "自己検査c: 期待値の件数を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査c: 件数を壊した期待値が誤って conform になった"
  selftest_rc=1
fi

# 期待値の1行(SHA-256)を壊す
exp_bad_sha="$WORK/selftest/expected_bad_sha.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next}
     {sha=$5; last=substr(sha,length(sha),1); $5=substr(sha,1,length(sha)-1) (last=="0"?"f":"0"); print}' \
    "$exp_good" > "$exp_bad_sha"
verdict_d="$(check_record_against_expected selftest_arm "$exp_bad_sha" "$good_line")"
if [ "${verdict_d#not_conform}" != "$verdict_d" ]; then
  ok "自己検査d: 期待値のSHA-256を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査d: SHA-256を壊した期待値が誤って conform になった"
  selftest_rc=1
fi

if [ "$selftest_rc" -eq 0 ]; then
  ok "検出力の自己検査: 全項目OK"
else
  ng "検出力の自己検査: 失敗した項目がある"
fi
overall_rc=$(( overall_rc || selftest_rc ))

# -----------------------------------------------------------------------
# PRINT場面用の検出力自己検査（公式環境が無くても常に実行する）。
# 記録の形が異なる(cell_count/ok_relative_row/sha256の3列)ため、echo場面
# の自己検査とは別に、専用の照合関数(check_print_record_against_expected)
# で同じ4項目(a/b1/c/d)を確かめる。
# -----------------------------------------------------------------------
say "検出力の自己検査(PRINT場面。記録・期待値をわざと壊して検出できるか)"

print_selftest_rc=0
mkdir -p "$WORK/selftest_print"

python3 - "$WORK/selftest_print" <<'PYEOF'
import sys
out = sys.argv[1]
STRIDE = 120
before = bytearray(25 * STRIDE)
for r in range(25):
    for c in range(80):
        before[r * STRIDE + c] = 0x20
after = bytearray(before)
cmd = b"print 1"
for i, ch in enumerate(cmd):
    after[6 * STRIDE + i] = ch
after[7 * STRIDE + 0] = ord('1')
after[8 * STRIDE + 0] = ord('O')
after[8 * STRIDE + 1] = ord('k')
with open(out + "/before.bin", "wb") as f:
    f.write(bytes(before))
with open(out + "/after.bin", "wb") as f:
    f.write(bytes(after))
# 1バイトだけ違う対照(出力セルの文字コードを変える)
after2 = bytearray(after)
after2[7 * STRIDE + 0] = ord('2')
with open(out + "/after_bad.bin", "wb") as f:
    f.write(bytes(after2))
PYEOF

good_line_p="$(python3 "$PRINT_RECORD" --before "$WORK/selftest_print/before.bin" --after "$WORK/selftest_print/after.bin" --count-only-rows 19)"
bad_line_p="$(python3 "$PRINT_RECORD" --before "$WORK/selftest_print/before.bin" --after "$WORK/selftest_print/after_bad.bin" --count-only-rows 19)"
good_sha_p="$(printf '%s' "$good_line_p" | cut -f3)"
bad_sha_p="$(printf '%s' "$bad_line_p" | cut -f3)"
if [ "$good_sha_p" != "$bad_sha_p" ]; then
  ok "自己検査a(PRINT): 記録の出力セルを変えるとSHA-256が変わる(検出力あり)"
else
  ng "自己検査a(PRINT): 記録の出力セルを変えてもSHA-256が変わらなかった"
  print_selftest_rc=1
fi

exp_good_p="$WORK/selftest_print/expected_good.tsv"
{
  echo "# selftest"
  printf 'selftest_arm\t%s\n' "$good_line_p"
} > "$exp_good_p"

check_print_record_against_expected() {
  # $1=arm名 $2=期待値TSV $3=実測record行 -> echo conform/not_conform
  local arm="$1" expected="$2" actual_line="$3"
  local e_count e_ok e_sha a_count a_ok a_sha row
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$expected")"
  if [ -z "$row" ]; then
    echo "gate_failed"
    return
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_ok="$(printf '%s' "$row" | cut -f3)"
  e_sha="$(printf '%s' "$row" | cut -f4)"
  a_count="$(printf '%s' "$actual_line" | cut -f1)"
  a_ok="$(printf '%s' "$actual_line" | cut -f2)"
  a_sha="$(printf '%s' "$actual_line" | cut -f3)"
  if [ "$a_count" != "$e_count" ] || [ "$a_ok" != "$e_ok" ]; then
    echo "not_conform(件数不一致)"
  elif [ "$a_sha" != "$e_sha" ]; then
    echo "not_conform(sha256不一致)"
  else
    echo "conform"
  fi
}

verdict_b_self_p="$(check_print_record_against_expected selftest_arm "$exp_good_p" "$good_line_p")"
verdict_b_bad_p="$(check_print_record_against_expected selftest_arm "$exp_good_p" "$bad_line_p")"
if [ "$verdict_b_self_p" = "conform" ] && [ "${verdict_b_bad_p#not_conform}" != "$verdict_b_bad_p" ]; then
  ok "自己検査b1(PRINT): 正しい記録は期待値と conform、壊した記録は not_conform"
else
  ng "自己検査b1(PRINT): 正しい記録(${verdict_b_self_p})/壊した記録(${verdict_b_bad_p})の判定がおかしい"
  print_selftest_rc=1
fi

exp_bad_count_p="$WORK/selftest_print/expected_bad_count.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next} {$2=$2+1; print}' "$exp_good_p" > "$exp_bad_count_p"
verdict_c_p="$(check_print_record_against_expected selftest_arm "$exp_bad_count_p" "$good_line_p")"
if [ "${verdict_c_p#not_conform}" != "$verdict_c_p" ]; then
  ok "自己検査c(PRINT): 期待値の件数を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査c(PRINT): 件数を壊した期待値が誤って conform になった"
  print_selftest_rc=1
fi

exp_bad_sha_p="$WORK/selftest_print/expected_bad_sha.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next}
     {sha=$4; last=substr(sha,length(sha),1); $4=substr(sha,1,length(sha)-1) (last=="0"?"f":"0"); print}' \
    "$exp_good_p" > "$exp_bad_sha_p"
verdict_d_p="$(check_print_record_against_expected selftest_arm "$exp_bad_sha_p" "$good_line_p")"
if [ "${verdict_d_p#not_conform}" != "$verdict_d_p" ]; then
  ok "自己検査d(PRINT): 期待値のSHA-256を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査d(PRINT): SHA-256を壊した期待値が誤って conform になった"
  print_selftest_rc=1
fi

if [ "$print_selftest_rc" -eq 0 ]; then
  ok "検出力の自己検査(PRINT): 全項目OK"
else
  ng "検出力の自己検査(PRINT): 失敗した項目がある"
fi
overall_rc=$(( overall_rc || print_selftest_rc ))

# -----------------------------------------------------------------------
# l4-c3 浮動小数点PRINT場面用の検出力自己検査（公式環境不要）。
# 記録の書式はPRINT場面と全く同一(cell_count/ok_relative_row/sha256)
# なので、既存のcheck_print_record_against_expectedをそのまま使い回す
# (二重実装しない)。フィクスチャだけPRINT場面用と別に用意する。
# -----------------------------------------------------------------------
say "検出力の自己検査(FLOAT場面。記録・期待値をわざと壊して検出できるか)"

float_selftest_rc=0
mkdir -p "$WORK/selftest_float"

python3 - "$WORK/selftest_float" <<'PYEOF'
import sys
out = sys.argv[1]
STRIDE = 120
before = bytearray(25 * STRIDE)
for r in range(25):
    for c in range(80):
        before[r * STRIDE + c] = 0x20
after = bytearray(before)
cmd = b"print 1.5"
for i, ch in enumerate(cmd):
    after[6 * STRIDE + i] = ch
for i, ch in enumerate(b"1.5"):
    after[7 * STRIDE + 1 + i] = ch
after[8 * STRIDE + 0] = ord('O')
after[8 * STRIDE + 1] = ord('k')
with open(out + "/before.bin", "wb") as f:
    f.write(bytes(before))
with open(out + "/after.bin", "wb") as f:
    f.write(bytes(after))
# 1バイトだけ違う対照(出力セルの文字コードを変える)
after2 = bytearray(after)
after2[7 * STRIDE + 1] = ord('2')
with open(out + "/after_bad.bin", "wb") as f:
    f.write(bytes(after2))
PYEOF

good_line_f="$(python3 "$PRINT_RECORD" --before "$WORK/selftest_float/before.bin" --after "$WORK/selftest_float/after.bin" --count-only-rows 19)"
bad_line_f="$(python3 "$PRINT_RECORD" --before "$WORK/selftest_float/before.bin" --after "$WORK/selftest_float/after_bad.bin" --count-only-rows 19)"
good_sha_f="$(printf '%s' "$good_line_f" | cut -f3)"
bad_sha_f="$(printf '%s' "$bad_line_f" | cut -f3)"
if [ "$good_sha_f" != "$bad_sha_f" ]; then
  ok "自己検査a(FLOAT): 記録の出力セルを変えるとSHA-256が変わる(検出力あり)"
else
  ng "自己検査a(FLOAT): 記録の出力セルを変えてもSHA-256が変わらなかった"
  float_selftest_rc=1
fi

exp_good_f="$WORK/selftest_float/expected_good.tsv"
{
  echo "# selftest"
  printf 'selftest_arm\t%s\n' "$good_line_f"
} > "$exp_good_f"

verdict_b_self_f="$(check_print_record_against_expected selftest_arm "$exp_good_f" "$good_line_f")"
verdict_b_bad_f="$(check_print_record_against_expected selftest_arm "$exp_good_f" "$bad_line_f")"
if [ "$verdict_b_self_f" = "conform" ] && [ "${verdict_b_bad_f#not_conform}" != "$verdict_b_bad_f" ]; then
  ok "自己検査b1(FLOAT): 正しい記録は期待値と conform、壊した記録は not_conform"
else
  ng "自己検査b1(FLOAT): 正しい記録(${verdict_b_self_f})/壊した記録(${verdict_b_bad_f})の判定がおかしい"
  float_selftest_rc=1
fi

exp_bad_count_f="$WORK/selftest_float/expected_bad_count.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next} {$2=$2+1; print}' "$exp_good_f" > "$exp_bad_count_f"
verdict_c_f="$(check_print_record_against_expected selftest_arm "$exp_bad_count_f" "$good_line_f")"
if [ "${verdict_c_f#not_conform}" != "$verdict_c_f" ]; then
  ok "自己検査c(FLOAT): 期待値の件数を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査c(FLOAT): 件数を壊した期待値が誤って conform になった"
  float_selftest_rc=1
fi

exp_bad_sha_f="$WORK/selftest_float/expected_bad_sha.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next}
     {sha=$4; last=substr(sha,length(sha),1); $4=substr(sha,1,length(sha)-1) (last=="0"?"f":"0"); print}' \
    "$exp_good_f" > "$exp_bad_sha_f"
verdict_d_f="$(check_print_record_against_expected selftest_arm "$exp_bad_sha_f" "$good_line_f")"
if [ "${verdict_d_f#not_conform}" != "$verdict_d_f" ]; then
  ok "自己検査d(FLOAT): 期待値のSHA-256を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査d(FLOAT): SHA-256を壊した期待値が誤って conform になった"
  float_selftest_rc=1
fi

if [ "$float_selftest_rc" -eq 0 ]; then
  ok "検出力の自己検査(FLOAT): 全項目OK"
else
  ng "検出力の自己検査(FLOAT): 失敗した項目がある"
fi
overall_rc=$(( overall_rc || float_selftest_rc ))

# -----------------------------------------------------------------------
# l4-c5 代表プログラム集用の検出力自己検査（公式環境不要）。
# 記録の書式(status<TAB>cell_count<TAB>ok_relative_row<TAB>sha256)は
# tools/l4_program_conform_record.py の陽性対照フィクスチャ
# (tools/l4_program_conform_selftest.sh 検査1)と同じ形の合成VRAM写しを
# 使う(row0=runのエコー・row1=出力"42"・row2="Ok!"・row19=最下行)。
# -----------------------------------------------------------------------
say "検出力の自己検査(PROGRAM場面。記録・期待値をわざと壊して検出できるか)"

program_selftest_rc=0
mkdir -p "$WORK/selftest_program"

python3 - "$WORK/selftest_program" <<'PYEOF'
import sys
out = sys.argv[1]
ROWS, STRIDE = 25, 120

def blank():
    b = bytearray(ROWS * STRIDE)
    for r in range(ROWS):
        for c in range(80):
            b[r * STRIDE + c] = 0x20
    return b

before = blank()
after = blank()
for i, ch in enumerate("FKEYB"):
    before[19 * STRIDE + i] = ord(ch)
for i, ch in enumerate("FKEYA"):
    after[19 * STRIDE + i] = ord(ch)
for i, ch in enumerate("run"):
    after[0 * STRIDE + i] = ord(ch)
for i, ch in enumerate("42"):
    after[1 * STRIDE + i] = ord(ch)
for i, ch in enumerate("Ok!"):
    after[2 * STRIDE + i] = ord(ch)
with open(out + "/before.bin", "wb") as f:
    f.write(bytes(before))
with open(out + "/after.bin", "wb") as f:
    f.write(bytes(after))
after_bad = bytearray(after)
after_bad[1 * STRIDE + 1] = ord('9')
with open(out + "/after_bad.bin", "wb") as f:
    f.write(bytes(after_bad))
PYEOF

good_line_pg="$(python3 "$PROGRAM_RECORD" --before "$WORK/selftest_program/before.bin" --after "$WORK/selftest_program/after.bin")"
bad_line_pg="$(python3 "$PROGRAM_RECORD" --before "$WORK/selftest_program/before.bin" --after "$WORK/selftest_program/after_bad.bin")"
good_sha_pg="$(printf '%s' "$good_line_pg" | cut -f4)"
bad_sha_pg="$(printf '%s' "$bad_line_pg" | cut -f4)"
if [ "$good_sha_pg" != "$bad_sha_pg" ]; then
  ok "自己検査a(PROGRAM): 記録の出力セルを変えるとSHA-256が変わる(検出力あり)"
else
  ng "自己検査a(PROGRAM): 記録の出力セルを変えてもSHA-256が変わらなかった"
  program_selftest_rc=1
fi

exp_good_pg="$WORK/selftest_program/expected_good.tsv"
{
  echo "# selftest"
  a_count_pg="$(printf '%s' "$good_line_pg" | cut -f2)"
  a_ok_pg="$(printf '%s' "$good_line_pg" | cut -f3)"
  a_sha_pg="$(printf '%s' "$good_line_pg" | cut -f4)"
  printf 'selftest_arm\t%s\t%s\t%s\n' "$a_count_pg" "$a_ok_pg" "$a_sha_pg"
} > "$exp_good_pg"

verdict_b_self_pg="$(check_program_record_against_expected selftest_arm "$exp_good_pg" "$good_line_pg")"
verdict_b_bad_pg="$(check_program_record_against_expected selftest_arm "$exp_good_pg" "$bad_line_pg")"
if [ "$verdict_b_self_pg" = "conform" ] && [ "${verdict_b_bad_pg#not_conform}" != "$verdict_b_bad_pg" ]; then
  ok "自己検査b1(PROGRAM): 正しい記録は期待値と conform、壊した記録は not_conform"
else
  ng "自己検査b1(PROGRAM): 正しい記録(${verdict_b_self_pg})/壊した記録(${verdict_b_bad_pg})の判定がおかしい"
  program_selftest_rc=1
fi

exp_bad_count_pg="$WORK/selftest_program/expected_bad_count.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next} {$2=$2+1; print}' "$exp_good_pg" > "$exp_bad_count_pg"
verdict_c_pg="$(check_program_record_against_expected selftest_arm "$exp_bad_count_pg" "$good_line_pg")"
if [ "${verdict_c_pg#not_conform}" != "$verdict_c_pg" ]; then
  ok "自己検査c(PROGRAM): 期待値の件数を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査c(PROGRAM): 件数を壊した期待値が誤って conform になった"
  program_selftest_rc=1
fi

exp_bad_sha_pg="$WORK/selftest_program/expected_bad_sha.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next}
     {sha=$4; last=substr(sha,length(sha),1); $4=substr(sha,1,length(sha)-1) (last=="0"?"f":"0"); print}' \
    "$exp_good_pg" > "$exp_bad_sha_pg"
verdict_d_pg="$(check_program_record_against_expected selftest_arm "$exp_bad_sha_pg" "$good_line_pg")"
if [ "${verdict_d_pg#not_conform}" != "$verdict_d_pg" ]; then
  ok "自己検査d(PROGRAM): 期待値のSHA-256を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査d(PROGRAM): SHA-256を壊した期待値が誤って conform になった"
  program_selftest_rc=1
fi

if [ "$program_selftest_rc" -eq 0 ]; then
  ok "検出力の自己検査(PROGRAM): 全項目OK"
else
  ng "検出力の自己検査(PROGRAM): 失敗した項目がある"
fi
overall_rc=$(( overall_rc || program_selftest_rc ))

say "検出力の自己検査(ARITH場面。記録・期待値をわざと壊して検出できるか)"

arith_selftest_rc=0
mkdir -p "$WORK/selftest_arith"

python3 - "$WORK/selftest_arith" <<'PYEOF2'
import sys
out = sys.argv[1]
STRIDE = 120
before = bytearray(25 * STRIDE)
for r in range(25):
    for c in range(80):
        before[r * STRIDE + c] = 0x20
after = bytearray(before)
cmd = b"print cdbl(1!+1!)"
for i, ch in enumerate(cmd):
    after[6 * STRIDE + i] = ch
for i, ch in enumerate(b"2"):
    after[7 * STRIDE + 1 + i] = ch
after[8 * STRIDE + 0] = ord('O')
after[8 * STRIDE + 1] = ord('k')
with open(out + "/before.bin", "wb") as f:
    f.write(bytes(before))
with open(out + "/after.bin", "wb") as f:
    f.write(bytes(after))
# 1バイトだけ違う対照(出力セルの文字コードを変える)
after2 = bytearray(after)
after2[7 * STRIDE + 1] = ord('3')
with open(out + "/after_bad.bin", "wb") as f:
    f.write(bytes(after2))
PYEOF2

good_line_a="$(python3 "$PRINT_RECORD" --before "$WORK/selftest_arith/before.bin" --after "$WORK/selftest_arith/after.bin" --count-only-rows 19)"
bad_line_a="$(python3 "$PRINT_RECORD" --before "$WORK/selftest_arith/before.bin" --after "$WORK/selftest_arith/after_bad.bin" --count-only-rows 19)"
good_sha_a="$(printf '%s' "$good_line_a" | cut -f3)"
bad_sha_a="$(printf '%s' "$bad_line_a" | cut -f3)"
if [ "$good_sha_a" != "$bad_sha_a" ]; then
  ok "自己検査a(ARITH): 記録の出力セルを変えるとSHA-256が変わる(検出力あり)"
else
  ng "自己検査a(ARITH): 記録の出力セルを変えてもSHA-256が変わらなかった"
  arith_selftest_rc=1
fi

exp_good_a="$WORK/selftest_arith/expected_good.tsv"
{
  echo "# selftest"
  printf 'selftest_arm\t%s\n' "$good_line_a"
} > "$exp_good_a"

verdict_b_self_a="$(check_print_record_against_expected selftest_arm "$exp_good_a" "$good_line_a")"
verdict_b_bad_a="$(check_print_record_against_expected selftest_arm "$exp_good_a" "$bad_line_a")"
if [ "$verdict_b_self_a" = "conform" ] && [ "${verdict_b_bad_a#not_conform}" != "$verdict_b_bad_a" ]; then
  ok "自己検査b1(ARITH): 正しい記録は期待値と conform、壊した記録は not_conform"
else
  ng "自己検査b1(ARITH): 正しい記録(${verdict_b_self_a})/壊した記録(${verdict_b_bad_a})の判定がおかしい"
  arith_selftest_rc=1
fi

exp_bad_count_a="$WORK/selftest_arith/expected_bad_count.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next} {$2=$2+1; print}' "$exp_good_a" > "$exp_bad_count_a"
verdict_c_a="$(check_print_record_against_expected selftest_arm "$exp_bad_count_a" "$good_line_a")"
if [ "${verdict_c_a#not_conform}" != "$verdict_c_a" ]; then
  ok "自己検査c(ARITH): 期待値の件数を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査c(ARITH): 件数を壊した期待値が誤って conform になった"
  arith_selftest_rc=1
fi

exp_bad_sha_a="$WORK/selftest_arith/expected_bad_sha.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next}
     {sha=$4; last=substr(sha,length(sha),1); $4=substr(sha,1,length(sha)-1) (last=="0"?"f":"0"); print}' \
    "$exp_good_a" > "$exp_bad_sha_a"
verdict_d_a="$(check_print_record_against_expected selftest_arm "$exp_bad_sha_a" "$good_line_a")"
if [ "${verdict_d_a#not_conform}" != "$verdict_d_a" ]; then
  ok "自己検査d(ARITH): 期待値のSHA-256を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査d(ARITH): SHA-256を壊した期待値が誤って conform になった"
  arith_selftest_rc=1
fi

if [ "$arith_selftest_rc" -eq 0 ]; then
  ok "検出力の自己検査(ARITH): 全項目OK"
else
  ng "検出力の自己検査(ARITH): 失敗した項目がある"
fi
overall_rc=$(( overall_rc || arith_selftest_rc ))

say "検出力の自己検査(TRANS場面。記録・期待値をわざと壊して検出できるか)"

trans_selftest_rc=0
mkdir -p "$WORK/selftest_trans"

python3 - "$WORK/selftest_trans" <<'PYEOF3'
import sys
out = sys.argv[1]
STRIDE = 120
before = bytearray(25 * STRIDE)
for r in range(25):
    for c in range(80):
        before[r * STRIDE + c] = 0x20
after = bytearray(before)
cmd = b"print cdbl(sin(3))"
for i, ch in enumerate(cmd):
    after[6 * STRIDE + i] = ch
for i, ch in enumerate(b".1411202"):
    after[7 * STRIDE + i] = ch
after[8 * STRIDE + 0] = ord('O')
after[8 * STRIDE + 1] = ord('k')
with open(out + "/before.bin", "wb") as f:
    f.write(bytes(before))
with open(out + "/after.bin", "wb") as f:
    f.write(bytes(after))
# 1バイトだけ違う対照(出力セルの文字コードを変える)
after2 = bytearray(after)
after2[7 * STRIDE + 0] = ord('9')
with open(out + "/after_bad.bin", "wb") as f:
    f.write(bytes(after2))
PYEOF3

good_line_t="$(python3 "$PRINT_RECORD" --before "$WORK/selftest_trans/before.bin" --after "$WORK/selftest_trans/after.bin" --count-only-rows 19)"
bad_line_t="$(python3 "$PRINT_RECORD" --before "$WORK/selftest_trans/before.bin" --after "$WORK/selftest_trans/after_bad.bin" --count-only-rows 19)"
good_sha_t="$(printf '%s' "$good_line_t" | cut -f3)"
bad_sha_t="$(printf '%s' "$bad_line_t" | cut -f3)"
if [ "$good_sha_t" != "$bad_sha_t" ]; then
  ok "自己検査a(TRANS): 記録の出力セルを変えるとSHA-256が変わる(検出力あり)"
else
  ng "自己検査a(TRANS): 記録の出力セルを変えてもSHA-256が変わらなかった"
  trans_selftest_rc=1
fi

exp_good_t="$WORK/selftest_trans/expected_good.tsv"
{
  echo "# selftest"
  printf 'selftest_arm\t%s\n' "$good_line_t"
} > "$exp_good_t"

verdict_b_self_t="$(check_print_record_against_expected selftest_arm "$exp_good_t" "$good_line_t")"
verdict_b_bad_t="$(check_print_record_against_expected selftest_arm "$exp_good_t" "$bad_line_t")"
if [ "$verdict_b_self_t" = "conform" ] && [ "${verdict_b_bad_t#not_conform}" != "$verdict_b_bad_t" ]; then
  ok "自己検査b1(TRANS): 正しい記録は期待値と conform、壊した記録は not_conform"
else
  ng "自己検査b1(TRANS): 正しい記録(${verdict_b_self_t})/壊した記録(${verdict_b_bad_t})の判定がおかしい"
  trans_selftest_rc=1
fi

exp_bad_count_t="$WORK/selftest_trans/expected_bad_count.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next} {$2=$2+1; print}' "$exp_good_t" > "$exp_bad_count_t"
verdict_c_t="$(check_print_record_against_expected selftest_arm "$exp_bad_count_t" "$good_line_t")"
if [ "${verdict_c_t#not_conform}" != "$verdict_c_t" ]; then
  ok "自己検査c(TRANS): 期待値の件数を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査c(TRANS): 件数を壊した期待値が誤って conform になった"
  trans_selftest_rc=1
fi

exp_bad_sha_t="$WORK/selftest_trans/expected_bad_sha.tsv"
awk 'BEGIN{FS=OFS="\t"} /^#/{print;next}
     {sha=$4; last=substr(sha,length(sha),1); $4=substr(sha,1,length(sha)-1) (last=="0"?"f":"0"); print}' \
    "$exp_good_t" > "$exp_bad_sha_t"
verdict_d_t="$(check_print_record_against_expected selftest_arm "$exp_bad_sha_t" "$good_line_t")"
if [ "${verdict_d_t#not_conform}" != "$verdict_d_t" ]; then
  ok "自己検査d(TRANS): 期待値のSHA-256を壊すと正しい記録でも not_conform で検出される"
else
  ng "自己検査d(TRANS): SHA-256を壊した期待値が誤って conform になった"
  trans_selftest_rc=1
fi

if [ "$trans_selftest_rc" -eq 0 ]; then
  ok "検出力の自己検査(TRANS): 全項目OK"
else
  ng "検出力の自己検査(TRANS): 失敗した項目がある"
fi
overall_rc=$(( overall_rc || trans_selftest_rc ))

# -----------------------------------------------------------------------
# 自作main ROM側の照合（公式環境の有無に関わらず常に実行する）。
# -----------------------------------------------------------------------
say "自作main ROM側の照合（公式環境不要。11腕）"

CORE="$(find_l3_core)"
if [ -z "$CORE" ]; then
  echo "エラー: コアが無い。tools/setup_harness.sh を先に実行すること" >&2
  exit 1
fi
if ! ensure_l3_frontend; then
  echo "エラー: フロントエンドのビルドに失敗した" >&2
  exit 1
fi

say "G5: 自作main ROM側の自己検査 (tools/l3_main_selftest.sh)"
if bash "$REPO/tools/l3_main_selftest.sh" >"$WORK/l3_main_selftest.out.txt" 2>&1; then
  ok "G5: tools/l3_main_selftest.sh はrc=0"
else
  ng "G5: tools/l3_main_selftest.sh が失敗した(rc!=0)"
  tail -20 "$WORK/l3_main_selftest.out.txt" | sed 's/^/       /'
  overall_rc=1
fi

SELF_ROMDIR="$WORK/self_rom"
mkdir -p "$SELF_ROMDIR"
if ! python3 "$BUILD_MAIN" "$SELF_ROMDIR" >"$WORK/self_build.txt" 2>&1; then
  echo "エラー: 自作main ROMの組み立てに失敗した" >&2
  cat "$WORK/self_build.txt" >&2
  exit 1
fi

say "G4: 陰性対照（自作ROM、何も打たない走）"
neg_json="$(run_negative_control "$SELF_ROMDIR" "$WORK/self_negctl" 2>"$WORK/self_negctl.err.txt")" || {
  ng "G4: 陰性対照の走行に失敗した"
  cat "$WORK/self_negctl.err.txt" >&2
  overall_rc=1
}
if [ -n "${neg_json:-}" ]; then
  neg_char="$(printf '%s' "$neg_json" | python3 -c 'import json,sys; d=json.load(sys.stdin)["vram_diff"]; print(d["char_change_count"])' 2>/dev/null)"
  neg_attr="$(printf '%s' "$neg_json" | python3 -c 'import json,sys; d=json.load(sys.stdin)["vram_diff"]; print(d["attr_change_count"])' 2>/dev/null)"
  neg_c19="$(printf '%s' "$neg_json" | python3 -c 'import json,sys; d=json.load(sys.stdin)["vram_diff"]; s=d["count_only_summary"]; print(sum(e["char_change_count"] for e in s))' 2>/dev/null)"
  neg_a19="$(printf '%s' "$neg_json" | python3 -c 'import json,sys; d=json.load(sys.stdin)["vram_diff"]; s=d["count_only_summary"]; print(sum(e["attr_change_count"] for e in s))' 2>/dev/null)"
  if [ "${neg_char:-x}" = "0" ] && [ "${neg_attr:-x}" = "0" ] && [ "${neg_c19:-x}" = "0" ] && [ "${neg_a19:-x}" = "0" ]; then
    ok "G4: 自作ROM、何も打たない走で全行の変化が0件"
  else
    ng "G4: 自作ROM、何も打たない走で変化が検出された(文字${neg_char}/属性${neg_attr}/row19文字${neg_c19}/row19属性${neg_a19})"
    overall_rc=1
  fi
fi

conform_count=0
not_conform_count=0
gate_failed_count=0
declare -a SELF_RESULTS

for arm in "${ARM_NAMES[@]}"; do
  arm_params "$arm"
  prefix="$WORK/self_${arm}"
  line1="$(run_arm_once "$SELF_ROMDIR" "$prefix" "${ARM_ARGS[@]}" 2>"$prefix.err.txt")"
  rc1=$?
  if [ "$rc1" -ne 0 ] || [ -z "$line1" ]; then
    ng "[自作] ${arm}: 走行または記録化に失敗した(gate_failed)"
    sed 's/^/       /' "$prefix.err.txt"
    gate_failed_count=$((gate_failed_count + 1))
    SELF_RESULTS+=("${arm}\tgate_failed")
    overall_rc=1
    continue
  fi
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$EXPECTED")"
  if [ -z "$row" ]; then
    ng "[自作] ${arm}: 期待値に行が無い(gate_failed)"
    gate_failed_count=$((gate_failed_count + 1))
    SELF_RESULTS+=("${arm}\tgate_failed")
    overall_rc=1
    continue
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_nonblank="$(printf '%s' "$row" | cut -f3)"
  e_attr="$(printf '%s' "$row" | cut -f4)"
  e_sha="$(printf '%s' "$row" | cut -f5)"
  a_count="$(printf '%s' "$line1" | cut -f1)"
  a_nonblank="$(printf '%s' "$line1" | cut -f2)"
  a_attr="$(printf '%s' "$line1" | cut -f3)"
  a_sha="$(printf '%s' "$line1" | cut -f4)"
  if [ "$a_count" != "$e_count" ] || [ "$a_nonblank" != "$e_nonblank" ] || [ "$a_attr" != "$e_attr" ]; then
    ng "[自作] ${arm}: not_conform(件数不一致: cell ${a_count}/${e_count} nonblank ${a_nonblank}/${e_nonblank} attr_rows ${a_attr}/${e_attr})"
    not_conform_count=$((not_conform_count + 1))
    SELF_RESULTS+=("${arm}\tnot_conform(件数不一致)")
    overall_rc=1
  elif [ "$a_sha" != "$e_sha" ]; then
    ng "[自作] ${arm}: not_conform(件数は一致するがSHA-256が不一致)"
    not_conform_count=$((not_conform_count + 1))
    SELF_RESULTS+=("${arm}\tnot_conform(sha256不一致)")
    overall_rc=1
  else
    ok "[自作] ${arm}: conform(件数${a_count}/${a_nonblank}/${a_attr}・SHA-256一致)"
    conform_count=$((conform_count + 1))
    SELF_RESULTS+=("${arm}\tconform")
  fi
done

say "自作ROM側の集計"
echo "  conform: ${conform_count} / 11"
echo "  not_conform: ${not_conform_count} / 11"
echo "  gate_failed: ${gate_failed_count} / 11"

say "自作main ROM側の照合(PRINT場面。公式環境不要。16腕)"

print_conform_count=0
print_not_conform_count=0
print_gate_failed_count=0

for arm in "${PRINT_ARM_NAMES[@]}"; do
  print_arm_params "$arm"
  prefix="$WORK/self_print_${arm}"
  line1="$(run_print_arm_once "$SELF_ROMDIR" "$prefix" "${PRINT_ARM_ARGS[@]}" 2>"$prefix.err.txt")"
  rc1=$?
  if [ "$rc1" -ne 0 ] || [ -z "$line1" ]; then
    ng "[自作/PRINT] ${arm}: 走行または記録化に失敗した(gate_failed)"
    sed 's/^/       /' "$prefix.err.txt"
    print_gate_failed_count=$((print_gate_failed_count + 1))
    overall_rc=1
    continue
  fi
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$EXPECTED_PRINT")"
  if [ -z "$row" ]; then
    ng "[自作/PRINT] ${arm}: 期待値に行が無い(gate_failed)"
    print_gate_failed_count=$((print_gate_failed_count + 1))
    overall_rc=1
    continue
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_ok="$(printf '%s' "$row" | cut -f3)"
  e_sha="$(printf '%s' "$row" | cut -f4)"
  a_count="$(printf '%s' "$line1" | cut -f1)"
  a_ok="$(printf '%s' "$line1" | cut -f2)"
  a_sha="$(printf '%s' "$line1" | cut -f3)"
  if [ "$a_count" != "$e_count" ] || [ "$a_ok" != "$e_ok" ]; then
    ng "[自作/PRINT] ${arm}: not_conform(件数不一致: cell ${a_count}/${e_count} ok_row ${a_ok}/${e_ok})"
    print_not_conform_count=$((print_not_conform_count + 1))
    overall_rc=1
  elif [ "$a_sha" != "$e_sha" ]; then
    ng "[自作/PRINT] ${arm}: not_conform(件数は一致するがSHA-256が不一致)"
    print_not_conform_count=$((print_not_conform_count + 1))
    overall_rc=1
  else
    ok "[自作/PRINT] ${arm}: conform(cell${a_count}・ok行+${a_ok}・SHA-256一致)"
    print_conform_count=$((print_conform_count + 1))
  fi
done

say "自作ROM側の集計(PRINT場面)"
echo "  conform: ${print_conform_count} / 16"
echo "  not_conform: ${print_not_conform_count} / 16"
echo "  gate_failed: ${print_gate_failed_count} / 16"

# -----------------------------------------------------------------------
# l4-c3 自作main ROM側の照合(FLOAT場面。公式環境不要。25腕)。
#
# 群(FS単精度/FD倍精度)ごとの実装状態をexpected_l4_float.tsvの見出し
# コメントから読み、not_implemented_yetの群は判定外(not_implemented_yet)
# として表示するだけでrcに含めない。SKIPの表示(catブロック)とは別の
# 表示(na、黄色の"--")にして区別する。
# -----------------------------------------------------------------------
say "自作main ROM側の照合(FLOAT場面。公式環境不要。25腕)"

float_conform_count=0
float_not_conform_count=0
float_gate_failed_count=0
float_notimpl_count=0

for arm in "${FLOAT_ARM_NAMES[@]}"; do
  group="$(float_arm_group "$arm")"
  status="$(float_group_status "$group")"
  if [ "$status" = "not_implemented_yet" ]; then
    na "[自作/FLOAT] ${arm}: not_implemented_yet(群${group}は自作側未実装のため判定外)"
    float_notimpl_count=$((float_notimpl_count + 1))
    continue
  fi
  float_arm_params "$arm"
  prefix="$WORK/self_float_${arm}"
  line1="$(run_print_arm_once "$SELF_ROMDIR" "$prefix" "${PRINT_ARM_ARGS[@]}" 2>"$prefix.err.txt")"
  rc1=$?
  if [ "$rc1" -ne 0 ] || [ -z "$line1" ]; then
    ng "[自作/FLOAT] ${arm}: 走行または記録化に失敗した(gate_failed)"
    sed 's/^/       /' "$prefix.err.txt"
    float_gate_failed_count=$((float_gate_failed_count + 1))
    overall_rc=1
    continue
  fi
  ok_rel="$(printf '%s' "$line1" | cut -f2)"
  if [ "$ok_rel" = "NA" ] || { [ "$ok_rel" != "" ] && [ "$ok_rel" -lt 2 ] 2>/dev/null; }; then
    ng "[自作/FLOAT] ${arm}: G8(出力完了の確認)が偽(写しが早すぎた。gate_failed)"
    float_gate_failed_count=$((float_gate_failed_count + 1))
    overall_rc=1
    continue
  fi
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$EXPECTED_FLOAT")"
  if [ -z "$row" ]; then
    ng "[自作/FLOAT] ${arm}: 期待値に行が無い(gate_failed)"
    float_gate_failed_count=$((float_gate_failed_count + 1))
    overall_rc=1
    continue
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_ok="$(printf '%s' "$row" | cut -f3)"
  e_sha="$(printf '%s' "$row" | cut -f4)"
  a_count="$(printf '%s' "$line1" | cut -f1)"
  a_sha="$(printf '%s' "$line1" | cut -f3)"
  if [ "$a_count" != "$e_count" ] || [ "$ok_rel" != "$e_ok" ]; then
    ng "[自作/FLOAT] ${arm}: not_conform(件数不一致: cell ${a_count}/${e_count} ok_row ${ok_rel}/${e_ok})"
    float_not_conform_count=$((float_not_conform_count + 1))
    overall_rc=1
  elif [ "$a_sha" != "$e_sha" ]; then
    ng "[自作/FLOAT] ${arm}: not_conform(件数は一致するがSHA-256が不一致)"
    float_not_conform_count=$((float_not_conform_count + 1))
    overall_rc=1
  else
    ok "[自作/FLOAT] ${arm}: conform(cell${a_count}・ok行+${ok_rel}・SHA-256一致)"
    float_conform_count=$((float_conform_count + 1))
  fi
done

say "自作ROM側の集計(FLOAT場面)"
echo "  conform: ${float_conform_count} / 25"
echo "  not_conform: ${float_not_conform_count} / 25"
echo "  gate_failed: ${float_gate_failed_count} / 25"
echo "  not_implemented_yet: ${float_notimpl_count} / 25 (判定外・rcに含めない)"

# -----------------------------------------------------------------------
# l4-c5 自作main ROM側の照合(PROGRAM場面。公式環境不要。8腕・1群)。
# 群"programs"がnot_implemented_yetの間は判定外(na表示)としてrcに
# 含めない(l4-c3のFS/FDと同じ作法)。
# -----------------------------------------------------------------------
say "自作main ROM側の照合(PROGRAM場面。公式環境不要。8腕)"

program_conform_count=0
program_not_conform_count=0
program_gate_failed_count=0
program_notimpl_count=0

program_status_now="$(program_group_status)"
if [ "$program_status_now" = "not_implemented_yet" ]; then
  for arm in "${PROGRAM_ARM_NAMES[@]}"; do
    na "[自作/PROGRAM] ${arm}: not_implemented_yet(群programsは自作側未実装のため判定外)"
    program_notimpl_count=$((program_notimpl_count + 1))
  done
else
  for arm in "${PROGRAM_ARM_NAMES[@]}"; do
    bas="$(program_arm_bas "$arm")"
    input="$(program_arm_input "$arm")"
    prefix="$WORK/self_program_${arm}"
    line1="$(run_program_arm_once "$SELF_ROMDIR" "$prefix" "$bas" "$input" 2>"$prefix.err.txt")"
    status1="$(printf '%s' "$line1" | cut -f1)"
    g9_1="$(printf '%s' "$line1" | cut -f5)"
    g10_1="$(printf '%s' "$line1" | cut -f6)"
    if [ "$status1" != "ok" ]; then
      ng "[自作/PROGRAM] ${arm}: 出力完了の確認(G8)が偽(走行失敗または${status1}。gate_failed)"
      sed 's/^/       /' "$prefix.err.txt" 2>/dev/null
      program_gate_failed_count=$((program_gate_failed_count + 1))
      overall_rc=1
      continue
    fi
    if [ "$g9_1" != "1" ]; then
      ng "[自作/PROGRAM] ${arm}: G9(打鍵到達確認)が偽(打鍵が抜けていた。gate_failed)"
      program_gate_failed_count=$((program_gate_failed_count + 1))
      overall_rc=1
      continue
    fi
    if [ "$g10_1" != "1" ]; then
      ng "[自作/PROGRAM] ${arm}: G10(画面に収まっていること)が偽(出力が画面に収まらなかった。gate_failed)"
      program_gate_failed_count=$((program_gate_failed_count + 1))
      overall_rc=1
      continue
    fi
    verdict="$(check_program_record_against_expected "$arm" "$EXPECTED_PROGRAMS" "$line1")"
    case "$verdict" in
      conform)
        ok "[自作/PROGRAM] ${arm}: conform(cell$(printf '%s' "$line1" | cut -f2)・ok行+$(printf '%s' "$line1" | cut -f3)・SHA-256一致)"
        program_conform_count=$((program_conform_count + 1))
        ;;
      gate_failed)
        ng "[自作/PROGRAM] ${arm}: 期待値に行が無い(gate_failed)"
        program_gate_failed_count=$((program_gate_failed_count + 1))
        overall_rc=1
        ;;
      *)
        ng "[自作/PROGRAM] ${arm}: ${verdict}"
        program_not_conform_count=$((program_not_conform_count + 1))
        overall_rc=1
        ;;
    esac
  done
fi

say "自作ROM側の集計(PROGRAM場面)"
echo "  conform: ${program_conform_count} / 8"
echo "  not_conform: ${program_not_conform_count} / 8"
echo "  gate_failed: ${program_gate_failed_count} / 8"
echo "  not_implemented_yet: ${program_notimpl_count} / 8 (判定外・rcに含めない)"

# -----------------------------------------------------------------------
# l4-c7 自作main ROM側の照合(ARITH場面。公式環境不要。40腕・1群)。
# 群"arith"がnot_implemented_yetの間は判定外(na表示)としてrcに含めない
# (l4-c3のFS/FD、l4-c5のprogramsと同じ作法)。
# -----------------------------------------------------------------------
say "自作main ROM側の照合(ARITH場面。公式環境不要。40腕)"

arith_conform_count=0
arith_not_conform_count=0
arith_gate_failed_count=0
arith_notimpl_count=0

arith_status_now="$(arith_group_status)"
if [ "$arith_status_now" = "not_implemented_yet" ]; then
  for arm in "${ARITH_ARM_NAMES[@]}"; do
    na "[自作/ARITH] ${arm}: not_implemented_yet(群arithは自作側未実装のため判定外)"
    arith_notimpl_count=$((arith_notimpl_count + 1))
  done
else
  for arm in "${ARITH_ARM_NAMES[@]}"; do
    arith_arm_params "$arm"
    prefix="$WORK/self_arith_${arm}"
    line1="$(run_print_arm_once "$SELF_ROMDIR" "$prefix" "${PRINT_ARM_ARGS[@]}" 2>"$prefix.err.txt")"
    rc1=$?
    if [ "$rc1" -ne 0 ] || [ -z "$line1" ]; then
      ng "[自作/ARITH] ${arm}: 走行または記録化に失敗した(gate_failed)"
      sed 's/^/       /' "$prefix.err.txt"
      arith_gate_failed_count=$((arith_gate_failed_count + 1))
      overall_rc=1
      continue
    fi
    ok_rel="$(printf '%s' "$line1" | cut -f2)"
    if [ "$ok_rel" = "NA" ] || { [ "$ok_rel" != "" ] && [ "$ok_rel" -lt 2 ] 2>/dev/null; }; then
      ng "[自作/ARITH] ${arm}: G8(出力完了の確認)が偽(写しが早すぎた。gate_failed)"
      arith_gate_failed_count=$((arith_gate_failed_count + 1))
      overall_rc=1
      continue
    fi
    verdict="$(check_print_record_against_expected "$arm" "$EXPECTED_ARITH" "$line1")"
    case "$verdict" in
      conform)
        ok "[自作/ARITH] ${arm}: conform(cell$(printf '%s' "$line1" | cut -f1)・ok行+${ok_rel}・SHA-256一致)"
        arith_conform_count=$((arith_conform_count + 1))
        ;;
      gate_failed)
        ng "[自作/ARITH] ${arm}: 期待値に行が無い(gate_failed)"
        arith_gate_failed_count=$((arith_gate_failed_count + 1))
        overall_rc=1
        ;;
      *)
        ng "[自作/ARITH] ${arm}: ${verdict}"
        arith_not_conform_count=$((arith_not_conform_count + 1))
        overall_rc=1
        ;;
    esac
  done
fi

say "自作ROM側の集計(ARITH場面)"
echo "  conform: ${arith_conform_count} / 40"
echo "  not_conform: ${arith_not_conform_count} / 40"
echo "  gate_failed: ${arith_gate_failed_count} / 40"
echo "  not_implemented_yet: ${arith_notimpl_count} / 40 (判定外・rcに含めない)"

# -----------------------------------------------------------------------
# 自己検査e: 群の印をnot_implemented_yet→implementedへ書き換えると、
# (a)not_implemented_yetの間は判定がスキップされること、
# (b)implementedにすると実際に照合が走り、現在の自作ROM(浮動小数点PRINT
# 未実装)ではNG(not_conform、またはgate_failed)になること
# ——つまり判定外の扱いが「本物の判定を隠していない」ことを確認する。
# 実データ(expected_l4_float.tsvの本番行)には依存せず、明らかに不一致に
# なる合成の期待値行を使う(自作ROMが偶然一致することを避けるため)。
# -----------------------------------------------------------------------
say "自己検査e(FLOAT): 群の印をimplementedにすると判定が実際に走りNGになるか"

selftest_e_rc=0
EG_ARM="FS1"
EG_GROUP="$(float_arm_group "$EG_ARM")"
EG_DIR="$WORK/selftest_group"
mkdir -p "$EG_DIR"

EG_NOTIMPL="$EG_DIR/expected_notimpl.tsv"
{
  echo "# selftest(自己検査e専用、実データではない)"
  echo "# group ${EG_GROUP} selfmade=not_implemented_yet"
  # わざと現実にありえない値にする(自作ROMが偶然一致しないように)
  printf '%s\t999\t2\t0000000000000000000000000000000000000000000000000000000000000000\n' "$EG_ARM"
} > "$EG_NOTIMPL"

EG_IMPL="$EG_DIR/expected_impl.tsv"
sed 's/selfmade=not_implemented_yet/selfmade=implemented/' "$EG_NOTIMPL" > "$EG_IMPL"

# float_group_status は $EXPECTED_FLOAT をグローバル変数として参照する
# ため、コマンド置換の中だけ一時的に差し替えて呼ぶ(本体スクリプトを
# 再sourceすると全体が再実行されてしまうので避ける)。
eg_status_before="$(EXPECTED_FLOAT="$EG_NOTIMPL" float_group_status "$EG_GROUP")"
if [ "$eg_status_before" = "not_implemented_yet" ]; then
  ok "自己検査e-1: 書き換え前は not_implemented_yet と読める"
else
  ng "自己検査e-1: 書き換え前の状態読み取りが期待どおりでない(${eg_status_before:-空})"
  selftest_e_rc=1
fi

eg_status_after="$(EXPECTED_FLOAT="$EG_IMPL" float_group_status "$EG_GROUP")"
if [ "$eg_status_after" = "implemented" ]; then
  ok "自己検査e-2: 書き換え後は implemented と読める"
else
  ng "自己検査e-2: 書き換え後の状態読み取りが期待どおりでない(${eg_status_after:-空})"
  selftest_e_rc=1
fi

# implemented状態で実際に自作ROMを走らせ、合成の(ありえない)期待値と
# 照合するとNG(not_conform/gate_failed)になることを確認する。
float_arm_params "$EG_ARM"
eg_prefix="$EG_DIR/self_${EG_ARM}"
eg_line="$(run_print_arm_once "$SELF_ROMDIR" "$eg_prefix" "${PRINT_ARM_ARGS[@]}" 2>"$eg_prefix.err.txt")"
eg_rc=$?
if [ "$eg_rc" -ne 0 ] || [ -z "$eg_line" ]; then
  ok "自己検査e-3: implemented時に実際に走行し、現在の自作ROMでは失敗(gate_failed相当)した=NGを検出できた"
else
  eg_row="$(awk -F'\t' -v a="$EG_ARM" '$1==a{print;exit}' "$EG_IMPL")"
  eg_e_count="$(printf '%s' "$eg_row" | cut -f2)"
  eg_e_ok="$(printf '%s' "$eg_row" | cut -f3)"
  eg_e_sha="$(printf '%s' "$eg_row" | cut -f4)"
  eg_a_count="$(printf '%s' "$eg_line" | cut -f1)"
  eg_a_ok="$(printf '%s' "$eg_line" | cut -f2)"
  eg_a_sha="$(printf '%s' "$eg_line" | cut -f3)"
  if [ "$eg_a_count" != "$eg_e_count" ] || [ "$eg_a_ok" != "$eg_e_ok" ] || [ "$eg_a_sha" != "$eg_e_sha" ]; then
    ok "自己検査e-3: implementedにすると実際に照合が走り、現在の自作ROMではNG(not_conform)になった(判定外が本物の判定を隠していない)"
  else
    ng "自己検査e-3: 合成の(ありえない)期待値と偶然一致してしまった(自己検査のフィクスチャを見直すこと)"
    selftest_e_rc=1
  fi
fi

if [ "$selftest_e_rc" -eq 0 ]; then
  ok "自己検査e(FLOAT): 全項目OK"
else
  ng "自己検査e(FLOAT): 失敗した項目がある"
fi
overall_rc=$(( overall_rc || selftest_e_rc ))

# -----------------------------------------------------------------------
# 自己検査e(PROGRAM): 群"programs"の印をnot_implemented_yet→implemented
# へ書き換えると、(a)not_implemented_yetの間は判定がスキップされること、
# (b)implementedにすると実際に照合が走り、現在の自作ROM(プログラム
# モード未実装)ではNG(not_conform/gate_failed)になること——つまり
# 判定外の扱いが「本物の判定を隠していない」ことを確認する。FLOATの
# 自己検査eと同じ作法。実データ(expected_l4_programs.tsvの本番行)には
# 依存せず、明らかに不一致になる合成の期待値行を使う。
# -----------------------------------------------------------------------
say "自己検査e(PROGRAM): 群の印をimplementedにすると判定が実際に走りNGになるか"

program_selftest_e_rc=0
PEG_ARM="P1"
PEG_DIR="$WORK/selftest_program_group"
mkdir -p "$PEG_DIR"

PEG_NOTIMPL="$PEG_DIR/expected_notimpl.tsv"
{
  echo "# selftest(自己検査e専用、実データではない)"
  echo "# group programs selfmade=not_implemented_yet"
  printf '%s\t999\t2\t0000000000000000000000000000000000000000000000000000000000000000\n' "$PEG_ARM"
} > "$PEG_NOTIMPL"

PEG_IMPL="$PEG_DIR/expected_impl.tsv"
sed 's/selfmade=not_implemented_yet/selfmade=implemented/' "$PEG_NOTIMPL" > "$PEG_IMPL"

peg_status_before="$(EXPECTED_PROGRAMS="$PEG_NOTIMPL" program_group_status)"
if [ "$peg_status_before" = "not_implemented_yet" ]; then
  ok "自己検査e-1(PROGRAM): 書き換え前は not_implemented_yet と読める"
else
  ng "自己検査e-1(PROGRAM): 書き換え前の状態読み取りが期待どおりでない(${peg_status_before:-空})"
  program_selftest_e_rc=1
fi

peg_status_after="$(EXPECTED_PROGRAMS="$PEG_IMPL" program_group_status)"
if [ "$peg_status_after" = "implemented" ]; then
  ok "自己検査e-2(PROGRAM): 書き換え後は implemented と読める"
else
  ng "自己検査e-2(PROGRAM): 書き換え後の状態読み取りが期待どおりでない(${peg_status_after:-空})"
  program_selftest_e_rc=1
fi

peg_bas="$(program_arm_bas "$PEG_ARM")"
peg_input="$(program_arm_input "$PEG_ARM")"
peg_prefix="$PEG_DIR/self_${PEG_ARM}"
peg_line="$(run_program_arm_once "$SELF_ROMDIR" "$peg_prefix" "$peg_bas" "$peg_input" 2>"$peg_prefix.err.txt")"
peg_verdict="$(check_program_record_against_expected "$PEG_ARM" "$PEG_IMPL" "$peg_line")"
if [ "$peg_verdict" = "conform" ]; then
  ng "自己検査e-3(PROGRAM): 合成の(ありえない)期待値と偶然一致してしまった(自己検査のフィクスチャを見直すこと)"
  program_selftest_e_rc=1
else
  ok "自己検査e-3(PROGRAM): implementedにすると実際に照合が走り、現在の自作ROMではNG(${peg_verdict})になった(判定外が本物の判定を隠していない)"
fi

if [ "$program_selftest_e_rc" -eq 0 ]; then
  ok "自己検査e(PROGRAM): 全項目OK"
else
  ng "自己検査e(PROGRAM): 失敗した項目がある"
fi
overall_rc=$(( overall_rc || program_selftest_e_rc ))

# -----------------------------------------------------------------------
# 自己検査e(ARITH): 群"arith"の印をnot_implemented_yet→implementedへ
# 書き換えると、(a)not_implemented_yetの間は判定がスキップされること、
# (b)implementedにすると実際に照合が走り、現在の自作ROM(本節時点では
# 実装前)ではNG(not_conform/gate_failed)になること——つまり判定外の
# 扱いが「本物の判定を隠していない」ことを確認する。FLOAT/PROGRAMの
# 自己検査eと同じ作法。実データ(expected_l4_arith.tsvの本番行)には
# 依存せず、明らかに不一致になる合成の期待値行を使う。
# -----------------------------------------------------------------------
say "自己検査e(ARITH): 群の印をimplementedにすると判定が実際に走りNGになるか"

arith_selftest_e_rc=0
AEG_ARM="K1"
AEG_DIR="$WORK/selftest_arith_group"
mkdir -p "$AEG_DIR"

AEG_NOTIMPL="$AEG_DIR/expected_notimpl.tsv"
{
  echo "# selftest(自己検査e専用、実データではない)"
  echo "# group arith selfmade=not_implemented_yet"
  printf '%s\t999\t2\t0000000000000000000000000000000000000000000000000000000000000000\n' "$AEG_ARM"
} > "$AEG_NOTIMPL"

AEG_IMPL="$AEG_DIR/expected_impl.tsv"
sed 's/selfmade=not_implemented_yet/selfmade=implemented/' "$AEG_NOTIMPL" > "$AEG_IMPL"

aeg_status_before="$(EXPECTED_ARITH="$AEG_NOTIMPL" arith_group_status)"
if [ "$aeg_status_before" = "not_implemented_yet" ]; then
  ok "自己検査e-1(ARITH): 書き換え前は not_implemented_yet と読める"
else
  ng "自己検査e-1(ARITH): 書き換え前の状態読み取りが期待どおりでない(${aeg_status_before:-空})"
  arith_selftest_e_rc=1
fi

aeg_status_after="$(EXPECTED_ARITH="$AEG_IMPL" arith_group_status)"
if [ "$aeg_status_after" = "implemented" ]; then
  ok "自己検査e-2(ARITH): 書き換え後は implemented と読める"
else
  ng "自己検査e-2(ARITH): 書き換え後の状態読み取りが期待どおりでない(${aeg_status_after:-空})"
  arith_selftest_e_rc=1
fi

arith_arm_params "$AEG_ARM"
aeg_prefix="$AEG_DIR/self_${AEG_ARM}"
aeg_line="$(run_print_arm_once "$SELF_ROMDIR" "$aeg_prefix" "${PRINT_ARM_ARGS[@]}" 2>"$aeg_prefix.err.txt")"
aeg_verdict="$(check_print_record_against_expected "$AEG_ARM" "$AEG_IMPL" "$aeg_line")"
if [ "$aeg_verdict" = "conform" ]; then
  ng "自己検査e-3(ARITH): 合成の(ありえない)期待値と偶然一致してしまった(自己検査のフィクスチャを見直すこと)"
  arith_selftest_e_rc=1
else
  ok "自己検査e-3(ARITH): implementedにすると実際に照合が走り、現在の自作ROMではNG(${aeg_verdict})になった(判定外が本物の判定を隠していない)"
fi

if [ "$arith_selftest_e_rc" -eq 0 ]; then
  ok "自己検査e(ARITH): 全項目OK"
else
  ng "自己検査e(ARITH): 失敗した項目がある"
fi
overall_rc=$(( overall_rc || arith_selftest_e_rc ))

# -----------------------------------------------------------------------
# l4-c8 自作main ROM側の照合(TRANS場面。公式環境不要。59腕・7群)。
# 群(sin/cos/tan/atn/exp/log/sqr)ごとにexpected_l4_trans.tsvの見出し
# コメントから実装状態を読み、not_implemented_yetの群は判定外(na表示)
# としてrcに含めない(l4-c3のFS/FDと同じ作法)。SQR群だけは`a3fb09e`で
# 実装済みのためselfmade=implementedから始まり、実際に照合が走る。
# -----------------------------------------------------------------------
say "自作main ROM側の照合(TRANS場面。公式環境不要。59腕)"

trans_conform_count=0
trans_not_conform_count=0
trans_gate_failed_count=0
trans_notimpl_count=0

for arm in "${TRANS_ARM_NAMES[@]}"; do
  group="$(trans_arm_group "$arm")"
  status="$(trans_group_status "$group")"
  if [ "$status" = "not_implemented_yet" ]; then
    na "[自作/TRANS] ${arm}: not_implemented_yet(群${group}は自作側未実装のため判定外)"
    trans_notimpl_count=$((trans_notimpl_count + 1))
    continue
  fi
  trans_arm_params "$arm"
  prefix="$WORK/self_trans_${arm}"
  line1="$(run_print_arm_once "$SELF_ROMDIR" "$prefix" "${PRINT_ARM_ARGS[@]}" 2>"$prefix.err.txt")"
  rc1=$?
  if [ "$rc1" -ne 0 ] || [ -z "$line1" ]; then
    ng "[自作/TRANS] ${arm}: 走行または記録化に失敗した(gate_failed)"
    sed 's/^/       /' "$prefix.err.txt"
    trans_gate_failed_count=$((trans_gate_failed_count + 1))
    overall_rc=1
    continue
  fi
  ok_rel="$(printf '%s' "$line1" | cut -f2)"
  if [ "$ok_rel" = "NA" ] || { [ "$ok_rel" != "" ] && [ "$ok_rel" -lt 2 ] 2>/dev/null; }; then
    ng "[自作/TRANS] ${arm}: G8(出力完了の確認)が偽(写しが早すぎた。gate_failed)"
    trans_gate_failed_count=$((trans_gate_failed_count + 1))
    overall_rc=1
    continue
  fi
  verdict="$(check_print_record_against_expected "$arm" "$EXPECTED_TRANS" "$line1")"
  case "$verdict" in
    conform)
      ok "[自作/TRANS] ${arm}: conform(cell$(printf '%s' "$line1" | cut -f1)・ok行+${ok_rel}・SHA-256一致)"
      trans_conform_count=$((trans_conform_count + 1))
      ;;
    gate_failed)
      ng "[自作/TRANS] ${arm}: 期待値に行が無い(gate_failed)"
      trans_gate_failed_count=$((trans_gate_failed_count + 1))
      overall_rc=1
      ;;
    *)
      ng "[自作/TRANS] ${arm}: ${verdict}"
      trans_not_conform_count=$((trans_not_conform_count + 1))
      overall_rc=1
      ;;
  esac
done

say "自作ROM側の集計(TRANS場面)"
echo "  conform: ${trans_conform_count} / 59"
echo "  not_conform: ${trans_not_conform_count} / 59"
echo "  gate_failed: ${trans_gate_failed_count} / 59"
echo "  not_implemented_yet: ${trans_notimpl_count} / 59 (判定外・rcに含めない)"

# -----------------------------------------------------------------------
# 自己検査e(TRANS): 群(ここでは"sin")の印をnot_implemented_yet→
# implementedへ書き換えると、(a)not_implemented_yetの間は判定がスキップ
# されること、(b)implementedにすると実際に照合が走り、現在の自作ROM
# (SIN未実装)ではNGになること——を確認する。FLOAT/ARITHの自己検査eと
# 同じ作法。実データ(expected_l4_trans.tsvの本番行)には依存せず、明らか
# に不一致になる合成の期待値行を使う。
# -----------------------------------------------------------------------
say "自己検査e(TRANS): 群の印をimplementedにすると判定が実際に走りNGになるか"

trans_selftest_e_rc=0
TEG_ARM="SIN1"
TEG_GROUP="$(trans_arm_group "$TEG_ARM")"
TEG_DIR="$WORK/selftest_trans_group"
mkdir -p "$TEG_DIR"

TEG_NOTIMPL="$TEG_DIR/expected_notimpl.tsv"
{
  echo "# selftest(自己検査e専用、実データではない)"
  echo "# group ${TEG_GROUP} selfmade=not_implemented_yet"
  printf '%s\t999\t2\t0000000000000000000000000000000000000000000000000000000000000000\n' "$TEG_ARM"
} > "$TEG_NOTIMPL"

TEG_IMPL="$TEG_DIR/expected_impl.tsv"
sed 's/selfmade=not_implemented_yet/selfmade=implemented/' "$TEG_NOTIMPL" > "$TEG_IMPL"

teg_status_before="$(EXPECTED_TRANS="$TEG_NOTIMPL" trans_group_status "$TEG_GROUP")"
if [ "$teg_status_before" = "not_implemented_yet" ]; then
  ok "自己検査e-1(TRANS): 書き換え前は not_implemented_yet と読める"
else
  ng "自己検査e-1(TRANS): 書き換え前の状態読み取りが期待どおりでない(${teg_status_before:-空})"
  trans_selftest_e_rc=1
fi

teg_status_after="$(EXPECTED_TRANS="$TEG_IMPL" trans_group_status "$TEG_GROUP")"
if [ "$teg_status_after" = "implemented" ]; then
  ok "自己検査e-2(TRANS): 書き換え後は implemented と読める"
else
  ng "自己検査e-2(TRANS): 書き換え後の状態読み取りが期待どおりでない(${teg_status_after:-空})"
  trans_selftest_e_rc=1
fi

trans_arm_params "$TEG_ARM"
teg_prefix="$TEG_DIR/self_${TEG_ARM}"
teg_line="$(run_print_arm_once "$SELF_ROMDIR" "$teg_prefix" "${PRINT_ARM_ARGS[@]}" 2>"$teg_prefix.err.txt")"
teg_verdict="$(check_print_record_against_expected "$TEG_ARM" "$TEG_IMPL" "$teg_line")"
if [ "$teg_verdict" = "conform" ]; then
  ng "自己検査e-3(TRANS): 合成の(ありえない)期待値と偶然一致してしまった(自己検査のフィクスチャを見直すこと)"
  trans_selftest_e_rc=1
else
  ok "自己検査e-3(TRANS): implementedにすると実際に照合が走り、現在の自作ROMではNG(${teg_verdict})になった(判定外が本物の判定を隠していない)"
fi

if [ "$trans_selftest_e_rc" -eq 0 ]; then
  ok "自己検査e(TRANS): 全項目OK"
else
  ng "自己検査e(TRANS): 失敗した項目がある"
fi
overall_rc=$(( overall_rc || trans_selftest_e_rc ))

# -----------------------------------------------------------------------
# 公式ROM側（環境変数が無ければSKIP）。
# -----------------------------------------------------------------------
say "公式ROM側の再導出（公式環境が必要）"

if [ -z "${PC88_REF_ROM_DIR:-}" ]; then
  cat <<'EOF'
  SKIP: 公式ROMの環境変数(PC88_REF_ROM_DIR)が未設定。

  公式側の再導出（期待値の再現性確認）には以下が要る:
    PC88_REF_ROM_DIR   公式ROM(N88.ROM等)の置き場

  自作ROM側の照合は上で完了済み(公式環境の有無と無関係)。
EOF
  echo
  if [ "$overall_rc" -eq 0 ]; then
    echo "conform_l4: 自作ROM側の照合OK・公式側はSKIP（公式環境未設定）"
  else
    echo "conform_l4: 自作ROM側の照合で不一致あり（公式側はSKIP）"
  fi
  exit "$overall_rc"
fi

OFFICIAL_ROMDIR="$WORK/official_rom"
mkdir -p "$OFFICIAL_ROMDIR"
copied=0
for f in "$PC88_REF_ROM_DIR"/*.ROM; do
  [ -f "$f" ] || continue
  cp -p "$f" "$OFFICIAL_ROMDIR/" || { echo "エラー: 公式ROMのコピーに失敗した" >&2; exit 1; }
  copied=1
done
if [ "$copied" -ne 1 ]; then
  echo "エラー: 公式ROMディレクトリに *.ROM が無い: $PC88_REF_ROM_DIR" >&2
  exit 1
fi

say "G4: 陰性対照（公式ROM、何も打たない走）"
neg_json_o="$(run_negative_control "$OFFICIAL_ROMDIR" "$WORK/official_negctl" 2>"$WORK/official_negctl.err.txt")" || {
  ng "G4: 公式側陰性対照の走行に失敗した"
  cat "$WORK/official_negctl.err.txt" >&2
  overall_rc=1
}
if [ -n "${neg_json_o:-}" ]; then
  o_char="$(printf '%s' "$neg_json_o" | python3 -c 'import json,sys; d=json.load(sys.stdin)["vram_diff"]; print(d["char_change_count"])' 2>/dev/null)"
  o_attr="$(printf '%s' "$neg_json_o" | python3 -c 'import json,sys; d=json.load(sys.stdin)["vram_diff"]; print(d["attr_change_count"])' 2>/dev/null)"
  o_c19="$(printf '%s' "$neg_json_o" | python3 -c 'import json,sys; d=json.load(sys.stdin)["vram_diff"]; s=d["count_only_summary"]; print(sum(e["char_change_count"] for e in s))' 2>/dev/null)"
  o_a19="$(printf '%s' "$neg_json_o" | python3 -c 'import json,sys; d=json.load(sys.stdin)["vram_diff"]; s=d["count_only_summary"]; print(sum(e["attr_change_count"] for e in s))' 2>/dev/null)"
  if [ "${o_char:-x}" = "0" ] && [ "${o_attr:-x}" = "0" ] && [ "${o_c19:-x}" = "0" ] && [ "${o_a19:-x}" = "0" ]; then
    ok "G4: 公式ROM、何も打たない走で全行の変化が0件"
  else
    ng "G4: 公式ROM、何も打たない走で変化が検出された(文字${o_char}/属性${o_attr}/row19文字${o_c19}/row19属性${o_a19})"
    overall_rc=1
  fi
fi

official_conform=0
official_not_conform=0
official_gate_failed=0

for arm in "${ARM_NAMES[@]}"; do
  arm_params "$arm"
  prefix1="$WORK/official_${arm}_run1"
  prefix2="$WORK/official_${arm}_run2"
  line1="$(run_arm_once "$OFFICIAL_ROMDIR" "$prefix1" "${ARM_ARGS[@]}" 2>"$prefix1.err.txt")"
  rc1=$?
  arm_params "$arm"
  line2="$(run_arm_once "$OFFICIAL_ROMDIR" "$prefix2" "${ARM_ARGS[@]}" 2>"$prefix2.err.txt")"
  rc2=$?
  if [ "$rc1" -ne 0 ] || [ "$rc2" -ne 0 ] || [ -z "$line1" ] || [ -z "$line2" ]; then
    ng "[公式] ${arm}: 走行または記録化に失敗した(gate_failed)"
    sed 's/^/       /' "$prefix1.err.txt" "$prefix2.err.txt" 2>/dev/null
    official_gate_failed=$((official_gate_failed + 1))
    overall_rc=1
    continue
  fi
  if [ "$line1" != "$line2" ]; then
    ng "[公式] ${arm}: G3決定論性が破れた(2走の記録が不一致。gate_failed)"
    official_gate_failed=$((official_gate_failed + 1))
    overall_rc=1
    continue
  fi
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$EXPECTED")"
  if [ -z "$row" ]; then
    ng "[公式] ${arm}: 期待値に行が無い(gate_failed)"
    official_gate_failed=$((official_gate_failed + 1))
    overall_rc=1
    continue
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_nonblank="$(printf '%s' "$row" | cut -f3)"
  e_attr="$(printf '%s' "$row" | cut -f4)"
  e_sha="$(printf '%s' "$row" | cut -f5)"
  a_count="$(printf '%s' "$line1" | cut -f1)"
  a_nonblank="$(printf '%s' "$line1" | cut -f2)"
  a_attr="$(printf '%s' "$line1" | cut -f3)"
  a_sha="$(printf '%s' "$line1" | cut -f4)"
  if [ "$a_count" != "$e_count" ] || [ "$a_nonblank" != "$e_nonblank" ] || [ "$a_attr" != "$e_attr" ] || [ "$a_sha" != "$e_sha" ]; then
    ng "[公式] ${arm}: not_conform（再導出した記録が期待値と不一致）"
    official_not_conform=$((official_not_conform + 1))
    overall_rc=1
  else
    ok "[公式] ${arm}: conform（2走一致・期待値とも一致）"
    official_conform=$((official_conform + 1))
  fi
done

say "公式ROM側の集計"
echo "  conform: ${official_conform} / 11"
echo "  not_conform: ${official_not_conform} / 11"
echo "  gate_failed: ${official_gate_failed} / 11"

say "公式ROM側の再導出(PRINT場面。16腕)"

official_print_conform=0
official_print_not_conform=0
official_print_gate_failed=0

for arm in "${PRINT_ARM_NAMES[@]}"; do
  print_arm_params "$arm"
  prefix1="$WORK/official_print_${arm}_run1"
  prefix2="$WORK/official_print_${arm}_run2"
  line1="$(run_print_arm_once "$OFFICIAL_ROMDIR" "$prefix1" "${PRINT_ARM_ARGS[@]}" 2>"$prefix1.err.txt")"
  rc1=$?
  print_arm_params "$arm"
  line2="$(run_print_arm_once "$OFFICIAL_ROMDIR" "$prefix2" "${PRINT_ARM_ARGS[@]}" 2>"$prefix2.err.txt")"
  rc2=$?
  if [ "$rc1" -ne 0 ] || [ "$rc2" -ne 0 ] || [ -z "$line1" ] || [ -z "$line2" ]; then
    ng "[公式/PRINT] ${arm}: 走行または記録化に失敗した(gate_failed)"
    sed 's/^/       /' "$prefix1.err.txt" "$prefix2.err.txt" 2>/dev/null
    official_print_gate_failed=$((official_print_gate_failed + 1))
    overall_rc=1
    continue
  fi
  if [ "$line1" != "$line2" ]; then
    ng "[公式/PRINT] ${arm}: G3決定論性が破れた(2走の記録が不一致。gate_failed)"
    official_print_gate_failed=$((official_print_gate_failed + 1))
    overall_rc=1
    continue
  fi
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$EXPECTED_PRINT")"
  if [ -z "$row" ]; then
    ng "[公式/PRINT] ${arm}: 期待値に行が無い(gate_failed)"
    official_print_gate_failed=$((official_print_gate_failed + 1))
    overall_rc=1
    continue
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_ok="$(printf '%s' "$row" | cut -f3)"
  e_sha="$(printf '%s' "$row" | cut -f4)"
  a_count="$(printf '%s' "$line1" | cut -f1)"
  a_ok="$(printf '%s' "$line1" | cut -f2)"
  a_sha="$(printf '%s' "$line1" | cut -f3)"
  if [ "$a_count" != "$e_count" ] || [ "$a_ok" != "$e_ok" ] || [ "$a_sha" != "$e_sha" ]; then
    ng "[公式/PRINT] ${arm}: not_conform（再導出した記録が期待値と不一致）"
    official_print_not_conform=$((official_print_not_conform + 1))
    overall_rc=1
  else
    ok "[公式/PRINT] ${arm}: conform（2走一致・期待値とも一致）"
    official_print_conform=$((official_print_conform + 1))
  fi
done

say "公式ROM側の集計(PRINT場面)"
echo "  conform: ${official_print_conform} / 16"
echo "  not_conform: ${official_print_not_conform} / 16"
echo "  gate_failed: ${official_print_gate_failed} / 16"

say "公式ROM側の再導出(FLOAT場面。25腕)"

official_float_conform=0
official_float_not_conform=0
official_float_gate_failed=0

for arm in "${FLOAT_ARM_NAMES[@]}"; do
  float_arm_params "$arm"
  prefix1="$WORK/official_float_${arm}_run1"
  prefix2="$WORK/official_float_${arm}_run2"
  line1="$(run_print_arm_once "$OFFICIAL_ROMDIR" "$prefix1" "${PRINT_ARM_ARGS[@]}" 2>"$prefix1.err.txt")"
  rc1=$?
  float_arm_params "$arm"
  line2="$(run_print_arm_once "$OFFICIAL_ROMDIR" "$prefix2" "${PRINT_ARM_ARGS[@]}" 2>"$prefix2.err.txt")"
  rc2=$?
  if [ "$rc1" -ne 0 ] || [ "$rc2" -ne 0 ] || [ -z "$line1" ] || [ -z "$line2" ]; then
    ng "[公式/FLOAT] ${arm}: 走行または記録化に失敗した(gate_failed)"
    sed 's/^/       /' "$prefix1.err.txt" "$prefix2.err.txt" 2>/dev/null
    official_float_gate_failed=$((official_float_gate_failed + 1))
    overall_rc=1
    continue
  fi
  if [ "$line1" != "$line2" ]; then
    ng "[公式/FLOAT] ${arm}: G3決定論性が破れた(2走の記録が不一致。gate_failed)"
    official_float_gate_failed=$((official_float_gate_failed + 1))
    overall_rc=1
    continue
  fi
  ok_rel="$(printf '%s' "$line1" | cut -f2)"
  if [ "$ok_rel" = "NA" ] || { [ "$ok_rel" != "" ] && [ "$ok_rel" -lt 2 ] 2>/dev/null; }; then
    ng "[公式/FLOAT] ${arm}: G8(出力完了の確認)が偽(写しが早すぎた。gate_failed)"
    official_float_gate_failed=$((official_float_gate_failed + 1))
    overall_rc=1
    continue
  fi
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$EXPECTED_FLOAT")"
  if [ -z "$row" ]; then
    ng "[公式/FLOAT] ${arm}: 期待値に行が無い(gate_failed)"
    official_float_gate_failed=$((official_float_gate_failed + 1))
    overall_rc=1
    continue
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_ok="$(printf '%s' "$row" | cut -f3)"
  e_sha="$(printf '%s' "$row" | cut -f4)"
  a_count="$(printf '%s' "$line1" | cut -f1)"
  a_sha="$(printf '%s' "$line1" | cut -f3)"
  if [ "$a_count" != "$e_count" ] || [ "$ok_rel" != "$e_ok" ] || [ "$a_sha" != "$e_sha" ]; then
    ng "[公式/FLOAT] ${arm}: not_conform（再導出した記録が期待値と不一致）"
    official_float_not_conform=$((official_float_not_conform + 1))
    overall_rc=1
  else
    ok "[公式/FLOAT] ${arm}: conform（2走一致・期待値とも一致）"
    official_float_conform=$((official_float_conform + 1))
  fi
done

say "公式ROM側の集計(FLOAT場面)"
echo "  conform: ${official_float_conform} / 25"
echo "  not_conform: ${official_float_not_conform} / 25"
echo "  gate_failed: ${official_float_gate_failed} / 25"

say "公式ROM側の再導出(PROGRAM場面。8腕)"

official_program_conform=0
official_program_not_conform=0
official_program_gate_failed=0

for arm in "${PROGRAM_ARM_NAMES[@]}"; do
  bas="$(program_arm_bas "$arm")"
  input="$(program_arm_input "$arm")"
  prefix1="$WORK/official_program_${arm}_run1"
  prefix2="$WORK/official_program_${arm}_run2"
  line1="$(run_program_arm_once "$OFFICIAL_ROMDIR" "$prefix1" "$bas" "$input" 2>"$prefix1.err.txt")"
  line2="$(run_program_arm_once "$OFFICIAL_ROMDIR" "$prefix2" "$bas" "$input" 2>"$prefix2.err.txt")"
  status1="$(printf '%s' "$line1" | cut -f1)"
  status2="$(printf '%s' "$line2" | cut -f1)"
  g9_1="$(printf '%s' "$line1" | cut -f5)"
  g9_2="$(printf '%s' "$line2" | cut -f5)"
  g10_1="$(printf '%s' "$line1" | cut -f6)"
  g10_2="$(printf '%s' "$line2" | cut -f6)"
  if [ "$status1" != "ok" ] || [ "$status2" != "ok" ]; then
    ng "[公式/PROGRAM] ${arm}: 出力完了の確認(G8)が偽(走行失敗または${status1}/${status2}。gate_failed)"
    sed 's/^/       /' "$prefix1.err.txt" "$prefix2.err.txt" 2>/dev/null
    official_program_gate_failed=$((official_program_gate_failed + 1))
    overall_rc=1
    continue
  fi
  if [ "$g9_1" != "1" ] || [ "$g9_2" != "1" ]; then
    ng "[公式/PROGRAM] ${arm}: G9(打鍵到達確認)が偽(打鍵が抜けていた。gate_failed)"
    official_program_gate_failed=$((official_program_gate_failed + 1))
    overall_rc=1
    continue
  fi
  if [ "$g10_1" != "1" ] || [ "$g10_2" != "1" ]; then
    ng "[公式/PROGRAM] ${arm}: G10(画面に収まっていること)が偽(出力が画面に収まらなかった。gate_failed)"
    official_program_gate_failed=$((official_program_gate_failed + 1))
    overall_rc=1
    continue
  fi
  if [ "$line1" != "$line2" ]; then
    ng "[公式/PROGRAM] ${arm}: G3決定論性が破れた(2走の記録が不一致。gate_failed)"
    official_program_gate_failed=$((official_program_gate_failed + 1))
    overall_rc=1
    continue
  fi
  verdict="$(check_program_record_against_expected "$arm" "$EXPECTED_PROGRAMS" "$line1")"
  case "$verdict" in
    conform)
      ok "[公式/PROGRAM] ${arm}: conform（2走一致・期待値とも一致）"
      official_program_conform=$((official_program_conform + 1))
      ;;
    gate_failed)
      ng "[公式/PROGRAM] ${arm}: 期待値に行が無い(gate_failed)"
      official_program_gate_failed=$((official_program_gate_failed + 1))
      overall_rc=1
      ;;
    *)
      ng "[公式/PROGRAM] ${arm}: ${verdict}（再導出した記録が期待値と不一致）"
      official_program_not_conform=$((official_program_not_conform + 1))
      overall_rc=1
      ;;
  esac
done

say "公式ROM側の集計(PROGRAM場面)"
echo "  conform: ${official_program_conform} / 8"
echo "  not_conform: ${official_program_not_conform} / 8"
echo "  gate_failed: ${official_program_gate_failed} / 8"

say "公式ROM側の再導出(ARITH場面。40腕)"

official_arith_conform=0
official_arith_not_conform=0
official_arith_gate_failed=0

for arm in "${ARITH_ARM_NAMES[@]}"; do
  arith_arm_params "$arm"
  prefix1="$WORK/official_arith_${arm}_run1"
  prefix2="$WORK/official_arith_${arm}_run2"
  line1="$(run_print_arm_once "$OFFICIAL_ROMDIR" "$prefix1" "${PRINT_ARM_ARGS[@]}" 2>"$prefix1.err.txt")"
  rc1=$?
  arith_arm_params "$arm"
  line2="$(run_print_arm_once "$OFFICIAL_ROMDIR" "$prefix2" "${PRINT_ARM_ARGS[@]}" 2>"$prefix2.err.txt")"
  rc2=$?
  if [ "$rc1" -ne 0 ] || [ "$rc2" -ne 0 ] || [ -z "$line1" ] || [ -z "$line2" ]; then
    ng "[公式/ARITH] ${arm}: 走行または記録化に失敗した(gate_failed)"
    sed 's/^/       /' "$prefix1.err.txt" "$prefix2.err.txt" 2>/dev/null
    official_arith_gate_failed=$((official_arith_gate_failed + 1))
    overall_rc=1
    continue
  fi
  if [ "$line1" != "$line2" ]; then
    ng "[公式/ARITH] ${arm}: G3決定論性が破れた(2走の記録が不一致。gate_failed)"
    official_arith_gate_failed=$((official_arith_gate_failed + 1))
    overall_rc=1
    continue
  fi
  ok_rel="$(printf '%s' "$line1" | cut -f2)"
  if [ "$ok_rel" = "NA" ] || { [ "$ok_rel" != "" ] && [ "$ok_rel" -lt 2 ] 2>/dev/null; }; then
    ng "[公式/ARITH] ${arm}: G8(出力完了の確認)が偽(写しが早すぎた。gate_failed)"
    official_arith_gate_failed=$((official_arith_gate_failed + 1))
    overall_rc=1
    continue
  fi
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$EXPECTED_ARITH")"
  if [ -z "$row" ]; then
    ng "[公式/ARITH] ${arm}: 期待値に行が無い(gate_failed)"
    official_arith_gate_failed=$((official_arith_gate_failed + 1))
    overall_rc=1
    continue
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_ok="$(printf '%s' "$row" | cut -f3)"
  e_sha="$(printf '%s' "$row" | cut -f4)"
  a_count="$(printf '%s' "$line1" | cut -f1)"
  a_sha="$(printf '%s' "$line1" | cut -f3)"
  if [ "$a_count" != "$e_count" ] || [ "$ok_rel" != "$e_ok" ] || [ "$a_sha" != "$e_sha" ]; then
    ng "[公式/ARITH] ${arm}: not_conform（再導出した記録が期待値と不一致）"
    official_arith_not_conform=$((official_arith_not_conform + 1))
    overall_rc=1
  else
    ok "[公式/ARITH] ${arm}: conform（2走一致・期待値とも一致）"
    official_arith_conform=$((official_arith_conform + 1))
  fi
done

say "公式ROM側の集計(ARITH場面)"
echo "  conform: ${official_arith_conform} / 40"
echo "  not_conform: ${official_arith_not_conform} / 40"
echo "  gate_failed: ${official_arith_gate_failed} / 40"

say "公式ROM側の再導出(TRANS場面。59腕)"

official_trans_conform=0
official_trans_not_conform=0
official_trans_gate_failed=0

for arm in "${TRANS_ARM_NAMES[@]}"; do
  trans_arm_params "$arm"
  prefix1="$WORK/official_trans_${arm}_run1"
  prefix2="$WORK/official_trans_${arm}_run2"
  line1="$(run_print_arm_once "$OFFICIAL_ROMDIR" "$prefix1" "${PRINT_ARM_ARGS[@]}" 2>"$prefix1.err.txt")"
  rc1=$?
  trans_arm_params "$arm"
  line2="$(run_print_arm_once "$OFFICIAL_ROMDIR" "$prefix2" "${PRINT_ARM_ARGS[@]}" 2>"$prefix2.err.txt")"
  rc2=$?
  if [ "$rc1" -ne 0 ] || [ "$rc2" -ne 0 ] || [ -z "$line1" ] || [ -z "$line2" ]; then
    ng "[公式/TRANS] ${arm}: 走行または記録化に失敗した(gate_failed)"
    sed 's/^/       /' "$prefix1.err.txt" "$prefix2.err.txt" 2>/dev/null
    official_trans_gate_failed=$((official_trans_gate_failed + 1))
    overall_rc=1
    continue
  fi
  if [ "$line1" != "$line2" ]; then
    ng "[公式/TRANS] ${arm}: G3決定論性が破れた(2走の記録が不一致。gate_failed)"
    official_trans_gate_failed=$((official_trans_gate_failed + 1))
    overall_rc=1
    continue
  fi
  ok_rel="$(printf '%s' "$line1" | cut -f2)"
  if [ "$ok_rel" = "NA" ] || { [ "$ok_rel" != "" ] && [ "$ok_rel" -lt 2 ] 2>/dev/null; }; then
    ng "[公式/TRANS] ${arm}: G8(出力完了の確認)が偽(写しが早すぎた。gate_failed)"
    official_trans_gate_failed=$((official_trans_gate_failed + 1))
    overall_rc=1
    continue
  fi
  row="$(awk -F'\t' -v a="$arm" '$1==a{print;exit}' "$EXPECTED_TRANS")"
  if [ -z "$row" ]; then
    ng "[公式/TRANS] ${arm}: 期待値に行が無い(gate_failed)"
    official_trans_gate_failed=$((official_trans_gate_failed + 1))
    overall_rc=1
    continue
  fi
  e_count="$(printf '%s' "$row" | cut -f2)"
  e_ok="$(printf '%s' "$row" | cut -f3)"
  e_sha="$(printf '%s' "$row" | cut -f4)"
  a_count="$(printf '%s' "$line1" | cut -f1)"
  a_sha="$(printf '%s' "$line1" | cut -f3)"
  if [ "$a_count" != "$e_count" ] || [ "$ok_rel" != "$e_ok" ] || [ "$a_sha" != "$e_sha" ]; then
    ng "[公式/TRANS] ${arm}: not_conform（再導出した記録が期待値と不一致）"
    official_trans_not_conform=$((official_trans_not_conform + 1))
    overall_rc=1
  else
    ok "[公式/TRANS] ${arm}: conform（2走一致・期待値とも一致）"
    official_trans_conform=$((official_trans_conform + 1))
  fi
done

say "公式ROM側の集計(TRANS場面)"
echo "  conform: ${official_trans_conform} / 59"
echo "  not_conform: ${official_trans_not_conform} / 59"
echo "  gate_failed: ${official_trans_gate_failed} / 59"

if [ "$overall_rc" -eq 0 ]; then
  echo
  echo "conform_l4: 自作ROM側・公式ROM側とも全項目OK"
else
  echo
  echo "conform_l4: 失敗した項目がある（上記参照）"
fi
exit "$overall_rc"
