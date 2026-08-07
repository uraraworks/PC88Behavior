#!/usr/bin/env bash
# tools/fetch_misaki.sh — 半角カナ(0xA1-0xDF)候補の素材「美咲フォント」BDF版を取得する。
#
# 背景: docs/notes/l2-font-misaki-recheck.md（本スクリプトと同じセッションの判定ノート）。
# docs/spec/l2-font.md 4.2節は美咲フォントを「半角(ANK)グリフが4x8」という理由で
# 不採用にしていたが、それは事実誤認だった。美咲フォントはそもそも8x8の日本語
# ビットマップフォントで、必要なのは「全角側のカタカナが8x8で揃っているか」である
# （半角/全角という呼び名ではなく実寸法で見る）。
#
# tools/fetch_unscii.sh と同じ作法にする:
#   - 配布元 https://littlelimit.net/misaki.htm の**BDF配布版**を、
#     **バージョンを固定**して取得する（タグ/コミットではなく配布側の版番号）
#   - 取得後にチェックサム(SHA-256)を検証し、合わなければ止まる
#   - 取得先はこのリポジトリの**外**（既定 ../vendor/misaki/）。
#     フォント本体（BDF）はこのリポジトリにコミットしない
#   - ライセンス条項（アーカイブ同梱の misaki.txt に記載）も一緒に取得する
#     （zip を展開してそのまま置く。misaki.txt が「ライセンスに従う」原本）
#
# 何を、どこに置くか（このスクリプトの唯一の置き場所の記録）:
#   $VENDOR/misaki_bdf_2021-05-05.zip  — 配布アーカイブそのもの（検証対象）
#   $VENDOR/misaki_gothic.bdf          — 美咲ゴシック BDF（グリフのソース）
#   $VENDOR/misaki_mincho.bdf          — 美咲明朝 BDF（今回は未使用。参考として同梱）
#   $VENDOR/misaki_gothic_2nd.bdf      — 美咲ゴシック第2 BDF（今回は未使用）
#   $VENDOR/misaki.txt                 — フォント本体のマニュアル。ライセンス条項を含む
#   $VENDOR/readme.txt                 — BDF版アーカイブのマニュアル
#
# 使い方: tools/fetch_misaki.sh [取得先ディレクトリ]
#   既定の取得先は ../vendor/misaki（このリポジトリの外）
set -euo pipefail

DOWNLOAD_URL="https://littlelimit.net/arc/misaki/misaki_bdf_2021-05-05.zip"
# 配布元 https://littlelimit.net/misaki.htm の「ダウンロード」節に掲載された
# 2021-05-05 版（2026-08-07 確認時点で最新の BDF 配布）。
ARCHIVE_NAME="misaki_bdf_2021-05-05.zip"

# 取得したアーカイブおよび主要ファイルの SHA-256
# （2026-08-07 に本スクリプト作成時、実際に取得して算出した値）。
ARCHIVE_SHA256="a275f173cf5935890f84d3e65d05b1bf73028e4d4bf41cb3de0ef3b5ebe8e217"
MISAKI_TXT_SHA256="82929cc3b34c79b6a67f21fe137c7bb165589c9e34ba1441611e493afd67dfca"
README_TXT_SHA256="429ec2de7a856712203ef80bf86fea49f2f611b9b58b87f7ce7709169bdcf0af"
GOTHIC_BDF_SHA256="28a8745552c844f7c73f11bdf4470225f5e08645a98c5404b2e25bb326a5cabd"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="${1:-$(cd "$REPO/.." && pwd)/vendor/misaki}"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }

say "取得先: $VENDOR"
mkdir -p "$VENDOR"

say "取得: $DOWNLOAD_URL"
curl -fsSL -o "$VENDOR/$ARCHIVE_NAME" "$DOWNLOAD_URL"

say "チェックサム検証（アーカイブ本体、SHA-256）"
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
verify "$VENDOR/$ARCHIVE_NAME" "$ARCHIVE_SHA256"

say "展開"
unzip -o -q "$VENDOR/$ARCHIVE_NAME" -d "$VENDOR"

say "チェックサム検証（展開後の主要ファイル、SHA-256）"
verify "$VENDOR/misaki.txt"        "$MISAKI_TXT_SHA256"
verify "$VENDOR/readme.txt"        "$README_TXT_SHA256"
verify "$VENDOR/misaki_gothic.bdf" "$GOTHIC_BDF_SHA256"

say "ライセンス条項の所在（misaki.txt 内。原文引用は docs/notes/l2-font-misaki-recheck.md）"
echo "  $VENDOR/misaki.txt の「ライセンス」節"
echo "  （readme.txt にも「アーカイブ同梱の misaki.txt の内容に従う」との記載あり）"

say "完了"
echo "  $VENDOR/misaki_gothic.bdf — グリフソース（このリポジトリにはコミットしない）"
echo "  $VENDOR/misaki.txt        — ライセンス条項（同上）"
