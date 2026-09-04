#!/usr/bin/env bash
# tools/stage_disk_by_digest_selftest.sh — tools/stage_disk_by_digest.sh を
# 公式ROM・公式ディスク無しで検査する。
#
# 既存の *_selftest.sh の作法（合成フィクスチャのみ使用、わざと壊して
# 検出できることまで確かめる）を踏襲する。
#
# 使い方: tools/stage_disk_by_digest_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGE="$SCRIPT_DIR/stage_disk_by_digest.sh"
LIB="$SCRIPT_DIR/lib_screen_boot_disks.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

source "$LIB"

# =========================================================================
# フィクスチャ: 実物ではない合成ダミーの .D88 を用意する。
# 名前はわざと目立つダミー名(TOPSECRET_*)にして、漏れたら検出できるようにする。
# 中身も実データではない合成バイト列（ROM/ディスク由来ではない）。
# =========================================================================
DISKDIR="$WORK/diskdir"
mkdir -p "$DISKDIR"

SECRET1="TOPSECRET_ALPHA_TITLE.D88"
SECRET2="TOPSECRET_BETA_TITLE.d88"
printf 'DUMMY-NOT-REAL-DISK-DATA-ALPHA-0123456789' > "$DISKDIR/$SECRET1"
printf 'DUMMY-NOT-REAL-DISK-DATA-BETA-9876543210'  > "$DISKDIR/$SECRET2"

DIGEST1="$(digest_basename "$SECRET1")"
DIGEST2="$(digest_basename "$SECRET2")"

SRC1_SHA_BEFORE="$(shasum -a 256 "$DISKDIR/$SECRET1" | awk '{print $1}')"
SRC2_SHA_BEFORE="$(shasum -a 256 "$DISKDIR/$SECRET2" | awk '{print $1}')"

# =========================================================================
# a. ダイジェストを与えると中立名の複製ができること
# =========================================================================
OUT1="$WORK/run1.out.txt"
ERR1="$WORK/run1.err.txt"
STAGEDIR1="$WORK/staged1"
PC88_REF_DISK_DIR="$DISKDIR" "$STAGE" "$DIGEST1" "$STAGEDIR1" >"$OUT1" 2>"$ERR1"
RC1=$?

if [ "$RC1" -eq 0 ]; then
  pass "a. 一致1件のとき正常終了する(rc=0)"
else
  fail "a. 一致1件のはずが異常終了した(rc=$RC1)"
  sed 's/^/       /' "$ERR1"
fi

STAGED_PATH1="$(cat "$OUT1")"
EXPECT_PATH1="$STAGEDIR1/${DIGEST1}.d88"
if [ "$STAGED_PATH1" = "$EXPECT_PATH1" ] && [ -f "$STAGED_PATH1" ]; then
  pass "a. 標準出力が期待どおりの中立パス1行で、複製ファイルが実在する"
else
  fail "a. 標準出力(パス)が期待と違う: got=[$STAGED_PATH1] expect=[$EXPECT_PATH1]"
fi

# 標準出力が1行だけであること（余計な行が混ざっていないか）
LINECOUNT1="$(wc -l < "$OUT1" | tr -d ' ')"
if [ "$LINECOUNT1" = "1" ]; then
  pass "a. 標準出力はちょうど1行"
else
  fail "a. 標準出力が1行ではない($LINECOUNT1 行)"
fi

# =========================================================================
# b. 標準出力・標準エラーのどこにも実ファイル名(SECRET)が現れないこと
# =========================================================================
LEAKED=0
for s in "$SECRET1" "TOPSECRET"; do
  if grep -qF "$s" "$OUT1" "$ERR1"; then
    LEAKED=1
    fail "b. 出力にファイル名由来の文字列が漏れている: (伏せる)"
  fi
done
[ "$LEAKED" = 0 ] && pass "b. 標準出力・標準エラーのいずれにも実ファイル名が含まれない"

