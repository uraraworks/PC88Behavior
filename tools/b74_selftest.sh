#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d /tmp/b74-selftest.XXXXXX)"; trap 'rm -rf "$work"' EXIT
export PC88_SUB_READ_CORE="${PC88_SUB_READ_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
export PC88_SUB_READ_CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro/src}"
python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" >"$work/sub.log" 2>&1
PC88_B74_WORK="$work/measure" bash "$REPO/tools/measure_b74.sh" --dry-run-sub-rom "$work/sub/DISK.ROM" --output-dir "$work/result"
grep -qx 'row 4 S reply=2 match=2 timeout=0 executed=-' "$work/result/b74-sub-0e-after-00c1.txt"
cat "$work/result/b74-sub-0e-after-00c1.txt"
