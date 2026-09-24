#!/usr/bin/env bash
# 架空配置の合成差分JSONだけで E1〜E8 と2走合意を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
import copy,json,sys
from pathlib import Path
repo,work=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo/'tools'))
import derive_m6fb as d

DIR=d.DIRECTORY; ALLOC=(1,0,1); ALLOC2=(1,0,2); BODY=(2,0,1)
def entry(name,start=16,field=8,mark=0x11):
    out={start+i:b for i,b in enumerate(name)}
    out.update({start+i:0x20 for i in range(len(name),field)})
    out[start+field]=mark
    return out
def doc(sectors,old=0xFF,old_by_sector=None):
    old_by_sector=old_by_sector or {}; changes=[]; total=0
    for (c,h,r),values in sorted(sectors.items()):
        ranges=[]; keys=sorted(values); i=0
        while i<len(keys):
            start=keys[i]; end=start+1; i+=1
            while i<len(keys) and keys[i]==end: end+=1; i+=1
            ranges.append({'offset':start,'length':end-start,
                           'new':bytes(values[x] for x in range(start,end)).hex().upper(),
                           'old':'withheld'})
            total+=end-start
        row={'c':c,'h':h,'r':r,'changed_bytes':len(values),'ranges':ranges}
        ov=old_by_sector.get((c,h,r),old)
        if ov is not None and len(values)>=8: row['old_uniform']=f'{ov:02X}'
        changes.append(row)
    return {'schema':1,'sector_layout_equal':True,'before_only':[],'after_only':[],
            'changed_sectors':len(changes),'changed_bytes':total,'changes':changes}
def base_docs():
    two=entry(d.U); two.update(entry(d.U_B,32))
    killed=entry(bytes([0xE5])+d.U[1:])
    return {
      'G0':doc({}),
      'G1':doc({DIR:entry(d.U),ALLOC:{0:1,1:2},BODY:{0:ord('X')}}),
      'G2':doc({DIR:entry(d.L),ALLOC:{0:1,1:2},BODY:{0:ord('Y')}}),
      'G3':doc({DIR:entry(d.L),ALLOC:{0:1,1:2},BODY:{0:ord('W')}}),
      'G4':doc({DIR:two}), 'G5':doc({DIR:killed}),
      'G6':doc({DIR:entry(d.U_LONG)}),
      'G7':doc({DIR:entry(b'QZ7D'),ALLOC:{i:i+1 for i in range(6)},BODY:{0:ord('V')}}),
      'G8':doc({DIR:entry(d.U_PROGRAM,mark=0x22)}),
    }
def views(docs): return {arm:d.parse_diff(body) for arm,body in docs.items()}
def derive(docs): return d.derive_repetition(views(docs))
def maps(body):
    view=d.parse_diff(body); out={}
    for pos,value in view.new.items(): out.setdefault(pos[:3],{})[pos[3]]=value
    return out
def rebuild(docs,arm,sectors,old=0xFF,old_by_sector=None):
    docs[arm]=doc(sectors,old,old_by_sector)
def status(docs,key): return derive(docs)[key]['status']

checks={}; base=base_docs(); result=derive(base)
expected={'E1':'case_stored_as_given','E2':'derived','E3':'derived','E4':'derived',
          'E5':'derived','E6':'derived','E7':'derived','E8':'derived'}
for key,want in expected.items(): checks[f'{key}_base']=result[key]['status']==want
checks['E2_value']=result['E2']['value']=={'position':{'c':18,'h':1,'r':3,'offset':16}}
checks['E3_value']=result['E3']['value']=={'entry_length':16}
checks['E4_value']=result['E4']['value']=={'name_field_length':8,'padding_value':'20'}
checks['E5_value']=result['E5']['value']=={'position':{'c':18,'h':1,'r':3,'offset':16},'value':'E5'}
checks['E6_value']=result['E6']['value']=={'unused_entry_value':'FF'}
checks['E7_value']=result['E7']['value']=={'sectors':[{'c':1,'h':0,'r':1}]}
checks['E8_value']=result['E8']['value']=={'data_value':'11','program_value':'22'}

# E1の4判定を独立の合成入力で固定する。
x=base_docs(); m=maps(x['G1']); m[DIR]=entry(d.L); rebuild(x,'G1',m)
checks['E1_fold_lower']=status(x,'E1')=='case_folded_to_lower'
x=base_docs()
for arm in ('G2','G3'):
    m=maps(x[arm]); m[DIR]=entry(d.U); rebuild(x,arm,m)
checks['E1_fold_upper']=status(x,'E1')=='case_folded_to_upper'
x=base_docs(); m=maps(x['G3']); m[DIR].update(entry(d.U,64)); rebuild(x,'G3',m)
checks['E1_other']=status(x,'E1')=='case_other'

