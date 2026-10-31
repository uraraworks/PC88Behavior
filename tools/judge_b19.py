#!/usr/bin/env python3
"""B19 の白リストと事前登録済み判定。"""
import argparse, csv, json, re
FIELDS = ('row','run','complete','sent','timeout','rom','ram','high_rom','high_ram','crossings','read1','stamp1','read2','stamp2','out_fd','sub_dropped')
from judge_b17 import load as load17

def load(paths):
    # B17 と同じ書式検査を使い、B19 固有の行・読み要求を検査する。
    import io
    records = {}
    for path in paths:
        with open(path, encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f, delimiter='\t')
            if tuple(reader.fieldnames or ()) != FIELDS: raise ValueError('header')
            for row in reader:
                if None in row or row['row'] not in '12345' or len(row['row']) != 1: raise ValueError('row')
                n = int(row['row']); proxy = row.copy()
                # B17 の読み要求ありの行番号へ写像する。
                proxy['row'] = '3' if n == 3 else '2'
                buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=FIELDS, delimiter='\t', lineterminator='\n'); w.writeheader(); w.writerow(proxy); buf.seek(0)
                load17([buf])
                key = (n, int(row['run']))
                if key in records: raise ValueError('duplicate')
                records[key] = row
    return records

def judge(records):
    same = {n: all((n,r) in records for r in (1,2)) and all(records[n,1][k] == records[n,2][k] for k in FIELDS if k != 'run') for n in range(1,6)}
    def marker(n, addr):
        spans = records[n,1]['ram'].split(';')
        return any(int(x[:4],16) <= addr <= int(x[5:9],16) for x in spans if x != '-')
    def state(n, addr):
        a,b = marker(n,addr),marker(n,addr+1)
        return 'enabled' if a and not b else 'disabled' if b and not a else 'inconclusive'
    control = all(same.values()) and state(4,0x7810)=='enabled'
    result = {'controls':control, 'same':[same[n] for n in range(1,6)], 'row1':'inconclusive','row2':'inconclusive','row3':'inconclusive','row5':'inconclusive','int':[]}
    if all((n,1) in records for n in range(1,6)):
        for n in range(1,6):
            result['int'].append(sum(int(x.split(':')[1].split(',')[3]) for x in records[n,1]['crossings'].split(';') if x != '-'))
    if control:
        for n in (1,2,3,5): result[f'row{n}'] = state(n,0x7810 if n==1 else 0x7820)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('tsv',nargs='+');a=p.parse_args()
    try: print(json.dumps(judge(load(a.tsv)),sort_keys=True,separators=(',',':')))
    except (OSError,ValueError,TypeError,KeyError,IndexError): print('{"error":"invalid_input"}');return 2
    return 0
if __name__=='__main__': raise SystemExit(main())
