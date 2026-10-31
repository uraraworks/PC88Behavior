#!/usr/bin/env python3
"""B10 生ログを白リスト項目だけに変換する。"""
import argparse
import csv
import io
import re
import sys
from pathlib import Path
from analyze_main_to_sub import parse_iolog
from analyze_m6ia_main_sub import read_memlog, require_no_drops, AnalysisError
from analyze_m6ik import status_names
from judge_b10 import FIELDS, PATTERNS, ROWS, load


def analyze(row, run, events, memory):
    values = {e.addr: e.value for e in memory if 0xDF00 <= e.addr <= 0xDF53}
    if values.get(0xDF53) != 1 or 0xDF50 not in values or 0xDF51 not in values:
        raise ValueError('incomplete')
    count = values[0xDF50] + 256 * values[0xDF51]
    if count > (ROWS[row][2]+1)*256 or values.get(0xDF52) not in (0, 1):
        raise ValueError('count')
    blocks = []
    for i in range((count+255)//256):
        stamp = [values.get(0xDF00+i*4+j) for j in range(4)]
        if count-i*256 >= 4 and stamp[0] == 0xA1 and stamp[1] is not None and stamp[1] < 40 and stamp[2] in (0,1) and stamp[3] is not None and 1 <= stamp[3] <= 16:
            blocks.append(','.join(map(str, stamp[1:])))
        else:
            blocks.append('other')
    writes = [e for e in events if e.cpu == 'sub' and e.kind == 'OUT' and e.port == '00FB']
    reads, st0, st1 = [], [], []
    for i, e in enumerate(writes):
        if e.value not in (0x46, 0x66) or i+8 >= len(writes):
            continue
        a = writes[i+1:i+9]
        if any(x.value is None for x in a):
            raise ValueError('missing command')
        end = writes[i+9].clock if i+9 < len(writes) else float('inf')
        result = [x.value for x in events if x.cpu == 'sub' and x.kind == 'IN' and x.port == '00FB' and a[-1].clock < x.clock < end and x.value is not None]
        if len(result) < 7:
            raise ValueError('missing status')
        reads.append(','.join(str(a[j].value) for j in (1,2,3,5)))
        status = status_names(result[-7], result[-6])
        st0.append(','.join(status['st0']))
        st1.append(','.join(status['st1']) or 'none')
    vals = [str(row),str(run),str(count),str(values[0xDF52]),';'.join(blocks) or '-',str(len(reads)), ';'.join(reads) or '-', ';'.join(st0) or '-', ';'.join(st1) or '-']
    if any(not re.fullmatch(p, v) for p,v in zip(PATTERNS, vals)):
        raise ValueError('whitelist')
    return vals


def main():
    p=argparse.ArgumentParser(); p.add_argument('--row',type=int,choices=range(1,12),required=True); p.add_argument('--run',type=int,choices=(1,2),required=True); p.add_argument('--iolog',type=Path,required=True); p.add_argument('--memlog',type=Path,required=True)
    a=p.parse_args()
    try:
        require_no_drops(a.iolog)
        events, masked=parse_iolog(a.iolog)
        if masked or not events or events[0].frame != 0: raise ValueError('iolog')
        sends=[e.value for e in events if e.cpu == 'main' and e.kind == 'OUT' and e.port == '00FD']
        track, sector, p1 = ROWS[a.row]
        want=[2,p1,0,track,sector + (a.row == 11)]
        if not any(sends[i:i+5] == want for i in range(len(sends)-4)): raise ValueError('request')
        vals=analyze(a.row,a.run,events,read_memlog(a.memlog))
        out=io.StringIO(newline=''); w=csv.writer(out,delimiter='\t',lineterminator='\n'); w.writerow(FIELDS); w.writerow(vals)
        # 判定器と同じ検証も全行に適用してから公開する。
        load([io.StringIO(out.getvalue())])
        sys.stdout.write(out.getvalue())
    except (OSError, ValueError, IndexError, TypeError, AnalysisError):
        print('解析失敗',file=sys.stderr); return 2
    return 0
if __name__ == '__main__': sys.exit(main())
