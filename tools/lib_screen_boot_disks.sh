# tools/lib_screen_boot_disks.sh — tools/screen_boot_disks.sh が使う関数群。
#
# 単体で実行されるスクリプトではなく、source される「関数の置き場」だけに
# する（tools/lib_l3_measure.sh と同じ流儀。トップレベルで副作用を起こさない）。
# こう切り出す理由は、tools/screen_boot_disks_selftest.sh から公式ROM無しで
# 個々の関数（列挙・ダイジェスト計算・判定）を直接検査できるようにするため。
#
# 使い方:
#   REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
#   source "$REPO/tools/lib_screen_boot_disks.sh"

# -----------------------------------------------------------------------
# $1 = ディスク置き場のディレクトリ
#
# *.d88 / *.D88 を大文字小文字を無視して列挙し、basename だけを
# LC_ALL=C でソートして重複なく返す（大文字小文字を区別しないファイル
# システムで同じファイルを2回数えないよう、find の結果を basename の
# 集合として一意化してからソートする）。
# -----------------------------------------------------------------------
list_disk_basenames() {
  local dir="$1"
  find "$dir" -maxdepth 1 -type f \( -iname '*.d88' \) -print0 2>/dev/null \
    | xargs -0 -n1 basename 2>/dev/null \
    | LC_ALL=C sort -u
}

# -----------------------------------------------------------------------
# $1 = basename（パスを含まない）
#
# basename 文字列そのものの SHA-256 先頭8桁を返す。ファイルの中身では
# なく「ファイル名という文字列」のハッシュである点に注意
# （中身のハッシュを取るとディスクイメージのバイト列由来の情報になり、
# CLAUDE.md 禁止事項4・5の対象になりかねないため、意図的に名前だけを
# ハッシュする）。
# -----------------------------------------------------------------------
digest_basename() {
  python3 -c 'import sys, hashlib; print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest()[:8])' "$1"
}

# -----------------------------------------------------------------------
# $1 = REPO のルート（tools/hash_io_stream.py を探すため）
# $2 = iolog のパス
#
# tools/conform_l3.sh の count_sub_fc と同じ器材(tools/hash_io_stream.py)・
# 同じ引数(--cpu sub --port FC --kind OUT)・同じ「抽出0件はエラーになるので
# 0として扱う」規約で数える。二重実装(値の抽出ロジックそのものの再実装)は
# しない。値は一切標準出力に出さない設計の hash_io_stream.py をそのまま
# 呼ぶだけ。
# -----------------------------------------------------------------------
count_sub_fc() {
  local repo="$1" iolog="$2"
  local hash_tool="$repo/tools/hash_io_stream.py"
  local out
  if out="$(python3 "$hash_tool" "$iolog" --cpu sub --port FC --kind OUT 2>/dev/null)"; then
    printf '%s\n' "$out" | awk -F'\t' '$1=="count"{print $2}'
  else
    echo 0
  fi
}

# -----------------------------------------------------------------------
# 判定基準（docs/notes/m6-sub-invariant.md 第2版の実測）:
#   diskA（N88-BASIC）起動: sub OUT $FC が多数（実測5635件）→ L3サービスに入る
#   diskB（市販ソフト）起動: sub OUT $FC が0件（600/1800/3600フレームいずれも）
#     → L3サービスに入らない
#
# 引数に渡された各フレーム数での件数のうち、1つでも0より大きければ
# 「L3に入る」と判定する（1つのフレーム数の値だけに判定を依存させない）。
# -----------------------------------------------------------------------
classify_l3_entry() {
  local c
  for c in "$@"; do
    if [ -n "$c" ] && [ "$c" -gt 0 ] 2>/dev/null; then
      echo "L3に入る"
      return 0
    fi
  done
  echo "入らない"
}
