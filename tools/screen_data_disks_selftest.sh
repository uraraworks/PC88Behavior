#!/usr/bin/env bash
# tools/screen_data_disks_selftest.sh — tools/screen_data_disks.sh /
# tools/lib_screen_data_disks.sh を公式ROM・公式ディスク無しで検査する。
#
# tools/screen_boot_disks_selftest.sh と同じ作法（合成フィクスチャのみ
# 使用、わざと壊して検出できることまで確かめる、「名前を出さない」性質を
# 本体スクリプト経由で検査する）を踏襲する。
#
# 使い方: tools/screen_data_disks_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCREEN="$SCRIPT_DIR/screen_data_disks.sh"
LIB_DATA="$SCRIPT_DIR/lib_screen_data_disks.sh"
LIB_BOOT="$SCRIPT_DIR/lib_screen_boot_disks.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

source "$LIB_BOOT"
source "$LIB_DATA"

# =========================================================================
# 1. read_screen_signature: 合成reportから line/char/sha を取り出す
# =========================================================================
make_report() {
  local path="$1"; shift
  {
    echo "[測定終了時のテキスト画面]"
    local row
    for row in "$@"; do
      printf '  %s\n' "$row"
    done
    echo
  } > "$path"
}

REPORT_MULTI="$WORK/multi.report.txt"
make_report "$REPORT_MULTI" "0| AAA.BAS" "1| BBB.BAS" "2| CCC.BAS"
SIG_MULTI="$(read_screen_signature "$REPO_ROOT" "$REPORT_MULTI")"
IFS=$'\t' read -r LC CC SHA <<<"$SIG_MULTI"
if [ "$LC" = "3" ] && [ -n "$SHA" ] && [ "${#SHA}" = 64 ]; then
  pass "a. read_screen_signature: 3行の合成画面からline_count=3・64桁SHAを返す"
else
  fail "a. read_screen_signature: got [$SIG_MULTI]"
fi

REPORT_MULTI2="$WORK/multi2.report.txt"
make_report "$REPORT_MULTI2" "0| AAA.BAS" "1| BBB.BAS" "2| CCC.BAS"
SIG_MULTI2="$(read_screen_signature "$REPO_ROOT" "$REPORT_MULTI2")"
if [ "$SIG_MULTI" = "$SIG_MULTI2" ]; then
  pass "a. read_screen_signature: 同一内容の画面は同じ署名を返す（決定論性）"
else
  fail "a. read_screen_signature: 同一内容なのに署名が違う"
fi

REPORT_ONE="$WORK/one.report.txt"
make_report "$REPORT_ONE" "0| Device I/O Error"
SIG_ONE="$(read_screen_signature "$REPO_ROOT" "$REPORT_ONE")"
IFS=$'\t' read -r LC1 CC1 SHA1 <<<"$SIG_ONE"
if [ "$LC1" = "1" ] && [ "$SHA1" != "$SHA" ]; then
  pass "a. read_screen_signature: 異なる内容の画面は異なる署名を返す（衝突しない）"
else
  fail "a. read_screen_signature: 内容が違うのに署名が同じ、または行数が違う: got [$SIG_ONE]"
fi

REPORT_NOSCREEN="$WORK/noscreen.report.txt"
echo "画面節が無いダミーレポート" > "$REPORT_NOSCREEN"
SIG_NONE="$(read_screen_signature "$REPO_ROOT" "$REPORT_NOSCREEN")"
if [ -z "$SIG_NONE" ]; then
  pass "a. read_screen_signature: 画面節が無いreportでは空を返す（黙って一致に化けない）"
else
  fail "a. read_screen_signature: 画面節が無いのに署名が返った: [$SIG_NONE]"
fi

# =========================================================================
# 2. read_read_data_count: 打鍵後の窓で件数を絞れるか
# =========================================================================
make_fb_iolog() {
  # $1=path 以降: "kind:value:frame" のFBイベント列
  local path="$1"; shift
  python3 - "$path" "$@" <<'EOF'
import sys
path = sys.argv[1]
events = []
for spec in sys.argv[2:]:
    kind, value, frame = spec.split(":")
    events.append((kind, int(value, 0), int(frame)))
with open(path, "w", encoding="utf-8") as fp:
    fp.write("# 合成FDCログ（公式データ不使用）\n")
    fp.write("core      : (テスト用ダミー)\nframes    : 4000\n\n")
    fp.write("# main\n# seq clock frame cpu kind port value pc\n\n")
    fp.write("# sub\n# seq clock frame cpu kind port value pc\n")
    for seq, (kind, value, frame) in enumerate(events, 1):
        fp.write(f"{seq:6d} {seq:6d} {frame:4d} sub {kind:<4} 00FB {value:02X} 0100\n")
EOF
}

