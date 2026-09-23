#!/usr/bin/env bash
# m6i-h解析器のG5/G6/G7/G8/G10を合成入力で検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
from pathlib import Path
import sys
repo,scratch=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo/'tools'))
import analyze_m6ia_main_sub as a6
import analyze_main_to_sub as m2s
import analyze_m6ih as a
import build_m6ib_measure_rom as roms

def facts(**updates):
    row={'timeout_marker_count':0,'receive_complete_block_count':1,
         'receive_sha256':a6.EXPECT_SHA[1],'key_input_accepted':True}
    row.update(updates); return row
def sector_mem(count, success=False, retry=False):
    rows=[a6.MemEvent(i+1,1,0x7000,0xDF00+i,i&0xff) for i in range(count)]
    if retry: rows.append(a6.MemEvent(300,1,0,0xE00D,1))
    if success: rows.append(a6.MemEvent(301,1,0,0xE002,1))
    return rows
def marker_mem(b=0,c=0):
    rows=[]
    if b: rows.append(a6.MemEvent(1,1,0,0xE00B,1))
    if c: rows.append(a6.MemEvent(2,1,0,0xE00C,1))
    return rows
def preamble_rows(b=0,c=0):
    rows=[]; seq=1
    if b:
        rows += [m2s.Ev(seq,10,1,'main','OUT','00FD',0,'0000'),
                 m2s.Ev(seq+1,11,1,'sub','IN','00FC',0,'0000')]; seq+=2
    if c: rows.append(m2s.Ev(seq,35,2,'sub','OUT','00FD',0,'0000'))
    return rows

# G7（m6i-gから継承）
shape=(7,20,30,1,2)
for expected,rows,mem in [((1,0,0),[],[]),((1,1,0),preamble_rows(1),marker_mem(1)),
                          ((1,0,1),preamble_rows(c=1),marker_mem(c=1))]:
    if a.observe_state(shape,rows,mem,40).counts!=expected: raise SystemExit('G7')
obs=a.observe_state(shape,preamble_rows(1,1),marker_mem(1,1),40)
if obs.counts!=(1,1,1) or not obs.independent or not obs.event_counts_consistent: raise SystemExit('G7独立')

# G10（窓の両端3件をm6i-gから継承）
sub_start=[m2s.Ev(1,10,1,'sub','OUT','00FD',0,'0000')]
if not a.observe_state(None,sub_start,[],40).event_counts_consistent: raise SystemExit('G10-1')
main_start=preamble_rows(b=1)
if a.state_event_counts(None,main_start,40)!=(1,1,None) \
        or not a.observe_state(None,main_start,marker_mem(1),40).event_counts_consistent: raise SystemExit('G10-2')
late=(7,50,60,1,2); post=[m2s.Ev(1,45,1,'main','OUT','00FD',0,'0000'),m2s.Ev(2,46,1,'sub','IN','00FC',0,'0000')]
if a.state_event_counts(late,post,40)!=(0,0,None) \
        or not a.observe_state(late,post,[],40).event_counts_consistent: raise SystemExit('G10-3')

# G5: H-A/H-BのaとH-Aのframeは任意、H-Bだけ再試行印を要求する。
for arm in a.ARMS:
    expected=tuple(0 if x is None else x for x in a.EXPECTED_STATES[arm])
    retry=1 if arm=='H-B' else 0; frame=a.ISSUE_FRAMES.get(arm,123)
    if not a.reached(arm,a.StateObservation(expected,True,True),frame,retry,True): raise SystemExit('G5 '+arm)
if not a.reached('H-A',a.StateObservation((9,1,0),True,True),999,0,True): raise SystemExit('G5 H-A非凍結')
if not a.reached('H-B',a.StateObservation((8,0,0),True,True),777,1,True): raise SystemExit('G5 H-B非凍結')
for arm in a.ARMS:
    expected=tuple(0 if x is None else x for x in a.EXPECTED_STATES[arm])
    retry=0 if arm=='H-B' else 1
    if a.reached(arm,a.StateObservation(expected,True,True),a.ISSUE_FRAMES.get(arm,1),retry,True): raise SystemExit('G5 retry '+arm)

# 発行後run数を記録するが、H-Bの結果条件には使わない。
vals=[2,0,0,0,1]; rows=[]; seq=1
for clock in (10,100):
    for i,value in enumerate(vals): rows.append(m2s.Ev(seq,clock+i,1,'main','OUT','00FD',value,'0000')); seq+=1
if a.request_runs_after_issue(rows,100)!=1: raise SystemExit('run窓')

# G6標準5件。
cases={
 'positions_256_match':(facts(),sector_mem(256)),
 'one_position_missing':(facts(receive_complete_block_count=0,receive_sha256=None),sector_mem(255)),
 'sha_mismatch':(facts(receive_sha256='0'*64),sector_mem(256)),
 'timeout':(facts(timeout_marker_count=1),[]),
 'steady_wait_not_returned':(facts(key_input_accepted=False),sector_mem(256)),
}
import analyze_m6ib_first_request as b
for expected,(row,mem) in cases.items():
    if b.classify_result(row,mem,a6.EXPECT_SHA[1])!=expected: raise SystemExit('G6 '+expected)
# H-B: 1回目失敗→2回目成功は成功、2回とも失敗は別の失敗名。
mem=sector_mem(256,success=True,retry=True)
detail=a.h_b_result_detail(facts(timeout_marker_count=1),mem,a6.EXPECT_SHA[1])
if detail!='positions_256_match' or a.result_kind('H-B',detail,2)!='success': raise SystemExit('G6 H-B再試行成功')
mem=sector_mem(0,success=False,retry=True)
detail=a.h_b_result_detail(facts(receive_complete_block_count=0,receive_sha256=None),mem,a6.EXPECT_SHA[1])
if detail!='retry_failed' or a.result_kind('H-B',detail,2)!='failure': raise SystemExit('G6 H-B二重失敗')

# G8: 固定7名だけを読むので走が追加するファイルで到達用SHAは変わらない。
rom_dir=scratch/'rom'; rom_dir.mkdir()
for name,size in roms.EXPECTED_SIZES.items(): (rom_dir/name).write_bytes(bytes(size))
before=a.rom_digest(rom_dir); (rom_dir/'generated.srm').write_bytes(b'synthetic')
if a.rom_digest(rom_dir)!=before: raise SystemExit('G8')
print('analyze_m6ih_selftest: 項目数=26、G5=10・run窓=1・G6=7・G7=4・G8=1・G10=3 OK')
PY
