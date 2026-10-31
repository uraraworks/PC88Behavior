#!/usr/bin/env python3
"""B12 生ログから白リスト項目だけを出力する。"""
import argparse, csv, io, re, sys
from collections import Counter
from pathlib import Path
from analyze_main_to_sub import parse_iolog
from analyze_m6ia_main_sub import read_memlog, require_no_drops, AnalysisError
from analyze_m6ik import status_names
from judge_b12 import ROWS,FIELDS,PATTERNS,load

# uPD765 のコマンド長（コマンドバイトを含む）。
CMDS={2:('read_track',9),3:('specify',3),4:('sense_drive_status',2),5:('write_data',9),6:('read_data',9),7:('recalibrate',2),8:('sense_interrupt',1),9:('write_deleted_data',9),10:('read_id',2),12:('read_deleted_data',9),13:('format_track',6),15:('seek',3),17:('scan_equal',9),25:('scan_low_or_equal',9),29:('scan_high_or_equal',9)}

def analyze(row,run,events,memory):
    requests=[(0,2,1),(2,1,2)] if row==12 else [ROWS[row]]
    sends=[e for e in events if e.cpu=='main' and e.kind=='OUT' and e.port=='00FD']
    starts=[]; at=0
    for t,r,p in requests:
        want=[2,p,0,t,r+(row==11)]
        for i in range(at,len(sends)-4):
            if [e.value for e in sends[i:i+5]]==want:
                starts.append(sends[i].clock); at=i+5; break
        else: raise ValueError('request')
    values={e.addr:e.value for e in memory if 0xDF00<=e.addr<=0xDFE7}
    rows=[]
    for q,(t,r,p) in enumerate(requests):
        base=0xDFE0+q*4
        if values.get(base+3)!=1 or values.get(base+2) not in (0,1) or base not in values or base+1 not in values: raise ValueError('incomplete')
        count=values[base]+256*values[base+1]
        if count>(p+1)*1024: raise ValueError('count')
        blocks=[]
        for i in range((count+255)//256):
            stamp=[values.get(0xDF00+q*0x90+i*5+j) for j in range(5)]
            ident,c,h,sec,b=stamp
            valid=(count-i*256>=5 and ident==0xA1 and c is not None and 0<=c<40 and h in (0,1) and sec is not None and b is not None and (1<=sec<=16 and b==0 if (c,h)==(0,0) else 1<=sec<=5 and 0<=b<4))
            blocks.append(f'{c},{h},{sec},{b}' if valid else 'other')
        end=starts[q+1] if q+1<len(starts) else float('inf')
        ev=[e for e in events if starts[q]<=e.clock<end and e.cpu=='sub' and e.port=='00FB']
        writes=[e for e in ev if e.kind=='OUT']; reads=[]; st0=[]; st1=[]; others=Counter(); ids=0; i=0
        while i<len(writes):
            cmd=writes[i]; name,length=CMDS.get(cmd.value & 31,('unknown',1))
            if i+length>len(writes): raise ValueError('command')
            args=writes[i+1:i+length]
            if name=='read_data':
                if any(x.value is None for x in args): raise ValueError('command')
                limit=writes[i+length].clock if i+length<len(writes) else end
                result=[x.value for x in ev if x.kind=='IN' and args[-1].clock<x.clock<limit and x.value is not None]
                if len(result)<7: raise ValueError('status')
                reads.append(','.join(str(args[j].value) for j in (1,2,3,4,5)))
                status=status_names(result[-7],result[-6]); st0.append(','.join(status['st0'])); st1.append(','.join(status['st1']) or 'none')
            elif name=='read_id': ids+=1
            else: others[name]+=1
            i+=length
        vals=[str(row),str(run),str(q+1),str(count),str(values[base+2]),';'.join(blocks) or '-',str(len(reads)),';'.join(reads) or '-',str(ids),';'.join(f'{k}:{v}' for k,v in sorted(others.items())) or '-',';'.join(st0) or '-',';'.join(st1) or '-']
        if any(not re.fullmatch(pattern,val) for pattern,val in zip(PATTERNS,vals)): raise ValueError('whitelist')
        rows.append(vals)
    return rows

def main():
    p=argparse.ArgumentParser(); p.add_argument('--row',type=int,choices=range(1,13),required=True); p.add_argument('--run',type=int,choices=(1,2),required=True); p.add_argument('--iolog',type=Path,required=True); p.add_argument('--memlog',type=Path,required=True); a=p.parse_args()
    try:
        require_no_drops(a.iolog); events,masked=parse_iolog(a.iolog)
        if masked or not events or events[0].frame!=0: raise ValueError('iolog')
        vals=analyze(a.row,a.run,events,read_memlog(a.memlog)); out=io.StringIO(newline=''); w=csv.writer(out,delimiter='\t',lineterminator='\n'); w.writerow(FIELDS); w.writerows(vals)
        load([io.StringIO(out.getvalue())]); sys.stdout.write(out.getvalue())
    except (OSError,ValueError,IndexError,TypeError,AnalysisError): print('解析失敗',file=sys.stderr); return 2
    return 0
if __name__=='__main__': sys.exit(main())
