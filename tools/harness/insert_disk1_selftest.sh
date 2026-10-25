#!/usr/bin/env bash
# q88measure --insert-disk1/--insert-disk1-at の末端自己検査。
# 空のDRIVE_1へ挿入する器具（実行中フレームでのDRIVE_1差し込み）が末端まで
# ちゃんと効いているかを、自作ROM・自作媒体だけで確かめる。
# tools/harness/disk2_selftest.sh の作法を踏襲する。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-insertdisk1.XXXXXX")"
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

# --- 陽性: 空のDRIVE_1へ挿入。stderr/reportをコア末端状態と像のSHA-256で照合 ---
disk_sha="$(sha256_file "$WORK/disk2.d88")"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --insert-disk1 "$WORK/disk2.d88" --insert-disk1-at 5 \
  --frames 10 --out "$WORK/positive.out" \
  >"$WORK/positive.stdout" 2>"$WORK/positive.stderr" \
  || ng "実行中挿入の陽性対照が失敗した"
grep -q '挿入前のDRIVE_1空状態をコア末端で確認' "$WORK/positive.stderr" \
  || ng "挿入前の空状態を末端で確認できない"
grep -q 'DRIVE_1への実行中挿入をコア末端状態で確認 (frame=5)' "$WORK/positive.stderr" \
  || ng "実行中挿入を末端で確認できない"
grep -qF $'event\tinsert_disk1\tframe=5\tsuccess=1' "$WORK/positive.stderr" \
  || ng "stderrにevent行が無い"
grep -qF $'event\tinsert_disk1\tframe=5\tsuccess=1' "$WORK/positive.out" \
  || ng "reportにevent行が無い"
[ "$(grep -F $'insert_disk1_sha256\t' "$WORK/positive.out" | cut -f2)" = "$disk_sha" ] \
  || ng "reportのSHA-256が媒体と一致しない"
ok "空のDRIVE_1への実行中挿入をコア末端状態・event行・SHA-256で確認"

# --- 末端の効き: --disk で最初から入れた走（対照）には挿入前の空確認が無く、
#     かつ --disk との同時指定は弾かれる。挿入前に空であることの確認は
#     陽性走で出ている（上）ので、ここでは未使用時にevent行が出ないことを見る ---
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --disk "$WORK/disk2.d88" \
  --frames 10 --out "$WORK/control.out" >/dev/null 2>"$WORK/control.stderr" \
  || ng "対照走が失敗した"
! grep -q 'insert_disk1' "$WORK/control.out" "$WORK/control.stderr" \
  || ng "未使用の走にinsert_disk1関連行が出ている"
! grep -q '挿入前のDRIVE_1空状態' "$WORK/control.stderr" \
  || ng "未使用の走に空状態確認が出ている"
ok "未使用の走にはinsert_disk1関連行が出ない"

# --- 引数の組の誤り ---
expect_rc2() { # 名前 期待メッセージ 引数...
  local name="$1" msg="$2"; shift 2
  set +e
  "$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" "$@" >/dev/null 2>"$WORK/$name.stderr"
  local rc=$?
  set -e
  [ "$rc" -eq 2 ] || ng "$name: rc=2にならない(rc=${rc})"
  grep -q -- "$msg" "$WORK/$name.stderr" || ng "$name: 分類メッセージが無い"
  ok "$name はエラー(rc=2)になる"
}
expect_rc2 only_path '--insert-disk1 と --insert-disk1-at は両方必須' \
  --insert-disk1 "$WORK/disk2.d88" --frames 10
expect_rc2 only_at '--insert-disk1 と --insert-disk1-at は両方必須' \
  --insert-disk1-at 3 --frames 10
expect_rc2 with_disk '--insert-disk1 と --disk は同時指定できない' \
  --disk "$WORK/disk1.d88" --insert-disk1 "$WORK/disk2.d88" --insert-disk1-at 3 --frames 10
expect_rc2 with_swap '--insert-disk1 と --swap-disk1 は同時指定できない' \
  --disk "$WORK/disk1.d88" --swap-disk1 "$WORK/disk2.d88" --swap-disk1-at 3 \
  --insert-disk1 "$WORK/disk2.d88" --insert-disk1-at 3 --frames 10
expect_rc2 oob '--insert-disk1-at は --frames 未満で指定すること' \
  --insert-disk1 "$WORK/disk2.d88" --insert-disk1-at 10 --frames 10
expect_rc2 noexist '通常ファイルを読めない' \
  --insert-disk1 "$WORK/NOPE.d88" --insert-disk1-at 3 --frames 10

# --- 故障注入: quasi88_disk_insertを呼ばない(呼んだふりだけの)別成果物 ---
cc -O2 -Wall -Wextra -std=c99 -D_POSIX_C_SOURCE=200809L \
  -DQ88MEASURE_FAULT_SKIP_INSERT_DISK1 \
  -I"$VENDOR/src/LIBRETRO/libretro-common/include" \
  -I"$REPO/tools/harness/core" \
  -o "$WORK/q88measure-fault" "$FRONTEND_DIR/main.c" -ldl
normal_sha="$(sha256_file "$FRONTEND")"
fault_sha="$(sha256_file "$WORK/q88measure-fault")"
[ "$normal_sha" != "$fault_sha" ] || ng "故障注入版の成果物が通常版から変化していない"
ok "故障注入によりq88measure成果物のSHA-256が実際に変化"

set +e
"$WORK/q88measure-fault" --core "$CORE" --rom-dir "$WORK/rom" \
  --insert-disk1 "$WORK/disk2.d88" --insert-disk1-at 5 \
  --frames 10 >"$WORK/fault.stdout" 2>"$WORK/fault.stderr"
fault_rc=$?
set -e
[ "$fault_rc" -ne 0 ] || ng "「呼んだふり」故障を検出できない"
grep -q 'NG: DRIVE_1への実行中挿入が末端で確認できない' "$WORK/fault.stderr" \
  || ng "「呼んだふり」故障の末端検出分類が無い"
ok "quasi88_disk_insertを呼ばない故障注入は末端検査で非0終了した（rc=${fault_rc}）"

printf 'insert_disk1_selftest: 全項目OK\n'
