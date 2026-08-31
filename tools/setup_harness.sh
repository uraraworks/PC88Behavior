#!/usr/bin/env bash
# 計測ハーネスの土台を用意する。
#
# 上流 QUASI88-libretro を固定コミットで取得し、クリーンルーム用の改変を当てる。
# 第三者コードをこのリポジトリに置かずに済むよう、
# 「ピン留めコミット + パッチ列」という形にしてある。誰が実行しても同じ物ができる。
#
# ここでやること:
#   1. 上流をピン留めコミットで取得
#   2. 逆アセンブラ (src/z80-debug.c) を削除
#      → 「使わない」ではなく「持っていない」状態にする
#   3. 疑似BIOS (src/LIBRETRO/pseudo_bios.h) を削除
#      → 権利関係が不明瞭（docs/notes/m1-quasi88-survey.md 4.1/4.2）。
#        加えて、これが残っていると公式ROMの読み込みに失敗したとき
#        黙って別物が動き、測定対象がすり替わる
#   4. 内蔵フォント (src/font.h) を削除
#      → built_in_font_ANK/ANH/graph の出所が不明（docs/spec/l2-font.md 3節）。
#        これが残っていると FONT.ROM の読み込みに成功していても中身が
#        黙って differs 差し替わる（同節の表、7経路）
#   5. パッチを適用（スタブ差し替え、フォールバック廃止、ROM探索順の修正、
#      フォント供給源の可視化と font.h 削除に伴う参照修正）
#   6. ビルド
#
# 削除する 3 ファイルはパッチではなく rm で消す。
# 削除をパッチで表現すると unified diff の中に消したい内容が丸ごと入ってしまい、
# このリポジトリに疑似BIOS・内蔵フォントのバイト列を持ち込むことになるため。
#
# 使い方: tools/setup_harness.sh [作業ディレクトリ]
#   既定の作業ディレクトリは ../vendor（このリポジトリの外）
set -euo pipefail

UPSTREAM_URL="https://github.com/libretro/quasi88-libretro.git"
UPSTREAM_COMMIT="b5a0e044a914c9a6b8d7b2dd2ddd152f93d35687"   # 2026-07-22

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="${1:-$(cd "$REPO/.." && pwd)/vendor}"
SRC="$VENDOR/quasi88-libretro"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }

say "上流を取得: $UPSTREAM_COMMIT"
mkdir -p "$VENDOR"
if [ ! -d "$SRC/.git" ]; then
  git clone "$UPSTREAM_URL" "$SRC"
fi
git -C "$SRC" fetch --all --quiet
git -C "$SRC" checkout --quiet --force "$UPSTREAM_COMMIT"
git -C "$SRC" clean -qfdx

say "逆アセンブラ・疑似BIOS・内蔵フォントを削除"
rm -f "$SRC/src/z80-debug.c"
rm -f "$SRC/src/LIBRETRO/pseudo_bios.h"
rm -f "$SRC/src/font.h"
# 消えたことを確認してから進む（消し損ねたまま進むと規律が空文になる）
for f in src/z80-debug.c src/LIBRETRO/pseudo_bios.h src/font.h; do
  if [ -e "$SRC/$f" ]; then echo "削除できていない: $f" >&2; exit 1; fi
done

