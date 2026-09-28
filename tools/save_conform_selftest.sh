#!/usr/bin/env bash
# 合成D88・偽フロントエンドだけで SAVE 適合器の正例と陰性対照を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/save-conform-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
CANARY=SAVE_BODY_LEAK_5C91
FAT_CANARY=FAT_TAIL_LEAK_7F2A
ng() { printf 'NG %s\n' "$1" >&2; exit 1; }
mkdir "$WORK/rom"
printf 'synthetic\n' >"$WORK/rom/N88.ROM"
EXPECTED="$REPO/tools/save_conform_expected.tsv"
python3 "$REPO/tools/save_conform_check.py" validate "$EXPECTED" >/dev/null || ng 期待値
python3 - "$EXPECTED" "$WORK" "$REPO/tools" <<'PY'
import copy,json,pathlib,sys
expected,work,tools=map(pathlib.Path,sys.argv[1:]);sys.path.insert(0,str(tools))
import save_conform_check as check
values=check.load(expected)
classes={'J-1':'no_line','J-2':'overwrite_same_slot_frees_old',
         'J-3':'first_free_in_2_5_order','J-4':'error_61',
         'J-5':'error_68','J-6':'waits_for_media'}
groups=({}, {})
for arm,fields in values.items():
    entries=[]
    for entry in fields['entries'].split(','):
        if not entry:continue
        name,pos,tail=entry.split(':')
        entries.append({'name':name,'position':int(pos),'bytes9_15':list(bytes.fromhex(tail))})
    lines=[]
    for line in fields['screen'].split(','):
        if not line:continue
        row,count,digest=line.split(':')
        lines.append({'physical_row':int(row),'char_count':int(count),'sha256':digest})
    run={'g8_max_position':159,'entries':entries,'screen_lines':lines,
         'candidates':[classes[arm]],'newly_used_units':[72] if arm in ('J-1','J-2','J-3') else []}
    if arm in ('J-1','J-2'):run['body_matches_2_6']=True
    if arm in ('J-4','J-5'):run['media_unchanged']=True
    if arm=='J-6':run['preinsert_screen_lines']=[]
    groups[0 if arm in ('J-1','J-2','J-3') else 1][arm]=[copy.deepcopy(run),copy.deepcopy(run)]
for name,group in zip(('base','add'),groups):
    (work/f'{name}.json').write_text(json.dumps({'schema':1,'observations':group}),encoding='ascii')
groups[0]['J-1'][1]['entries'][0]['position']=2
(work/'bad.json').write_text(json.dumps({'schema':1,'observations':groups[0]}),encoding='ascii')
PY
python3 "$REPO/tools/save_conform_check.py" freeze "$WORK/base.json" "$WORK/add.json" \
  "$WORK/extracted.tsv" >"$WORK/freeze.out" || ng 2走抽出
cmp -s "$EXPECTED" "$WORK/extracted.tsv" || ng 固定値
if python3 "$REPO/tools/save_conform_check.py" freeze "$WORK/bad.json" "$WORK/add.json" \
    "$WORK/rejected.tsv" >"$WORK/reject.out" 2>"$WORK/reject.err"; then ng 2走陰性対照; fi

cat >"$WORK/fake.py" <<'PY'
#!/usr/bin/env python3
import hashlib, os, pathlib, sys
sys.path.insert(0, os.environ['SAVE_FAKE_TOOLS'])
import m6fj_script as script
import save_conform_check as check
from make_m6fj_disk import offsets

args=sys.argv[1:]
def arg(name): return args[args.index(name)+1]
arm=os.environ['SAVE_CONFORM_ARM']
expected=check.load(pathlib.Path(os.environ['SAVE_FAKE_SOURCE']))[arm]
image_path=pathlib.Path(arg('--insert-disk2') if arm=='J-6' else arg('--disk2'))
image=bytearray(image_path.read_bytes())
off=offsets(image)
for i,record in enumerate(expected['entries'].split(',')):
    if not record: continue
    name,pos,tail=record.split(':')
    sector=1+int(pos)//16
    position=off[(18,1,sector)]+16*(int(pos)%16)
    image[position:position+16]=name.encode('ascii').ljust(9,b' ')+bytes.fromhex(tail)
