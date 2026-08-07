#!/usr/bin/env bash
# クリーンルーム防御が実際に効いている状態かを検査する。
#
# 規律は「書いてある」だけでは効かない。以下を機械的に確かめる:
#   1. private/ が git から遮断されている（実際にダミーを置いて確認）
#   2. リポジトリの外に置いた ROM 系ファイルも遮断される
#   3. 追跡ファイルに ROM 由来らしきバイナリが混入していない
#   4. permission 設定が実効位置（cwd 側）から見えている
#   5. 実効側と実体（このリポジトリ）が同じ内容である
#
# 使い方: tools/check_cleanroom.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

fail=0
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()   { printf '  \033[31mNG\033[0m   %s\n' "$1"; fail=$((fail+1)); }
info() { printf '  --   %s\n' "$1"; }

echo "clean-room check: $REPO"

# --- 1. private/ の遮断 -------------------------------------------------
mkdir -p private
probe="private/.__probe__"
: > "$probe"
if git check-ignore -q "$probe"; then ok "private/ は git から遮断されている"
else ng "private/ が git に見えている（.gitignore を確認）"; fi
rm -f "$probe"

# --- 2. private/ の外に置いた ROM 系も遮断されるか ----------------------
stray=".__probe__.rom"
: > "$stray"
if git check-ignore -q "$stray"; then ok "リポジトリ直下の *.rom も遮断される"
else ng "*.rom が遮断されていない"; fi
rm -f "$stray"

# --- 3. 追跡ファイルへのバイナリ混入 ------------------------------------
# ROM 由来のバイト列は必ずバイナリになる。テキストしか追跡していないはず。
# 空ファイル(.gitkeep 等)は対象外。NUL バイトを含むものをバイナリとみなす。
binaries=""
while IFS= read -r f; do
  [ -s "$f" ] || continue
  # シェル文字列に NUL は入らないので grep のパターンには書けない。
  # NUL を除去した長さが元と違えば NUL を含む = バイナリ。
  if [ "$(LC_ALL=C tr -d '\000' < "$f" | wc -c)" -ne "$(wc -c < "$f")" ]; then
    binaries="$binaries $f"
  fi
done < <(git ls-files)
if [ -z "$binaries" ]; then ok "追跡ファイルにバイナリの混入なし"
else ng "バイナリが追跡されている:"; printf '       %s\n' $binaries; fi

# --- 4/5. permission 設定の実体と実効位置 -------------------------------
src="$REPO/.claude/settings.json"
eff="$(cd "$REPO/.." && pwd)/.claude/settings.json"   # cwd 側 = PC88/.claude/

if [ -f "$src" ]; then ok "permission 設定の実体がある（公開repo側）"
else ng "permission 設定の実体が無い: $src"; fi

if [ -e "$eff" ]; then
  if [ -L "$eff" ]; then info "実効側は symlink → $(readlink "$eff")"; fi
  if cmp -s "$src" "$eff"; then ok "実効側 (cwd) と実体の内容が一致している"
  else ng "実効側と実体の内容がずれている: $eff"; fi
else
  ng "実効側に permission 設定が無い: $eff（cwd が PC88 だと実体だけでは読まれない）"
fi

# --- 6. 計測ハーネスが禁止された能力を持っていないか ----------------------
# 「使わない」ではなく「持っていない」を検査する。
harness="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
if [ -d "$harness" ]; then
  for f in src/z80-debug.c src/LIBRETRO/pseudo_bios.h; do
    if [ -e "$harness/$f" ]; then ng "ハーネスに $f が存在する（setup_harness.sh が消すはず）"
    else ok "ハーネスに $f は存在しない"; fi
  done
  lib="$(ls "$harness"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
  if [ -n "$lib" ]; then
    # `nm | grep -q` は使わない。pipefail 下では grep -q の早期終了が
    # nm を SIGPIPE で殺し、判定が反転する（setup_harness.sh の注記参照）。
    syms="$(nm "$lib" 2>/dev/null || true)"
    case "$syms" in
      *pbios*) ng "ビルド成果物に疑似BIOSのシンボルがある" ;;
      *)       ok "ビルド成果物に疑似BIOSのシンボルなし" ;;
    esac
    case "$syms" in
      *retro_q88h_trace*) ok "ビルド成果物に計測フックのシンボルあり" ;;
      *)                  ng "ビルド成果物に計測フックのシンボルが無い" ;;
    esac
  fi
else
  info "ハーネス未取得のためスキップ（tools/setup_harness.sh）"
fi

echo
if [ "$fail" -eq 0 ]; then echo "全項目 OK"; else echo "$fail 件 NG"; fi
exit "$fail"
