#!/usr/bin/env python3
"""B12 事前登録の判定。"""
import argparse, contextlib, csv, json, re, sys
ROWS = {1:(0,1,1),2:(2,1,1),3:(2,1,2),4:(2,1,5),5:(2,2,4),6:(2,5,1),7:(2,5,2),8:(2,1,6),9:(2,1,0),10:(3,1,4),11:(2,2,1),12:(0,2,1)}
FIELDS = ('row','run','request','count','timeout','blocks','read_count','reads','read_id_count','other_commands','st0','st1')
N = r'(?:0|[1-9][0-9]*)'
COORD = rf'(?:{N},[01],{N},[0-3]|other)'
PATTERNS = (r'(?:[1-9]|1[0-2])',r'[12]',r'[12]',N,r'[01]',rf'(?:-|{COORD}(?:;{COORD})*)',N,rf'(?:-|{N},{N},{N},{N},{N}(?:;{N},{N},{N},{N},{N})*)',N,rf'(?:-|[a-z_]+:{N}(?:;[a-z_]+:{N})*)',r'(?:-|[a-z_0-9]+(?:,[a-z_0-9]+)*(?:;[a-z_0-9]+(?:,[a-z_0-9]+)*)*)',r'(?:-|[a-z_0-9]+(?:,[a-z_0-9]+)*(?:;[a-z_0-9]+(?:,[a-z_0-9]+)*)*)')
from judge_b10 import ST0, ST1
COMMANDS={'specify','sense_drive_status','write_data','recalibrate','sense_interrupt','write_deleted_data','read_deleted_data','format_track','seek','scan_equal','scan_low_or_equal','scan_high_or_equal','read_track','unknown'}

def load(paths):
    records={}
    for path in paths:
        with (contextlib.nullcontext(path) if hasattr(path,'read') else open(path,encoding='utf-8',newline='')) as f:
            reader=csv.DictReader(f,delimiter='\t')
            if tuple(reader.fieldnames or ()) != FIELDS: raise ValueError('header')
            for r in reader:
                if None in r or any(not re.fullmatch(p,r[k] or '') for k,p in zip(FIELDS,PATTERNS)): raise ValueError('format')
                row,run,req=map(int,(r['row'],r['run'],r['request'])); key=(row,run,req)
                if req != 1 and (row,req)!=(12,2): raise ValueError('request')
                p1=2 if (row,req)==(12,2) else ROWS[row][2]
                count=int(r['count']); blocks=[] if r['blocks']=='-' else r['blocks'].split(';'); reads=[] if r['reads']=='-' else r['reads'].split(';')
                if key in records or count>(p1+1)*1024 or len(blocks)!=(count+255)//256 or len(reads)!=int(r['read_count']): raise ValueError('length')
                for block in blocks:
                    if block != 'other':
                        c,h,sec,b=map(int,block.split(','))
                        if c>=40 or not (1<=sec<=16 and b==0 if (c,h)==(0,0) else 1<=sec<=5 and b<4): raise ValueError('block')
                if any(any(int(value)>255 for value in read.split(',')) for read in reads): raise ValueError('read')
                for field, allowed in [('st0',ST0),('st1',ST1)]:
                    if ((r[field]=='-') != (not reads) or (reads and len(r[field].split(';'))!=len(reads)) or (r[field]!='-' and any(x not in allowed for x in re.split('[,;]',r[field])))): raise ValueError('status')
                if r['other_commands']!='-':
                    parts=[x.split(':') for x in r['other_commands'].split(';')]
                    if any(k not in COMMANDS or int(v)<1 for k,v in parts) or len({x[0] for x in parts})!=len(parts): raise ValueError('commands')
                records[key]=r
    return records

def judge(records):
    same={n: all((n,1,q) in records and (n,2,q) in records and all(records[n,1,q][k]==records[n,2,q][k] for k in FIELDS if k!='run') for q in (1,2) if q==1 or n==12) for n in ROWS}
    def rec(n,q=1): return records[n,1,q]
    controls=all(same[n] for n in (1,11)) and rec(1)['count']=='256' and rec(1)['blocks']=='0,0,1,0' and rec(11)['blocks'].split(';')[0]=='1,0,3,0'
    result={'controls_passed':controls,'agreement':same,'p1':'inconclusive','n_eot':{},'crossing':{},'after_track_zero':'inconclusive'}
    if not controls: return result
    rows=(2,3,4,5,6)
    if all(same[n] for n in rows):
        counts=[int(rec(n)['count']) for n in rows]
        result['p1']='sectors_1024' if all(v==ROWS[n][2]*1024 for n,v in zip(rows,counts)) else 'units_256' if all(v==ROWS[n][2]*256 for n,v in zip(rows,counts)) else {'counts':counts}
    for n in ROWS:
        if same[n]: result['n_eot'][n]=[rec(n,q)['reads'] for q in (1,2) if q==1 or n==12]
    for n in (7,8):
        if not same[n]: result['crossing'][n]='inconclusive'; continue
        r=rec(n); blocks=[] if r['blocks']=='-' else r['blocks'].split(';'); t,_,_=ROWS[n]
        crossed=any(b!='other' and tuple(map(int,b.split(',')[:2]))!=divmod(t,2) for b in blocks)
        result['crossing'][n]='advances' if crossed else ('fails' if not blocks else 'partial')
    if same[12] and same[3]: result['after_track_zero']=all(rec(12,2)[k]==rec(3)[k] for k in FIELDS if k not in ('row','run','request'))
    return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('tsv',nargs='+'); a=p.parse_args()
    try: print(json.dumps(judge(load(a.tsv)),sort_keys=True,separators=(',',':')))
    except (ValueError,OSError,KeyError,TypeError): print('{"error":"invalid_input"}'); return 2
    return 0
if __name__=='__main__': sys.exit(main())
