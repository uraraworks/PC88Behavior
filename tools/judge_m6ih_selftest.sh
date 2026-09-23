#!/usr/bin/env bash
# m6i-h判定器の総合3種、副問2種、2走不一致、関門偽を検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
import copy,json,subprocess,sys,tempfile
from pathlib import Path
repo,scratch=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo/'tools'))
import judge_m6ih as j
D='1'*64
def dataset(ha=True,hb=True,hn=False,hw=True):
    outcomes={'H-N':hn,'H-W':hw,'H-A':ha,'H-B':hb}; result={}
    for arm in j.ARMS:
        row={'arm':arm,'fault_injection':None,'reached':True,
             'result':'success' if outcomes[arm] else 'failure','rom_set_sha256':D}
        result[arm]=[copy.deepcopy(row),copy.deepcopy(row)]
    return result
def run(rows,failed=None):
    with tempfile.TemporaryDirectory(dir=scratch) as raw:
        tmp=Path(raw); cmd=[sys.executable,str(repo/'tools/judge_m6ih.py')]
        for n in range(1,11): cmd += ['--gate',f'G{n}={"false" if failed==f"G{n}" else "true"}']
        i=0
        for arm in j.ARMS:
            for row in rows[arm]:
                p=tmp/f'{i}.json'; p.write_text(json.dumps(row)); cmd += ['--result',str(p)]; i+=1
        proc=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    body=json.loads(proc.stdout); return proc.returncode,{r['judgment'] for r in body['judgments'] if r['present']}
for expected,rows in [
 ('m6i_h_no_wait_sufficient',dataset(True,True)),
 ('m6i_h_wait_required',dataset(False,True)),
 ('m6i_h_inconclusive',dataset(True,True,hn=True))]:
    rc,p=run(rows)
    if rc or expected not in p or len(set(j.OVERALL)&p)!=1: raise SystemExit(expected)
for expected,rows in [('m6i_h_retry_without_send_sufficient',dataset(hb=True)),
                      ('m6i_h_retry_without_send_insufficient',dataset(hb=False))]:
    rc,p=run(rows)
    if rc or expected not in p or len(set(j.SECONDARY)&p)!=1: raise SystemExit(expected)
rows=dataset(); rows['H-A'][1]['result']='failure'; rc,p=run(rows)
if rc or 'unreached' not in p or 'm6i_h_inconclusive' not in p: raise SystemExit('2走不一致')
rc,p=run(dataset(),failed='G10')
if rc!=1 or 'gate_failed' not in p: raise SystemExit('関門偽')
print('judge_m6ih_selftest: 項目数=7、総合3種・副問2種・2走不一致・関門偽 OK')
PY
