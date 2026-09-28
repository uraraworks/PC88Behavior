#!/usr/bin/env python3
"""m6f-h の合成D88・偽フロントエンド・陰性対照。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import m6fh_body as body
import m6fh_script as script
import make_m6fc_blank_disk as blank

MARKER = b'LEAK_PROBE_M6FH_DO_NOT_PRINT'


def image_for(arm: str, candidate: str, *, swapped=False, bad_type=False, leak=False) -> bytes:
    data = bytearray(blank.build_blank_disk(0xff, 0xff, sector_fills={(18,1,13):0}))
    img = body.Image(data)
    def put(coord, offset, payload):
        start, _ = img.sectors[coord]
        data[start+offset:start+offset+len(payload)] = payload
    name = script.NAMES[arm]
    entry = bytearray([0xff]*16)
    entry[:9] = name.ljust(9,b' ')
    entry[9] = 0x80 if bad_type else 0
    entry[10] = 1
    put((18,1,1), 0, entry)
    if candidate == 'EMPTY':
        payload = b'Z'
    else:
        payload = script.predicted(arm,candidate)
    units = [1,3] if (len(payload)+255)//256 + (arm != 'H-0' and not candidate.endswith('_NONE')) > 8 else [1]
    sectors = (len(payload)+255)//256
    if not sectors:
        sectors = 1
    # 印あり候補は合成像だけ使用セクタを1つ余分に取る。
    if arm not in ('H-0',) and not candidate.endswith('_NONE'):
        sectors += 1
    used_last = sectors-8*(len(units)-1)
    for coord in ((18,1,14),(18,1,15),(18,1,16)):
        put(coord, units[0], bytes([units[1] if len(units)>1 else 0xc0+used_last]))
        if len(units)>1:
            put(coord, units[1], bytes([0xc0+used_last]))
    stream = payload.ljust(sectors*256,b'Q')
    if leak:
        stream = stream[:len(payload)+3] + MARKER + stream[len(payload)+3+len(MARKER):]
    for index in range(sectors):
        logical = index
        if swapped and len(units)>1:
            unit = units[1] if index < 8 else units[0]
            sub = index % 8
        else:
            unit = units[index//8]
            sub = index%8
        linear=unit*8+sub
        put((linear//32,(linear//16)%2,linear%16+1),0,stream[index*256:(index+1)*256])
    return bytes(data)


def fake_frontend(argv: list[str]) -> int:
    def val(key): return argv[argv.index(key)+1]
    out = Path(val('--out'))
    assert '--screen-signature-only' in argv
    arm = next(a for a in script.ARMS if out.name.startswith(a+'-r'))
    assert val('--frames') == str(script.FRAMES[arm])
    assert argv[argv.index('--type-at', argv.index('--type-at')+1)+3] == script.escaped(script.keystrokes(arm))
    assert os.environ.get('M6FH_LONG_TYPING') == '1'
    Path(os.environ['M6FH_FAKE_COUNT']).open('a').write('1\n')
    img = image_for(arm, {'H-1':'LIST_CRLF_1A','H-2':'LIST_CRLF_1A',
                          'H-3':'CRLF_1A','H-0':'1A'}[arm],
                    bad_type=os.environ.get('M6FH_FAKE_BAD_TYPE')==arm)
    Path(val('--disk2')).write_bytes(img)
    out.write_text('{"signature":"synthetic"}\n')
    Path(val('--io-log')).write_text('synthetic\n')
    return 0


def components() -> None:
    assert len(script.program_lines('H-2')) == 70
    assert len(script.candidate_ids('H-1')) == len(script.candidate_ids('H-2')) == 18
    assert len(script.candidate_ids('H-3')) == 9
    for arm in script.ARMS:
        for cid in script.candidate_ids(arm):
            got = body.compare(image_for(arm,cid),arm)
            matches = {c for c,v in got['candidates'].items() if v['match']}
            assert matches == {cid}, (arm,cid,matches)
            assert got['g7_max_position'] <= got['g7_limit']
    # 追補1: 印あり、別値、セクタ末尾の三つを合成本体で分ける。
    arm='H-1'; none='LIST_CRLF_NONE'; marked='LIST_CRLF_1A'
    def matches(data):
        result=body.compare(data,arm)
        return {c for c,v in result['candidates'].items() if v['match']}, result
    marked_image=image_for(arm,marked)
    found, marked_result=matches(marked_image)
    assert found=={marked} and not marked_result['candidates'][none]['match']
    assert marked_result['candidates'][none]['first_mismatch']==len(script.predicted(arm,none))
    unmarked_image=image_for(arm,none)
    found, unmarked_result=matches(unmarked_image)
    assert found=={none} and unmarked_result['g7_max_position'] <= unmarked_result['g7_limit']
    unmarked_view=body.Image(unmarked_image)
    _, none_position=body.read_bounded(unmarked_view, body.chain(unmarked_view,script.NAMES[arm])[0],len(script.predicted(arm,none))+1)
    assert none_position==len(script.predicted(arm,none))
    next_pos=unmarked_view.sectors[(0,0,9)][0]+len(script.predicted(arm,none))
    broken_next=bytearray(unmarked_image)
    broken_next[next_pos]=0x1a
    assert matches(bytes(broken_next))[0]=={marked}  # 別値条件の陰性対照。
    broken_next[next_pos]=0x00
    assert matches(bytes(broken_next))[0]=={'LIST_CRLF_00'}
    # 凍結候補を変えず、境界条件だけ256バイトの合成予測で検査する。
    original_predicted=script.predicted
    boundary_body=original_predicted(arm,none).ljust(256,b'Q')
    def boundary_predicted(which_arm, cid):
        if which_arm==arm and cid==none:
            return boundary_body
        return original_predicted(which_arm,cid)
    with patch.object(script,'predicted',side_effect=boundary_predicted):
        boundary_image=image_for(arm,none)
        found, boundary_result=matches(boundary_image)
        assert found=={none}
        assert boundary_result['used_sectors']==1
        assert boundary_result['g7_max_position']==255  # 範囲外の257バイト目は読まない。
        assert boundary_result['g7_limit']==256
        broken_boundary=bytearray(boundary_image)
        last_pos=body.Image(boundary_image).sectors[(0,0,9)][0]+255
        broken_boundary[last_pos]=ord('R')
        assert matches(bytes(broken_boundary))[0]==set()  # 末尾一致の陰性対照。
    empty_zero=bytearray(image_for('H-0','EMPTY'))
    zero_pos=body.Image(empty_zero).sectors[(18,1,1)][0]+10
    empty_zero[zero_pos]=0xff
    empty_result=body.compare(bytes(empty_zero),'H-0')
    assert empty_result['used_sectors']==0
    assert {c for c,v in empty_result['candidates'].items() if v['match']}=={'EMPTY'}
    arm='H-2'; cid='LIST_CRLF_1A'
    got=body.compare(image_for(arm,cid,swapped=True),arm)
    assert {c for c,v in got['candidates'].items() if v['match']} == set()
    leak_image=image_for('H-1','LIST_CRLF_1A',leak=True)
    assert MARKER in leak_image  # 陰性対照の目印が実際に像にある。
    got=body.compare(leak_image,'H-1')
    assert MARKER not in json.dumps(got).encode()
    assert got['g7_max_position'] <= got['g7_limit']
    inside=bytearray(image_for('H-1','LIST_CRLF_1A'))
    inside_index=body.Image(inside).sectors[(0,0,9)][0]
    inside[inside_index:inside_index+len(MARKER)]=MARKER
    got_inside=body.compare(bytes(inside),'H-1')
    assert not any(v['match'] for v in got_inside['candidates'].values())
    assert MARKER not in json.dumps(got_inside).encode()
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'leak.d88'; path.write_bytes(leak_image)
        p=subprocess.run([sys.executable,str(HERE/'m6fh_body.py'),'--image',str(path),'--arm','H-1'],capture_output=True)
        assert p.returncode==0 and MARKER not in p.stdout+p.stderr
    try:
        body.compare(image_for('H-1','LIST_CRLF_1A',bad_type=True),'H-1')
    except body.BodyError as exc:
        assert str(exc)=='G6_種別'
    else:
        raise AssertionError('G6')
    # 判定器の全腕とNG集合を確認。
    import judge_m6fh
    runs=[]
    for arm in script.ARMS:
        cid={'H-1':'LIST_CRLF_1A','H-2':'LIST_CRLF_1A','H-3':'CRLF_1A','H-0':'1A'}[arm]
        for rep in (1,2):
            runs.append(dict(body.compare(image_for(arm,cid),arm),arm=arm,repetition=rep,drive1_sha_ok=True))
    verdict=judge_m6fh.judge({'runs':runs})
    assert verdict['status']=='OK' and verdict['H-IV']=='chain_concatenates' and verdict['H-V']=='data_same_as_ascii_program'
    overlapping=json.loads(json.dumps(runs))
    for row in overlapping:
        if row['arm']=='H-1':
            row['candidates'][none]['match']=True
    assert judge_m6fh.judge({'runs':overlapping})['arms']['H-1']=='inconclusive_H-1_multiple'
    broken=json.loads(json.dumps(runs))
    broken[0]['candidates']['LIST_CRLF_1A']['match']=False
    assert judge_m6fh.judge({'runs':broken})=={'status':'gate_failed','reason':'G4','arm':'H-1'}
    broken=json.loads(json.dumps(runs))
    broken[0]['gate']='NG'
    assert judge_m6fh.judge({'runs':broken})['status']=='gate_failed'


def driver_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        work=Path(td)
        fake=work/'fake'
        fake.write_text('#!/bin/sh\nexec python3 '+str(Path(__file__).resolve())+' --fake "$@"\n')
        fake.chmod(0o755)
        rom=work/'rom'; rom.mkdir()
        disk=work/'disk'; disk.mkdir()
        (disk/'N88_FE.D88').write_bytes(b'synthetic-reference')
        count=work/'count'
        env=dict(os.environ,M6FH_FRONTEND=str(fake),M6FH_TEST_CORE=str(fake),M6FH_TEST_SKIP_G1='1',
                 M6FH_FAKE_COUNT=str(count),M6FH_TEST_ROM_DIR=str(rom),M6FH_TEST_DISK_DIR=str(disk))
        command=['bash',str(HERE/'measure_m6fh.sh'),'--raw-dir',str(work/'raw'),'--result',str(work/'result.json')]
        bad=work/'bad.tsv'
        bad.write_bytes((HERE/'m6fh_frozen.tsv').read_bytes().replace(b'media_sha256\t',b'media_sha256\tx',1))
        env['M6FH_FROZEN_CONFIG']=str(bad)
        p=subprocess.run(command,env=env,capture_output=True)
        assert p.returncode!=0 and b'"frontend_launch_count":0' in p.stdout and not count.exists()
        del env['M6FH_FROZEN_CONFIG']
        p=subprocess.run(command,env=env,capture_output=True)
        assert p.returncode==0, (p.returncode,p.stdout,p.stderr)
        assert len(count.read_text().splitlines())==8
        result=json.loads((work/'result.json').read_text())
        assert judge_result(result)
        assert MARKER not in p.stdout+p.stderr+(work/'result.json').read_bytes()
        assert not list((work/'raw').glob('*.d88'))
        count.unlink(); (work/'result.json').unlink()
        (work/'raw').rmdir()
        env['M6FH_FAKE_BAD_TYPE']='H-1'
        p=subprocess.run(command,env=env,capture_output=True)
        assert p.returncode!=0 and b'"reason":"G6"' in p.stdout


def judge_result(result):
    import judge_m6fh
    return judge_m6fh.judge(result)['status']=='OK'


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--fake':
        return fake_frontend(sys.argv[2:])
    components()
    if not (len(sys.argv)>1 and sys.argv[1]=='--components-only'):
        driver_test()
    print('m6f-h 自己検査: OK')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
