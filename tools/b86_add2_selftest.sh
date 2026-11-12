#!/usr/bin/env bash
set -euo pipefail
unset PC88_REF_ROM_DIR PC88_REF_DISK_DIR PC88_REF_DISKB PC88_GAME_DIR B86_FRAMES B86_TIMEOUT PC88_CORE PC88_FRONTEND
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add2.XXXXXX")"
trap 'rm -rf "$work"' EXIT
bash "$repo/tools/b86_add2_run.sh" "$work/run"
python3 - "$work/run" "$repo/tools" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); sys.path.insert(0,sys.argv[2]); import b86_add2 as m
arms=list(m.fixed_arms()); assert len(arms)==17
for arm in arms:
    s=json.loads((p/'summary'/f'{arm[0]}.json').read_text())
    assert all(r['開始']=='確認' for r in s['区間'])
    assert s['RAM']['判定']=='取得'
    if len(arm[1])>1: assert s['前置き終了印']=='確認'
assert json.loads((p/'summary/positive.json').read_text())['区間'][0]['送信長']==1
sec,marks=m.generate(m.arm_by_name('ram-d123-1')); assert b'\x3e\x01\x32\x23\xd1' in sec[:0x80]
disk=m.disk(sec); offset=int.from_bytes(disk[0x20:0x24],'little'); assert disk[offset+16:offset+272]==sec
assert disk[offset+272+16:offset+544]==m.coord_header_pattern(0xa1,0,0,2)
sample={'RAM':{'判定':'取得','変化番地範囲':[['C123','C124']]}}
(p/'candidate-test.json').write_text(json.dumps(sample))
import subprocess
out=subprocess.check_output([sys.executable,str(pathlib.Path(sys.argv[2])/'b86_add2.py'),'candidates',str(p/'candidate-test.json')],text=True).splitlines()
assert out==['ram-c123-0','ram-c123-1','ram-c124-0','ram-c124-1']
arm=m.arm_by_name('3847-pair'); _,marks=m.generate(arm)
assert len(marks)==7
s=m.summarize(p/'raw'/'3847-pair',arm,marks); assert s['前置き終了印']=='確認'
# 欠落・取りこぼしと再起動、要求見出しの切り出しを故障注入する。
import re,shutil
arm=m.arm_by_name('3391-37c9'); _,marks=m.generate(arm)
d=p/'mutation'; shutil.copytree(p/'raw'/arm[0],d)
io=(d/'io').read_text(); target=marks[-2]
pat=r'(\sOUT\s+007F\s+[0-9A-F]{2}\s+)'+f'{target:04X}'+r'$'
io,n=re.subn(pat,r'\g<1>FFFF',io,flags=re.M); assert n==1
(d/'io').write_text(io); result=m.summarize(d,arm,marks)
assert result['区間'][-1]['開始']=='欠測'
(d/'io').write_text(io.replace('取りこぼし: 0件','取りこぼし: 1件',1))
assert m.summarize(d,arm,marks)['判定'].startswith('欠測')
for a in arms:
    text=(p/'summary'/f'{a[0]}.json').read_text()
    assert '5A' not in text and '00FD' not in text
print('PASS: 17腕、対照、前置き印、自作媒体、介入候補、値なし集計')
PY
