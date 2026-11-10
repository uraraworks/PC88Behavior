#!/usr/bin/env python3
"""l1-ipl.md 付録A・第3節から、L3自己検査用の基準OUT列を作る。"""
import argparse
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
spec = (root / 'docs/spec/l1-ipl.md').read_text(encoding='utf-8')
appendix = spec.split('## 付録A.', 1)[1].split('```', 2)[1]
rows = re.findall(r'^\s*(\d+)\s+OUT\s+([0-9A-F]{2})\s+<-\s+([0-9A-F]{2})', appendix, re.M)
if [int(row[0]) for row in rows] != list(range(1, 351)):
    raise SystemExit('付録Aの350件を取得できない')
section = spec.split('## 3. 観測', 1)[1].split('```', 2)[1]
steady = re.findall(r'^OUT\s+([0-9A-F]{2})\s+←\s+([0-9A-F]{2})', section, re.M)
if len(steady) != 7 or [(p, v) for _, p, v in rows[-7:]] != steady:
    raise SystemExit('定常状態の7件が付録A末尾と一致しない')
values = [(p, v) for _, p, v in rows] + steady
args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open('w', encoding='ascii') as f:
    f.write('# main\n')
    for index, (port, value) in enumerate(values, 1):
        f.write(f'{index} 0 main OUT {port.zfill(4)} {value} 0000\n')
