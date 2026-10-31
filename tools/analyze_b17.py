#!/usr/bin/env python3
"""B17 の生記録を白リストの形に集約する。"""
import argparse,csv,io,re,sys
from pathlib import Path
from analyze_main_to_sub import parse_iolog
from analyze_m6ia_main_sub import read_memlog,AnalysisError
from analyze_b16 import io_drops
from b15_whitelist_sub_boundary import filter_lines
from judge_b17 import FIELDS,PATTERNS,load

def analyze(row,run,events,memory,lines,drops=0):
    m={e.addr:e.value for e in memory if 0xdf00<=e.addr<=0xdf57}; complete=m.get(0xdf53)==1
    if complete and (any(k not in m for k in (0xdf50,0xdf51,0xdf52,0xdf54,0xdf55,0xdf56,0xdf57)) or m[0xdf52] not in (0,1)): raise ValueError('memory')
    counts=[m.get(0xdf50,0)+256*m.get(0xdf51,0),m.get(0xdf56,0)+256*m.get(0xdf57,0)]
    if complete:
        address={4:0x6000,5:0x7900}.get(row,0x7800)
        length=256 if row==5 else 16
        def payload(marker): return [0x3e,0x5a,0x32,marker&255,marker>>8,0xc3,0xc1,0]+[0]*(length-8)
        marker={4:0x6010,5:0x7a10}.get(row,0x7810)
        phases=[[12,address>>8,address&255,length>>8,length&255]+payload(marker)]
        if row!=1: phases.append([13,address>>8,(address+(3 if row==6 else 0))&255])
        if row==7:
            phases.extend([[12,0x78,0,0,16]+payload(0x7820),[13,0x78,0]])
        sent=[e.value for e in events if e.cpu=='main' and e.kind=='OUT' and e.port=='00FD']
        def locate(seq,start):
            for j in range(start,len(sent)-len(seq)+1):
                if sent[j:j+len(seq)]==seq:return j+len(seq)
            raise ValueError('request')
        cursor=locate([0,0x17,0x0f],0)
        remaining=m[0xdf54]+256*m[0xdf55]
        for phase in phases:
            count=min(remaining,len(phase))
            if count: cursor=locate(phase[:count],cursor)
            remaining-=count
            if count<len(phase): break
        if remaining: raise ValueError('count')
        if counts[0] or counts[1]: locate([2,1,0,0,1],0)
    def stamp(i):
        out=[]
        for block in range((counts[i]+255)//256):
            v=[m.get(0xdf00+i*8+block*4+j) for j in range(4)]
            out.append(','.join(map(str,v[1:])) if counts[i]-block*256>=4 and v[0]==0xa1 and v[1] is not None and v[1]<40 and v[2] in (0,1) and v[3] is not None and 1<=v[3]<=16 else 'other')
        return ';'.join(out) or '-'
    low=[]; high=[]
    for line in lines:
        w=re.fullmatch(r'W ([0-9A-F]{4}) (rom|ram) ([0-9]+)',line)
        (high if w and int(w[1],16)>=0x7f00 else low).append(line)
    filtered,dropped=filter_lines(low,'G2','self')
    high_filtered,high_dropped=filter_lines(high,'G2','self')
    if dropped or high_dropped: raise ValueError('boundary')
    filtered += high_filtered[2:]
    groups={k:[] for k in ('rom','ram','high_rom','high_ram')}; cross=[]
    for line in filtered[2:]:
        parts=line.split()
        if parts[0]=='A': cross.append(parts[1]+':'+','.join(parts[2:]));continue
        a,b=(int(x,16) for x in parts[1].split('-')); source=parts[2]; count=int(parts[3])
        # 7F00 を跨ぐ集約区間は元の記録から個別に再集約する。
        if a<0x7f00<=b:
            raise ValueError('split')
        groups[('high_' if a>=0x7f00 else '')+source].append(f'{a:04X}-{b:04X}:{count}')
    values=[str(row),str(run),str(int(complete)),str(m[0xdf54]+256*m[0xdf55]) if complete else '-',str(m[0xdf52]) if complete else '-']+[';'.join(groups[k]) or '-' for k in ('rom','ram','high_rom','high_ram')]+[';'.join(cross) or '-']
    for i in (0,1):
        enabled=complete and (row in (3,7) if i==0 else row==7)
        values += [str(counts[i]) if enabled else '-',stamp(i) if enabled else '-']
    values += [str(sum(e.cpu=='sub' and e.kind=='OUT' and e.port=='00FD' for e in events)),str(drops)]
    if any(not re.fullmatch(p,v) for p,v in zip(PATTERNS,values)): raise ValueError('whitelist')
    return values

def main():
    p=argparse.ArgumentParser();p.add_argument('--row',type=int,choices=range(1,8),required=True);p.add_argument('--run',type=int,choices=(1,2),required=True)
    for n in ('iolog','memlog','boundary'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    try:
        drops=io_drops(a.iolog);events,masked=parse_iolog(a.iolog)
        if masked or not events or events[0].frame!=0:raise ValueError('iolog')
        vals=analyze(a.row,a.run,events,read_memlog(a.memlog),a.boundary.read_text().splitlines(),drops)
        out=io.StringIO(newline='');w=csv.writer(out,delimiter='\t',lineterminator='\n');w.writerow(FIELDS);w.writerow(vals);load([io.StringIO(out.getvalue())]);sys.stdout.write(out.getvalue())
    except (OSError,ValueError,IndexError,TypeError,AnalysisError):print('解析失敗',file=sys.stderr);return 2
    return 0
if __name__=='__main__':sys.exit(main())
