#!/usr/bin/env python3
"""生データを残さず B52 の読み返しを比較する。"""
import argparse,csv,json,re,sys
from analyze_m6ia_main_sub import MEM_RE
from judge_b52 import FIELDS
LENGTHS=(8,2,16,8,9,0,8,8)
def analyze(row,run,lines,pc_range=(0,0xffff)):
    data=[];state={};seq=0;drops=None;active=False;receiving=False
    for line in lines:
        m=MEM_RE.match(line)
        if m:
            n,_,pc,addr,value=m.groups();seq+=1
            if int(n)!=seq: raise ValueError('sequence')
            if not pc_range[0] <= int(pc,16) < pc_range[1]: continue
            a=int(addr,16);v=int(value,16)
            if a==0xde04 and v==0x5a: active=True
            if not active: continue
            if a in (0xde00,0xde01): state[a]=v
            elif a==0xde03 and v==0xa5: receiving=True
            elif receiving and 0xe000<=a<0xe040:
                if a!=0xe000+len(data): raise ValueError('address')
                data.append(v)
        m=re.search(r'取りこぼし:\s*(\d+)件',line)
        if m: drops=int(m[1])
    if drops!=0: raise ValueError('drops')
    length=LENGTHS[row-1]; start=0x20 if row==4 else 0x10
    payload=bytes([0x3e,0x5a,0x32,0x3f,0x78,0xc3,0xc1,0]) if row==7 else bytes(0xa0+i for i in range(length))
    def base(i): return (i*7+13)&255
    written=sum(data[i]==payload[i-start] for i in range(start,min(start+length,len(data))))
    before=sum(data[i]!=base(i) for i in range(min(start,len(data))))
    after=sum(data[i]!=base(i) for i in range(start+length,len(data)) if not (row==7 and i==63))
    match='-' if len(data)<64 else str(int(written==length and before==0 and after==0))
    executed='-' if row!=7 or len(data)<64 else str(int(data[63]==0x5a))
    return [str(row),str(run),str(int(state.get(0xde01)==1)),str(state.get(0xde00,'-')),str(len(data)),str(written),str(before),str(after),match,executed]
def main():
    p=argparse.ArgumentParser();p.add_argument('--row',type=int,choices=range(1,9),required=True);p.add_argument('--run',type=int,choices=(1,2),required=True);p.add_argument('--memlog',required=True);p.add_argument('--labels',required=True);a=p.parse_args()
    try:
        with open(a.labels) as f: labels=json.load(f)['labels']
        with open(a.memlog) as f: r=analyze(a.row,a.run,f,(labels['_b52_begin'],labels['_b52_end']))
        w=csv.writer(sys.stdout,delimiter='\t',lineterminator='\n');w.writerow(FIELDS);w.writerow(r)
    except (ValueError,OSError,KeyError): print('解析失敗',file=sys.stderr);return 2
    return 0
if __name__=='__main__': raise SystemExit(main())
