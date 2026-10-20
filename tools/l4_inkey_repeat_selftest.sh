#!/usr/bin/env bash
# r5（d4f425a）。自作ROMだけでINKEY$の短打=1文字・長押し=複数文字を各2走で確かめる。
# 公式ROM・私物は使わない。ROMはリポジトリ外の一時領域へ組む。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unset PC88_REF_ROM_DIR PC88_REF_DISK_DIR PC88_REF_DISKB
WORK="$(mktemp -d "${TMPDIR:-/tmp}/l4-inkey-repeat.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
python3 -B "$REPO/src/build_main_rom.py" "$WORK/rom" --work-dir "$WORK/asm" >/dev/null
nice -n 10 python3 -B "$REPO/tools/l4_inkey_repeat_selftest.py" --rom-dir "$WORK/rom"
