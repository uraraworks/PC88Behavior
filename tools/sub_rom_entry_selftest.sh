#!/usr/bin/env bash
# 固定入口を自作main・自作sub・RAM上の自作プローブで検査する。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
for name in ${!PC88_REF_@}; do unset "$name"; done
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* | head -1)}"
# 古いコアにはスナップショットがない。固定済み上流と自前パッチから
# 一時コアを作り、既存のvendorや他の作業には手を加えない。
SYMS="$(nm "$CORE" 2>/dev/null || true)"
if [[ "$SYMS" != *retro_q88h_sub_snapshot_config* || "$SYMS" != *retro_q88h_sub_rom_read_config* ]]; then
  CORE_TREE="$WORK/core"
  mkdir -p "$CORE_TREE"
  git -C "$VENDOR" archive b5a0e044a914c9a6b8d7b2dd2ddd152f93d35687 | \
    tar -xf - -C "$CORE_TREE" --exclude='src/z80-debug.c' \
      --exclude='src/LIBRETRO/pseudo_bios.h' --exclude='src/font.h'
  cp "$REPO"/tools/harness/core/* "$CORE_TREE/src/"
  for patch in "$REPO"/tools/patches/*.patch; do
    git -C "$CORE_TREE" apply --whitespace=nowarn "$patch"
  done
  printf '{ global: *; };\n' > "$CORE_TREE/link.T"
  platform=()
  if [[ "$(uname -s)" == Darwin ]]; then platform=(platform=osx); fi
  if ! make -s -C "$CORE_TREE" "${platform[@]}" -j4 >"$WORK/build.log" 2>&1; then
    cat "$WORK/build.log" >&2
    exit 1
  fi
  CORE="$(ls "$CORE_TREE"/quasi88_libretro.* | head -1)"
fi
make -s -C "$REPO/tools/harness/frontend"
python3 "$REPO/tools/sub_rom_entry_selftest.py" "$REPO" "$WORK" "$CORE"
