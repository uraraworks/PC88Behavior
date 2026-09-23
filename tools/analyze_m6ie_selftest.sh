#!/usr/bin/env bash
# m6i-e解析器の到達、結果5種、G8自己汚染を合成入力で検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
from pathlib import Path
import sys
repo, scratch = map(Path, sys.argv[1:])
sys.path.insert(0, str(repo/'tools'))
import analyze_m6ia_main_sub as a6
import analyze_m6ie as a
import build_m6ib_measure_rom as roms

def facts(**updates):
    row={"timeout_marker_count":0,"receive_complete_block_count":1,
         "receive_sha256":a6.EXPECT_SHA[1],"key_input_accepted":True}
    row.update(updates); return row
def mem(count):
    return [a6.MemEvent(i+1,1,0x7000,0xDF00+i,i&0xff) for i in range(count)]

# b→a→cの順序と各1回。
if not a.preamble_complete(1,1,7,10,20,30,40): raise SystemExit('前置き陽性')
if a.preamble_complete(1,1,7,40,20,30,10): raise SystemExit('前置き順序故障')
if not a.reached(True,60,True): raise SystemExit('到達陽性')
for fault in a.FAULTS:
    b,frame,runs,integrity=a.inject_fault(fault,1,60,1)
    if a.reached(b==1,frame,integrity): raise SystemExit('到達故障 '+fault)

cases={
 "positions_256_match":(facts(),mem(256)),
 "one_position_missing":(facts(receive_complete_block_count=0,receive_sha256=None),mem(255)),
 "sha_mismatch":(facts(receive_sha256='0'*64),mem(256)),
 "timeout":(facts(timeout_marker_count=1),mem(0)),
 "steady_wait_not_returned":(facts(key_input_accepted=False),mem(256)),
}
for expected,(row,memory) in cases.items():
    actual=a.result_detail(row,memory,a6.EXPECT_SHA[1])
    if actual!=expected: raise SystemExit('結果分類 '+expected+'/'+actual)
if a.result_kind('positions_256_match',1)!='success': raise SystemExit('成功分類')

# G8: 固定7名だけを読むので、走が生成しうる余分なファイルでSHAも到達も変わらない。
rom_dir=scratch/'rom'; rom_dir.mkdir()
for name,size in roms.EXPECTED_SIZES.items(): (rom_dir/name).write_bytes(bytes(size))
before=a.rom_digest(rom_dir)
(rom_dir/'generated.srm').write_bytes(b'synthetic')
after=a.rom_digest(rom_dir)
if before!=after or not a.reached(True,60,True): raise SystemExit('G8自己汚染')
print('analyze_m6ie_selftest: 項目数=12、前置き2・到達4・結果5・G8=1 OK')
PY
