#!/usr/bin/env python3
"""自作コードが保存したレジスタ値だけを TSV にする。"""
import argparse, csv, io, json, re, sys
from analyze_m6ia_main_sub import MEM_RE
from judge_b35 import FIELDS, load

REGS = (('a', 1), ('bc', 2), ('de', 2), ('hl', 2), ('ix', 2), ('iy', 2), ('sp', 2), ('i', 1))

def analyze(row, run, lines, pc_range=(0, 0x10000)):
    data = []; active = False; done = False; status = None; drops = None; seq = 0
    for line in lines:
        m = MEM_RE.match(line)
        if m:
            n, _, pc, addr, value = m.groups(); seq += 1
            if int(n) != seq: raise ValueError('sequence')
            pc, addr, value = int(pc, 16), int(addr, 16), int(value, 16)
            if not pc_range[0] <= pc < pc_range[1] or done: continue
            if addr == 0xde04 and value == 0x5a: active = True
            if not active: continue
            if addr == 0xde00: status = value
            elif addr == 0xde01 and value == 1: done = True
            elif 0xe000 <= addr < 0xe010:
                if addr != 0xe000 + len(data): raise ValueError('address')
                data.append(value)
        m = re.search(r'取りこぼし:\s*(\d+)件', line)
        if m: drops = int(m[1])
    if drops != 0: raise ValueError('drops')
    complete = done and status == 0 and len(data) == 16 and data[14:] == [0x5a, 0xa5]
    values=[]; pos=0
    for _, size in REGS:
        values.append(f'{int.from_bytes(bytes(data[pos:pos+size]), "little"):0{size*2}X}' if complete else '-')
        pos += size
    return [str(row), str(run), str(int(complete)), *values]

def main():
    p=argparse.ArgumentParser(); p.add_argument('--row',type=int,choices=range(1,7),required=True); p.add_argument('--run',type=int,choices=(1,2),required=True); p.add_argument('--memlog',required=True); p.add_argument('--labels',required=True); a=p.parse_args()
    try:
        with open(a.labels,encoding='utf-8') as f: labels=json.load(f)['labels']
        with open(a.memlog,encoding='utf-8') as f: values=analyze(a.row,a.run,f,(labels['_b35_begin'],labels['_b35_end']))
        out=io.StringIO(newline=''); w=csv.writer(out,delimiter='\t',lineterminator='\n'); w.writerow(FIELDS); w.writerow(values); load([io.StringIO(out.getvalue())]); sys.stdout.write(out.getvalue())
    except (OSError,ValueError,KeyError,IndexError): print('解析失敗',file=sys.stderr); return 2
    return 0
if __name__=='__main__': sys.exit(main())
