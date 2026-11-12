#!/usr/bin/env bash
set -euo pipefail
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
unset PC88_CORE PC88_FRONTEND B86_FRAMES B86_TIMEOUT B86_ADD7_OWN_ROM_DIR B86_ADD7_FILTER B86_ADD7_KEEP_IO
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add7.XXXXXX")"
trap 'rm -rf "$work"' EXIT
# 実行器と VSYNC 受け口を自作 ROM だけで試験する。
B86_ADD7_FILTER='^(control|positive)-(di|ei|irq)-(0|6)$|^3391-base-(same|changed|no369a)-(ret|wait)$' bash "$repo/tools/b86_add7_run.sh" "$work/run"
PYTHONDONTWRITEBYTECODE=1 python3 - "$repo/tools" "$work/run" <<'PY'
import json,pathlib,sys,tempfile
sys.path.insert(0,sys.argv[1]); import b86_add7 as m
arms=dict(m.arms()); assert len(arms)==186
for a in arms.values():
    data,marks=m.generate(a); assert len(data)==256 and len(set(marks.values()))==len(marks)
run=pathlib.Path(sys.argv[2]); report=json.loads((run/'summary.json').read_text())
for mode in ('di','ei','irq'):
    assert report['対照'][mode]['成立'],mode
    row=report['腕'][f'positive-{mode}-6']
    for index,reg in enumerate(('IY','IX','HL','DE','BC','AF')):
        assert row['ダミーとの一致'][reg]==[i==index for i in range(6)],(mode,reg)
    assert row['EI状態']==(mode=='ei')
    assert report['腕'][f'control-{mode}-6']['戻り']=='戻らない（再起動）'
assert all(not list((run/'raw'/name).glob('io*')) for name in report['腕'])
old=m.base.events
try:
 with tempfile.TemporaryDirectory() as t:
    path=pathlib.Path(t); a=arms['3391-base-changed-ret']; _,mark=m.generate(a)
    start=('OUT',0x7e,0,mark['boot']); begin=('OUT',0x7f,0,mark['start'])
    m.base.events=lambda _:[start,begin,('OUT',0x7b,0xab,0xc900),('OUT',0xfd,0xde,0x1234),('OUT',0x7f,0,mark['end'])]
    row=m.summarize(path,a,mark); assert row['自作コード到達']==['C900'] and row['戻り']=='確認'
    assert 'AB' not in json.dumps(row) and 'DE' not in json.dumps(row)
    m.base.events=lambda _:[start,begin,start]
    assert m.summarize(path,a,mark)['戻り']=='戻らない（再起動）'
    m.base.events=lambda _:None
    assert m.summarize(path,a,mark)['判定'].startswith('欠測')
    a=arms['3080-di-1']; _,mark=m.generate(a)
    m.base.events=lambda _:[('OUT',0x7e,0,mark['boot']),('OUT',0x7f,0,mark['start']),('OUT',0x7c,0,0x1234)]*20
    assert m.summarize(path,a,mark)['戻り']!='確認'
finally: m.base.events=old
print('PASS: 186腕の生成・対照・割り込み受理・再起動・値なし集計')
PY
