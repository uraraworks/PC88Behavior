#!/usr/bin/env bash
# 合成署名・偽フロントエンドだけによるLOAD適合器の自己検査。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/load-conform-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
EXPECTED="$REPO/tools/load_conform_expected.tsv"
CANARY=LOAD_SCREEN_LEAK_6E71
ng() { printf 'NG %s\n' "$1" >&2; exit 1; }
mkdir "$WORK/rom"
printf 'synthetic\n' >"$WORK/rom/N88.ROM"

python3 - "$REPO" "$EXPECTED" "$WORK" <<'PY'
import copy,json,pathlib,sys
repo,expected,work=map(pathlib.Path,sys.argv[1:])
sys.path.insert(0,str(repo/'tools'))
import load_conform_check as check
import extract_load_conform_expected as extract
values=check.expected(expected)
for fmt,arms in extract.GROUPS:
    group={}
    for arm in arms:
        _,rows,load=values[arm]
        lines=[{'physical_row':r,'char_count':n,'sha256':h} for r,n,h in rows]
        summary=None if load is None else {'line_count':load[0],'char_count':load[1],'sha256':load[2]}
        group[arm]=[{'entry_lines':copy.deepcopy(lines),'load_screen':summary} for _ in range(2)]
    name='base.json' if fmt=='m6fi-observations-v1' else 'add2.json'
    (work/name).write_text(json.dumps({'format':fmt,'arms':group},sort_keys=True),encoding='ascii')
bad=json.loads((work/'base.json').read_text(encoding='ascii'))
bad['arms']['I-1'][1]['entry_lines'][0]['sha256']='0'*64
(work/'bad.json').write_text(json.dumps(bad,sort_keys=True),encoding='ascii')
PY
python3 "$REPO/tools/extract_load_conform_expected.py" "$WORK/base.json" "$WORK/add2.json" "$WORK/extracted.tsv" >"$WORK/extract.out" 2>"$WORK/extract.err" || ng 抽出
cmp -s "$EXPECTED" "$WORK/extracted.tsv" || ng 固定値
if python3 "$REPO/tools/extract_load_conform_expected.py" "$WORK/bad.json" "$WORK/add2.json" "$WORK/rejected.tsv" >"$WORK/reject.out" 2>"$WORK/reject.err"; then ng 2走不一致; fi

cat >"$WORK/fake.py" <<'PY'
#!/usr/bin/env python3
import hashlib,os,pathlib,sys
args=sys.argv[1:]
out=pathlib.Path(args[args.index('--out')+1])
arm=os.environ['LOAD_CONFORM_ARM']
source=pathlib.Path(os.environ['LOAD_FAKE_SOURCE'])
rows=[];active=None
for line in source.read_text(encoding='ascii').splitlines()[2:]:
    f=line.split('\t')
    if f[0]=='arm': active=f[1]
    elif f[0]=='row' and active==arm: rows.append((int(f[2]),int(f[3]),f[4]))
if arm in os.environ.get('LOAD_FAKE_BAD_ARMS','').split():
    r,n,h=rows[0];rows[0]=(r,n,('0' if h[0]!='0' else '1')+h[1:])
prompt_row=max((r for r,_,_ in rows),default=-1)+1
canary=os.environ['LOAD_FAKE_CANARY']
digest=hashlib.sha256(f'{prompt_row}\tOk\n'.encode()).hexdigest()
final=rows+[(prompt_row,2,digest)]
load=[(r,2,hashlib.sha256(f'{r}\tOk\n'.encode()).hexdigest()) for r in (0,1)]
def snap(name,values):
    lines=[f'snapshot_id\t{name}','physical_row\tchar_count\tsha256']
    lines += [f'{r}\t{n}\t{h}' for r,n,h in values]
    lines += [f'line_count\t{len(values)}',f'char_count\t{sum(n for _,n,_ in values)}',f'sha256\t{"3"*64}']
    return lines
