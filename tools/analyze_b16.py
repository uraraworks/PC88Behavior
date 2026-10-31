#!/usr/bin/env python3
"""B16 の生記録を値のない TSV に変換する。"""
import argparse, csv, io, re, sys
from pathlib import Path
from analyze_main_to_sub import parse_iolog
from analyze_m6ia_main_sub import read_memlog, AnalysisError
from b15_whitelist_sub_boundary import filter_lines
from judge_b16 import FIELDS, PATTERNS, load

ROWS = ((), (12,0,0,0,0), (12,1,0,0,0), (12,0,1,0,0),
        (12,0,0,1,0), (12,0,0,0,1), (12,16,0,0,120),
        (12,0,120,16,0), (12,120,0,0,16), (12,16,0,120,0),
        (12,0,120,0,16), (13,0,0,0,0), (13,0,120,16,0),
        (13,16,0,0,120), (12,0,120,32,0))

def io_drops(path):
    sections = {'main': [], 'sub': []}
    section = None
    for line in path.read_text(encoding='utf-8', errors='strict').splitlines():
        if line.strip() in ('# main', '# sub'):
            section = line.strip()[2:]
            continue
        drops = re.findall(r'取りこぼし:\s*([0-9]+)件', line)
        if drops and section is None: raise AnalysisError('log_drops')
        if section is not None: sections[section].extend(map(int, drops))
    if any(not values for values in sections.values()) or any(sections['main']):
        raise AnalysisError('log_drops')
    return sum(sections['sub'])

def analyze(row,run,events,memory,lines,sub_dropped=0):
    m={e.addr:e.value for e in memory if 0xdf50<=e.addr<=0xdf53}
    complete = m.get(0xdf53) == 1
    if complete and (m.get(0xdf52) not in (0,1) or 0xdf50 not in m): raise ValueError('incomplete')
    # 送信成功数に対応する要求列が実際に観測されたことを確認する。
    sent=[e.value for e in events if e.cpu=='main' and e.kind=='OUT' and e.port=='00FD']
    request=ROWS[row-1] + ((0x55,)*64 if row != 1 else ())
    if complete:
        count=m[0xdf50]
        if count > len(request): raise ValueError('count')
        expected=[0,0x17,0x0f]+list(request[:count])
        if not any(sent[i:i+len(expected)]==expected for i in range(len(sent)-len(expected)+1)):
            raise ValueError('request')
    filtered,dropped=filter_lines(lines,'G2','self')
    if dropped: raise ValueError('boundary')
    writes=[];cross=[]
    for line in filtered[2:]:
        parts=line.split()
        if parts[0]=='A': cross.append(parts[1]+':'+','.join(parts[2:]))
        elif parts[2]=='rom': writes.append(parts[1]+':'+parts[3])
    outfd=sum(e.cpu=='sub' and e.kind=='OUT' and e.port=='00FD' for e in events)
    vals=[str(row),str(run),str(int(complete)),str(m[0xdf50]) if complete else '-',str(m[0xdf52]) if complete else '-',';'.join(writes) or '-',';'.join(cross) or '-',str(outfd),str(sub_dropped)]
    if any(not re.fullmatch(p,v) for p,v in zip(PATTERNS,vals)): raise ValueError('whitelist')
    return vals

def main():
    p=argparse.ArgumentParser();p.add_argument('--row',type=int,choices=range(1,16),required=True);p.add_argument('--run',type=int,choices=(1,2),required=True)
    for name in ('iolog','memlog','boundary'): p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    try:
        sub_dropped=io_drops(a.iolog);events,masked=parse_iolog(a.iolog)
        if masked or not events or events[0].frame!=0: raise ValueError('iolog')
        vals=analyze(a.row,a.run,events,read_memlog(a.memlog),a.boundary.read_text().splitlines(),sub_dropped)
        out=io.StringIO(newline='');w=csv.writer(out,delimiter='\t',lineterminator='\n');w.writerow(FIELDS);w.writerow(vals)
        load([io.StringIO(out.getvalue())]);sys.stdout.write(out.getvalue())
    except (OSError,ValueError,IndexError,TypeError,AnalysisError): print('解析失敗',file=sys.stderr);return 2
    return 0
if __name__=='__main__': sys.exit(main())
