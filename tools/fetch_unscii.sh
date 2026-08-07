#!/usr/bin/env bash
# tools/fetch_unscii.sh — 半角ANK(英数記号)フォントの素材 unscii-8 を取得する。
#
# docs/spec/l2-font.md 4.1節・4.6節（利用者判断で採用確定）に基づき、
# unscii フォントファミリーの 8x8 バリアント unscii-8 を、作者 viznut 本人の
# 公開リポジトリ https://github.com/viznut/unscii から取得する。
#
# tools/setup_harness.sh と同じ作法にする:
#   - タグ/ブランチではなく**コミットハッシュでピン留め**
#   - 取得後にチェックサム(SHA-256)を検証し、合わなければ止まる
#   - 取得先はこのリポジトリの**外**（既定 ../vendor/unscii/）。
#     unscii-8.hex 自体はこのリポジトリにコミットしない
#     （ライセンスは CC-0/PD だが、「ダウンロード物を置かない」という
#     tools/setup_harness.sh の構成をフォントでも踏襲する。
#     生成に使うのはビルド時であって、リポジトリの中身ではない）
#   - ライセンス条項（README.md にライセンス条項が書かれている）も
#     一緒に取得する
#
# 何を、どこに置くか（このスクリプトの唯一の置き場所の記録）:
#   $VENDOR/unscii-8.hex  — グリフのソース（Unifont互換 .hex 形式）
#   $VENDOR/README.md     — ライセンス条項を含む配布物の README
#
# 使い方: tools/fetch_unscii.sh [取得先ディレクトリ]
#   既定の取得先は ../vendor/unscii（このリポジトリの外）
set -euo pipefail

UPSTREAM_OWNER="viznut"
UPSTREAM_REPO="unscii"
# 2026-08-07 時点の HEAD（commit message: "clarify license"）。
# `curl -s https://api.github.com/repos/viznut/unscii/commits?per_page=1` で確認。
UPSTREAM_COMMIT="257b4dfeb50651510fe8b9cf4f151a148a4490e4"

# 取得したファイルの SHA-256（同じコミットから取得すれば毎回同じ値になる）。
# 2026-08-07 に本スクリプト作成時、上記コミットに対して実際に取得して算出した値。
HEX_SHA256="03094f7fbab7085cf6a6b624cee61e47e71ce5d0c2f308c2f4436afdc17f776c"
README_SHA256="687095d7e32c466192a81c9b52ddeeaf99036fa2bc9ae4f818f1cb8b96096b3c"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="${1:-$(cd "$REPO/.." && pwd)/vendor/unscii}"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }

BASE_URL="https://raw.githubusercontent.com/$UPSTREAM_OWNER/$UPSTREAM_REPO/$UPSTREAM_COMMIT"

say "取得先: $VENDOR"
mkdir -p "$VENDOR"

fetch_one() {
  local relpath="$1" dest="$2"
  echo "  $relpath"
  curl -fsSL -o "$dest" "$BASE_URL/$relpath"
}

say "取得: $UPSTREAM_OWNER/$UPSTREAM_REPO @ $UPSTREAM_COMMIT"
fetch_one "fontfiles/unscii-8.hex" "$VENDOR/unscii-8.hex"
fetch_one "README.md"              "$VENDOR/README.md"

say "チェックサム検証（SHA-256）"
verify() {
  local file="$1" want="$2"
  local got
  got="$(shasum -a 256 "$file" | awk '{print $1}')"
  if [ "$got" != "$want" ]; then
    echo "NG: $file のチェックサムが一致しない" >&2
    echo "    期待: $want" >&2
    echo "    実際: $got" >&2
    exit 1
  fi
  echo "  OK: $(basename "$file") ($got)"
}
verify "$VENDOR/unscii-8.hex" "$HEX_SHA256"
verify "$VENDOR/README.md"    "$README_SHA256"

say "ライセンス条項の所在（README.md 内。原文引用は docs/spec/l2-font.md 4.1節）"
echo "  $VENDOR/README.md の \"Licensing:\" セクション"

say "完了"
echo "  $VENDOR/unscii-8.hex — グリフソース（このリポジトリにはコミットしない）"
echo "  $VENDOR/README.md    — ライセンス条項（同上）"
echo "  生成器の使い方: python3 src/l2_font/make_font_rom.py <出力先> --unscii-hex $VENDOR/unscii-8.hex"
