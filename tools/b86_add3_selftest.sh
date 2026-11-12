#!/usr/bin/env bash
set -euo pipefail
unset PC88_REF_ROM_DIR PC88_REF_DISK_DIR PC88_REF_DISKB PC88_GAME_DIR B86_FRAMES B86_TIMEOUT PC88_CORE PC88_FRONTEND
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add3.XXXXXX")"
trap 'rm -rf "$work"' EXIT
bash "$repo/tools/b86_add3_run.sh" "$work/run"
python3 - "$work/run" "$repo/tools" <<'PY'
import json,pathlib,re,shutil,subprocess,sys
p=pathlib.Path(sys.argv[1]); sys.path.insert(0,sys.argv[2]); import b86_add3 as m
arms=list(m.fixed_arms()); assert len(arms)==29
for arm in arms:
    sector,marks=m.generate(arm)
    assert len(sector)==256 and len(marks)==2*len(arm[1])+(len(arm[1])>1)
    s=json.loads((p/'summary'/f'{arm[0]}.json').read_text())
    assert all(r['開始']=='確認' and r['終了印']=='確認' for r in s['区間'])
    assert s['RAM']['判定']=='取得'
    if len(arm[1])>1: assert s['前置き終了印']=='確認'
    text=json.dumps(s,ensure_ascii=False)
    assert '5A' not in text and '00FD' not in text
assert json.loads((p/'summary/positive.json').read_text())['区間'][0]['送信長']==1
assert json.loads((p/'summary/control.json').read_text())['区間'][0]['送信長']==0
sector,_=m.generate(m.arm_by_name('ram-d123-flip'))
assert bytes.fromhex('3a 23 d1 ee ff 32 23 d1') in sector[:0x80]
disk=m.disk(sector); offset=int.from_bytes(disk[0x20:0x24],'little'); assert disk[offset+16:offset+272]==sector
b=p/'boundary-test'; b.write_text('C C123 1 0 0 1\nC C124 0 1 1 0\n# (C 終わり)\n')
out=subprocess.check_output([sys.executable,str(pathlib.Path(sys.argv[2])/'b86_add3.py'),'candidates',str(b)],text=True).splitlines(); assert out==['ram-c123-flip']
b.write_text('C C123 1 0 0 1\n'); assert subprocess.run([sys.executable,str(pathlib.Path(sys.argv[2])/'b86_add3.py'),'candidates',str(b)],capture_output=True).returncode != 0
arm=m.arm_by_name('3847-twice'); _,marks=m.generate(arm); d=p/'mutation'; shutil.copytree(p/'raw'/arm[0],d)
io=(d/'io').read_text(); pat=r'(\sOUT\s+007F\s+[0-9A-F]{2}\s+)'+f'{marks[-2]:04X}'+r'$'
io,n=re.subn(pat,r'\g<1>FFFF',io,flags=re.M); assert n==1
(d/'io').write_text(io); assert m.summarize(d,arm,marks)['区間'][-1]['開始']=='欠測'
(d/'io').write_text(io.replace('取りこぼし: 0件','取りこぼし: 1件',1)); assert m.summarize(d,arm,marks)['判定'].startswith('欠測')
print('PASS: 29腕、対照、候補、欠測、値なし集計')
PY
