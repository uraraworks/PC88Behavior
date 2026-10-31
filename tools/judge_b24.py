#!/usr/bin/env python3
"""事前登録第4節の比較だけで判定する。"""
import argparse,contextlib,csv,json,re
FIELDS=('row','run','complete','count','timeout','prefix','extra','stamps')
LENGTHS=(16,1,16,256,256,512,0,16)
def load(paths):
    result={}
    for path in paths:
        with (contextlib.nullcontext(path) if hasattr(path,'read') else open(path,encoding='utf-8',newline='')) as f:
            reader=csv.DictReader(f,delimiter='\t')
            if tuple(reader.fieldnames or ())!=FIELDS: raise ValueError('header')
            for r in reader:
                if None in r or any(r[k] is None for k in FIELDS): raise ValueError('columns')
                if not re.fullmatch('[1-8]',r['row']) or not re.fullmatch('[12]',r['run']) or not re.fullmatch('[01]',r['complete']): raise ValueError('key')
                n=int(r['row']); key=(n,int(r['run'])); length=LENGTHS[n-1]
                if key in result or not re.fullmatch(r'0|[1-9][0-9]*',r['count']) or not re.fullmatch(r'0|[1-9][0-9]*',r['prefix']): raise ValueError('count')
                count=int(r['count']); prefix=int(r['prefix'])
                if count>length+8 or prefix>min(count,length) or r['timeout'] not in (('0','1') if r['complete']=='1' else ('-',)): raise ValueError('range')
                if not re.fullmatch(r'-|[01](?:;[01])*',r['extra']) or len([] if r['extra']=='-' else r['extra'].split(';'))!=max(0,count-length): raise ValueError('extra')
                if not re.fullmatch(r'-|(?:other|[0-9]+,[01],[0-9]+)(?:;(?:other|[0-9]+,[01],[0-9]+))*',r['stamps']): raise ValueError('stamp')
                if len([] if r['stamps']=='-' else r['stamps'].split(';')) != ((min(count,length)+255)//256 if n in (5,6) else 0): raise ValueError('stamp count')
                result[key]=r
    return result
def judge(records):
    same={str(n): all((n,r) in records for r in (1,2)) and all(records[n,1][k]==records[n,2][k] for k in FIELDS if k!='run') for n in range(1,9)}
    control=all(same.values()) and records[8,1]['complete']=='1' and int(records[8,1]['prefix'])==0 and int(records[8,1]['count'])>0
    result={'controls_passed':control,'agreement':same,'transfer':'inconclusive'}
    if control:
        rows=[records[n,1] for n in range(1,7)]
        result['transfer']='confirmed' if all(r['complete']=='1' and int(r['prefix'])==LENGTHS[int(r['row'])-1] for r in rows[:4]) and rows[4]['stamps']=='0,0,1' and rows[5]['stamps']=='0,0,1;0,0,2' else 'not_confirmed'
    return result
def main():
    p=argparse.ArgumentParser();p.add_argument('tsv',nargs='+');a=p.parse_args()
    try: print(json.dumps(judge(load(a.tsv)),sort_keys=True,separators=(',',':')))
    except (OSError,ValueError,KeyError,TypeError): print('{"error":"invalid_input"}');return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
