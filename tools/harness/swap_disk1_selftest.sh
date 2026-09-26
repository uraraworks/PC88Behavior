#!/usr/bin/env bash
# tools/harness/swap_disk1_selftest.sh — q88measure --swap-disk1/--swap-disk1-at
# （実行中にDRIVE_1媒体を差し替える器具）の自己検査。
#
# 公式ROM・公式ディスクは使わない。自作ROMは src/build_main_rom.py、
# 自作媒体は tools/make_m6fe_disk.py の像だけを使う（いずれも既存生成器・
# 既存自己検査済み。バイト列は全て自分で選んだ規則から作られる）。
#
# --insert-disk2/--insert-disk2-at（DRIVE_2への実行中差し込み。
# tools/harness/insert_disk2_selftest.sh 参照——本検査は開かない）と同じ
# 枠組みで、対象がDRIVE_2ではなくDRIVE_1である点だけが違う。
#
# 検査:
#   1. 陽性: --disk（D2.d88）で起動し、frame=30で--swap-disk1（D1.d88）へ
#      差し替える。stderr の確認イベント（差し替え前DRIVE_1確認・差し替え後
#      OK・event行）と、--out report の event/SHA-256行を、差し替え先像
#      自身のSHA-256（このスクリプトが独立に計算した値）と照合する。
#   2. 陰性対照: --swap-disk1-at を外す（--swap-disk1 のみ）→ 引数エラー
#      (rc=2)で走行前に止まり、event行が無い。
#   3. 陰性対照: 存在しない像を指定 → 走行前にエラー終了(rc=2)。
#   4. 陰性対照: --swap-disk1-at が --frames 以上 → エラー終了(rc=2)。
#   5. 陰性対照: --swap-disk1 のみ指定して --disk を省略 → エラー終了(rc=2)。
#   6. 陰性対照: --swap-disk1 を一切指定しない通常走行の report に
#      swap_disk1 関連行が一切無いこと（未使用時に何も出さないこと）。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
BUILD_ROM="$REPO/src/build_main_rom.py"
MAKE_MEDIA="$REPO/tools/make_m6fe_disk.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-swapdisk1.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

FAILED=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; FAILED=1; }
ng_fatal() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng_fatal "コア成果物が無い。先に tools/setup_harness.sh を実行すること"

make -s -C "$FRONTEND_DIR" || ng_fatal "q88measure のビルドが失敗"

python3 "$BUILD_ROM" "$WORK/rom" >"$WORK/build_rom.log" 2>&1 \
  || ng_fatal "build_main_rom.py が失敗(ログ: $WORK/build_rom.log)"
ok "自作ROM(build_main_rom.py、無指定)を生成"

python3 "$MAKE_MEDIA" "$WORK/media" >"$WORK/make_media.log" 2>&1 \
  || ng_fatal "make_m6fe_disk.py が失敗(ログ: $WORK/make_media.log)"
[ -f "$WORK/media/D1.d88" ] && [ -f "$WORK/media/D2.d88" ] \
  || ng_fatal "make_m6fe_disk.py の出力にD1.d88/D2.d88が無い"
ok "自作媒体(make_m6fe_disk.py)を生成(D1.d88/D2.d88)"

DISK1_INITIAL="$WORK/media/D2.d88"   # --diskで最初にDRIVE_1へ入れる媒体
DISK1_SWAP="$WORK/media/D1.d88"      # --swap-disk1で差し替える先

