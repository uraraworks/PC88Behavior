#!/usr/bin/env bash
set -euo pipefail
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
unset PC88_CORE PC88_FRONTEND B86_FRAMES B86_TIMEOUT B86_ADD13_FILTER B86_ADD13_OWN_ROM_DIR
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add13.XXXXXX")"; trap 'rm -rf "$work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 - "$repo/tools" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]); import b86_add13 as m
a=dict(m.arms()); assert 0xe700 not in m.addresses()
assert len(a)==2*(1+(len(m.addresses())+1)*len(m.VALUES))-len(m.VALUES)+len(m.SHADOW_MASKS)
assert [v['value'] for v in a.values() if v['target']=='7071' and v['addr']==0xe6c2] == list(m.SHADOW_MASKS)
for name,v in a.items():
 if v['target']=='7071':
  data, labels=m.generate(v)
  assert bytes.fromhex('d3 31') not in data[labels['start']-0xc000:labels['end']-0xc000]
  assert (bytes.fromhex('3a c2 e6 ee') in data) == (v['addr']==0xe6c2)
for v in a.values(): assert len(m.generate(v)[0])==256
r=m.relation([(0,0),(1,1),(2,2),(255,255)])
assert r['入力と一致'] and '0' in r['ビット対応候補']['0']
assert m.relation([(0,42),(1,42)])['判定'].startswith('定数')
PY
B86_ADD13_FILTER='^(7071-base|7071-e6c2-01|3e0d-e6c4-01)$' B86_FRAMES=15 bash "$repo/tools/b86_add13_run.sh" "$work/run"
python3 - "$work/run" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); s=json.loads((p/'summary.json').read_text())
for n in ('7071-base','7071-e6c2-01','3e0d-e6c4-01'):
 assert s['腕'][n]['判定']=='取得' and s['腕'][n]['戻り']=='確認', s['腕'][n]
assert not any(p.rglob('values.tmp')) and not any(p.rglob('io')) and not any(p.rglob('rom'))
print('PASS: 全腕生成・自作ROM 3腕・関係判定・一時値削除')
PY