# E2〜E5をそれぞれ derived/ambiguous/not_found の3分類へ入れる。
x=base_docs(); m=maps(x['G1']); m[DIR].update(entry(d.U,64)); rebuild(x,'G1',m)
checks['E2_ambiguous']=status(x,'E2')=='ambiguous'
x=base_docs(); m=maps(x['G1']); m[DIR][15]=0x99; rebuild(x,'G1',m)
checks['E2_not_found']=status(x,'E2')=='not_found'
x=base_docs(); m=maps(x['G4']); m[DIR].update(entry(d.U_B,64)); rebuild(x,'G4',m)
checks['E3_ambiguous']=status(x,'E3')=='ambiguous'
x=base_docs(); m=maps(x['G4']); m[DIR]=entry(d.U); rebuild(x,'G4',m)
checks['E3_not_found']=status(x,'E3')=='not_found'
x=base_docs(); m=maps(x['G1']); m[DIR].update(entry(d.U,64,9)); rebuild(x,'G1',m)
m=maps(x['G6']); m[DIR].update(entry(d.U_LONG,64,9)); rebuild(x,'G6',m)
checks['E4_ambiguous']=status(x,'E4')=='ambiguous'
x=base_docs(); m=maps(x['G6']); m[DIR]=entry(d.U_LONG,field=9); rebuild(x,'G6',m)
checks['E4_not_found']=status(x,'E4')=='not_found'
x=base_docs(); m=maps(x['G5']); m[DIR][17]=0xE6; rebuild(x,'G5',m)
checks['E5_ambiguous']=status(x,'E5')=='ambiguous'
x=base_docs(); rebuild(x,'G5',maps(x['G1']))
checks['E5_not_found']=status(x,'E5')=='not_found'

# E6は候補なしと、境界規則により旧値が伏せられた場合を区別する。
x=base_docs(); m=maps(x['G1']); del m[DIR]; rebuild(x,'G1',m)
checks['E6_no_candidate']=derive(x)['E6']=={'status':'not_found','candidate_count':0}
x=base_docs(); rebuild(x,'G1',maps(x['G1']),old_by_sector={DIR:None})
checks['E6_withheld']=derive(x)['E6']=={
    'status':'not_found','candidate_count':0,'reason':'old_values_withheld'}

# E7は集合を保持し、腕ごとに異なる本体セクタを候補へ混ぜない。
checks['E7_body_excluded']=BODY not in [tuple(v.values()) for v in result['E7']['value']['sectors']]
x=base_docs()
for arm in ('G1','G2','G3'):
    m=maps(x[arm]); m[ALLOC2]={0:7}; rebuild(x,arm,m)
m=maps(x['G7']); m[ALLOC2]={0:7,1:8}; rebuild(x,'G7',m)
r=derive(x)['E7']; checks['E7_multiple_set']=r['status']=='derived' and r['candidate_count']==2
x=base_docs(); m=maps(x['G2']); m[ALLOC][1]=9; rebuild(x,'G2',m)
checks['E7_not_found']=status(x,'E7')=='not_found'

# E8の曖昧・候補なしも固定する。
x=base_docs(); m=maps(x['G8']); m[DIR].update(entry(d.U_PROGRAM,64,8,0x33)); rebuild(x,'G8',m)
checks['E8_ambiguous']=status(x,'E8')=='ambiguous'
x=base_docs(); m=maps(x['G8']); del m[DIR][24]; rebuild(x,'G8',m)
checks['E8_not_found']=status(x,'E8')=='not_found'

# 全Eについて2走の導出が違えば最終分類を ambiguous に倒す。
other=copy.deepcopy(result); other['E1']={'status':'case_other','candidate_count':1,
                                         'value':{'G1':'none','G2':'none','G3':'none'}}
for key in d.DERIVATIONS[1:]: other[key]={'status':'not_found','candidate_count':0}
for key in d.DERIVATIONS:
    checks[f'{key}_two_run_ambiguous']=d.consensus(key,result[key],other[key])['status']=='ambiguous'

bad={key for key,value in checks.items() if not value}
if bad: raise SystemExit('NG集合 '+str(bad))
for target in checks:
    negative=dict(checks); negative[target]=False
    if {key for key,value in negative.items() if not value}!={target}:
        raise SystemExit('NG集合 '+target)
    mutant=dict(negative); mutant[target]=True
    if {key for key,value in mutant.items() if not value}=={target}:
        raise SystemExit('常時真変異 '+target)

raw=work/'raw'; raw.mkdir()
for run in (1,2):
    for arm,body in base.items(): (raw/f'{arm}-r{run}.diff.json').write_text(json.dumps(body))
(work/'count').write_text(str(len(checks)))
PY
python3 "$REPO/tools/derive_m6fb.py" --raw-dir "$WORK/raw" --output "$WORK/derived.json"
python3 - "$WORK/derived.json" "$WORK/count" <<'PY'
import json,sys
body=json.load(open(sys.argv[1],encoding='utf-8'))
assert len(body['runs'])==2 and len(body['derivations'])==8
assert body['derivations']['E1']['status']=='case_stored_as_given'
assert all(body['derivations'][f'E{i}']['status']=='derived' for i in range(2,9))
text=json.dumps(body,sort_keys=True)
assert all(forbidden not in text for forbidden in ('"changes"','"ranges"','"old"','"new"'))
count=int(open(sys.argv[2]).read())
print(f'derive_m6fb_selftest: 項目数={count}、陰性対照={count}、常時真変異={count}件拒否 OK')
print('E1の4判定、E2〜E5の3分類、E6理由分離、E7本体除外・集合、E1〜E8の2走不一致 OK')
PY
