#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
umask 077
work="$(mktemp -d "${TMPDIR:-/tmp}/b92-selftest.XXXXXX")"
trap 'rm -rf "$work"' EXIT
if [ -n "${B92_TEST_CORE:-}" ]; then
  core="$B92_TEST_CORE"
else
  "$repo/tools/b92_patch_selftest.sh" "$work/build"
  core="$(find "$work/build/core" -maxdepth 1 -name 'quasi88_libretro.*' -type f | head -1)"
fi
python3 "$repo/tools/b92_summary_selftest.py"
python3 "$repo/tools/b92_selftest.py" "$work" "$core"