fat=bytes.fromhex(expected['fat_0_159'])
for r in (14,15,16):
    position=off[(18,1,r)]
    image[position:position+160]=fat
    if arm not in ('J-4','J-5'):
        image[position+160:position+160+len(os.environ['SAVE_FAKE_FAT_CANARY'])]=os.environ['SAVE_FAKE_FAT_CANARY'].encode()
if arm in ('J-1','J-2'):
    unit=72
    linear=unit*8
    position=off[(linear//32,(linear//16)%2,linear%16+1)]
    body=script.body(arm)
    image[position:position+len(body)]=body
    marker=os.environ['SAVE_FAKE_CANARY'].encode()
    image[position+40:position+40+len(marker)]=marker
image_path.write_bytes(image)

def parsed(value):
    if not value:return []
    return [(int(r),int(n),h) for r,n,h in (x.split(':') for x in value.split(','))]
rows=parsed(expected['screen'])
if arm in os.environ.get('SAVE_FAKE_BAD_ARMS','').split():
    if rows:
        r,n,h=rows[0];rows[0]=(r,n,('0' if h[0]!='0' else '1')+h[1:])
    else:rows=[(0,1,'0'*64)]
prompt_row=max([r for r,_,_ in rows],default=-1)+1
prompt=(prompt_row,2,hashlib.sha256(f'{prompt_row}\tOk\n'.encode()).hexdigest())
def snapshot(name,visible):
    current=visible+[prompt]
    output=[f'snapshot_id\t{name}','physical_row\tchar_count\tsha256']
    output.extend(f'{r}\t{n}\t{h}' for r,n,h in current)
    output.extend((f'line_count\t{len(current)}',f'char_count\t{sum(n for _,n,_ in current)}',f'sha256\t{"3"*64}'))
    return output
output=[]
for name in ('baseline','preinsert','final','late'):
    if name=='preinsert' and arm!='J-6':continue
    output += snapshot(name, [] if name in ('baseline','preinsert') else rows)
pathlib.Path(arg('--out')).write_text('\n'.join(output)+'\n',encoding='ascii')
PY
chmod +x "$WORK/fake.py"
run_fake() {
  local tag="$1" expectation="$2" bad="$3" rc=0
  SAVE_CONFORM_FRONTEND="$WORK/fake.py" SAVE_CONFORM_CORE=dummy \
    SAVE_CONFORM_TEST_ROM_DIR="$WORK/rom" SAVE_CONFORM_EXPECTED="$expectation" \
    SAVE_FAKE_TOOLS="$REPO/tools" SAVE_FAKE_SOURCE="$EXPECTED" SAVE_FAKE_BAD_ARMS="$bad" \
    SAVE_FAKE_CANARY="$CANARY" SAVE_FAKE_FAT_CANARY="$FAT_CANARY" \
    PC88_SAVE_CONFORM_WORK="$WORK/$tag.work" \
    bash "$REPO/tools/conform_save.sh" local >"$WORK/$tag.out" 2>"$WORK/$tag.err" || rc=$?
  printf '%s' "$rc"
}
[ "$(run_fake good "$EXPECTED" '')" -eq 0 ] || ng 正例
[ "$(awk -F '\t' '$2=="OK"{n++} END{print n+0}' "$WORK/good.out")" -eq 6 ] || ng 正例集合
python3 "$REPO/tools/save_conform_check.py" verify-j1-image "$EXPECTED" \
  "$WORK/good.work/runs/J-1/drive2.d88" >"$WORK/j1-image.out" || ng J1像正例
if python3 "$REPO/tools/save_conform_check.py" verify-j1-image "$EXPECTED" \
    "$WORK/good.work/media/B0.d88" >"$WORK/j1-image-bad.out"; then ng J1像陰性対照; fi
cp "$EXPECTED" "$WORK/broken.tsv"
python3 - "$WORK/broken.tsv" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1]);lines=p.read_text(encoding='ascii').splitlines()
for i,line in enumerate(lines):
    if line.startswith('J-1\tfat_0_159\t'):
        arm,field,value=line.split('\t');value=('0' if value[0]!='0' else '1')+value[1:]
        lines[i]='\t'.join((arm,field,value));break
