#!/usr/bin/env bash
set -euo pipefail
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
unset PC88_CORE PC88_FRONTEND B86_FRAMES B86_TIMEOUT B86_ADD9_FILTER
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add9.XXXXXX")"; trap 'rm -rf "$work"' EXIT
B86_ADD9_FILTER='^(37c9|37d2|3847|3391|369a)-00-[0-3]$' bash "$repo/tools/b86_add9_run.sh" "$work/run"
PYTHONDONTWRITEBYTECODE=1 python3 - "$repo/tools" "$work/run" <<'PY'
import json,pathlib,sys,tempfile
sys.path.insert(0,sys.argv[1]); import b86_add9 as m
arms=dict(m.arms()); assert len(arms)==160
for a in arms.values(): assert len(m.generate(a)[0])==256
r=json.loads((pathlib.Path(sys.argv[2])/'summary.json').read_text())
for t in ('37c9','37d2','3847','3391','369a'):
 for n in range(4):
  row=r['腕'][f'{t}-00-{n}']; assert row['戻り']=='確認',row
  if t=='3391': assert row['自作コード到達'] is True
 for reg in ('A','BC','DE','HL','IX','IY','F','IFF'):
  assert r['組'][t+'-00']['関係'][reg]['不変'] is True,(t,reg)
assert r['組']['37c9-00']['関係']['SP']['不変'] is True
assert r['組']['3391-00']['関係']['SP']['不変'] is False
assert m.relations([(1,3),(2,4)])['入力加算一定']
assert not m.relations([(1,3),(2,5)])['入力加算一定']
assert m.relations([(1,3)])['定数'] is None
assert not list(pathlib.Path(sys.argv[2]).rglob('values.tmp'))
a=arms['37c9-00-0']; marks=m.generate(a)[1]; old=m.base.events
try:
 m.base.events=lambda p:[('OUT',0x7e,0,marks['boot']),('OUT',0x7f,0,marks['start']),('OUT',0x7e,0,marks['boot'])]
 assert m.extract(pathlib.Path('.'),a)[0]['戻り']=='戻らない'
 m.base.events=lambda p:None
 assert m.extract(pathlib.Path('.'),a)[0]['判定'].startswith('欠測')
finally: m.base.events=old
print('PASS: 160腕生成、対照20腕、関係、飛び先、再起動、欠測、値なし')
PY
