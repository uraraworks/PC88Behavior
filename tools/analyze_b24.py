#!/usr/bin/env python3
"""B24 のメモリ書き込みを入力から一度だけ読み、比較結果のみ出力する。"""
import argparse,csv,io,json,re,sys
from analyze_m6ia_main_sub import MEM_RE
from judge_b24 import FIELDS, load
from make_l3_testdisk import coord_header_pattern

LENGTHS=(16,1,16,256,256,512,0,16)
def analyze(row,run,lines,pc_range=(0,0xffff)):
    length=LENGTHS[row-1]; data=[]; state={}; seq=0; drops=None; receiving=False; finished=False; active=False
    for line in lines:
        m=MEM_RE.match(line)
        if m:
            n,_,pc,addr,value=m.groups(); seq+=1
            if int(n)!=seq: raise ValueError('sequence')
            a=int(addr,16); v=int(value,16)
            if not pc_range[0] <= int(pc,16) < pc_range[1]: continue
            if finished: continue
            if a==0xde04 and v==0x5a: active=True
            if not active: continue
            if a in (0xde00,0xde01):
                state[a]=v
                if a==0xde01 and v==1: receiving=False; finished=True
            elif a==0xde03 and v==0xa5: receiving=True
            elif receiving and 0xe000<=a<0xe000+length+8:
                if a!=0xe000+len(data): raise ValueError('address')
                data.append(v)
        m=re.search(r'取りこぼし:\s*(\d+)件',line)
        if m: drops=int(m[1])
    if drops!=0: raise ValueError('drops')
    complete=state.get(0xde01)==1
    if complete and state.get(0xde00) not in (0,1): raise ValueError('state')
    def expected(i):
        if row in (5,6):
            return coord_header_pattern(0xa1,0,0,i//256+1)[i%256]
        return ((i+(8 if row==3 else 0))*7+13)&255
    prefix=0
    for i,v in enumerate(data[:length]):
        if v!=expected(i): break
        prefix+=1
    extra=';'.join('1' if v==expected(i) else '0' for i,v in enumerate(data[length:],length)) or '-'
    stamps=[]
    if row in (5,6):
        for start in range(0,min(len(data),length),256):
            block=data[start:start+4]
            if len(block)==4 and block[0]==0xa1 and block[1]<40 and block[2] in (0,1) and 1<=block[3]<=16:
                stamps.append(','.join(map(str,block[1:])))
            else: stamps.append('other')
    return [str(row),str(run),str(int(complete)),str(len(data)),str(state.get(0xde00,0)) if complete else '-',str(prefix),extra,';'.join(stamps) or '-']
def main():
    p=argparse.ArgumentParser();p.add_argument('--row',type=int,choices=range(1,9),required=True);p.add_argument('--run',type=int,choices=(1,2),required=True);p.add_argument('--memlog',required=True);p.add_argument('--labels',required=True);a=p.parse_args()
    try:
        with open(a.labels,encoding='utf-8') as f: labels=json.load(f)['labels']
        with open(a.memlog,encoding='utf-8') as f: values=analyze(a.row,a.run,f,(labels['_b24_begin'],labels['_b24_end']))
        out=io.StringIO(newline='');w=csv.writer(out,delimiter='\t',lineterminator='\n');w.writerow(FIELDS);w.writerow(values);load([io.StringIO(out.getvalue())]);sys.stdout.write(out.getvalue())
    except (ValueError,OSError,IndexError,KeyError): print('解析失敗',file=sys.stderr);return 2
    return 0
if __name__=='__main__':sys.exit(main())
