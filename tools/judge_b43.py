#!/usr/bin/env python3
"""B43 の対照と列の値を出力する。"""
import argparse, contextlib, csv, json, re
from judge_b35 import load as load_b35
REGS = ('a', 'bc', 'de', 'hl', 'ix', 'iy', 'sp', 'i', 'f')
FIELDS = ('row', 'run', 'complete', *REGS)

def load(paths):
    records = {}
    for path in paths:
        with (contextlib.nullcontext(path) if hasattr(path, 'read') else open(path, encoding='utf-8', newline='')) as f:
            reader = csv.DictReader(f, delimiter='\t')
            if tuple(reader.fieldnames or ()) != FIELDS: raise ValueError('header')
            for row in reader:
                if None in row or any(v is None for v in row.values()) or not re.fullmatch('[1-6]', row['row']) or not re.fullmatch('[12]', row['run']) or row['complete'] not in ('0', '1'): raise ValueError('format')
                for k in REGS:
                    pattern = ('[0-9A-F]{2}' if k in ('a','i','f') else '[0-9A-F]{4}') if row['complete'] == '1' else '-'
                    if not re.fullmatch(pattern, row[k]): raise ValueError('register')
                key = int(row['row']), int(row['run'])
                if key in records: raise ValueError('duplicate')
                records[key] = row
    return records

def judge(records, baseline):
    agreement = {str(n): all((n,r) in records and records[n,r]['complete'] == '1' for r in (1,2)) and all(records[n,1][k] == records[n,2][k] for k in REGS) for n in range(1,7)}
    b35 = {str(n): all((n,r) in records and (n,r) in baseline and records[n,r]['complete'] == baseline[n,r]['complete'] == '1' and all(records[n,r][k] == baseline[n,r][k] for k in REGS if k != 'f') for r in (1,2)) for n in range(1,7)}
    return {'controls_passed': all(agreement.values()) and all(b35.values()), 'agreement': agreement, 'b35_match': b35, 'f_constant': (len({records[n,1]['f'] for n in range(1,7)}) == 1 if all((n,1) in records and records[n,1]['complete'] == '1' for n in range(1,7)) else None), 'registers': {k: {str(n): records[n,1][k] if (n,1) in records else '-' for n in range(1,7)} for k in REGS}}

def main():
    p = argparse.ArgumentParser(); p.add_argument('tsv', nargs='+'); p.add_argument('--b35', nargs='+', required=True); a = p.parse_args()
    try: print(json.dumps(judge(load(a.tsv), load_b35(a.b35)), sort_keys=True, separators=(',', ':')))
    except (OSError, ValueError, KeyError, TypeError): print('{"error":"invalid_input"}'); return 2
    return 0
if __name__ == '__main__': raise SystemExit(main())
