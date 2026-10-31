#!/usr/bin/env python3
"""B16 事前登録の白リスト検証と判定。"""
import argparse, contextlib, csv, json, re, sys
FIELDS = ('row','run','complete','count','timeout','writes','crossings','out_fd','sub_dropped')
NUM = r'(?:0|[1-9][0-9]*)'
W = rf'[0-9A-F]{{4}}-[0-9A-F]{{4}}:{NUM}'
A = rf'[0-9A-F]{{4}}:{NUM},{NUM},{NUM},{NUM},{NUM}'
PATTERNS = (r'(?:[1-9]|1[0-5])', r'[12]', r'[01]', rf'(?:-|{NUM})', r'(?:-|[01])', rf'(?:-|{W}(?:;{W})*)', rf'(?:-|{A}(?:;{A})*)', NUM, NUM)

def load(paths):
    records = {}
    for path in paths:
        with (contextlib.nullcontext(path) if hasattr(path, 'read') else open(path, encoding='utf-8', newline='')) as f:
            reader = csv.DictReader(f, delimiter='\t')
            if tuple(reader.fieldnames or ()) != FIELDS: raise ValueError('header')
            for row in reader:
                if None in row or any(not re.fullmatch(p,row[k] or '') for k,p in zip(FIELDS,PATTERNS)): raise ValueError('format')
                key = int(row['row']), int(row['run'])
                if key in records: raise ValueError('duplicate')
                if row['complete'] == '0':
                    if row['count'] != '-' or row['timeout'] != '-': raise ValueError('incomplete')
                elif row['count'] == '-' or row['timeout'] == '-' or int(row['count']) > (0 if key[0] == 1 else 69): raise ValueError('count')
                prev = 0x3fff
                for item in ([] if row['writes']=='-' else row['writes'].split(';')):
                    span, count = item.split(':'); start,end = (int(x,16) for x in span.split('-'))
                    if start <= prev or start > end or int(count) < end-start+1: raise ValueError('span')
                    prev=end
                prev=-1
                for item in ([] if row['crossings']=='-' else row['crossings'].split(';')):
                    addr,counts=item.split(':'); addr=int(addr,16); n=list(map(int,counts.split(',')))
                    if addr >= 0x2000 or addr <= prev or n[0]!=n[1]+n[2] or n[3]>n[1] or n[4]>n[1]: raise ValueError('crossing')
                    prev=addr
                records[key]=row
    return records

def judge(records):
    same={n: (all((n,r) in records for r in (1,2)) and all(records[n,1][k]==records[n,2][k] for k in FIELDS if k not in ('run','sub_dropped') and (k != 'out_fd' or not any(int(records[n,r]['sub_dropped']) for r in (1,2))))) for n in range(1,16)}
    def spans(n):
        s=records[n,1]['writes']
        return [] if s=='-' else s.split(';')
    def start(s): return int(s[:4],16)
    control=all(same.values()) and records[1,1]['complete']=='1' and all(int(x.split('-')[1][:4],16)<0x7800 for x in spans(1))
    result={'controls_passed':control,'agreement':same,'position':'inconclusive','shape':'inconclusive','request_0d':{}}
    if not control: return result
    incomplete=[n for n in range(1,16) if records[n,1]['complete']=='0']
    result['incomplete']={n:'測定 ROM が戻らなかった' for n in incomplete}
    baseline=set(spans(1))
    result['position']={'differences':{n:sorted(set(spans(n))-baseline) for n in range(2,7) if n not in incomplete},'starts_7800':[n for n in list(range(2,12))+[15] if n not in incomplete and any(start(s)==0x7800 for s in spans(n))]}
    def lengths(n): return [int(s.split('-')[1][:4],16)-0x7800+1 for s in spans(n) if start(s)==0x7800]
    l8,l15=lengths(8),lengths(15)
    result['shape']={'address_positions':[1,2], 'length_positions':[3,4]} if 8 not in incomplete and 15 not in incomplete and len(l8)==len(l15)==1 and l8[0]>0 and l15[0]==2*l8[0] else 'undetermined'
    result['request_0d']={n:{'writes':records[n,1]['writes'],'out_fd':None if any(int(records[n,r]['sub_dropped']) for r in (1,2)) else int(records[n,1]['out_fd'])} for n in (12,13,14) if n not in incomplete}
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('tsv',nargs='+');a=p.parse_args()
    try: print(json.dumps(judge(load(a.tsv)),sort_keys=True,separators=(',',':')))
    except (OSError,ValueError,TypeError,KeyError): print('{"error":"invalid_input"}');return 2
    return 0
if __name__=='__main__': sys.exit(main())
