#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO" <<'PY'
import copy,json,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'tools'))
import judge_m6ik as j

def dataset(k00='cylinder',k01='cylinder',f0='logical',f1='logical'):
    selected={'K-00':k00,'K-01':k01,'K-F0':f0,'K-F1':f1,'K-M1':'logical','K-FR':'other'}
    out={}
    for arm in j.ARMS:
        rows=[]
        for n in range(1,7):
            c='agree' if n in (1,6) and arm!='K-FR' else selected[arm]
            rows.append({'row':n,'classification':c,'success':'success',
                         'index_disagree':False,'stamp':[0xA1,0,0,1],
                         'read_data_count':1,'status':[{'st0':[],'st1':[]}]})
        run={'arm':arm,'reached':True,'pre_send_fd_count':0,'rows':rows}
        out[arm]=[copy.deepcopy(run),copy.deepcopy(run)]
    return out

cases=[(dataset(),'m6i_k_conversion_by_17'),
       (dataset(f0='cylinder'),'m6i_k_conversion_needs_both'),
       (dataset(k00='mixed',f0='mixed'),'m6i_k_conversion_by_p1_after_17'),
       (dataset(f0='cylinder',f1='cylinder'),'m6i_k_no_conversion'),
       (dataset(k00='mixed',f0='mixed',f1='mixed'),'m6i_k_other')]
for data,want in cases: assert j.judge(data)['judgment']==want,(want,j.judge(data))
d=dataset(); d['K-FR'][0]['rows'][0]['classification']='agree'; d['K-FR'][1]['rows'][0]['classification']='agree'
assert j.judge(d)['judgment']=='m6i_k_measurement_blind'
d=dataset(); d['K-F0'][0]['rows'][2]['index_disagree']=d['K-F0'][1]['rows'][2]['index_disagree']=True
assert j.judge(d)['judgment']=='m6i_k_inconclusive'
d=dataset(); d['K-00'][0]['rows'][0]['success']=d['K-00'][1]['rows'][0]['success']='failed'
assert j.judge(d)['judgment']=='m6i_k_inconclusive'
d=dataset(); d['K-00'][1]['rows'][1]['classification']='logical'
assert j.judge(d)['arms']['K-00']=='unreached'
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'run.json'; path.write_text(json.dumps({'arm':'K-00','dry_run':True}))
    for bad_gate in j.GATES:
        args=[sys.executable,str(Path(sys.argv[1])/'tools/judge_m6ik.py')]
        for gate in j.GATES: args += ['--gate',gate+'='+('false' if gate==bad_gate else 'true')]
        proc=subprocess.run(args,capture_output=True,text=True)
        assert proc.returncode==1 and json.loads(proc.stdout)['judgment']=='gate_failed'
    args=[sys.executable,str(Path(sys.argv[1])/'tools/judge_m6ik.py')]
    for gate in j.GATES: args += ['--gate',gate+'=true']
    proc=subprocess.run(args+['--result',str(path)],capture_output=True,text=True)
    assert proc.returncode==2 and json.loads(proc.stdout)['judgment']=='gate_failed'
print('judge_m6ik_selftest: 総合8名・2走不一致・指標不一致 OK')
PY
