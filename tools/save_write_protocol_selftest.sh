#!/usr/bin/env bash
# 1.35a節の制御第2位置を実Z80で検査する。旧独自値0x00は陰性対照。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/save-write-protocol.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
python3 "$REPO/src/build_main_rom.py" "$WORK/good" >"$WORK/build.out" 2>"$WORK/build.err"
SAVE_CONFORM_TEST_ROM_DIR="$WORK/good" bash "$REPO/tools/conform_save.sh" >"$WORK/good.result"
[ "$(grep -c $'\tOK$' "$WORK/good.result")" -eq 6 ]
cp -R "$WORK/good" "$WORK/bad"
python3 - "$REPO" "$WORK/bad/N88_2.ROM" <<'PY'
from pathlib import Path
import sys
repo, path = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo / 'tools' / 'asm'))
import z80text
import tempfile
sys.path.insert(0, str(repo / "src"))
import memmap
asm = z80text.Assembler()
with tempfile.TemporaryDirectory() as tmp:
    source = Path(tmp) / 'bank2.asm'
    source.write_text(memmap.asm_prelude() + (repo / 'src/ext_bank/bank2.asm').read_text())
    asm.assemble(source)
offset = asm.labels['s2_ws_request'] - 0x6000 + 7
rom = bytearray(path.read_bytes())
if rom[offset - 1:offset + 1] != b'\x3e\x01':
    raise SystemExit('NG: 故障注入位置')
rom[offset] = 0x00
path.write_bytes(rom)
PY
set +e
SAVE_CONFORM_TEST_ROM_DIR="$WORK/bad" bash "$REPO/tools/conform_save.sh" >"$WORK/bad.result"
rc=$?
set -e
[ "$rc" -eq 1 ]
for arm in J-1 J-2 J-3 J-6; do
    grep -qx "$arm"$'\tNG' "$WORK/bad.result"
done
for arm in J-4 J-5; do
    grep -qx "$arm"$'\tOK' "$WORK/bad.result"
done
cp -R "$WORK/good" "$WORK/bad_s"
python3 - "$REPO" "$WORK/bad_s/N88_2.ROM" <<'PY'
from pathlib import Path
import sys
repo, path = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo / 'tools' / 'asm'))
import z80text
import tempfile
sys.path.insert(0, str(repo / "src"))
import memmap
asm = z80text.Assembler()
with tempfile.TemporaryDirectory() as tmp:
    source = Path(tmp) / 'bank2.asm'
    source.write_text(memmap.asm_prelude() + (repo / 'src/ext_bank/bank2.asm').read_text())
    asm.assemble(source)
offset = asm.labels['s2_ws_later'] - 0x6000 + 1
rom = bytearray(path.read_bytes())
if rom[offset - 1:offset + 1] != b'\x3e\x06':
    raise SystemExit('NG: S故障注入位置')
rom[offset] = 0x05
path.write_bytes(rom)
PY
set +e
SAVE_CONFORM_TEST_ROM_DIR="$WORK/bad_s" bash "$REPO/tools/conform_save.sh" >"$WORK/bad_s.result"
rc=$?
set -e
[ "$rc" -eq 1 ]
for arm in J-1 J-2 J-3 J-6; do
    grep -qx "$arm"$'\tNG' "$WORK/bad_s.result"
done
printf 'SAVE送信規約\tOK（旧制御値・S破損はNG）\n'
