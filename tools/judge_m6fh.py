#!/usr/bin/env python3
"""m6f-h 事前登録第5節の判定。出力は候補名・オフセットだけ。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import m6fh_script as script


def judge(doc: dict) -> dict:
    runs = doc['runs']
    if len(runs) != 8 or {(r['arm'], r['repetition']) for r in runs} != {(a,n) for a in script.ARMS for n in (1,2)}:
        return {'status':'gate_failed', 'reason':'runs'}
    if any(r.get('gate') == 'NG' or r.get('drive1_sha_ok') is not True or
           r.get('g7_max_position', -1) > r.get('g7_limit', -1) for r in runs):
        return {'status':'gate_failed', 'reason':'G5_G6_G7'}
    arms = {}
    for arm in script.ARMS:
        pair = [next(r for r in runs if r['arm']==arm and r['repetition']==n) for n in (1,2)]
        sets = [tuple(c for c in script.candidate_ids(arm) if r['candidates'][c]['match']) for r in pair]
        if sets[0] != sets[1]:
            return {'status':'gate_failed', 'reason':'G4', 'arm':arm}
        elif len(sets[0]) == 0:
            arms[arm] = f'inconclusive_{arm}_no_candidate'
        elif len(sets[0]) > 1:
            arms[arm] = f'inconclusive_{arm}_multiple'
        else:
            arms[arm] = sets[0][0]
    h1, h3 = arms['H-1'], arms['H-3']
    same = (h1.rsplit('_', 2)[-2:] == h3.rsplit('_', 2)[-2:]) if h1 in script.candidate_ids('H-1') and h3 in script.candidate_ids('H-3') else None
    return {'status':'OK', 'arms':arms,
            'H-IV':'chain_concatenates' if arms['H-2'] in script.candidate_ids('H-2') else arms['H-2'],
            'H-V': 'data_same_as_ascii_program' if same is True else 'data_differs' if same is False else 'inconclusive_H-V'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--result', type=Path, required=True)
    a=p.parse_args()
    try:
        out=judge(json.loads(a.result.read_text(encoding='utf-8')))
    except (OSError, ValueError, KeyError, TypeError):
        out={'status':'gate_failed','reason':'result_format'}
    print(json.dumps(out,sort_keys=True,separators=(',',':')))
    return 0 if out['status']=='OK' else 1


if __name__=='__main__':
    raise SystemExit(main())
