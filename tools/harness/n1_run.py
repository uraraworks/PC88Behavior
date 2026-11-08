#!/usr/bin/env python3
"""事前登録n1の自作ROMを2走し、結果を記録する。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from ext1_run import find_core, parse_memlog, last_value, parse_intlog_main, parse_iolog_main
from make_n1_rom_test import build

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / 'tools/harness/frontend/q88measure'
WORK = ROOT / 'tmp/n1-work'


def run(variant, mode, tag):
    work = WORK / tag
    work.mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(WORK)
    build(work / 'rom', variant, variant in ('normal', 'changed', 'long'))
    cmd = [str(FRONT), '--core', find_core(), '--rom-dir', str(work / 'rom'),
           '--basic-mode', mode, '--frames', '35', '--out', str(work / 'report'),
           '--mem-write-log', str(work / 'mem'), '--mem-write-range', '0xC100-0xC122',
           '--mem-write-from-frame', '0', '--int-log', str(work / 'int'),
           '--io-log', str(work / 'io'), '--io-log-from-frame', '0']
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f'{tag}: q88measure終了コード {p.returncode}: {p.stderr[-1000:]}')
    ev = parse_memlog(work / 'mem')
    values = {f'{a:04X}': last_value(ev, f'{a:04X}') for a in
              [0xc100,0xc101,0xc102,*range(0xc110,0xc123)]}
    ints = parse_intlog_main(work / 'int')
    ram_ints = sum(0x9000 <= int(e[5],16) < 0xa000 and e[3] == '1' and int(e[6],16) == 0x38 for e in ints)
    io = parse_iolog_main(work / 'io')
    out31 = [e[5] for e in io if e[3] == 'OUT' and e[4] == '0031']
    if values['C122'] != '5A': raise RuntimeError(f'{tag}: 完了印なし')
    if out31 != ['A1','A5','A1']: raise RuntimeError(f'{tag}: ポート31出力不一致 {out31}')
    log = (work/'mem').read_text()
    if '取りこぼし: 0件' not in log: raise RuntimeError(f'{tag}: メモリログ欠落')
    return {'values': values, 'interrupts_total':len(ints), 'interrupts_ram_im1':ram_ints, 'out31':out31}


def standard_ok(r):
    v=r['values']
    return ([v[f'C{x:03X}'] for x in range(0x110,0x120)] ==
            ['11','11','11','11','44','44','22','22','22','22','22','11','44','44','11','11']
            and v['C120']=='00' and int(v['C121'],16)>=5 and r['interrupts_ram_im1']>=5)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--selftest',action='store_true'); a=ap.parse_args()
    WORK.mkdir(parents=True,exist_ok=True)
    if a.selftest:
        runs={v:run(v,'N88 V2','self_'+v) for v in ('normal','missing','changed')}
        assert standard_ok(runs['normal']), '正常対照不一致'
        assert not standard_ok(runs['missing']) and runs['missing']['values']['C116'] != '22', '欠落を検出できない'
        assert not standard_ok(runs['changed']) and runs['changed']['values']['C116'] == '33', 'パターン変更を検出できない'
        print('正常対照・欠落・識別値変更: OK')
        return
    arms=[('normal',m) for m in ('N88 V2','N88 V1H','N88 V1S','N')] + [(v,'N88 V2') for v in ('missing','short','long')]
    results={}
    for variant,mode in arms:
        key=variant+'_'+mode.replace(' ','_')
        r1=run(variant,mode,key+'_1'); r2=run(variant,mode,key+'_2')
        if r1 != r2: raise RuntimeError(f'{key}: 2走不一致')
        if variant == 'normal' and not standard_ok(r1): raise RuntimeError(f'{key}: 基準判定不一致 {r1}')
        results[key]={'run1':r1,'run2':r2,'equal':True}
        print(key, '2走一致', flush=True)
    dest=ROOT/'measurements/n1/results.json'; dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print('記録:',dest)

if __name__=='__main__': main()
