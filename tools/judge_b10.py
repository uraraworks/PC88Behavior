#!/usr/bin/env python3
"""事前登録 B10 §5 の判定。入力は白リスト TSV の2走分。"""
import argparse
import csv
import contextlib
import json
import re
import sys

ROWS = {1:(0,1,1), 2:(0,1,0), 3:(0,1,2), 4:(0,1,3),
        5:(0,2,15), 6:(0,1,16), 7:(0,16,1), 8:(0,16,2),
        9:(1,16,2), 10:(0,1,17), 11:(0,2,2)}
FIELDS = ('row','run','count','timeout','blocks','read_count','reads','st0','st1')
COORD = r'(?:[0-9]+,[01],[0-9]+|other)'
PATTERNS = (r'(?:[1-9]|10|11)', r'[12]', r'(?:0|[1-9][0-9]*)', r'[01]',
            rf'(?:-|{COORD}(?:;{COORD})*)', r'(?:0|[1-9][0-9]*)',
            r'(?:-|[0-9]+,[01],[0-9]+,[0-9]+(?:;[0-9]+,[01],[0-9]+,[0-9]+)*)',
            r'(?:-|[a-z_0-9]+(?:,[a-z_0-9]+)*(?:;[a-z_0-9]+(?:,[a-z_0-9]+)*)*)',
            r'(?:-|[a-z_0-9]+(?:,[a-z_0-9]+)*(?:;[a-z_0-9]+(?:,[a-z_0-9]+)*)*)')
ST0 = {'normal_termination','abnormal_termination','invalid_command','abnormal_ready_transition','seek_end','equipment_check','not_ready','head_address','unit_bit1','unit_bit0'}
ST1 = {'end_of_cylinder','data_error','overrun','no_data','not_writable','missing_address_mark','none'}

def load(paths):
    records = {}
    for path in paths:
        with (contextlib.nullcontext(path) if hasattr(path, 'read') else open(path, newline='', encoding='utf-8')) as f:
            reader = csv.DictReader(f, delimiter='\t')
            if tuple(reader.fieldnames or ()) != FIELDS:
                raise ValueError('header')
            for r in reader:
                if None in r or any(not re.fullmatch(p, r[k] or '') for k,p in zip(FIELDS,PATTERNS)):
                    raise ValueError('format')
                key = (int(r['row']), int(r['run']))
                if key in records or int(r['count']) > (ROWS[key[0]][2]+1)*256:
                    raise ValueError('duplicate or count')
                blocks = [] if r['blocks']=='-' else r['blocks'].split(';')
                reads = [] if r['reads']=='-' else r['reads'].split(';')
                if len(blocks) != (int(r['count'])+255)//256 or len(reads) != int(r['read_count']):
                    raise ValueError('length')
                for field, allowed in [('st0',ST0),('st1',ST1)]:
                    if ((r[field] == '-') != (not reads) or (reads and len(r[field].split(';')) != len(reads)) or
                        (r[field] != '-' and any(x not in allowed for x in re.split('[,;]',r[field])))):
                        raise ValueError('status')
                records[key] = r
    return records

def judge(records):
    same = {n: ((n,1) in records and (n,2) in records and
                 all(records[n,1][k] == records[n,2][k] for k in FIELDS if k != 'run'))
            for n in ROWS}
    def blocks(n):
        s = records[n,1]['blocks']
        return [] if s == '-' else s.split(';')
    def expected(n):
        t,r,p = ROWS[n]
        return [f'{t//2},{t%2},{r+i}' for i in range(p)]
    controls = (all(same[n] for n in (1,2,11)) and
                int(records[1,1]['count']) == 256 and blocks(1) == expected(1) and
                int(records[2,1]['count']) == 0 and bool(blocks(11)) and
                blocks(11)[0] != expected(11)[0])
    result = {'controls_passed': controls, 'agreement': same, 'p1': 'inconclusive', 'crossing': {}}
    if not controls:
        return result
    if all(same[n] for n in (3,4,5,6)):
        result['p1'] = ('count' if all(int(records[n,1]['count']) == ROWS[n][2]*256 and
                        records[n,1]['timeout']=='1' and blocks(n)==expected(n)
                        for n in (3,4,5,6)) else 'not_count')
    for n in (8,9,10):
        if not same[n]:
            result['crossing'][n] = {'judgment':'inconclusive'}
            continue
        r = records[n,1]; b = blocks(n); t, start, _ = ROWS[n]
        crossed = any(x != 'other' and tuple(map(int,x.split(',')))[:2] != (t//2,t%2) for x in b)
        classification = 'crosses' if crossed else ('fails' if not b or 'other' in b else 'does_not_cross')
        result['crossing'][n] = {'judgment':classification, 'blocks':b, 'reads':r['reads']}
    return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('tsv', nargs='+'); args=p.parse_args()
    try:
        print(json.dumps(judge(load(args.tsv)), sort_keys=True, separators=(',',':')))
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({'error':'invalid_input'})); return 2
    return 0
if __name__ == '__main__':
    sys.exit(main())
