#!/usr/bin/env python3
"""B21 の事前登録第4節による判定。"""
import argparse, csv, json, re
FIELDS = ('row', 'run', 'response', 'timeout', 'boundary')

def load(paths):
    records = {}
    for path in paths:
        with open(path, encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f, delimiter='\t')
            if tuple(reader.fieldnames or ()) != FIELDS: raise ValueError('header')
            for r in reader:
                if None in r or not re.fullmatch('[1-7]', r['row']) or not re.fullmatch('[12]', r['run']): raise ValueError('row')
                if not re.fullmatch(r'(?:[0-9A-F]{2}|none)', r['response']) or r['timeout'] not in ('0','1','unknown'): raise ValueError('response')
                if not re.fullmatch(r'(?:-|(?:A [0-9A-F]{4} [0-9]+ [0-9]+ [0-9]+ [0-9]+ [0-9]+|W [0-9A-F]{4} (?:rom|ram) [0-9]+)(?:;(?:A [0-9A-F]{4} [0-9]+ [0-9]+ [0-9]+ [0-9]+ [0-9]+|W [0-9A-F]{4} (?:rom|ram) [0-9]+))*)', r['boundary']): raise ValueError('boundary')
                key = int(r['row']), int(r['run'])
                if key in records: raise ValueError('duplicate')
                records[key] = r
    return records

def judge(records):
    agreement = {n: all((n, r) in records for r in (1, 2)) and records[n, 1]['response'] == records[n, 2]['response'] for n in range(1, 8)}
    passed = all(agreement.values()) and records[1, 1]['response'] == 'C0'
    return {'controls_passed': passed, 'agreement': agreement, 'responses': {n: records[n, 1]['response'] if agreement[n] else None for n in range(1, 8)}}

def main():
    p = argparse.ArgumentParser(); p.add_argument('tsv', nargs='+'); a = p.parse_args()
    try: print(json.dumps(judge(load(a.tsv)), sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError): print('{"error":"invalid_input"}'); return 2
    return 0
if __name__ == '__main__': raise SystemExit(main())
