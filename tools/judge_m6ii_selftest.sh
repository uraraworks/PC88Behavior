#!/usr/bin/env bash
# m6i-i判定器の全腕・全総合名・関門偽を合成入力で検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
import copy,json,subprocess,sys
from pathlib import Path
repo,work=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo/'tools'))
import judge_m6ii as j
def rows(kind='row_match',retry=False):
    return [{'row':n,'result':kind,'entry_count':2 if retry and n==8 else 1,'retried':retry and n==8} for n in range(1,12)]
def dataset():
    values={}
    for arm in j.ARMS:
        kind='row_match' if arm=='I-S' else 'row_mismatch'
        rr=rows(kind,retry=arm=='I-F-RETRY')
        run={'arm':arm,'reached':True,'rows':rr}
        values[arm]=[copy.deepcopy(run),copy.deepcopy(run)]
    return values
def judged(values): return j.judge(values)
checks={}
seen=set()
counts,arms=judged(dataset())
seen.update(k for k,v in counts.items() if v); seen.update(arms.values())
checks['verified']=counts['m6i_i_general_read_verified']==1
checks['all_match']=arms['I-S']=='sweep_all_match'
checks['fault_detected']=all(arms[x]=='fault_detected' for x in j.ARMS[1:])
d=dataset(); d['I-S'][0]['rows'][0]['result']=d['I-S'][1]['rows'][0]['result']='row_no_data'; counts,arms=judged(d)
seen.update(k for k,v in counts.items() if v); seen.update(arms.values())
checks['wrong']=counts['m6i_i_general_read_wrong']==1 and arms['I-S']=='sweep_mismatch' and counts['row_no_data']>0
d=dataset();
for run in d['I-F-H']: run['rows'][1]['result']='row_match'
counts,arms=judged(d); checks['blind']=counts['m6i_i_measurement_blind']==1 and arms['I-F-H']=='fault_missed'
seen.update(k for k,v in counts.items() if v); seen.update(arms.values())
d=dataset(); d['I-F-D'][0]['reached']=d['I-F-D'][1]['reached']=False
counts,arms=judged(d); checks['inconclusive']=counts['m6i_i_inconclusive']==1 and arms['I-F-D']=='unreached'
seen.update(k for k,v in counts.items() if v); seen.update(arms.values())
d=dataset()
for run in d['I-F-RETRY']:
    for row in run['rows']: row['entry_count']=1
counts,arms=judged(d); checks['not_exercised']=arms['I-F-RETRY']=='fault_not_exercised'
seen.update(k for k,v in counts.items() if v); seen.update(arms.values())
d=dataset(); d['I-S'][1]['rows'][0]['result']='row_mismatch'; counts,arms=judged(d)
checks['two_run_disagree']=arms['I-S']=='unreached' and counts['m6i_i_inconclusive']==1
seen.update(k for k,v in counts.items() if v); seen.update(arms.values())

# CLIのG1〜G10偽を各1回ずつ通し、必ずgate_failedだけになる。
for failed in range(1,11):
    cmd=[sys.executable,str(repo/'tools/judge_m6ii.py')]
    for n in range(1,11): cmd += ['--gate',f'G{n}={"false" if n==failed else "true"}']
    p=subprocess.run(cmd,text=True,capture_output=True); body=json.loads(p.stdout)
    present={x['judgment'] for x in body['judgments'] if x['present']}
    seen.update(present)
    checks['gate_'+str(failed)]=p.returncode==1 and present=={'gate_failed'}
checks['all_registered']=seen==set(j.REGISTERED)
if not all(checks.values()): raise SystemExit('NG: '+str({k for k,v in checks.items() if not v}))
for target in checks:
    negative=dict(checks); negative[target]=False
    if {k for k,v in negative.items() if not v}!={target}: raise SystemExit('NG集合 '+target)
    mutant=dict(negative); mutant[target]=True
    if {k for k,v in mutant.items() if not v}=={target}: raise SystemExit('常時真変異 '+target)
print(f"judge_m6ii_selftest: 項目数={len(checks)}、陰性対照={len(checks)}、常時真変異={len(checks)}件拒否 OK")
print('総合4種・腕別2種・故障3種・G1-G10偽 OK')
PY