sha256_of() { python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$1"; }
SWAP_SHA="$(sha256_of "$DISK1_SWAP")"

# --- 1. 陽性: frame=30で差し替え、stderr/reportの両方で確認 ----------------
POS_OUT="$WORK/pos.report.txt"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --disk "$DISK1_INITIAL" \
  --frames 60 --swap-disk1 "$DISK1_SWAP" --swap-disk1-at 30 \
  --out "$POS_OUT" >"$WORK/pos.stdout" 2>"$WORK/pos.stderr"
pos_rc=$?

if [ "$pos_rc" -eq 0 ]; then
  ok "陽性: 走行が成功(rc=0)"
else
  ng "陽性: 走行が失敗(rc=$pos_rc)"; cat "$WORK/pos.stderr" >&2
fi

if grep -qF '差し替え前のDRIVE_1媒体をコア末端で確認' "$WORK/pos.stderr"; then
  ok "陽性: 差し替え前のDRIVE_1媒体確認をstderrで確認"
else
  ng "陽性: 差し替え前確認のstderr行が無い"
fi

if grep -qF 'OK: DRIVE_1への実行中差し替えをコア末端状態で確認 (frame=30)' "$WORK/pos.stderr"; then
  ok "陽性: 差し替え後のOK確認をstderrで確認"
else
  ng "陽性: 差し替え後OK確認のstderr行が無い"
fi

if grep -qF $'event\tswap_disk1\tframe=30\tsuccess=1' "$WORK/pos.stderr"; then
  ok "陽性: stderrのイベント行(event\\tswap_disk1\\tframe=30\\tsuccess=1)を確認"
else
  ng "陽性: stderrにイベント行が無い"
fi

if [ -f "$POS_OUT" ] && grep -qF $'event\tswap_disk1\tframe=30\tsuccess=1' "$POS_OUT"; then
  ok "陽性: reportのイベント行を確認"
else
  ng "陽性: reportにイベント行が無い"
fi

REPORT_SHA="$(grep -F $'swap_disk1_sha256\t' "$POS_OUT" 2>/dev/null | cut -f2)"
if [ "$REPORT_SHA" = "$SWAP_SHA" ]; then
  ok "陽性: reportのSHA-256が差し替え先像自身のSHA-256と一致"
else
  ng "陽性: reportのSHA-256が不一致(report=$REPORT_SHA expected=$SWAP_SHA)"
fi

# --- 2. 陰性対照: --swap-disk1-at を外す(片方だけの指定はエラー) -----------
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --disk "$DISK1_INITIAL" \
  --frames 60 --swap-disk1 "$DISK1_SWAP" \
  --out "$WORK/neg_missing_at.report.txt" \
  >"$WORK/neg_missing_at.stdout" 2>"$WORK/neg_missing_at.stderr"
neg1_rc=$?
if [ "$neg1_rc" -eq 2 ] && grep -qF '両方必須' "$WORK/neg_missing_at.stderr" \
  && [ ! -e "$WORK/neg_missing_at.report.txt" ]; then
  ok "陰性対照: --swap-disk1-at 省略はエラー終了(rc=2)、report未作成"
else
  ng "陰性対照: --swap-disk1-at 省略時の停止条件が不正(rc=$neg1_rc)"
fi

# --- 3. 陰性対照: 存在しない像 ---------------------------------------------
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --disk "$DISK1_INITIAL" \
  --frames 60 --swap-disk1 "$WORK/media/DOES_NOT_EXIST.d88" --swap-disk1-at 30 \
  >"$WORK/neg_noexist.stdout" 2>"$WORK/neg_noexist.stderr"
neg2_rc=$?
if [ "$neg2_rc" -eq 2 ] && grep -qF '通常ファイルを読めない' "$WORK/neg_noexist.stderr"; then
  ok "陰性対照: 存在しない像はエラー終了(rc=2)"
else
  ng "陰性対照: 存在しない像の停止条件が不正(rc=$neg2_rc)"
fi

# --- 4. 陰性対照: --swap-disk1-at が --frames 以上 -------------------------
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --disk "$DISK1_INITIAL" \
  --frames 60 --swap-disk1 "$DISK1_SWAP" --swap-disk1-at 60 \
  >"$WORK/neg_toolate.stdout" 2>"$WORK/neg_toolate.stderr"
neg3_rc=$?
if [ "$neg3_rc" -eq 2 ] && grep -qF -- '--frames 未満' "$WORK/neg_toolate.stderr"; then
  ok "陰性対照: --swap-disk1-at >= --frames はエラー終了(rc=2)"
else
  ng "陰性対照: --swap-disk1-at >= --frames の停止条件が不正(rc=$neg3_rc)"
fi

# --- 5. 陰性対照: --disk を省略 ---------------------------------------------
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --frames 60 --swap-disk1 "$DISK1_SWAP" --swap-disk1-at 30 \
  >"$WORK/neg_nodisk.stdout" 2>"$WORK/neg_nodisk.stderr"
neg4_rc=$?
if [ "$neg4_rc" -eq 2 ] && grep -qF -- '--disk' "$WORK/neg_nodisk.stderr"; then
  ok "陰性対照: --disk 省略はエラー終了(rc=2)"
else
  ng "陰性対照: --disk 省略時の停止条件が不正(rc=$neg4_rc)"
fi

# --- 6. 陰性対照: --swap-disk1 未指定の通常走行にはイベント行が無い --------
NOUSE_OUT="$WORK/nouse.report.txt"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --disk "$DISK1_INITIAL" \
  --frames 60 --out "$NOUSE_OUT" \
  >"$WORK/nouse.stdout" 2>"$WORK/nouse.stderr"
nouse_rc=$?
if [ "$nouse_rc" -eq 0 ] && [ -f "$NOUSE_OUT" ] && ! grep -q 'swap_disk1' "$NOUSE_OUT" \
  && ! grep -q 'swap_disk1' "$WORK/nouse.stderr"; then
  ok "陰性対照: --swap-disk1 未指定時はreport/stderrにswap_disk1関連行が無い"
else
  ng "陰性対照: --swap-disk1 未指定なのにswap_disk1関連行が出た(rc=$nouse_rc)"
fi

echo
if [ "$FAILED" -eq 0 ]; then
  printf '%s\n' '全項目 OK'
else
  printf '%s\n' 'NG あり'
fi
exit "$FAILED"
