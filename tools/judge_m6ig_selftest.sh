#!/usr/bin/env bash
# m6i-g判定器の総合4種、2走不一致、関門偽を検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
import copy,json,subprocess,sys,tempfile
from pathlib import Path
repo,scratch=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo/'tools'))
import judge_m6ig as j
D='1'*64
def dataset(l0,l1,gn=False,l2=True):
    outcomes={'G-N':gn,'G-L0':l0,'G-L1':l1,'G-L2':l2}; result={}
    for arm in j.ARMS:
        row={'arm':arm,'fault_injection':None,'reached':True,
             'result':'success' if outcomes[arm] else 'failure','rom_set_sha256':D}
        result[arm]=[copy.deepcopy(row),copy.deepcopy(row)]
    return result
def run(rows,failed=None):
    with tempfile.TemporaryDirectory(dir=scratch) as raw:
        tmp=Path(raw); cmd=[sys.executable,str(repo/'tools/judge_m6ig.py')]
        for n in range(1,11): cmd += ['--gate',f'G{n}={"false" if failed==f"G{n}" else "true"}']
        i=0
        for arm in j.ARMS:
            for row in rows[arm]:
                p=tmp/f'{i}.json'; p.write_text(json.dumps(row)); cmd += ['--result',str(p)]; i+=1
        proc=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    body=json.loads(proc.stdout); present={r['judgment'] for r in body['judgments'] if r['present']}
    return proc.returncode,present
cases={
 'm6i_g_elapsed_time_only':dataset(True,False),
 'm6i_g_ab_sufficient':dataset(False,True),
 'm6i_g_c_required':dataset(False,False),
 'm6i_g_inconclusive':dataset(False,True,gn=True),
}
for expected,rows in cases.items():
    rc,present=run(rows)
    if rc!=0 or expected not in present or len(set(j.OVERALL)&present)!=1: raise SystemExit('総合 '+expected)
rows=dataset(False,True); rows['G-L1'][1]['result']='failure'
rc,present=run(rows)
if rc!=0 or 'unreached' not in present or 'm6i_g_inconclusive' not in present: raise SystemExit('2走不一致')
rc,present=run(dataset(False,True),'G10')
if rc!=1 or 'gate_failed' not in present: raise SystemExit('関門偽')
print('judge_m6ig_selftest: 項目数=6、総合4種・2走不一致・関門偽 OK')
PY
