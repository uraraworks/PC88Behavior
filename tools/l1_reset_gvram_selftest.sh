#!/usr/bin/env bash
# 自作ROMで描画・リセット後の3面を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
core="$(find_l3_core)"
[ -n "$core" ] || { echo 'FAIL: コアがありません' >&2; exit 1; }
ensure_l3_frontend
python3 "$REPO/src/build_main_rom.py" "$WORK/rom" >"$WORK/build.log" 2>&1 || { grep -i error "$WORK/build.log" >&2 || true; exit 1; }
cp -R "$WORK/rom" "$WORK/fault"
# 判定を常に電源投入直後にする（各区画の不一致分岐を無効化）。
python3 - "$WORK/fault/N88.ROM" <<'PYCODE'
import sys
p = sys.argv[1]
b = bytearray(open(p, 'rb').read())
for address in (0x8000, 0x9000, 0xA000, 0xB000, 0xC000, 0xD000, 0xE000, 0xF210, 0xFFB0):
    pattern = bytes((0x21, address & 255, address >> 8, 0x7e, 0x06, 15, 0x23, 0xbe, 0xc2))
    i = b.find(pattern)
    assert i >= 0 and b.find(pattern, i + 1) < 0
    b[i+8:i+11] = b'\x00\x00\x00'
open(p, 'wb').write(b)
PYCODE
run() {
  local rom="$1" dump="$2" reset="$3" overwrite="${4:-no}"
  local args=() frames=2102 dump_at=2100 reset_at=1800
  [ "$overwrite" = yes ] && frames=7002 && dump_at=7000 && reset_at=6700
  [ "$reset" = yes ] && args=(--reset-at "$reset_at")
  [ "$overwrite" = yes ] && args+=(--mem-write-log "$WORK/writes" --mem-write-range C000-CFFF --mem-write-from-frame 1600 --type-at 1100 --type 'poke &hf22c,0:poke &hf22d,0:for i=&hc000 to &hcfff:poke i,i and 255:next\n')
  "$REPO/tools/harness/frontend/q88measure" --core "$core" --rom-dir "$rom" \
    --frames "$frames" --type-at 300 --type '\n' --type-at 700 \
    --type 'screen 0,0:line(0,0)-(639,199),7,bf\n' \
    ${args[@]+"${args[@]}"} --gvram-dump "$dump" --gvram-dump-at "$dump_at" \
    --out "$WORK/trace" >"$WORK/stdout" 2>"$WORK/stderr"
}
run "$WORK/rom" "$WORK/before" no
run "$WORK/rom" "$WORK/after" yes
run "$WORK/rom" "$WORK/overwrite-after" yes yes
python3 - "$WORK/writes" <<'PYCODE'
import re, sys
rows = [m.groups() for line in open(sys.argv[1]) if (m := re.match(r'^\s*\d+\s+(\d+)\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})$', line))]
writes = {(int(addr, 16), int(value, 16)) for frame, addr, value in rows if int(frame) < 6700}
assert all((addr, addr & 255) in writes for addr in (0xC000, 0xC7FF, 0xCFFF)), '広範囲のPOKEが完了していない'
PYCODE
run "$WORK/fault" "$WORK/fault-after" yes
python3 - "$WORK/before" "$WORK/after" "$WORK/overwrite-after" "$WORK/fault-after" <<'PY'
import pathlib, sys
before, after, overwrite, fault = (pathlib.Path(p).read_bytes() for p in sys.argv[1:])
assert all(len(b) == 0xc000 for b in (before, after, overwrite, fault))
assert all(any(before[i:i+0x4000]) for i in range(0, 0xc000, 0x4000)), '描画失敗'
assert not any(after), 'リセット後のVRAMが非ゼロ'
assert not any(overwrite), '作業域上書き後のVRAMが非ゼロ'
assert any(fault), '陰性対照を検出できない'
print('PASS: 描画・リセット後の3面消去、陰性対照')
PY

# 電源投入時の先頭344 OUTを仕様の列と比較する。
python3 "$REPO/tools/l1_spec_iolog.py" "$WORK/spec.io"
"$REPO/tools/harness/frontend/q88measure" --core "$core" --rom-dir "$WORK/rom" \
  --frames 60 --io-log "$WORK/cold.io" --out "$WORK/cold.trace" >"$WORK/stdout" 2>"$WORK/stderr"
python3 - "$REPO/tools" "$WORK/spec.io" "$WORK/cold.io" <<'PYCODE'
import sys
sys.path.insert(0, sys.argv[1])
from cmp_io import parse_iolog
expected = [(e.port, e.value) for e in parse_iolog(sys.argv[2], 'main') if e.kind == 'OUT'][:344]
actual = [(e.port, e.value) for e in parse_iolog(sys.argv[3], 'main') if e.kind == 'OUT'][:344]
assert len(expected) == len(actual) == 344 and actual == expected, '電源投入時のI/O列が不一致'
print('PASS: 電源投入時のI/O列（先頭344 OUT）')
PYCODE
