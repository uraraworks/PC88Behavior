#!/usr/bin/env bash
# tools/stage_disk_by_digest.sh — ダイジェスト(basenameのSHA-256先頭8桁)を
# 渡すと、対応するディスクイメージの「中立な名前の使い捨て複製」を作り、
# その中立パスだけを返すヘルパ。
#
# 位置づけ: docs/notes/m7gg-data-disk-screening.md・
# docs/notes/m7go-write-data-unit-results.md の開示節に記録されたとおり、
# 測定コマンドを組み立てる過程やデバッグ出力で実ファイル名が漏れる事故が
# 2回起きた。原因は個々の不注意ではなく、「q88measure にパスを渡すには
# 実ファイル名を含むパスを扱わざるを得ない」という経路そのものにある。
# このスクリプトは、ダイジェストを受け取った時点で中立名の複製を作り、
# 以降のコマンドが実ファイル名に一切触れずに済むようにする。詳細:
# docs/notes/m7gp-disk-name-leak-path-closed.md。
#
# ダイジェストの計算は再実装しない。tools/lib_screen_boot_disks.sh の
# digest_basename（basename文字列のSHA-256先頭8桁）をそのまま source して使う。
#
# 使い方:
#   tools/stage_disk_by_digest.sh <ダイジェスト8桁> [出力ディレクトリ]
#
# 引数:
#   ダイジェスト8桁    docs/notes/m7gd 等が使う basename の SHA-256 先頭8桁
#                       （小文字16進、8文字）
#   出力ディレクトリ   省略時は $TMPDIR 配下（無ければ /tmp 配下）に
#                       このスクリプトが作る使い捨てディレクトリ
#
# 探索対象:
#   PC88_REF_DISK_DIR（未設定なら $REPO/private/disk。tools/measure.sh の
#   フォールバック規約と同じ）配下の *.d88 / *.D88（大文字小文字を無視）。
#
# 出力:
#   標準出力へ、複製先の中立パス（<出力ディレクトリ>/<ダイジェスト>.d88）
#   1行だけを出す。それ以外は一切標準出力に出さない。
#
# 名前を出さないことの徹底:
#   - 一致0件・一致2件以上はエラー終了する（無言で1本を選ばない）。
#     エラーメッセージにも実ファイル名を書かず、件数とダイジェストのみで表す。
#   - set -x は使わない。候補一覧をデバッグ表示しない。
#   - 元ファイルは読むだけで、書き込まない（複製先だけに書く）。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_screen_boot_disks.sh"

usage() {
  cat <<'USAGE' >&2
使い方: tools/stage_disk_by_digest.sh <ダイジェスト8桁> [出力ディレクトリ]

  <ダイジェスト8桁>    basename の SHA-256 先頭8桁（小文字16進、8文字）。
                        docs/notes/m7gd-boot-disk-screening.md 等が出す値。
  [出力ディレクトリ]   省略時は使い捨ての一時ディレクトリを新規に作る。

PC88_REF_DISK_DIR（未設定なら private/disk）配下の *.d88 / *.D88 から、
basename のダイジェストが一致する1本を探し、<出力ディレクトリ>/<ダイジェスト>.d88
という中立な名前で複製する。標準出力にはその複製先パス1行だけを出す。

例:
  path="$(tools/stage_disk_by_digest.sh 3c218749)"
  q88measure ... --disk "$path" ...
USAGE
}

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  usage
  exit 2
fi

DIGEST="$1"
OUTDIR="${2:-}"

# ダイジェストの形式検査（小文字16進8文字）。ここで弾いておかないと、
# 後段のファイル名生成にそのまま使われてしまう。
case "$DIGEST" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *)
    echo "エラー: ダイジェストの形式が不正（小文字16進8文字ではない）" >&2
    exit 2
    ;;
esac

# --- ディスク置き場の決定（tools/measure.sh・tools/screen_boot_disks.sh と同じ規約）
if [ -z "${PC88_REF_DISK_DIR:-}" ] && [ -d "$REPO/private/disk" ]; then
  PC88_REF_DISK_DIR="$REPO/private/disk"
fi
if [ -z "${PC88_REF_DISK_DIR:-}" ]; then
  echo "エラー: PC88_REF_DISK_DIR が未設定で、既定位置 $REPO/private/disk も無い。" >&2
  echo "        export PC88_REF_DISK_DIR=/path/to/disk などで指定すること。" >&2
  exit 1
fi
if [ ! -d "$PC88_REF_DISK_DIR" ]; then
  echo "エラー: ディスク置き場がディレクトリではない（環境変数の値を確認すること）" >&2
  exit 1
fi

# --- 出力ディレクトリの決定 -----------------------------------------------
if [ -z "$OUTDIR" ]; then
  base="${TMPDIR:-/tmp}"
  OUTDIR="$(mktemp -d "${base%/}/pc88_stage_disk.XXXXXX")"
else
  mkdir -p "$OUTDIR"
fi

# --- 一致するディスクを1本だけ探す（basenameのダイジェストで照合、名前は出さない）
MATCH_COUNT=0
MATCH_NAME=""
while IFS= read -r name; do
  [ -n "$name" ] || continue
  d="$(digest_basename "$name")"
  if [ "$d" = "$DIGEST" ]; then
    MATCH_COUNT=$((MATCH_COUNT + 1))
    MATCH_NAME="$name"
  fi
done < <(list_disk_basenames "$PC88_REF_DISK_DIR")

if [ "$MATCH_COUNT" -eq 0 ]; then
  echo "エラー: ダイジェスト ${DIGEST} に一致するディスクが0件だった。" >&2
  exit 1
fi
if [ "$MATCH_COUNT" -gt 1 ]; then
  echo "エラー: ダイジェスト ${DIGEST} に一致するディスクが${MATCH_COUNT}件あり、1本に絞れない。" >&2
  exit 1
fi

# --- 中立名で複製する（元ファイルは読むだけ、書き込まない） ----------------
DEST="$OUTDIR/${DIGEST}.d88"
cp -- "$PC88_REF_DISK_DIR/$MATCH_NAME" "$DEST"

# 標準出力へは複製先の中立パス1行だけ。
printf '%s\n' "$DEST"