output=[]
for name,values in [('baseline',[(0,len(canary),hashlib.sha256(f'0\t{canary}\n'.encode()).hexdigest())]),('load',load),('load_late',load),('final',final),('late',final)]:
    output+=snap(name,values)
out.write_text('\n'.join(output)+'\n',encoding='ascii')
PY
chmod +x "$WORK/fake.py"
run_fake() {
  local tag="$1" expect="$2" bad="$3" rc=0
  LOAD_CONFORM_FRONTEND="$WORK/fake.py" LOAD_CONFORM_CORE=dummy \
    LOAD_CONFORM_TEST_ROM_DIR="$WORK/rom" LOAD_CONFORM_EXPECTED="$expect" \
    LOAD_FAKE_SOURCE="$EXPECTED" LOAD_FAKE_BAD_ARMS="$bad" LOAD_FAKE_CANARY="$CANARY" \
    PC88_LOAD_CONFORM_WORK="$WORK/$tag.work" \
    bash "$REPO/tools/conform_load.sh" >"$WORK/$tag.out" 2>"$WORK/$tag.err" || rc=$?
  printf '%s' "$rc"
}
[ "$(run_fake all-ok "$EXPECTED" '')" -eq 0 ] || ng 偽フロントエンド正例
[ "$(awk -F '\t' '$2=="OK"{n++} END{print n+0}' "$WORK/all-ok.out")" -eq 8 ] || ng OK集合
cp "$EXPECTED" "$WORK/broken.tsv"
python3 - "$WORK/broken.tsv" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1]);lines=p.read_text(encoding='ascii').splitlines()
for i,line in enumerate(lines):
    if line.startswith('row\tI-1\t'):
        f=line.split('\t');f[4]=('0' if f[4][0]!='0' else '1')+f[4][1:];lines[i]='\t'.join(f);break
p.write_text('\n'.join(lines)+'\n',encoding='ascii')
PY
[ "$(run_fake one-broken "$WORK/broken.tsv" '')" -eq 1 ] || ng 期待値破損
[ "$(awk -F '\t' '$2=="NG"{print $1}' "$WORK/one-broken.out")" = I-1 ] || ng 破損腕
[ "$(run_fake fake-bad "$EXPECTED" 'E-1')" -eq 1 ] || ng 偽故障
[ "$(awk -F '\t' '$2=="NG"{print $1}' "$WORK/fake-bad.out")" = E-1 ] || ng 偽故障腕
if grep -R -qF "$CANARY" "$WORK"/*.out "$WORK"/*.err "$WORK"/*.work 2>/dev/null; then ng 漏えい; fi
printf '%s\n' "$CANARY" >"$WORK/leak.txt"
grep -qF "$CANARY" "$WORK/leak.txt" || ng 漏えい陰性対照
printf 'OK LOAD適合器: 2走・選択NG・漏えい陰性対照\n'

python3 - "$REPO/tools" "$WORK" <<'PY'
import hashlib,sys
from pathlib import Path
tools,work=map(Path,sys.argv[1:]);sys.path.insert(0,str(tools))
import compare_screen_signatures as css
import load_conform_check as check
def signature(rows):
    lines={r:css.LineSignature(n,h) for r,n,h in rows}
    return css.ScreenSignature(lines,len(lines),sum(x.char_count for x in lines.values()),'0'*64)
def invoke(rows):
    return check.entries(signature(rows))
digest=hashlib.sha256(b'0\tOk\n').hexdigest()
assert not invoke([(0,2,digest)])
for rows in ([],[(19,2,'0'*64)],[(0,2,'0'*64)],[(0,1,digest)],[(1,2,digest)]):
    try: invoke(rows)
    except ValueError: pass
    else: raise SystemExit('NG 入力待ちOk陰性対照')
PY
printf 'OK 入力待ちOk: 欠落・非Ok・文字数・行番号の陰性対照\n'
