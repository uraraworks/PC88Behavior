#!/usr/bin/env bash
# tools/vsync_regcheck_selftest.sh — VSYNCハンドラのレジスタ非退避の
# 潜在不具合の再現・修正の自己検査(陰性対照つき)。**公式ROMは要らない**。
#
# 経緯: docs/spec/ext-rom-bank.md の実装(EXT_BANK_LOOP_TEST、割り込みを
# 有効にしたまま連続呼び出し)で、BC/DEに置いた作業値が実際に壊れる
# 不具合を踏んだ。原因はext_bank固有ではなく、VSYNCハンドラ
# (src/l1_ipl/make_ipl_rom.py sub_vsync_handler、およびそこから呼ばれる
# src/l3_main/keyboard.asm L3_VSYNC_HOOK以下・KEYSCAN)がAF/BC/DE/HL/
# IX/IYを一切PUSH/POPしていなかったことによる潜在不具合だった
# (裏レジスタEXX/EX AF,AF'はこのリポジトリのどのコードも使っていない
# のでgrepで確認済み・対象外)。この検査は、その潜在不具合そのものを
# ext_bankを介さず直接再現・確認する。
#
# 検査:
#   1. --enable-vsync-regcheckビルド(修正後の通常ビルド、PUSH/POP入り):
#      A/BC/DE/HL/IX/IYへ目印値を積みHALTで実際に1回VSYNCを受理させても
#      全レジスタが保たれること(VSYNC_REGCHECK_RESULT=1)。
#   2. 陰性対照(--enable-vsync-regcheck --inject-vsync-no-save-fault):
#      VSYNC_HANDLER冒頭・末尾のPUSH/POPをNOPへ置き換えた(=修正前を
#      再現した)ビルドで、同じ検査が実際に不一致を検出すること
#      (VSYNC_REGCHECK_RESULT=0)。
#   3. 割り込みを有効にしたまま長いBASIC処理(tools/conform_l4.sh・
#      tools/l3_main_selftest.sh・tools/l3_screen_editor_selftest.sh)を
#      通常ビルド(修正後)で回し、前後で結果が変わらないこと。
#
# 使い方: tools/vsync_regcheck_selftest.sh

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
BUILD="$REPO/src/build_main_rom.py"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
fail() { echo "NG: $1" >&2; FAILED=1; }

FAILED=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi
make -s -C "$REPO/tools/harness/frontend" || exit 1

read_regcheck() {
  # $1=rom-dir -> 標準出力に "DONE RESULT"（16進2桁ずつ）
  local romdir="$1" memlog="$WORK/regcheck.memlog.txt"
  "$FRONTEND" --core "$CORE" --rom-dir "$romdir" --frames 200 \
      --mem-write-log "$memlog" --mem-write-range E8D0-E8DD \
      >"$WORK/regcheck.stdout.txt" 2>"$WORK/regcheck.stderr.txt"
  if [ $? -ne 0 ]; then
    fail "q88measure(vsync regcheck)が失敗"; cat "$WORK/regcheck.stderr.txt" >&2; echo "FF FF"; return
  fi
  python3 - "$memlog" << 'PYEOF'
import re, sys
last = {}
for line in open(sys.argv[1]):
    m = re.match(r'\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})', line)
    if m:
        last[m.group(4).upper()] = m.group(5)
print(last.get("E8D0", "FF"), last.get("E8D1", "FF"))
PYEOF
}

# -----------------------------------------------------------------------
say "1. 修正後ビルド（--enable-vsync-regcheck）: 割り込みを1回受理してもレジスタが保たれること"
FIXED_ROM="$WORK/rom_fixed"
if ! python3 "$BUILD" "$FIXED_ROM" --enable-vsync-regcheck >"$WORK/build_fixed.txt" 2>&1; then
  fail "build_main_rom.py(修正後)が失敗"; cat "$WORK/build_fixed.txt" >&2
fi
read -r DONE1 RESULT1 <<< "$(read_regcheck "$FIXED_ROM")"
echo "DONE=$DONE1 RESULT=$RESULT1"
if [ "$DONE1" = "01" ] && [ "$RESULT1" = "01" ]; then
  echo "OK: 修正後ビルドはA/BC/DE/HL/IX/IYすべて割り込み前後で一致した"
else
  fail "修正後ビルドでレジスタ不一致が起きた(DONE=$DONE1 RESULT=$RESULT1、修正が効いていない可能性)"
fi

# -----------------------------------------------------------------------
say "2. 陰性対照（--inject-vsync-no-save-fault）: PUSH/POPを外すと同じ検査が不一致を検出すること"
FAULT_ROM="$WORK/rom_fault"
if ! python3 "$BUILD" "$FAULT_ROM" --enable-vsync-regcheck --inject-vsync-no-save-fault >"$WORK/build_fault.txt" 2>&1; then
  fail "build_main_rom.py(陰性対照)が失敗"; cat "$WORK/build_fault.txt" >&2
fi
read -r DONE2 RESULT2 <<< "$(read_regcheck "$FAULT_ROM")"
echo "DONE=$DONE2 RESULT=$RESULT2"
if [ "$DONE2" = "01" ] && [ "$RESULT2" = "00" ]; then
  echo "OK(検出力): PUSH/POPを外すと実際にレジスタ不一致を検出できた(修正前の再現)"
else
  fail "陰性対照で不一致を検出できなかった(DONE=$DONE2 RESULT=$RESULT2、検査に検出力が無い)"
fi

# -----------------------------------------------------------------------
say "3. 通常ビルド(修正後)で既存の長いBASIC処理系の検査が引き続きOKであること"
if bash "$REPO/tools/conform_l4.sh" >"$WORK/conform_l4.txt" 2>&1; then
  echo "OK: tools/conform_l4.sh はrc=0"
else
  fail "tools/conform_l4.sh がNG"; tail -40 "$WORK/conform_l4.txt" >&2
fi

if bash "$REPO/tools/l3_main_selftest.sh" >"$WORK/l3_main_selftest.txt" 2>&1; then
  echo "OK: tools/l3_main_selftest.sh はrc=0"
else
  fail "tools/l3_main_selftest.sh がNG"; tail -40 "$WORK/l3_main_selftest.txt" >&2
fi

if bash "$REPO/tools/l3_screen_editor_selftest.sh" >"$WORK/l3_screen_editor_selftest.txt" 2>&1; then
  echo "OK: tools/l3_screen_editor_selftest.sh はrc=0"
else
  fail "tools/l3_screen_editor_selftest.sh がNG"; tail -40 "$WORK/l3_screen_editor_selftest.txt" >&2
fi

# -----------------------------------------------------------------------
echo
if [ "$FAILED" -eq 0 ]; then
  echo "vsync_regcheck_selftest: OK"
  exit 0
else
  echo "vsync_regcheck_selftest: NG"
  exit 1
fi
