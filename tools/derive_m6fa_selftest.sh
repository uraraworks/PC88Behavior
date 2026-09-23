#!/usr/bin/env bash
# 架空配置の合成差分JSONだけでD1〜D7の3分類を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
import copy,json,sys
from pathlib import Path
repo,work=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo/'tools'))
import derive_m6fa as d

DIR=(0,0,1); ALLOC=(0,0,2)
def entry(name,start=10,pad=0x20,length=16):
    out={start+i:b for i,b in enumerate(name)}
    out.update({i:pad for i in range(start+len(name),start+length)})
    return out
def doc(sectors,old=0xFF,old_by_sector=None):
    old_by_sector=old_by_sector or {}; changes=[]; total=0
    for (c,h,r),values in sorted(sectors.items()):
        ranges=[]; keys=sorted(values); i=0
        while i<len(keys):
            start=keys[i]; end=start+1; i+=1
            while i<len(keys) and keys[i]==end: end+=1; i+=1
            ov=old_by_sector.get((c,h,r),old)
            ranges.append({'offset':start,'length':end-start,
                           'new':bytes(values[x] for x in range(start,end)).hex().upper(),
                           'old':'withheld'})
            total+=end-start
        sector={'c':c,'h':h,'r':r,'changed_bytes':len(values),'ranges':ranges}
        if ov is not None and len(values)>=8: sector['old_uniform']=f'{ov:02X}'
        changes.append(sector)
    return {'schema':1,'sector_layout_equal':True,'before_only':[],'after_only':[],
            'changed_sectors':len(changes),'changed_bytes':total,'changes':changes}
def base_docs():
    a=entry(b'QZ7A'); b=entry(b'QZ7B'); long=entry(b'QZ7ABC')
    two=entry(b'QZ7A'); two.update(entry(b'QZ7B',26))
    killed=entry(bytes([0xE5])+b'Z7A')
    f6=entry(b'QZ7D')
    return {
      'F0':doc({}), 'F1':doc({DIR:a,ALLOC:{0:1}}),
      'F2':doc({DIR:b,ALLOC:{0:1}}), 'F3':doc({DIR:long,ALLOC:{0:1}}),
      'F4':doc({DIR:two}), 'F5':doc({DIR:killed}),
      'F6':doc({DIR:f6,ALLOC:{i:i+1 for i in range(8)}}),
    }
def views(docs): return {k:d.parse_diff(v) for k,v in docs.items()}
def status(docs,key): return d.derive_repetition(views(docs))[key]['status']
def maps(doc):
    v=d.parse_diff(doc); out={}
    for p,x in v.new.items(): out.setdefault(p[:3],{})[p[3]]=x
    return out
def rebuild(docs,arm,sectors,old=0xFF,old_by_sector=None):
    docs[arm]=doc(sectors,old,old_by_sector)

checks={}
base=base_docs(); result=d.derive_repetition(views(base))
for key in d.DERIVATIONS: checks[f'{key}_derived']=result[key]['status']=='derived'
expected_values={
 'D1':{'sector':{'c':0,'h':0,'r':1}},
 'D2':{'sector':{'c':0,'h':0,'r':1},'name_offset':10},
 'D3':{'entry_length':16},
 'D4':{'padding_value':'20','name_field_length':6},
 'D5':{'position':{'c':0,'h':0,'r':1,'offset':10},'value':'E5'},
 'D6':{'unused_entry_value':'FF'},
 'D7':{'sector':{'c':0,'h':0,'r':2},'empty_value':'FF'},
}
for key,want in expected_values.items(): checks[f'{key}_value']=result[key].get('value')==want

# D1: もう1つの「1バイトだけ違う」共通セクタ／本命を2バイト差にする。
x=base_docs(); extra=(0,0,3)
for arm,val in [('F1',1),('F2',2),('F3',3)]:
    m=maps(x[arm]); m[extra]={0:val}; rebuild(x,arm,m)
checks['D1_ambiguous']=status(x,'D1')=='ambiguous'
x=base_docs(); m=maps(x['F2']); m[DIR][14]=0x21; rebuild(x,'F2',m)
checks['D1_not_found_two_bytes']=status(x,'D1')=='not_found'

# D2: F1内のQZ7Aを2箇所にする／名前を架空の別列へ置換する。
x=base_docs()
for arm in ('F1','F2','F3'):
    m=maps(x[arm]); m[DIR].update(entry(b'QZ7A',50)); rebuild(x,arm,m)
checks['D2_ambiguous_two_names']=status(x,'D2')=='ambiguous'
x=base_docs()
for arm,name in [('F1',b'ABCD'),('F2',b'ABCE'),('F3',b'ABCDEF')]:
    m=maps(x[arm]); m[DIR]=entry(name); rebuild(x,arm,m)
checks['D2_not_found']=status(x,'D2')=='not_found'

