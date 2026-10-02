#!/usr/bin/env bash
# 公式ROMも測定も使わず、偽の結果JSONで照合器の検出力を確認する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bash -n "$REPO/tools/conform_killname.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/killname-conform-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO/tools" "$WORK" <<'PY'
import copy,json,subprocess,sys
from pathlib import Path
tools,work=map(Path,sys.argv[1:]);sys.path.insert(0,str(tools))
import killname_conform_check as check
import m6fk_judge as judge
expected=tools/'killname_conform_expected.tsv'
values=check.load(expected)
observations={arm:[dict(candidates=[value],g8_max_position=159,g11_input_ready=True) for _ in range(2)]
              for arm,value in values.items()}
good=dict(schema=1,frontend_launch_count=20,observations=observations,judgment=judge.combine(observations))
def run(root,tag,rc):
    path=work/(tag+'.json');path.write_text(json.dumps(root),encoding='ascii')
    p=subprocess.run([sys.executable,str(tools/'killname_conform_check.py'),'compare',str(expected),str(path)],capture_output=True,text=True)
    if p.returncode != rc:raise SystemExit('NG '+tag)
    return p.stdout
assert run(good,'good',0).count('\tOK\n')==10
for arm in values:
    bad=copy.deepcopy(good)
    alternatives=[x for x in judge.candidate_ids()[arm] if x != values[arm]]
    for row in bad['observations'][arm]:row['candidates']=[alternatives[0]]
    bad['judgment']=judge.combine(bad['observations'])
    output=run(bad,arm,1)
    assert output.count('\tNG\n')==1 and f'{arm}\tNG\n' in output
for tag in ('missing','extra','forged','unready','range','launches'):
    bad=copy.deepcopy(good)
    if tag=='missing':del bad['observations']['K-1']
    elif tag=='extra':bad['observations']['K-0']=bad['observations']['K-1']
    elif tag=='forged':bad['judgment']['judgments']['K-1']='other'
    elif tag=='unready':bad['observations']['K-1'][0]['g11_input_ready']=False
    elif tag=='range':bad['observations']['K-1'][0]['g8_max_position']=160
    else:bad['frontend_launch_count']=19
    run(bad,tag,2)
bad=copy.deepcopy(good);bad['observations']['N-1'][1]['extra']=True
bad['judgment']=judge.combine(bad['observations'])
run(bad,'two-runs',1)
PY
printf 'OK KILL/NAME照合器: 全10腕、判定改変10件・集合/2走/ゲート陰性対照\n'

python3 - "$REPO/tools" "$WORK" <<'PY'
import hashlib,sys
from pathlib import Path
tools,work=map(Path,sys.argv[1:]);sys.path.insert(0,str(tools))
import compare_screen_signatures as css
import killname_conform_check as check
def signature(rows):
    lines={r:css.LineSignature(n,h) for r,n,h in rows}
    return css.ScreenSignature(lines,len(lines),sum(x.char_count for x in lines.values()),'0'*64)
def invoke(rows):
    return check.entry_lines(signature(rows))
digest=hashlib.sha256(b'0\tOk\n').hexdigest()
assert not invoke([(0,2,digest)])
for rows in ([],[(19,2,'0'*64)],[(0,2,'0'*64)],[(0,1,digest)],[(1,2,digest)]):
    try: invoke(rows)
    except ValueError: pass
    else: raise SystemExit('NG 入力待ちOk陰性対照')
PY
printf 'OK 入力待ちOk: 欠落・非Ok・文字数・行番号の陰性対照\n'
