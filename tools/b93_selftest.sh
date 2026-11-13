#!/usr/bin/env bash
# 自作ROM・自作媒体のみ。実ゲーム・公式ROM・run_allは使わない。
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
umask 077
work="$(mktemp -d "${TMPDIR:-/tmp}/b93-selftest.XXXXXX")"
trap 'rm -rf "$work"' EXIT
if [ -n "${B93_TEST_CORE:-}" ]; then
  core="$B93_TEST_CORE"
else
  "$repo/tools/b93_build_selftest.sh" "$work/build"
  core="$(find "$work/build/core" -maxdepth 1 -name 'quasi88_libretro.*' -type f | head -1)"
fi
PYTHONDONTWRITEBYTECODE=1 python3 "$repo/tools/b93_selftest.py" "$core"
