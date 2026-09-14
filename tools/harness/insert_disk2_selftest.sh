#!/usr/bin/env bash
# q88measure --insert-disk2/--insert-disk2-at の末端自己検査。
# m7lw用の器具（実行中フレームでのDRIVE_2差し込み）が末端まで
# ちゃんと効いているかを、自作ROM・自作媒体だけで確かめる。
# tools/harness/disk2_selftest.sh の作法を踏襲する。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-insertdisk2.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }
sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'
  fi
}

CORE="$(find "$VENDOR" -maxdepth 1 -type f -name 'quasi88_libretro.*' -print | head -1)"
[ -n "$CORE" ] || ng "コア成果物が無い"

make -s -C "$FRONTEND_DIR"
mkdir -p "$WORK/rom"
python3 "$REPO/tools/harness/make_test_rom.py" "$WORK/rom"
python3 "$REPO/tools/make_n88_blank_disk.py" "$WORK/disk1.d88" >/dev/null
python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/disk2.d88" >/dev/null

# --- 陽性: 挿入ありの走行でOKになり、レポートへinsert2行が正しく残る ---
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --disk "$WORK/disk1.d88" --insert-disk2 "$WORK/disk2.d88" --insert-disk2-at 5 \
  --frames 10 --out "$WORK/positive.out" --expect-exec 0x0000 \
  >"$WORK/positive.stdout" 2>"$WORK/positive.stderr" \
  || ng "実行中差し込みの陽性対照が失敗した"
grep -q '差し込み前のDRIVE_2空状態をコア末端で確認' "$WORK/positive.stderr" \
  || ng "差し込み前の空状態を末端で確認できない"
grep -q 'DRIVE_2への実行中差し込みをコア末端状態で確認 (frame=5)' "$WORK/positive.stderr" \
  || ng "実行中差し込みを末端で確認できない"
grep -q "^insert2   : frame=5 rc=1 actual=$WORK/disk2.d88\$" "$WORK/positive.out" \
  || ng "insert2行がレポートへ指定パスどおりに記録されない"
ok "実行中差し込みをDRIVE_2のコア末端状態とレポートで確認"

# --- 引数の組の誤り ---
set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --disk "$WORK/disk1.d88" --insert-disk2 "$WORK/disk2.d88" --frames 10 \
  >/dev/null 2>"$WORK/only_path.stderr"
only_path_rc=$?
set -e
[ "$only_path_rc" -eq 2 ] || ng "--insert-disk2のみの指定を弾けない(rc=${only_path_rc})"
grep -q -- '--insert-disk2 と --insert-disk2-at は両方必須' "$WORK/only_path.stderr" \
  || ng "--insert-disk2のみの分類メッセージが無い"
ok "--insert-disk2のみの指定はエラーになる"

set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --disk "$WORK/disk1.d88" --insert-disk2-at 3 --frames 10 \
  >/dev/null 2>"$WORK/only_at.stderr"
only_at_rc=$?
set -e
[ "$only_at_rc" -eq 2 ] || ng "--insert-disk2-atのみの指定を弾けない(rc=${only_at_rc})"
ok "--insert-disk2-atのみの指定はエラーになる"

set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --disk "$WORK/disk1.d88" --disk2 "$WORK/disk2.d88" \
  --insert-disk2 "$WORK/disk2.d88" --insert-disk2-at 3 --frames 10 \
  >/dev/null 2>"$WORK/combo.stderr"
combo_rc=$?
set -e
[ "$combo_rc" -eq 2 ] || ng "--disk2との同時指定を弾けない(rc=${combo_rc})"
grep -q -- '--insert-disk2 と --disk2 は同時指定できない' "$WORK/combo.stderr" \
  || ng "--disk2併用の分類メッセージが無い"
ok "--insert-disk2と--disk2の同時指定はエラーになる"

set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --disk "$WORK/disk1.d88" --insert-disk2 "$WORK/disk2.d88" --insert-disk2-at 10 \
  --frames 10 >/dev/null 2>"$WORK/oob.stderr"
oob_rc=$?
set -e
[ "$oob_rc" -eq 2 ] || ng "FRAME>=framesを弾けない(rc=${oob_rc})"
grep -q -- '--insert-disk2-at は --frames 未満で指定すること' "$WORK/oob.stderr" \
  || ng "FRAME>=framesの分類メッセージが無い"
ok "--insert-disk2-atが--frames以上だとエラーになる"

# --- 故障注入: quasi88_disk_insertを呼ばない(呼んだふりだけの)別成果物 ---
# ハッシュ差を先に要求し、注入が成果物へ入らない空振りを排除してから検出を見る。
cc -O2 -Wall -Wextra -std=c99 -D_POSIX_C_SOURCE=200809L \
  -DQ88MEASURE_FAULT_SKIP_INSERT_DISK2 \
  -I"$VENDOR/src/LIBRETRO/libretro-common/include" \
  -I"$REPO/tools/harness/core" \
  -o "$WORK/q88measure-fault" "$FRONTEND_DIR/main.c" -ldl
normal_sha="$(sha256_file "$FRONTEND")"
fault_sha="$(sha256_file "$WORK/q88measure-fault")"
[ "$normal_sha" != "$fault_sha" ] || ng "故障注入版の成果物が通常版から変化していない"
ok "故障注入によりq88measure成果物のSHA-256が実際に変化"

set +e
"$WORK/q88measure-fault" --core "$CORE" --rom-dir "$WORK/rom" \
  --disk "$WORK/disk1.d88" --insert-disk2 "$WORK/disk2.d88" --insert-disk2-at 5 \
  --frames 10 >"$WORK/fault.stdout" 2>"$WORK/fault.stderr"
fault_rc=$?
set -e
[ "$fault_rc" -ne 0 ] || ng "「呼んだふり」故障を検出できない"
grep -q 'NG: DRIVE_2への実行中差し込みが末端で確認できない' "$WORK/fault.stderr" \
  || ng "「呼んだふり」故障の末端検出分類が無い"
ok "quasi88_disk_insertを呼ばない故障注入は末端検査で実際に非0終了した（rc=${fault_rc}）"

printf 'insert_disk2_selftest: 全項目OK\n'
