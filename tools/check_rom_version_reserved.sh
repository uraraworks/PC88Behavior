#!/usr/bin/env bash
# tools/check_rom_version_reserved.sh — N88.ROM の番地 0x79D7 が埋め草
# (FILL)のまま固定されていることを確かめる。
#
# 背景: エミュレータ(QUASI88、vendor/quasi88-libretro/src/memory.h:48の
# `ROM_VERSION main_rom[0x79d7]`)は、この1バイトを文字コードとして読み
# 機種を切り替える('4'以上でV2既定・'8'以上でFH/MH相当のポートの振る舞い、
# src/pc88main.c:1051・1393・1399・2688・2698)。公式ROMの同じ番地の値は
# 読まない・合わせない(これはエミュレータ側の実装の事実であって公式ROMの
# 内部構造ではないため禁止事項1-2の対象外)。
#
# これまでの適合テストは全て「この番地がFILL(機種判定に既定値が使われる)」
# 状態で通っているため、自作コード・表がここへ伸びて命令の1バイトが来ると
# 機種が偶然変わり、原因の分かりにくい食い違いを生む。
# src/build_main_rom.py の assemble() 自体もビルド時にこれを検査して
# 失敗させるが、この自己検査はビルド成果物から独立に確認する。
#
# 使い方: tools/check_rom_version_reserved.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 src/build_main_rom.py "$WORK/rom" >"$WORK/build.txt" 2>&1
if [ $? -ne 0 ]; then
  echo "NG: build_main_rom.py が失敗" >&2
  cat "$WORK/build.txt" >&2
  exit 1
fi

python3 - "$WORK/rom/N88.ROM" << 'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
addr = 0x79D7
if data[addr] != 0x00:
    print(f"NG: N88.ROM[0x{addr:04X}] = 0x{data[addr]:02X} (FILL=0x00のはず)")
    sys.exit(1)
print(f"OK: N88.ROM[0x{addr:04X}] はFILLのまま(QUASI88の機種判定は既定値のまま)")
PYEOF
exit $?
