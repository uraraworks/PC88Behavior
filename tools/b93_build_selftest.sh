#!/usr/bin/env bash
# ネットワーク不要。固定上流から全パッチの適用と0030の単体検査・ビルドを行う。
# 引数があればその新規ディレクトリへ検査用コアを残す（結合自己検査用）。
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
source_repo="${B93_UPSTREAM:-${B92_UPSTREAM:-$repo/../vendor/quasi88-libretro}}"
if [ "$#" -gt 0 ]; then
  work="$1"
  [ ! -e "$work" ] || { echo 'B93: 検査先は新規ディレクトリが必要' >&2; exit 2; }
  mkdir -p "$work"
else
  work="$(mktemp -d "${TMPDIR:-/tmp}/b93-patch.XXXXXX")"
  trap 'rm -rf "$work"' EXIT
fi
mkdir "$work/core"
git -C "$source_repo" archive b5a0e044a914c9a6b8d7b2dd2ddd152f93d35687 |
  tar -x -C "$work/core" --exclude=src/z80-debug.c --exclude=src/LIBRETRO/pseudo_bios.h --exclude=src/font.h
cp "$repo"/tools/harness/core/* "$work/core/src/"
for patch in "$repo"/tools/patches/*.patch; do
  (cd "$work/core" && git apply --whitespace=nowarn "$patch")
done
(cd "$work/core" && git apply --reverse --check "$repo/tools/patches/0030-b93-r-after-return.patch")
"${CC:-cc}" -std=c99 -Wall -Wextra -Werror -I"$repo/tools/harness/core" \
  "$repo/tools/b93_patch_selftest.c" "$work/core/src/b93_intervention.c" -o "$work/unit"
"$work/unit" "$work/unit.events"
# Linuxでも frontend が参照する既存のコアシンボルを公開する。
printf '{ global: *; };\n' > "$work/core/link.T"
platform=()
case "$(uname -s)" in Darwin) platform=(platform=osx);; esac
if ! make -s -C "$work/core" ${platform[@]+"${platform[@]}"} -j2 >"$work/build.log" 2>&1; then
  echo 'B93: コアのビルド失敗（外部の build.log を確認）' >&2; exit 1
fi
make -s -B -C "$repo/tools/harness/frontend" CORE_SRC="$work/core/src" >"$work/frontend.log" 2>&1
echo 'B93: パッチ適用とビルド PASS' >&2
