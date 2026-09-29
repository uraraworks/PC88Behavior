#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO" <<'PY'
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / 'tools'))
import judge_m6ik_add1 as j

assert j.preflight() == []

def dataset():
    selected = {'K-00':'cylinder', 'K-01':'cylinder', 'K-F0':'logical',
                'K-F1':'logical', 'K-M1':'logical', 'K-FR':'other'}
    out = {}
    for arm in j.ARMS:
        rows = []
        for n in range(1, 7):
            classification = 'agree' if n in (1, 6) and arm != 'K-FR' else selected[arm]
            if arm == 'K-M1' and n in (3, 4): classification = 'cylinder'
            rows.append({'row':n, 'classification':classification,
                         'success':'failed' if arm in j.P1_ZERO else 'success',
                         'index_disagree':False, 'stamp':[1,2,3,4],
                         'read_data_count':1, 'status':[{'st0':[], 'st1':[]}]})
        run = {'arm':arm, 'reached':True, 'requests_sent':6,
               'pre_send_fd_count':0, 'rows':rows}
        out[arm] = [copy.deepcopy(run), copy.deepcopy(run)]
    return out

def change_both(d, arm, row, key, value):
    for run in d[arm]: run['rows'][row-1][key] = value

base = dataset()
result = j.judge(base)
assert result['judgment'] == 'm6i_k_conversion_by_17'
assert result['success_judgment'] == 'p1_success_split'
assert result['m1_bit0_drive1'] is True
assert set(result['pre_send_fd_count_by_arm']) == set(j.ARMS)

# G10(a): 対照の成否は解釈判定に影響しない。
d = dataset(); change_both(d, 'K-01', 1, 'success', 'failed')
assert j.judge(d)['arms']['K-01'] == 'cylinder'
assert j.judge(d)['judgment'] == 'm6i_k_conversion_by_17'

# G10(b): 対照の分類3種はどれも失敗。
for classification in ('no_read', 'other', 'index_disagree'):
    d = dataset()
    if classification == 'index_disagree':
        change_both(d, 'K-00', 1, 'index_disagree', True)
        assert j.judge(d)['arms']['K-00'] == 'control_failed'
    else:
        change_both(d, 'K-00', 1, 'classification', classification)
        assert j.judge(d)['arms']['K-00'] == 'control_failed'
    assert j.judge(d)['judgment'] == 'm6i_k_inconclusive'

# G10(c)(d): 1行だけ反転しても副判定は other。
for arm, value in (('K-00', 'success'), ('K-F1', 'failed')):
    d = dataset(); change_both(d, arm, 2, 'success', value)
    assert j.judge(d)['success_judgment'] == 'p1_success_other'

# G10(e): logical が0本なら P1 解釈判定にしない。
d = dataset()
for arm in j.ARMS[:4]:
    for n in range(2, 6): change_both(d, arm, n, 'classification', 'cylinder')
assert j.judge(d)['judgment'] == 'm6i_k_no_conversion'

# G10(f): 故障注入の other 以外は盲目、副判定は空。
d = dataset(); change_both(d, 'K-FR', 2, 'classification', 'logical')
assert j.judge(d)['judgment'] == 'm6i_k_measurement_blind'
assert j.judge(d)['success_judgment'] is None

# G10(g): 個数、欠落、2走の任意欄不一致。
d = dataset(); del d['K-00'][1]
assert j.judge(d)['judgment'] == 'm6i_k_inconclusive'
d = dataset(); del d['K-00']
assert j.judge(d)['judgment'] == 'm6i_k_inconclusive'
d = dataset(); d['K-00'][1]['rows'][2]['read_data_count'] = 2
assert j.judge(d)['judgment'] == 'm6i_k_inconclusive'

with tempfile.TemporaryDirectory() as td:
    temp = Path(td)
    paths = []
    for arm in j.ARMS:
        for n, run in enumerate(base[arm], 1):
            path = temp / f'{arm}-{n}.json'
            path.write_text(json.dumps(run))
            paths.extend(['--result', str(path)])
    cmd = [sys.executable, str(root/'tools/judge_m6ik_add1.py')]
    proc = subprocess.run(cmd + paths, capture_output=True, text=True)
    assert proc.returncode == 0 and json.loads(proc.stdout)['judgment'] == 'm6i_k_conversion_by_17'
    proc = subprocess.run(cmd + paths[:-2], capture_output=True, text=True)
    assert proc.returncode == 0 and json.loads(proc.stdout)['judgment'] == 'm6i_k_inconclusive'
    proc = subprocess.run(cmd + paths[:-2] + paths[:2], capture_output=True, text=True)
    assert proc.returncode == 0 and json.loads(proc.stdout)['judgment'] == 'm6i_k_inconclusive'

    # G11/G12: 一時的な複製を壊し、結果ファイルは存在しないパスでも先に停止。
    mirror = temp/'mirror'
    for rel, _ in j.INSTRUMENTS:
        target = mirror/rel; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/rel, target)
    frozen = mirror/'tools/m6ik_add1_frozen.tsv'
    shutil.copyfile(root/'tools/m6ik_add1_frozen.tsv', frozen)
    mirror_judge = mirror/'tools/judge_m6ik_add1.py'
    shutil.copyfile(root/'tools/judge_m6ik_add1.py', mirror_judge)
    (mirror/j.INSTRUMENTS[0][0]).write_bytes(b'changed')
    assert j.preflight(mirror) == ['G11']
    proc = subprocess.run([sys.executable, str(mirror_judge), '--result', str(temp/'missing.json')],
                          capture_output=True, text=True)
    assert proc.returncode == 1 and json.loads(proc.stdout)['failed_gates'] == ['G11']
    shutil.copyfile(root/j.INSTRUMENTS[0][0], mirror/j.INSTRUMENTS[0][0])
    frozen.write_text(frozen.read_text().replace('p1_success_split', 'p1_success_other', 1))
    assert j.preflight(mirror) == ['G12']
    proc = subprocess.run([sys.executable, str(mirror_judge), '--result', str(temp/'missing.json')],
                          capture_output=True, text=True)
    assert proc.returncode == 1 and json.loads(proc.stdout)['failed_gates'] == ['G12']
    assert j.preflight() == []
    proc = subprocess.run(cmd + ['--result', str(temp/'missing.json'), '--gate', 'G1=false'],
                          capture_output=True, text=True)
    assert proc.returncode == 1 and json.loads(proc.stdout)['judgment'] == 'gate_failed'

print('judge_m6ik_add1_selftest: G10(a)-(g), G11, G12 OK')
PY
