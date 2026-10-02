#!/usr/bin/env python3
"""m6f-kの判定JSONを、固定された公式の10判定に照合する。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

import compare_screen_signatures as css
import m6fk_judge as judge
from m6fk_script import ARMS


def load(path: Path) -> dict[str, str]:
    rows = [line.split('\t') for line in path.read_text(encoding='ascii').splitlines()
            if line and not line.startswith('#')]
    if len(rows) != len(ARMS) or any(len(row) != 2 for row in rows):
        raise ValueError('期待値形式')
    result = dict(rows)
    candidates = judge.candidate_ids()
    if tuple(result) != ARMS or any(value not in candidates[arm] for arm,value in result.items()):
        raise ValueError('期待値集合')
    return result


def entry_lines(screen: css.ScreenSignature) -> list[dict]:
    return [dict(physical_row=row, char_count=item.char_count, sha256=item.sha256)
            for row, item in css.without_ready_prompt(screen)]


def compare(expected: dict[str,str], root: dict) -> dict[str,bool]:
    if (not isinstance(root,dict) or type(root.get('schema')) is not int
            or root['schema'] != 1 or type(root.get('frontend_launch_count')) is not int
            or root['frontend_launch_count'] != 20
            or not isinstance(root.get('observations'),dict)
            or set(root['observations']) != set(ARMS)):
        raise ValueError('結果集合')
    observations = root['observations']
    for arm, runs in observations.items():
        if (not isinstance(runs,list) or len(runs) != 2
                or any(not isinstance(run,dict) for run in runs)
                or any(run.get('g11_input_ready') is not True or type(run.get('g8_max_position')) is not int
                       or run['g8_max_position'] != 159
                       or not isinstance(run.get('candidates'),list)
                       or len(run['candidates']) != 1
                       or run['candidates'][0] not in judge.candidate_ids()[arm] for run in runs)):
            raise ValueError('結果形式')
    # JSON中のjudgmentだけを信頼せず、2走一致の判定を再計算する。
    derived = judge.combine(observations)
    if root.get('judgment') != derived:
        raise ValueError('判定不整合')
    return {arm: derived['judgments'][arm] == expected[arm] for arm in ARMS}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('mode',choices=('validate','compare'))
    ap.add_argument('expected',type=Path)
    ap.add_argument('result',type=Path,nargs='?')
    args = ap.parse_args()
    try:
        expected = load(args.expected)
        if args.mode == 'validate':
            print('OK'); return 0
        if args.result is None:
            raise ValueError('結果なし')
        checked = compare(expected,json.loads(args.result.read_text(encoding='ascii')))
        for arm,ok in checked.items():
            print(f"{arm}\t{'OK' if ok else 'NG'}")
        return 0 if all(checked.values()) else 1
    except (OSError,ValueError,TypeError,KeyError):
        print('NG 形式',file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
