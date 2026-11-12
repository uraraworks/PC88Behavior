#!/usr/bin/env bash
set -euo pipefail
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
unset PC88_CORE PC88_FRONTEND B86_FRAMES B86_TIMEOUT B86_ADD11_FILTER
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add11.XXXXXX")"; trap 'rm -rf "$work"' EXIT
bash "$repo/tools/b86_add11_run.sh" "$work/run"
PYTHONDONTWRITEBYTECODE=1 python3 - "$repo/tools" "$work/run" <<'PY'
import json,pathlib,sys
sys.path.insert(0,sys.argv[1]); import b86_add11 as m
arms=dict(m.arms()); assert len(arms)==8
rows=json.loads((pathlib.Path(sys.argv[2])/'summary.json').read_text())['腕']
for name,a in arms.items():
 assert len(m.generate(a)[0])==256
 r=rows[name]; assert r['戻り'] and r['模様と一致']==(a['pattern']=='a'),r
 assert r['戻り時IFF']==(a['irq']=='ei'),r
 assert not r['受信確認']
 if a['irq']=='ei': assert r['受信前の受け口回数']>0 and all(r['受信前のPCがROM内']),r
 else: assert r['受信前の受け口回数']==0,r
a=arms['di-short-a']; labels=m.generate(a)[1]; old=m.base.events
boot=('OUT',0x7e,0,labels['boot']); start=('OUT',0x7f,0,labels['start'])
irq=lambda v:('OUT',0x7a,v,0xc2c2+15)
end=[('OUT',0x7c,4,labels['iff']),('OUT',0x7d,0x35,labels['value'])]
try:
 m.base.events=lambda p:[boot,start,irq(1),irq(0),('IN',0xfc,0x35,0x1234),irq(1)]+end
 r=m.extract(pathlib.Path('.'),a); assert r['受信前の受け口回数']==2 and r['受信前のPCがROM内']==[True,False] and r['戻り時IFF'] and r['模様と一致']
 m.base.events=lambda p:[boot,start,irq(0),('OUT',0x7c,0,labels['iff']),('OUT',0x7d,0,labels['value'])]
 r=m.extract(pathlib.Path('.'),a); assert r['受信前の受け口回数']==1 and not r['模様と一致'] and not r['受信確認']
 m.base.events=lambda p:None
 assert m.extract(pathlib.Path('.'),a)['判定'].startswith('欠測')
finally: m.base.events=old
assert not list(pathlib.Path(sys.argv[2]).rglob('io'))
print('PASS: 8腕、受け口、ROM内外、受信前後、不一致、欠測、値なし')
PY
