#!/usr/bin/env bash
set -euo pipefail
unset PC88_REF_ROM_DIR PC88_REF_DISK_DIR PC88_REF_DISKB PC88_GAME_DIR B86_FRAMES B86_TIMEOUT PC88_CORE PC88_FRONTEND
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add1.XXXXXX")"
trap 'rm -rf "$work"' EXIT
bash "$repo/tools/b86_add1_run.sh" "$work/run"
python3 - "$work/run" "$repo/tools" <<'PY'
import importlib.util, json, pathlib, re, shutil, sys
p=pathlib.Path(sys.argv[1]); sys.path.insert(0,sys.argv[2]); import b86_add1 as m
arms=list(m.arms()); assert len(arms)==54
single=[a for a in arms if a[0].startswith('3391-')]
assert len(single)==10 and {a[0] for a in single}=={'3391-'+v for v in ('zero','a','bc','de','hl','flags','mem-hl-zero','mem-hl-one','mem-de-zero','mem-de-one')}
assert {a[0][5:]: a[2:] for a in single} == {
    'zero':(0,0,0,0,0), 'a':(1,0,0,0,0), 'bc':(0,1,0,0,0),
    'de':(0,0,1,0,0), 'hl':(0,0,0,1,0), 'flags':(0,0,0,0,1),
    'mem-hl-zero':(0,0,0,0xd000,0), 'mem-hl-one':(0,0,0,0xd000,0),
    'mem-de-zero':(0,0,0xd100,0,0), 'mem-de-one':(0,0,0xd100,0,0)}
for a in single:
    sector, _, _ = m.generate(a)
    for kind, addr in (('hl',0xd000), ('de',0xd100)):
        setting = b'\x3e\x01\x32' + m.word(addr)
        assert (setting in sector[:0x80]) == (a[0] == f'3391-mem-{kind}-one')
assert {a[0] for a in arms if a[1]==['37c9','3391'] or a[1]==['369a','3391']}=={'37c9-then-3391','369a-then-3391'}
for arm in arms:
    s=json.loads((p/'summary'/f'{arm[0]}.json').read_text())
    assert all(x['開始']=='確認' and x['戻り']=='確認' for x in s['区間'])
    assert s['RAM']['判定']=='取得'
neg=json.loads((p/'summary/control.json').read_text())
pos=json.loads((p/'summary/positive.json').read_text())
assert neg['区間'][0]['I/O']==[]
assert pos['区間'][0]['送信長']==1 and ['D000','D000'] in pos['区間'][0]['書き込み番地範囲']
assert ['D000','D000'] in pos['RAM']['変化番地範囲']
arm=next(a for a in arms if a[0]=='37c9-then-37d2'); sector, markers, mm=m.generate(arm)
d=p/'mutation'; shutil.copytree(p/'raw'/arm[0],d)
io=(d/'io').read_text(); pattern=r'(\sOUT\s+007F\s+[0-9A-F]{2}\s+)'+f'{markers[1]:04X}'+r'$'
io,n=re.subn(pattern,r'\g<1>FFFF',io,flags=re.M); assert n==1
(d/'io').write_text(io); s=m.summarize(d,arm,markers,mm)
assert s['区間'][0]['戻り']=='欠測' and s['区間'][1]['開始']=='欠測'
# 後続の印もない場合だけ時間上限内の未帰還とする。
for pc in markers[2:]: io=re.sub(r'(\sOUT\s+007F\s+[0-9A-F]{2}\s+)'+f'{pc:04X}'+r'$',r'\g<1>FFFF',io,flags=re.M)
(d/'io').write_text(io); assert m.summarize(d,arm,markers,mm)['区間'][0]['戻り']=='時間上限内に戻らず'
(d/'io').write_text(io.replace('取りこぼし: 0件','取りこぼし: 1件',1))
assert m.summarize(d,arm,markers,mm)['区間'][0]['開始']=='欠測'
# 値自体を集計へ出さず、入力一致だけが変わる。
arm=next(a for a in arms if a[0]=='positive'); _, markers, mm=m.generate(arm)
d=p/'mutation2'; shutil.copytree(p/'raw/positive',d); io=(d/'io').read_text()
io,n=re.subn(r'(\sOUT\s+00FD\s+)5A',r'\g<1>00',io); assert n==1
(d/'io').write_text(io); s=m.summarize(d,arm,markers,mm)
assert s['区間'][0]['送信と入力の一致']['A'] is True
assert '5A' not in json.dumps(s) and '00FD' not in json.dumps(s)
# 自作媒体の完全一致だけを座標と判定する。
coord=m.coord_header_pattern(0xa1,3,1,7)
lines=io.splitlines(); inds=[i for i,l in enumerate(lines) if re.match(r'^\s*\d+\s+\d+\s+\d+\s+main\s+OUT\s+007D\s+[0-9A-F]{2}\s+C081$',l)]
assert len(inds)==2*0x2f00
for idx,v in zip(inds[0x2f00:0x2f00+256],coord): lines[idx]=re.sub(r'(\s007D\s+)[0-9A-F]{2}',lambda x:x[1]+f'{v:02X}',lines[idx])
(d/'io').write_text('\n'.join(lines)+'\n'); assert [3,1,7] in m.summarize(d,arm,markers,mm)['RAM']['自作媒体座標']
print('PASS: 54腕、対照、区間・書き込み、欠測、値非混入、自作媒体座標')
PY