p.write_text('\n'.join(lines)+'\n',encoding='ascii')
PY
[ "$(run_fake broken "$WORK/broken.tsv" '')" -eq 1 ] || ng 期待値破損
[ "$(awk -F '\t' '$2=="NG"{print $1}' "$WORK/broken.out")" = J-1 ] || ng 破損腕
[ "$(run_fake fake-bad "$EXPECTED" 'J-5')" -eq 1 ] || ng 偽故障
[ "$(awk -F '\t' '$2=="NG"{print $1}' "$WORK/fake-bad.out")" = J-5 ] || ng 偽故障腕
python3 - "$WORK/readback.tsv" "$WORK/readback-bad.tsv" "$REPO/tools" <<'PY'
import pathlib,sys
good,bad,tools=map(pathlib.Path,sys.argv[1:])
sys.path.insert(0,str(tools))
import save_conform_readback as r
def snap(name,values):
    lines=[f'snapshot_id\t{name}','physical_row\tchar_count\tsha256']
    lines.extend(f'{row}\t{count}\t{digest}' for row,count,digest in values)
    lines.extend((f'line_count\t{len(values)}',f'char_count\t{sum(x[1] for x in values)}',f'sha256\t{"3"*64}'))
    return lines
entry='qsb'.ljust(9)
signatures={'list':[r.signed(0,'10 PRINT 1')],
            'files':[r.signed(0,entry[:6]+' '+entry[6:]+' 1')]}
lines=[]
for name in ('list','list_late','files','files_late'):
    values=signatures['list' if name.startswith('list') else 'files']
    lines+=snap(name,values+[r.signed(1,'Ok')])
good.write_text('\n'.join(lines)+'\n',encoding='ascii')
bad_lines=lines.copy()
index=next(i for i,line in enumerate(bad_lines) if line.startswith('0\t12\t'))
parts=bad_lines[index].split('\t');parts[2]=('0' if parts[2][0]!='0' else '1')+parts[2][1:]
bad_lines[index]='\t'.join(parts)
bad.write_text('\n'.join(bad_lines)+'\n',encoding='ascii')
PY
python3 "$REPO/tools/save_conform_readback.py" "$WORK/readback.tsv" >"$WORK/readback.out" || ng 読戻し正例
if python3 "$REPO/tools/save_conform_readback.py" "$WORK/readback-bad.tsv" >"$WORK/readback-bad.out"; then ng 読戻し陰性対照; fi
[ "$(awk -F '\t' '$2=="NG"{print $1}' "$WORK/readback-bad.out")" = FILES ] || ng 読戻し故障腕
if grep -R -I -q -F -e "$CANARY" -e "$FAT_CANARY" \
    "$WORK"/*.out "$WORK"/*.err "$WORK"/*.work/runs/*/signatures.tsv \
    "$WORK"/*.work/runs/*/compare.out "$EXPECTED" 2>/dev/null; then ng 漏えい; fi
printf '%s\n%s\n' "$CANARY" "$FAT_CANARY" >"$WORK/leak-control.txt"
grep -qF "$CANARY" "$WORK/leak-control.txt" || ng 漏えい陰性対照
grep -qF "$FAT_CANARY" "$WORK/leak-control.txt" || ng FAT漏えい陰性対照
printf 'OK SAVE適合器: 6腕、選択NG、漏えい陰性対照\n'
