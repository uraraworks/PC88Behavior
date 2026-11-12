#!/usr/bin/env python3
"""B85 自作 main ROM。既存ビルダの B16 差し替え口を使用する。"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import build_main_rom as builder

ROWS = ((), (9,0,0,0,0), (9,1,0,0,0), (9,0,1,0,0),
        (9,0,0,1,0), (9,0,0,0,1), (9,), (9,0,0),
        (12,0x78,0,0,1,0x55))

def boot(row, fault=False):
    prefix = builder.b16_boot(1).split('    JP _b16_done')[0].replace('_b16_', '_b85_')
    seq = list(ROWS[row-1])
    if fault and seq:
        seq[-1] ^= 1
    send = ''
    for i, value in enumerate(seq):
        routine = 'MAIN_SUB_SEND' if i == 0 else 'MAIN_SUB_SEND_REQUEST_CONT'
        send += f'    LD A,0{value:02X}h\n    CALL {routine}\n    JP C,_b85_timeout\n    LD A,(0DF50h)\n    INC A\n    LD (0DF50h),A\n'
    return prefix + send + '''    JP _b85_done
_b85_timeout:
    LD A,001h
    LD (0DF52h),A
_b85_done:
    LD A,001h
    LD (0DF53h),A
    RET
'''

def main():
    p = argparse.ArgumentParser()
    p.add_argument('outdir'); p.add_argument('--row', type=int, choices=range(1,10), required=True)
    p.add_argument('--fault', action='store_true')
    a = p.parse_args()
    original = builder.b16_boot
    text = boot(a.row, a.fault)
    builder.b16_boot = lambda _: text
    sys.argv = [sys.argv[0], a.outdir, '--inject-b16-row', '1']
    builder.main()
    builder.b16_boot = original

if __name__ == '__main__': main()
