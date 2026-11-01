#!/usr/bin/env python3
"""B52 の事前登録対照を判定する。"""
import argparse, csv, json
FIELDS = ('row','run','complete','timeout','count','written','before','after','match','executed')
def load(paths):
    result = {}
    for path in paths:
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            if tuple(reader.fieldnames or ()) != FIELDS: raise ValueError('header')
            for r in reader:
                key = int(r['row']), int(r['run'])
                if key in result or key[0] not in range(1,9) or key[1] not in (1,2): raise ValueError('key')
                if r['complete'] not in ('0','1') or r['timeout'] not in ('0','1','-') or any(not r[k].isdigit() or int(r[k]) > 64 for k in ('count','written','before','after')) or r['match'] not in ('0','1','-') or r['executed'] not in ('0','1','-'): raise ValueError('value')
                result[key] = r
    return result
def judge(official, own):
    def stable(records):
        return {str(n): all((n,i) in records for i in (1,2)) and all(records[n,1][k] == records[n,2][k] for k in FIELDS if k != 'run') for n in range(1,9)}
    a,b=stable(official),stable(own)
    control = all(a.values()) and all(b.values()) and official[8,1]['match']=='0' and any(official[1,1][k] != own[1,1][k] for k in FIELDS if k not in ('row','run'))
    return {'controls_passed':control,'official_agreement':a,'self_agreement':b}
def main():
    p=argparse.ArgumentParser();p.add_argument('--official',nargs='+',required=True);p.add_argument('--self',dest='own',nargs='+',required=True);a=p.parse_args()
    try: print(json.dumps(judge(load(a.official),load(a.own)),sort_keys=True))
    except (OSError,ValueError,KeyError,TypeError): print('{"error":"invalid_input"}');return 2
    return 0
if __name__=='__main__': raise SystemExit(main())