# READ DATA(8パラメータ、結果7バイト)を frame=100 と frame=1000 で1回ずつ発行。
# パラメータ8バイトは unit/head, C, H, R, N, EOT, GPL, DTL
# (tools/analyze_write_path.py の PARAM_COUNTS[0x06]=8 と同じ形)。
IOLOG_TWO_READS="$WORK/two_reads.iolog.txt"
make_fb_iolog "$IOLOG_TWO_READS" \
  "OUT:0x06:100" "OUT:0x01:100" "OUT:0:100" "OUT:0:100" "OUT:1:100" "OUT:2:100" "OUT:0xFF:100" "OUT:0x1B:100" "OUT:0xFF:100" \
  "IN:0x20:100" "IN:0:100" "IN:5:100" "IN:0:100" "IN:1:100" "IN:2:100" "IN:7:100" \
  "OUT:0x06:1000" "OUT:0x01:1000" "OUT:0:1000" "OUT:0:1000" "OUT:1:1000" "OUT:2:1000" "OUT:0xFF:1000" "OUT:0x1B:1000" "OUT:0xFF:1000" \
  "IN:0x20:1000" "IN:0:1000" "IN:5:1000" "IN:0:1000" "IN:1:1000" "IN:2:1000" "IN:7:1000"

CNT_ALL="$(read_read_data_count "$REPO_ROOT" "$IOLOG_TWO_READS" 0)"
if [ "$CNT_ALL" = "2" ]; then
  pass "b. read_read_data_count: after-frame=0では2件(frame=100と1000)とも数える"
else
  fail "b. read_read_data_count(after=0): 期待2件のところ [$CNT_ALL]"
fi

CNT_AFTER="$(read_read_data_count "$REPO_ROOT" "$IOLOG_TWO_READS" 700)"
if [ "$CNT_AFTER" = "1" ]; then
  pass "b. read_read_data_count: after-frame=700では frame=100 のREAD DATAを除外し1件だけ数える"
else
  fail "b. read_read_data_count(after=700): 期待1件のところ [$CNT_AFTER]"
fi

IOLOG_ZERO_READS="$WORK/zero_reads.iolog.txt"
make_fb_iolog "$IOLOG_ZERO_READS" "OUT:0x08:100" "IN:0x20:100" "IN:5:100"
CNT_ZERO="$(read_read_data_count "$REPO_ROOT" "$IOLOG_ZERO_READS" 0)"
if [ "$CNT_ZERO" = "0" ]; then
  pass "b. read_read_data_count: READ DATAが無いiologから0を返す"
else
  fail "b. read_read_data_count: 期待0件のところ [$CNT_ZERO]"
fi

# =========================================================================
# 3. classify_data_disk: 判定ロジックの3分岐＋検出力
# =========================================================================
# refP: 3行/読める側の形。refN: 1行/読めない側の形。
RP_L=3; RP_C=30; RP_S="p_sha"
RN_L=1; RN_C=18; RN_S="n_sha"

V_READABLE="$(classify_data_disk 4 40 5 cand_sha "$RP_L" "$RP_C" "$RP_S" "$RN_L" "$RN_C" "$RN_S")"
[ "$V_READABLE" = "読める" ] && pass "c. classify_data_disk: refNより行数が多くREAD DATA>0なら読める" \
  || fail "c. 期待「読める」のところ [$V_READABLE]"

V_UNREADABLE_ZERO="$(classify_data_disk 1 18 0 "$RN_S" "$RP_L" "$RP_C" "$RP_S" "$RN_L" "$RN_C" "$RN_S")"
[ "$V_UNREADABLE_ZERO" = "読めない" ] && pass "c. classify_data_disk: READ DATA=0なら読めない" \
  || fail "c. 期待「読めない」(READ DATA=0)のところ [$V_UNREADABLE_ZERO]"

V_UNREADABLE_MATCH="$(classify_data_disk "$RN_L" "$RN_C" 3 "$RN_S" "$RP_L" "$RP_C" "$RP_S" "$RN_L" "$RN_C" "$RN_S")"
[ "$V_UNREADABLE_MATCH" = "読めない" ] && pass "c. classify_data_disk: 画面がrefNと同じ形(行数・文字数一致)なら読めない" \
  || fail "c. 期待「読めない」(refN一致)のところ [$V_UNREADABLE_MATCH]"

V_UNCLEAR="$(classify_data_disk 2 20 0 unclear_sha "$RP_L" "$RP_C" "$RP_S" "$RN_L" "$RN_C" "$RN_S")"
[ "$V_UNCLEAR" = "どちらとも言えない" ] && pass "c. classify_data_disk: refNより行数が多いがREAD DATA=0ならどちらとも言えない" \
  || fail "c. 期待「どちらとも言えない」のところ [$V_UNCLEAR]"

