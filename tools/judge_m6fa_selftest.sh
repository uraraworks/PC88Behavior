#!/usr/bin/env bash
# 各固定判定、2走不一致、G1〜G7偽を合成入力で検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
import copy,json,subprocess,sys
from pathlib import Path
repo,work=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo/'tools'))
import judge_m6fa as j
def item(status='derived',value=None):
    x={'status':status,'candidate_count':1 if status=='derived' else 2 if status=='ambiguous' else 0}
    if status=='derived': x['value']=value or {'n':1}
    return x
def derived(statuses=None):
    statuses=statuses or {}
    rows=[]
    for run in (1,2): rows.append({'repetition':run,'derivations':{k:item(statuses.get(k,'derived'),{'n':int(k[1:])}) for k in j.DERIVATIONS}})
    return {'schema':1,'runs':rows}
def measurement(reached=True):
    return {'schema':1,'runs':[{'arm':a,'repetition':r,'reached':reached,
      'write_data_count':0,'changed_sector_count':0,'changed_byte_count':0}
      for a in j.ARMS for r in (1,2)]}
checks={}; seen=set()
def record(name,d,m,present):
    counts,cons=j.judge(d,m); got={k for k,v in counts.items() if v}; seen.update(got)
    checks[name]=present in got; return counts,cons
record('located',derived(),measurement(),'m6f_a_directory_located')
record('not_found',derived({'D1':'not_found'}),measurement(),'m6f_a_directory_ambiguous')
record('ambiguous',derived({'D2':'ambiguous'}),measurement(),'m6f_a_directory_ambiguous')
record('unreached',derived(),measurement(False),'m6f_a_inconclusive')
d=derived(); d['runs'][1]['derivations']['D3']['value']={'n':99}
counts,cons=record('two_run_disagree',d,measurement(),'m6f_a_directory_ambiguous')
checks['two_run_is_ambiguous']=cons['D3']['status']=='ambiguous'
seen.update(x['status'] for x in cons.values())

# not_foundの境界理由は2走で一致すれば保存し、理由の不一致はambiguousへ倒す。
hidden=item('not_found'); hidden['reason']='old_values_withheld'
checks['withheld_reason_preserved']=j.consensus(hidden,copy.deepcopy(hidden))=={
    'status':'not_found','candidate_count':0,'reason':'old_values_withheld'}
checks['withheld_reason_disagree']=j.consensus(hidden,item('not_found'))['status']=='ambiguous'
try:
    bad_reason=copy.deepcopy(hidden); bad_reason['reason']='unknown'; j.consensus(bad_reason,bad_reason)
    checks['invalid_reason_rejected']=False
except j.InputError:
    checks['invalid_reason_rejected']=True

# CLIの各関門偽はgate_failedだけを出す。
(work/'d.json').write_text(json.dumps(derived())); (work/'m.json').write_text(json.dumps(measurement()))
for failed in range(1,8):
    cmd=[sys.executable,str(repo/'tools/judge_m6fa.py'),'--derived',str(work/'d.json'),'--measurement',str(work/'m.json')]
    for n in range(1,8): cmd += ['--gate',f'G{n}={"false" if n==failed else "true"}']
    p=subprocess.run(cmd,text=True,capture_output=True); body=json.loads(p.stdout)
    present={x['judgment'] for x in body['judgments'] if x['present']}; seen.update(present)
    checks[f'gate_{failed}']=p.returncode==1 and present=={'gate_failed'}
checks['all_registered']=seen==set(j.REGISTERED)
bad={k for k,v in checks.items() if not v}
if bad: raise SystemExit('NG: '+str(bad))
for target in checks:
    negative=dict(checks); negative[target]=False
    if {k for k,v in negative.items() if not v}!={target}: raise SystemExit('NG集合 '+target)
    mutant=dict(negative); mutant[target]=True
    if {k for k,v in mutant.items() if not v}=={target}: raise SystemExit('常時真変異 '+target)
print(f"judge_m6fa_selftest: 項目数={len(checks)}、陰性対照={len(checks)}、常時真変異={len(checks)}件拒否 OK")
print('全判定名・G1〜G7偽・2走不一致→ambiguous OK')
PY
