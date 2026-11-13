#!/usr/bin/env bash
set -euo pipefail
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
unset PC88_CORE PC88_FRONTEND B86_FRAMES B86_TIMEOUT B86_ADD12_FILTER B86_ADD12_OWN_ROM_DIR
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add12.XXXXXX")"; trap 'rm -rf "$work"' EXIT
PYTHONDONTWRITEBYTECODE=1 python3 - "$repo/tools" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]); import b86_add12 as m
a=dict(m.arms()); assert len(a)==45
for v in a.values(): assert len(m.generate(v)[0])==256
PY
B86_ADD12_FILTER='^(7071-port31-0|11df-a-0|3e0d-a-0)$' B86_FRAMES=15 bash "$repo/tools/b86_add12_run.sh" "$work/run"
python3 - "$work/run" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); s=json.loads((p/'summary.json').read_text())
for n in ('7071-port31-0','11df-a-0','3e0d-a-0'):
 assert s['腕'][n]['判定']=='取得' and s['腕'][n]['戻り']=='確認'
assert not list(p.rglob('values.tmp')) and not list(p.rglob('io')) and not list(p.rglob('rom'))
print('PASS: 全45腕生成・自作ROMの3腕・一時値削除')
PY
