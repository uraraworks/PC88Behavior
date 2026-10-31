#!/usr/bin/env bash
# N88.ROMの機種判定の印を独立に検査し、ビルド時の衝突検出も試す。
# コアの音源ポート条件から最小値 '4' を選択。公式ROMの値は読まない。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 src/build_main_rom.py "$WORK/rom" >"$WORK/build.txt" 2>&1 || {
  echo "NG: build_main_rom.py が失敗" >&2
  cat "$WORK/build.txt" >&2
  exit 1
}
python3 - "$WORK" <<'PY'
import pathlib
import sys

work = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(pathlib.Path.cwd()))
import src.build_main_rom as build
import z80text

def valid(data):
    return len(data) > 0x79D7 and data[0x79D7] == 0x34

data = bytearray((work / 'rom/N88.ROM').read_bytes())
assert valid(data), '成果物の機種判定の印が不正'
data[0x79D7] = 0
assert not valid(data), '成果物の印の破壊を見逃した'

# 印そのものと別の値の両方で、書き込み前の衝突検査を確認。
text = build.build_combined_asm(work, 0, False)
original = z80text.Assembler.assemble
for value in (0x00, 0x34, 0x76):
    def broken(self, path, value=value):
        code = bytearray(original(self, path))
        code[build.ROM_VERSION_RESERVED_ADDR] = value
        if value == 0:
            self.listing.append((build.ROM_VERSION_RESERVED_ADDR, b"\x00", 0, "NOP"))
        return bytes(code)
    z80text.Assembler.assemble = broken
    try:
        build.assemble(text, work)
    except SystemExit as exc:
        assert 'ROM_VERSION予約番地' in str(exc), str(exc)
    else:
        raise AssertionError(f'予約番地の衝突 0x{value:02X} を見逃した')
z80text.Assembler.assemble = original
print('OK: 0x79D7は0x34、印の破壊と配置衝突の陰性対照も検出')
PY
