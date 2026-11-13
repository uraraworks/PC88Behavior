#!/usr/bin/env python3
"""完全に自作した集計入力で値の漏出と比較を検査する。"""
import json
from b92_summary import relation, screen, summarize


def run(value, intervened):
    return {'out': [[49, value]], 'screen': [0xF300, 0xF301], 'returned': True,
            'sp': 0xF000, 'frames': 2, 'interventions': intervened,
            'reached': True, 'complete': True, 'escaped': True,
            'prior_out31': True, 'prior_e6c2': True, 'error': None}

values = [0, 1, 2, 4, 8, 16, 32, 64, 128, 255]
base = run(173, 0)
data = {'baseline': [base, run(173, 0)], 'arms': [
    {'address': 0xE60E, 'input': v, 'run': run(v, 1)} for v in values] + [
    {'address': 0xE700, 'input': v, 'run': run(173, 1)} for v in values]}
result = summarize(data)
assert result['基準2回比較']['OUT値一致'] == [True]
assert all(x['OUT値一致'] == [True] for x in result['腕']['E700'].values())
assert 'そのまま' in result['関係']['E60E'][0]
assert '定数（値はリポジトリ外）' in result['関係']['E700'][0]
assert '173' not in json.dumps(result, ensure_ascii=False)
assert any(isinstance(x, dict) and 'ビット対応' in x
           for x in relation(values, [x & 0x0F for x in values]))
assert any(isinstance(x, dict) and 'ビット対応' in x
           for x in relation(values, [x ^ 0xFF for x in values]))
assert relation(values, [(x + 1) & 255 for x in values]) == ['未分類']
assert screen([0xF300, 0xF302])['範囲'] != screen([0xF300, 0xF301, 0xF302])['範囲']
print('B92 集計の自作データ検査 PASS')
