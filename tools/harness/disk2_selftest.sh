#!/usr/bin/env bash
# q88measure --disk2 の末端自己検査。
# 公式ROM・公式媒体を使わず、自作ROMと公開規則だけで生成したD88だけを使う。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-disk2.XXXXXX")"
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

sha1="$(sha256_file "$WORK/disk1.d88")"
sha2="$(sha256_file "$WORK/disk2.d88")"
[ "$sha1" != "$sha2" ] || ng "二つの自作媒体を区別できない"
ok "陽性対照の二つの自作媒体はSHA-256が異なる"

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --disk "$WORK/disk1.d88" --disk2 "$WORK/disk2.d88" \
  --frames 8 --out "$WORK/positive.out" --expect-exec 0x0000 \
  >"$WORK/positive.stdout" 2>"$WORK/positive.stderr" \
  || ng "二本目ありの陽性対照が失敗した"
grep -q 'OK: 二本目のDRIVE_2挿入をコア末端状態で確認' "$WORK/positive.stderr" \
  || ng "二本目ありを末端で確認できない"
grep -q '^disk2     :' "$WORK/positive.out" \
  || ng "二本目が測定成果物へ記録されない"
ok "二本目ありをDRIVE_2のコア末端状態で確認"

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --disk "$WORK/disk1.d88" --expect-disk2-empty \
  --frames 8 --expect-exec 0x0000 \
  >"$WORK/empty.stdout" 2>"$WORK/empty.stderr" \
  || ng "二本目なしの陰性対照が失敗した"
grep -q 'OK: --disk2未指定時のDRIVE_2空状態をコア末端で確認' "$WORK/empty.stderr" \
  || ng "二本目なしを空状態と判定できない"
if grep -q '二本目のDRIVE_2挿入をコア末端状態で確認' "$WORK/empty.stderr"; then
  ng "--disk2未指定なのに二本目ありと誤判定した"
fi
ok "--disk2未指定時にDRIVE_2ありと誤判定しない"

set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --disk "$WORK/disk1.d88" --disk2 "$WORK/存在しない.d88" --frames 8 \
  >"$WORK/missing.stdout" 2>"$WORK/missing.stderr"
missing_rc=$?
set -e
[ "$missing_rc" -ne 0 ] || ng "壊した二本目パスを成功と誤判定した"
grep -q -- '--disk2 の通常ファイルを読めない' "$WORK/missing.stderr" \
  || ng "壊した二本目パスの失敗分類が無い"
if grep -q '二本目のDRIVE_2挿入をコア末端状態で確認' "$WORK/missing.stderr"; then
  ng "壊した二本目パスを末端確認済みと誤判定した"
fi
ok "壊した二本目パスの陰性対照は実際に非0終了した（rc=${missing_rc}）"

# 通常成果物とは別に、二本の順序だけを入れ替える故障注入版を作る。
# ハッシュ差を先に要求し、注入が成果物へ入らない空振りを排除してから検出を見る。
cc -O2 -Wall -Wextra -std=c99 -D_POSIX_C_SOURCE=200809L \
  -DQ88MEASURE_FAULT_SWAP_DISKS \
  -I"$VENDOR/src/LIBRETRO/libretro-common/include" \
  -I"$REPO/tools/harness/core" \
  -o "$WORK/q88measure-fault" "$FRONTEND_DIR/main.c" -ldl
normal_sha="$(sha256_file "$FRONTEND")"
fault_sha="$(sha256_file "$WORK/q88measure-fault")"
[ "$normal_sha" != "$fault_sha" ] || ng "故障注入版の成果物が通常版から変化していない"
ok "故障注入によりq88measure成果物のSHA-256が実際に変化"

set +e
"$WORK/q88measure-fault" --core "$CORE" --rom-dir "$WORK/rom" \
  --disk "$WORK/disk1.d88" --disk2 "$WORK/disk2.d88" --frames 8 \
  >"$WORK/fault.stdout" 2>"$WORK/fault.stderr"
fault_rc=$?
set -e
[ "$fault_rc" -ne 0 ] || ng "順序交換故障を検出できない"
grep -q 'NG: 二本のディスクがDRIVE_1/2へ指定順に入っていない' "$WORK/fault.stderr" \
  || ng "順序交換故障の末端検出分類が無い"
ok "順序交換の故障注入は末端検査で実際に非0終了した（rc=${fault_rc}）"

printf 'disk2_selftest: 全項目OK\n'