# =========================================================================
# c. 複製が元とバイト一致すること、元ファイルのハッシュが不変であること
# =========================================================================
if cmp -s "$DISKDIR/$SECRET1" "$STAGED_PATH1"; then
  pass "c. 複製は元とバイト一致する"
else
  fail "c. 複製が元とバイト一致しない"
fi

SRC1_SHA_AFTER="$(shasum -a 256 "$DISKDIR/$SECRET1" | awk '{print $1}')"
if [ "$SRC1_SHA_AFTER" = "$SRC1_SHA_BEFORE" ]; then
  pass "c. 元ファイルのハッシュは実行前後で不変（書き込んでいない）"
else
  fail "c. 元ファイルのハッシュが変化した（書き込んでしまっている）"
fi

# =========================================================================
# d. 一致0件はエラー終了(rc!=0)し、実ファイル名を漏らさないこと
# =========================================================================
OUTD="$WORK/run_zero.out.txt"
ERRD="$WORK/run_zero.err.txt"
PC88_REF_DISK_DIR="$DISKDIR" "$STAGE" "00000000" "$WORK/staged_zero" >"$OUTD" 2>"$ERRD"
RCD=$?
if [ "$RCD" -ne 0 ]; then
  pass "d. 一致0件はエラー終了する(rc=$RCD)"
else
  fail "d. 一致0件なのに正常終了した"
fi
if grep -qF "$SECRET1" "$OUTD" "$ERRD" || grep -qF "$SECRET2" "$OUTD" "$ERRD"; then
  fail "d. 一致0件のエラー出力に実ファイル名が漏れている"
else
  pass "d. 一致0件のエラー出力に実ファイル名は現れない"
fi

# =========================================================================
# e. 一致2件以上はエラー終了(rc!=0)すること。
#    SHA-256の衝突ペアを合成で作ることはできないので、テスト専用に複製した
#    lib_screen_boot_disks.sh（digest_basenameを固定値だけ返すよう差し替え、
#    元のtools/配下は一切変更しない）を使って、2ファイルが同一ダイジェスト
#    に一致する状況を再現する。
# =========================================================================
LIB_MULTI="$WORK/lib_multi.sh"
sed 's/^digest_basename() {$/digest_basename() {\n  echo "aaaaaaaa"; return 0;/' "$LIB" > "$LIB_MULTI"
STAGE_MULTI="$WORK/stage_multi.sh"
sed "s#source \"\$REPO/tools/lib_screen_boot_disks.sh\"#source \"$LIB_MULTI\"#" "$STAGE" > "$STAGE_MULTI"
chmod +x "$STAGE_MULTI"
OUTE="$WORK/run_multi2.out.txt"
ERRE="$WORK/run_multi2.err.txt"
PC88_REF_DISK_DIR="$DISKDIR" "$STAGE_MULTI" "aaaaaaaa" "$WORK/staged_multi2" >"$OUTE" 2>"$ERRE"
RCE="$?"
if [ "$RCE" -ne 0 ]; then
  pass "e. 一致2件以上（digest_basenameを固定値に差し替えたテスト用複製で再現）はエラー終了する(rc=$RCE)"
else
  fail "e. 一致2件以上でも正常終了してしまった"
fi
if grep -qF "$SECRET1" "$OUTE" "$ERRE" || grep -qF "$SECRET2" "$OUTE" "$ERRE"; then
  fail "e. 一致2件以上のエラー出力に実ファイル名が漏れている"
else
  pass "e. 一致2件以上のエラー出力にも実ファイル名は現れない"
fi

# =========================================================================
# f. 陰性対照: 実ファイル名をエコーする「壊れた版」を用意し、
#    bの検査（漏れないこと）がその壊れた版に対しては落ちることを確認する。
# =========================================================================
BROKEN="$WORK/stage_disk_by_digest_broken.sh"
sed -e 's/^# 標準出力へは複製先の中立パス1行だけ。$/echo "DEBUG: matched name was $MATCH_NAME" >\&2\n&/' \
    -e "s#source \"\$REPO/tools/lib_screen_boot_disks.sh\"#source \"$LIB\"#" \
  "$STAGE" > "$BROKEN"
