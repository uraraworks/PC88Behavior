#!/usr/bin/env bash
set -euo pipefail
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
unset PC88_CORE PC88_FRONTEND B86_FRAMES B86_TIMEOUT B86_ADD10_FILTER B86_ADD10_OWN_ROM_DIR
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add10.XXXXXX")"; trap 'rm -rf "$work"' EXIT
B86_ADD10_FILTER='^(7071-(call|jp0|jp1|jp2)-(di|ei)-[0-3]|6f6b-call-di-[0-3]|3080-(none|r00b0)-0)$' bash "$repo/tools/b86_add10_run.sh" "$work/run"
PYTHONDONTWRITEBYTECODE=1 python3 - "$repo/tools" "$work/run" <<'PY'
import json,pathlib,sys,tempfile
sys.path.insert(0,sys.argv[1]); import b86_add10 as m
arms=dict(m.arms()); assert len(arms)==284
for a in arms.values(): assert len(m.generate(a)[0])==256
root=pathlib.Path(sys.argv[2]); result=json.loads((root/'summary.json').read_text())
for mode in ('call','jp0','jp1','jp2'):
 for irq in ('di','ei'):
  for n in range(4): assert result['腕'][f'7071-{mode}-{irq}-{n}']['戻り']=='確認'
for n in range(4):
 row=result['腕'][f'6f6b-call-di-{n}']; assert row['戻り']=='確認' and row['自作HL受け口到達']=={'HL':True,'DE':False,'BC':False}
assert result['腕']['3080-r00b0-0']['戻り']=='確認'
key=result['キー関係']['3080-r00b0-0']['E6D0+r']; assert key['入力行と一致'] and key['無押下と異なる'],key
assert any(x['番地']=='E6D0' for x in result['腕']['3080-r00b0-0']['RAM変化（前値既知）'])
assert not list(root.rglob('values.tmp')) and not list(root.rglob('mem'))
a=arms['7071-call-di-0']; marks=m.generate(a)[1]; oldev=m.base.events; oldmem=m.kb.parsemem
try:
 m.kb.parsemem=lambda *a:[]
 m.base.events=lambda p:[('OUT',0x7e,0,marks['boot']),('OUT',0x7f,0,marks['start']),('OUT',0x7e,0,marks['boot'])]
 with tempfile.TemporaryDirectory() as d:
  pathlib.Path(d,'mem').write_text('')
  row,_=m.extract(pathlib.Path(d),a); assert row['戻り']=='戻らない' and row['再起動']
 m.base.events=lambda p:None; assert m.extract(pathlib.Path('.'),a)[0]['判定'].startswith('欠測')
finally: m.base.events=oldev; m.kb.parsemem=oldmem
print('PASS: 全腕生成・自作対照・JP深さ・HL受け口・打鍵・再起動・欠測・値削除')
PY
