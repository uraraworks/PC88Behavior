#!/usr/bin/env python3
"""B17 の白リストと事前登録判定。"""
import argparse, contextlib, csv, json, re
N=r'(?:0|[1-9][0-9]*)'
W=rf'[0-9A-F]{{4}}-[0-9A-F]{{4}}:{N}'
A=rf'[0-9A-F]{{4}}:{N},{N},{N},{N},{N}'
C=r'(?:[0-9]+,[01],[0-9]+|other)'
FIELDS=('row','run','complete','sent','timeout','rom','ram','high_rom','high_ram','crossings','read1','stamp1','read2','stamp2','out_fd','sub_dropped')
PATTERNS=(r'[1-7]',r'[12]',r'[01]',rf'(?:-|{N})',r'(?:-|[01])',*(rf'(?:-|{W}(?:;{W})*)',)*4,rf'(?:-|{A}(?:;{A})*)',rf'(?:-|{N})',rf'(?:-|{C}(?:;{C})*)',rf'(?:-|{N})',rf'(?:-|{C}(?:;{C})*)',N,N)
def load(paths):
    records={}
    for path in paths:
        with (contextlib.nullcontext(path) if hasattr(path,'read') else open(path,encoding='utf-8',newline='')) as f:
            reader=csv.DictReader(f,delimiter='\t')
            if tuple(reader.fieldnames or ()) != FIELDS: raise ValueError('header')
            for r in reader:
                if None in r or any(not re.fullmatch(p,r[k] or '') for k,p in zip(FIELDS,PATTERNS)): raise ValueError('format')
                key=int(r['row']),int(r['run'])
                if key in records: raise ValueError('duplicate')
                if r['complete']=='0':
                    if any(r[k]!='-' for k in ('sent','timeout','read1','stamp1','read2','stamp2')): raise ValueError('incomplete')
                else:
                    if r['sent']=='-' or r['timeout']=='-' or int(r['sent'])>300: raise ValueError('count')
                    for i in (1,2):
                        count=r[f'read{i}']; stamp=r[f'stamp{i}']
                        if (key[0] not in ((3,7) if i==1 else (7,))):
                            if count!='-' or stamp!='-': raise ValueError('read')
                        elif count=='-' or int(count)>512 or len([] if stamp=='-' else stamp.split(';'))!=(int(count)+255)//256: raise ValueError('read')
                for name in ('rom','ram','high_rom','high_ram'):
                    prev=0x3fff if not name.startswith('high') else 0x7eff
                    for item in ([] if r[name]=='-' else r[name].split(';')):
                        span,count=item.split(':'); a,b=(int(x,16) for x in span.split('-'))
                        if a<=prev or a>b or int(count)<b-a+1 or (not name.startswith('high') and b>=0x7f00): raise ValueError('span')
                        prev=b
                prev=-1
                for item in ([] if r['crossings']=='-' else r['crossings'].split(';')):
                    addr,counts=item.split(':'); a=int(addr,16); ns=list(map(int,counts.split(',')))
                    if a>=0x2000 or a<=prev or ns[0]!=ns[1]+ns[2] or ns[3]>ns[1] or ns[4]>ns[1]: raise ValueError('crossing')
                    prev=a
                records[key]=r
    return records
def judge(records):
    same={n:all((n,r) in records for r in (1,2)) and all(records[n,1][k]==records[n,2][k] for k in FIELDS if k not in ('run','sub_dropped') and (k!='out_fd' or not any(int(records[n,r]['sub_dropped']) for r in (1,2)))) for n in range(1,8)}
    def contains(n,field,start,end):
        return any(int(x[:4],16)<=start and int(x[5:9],16)>=end for x in records[n,1][field].split(';') if x!='-')
    def exact(n,field,start,end):
        return any(int(x[:4],16)==start and int(x[5:9],16)==end for x in records[n,1][field].split(';') if x!='-')
    control=all(same.values()) and records[1,1]['complete']=='1' and records[1,1]['crossings']=='-' and exact(1,'rom',0x7800,0x780f) and not contains(6,'ram',0x7810,0x7810)
    result={'controls_passed':control,'agreement':same,'writing':'inconclusive','execution':'inconclusive','return':'inconclusive'}
    if not control:return result
    result['incomplete']=[n for n in range(1,8) if records[n,1]['complete']=='0']
    if all(records[n,1]['complete']=='1' for n in (1,4,5)):
        result['writing']='confirmed' if all(exact(n,'rom',a,b) for n,a,b in ((1,0x7800,0x780f),(4,0x6000,0x600f),(5,0x7900,0x79ff))) else 'not_confirmed'
    if all(records[n,1]['complete']=='1' for n in (2,4,5)):
        result['execution']='confirmed' if all(contains(n,'ram',a,a) for n,a in ((2,0x7810),(4,0x6010),(5,0x7a10))) else 'not_confirmed'
    if all(records[n,1]['complete']=='1' for n in (2,3,7)):
        cross=records[2,1]['crossings'].split(';'); jump=any(x.startswith('00C1:') and x.split(':')[1].split(',')[2]=='1' for x in cross)
        reads=all(records[n,1][f'read{i}']=='256' and records[n,1][f'stamp{i}']=='0,0,1' for n,i in ((3,1),(7,1),(7,2)))
        result['return']='confirmed' if jump and reads else 'not_confirmed'
    return result
def main():
    p=argparse.ArgumentParser();p.add_argument('tsv',nargs='+');a=p.parse_args()
    try: print(json.dumps(judge(load(a.tsv)),sort_keys=True,separators=(',',':')))
    except (OSError,ValueError,TypeError,KeyError): print('{"error":"invalid_input"}');return 2
    return 0
if __name__=='__main__': raise SystemExit(main())
