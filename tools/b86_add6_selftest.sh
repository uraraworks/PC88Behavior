#!/usr/bin/env bash
set -euo pipefail
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
repo="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONDONTWRITEBYTECODE=1 python3 - "$repo/tools" <<'PY'
import pathlib,sys,tempfile
sys.path.insert(0,sys.argv[1]); import b86_add6 as m
arms=dict(m.arms()); assert len(arms)==127
for a in arms.values():
    data,marks=m.generate(a); assert len(data)==256 and len(set(marks))==len(marks)
start=('OUT',0x7e,0,0xc015)
old=m.base.events
try:
    with tempfile.TemporaryDirectory() as t:
        p=pathlib.Path(t); a=arms['3391-base']; _,marks=m.generate(a)
        def mark(i): return ('OUT',0x7f,0,marks[i])
        m.base.events=lambda _: [start]+[mark(i) for i in range(9)]+[('OUT',0xfd,6,0x100),('OUT',0xfd,0xab,0x101),('IN',0xfc,0xcd,0x102),mark(9)]
        s=m.summarize(p,a,marks); assert s['区間'][-1]['要求見出し']==[{'先頭':'06','長さ':2,'完結':True}]; assert 'AB' not in str(s) and 'CD' not in str(s)
        m.base.events=lambda _: [start,mark(0),start,mark(0)]
        assert m.summarize(p,a,marks)['区間'][0]['戻り']=='戻らない（再起動）'
        m.base.events=lambda _: [start,mark(1)]
        assert '順序異常' in m.summarize(p,a,marks)['判定']
        m.base.events=lambda _: None
        assert '欠測' in m.summarize(p,a,marks)['判定']
        for name in ('3080-push-di-base','3080-empty-ei-a','6f6b-call-di-base','positive-call-ei-hl'):
            a=arms[name]; _,marks=m.generate(a); first=('OUT',0x7f,0,marks[0]); last=('OUT',0x7f,0,marks[1])
            m.base.events=lambda _: [start,first,('OUT',0xfd,0xab,0x1234),last]
            s=m.summarize(p,a,marks); assert s['戻り']=='確認' and 'AB' not in str(s)
            m.base.events=lambda _: [start,first,start,first]
            assert m.summarize(p,a,marks)['戻り']=='戻らない（再起動）'
            m.base.events=lambda _: [start,first]
            assert m.summarize(p,a,marks)['戻り']=='時間上限内未確認'
finally: m.base.events=old
print('PASS: 生成・印・再起動・欠測・値非出力の自己検査')
PY