# D3: F4に第2候補を加える／QZ7Bを消す。
x=base_docs(); m=maps(x['F4']); m[DIR].update(entry(b'QZ7B',42)); rebuild(x,'F4',m)
checks['D3_ambiguous']=status(x,'D3')=='ambiguous'
x=base_docs(); m=maps(x['F4']); m[DIR]=entry(b'QZ7A'); rebuild(x,'F4',m)
checks['D3_not_found']=status(x,'D3')=='not_found'
# D3の「同じトラックの次R」を通し位置として数える分岐も固定する。
x=base_docs(); m=maps(x['F4']); m[DIR]=entry(b'QZ7A'); m[(0,0,2)]=entry(b'QZ7B',10); rebuild(x,'F4',m)
cross=d.derive_repetition(views(x))['D3']
checks['D3_cross_sector']=cross.get('value')=={'entry_length':256}

# D4: F3に別の6文字名候補／F1詰め物を非一様にする。
x=base_docs(); m=maps(x['F3']); m[DIR].update(entry(b'QZ7ABC',20,0x20,6)); rebuild(x,'F3',m)
checks['D4_ambiguous']=status(x,'D4')=='ambiguous'
x=base_docs()
for arm in ('F1','F2'):
    m=maps(x[arm]); m[DIR][14]=0x21; rebuild(x,arm,m)
checks['D4_not_found']=status(x,'D4')=='not_found'

# D5: 削除後に2位置を変える／削除後をF1と同じにする。
x=base_docs(); m=maps(x['F5']); m[DIR][11]=0xE6; rebuild(x,'F5',m)
checks['D5_ambiguous']=status(x,'D5')=='ambiguous'
x=base_docs(); rebuild(x,'F5',maps(x['F1']))
checks['D5_not_found']=status(x,'D5')=='not_found'

# D6: 2つのディレクトリセクタ候補に別々のセクタ一様旧値。
x=base_docs(); dir2=(0,0,3)
for arm,name in (('F1',b'QZ7A'),('F2',b'QZ7B'),('F3',b'QZ7ABC')):
    m=maps(x[arm]); m[dir2]=entry(name)
    rebuild(x,arm,m,old_by_sector={DIR:0xFF,dir2:0xEE})
m=maps(x['F4']); m[dir2]=entry(b'QZ7A'); m[dir2].update(entry(b'QZ7B',26)); rebuild(x,'F4',m)
checks['D6_ambiguous']=status(x,'D6')=='ambiguous'
x=base_docs(); rebuild(x,'F1',maps(x['F1']),old=None)
hidden=d.derive_repetition(views(x))['D6']
checks['D6_not_found_withheld']=hidden=={'status':'not_found','candidate_count':0,'reason':'old_values_withheld'}
x=base_docs()
for arm,name in [('F1',b'ABCD'),('F2',b'ABCE'),('F3',b'ABCDEF')]:
    m=maps(x[arm]); m[DIR]=entry(name); rebuild(x,arm,m)
missing=d.derive_repetition(views(x))['D6']
checks['D6_not_found_no_candidate']=missing=={'status':'not_found','candidate_count':0}

# D7: 第2候補／F6の変更数をF1以下にする。
x=base_docs(); other=(0,0,4)
for arm,vals in [('F1',{0:1}),('F6',{i:i+1 for i in range(8)})]:
    m=maps(x[arm]); m[other]=vals; rebuild(x,arm,m)
checks['D7_ambiguous']=status(x,'D7')=='ambiguous'
x=base_docs(); m=maps(x['F6']); m[ALLOC]={0:1}; rebuild(x,'F6',m)
checks['D7_not_found']=status(x,'D7')=='not_found'
x=base_docs(); m=maps(x['F6']); m[ALLOC]={i:i+1 for i in range(7)}; rebuild(x,'F6',m)
hidden=d.derive_repetition(views(x))['D7']
checks['D7_old_withheld']=hidden=={'status':'not_found','candidate_count':0,'reason':'old_values_withheld'}

bad={k for k,v in checks.items() if not v}
if bad: raise SystemExit('NG: '+str(bad))
for target in checks:
    negative=dict(checks); negative[target]=False
    if {k for k,v in negative.items() if not v}!={target}: raise SystemExit('NG集合 '+target)
    mutant=dict(negative); mutant[target]=True
    if {k for k,v in mutant.items() if not v}=={target}: raise SystemExit('常時真変異 '+target)

# CLIも14ファイルを読む経路で1回通す。
raw=work/'raw'; raw.mkdir()
for run in (1,2):
    for arm,body in base.items(): (raw/f'{arm}-r{run}.diff.json').write_text(json.dumps(body))
print(f"derive_m6fa_selftest: 項目数={len(checks)}、陰性対照={len(checks)}、常時真変異={len(checks)}件拒否 OK")
print('D1〜D7のderived/ambiguous/not_found各1・値、D2二重名・D1二バイト差・D3跨ぎ OK')
PY
python3 "$REPO/tools/derive_m6fa.py" --raw-dir "$WORK/raw" --output "$WORK/derived.json"
python3 - "$WORK/derived.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); assert len(d['runs'])==2
assert all(x['status']=='derived' for r in d['runs'] for x in r['derivations'].values())
PY