say "自前コードをコアツリーへ配置"
# 私たちが書いたファイルはこのリポジトリで管理し、コピーで持ち込む。
# パッチに埋め込むと、自分のコードが diff の中でしか読めなくなる。
for f in "$REPO"/tools/harness/core/*; do
  echo "  $(basename "$f")"
  cp "$f" "$SRC/src/"
done

say "パッチを適用"
for p in "$REPO"/tools/patches/*.patch; do
  echo "  $(basename "$p")"
  git -C "$SRC" apply --whitespace=nowarn "$p"
done

say "ビルド"
# macOS では platform の自動判定が壊れている。
# Makefile が uname -a に 'win' を含むかで win32 判定するが、"Darwin" が一致する。
PLATFORM_ARG=""
case "$(uname -s)" in
  Darwin) PLATFORM_ARG="platform=osx" ;;
esac
make -C "$SRC" $PLATFORM_ARG -j"$(sysctl -n hw.ncpu 2>/dev/null || nproc)"

say "検証"
LIB="$(ls "$SRC"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$LIB" ]; then echo "成果物が見つからない" >&2; exit 1; fi
echo "  成果物: $LIB"

# シンボル表は一度だけ変数に取る。
# `nm | grep -q` は set -o pipefail と噛み合わない: grep -q が最初の一致で
# 終了すると nm が SIGPIPE で死に、パイプライン全体が失敗扱いになる。
# 「シンボルが有るときだけ検査が失敗する」という反転した挙動になり、
# しかも無い側の検査は素通りするので気づきにくい。
SYMS="$(nm "$LIB" 2>/dev/null || true)"

case "$SYMS" in
  *pbios*) echo "  NG: 疑似BIOSのシンボルが残っている" >&2; exit 1 ;;
  *)       echo "  OK: 疑似BIOSのシンボルなし" ;;
esac
echo "  OK: 逆アセンブラのソースは存在しない（スタブのみ）"
case "$SYMS" in
  *retro_q88h_trace*) echo "  OK: 計測フックのシンボルあり" ;;
  *) echo "  NG: 計測フックのシンボルが無い" >&2; exit 1 ;;
esac
case "$SYMS" in
  *retro_q88h_iolog*) echo "  OK: 順序付きI/O記録のシンボルあり" ;;
  *) echo "  NG: 順序付きI/O記録のシンボルが無い" >&2; exit 1 ;;
esac
case "$SYMS" in
  *retro_q88h_exchange_intervention*) echo "  OK: 交換run介入のシンボルあり" ;;
  *) echo "  NG: 交換run介入のシンボルが無い" >&2; exit 1 ;;
esac
case "$SYMS" in
  *retro_q88h_sub_interrupt_intervention*) echo "  OK: sub割り込み介入のシンボルあり" ;;
  *) echo "  NG: sub割り込み介入のシンボルが無い" >&2; exit 1 ;;
esac
case "$SYMS" in
  *retro_q88h_intlog*) echo "  OK: 割り込み受理ログのシンボルあり" ;;
  *) echo "  NG: 割り込み受理ログのシンボルが無い" >&2; exit 1 ;;
esac
case "$SYMS" in
  *retro_q88h_fontsrc*) echo "  OK: フォント供給源記録のシンボルあり" ;;
  *) echo "  NG: フォント供給源記録のシンボルが無い" >&2; exit 1 ;;
esac
# built_in_font_* は font.h 削除に伴い、コード側の参照も消してある。
# static 配列なのでそもそも外部シンボルとしては出ないが、
# 「削除した」ことの検証は「使う側のコードから消えている」ことで行う
# （nm でのシンボル検査は疑似BIOS/逆アセンブラのような外部公開シンボルの
# あるものにしか使えないため）。
if [ -e "$SRC/src/font.h" ]; then
  echo "  NG: src/font.h が消えていない" >&2; exit 1
fi
echo "  OK: src/font.h は存在しない"
# コード中で「削除した理由」を説明するコメントには built_in_font という
# 単語そのものが出てくる（このファイルもそう）。それ自体は問題ないので、
# 実際に配列として使われている形（`built_in_font_XXX[`）だけを検査する。
if grep -rqE 'built_in_font_(ANK|ANH|graph)\[' "$SRC/src/memory.c" "$SRC/src/LIBRETRO/libretro.c"; then
  echo "  NG: built_in_font_* への実参照がまだ残っている" >&2
  grep -nE 'built_in_font_(ANK|ANH|graph)\[' "$SRC/src/memory.c" "$SRC/src/LIBRETRO/libretro.c" >&2
  exit 1
fi
echo "  OK: built_in_font_* への実参照は残っていない（コメントでの言及のみ）"

say "疎通試験"
# ここまでで「ビルドできた」だけ。フックが末端まで生きているかは別問題なので測る。
"$REPO/tools/harness/selftest.sh"
"$REPO/tools/harness/disk2_selftest.sh"
"$REPO/tools/harness/trap_selftest.sh"
"$REPO/tools/harness/iolog_selftest.sh"
"$REPO/tools/harness/intlog_selftest.sh"
"$REPO/tools/harness/fontsrc_selftest.sh"

say "完了"
