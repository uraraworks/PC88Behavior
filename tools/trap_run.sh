#!/usr/bin/env bash
# 全域トラップROMを実走させ、リセット直後に何番地が要求されるかを記録する。
#
# --selftest 無しの make_trap_rom.py が作る「全域 0x00 埋め + trap.map で
# 全域トラップ」の ROM を、stop / ret 両モードで走らせる。
#
# 公式 ROM は要らない（合成ROMのみ使う）。tools/measure.sh と違い
# PC88_REF_ROM_DIR を要求しないのはそのため。
#
# 使い方: tools/trap_run.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
OUTDIR="$REPO/measurements"
WORK="${TMPDIR:-/tmp}/pc88h-trap-run.$$"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || { echo "コアが無い。tools/setup_harness.sh を実行すること" >&2; exit 1; }
[ -x "$FRONTEND" ] || make -s -C "$REPO/tools/harness/frontend"

mkdir -p "$OUTDIR" "$WORK/rom"

say "全域トラップROM（自作の埋め草バイト、公式ROM不使用）を生成"
python3 "$REPO/tools/harness/make_trap_rom.py" "$WORK/rom"

run_one() {
  local mode="$1" name="$2"
  local out="$OUTDIR/$name.txt"
  say "実走: mode=$mode → $name.txt"
  # RET モードは SP 未初期化のまま RET する可能性があり、暴走した結果が
  # 出ることも正直に記録する（docs/notes/m2-trap-rom.md に書く）。
  # 暴走を止めるため --frames は短めに、--trap-stop-after で
  # 「新しい番地が出続ける限りは見る」ようにする。
  "$FRONTEND" \
    --core "$CORE" \
    --rom-dir "$WORK/rom" \
    --frames 60 \
    --out "$out" \
    --trap-map "$WORK/rom/trap.map" \
    --trap-mode "$mode" \
    --trap-stop-after 64 \
    || true   # 検査(--expect-*)は付けていないので終了コードは常に0のはずだが、念のため

  # 個人環境の絶対パスを残さない。
  if [ -f "$out" ]; then
    tmp="$out.tmp"
    sed -e "s|$(cd "$REPO/.." && pwd)|\$WORKDIR|g" \
        -e "s|$HOME|~|g" "$out" > "$tmp" && mv "$tmp" "$out"
  fi
  echo "  書いた: $out"
}

run_one stop t0-trap-all-stop
run_one ret  t0-trap-all-ret

say "完了"
