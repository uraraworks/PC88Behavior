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
#   4. パッチを適用（スタブ差し替え、フォールバック廃止、ROM探索順の修正）
#   5. ビルド
#
# 削除する 2 ファイルはパッチではなく rm で消す。
# 削除をパッチで表現すると unified diff の中に消したい内容が丸ごと入ってしまい、
# このリポジトリに疑似BIOSのバイト列を持ち込むことになるため。
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

say "逆アセンブラと疑似BIOSを削除"
rm -f "$SRC/src/z80-debug.c"
rm -f "$SRC/src/LIBRETRO/pseudo_bios.h"
# 消えたことを確認してから進む（消し損ねたまま進むと規律が空文になる）
for f in src/z80-debug.c src/LIBRETRO/pseudo_bios.h; do
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
  *retro_q88h_intlog*) echo "  OK: 割り込み受理ログのシンボルあり" ;;
  *) echo "  NG: 割り込み受理ログのシンボルが無い" >&2; exit 1 ;;
esac

say "疎通試験"
# ここまでで「ビルドできた」だけ。フックが末端まで生きているかは別問題なので測る。
"$REPO/tools/harness/selftest.sh"
"$REPO/tools/harness/trap_selftest.sh"
"$REPO/tools/harness/iolog_selftest.sh"
"$REPO/tools/harness/intlog_selftest.sh"

say "完了"
