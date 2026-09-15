#!/usr/bin/env bash
# tools/conform_l4.sh — l4-c1b「打鍵エコー適合の場面固定」・
# l4-c2c「直接モードPRINT適合の場面固定」のランナー。
#
# 事前登録: docs/notes/l4-c1b-echo-conformance-scene-preregistration.md
# （打鍵エコー、11腕）・
# docs/notes/l4-c2c-print-conformance-scene-preregistration.md
# （直接モードPRINT、P1〜P5の16腕）。
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
PROBE="$REPO/tools/l4_vram_probe.py"
BUILD_MAIN="$REPO/src/build_main_rom.py"
EXPECTED="$REPO/tests/conformance/expected_l4_echo.tsv"
EXPECTED_PRINT="$REPO/tests/conformance/expected_l4_print.tsv"

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

if [ "$overall_rc" -eq 0 ]; then
  echo
  echo "conform_l4: 自作ROM側・公式ROM側とも全項目OK"
else
  echo
  echo "conform_l4: 失敗した項目がある（上記参照）"
fi
exit "$overall_rc"
