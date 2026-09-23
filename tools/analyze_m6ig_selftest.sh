#!/usr/bin/env bash
# m6i-g解析器のG5/G6/G7/G8/G10を合成入力で検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
from pathlib import Path
import sys
repo,scratch=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo/'tools'))
import analyze_m6ia_main_sub as a6
import analyze_main_to_sub as m2s
import analyze_m6ig as a
import build_m6ib_measure_rom as roms

def facts(**updates):
    row={'timeout_marker_count':0,'receive_complete_block_count':1,
         'receive_sha256':a6.EXPECT_SHA[1],'key_input_accepted':True}
    row.update(updates); return row
def sector_mem(count):
    return [a6.MemEvent(i+1,1,0x7000,0xDF00+i,i&0xff) for i in range(count)]
def marker_mem(b=0,c=0):
    rows=[]
    if b: rows.append(a6.MemEvent(1,1,0,0xE00B,1))
    if c: rows.append(a6.MemEvent(2,1,0,0xE00C,1))
    return rows
def preamble_rows(b=0,c=0):
    rows=[]; seq=1
    if b:
        rows.append(m2s.Ev(seq,10,1,'main','OUT','00FD',0,'0000')); seq+=1
        rows.append(m2s.Ev(seq,11,1,'sub','IN','00FC',0,'0000')); seq+=1
    if c: rows.append(m2s.Ev(seq,35,2,'sub','OUT','00FD',0,'0000'))
    return rows

# G7: aはI/O形、b/cは相異なる書込み事象。単一事象を二状態へ数えない。
shape=(7,20,30,1,2)
if a.observe_state(shape,[],[],40).counts!=(1,0,0): raise SystemExit('G7 a')
if a.observe_state(shape,preamble_rows(b=1),marker_mem(b=1),40).counts!=(1,1,0): raise SystemExit('G7 b')
if a.observe_state(shape,preamble_rows(c=1),marker_mem(c=1),40).counts!=(1,0,1): raise SystemExit('G7 c')
obs=a.observe_state(shape,preamble_rows(1,1),marker_mem(1,1),40)
if obs.counts!=(1,1,1) or not obs.independent or not obs.event_counts_consistent:
    raise SystemExit('G7 独立性')

# G10: 修正前の observe_state(None, ...) に同じ2入力を与え、どちらも整合性が偽になることを実走確認済み。
sub_start=[m2s.Ev(1,10,1,'sub','OUT','00FD',0,'0000')]
if not a.observe_state(None,sub_start,[],40).event_counts_consistent:
    raise SystemExit('G10 初期化なしsub起動OUT')
main_start=preamble_rows(b=1)
startup_send,_,round0_response=a.state_event_counts(None,main_start,40)
if startup_send!=1 or round0_response is not None \
        or not a.observe_state(None,main_start,marker_mem(b=1),40).event_counts_consistent:
    raise SystemExit('G10 初期化なしmain起動SEND')

# G5: 腕ごとの異なる発行フレームと状態を同じ入口で照合する。
for arm in a.ARMS:
    observed=a.StateObservation(a.EXPECTED_STATES[arm],True,True)
    if not a.reached(observed,a.EXPECTED_STATES[arm],a.ISSUE_FRAMES[arm],a.ISSUE_FRAMES[arm],True):
        raise SystemExit('G5 '+arm)
base=a.StateObservation(a.EXPECTED_STATES['G-L2'],True,True)
for fault in a.FAULTS:
    observed,frame,runs,integrity=a.inject_fault(fault,base,60,1)
    if a.reached(observed,a.EXPECTED_STATES['G-L2'],frame,60,integrity):
        raise SystemExit('G5故障 '+fault)

# 前置きに同じ要求形があっても、発行後の1 runだけを数える。
vals=[0x02,0,0,0,1]
rows=[]; seq=1
for clock0 in (10,100):
    for i,value in enumerate(vals):
        rows.append(m2s.Ev(seq,clock0+i,1,'main','OUT','00FD',value,'0000')); seq+=1
if a.request_runs_after_issue(rows,100)!=1: raise SystemExit('前置きrun混入')

# G6: 成功、欠落、SHA違い、timeout、定常待ち未復帰を別名にする。
cases={
 'positions_256_match':(facts(),sector_mem(256)),
 'one_position_missing':(facts(receive_complete_block_count=0,receive_sha256=None),sector_mem(255)),
 'sha_mismatch':(facts(receive_sha256='0'*64),sector_mem(256)),
 'timeout':(facts(timeout_marker_count=1),sector_mem(0)),
 'steady_wait_not_returned':(facts(key_input_accepted=False),sector_mem(256)),
}
for expected,(row,memory) in cases.items():
    if a.result_detail(row,memory,a6.EXPECT_SHA[1])!=expected: raise SystemExit('G6 '+expected)

# G8: 固定7名だけを読むため、走が作る余分なファイルで到達用SHAは変わらない。
rom_dir=scratch/'rom'; rom_dir.mkdir()
for name,size in roms.EXPECTED_SIZES.items(): (rom_dir/name).write_bytes(bytes(size))
before=a.rom_digest(rom_dir); (rom_dir/'generated.srm').write_bytes(b'synthetic')
if a.rom_digest(rom_dir)!=before: raise SystemExit('G8自己汚染')
print('analyze_m6ig_selftest: 項目数=21、G5=8・前置きrun除外=1・G6=5・G7=4・G8=1・G10=2 OK')
PY
