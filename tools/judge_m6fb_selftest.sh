#!/usr/bin/env bash
# 各固定判定・各総合判定・全関門偽を合成入力で検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
import copy,json,subprocess,sys
from pathlib import Path
repo,work=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo/'tools'))
import judge_m6fb as j

def item(status='derived',value=None):
    out={'status':status,'candidate_count':1 if status=='derived' or status in j.CASE_JUDGMENTS else 2 if status=='ambiguous' else 0}
    if status=='derived' or status in j.CASE_JUDGMENTS: out['value']=value or {'n':1}
    return out
def derived(e1='case_stored_as_given',statuses=None):
    statuses=statuses or {}; values={'E1':item(e1,{'G1':'U','G2':'L','G3':'L'})}
    values.update({f'E{i}':item(statuses.get(f'E{i}','derived'),{'n':i}) for i in range(2,9)})
    return {'schema':1,'derivations':values}
def measurement(reached=True):
    return {'schema':1,'runs':[{'arm':arm,'repetition':run,'reached':reached,
      'write_data_count':0,'changed_sector_count':0,'changed_byte_count':0}
      for arm in j.ARMS for run in (1,2)]}

checks={}; seen=set()
def record(name,d,m,want):
    counts,_=j.judge(d,m); present={key for key,value in counts.items() if value}
    seen.update(present); checks[name]=want in present

record('overall_derived',derived(),measurement(),'m6f_b_entry_fields_derived')
record('overall_incomplete_case',derived('case_other'),measurement(),'m6f_b_entry_fields_incomplete')
record('overall_incomplete_field',derived(statuses={'E2':'not_found'}),measurement(),'m6f_b_entry_fields_incomplete')
record('overall_inconclusive',derived(),measurement(False),'m6f_b_inconclusive')
for case in j.CASE_JUDGMENTS:
    record('case_'+case,derived(case),measurement(),case)
for status in j.STATUSES:
    record('status_'+status,derived(statuses={'E6':status}),measurement(),status)

# CLIの各関門偽は gate_failed だけを出す。
(work/'d.json').write_text(json.dumps(derived())); (work/'m.json').write_text(json.dumps(measurement()))
for failed in j.GATES:
    cmd=[sys.executable,str(repo/'tools/judge_m6fb.py'),'--derived',str(work/'d.json'),'--measurement',str(work/'m.json')]
    for gate in j.GATES: cmd += ['--gate',f'{gate}={"false" if gate==failed else "true"}']
    proc=subprocess.run(cmd,text=True,capture_output=True); body=json.loads(proc.stdout)
    present={row['judgment'] for row in body['judgments'] if row['present']}; seen.update(present)
    checks['gate_'+failed]=proc.returncode==1 and present=={'gate_failed'}

checks['all_registered']=seen==set(j.REGISTERED)
try:
    bad=derived(); bad['derivations']['E1']['status']='derived'; j.judge(bad,measurement())
    checks['E1_generic_derived_rejected']=False
except j.InputError:
    checks['E1_generic_derived_rejected']=True
try:
    bad=derived(); bad['derivations']['E6']={'status':'not_found','candidate_count':0,'reason':'unknown'}; j.judge(bad,measurement())
    checks['invalid_reason_rejected']=False
except j.InputError:
    checks['invalid_reason_rejected']=True

bad={key for key,value in checks.items() if not value}
if bad: raise SystemExit('NG集合 '+str(bad))
for target in checks:
    negative=dict(checks); negative[target]=False
    if {key for key,value in negative.items() if not value}!={target}: raise SystemExit('NG集合 '+target)
    mutant=dict(negative); mutant[target]=True
    if {key for key,value in mutant.items() if not value}=={target}: raise SystemExit('常時真変異 '+target)
print(f'judge_m6fb_selftest: 項目数={len(checks)}、陰性対照={len(checks)}、常時真変異={len(checks)}件拒否 OK')
print('全判定名・全総合判定・G1〜G8/G5b偽・E1と通常3分類の分離 OK')
PY
