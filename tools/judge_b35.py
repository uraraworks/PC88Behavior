#!/usr/bin/env python3
"""B35 事前登録第4節に記載された比較。"""
import argparse, contextlib, csv, json, re
REGS=('a','bc','de','hl','ix','iy','sp','i')
FIELDS=('row','run','complete',*REGS)
PREVIOUS={'a':'66','bc':'2211','de':'4433','hl':'6655','ix':'8877','iy':'AA99','sp':'7E00','i':'55'}

def load(paths):
    records={}
    for path in paths:
        with (contextlib.nullcontext(path) if hasattr(path,'read') else open(path,encoding='utf-8',newline='')) as f:
            reader=csv.DictReader(f,delimiter='\t')
            if tuple(reader.fieldnames or ()) != FIELDS: raise ValueError('header')
            for r in reader:
                if None in r or any(v is None for v in r.values()) or not re.fullmatch('[1-6]',r['row']) or not re.fullmatch('[12]',r['run']) or r['complete'] not in ('0','1'): raise ValueError('format')
                for k in REGS:
                    pattern=('[0-9A-F]{2}' if k in ('a','i') else '[0-9A-F]{4}') if r['complete']=='1' else '-'
                    if not re.fullmatch(pattern,r[k]): raise ValueError('register')
                key=(int(r['row']),int(r['run']))
                if key in records: raise ValueError('duplicate')
                records[key]=r
    return records

def judge(records, own=None):
    same={str(n): all((n,r) in records for r in (1,2)) and all(records[n,1][k]==records[n,2][k] for k in FIELDS if k!='run') for n in range(1,7)}
    control=all(same.values()) and records[5,1]['complete']=='1'
    result={'controls_passed':control,'agreement':same,'registers':{}}
    for k in REGS:
        values={str(n):records[n,1][k] if (n,1) in records else '-' for n in range(1,7)}
        valid=all(v!='-' for v in values.values())
        item={'rows':values,'constant':len(set(values.values()))==1 if valid else None,
              'equals_entry_address':{str(n): (int(values[str(n)],16)==(0x6000 if n==5 else 0x7800)) if values[str(n)]!='-' else None for n in range(1,7)},
              'retains_row6_previous':values['6']==PREVIOUS[k] if values['6']!='-' else None}
        if own is not None:
            item['own_rows']={str(n):own[n,1][k] if (n,1) in own else '-' for n in range(1,7)}
            item['differs_from_own']={str(n): (values[str(n)]!=item['own_rows'][str(n)]) if values[str(n)]!='-' and item['own_rows'][str(n)]!='-' else None for n in range(1,7)}
        result['registers'][k]=item
    if own is not None:
        result['own_agreement']={str(n):all((n,r) in own for r in (1,2)) and all(own[n,1][k]==own[n,2][k] for k in FIELDS if k!='run') for n in range(1,7)}
        result['own_controls_passed']=all(result['own_agreement'].values()) and own[5,1]['complete']=='1'
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('tsv',nargs='+');p.add_argument('--own',nargs='+');a=p.parse_args()
    try: print(json.dumps(judge(load(a.tsv),load(a.own) if a.own else None),sort_keys=True,separators=(',',':')))
    except (OSError,ValueError,KeyError,TypeError): print('{"error":"invalid_input"}');return 2
    return 0
if __name__=='__main__': raise SystemExit(main())
