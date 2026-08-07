#!/usr/bin/env bash
# 計測ハーネスの疎通試験。
#
# 自作の合成 ROM（make_test_rom.py）を使い、5 種類のバスアクセスすべてが
# 採取結果の末端まで届くことを実測する。公式 ROM は一切要らない。
#
# これを通してから測定を始めること。
# 「アクセスが無かった」のか「観測できていなかった」のかを区別できないまま
# 仕様書を起こすと、その仕様書は静かに間違ったものになる。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
WORK="${TMPDIR:-/tmp}/pc88h-selftest.$$"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi

say "フロントエンドをビルド"
make -s -C "$REPO/tools/harness/frontend"

say "合成 ROM を生成（自作のバイト列。公式 ROM は使わない）"
mkdir -p "$WORK/rom"
python3 "$REPO/tools/harness/make_test_rom.py" "$WORK/rom"

say "疎通試験"
# make_test_rom.py が仕込んだ既知のアクセスを、5 種類すべてについて要求する。
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom" \
  --frames 8 \
  --out "$WORK/trace.txt" \
  --expect-exec   0x0000 \
  --expect-exec   0x1234 \
  --expect-read   0xC000 \
  --expect-write  0xC001 \
  --expect-io-out 0x99 \
  --expect-io-in  0x99

say "合格"
echo "5 種類のフック（exec / read / write / io-in / io-out）すべてが末端まで届いている。"
