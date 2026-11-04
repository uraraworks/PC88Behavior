#!/usr/bin/env python3
"""窓内の main 割り込み記録を集計する。"""
import argparse
from collections import Counter
from pathlib import Path
import re
import sys

ROW = re.compile(r'\s*\d+\s+\d+\s+\d+\s+main\s+([0-2])\s+(\d+)\s+[0-9A-Fa-f]{4}\s+([0-9A-Fa-f]{4})\s*')
END = re.compile(r'# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件')
HEADER = '# seq    clock   frame  cpu   im  level  ret_pc  handler_pc'


def read(path):
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    if lines.count('# main') != 1 or lines.count('# sub') != 1:
        raise ValueError('main/sub 節が不正')
    start, end = lines.index('# main'), lines.index('# sub')
    if start >= end:
        raise ValueError('節の順序が不正')
    counts = Counter()
    ended = False
    empty = False
    for line in lines[start + 1:end]:
        if not line:
            continue
        if ended:
            raise ValueError('集計後に余分な行')
        if line == HEADER:
            continue
        if line == '# (記録されたイベントなし)':
            if empty or counts:
                raise ValueError('空の記録が不正')
            empty = True
            continue
        m = END.fullmatch(line)
        if m:
            if int(m[1]) or int(m[2]) != sum(counts.values()) or empty != (not counts):
                raise ValueError('記録の欠落または件数不一致')
            ended = True
            continue
        m = ROW.fullmatch(line)
        if not m or empty:
            raise ValueError('イベント行が不正')
        addr = int(m[3], 16)
        counts[(int(m[1]), int(m[2]), 'rom' if addr < 0x8000 else f'{addr:04X}')] += 1
    if not ended:
        raise ValueError('集計行がない')
    sub_lines = lines[end + 1:]
    sub_ends = [END.fullmatch(line) for line in sub_lines if END.fullmatch(line)]
    sub_rows = [line for line in sub_lines if re.fullmatch(r'\s*\d+\s+\d+\s+\d+\s+sub\s+.*', line)]
    if len(sub_ends) != 1 or int(sub_ends[0][1]) or int(sub_ends[0][2]) != len(sub_rows):
        raise ValueError('sub 記録の欠落または件数不一致')
    return counts


def summarize(path, arm, window):
    counts = read(path)
    rows = [f'int {arm} {window} IM{im}-L{level} {addr} {n}'
            for (im, level, addr), n in sorted(counts.items())]
    rows.append(f'total {arm} {window} {sum(counts.values())}')
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('path')
    p.add_argument('--arm', choices=('O', 'S'), required=True)
    p.add_argument('--window', choices=('11400-11999', '12000-12599', '12600-13199'), required=True)
    args = p.parse_args()
    print('\n'.join(summarize(args.path, args.arm, args.window)))


if __name__ == '__main__':
    try:
        main()
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'記録を処理できません: {exc}', file=sys.stderr)
        sys.exit(1)
