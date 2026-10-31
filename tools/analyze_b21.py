#!/usr/bin/env python3
"""B21 の応答、時間切れ、サブ境界を集約する。"""
import argparse, csv, sys
from pathlib import Path
from analyze_m6ia_main_sub import read_memlog, AnalysisError
from b15_whitelist_sub_boundary import filter_lines
from judge_b21 import FIELDS

def analyze(row, run, memory, lines):
    m = {e.addr: e.value for e in memory if 0xdf50 <= e.addr <= 0xdf59}
    complete = m.get(0xdf53) == 1
    response = f"{m[0xdf58]:02X}" if m.get(0xdf59) == 1 and 0xdf58 in m else 'none'
    timeout = str(m.get(0xdf52, 0)) if complete else 'unknown'
    boundary, dropped = filter_lines(lines, 'G2', 'self')
    if dropped or timeout not in ('0','1','unknown'): raise ValueError('record')
    # 各番地の回数を保持する。filter_lines は構文と重複の検査に使う。
    return [str(row), str(run), response, timeout, ';'.join(sorted(line for line in lines if line)) or '-']

def main():
    p = argparse.ArgumentParser(); p.add_argument('--row', type=int, choices=range(1,8), required=True); p.add_argument('--run', type=int, choices=(1,2), required=True)
    p.add_argument('--memlog', type=Path, required=True); p.add_argument('--boundary', type=Path, required=True); a=p.parse_args()
    try: values=analyze(a.row,a.run,read_memlog(a.memlog),a.boundary.read_text().splitlines())
    except (OSError, ValueError, AnalysisError): print('解析失敗',file=sys.stderr); return 2
    w=csv.writer(sys.stdout,delimiter='\t',lineterminator='\n'); w.writerow(FIELDS); w.writerow(values); return 0
if __name__ == '__main__': raise SystemExit(main())
