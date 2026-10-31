#!/usr/bin/env python3
"""B26 事前登録第4節の対照と観測値を出力する。"""
import argparse
import contextlib
import csv
import json
import re

FIELDS = ('row', 'run', 'complete', 'send_timeout', 'body_count', 'stamps', 'extra_counts', 'extra', 'timeouts')
LENGTHS = (3840, 3840, 3840, 256, 3840, 3584, 0)
PHASES = ((1,), (1, 2), (1, 2, 3), (1,), (1,), (1,), (2,))

def load(paths):
    records = {}
    for path in paths:
        with (contextlib.nullcontext(path) if hasattr(path, 'read') else open(path, encoding='utf-8', newline='')) as f:
            reader = csv.DictReader(f, delimiter='\t')
            if tuple(reader.fieldnames or ()) != FIELDS:
                raise ValueError('header')
            for r in reader:
                if None in r or any(r[k] is None for k in FIELDS): raise ValueError('columns')
                if not re.fullmatch('[1-7]', r['row']) or not re.fullmatch('[12]', r['run']): raise ValueError('key')
                row, run = int(r['row']), int(r['run'])
                if (row, run) in records or r['complete'] not in ('0', '1') or r['send_timeout'] not in ('0', '1', '-'): raise ValueError('state')
                if not re.fullmatch(r'0|[1-9][0-9]*', r['body_count']) or int(r['body_count']) > LENGTHS[row-1]: raise ValueError('count')
                stamps = [] if r['stamps'] == '-' else r['stamps'].split(';')
                if len(stamps) != (int(r['body_count']) + 255)//256 or any(not re.fullmatch(r'other|[0-9]+,[0-9]+,[0-9]+', x) for x in stamps): raise ValueError('stamps')
                extra = r['extra'].split('|')
                times = r['timeouts'].split('|')
                counts = r['extra_counts'].split('|')
                if len(extra) != len(PHASES[row-1]) or len(times) != len(extra) or len(counts) != len(extra): raise ValueError('phases')
                if any(not re.fullmatch(r'-|[0-9A-F]{2}(?:;[0-9A-F]{2}){0,3}', x) for x in extra) or any(x not in ('0', '1', '-') for x in times): raise ValueError('phase')
                if counts != [str(0 if x == '-' else len(x.split(';'))) for x in extra]: raise ValueError('extra counts')
                records[row, run] = r
    return records

def judge(records):
    same = {str(n): all((n, r) in records for r in (1, 2)) and all(records[n, 1][k] == records[n, 2][k] for k in FIELDS if k != 'run') for n in range(1, 8)}
    expected = ';'.join(f'0,0,{i}' for i in range(2, 17))
    control = all(same.values()) and records[1, 1]['stamps'] == expected
    return {'controls_passed': control, 'agreement': same, 'observations': {str(n): {k: v for k, v in records[n, 1].items() if k not in ('row', 'run')} for n in range(1, 8) if (n, 1) in records}}

def main():
    p = argparse.ArgumentParser(); p.add_argument('tsv', nargs='+'); a = p.parse_args()
    try: print(json.dumps(judge(load(a.tsv)), ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError): print('{"error":"invalid_input"}'); return 2
    return 0
if __name__ == '__main__': raise SystemExit(main())