chmod +x "$BROKEN"

if grep -q 'DEBUG: matched name was \$MATCH_NAME' "$BROKEN"; then
  pass "f. 陰性対照用の壊れた版を用意できた（実ファイル名をstderrへエコーする1行を注入）"
else
  fail "f. 陰性対照用の壊れた版の注入に失敗した（sedパターンがstage_disk_by_digest.shの現在の実装と一致しない）"
fi

OUTB="$WORK/run_broken.out.txt"
ERRB="$WORK/run_broken.err.txt"
STAGEDIRB="$WORK/staged_broken"
PC88_REF_DISK_DIR="$DISKDIR" "$BROKEN" "$DIGEST1" "$STAGEDIRB" >"$OUTB" 2>"$ERRB"

if grep -qF "$SECRET1" "$OUTB" "$ERRB"; then
  pass "f. 陰性対照: 実ファイル名をエコーする壊れた版では、確かに実ファイル名が出力に現れる（bの検査に検出力がある）"
else
  fail "f. 陰性対照が機能していない（壊れた版でも実ファイル名が出力に現れなかった＝bの検査が何も見ていない可能性）"
fi

# =========================================================================
# g. 引数が不足・不正なときの扱い（--help相当のusageが出て非0で終わること）
# =========================================================================
OUTG="$WORK/run_usage.out.txt"
ERRG="$WORK/run_usage.err.txt"
PC88_REF_DISK_DIR="$DISKDIR" "$STAGE" >"$OUTG" 2>"$ERRG"
RCG=$?
if [ "$RCG" -ne 0 ] && grep -q '使い方' "$ERRG"; then
  pass "g. 引数無しはエラー終了し、使い方を表示する"
else
  fail "g. 引数無しの扱いが期待と違う(rc=$RCG)"
fi

OUTG2="$WORK/run_badfmt.out.txt"
ERRG2="$WORK/run_badfmt.err.txt"
PC88_REF_DISK_DIR="$DISKDIR" "$STAGE" "not-a-digest" >"$OUTG2" 2>"$ERRG2"
RCG2=$?
if [ "$RCG2" -ne 0 ]; then
  pass "g. ダイジェスト形式が不正なら非0で終了する"
else
  fail "g. 不正な形式のダイジェストでも正常終了してしまった"
fi

# =========================================================================
# h. 出力ディレクトリを省略した場合でも中立パスが返り、複製ができること
# =========================================================================
OUTH="$WORK/run_nooutdir.out.txt"
ERRH="$WORK/run_nooutdir.err.txt"
PC88_REF_DISK_DIR="$DISKDIR" "$STAGE" "$DIGEST2" >"$OUTH" 2>"$ERRH"
RCH=$?
STAGED_PATH2="$(cat "$OUTH")"
if [ "$RCH" -eq 0 ] && [ -f "$STAGED_PATH2" ] && cmp -s "$DISKDIR/$SECRET2" "$STAGED_PATH2"; then
  pass "h. 出力ディレクトリ省略時も既定の一時ディレクトリへ中立名で複製できる"
  rm -rf "$(dirname "$STAGED_PATH2")"
else
  fail "h. 出力ディレクトリ省略時の複製に失敗した(rc=$RCH)"
fi
if grep -qF "$SECRET2" "$OUTH" "$ERRH"; then
  fail "h. 出力ディレクトリ省略時の出力に実ファイル名が漏れている"
else
  pass "h. 出力ディレクトリ省略時の出力にも実ファイル名は現れない"
fi

# =========================================================================
echo
if [ "$FAIL" -eq 0 ]; then
  echo "stage_disk_by_digest_selftest: 全項目OK"
else
  echo "stage_disk_by_digest_selftest: 失敗した項目がある"
fi
exit "$FAIL"