# --- 検出力（陽性対照）: 常に同じ判定を返す壊れた実装と区別できるか ---
broken_always_readable() { echo "読める"; }
if [ "$(broken_always_readable)" != "$V_UNREADABLE_ZERO" ]; then
  pass "d. 陽性対照: 「常に読める」という壊れた実装なら期待「読めない」のケースで違う結果になる"
else
  fail "d. 陽性対照が機能していない"
fi

# =========================================================================
# 4. 本体スクリプトをフェイクデータ経由で通し、末端の出力を検査する。
#    ここが「名前を出さない」性質そのものの検査。
# =========================================================================
FAKEDISKDIR="$WORK/fake_diskdir"
mkdir -p "$FAKEDISKDIR"
SECRET1="TOPSECRET_DELTA_TITLE.D88"
SECRET2="TOPSECRET_EPSILON_TITLE.D88"
SECRET3="TOPSECRET_ZETA_TITLE.D88"
SECRET4="TOPSECRET_ETA_TITLE.D88"
SECRET5="TOPSECRET_THETA_TITLE.D88"
SECRET6="TOPSECRET_IOTA_TITLE.D88"
SECRET7="TOPSECRET_KAPPA_TITLE.D88"
SECRET8="TOPSECRET_LAMBDA_TITLE.D88"
for s in "$SECRET1" "$SECRET2" "$SECRET3" "$SECRET4" "$SECRET5" "$SECRET6" "$SECRET7" "$SECRET8"; do
  : > "$FAKEDISKDIR/$s"
done

SORTED="$(list_disk_basenames "$FAKEDISKDIR")"
D8_NAME="$(printf '%s\n' "$SORTED" | sed -n '8p')"
D8_DIGEST="$(digest_basename "$D8_NAME")"

FAKEDIR="$WORK/fake_measurements"
mkdir -p "$FAKEDIR"

# refP: 読める側の形（3行）。refN: 読めない側の形（1行、refPと違う内容）。
make_report "$FAKEDIR/refP.report.txt" "0| AAA.BAS" "1| BBB.BAS" "2| CCC.BAS"
make_fb_iolog "$FAKEDIR/refP.iolog.txt" \
  "OUT:0x06:800" "OUT:0x01:800" "OUT:0:800" "OUT:0:800" "OUT:1:800" "OUT:2:800" "OUT:0xFF:800" "OUT:0x1B:800" "OUT:0xFF:800" \
  "IN:0x20:800" "IN:0:800" "IN:5:800" "IN:0:800" "IN:1:800" "IN:2:800" "IN:7:800"
make_report "$FAKEDIR/refN.report.txt" "0| Device I/O Error"
make_fb_iolog "$FAKEDIR/refN.iolog.txt" "OUT:0x08:800" "IN:0x20:800" "IN:5:800"

# disk1..disk7: refNと同型（読めない）。disk8: refPと同型（読める、A:=B:相当）。
for n in 1 2 3 4 5 6 7; do
  cp "$FAKEDIR/refN.report.txt" "$FAKEDIR/disk${n}.report.txt"
  cp "$FAKEDIR/refN.iolog.txt" "$FAKEDIR/disk${n}.iolog.txt"
done
cp "$FAKEDIR/refP.report.txt" "$FAKEDIR/disk8.report.txt"
cp "$FAKEDIR/refP.iolog.txt" "$FAKEDIR/disk8.iolog.txt"

RUN_OUT="$WORK/run.out.txt"
RUN_ERR="$WORK/run.err.txt"
PC88_REF_DISK_DIR="$FAKEDISKDIR" PC88_REF_ROM_DIR="$WORK/unused_rom_dir" \
  SCREEN_DATA_DISKS_FAKE_DIR="$FAKEDIR" \
  SCREEN_DATA_DISKS_A_DIGEST="$D8_DIGEST" \
  "$SCREEN" >"$RUN_OUT" 2>"$RUN_ERR"
RUN_RC=$?

if [ "$RUN_RC" -eq 0 ]; then
  pass "e. 本体スクリプトがフェイクデータ経由で正常終了した(rc=0)"
else
  fail "e. 本体スクリプトが異常終了した(rc=$RUN_RC)。stderr:"
  sed 's/^/       /' "$RUN_ERR"
fi

LEAKED=0
for s in "$SECRET1" "$SECRET2" "$SECRET3" "$SECRET4" "$SECRET5" "$SECRET6" "$SECRET7" "$SECRET8" "TOPSECRET"; do
  if grep -qF "$s" "$RUN_OUT" "$RUN_ERR"; then
    LEAKED=1
    fail "f. 出力にファイル名由来の文字列が漏れている: $s"
  fi
