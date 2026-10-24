#!/usr/bin/env bash
# tools/register_game.sh — ユーザーが自分の端末で実行する登録用。
# ディスクの中身のSHA-256先頭16桁を計算し、PC88_GAME_DIR/games.tsv に1行追加する。
#
# 使い方: tools/register_game.sh <識別子> <ディスク番号> <ディスクのパス>
# 標準出力は「<識別子>-<番号> を登録した（ハッシュ先頭16桁）」だけ。パス・ファイル名は出さない。
# パスは PC88_GAME_DIR 配下でなければエラー。同じ識別子・番号が既にあればエラー(上書きしない)。
# 対応表(tools/stage_game.sh 参照)に実ファイル名は書かない。set -x 禁止。
set -uo pipefail

die() { echo "エラー: $1" >&2; exit "${2:-1}"; }
if [ $# -ne 3 ]; then
  echo "使い方: tools/register_game.sh <識別子> <ディスク番号> <ディスクのパス>" >&2
  exit 2
fi
ID="$1"; NUM="$2"; DISK="$3"

case "$ID" in
  G[1-9]|G[1-9][0-9]*) ;;
  *) die "識別子の形式が不正(G1, G2 ... の形ではない)" 2 ;;
esac
case "${ID#G}" in *[!0-9]*) die "識別子の形式が不正(G1, G2 ... の形ではない)" 2 ;; esac
case "$NUM" in ''|*[!0-9]*|0*) die "ディスク番号が不正(1始まりの整数)" 2 ;; esac

[ -n "${PC88_GAME_DIR:-}" ] || die "PC88_GAME_DIR が未設定"
[ -d "$PC88_GAME_DIR" ] || die "PC88_GAME_DIR がディレクトリではない"
[ -f "$DISK" ] || die "指定のディスクがファイルとして存在しない"

BASEDIR="$(cd "$PC88_GAME_DIR" 2>/dev/null && pwd -P)" || die "PC88_GAME_DIR を解決できない"
DDIR="$(cd "$(dirname -- "$DISK")" 2>/dev/null && pwd -P)" || die "ディスクの場所を解決できない"
case "$DDIR/" in
  "$BASEDIR"/*) ;;
  *) die "ディスクが PC88_GAME_DIR 配下ではない" ;;
esac

TSV="$PC88_GAME_DIR/games.tsv"
if [ -f "$TSV" ] && awk -F'\t' -v i="$ID" -v n="$NUM" '$0!~/^#/ && $1==i && $2==n{f=1} END{exit !f}' "$TSV"; then
  die "${ID}-${NUM} は既に登録されている(上書きしない)"
fi

H="$(shasum -a 256 -- "$DISK" 2>/dev/null | cut -c1-16)"
case "$H" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) die "ハッシュを計算できない" ;;
esac

printf '%s\t%s\t%s\n' "$ID" "$NUM" "$H" >> "$TSV" || die "対応表に書き込めない"
echo "${ID}-${NUM} を登録した（${H}）"
