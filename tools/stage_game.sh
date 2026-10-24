#!/usr/bin/env bash
# tools/stage_game.sh — ゲーム識別子(G1, G2 ...)を渡すと、そのゲームの全ディスクの
# 「中立な名前の使い捨て複製」を作り、中立パスだけをディスク番号順に返すヘルパ。
#
# 位置づけ: docs/notes/goal-b-policy-2026-10-24.md 第4節・第7節の3、
# docs/notes/b1-game-staging-helper.md。実ファイル名・タイトル名が端末に現れうる
# 経路をここ1点に閉じる(前例: tools/stage_disk_by_digest.sh、m7gp)。
#
# 使い方: tools/stage_game.sh <識別子> [出力ディレクトリ]
#   識別子           ^G[1-9][0-9]*$
#   出力ディレクトリ 省略時は使い捨ての一時ディレクトリを新規に作る
#
# 置き場: 環境変数 PC88_GAME_DIR(未設定はエラー。既定パスは持たない)。
#   直下に対応表 games.tsv: 識別子<TAB>ディスク番号(1始まり)<TAB>中身のSHA-256先頭16桁
#   (# 行はコメント)。対応表に実ファイル名は書かない。名前でなく中身のハッシュで引く。
#
# 出力: 標準出力は <出力ディレクトリ>/<識別子>-<番号>.d88 をディスク番号順に1行1本。
# 名前を出さないために: エラー文は識別子・番号・件数・ハッシュのみ。set -x 禁止、
# 候補一覧のデバッグ表示禁止。外部コマンドのstderrは捨てる(ファイル名が混ざりうる)。
# 元ファイルは読むだけ。
set -uo pipefail

usage() {
  echo "使い方: tools/stage_game.sh <識別子 G1 など> [出力ディレクトリ]" >&2
}
die() { echo "エラー: $1" >&2; exit "${2:-1}"; }

if [ $# -lt 1 ] || [ $# -gt 2 ]; then usage; exit 2; fi
ID="$1"
OUTDIR="${2:-}"

case "$ID" in
  G[1-9]|G[1-9][0-9]*) ;;
  *) die "識別子の形式が不正(G1, G2 ... の形ではない)" 2 ;;
esac
case "${ID#G}" in
  *[!0-9]*) die "識別子の形式が不正(G1, G2 ... の形ではない)" 2 ;;
esac

[ -n "${PC88_GAME_DIR:-}" ] || die "PC88_GAME_DIR が未設定"
[ -d "$PC88_GAME_DIR" ] || die "PC88_GAME_DIR がディレクトリではない"
TSV="$PC88_GAME_DIR/games.tsv"
[ -f "$TSV" ] || die "対応表 games.tsv が無い"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88_stage_game_work.XXXXXX")" || die "作業領域を作れない"
trap 'rm -rf "$WORK"' EXIT

# --- 対応表から該当識別子の行を取り出す(番号<TAB>ハッシュ) ---
WANT="$WORK/want.txt"; : > "$WANT"
LN=0
while IFS= read -r line || [ -n "$line" ]; do
  LN=$((LN + 1))
  case "$line" in ''|'#'*) continue ;; esac
  IFS=$'\t' read -r f_id f_num f_hash f_rest <<<"$line"
  if [ -z "$f_id" ] || [ -z "$f_num" ] || [ -z "$f_hash" ] || [ -n "${f_rest:-}" ]; then
    die "対応表 ${LN} 行目の書式が不正"
  fi
  [ "$f_id" = "$ID" ] || continue
  case "$f_num" in ''|*[!0-9]*|0*) die "対応表 ${LN} 行目のディスク番号が不正" ;; esac
  case "$f_hash" in
    [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
    *) die "対応表 ${LN} 行目のハッシュ形式が不正" ;;
  esac
  printf '%s\t%s\n' "$f_num" "$f_hash" >> "$WANT"
done < "$TSV"

N="$(wc -l < "$WANT" | tr -d ' ')"
[ "$N" -gt 0 ] || die "識別子 ${ID} が対応表に無い"
SORTED="$WORK/want_sorted.txt"
LC_ALL=C sort -n -k1,1 "$WANT" > "$SORTED"
i=0
while IFS=$'\t' read -r num hash; do
  i=$((i + 1))
  if [ "$num" -ne "$i" ]; then
    if [ "$num" -lt "$i" ]; then die "${ID}: ディスク番号 ${num} が重複している"; fi
    die "${ID}: ディスク番号 ${i} が欠番"
  fi
done < "$SORTED"

# --- PC88_GAME_DIR 直下の d88 を中身のSHA-256先頭16桁で索引化(名前は出さない) ---
INDEX="$WORK/index.txt"; : > "$INDEX"
while IFS= read -r -d '' p; do
  h="$(shasum -a 256 -- "$p" 2>/dev/null | cut -c1-16)"
  [ -n "$h" ] || continue
  printf '%s\t%s\n' "$h" "$p" >> "$INDEX"
done < <(find "$PC88_GAME_DIR" -maxdepth 1 -type f -iname '*.d88' -print0 2>/dev/null)

# --- 全ディスクを解決(複製は全部解決できてから) ---
RES="$WORK/resolved.txt"; : > "$RES"
while IFS=$'\t' read -r num hash; do
  cnt="$(awk -F'\t' -v h="$hash" '$1==h{c++} END{print c+0}' "$INDEX")"
  if [ "$cnt" -ne 1 ]; then
    die "${ID}-${num}: ハッシュ ${hash} に一致するディスクが${cnt}件(1件のみ可)"
  fi
  src="$(awk -F'\t' -v h="$hash" '$1==h{print substr($0, index($0, "\t")+1)}' "$INDEX")"
  printf '%s\t%s\n' "$num" "$src" >> "$RES"
done < "$SORTED"

# --- 出力先 ---
if [ -z "$OUTDIR" ]; then
  OUTDIR="$(mktemp -d "${TMPDIR:-/tmp}/pc88_stage_game.XXXXXX")" || die "出力先を作れない"
else
  mkdir -p -- "$OUTDIR" 2>/dev/null || die "出力ディレクトリを作れない"
fi

while IFS=$'\t' read -r num src; do
  dest="$OUTDIR/${ID}-${num}.d88"
  cp -- "$src" "$dest" 2>/dev/null || die "${ID}-${num}: 複製に失敗した"
  printf '%s\n' "$dest"
done < "$RES"