done
[ "$LEAKED" = 0 ] && pass "f. 標準出力・標準エラーのいずれにもディスクの実ファイル名が含まれない"

if grep -q "読める: 1 本" "$RUN_OUT" && grep -q "読めない: 7 本" "$RUN_OUT"; then
  pass "g. 集計: disk8のみ読める・disk1〜7が読めないという期待どおりの内訳"
else
  fail "g. 集計行が期待と違う"
  sed 's/^/       /' "$RUN_OUT"
fi

if grep -qF "disk#8  ${D8_DIGEST}" "$RUN_OUT" && grep -q "disk#8.*判定=読める" "$RUN_OUT"; then
  pass "g. disk#8(${D8_DIGEST}相当)が読めると判定され、通し番号・ダイジェストが出力されている"
else
  fail "g. disk#8 の出力行が期待と一致しない"
fi

# --- h. disk#8ダイジェスト不一致なら中断すること（誤ったA:を使わない防御） ---
RUN_OUT_MISMATCH="$WORK/run_mismatch.out.txt"
PC88_REF_DISK_DIR="$FAKEDISKDIR" PC88_REF_ROM_DIR="$WORK/unused_rom_dir" \
  SCREEN_DATA_DISKS_FAKE_DIR="$FAKEDIR" \
  SCREEN_DATA_DISKS_A_DIGEST="deadbeef" \
  "$SCREEN" >"$RUN_OUT_MISMATCH" 2>"$WORK/run_mismatch.err.txt"
RUN_MISMATCH_RC=$?
if [ "$RUN_MISMATCH_RC" -ne 0 ] && grep -q "ダイジェストが期待値と違う" "$WORK/run_mismatch.err.txt"; then
  pass "h. disk#8のダイジェストが期待と違えば測定に入らず中断する（誤ったA:での測定を防ぐ）"
else
  fail "h. ダイジェスト不一致を検出できていない(rc=$RUN_MISMATCH_RC)"
fi

# --- i. 参照Pの測定に失敗したら明示的に中断すること（黙ってSKIPしない） ---
FAKEDIR_NOREF="$WORK/fake_measurements_noref"
mkdir -p "$FAKEDIR_NOREF"
for n in 1 2 3 4 5 6 7 8; do
  cp "$FAKEDIR/disk${n}.report.txt" "$FAKEDIR_NOREF/disk${n}.report.txt"
  cp "$FAKEDIR/disk${n}.iolog.txt" "$FAKEDIR_NOREF/disk${n}.iolog.txt"
done
# refP.iolog.txt / refP.report.txt をわざと欠落させる。
RUN_OUT_NOREF="$WORK/run_noref.out.txt"
PC88_REF_DISK_DIR="$FAKEDISKDIR" PC88_REF_ROM_DIR="$WORK/unused_rom_dir" \
  SCREEN_DATA_DISKS_FAKE_DIR="$FAKEDIR_NOREF" \
  SCREEN_DATA_DISKS_A_DIGEST="$D8_DIGEST" \
  "$SCREEN" >"$RUN_OUT_NOREF" 2>"$WORK/run_noref.err.txt"
RUN_NOREF_RC=$?
if [ "$RUN_NOREF_RC" -ne 0 ] && grep -q "参照Pの測定に失敗した" "$WORK/run_noref.err.txt"; then
  pass "i. 参照Pが測れないときは明示的に中断する（黙ってOKの顔をして終わらない）"
else
  fail "i. 参照P欠落時の扱いが期待と違う(rc=$RUN_NOREF_RC)"
fi

# --- j. ディスクが0本の場合を明示的に報告すること -----------------------
EMPTYDIR="$WORK/empty_diskdir"
mkdir -p "$EMPTYDIR"
RUN_OUT_EMPTY="$WORK/run_empty.out.txt"
PC88_REF_DISK_DIR="$EMPTYDIR" PC88_REF_ROM_DIR="$WORK/unused_rom_dir" \
  SCREEN_DATA_DISKS_FAKE_DIR="$FAKEDIR" \
  "$SCREEN" >"$RUN_OUT_EMPTY" 2>"$WORK/run_empty.err.txt"
RUN_EMPTY_RC=$?
if [ "$RUN_EMPTY_RC" -eq 0 ] && grep -q "0本" "$RUN_OUT_EMPTY"; then
  pass "j. ディスク0本のとき「0本」であることを明示的に報告する"
else
  fail "j. ディスク0本の扱いが期待と違う(rc=$RUN_EMPTY_RC)"
fi

# =========================================================================
echo
if [ "$FAIL" -eq 0 ]; then
  echo "screen_data_disks_selftest: 全項目OK"
else
  echo "screen_data_disks_selftest: 失敗した項目がある"
fi
exit "$FAIL"
