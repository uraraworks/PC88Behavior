#!/usr/bin/env python3
"""B85 追補1: 受信値を保存せず、観測上限まで読み続ける自作 main。"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import build_main_rom as builder

LENGTHS = (1, 2, 3, 16, 255, 256, 257, 0x1000, 0)
# 末尾3腕は ROM 側、境界、RAM 側。境界腕は ROM を含む。
ARMS = [(0x7800, n, True) for n in LENGTHS] + [(0x5000,16,True), (0x7ff0,16,True), (0x0000,16,False), (0x3ff8,16,False), (0x4000,16,True), (0x7800,0x20,True)]
PATTERN = bytes((0x31 + 7*i) & 255 for i in range(16))

def boot(row, control=None):
    address, length, pattern = ARMS[row-1]
    prefix = builder.b16_boot(1).split('    JP _b16_done')[0].replace('_b16_', '_b85a_')
    def send(seq):
        return ''.join(f'    LD A,0{v:02X}h\n    CALL {"MAIN_SUB_SEND" if i == 0 else "MAIN_SUB_SEND_REQUEST_CONT"}\n    JP C,_b85a_timeout\n' for i,v in enumerate(seq))
    setup = send([12, address >> 8, address & 255, 0, 16, *PATTERN]) if pattern else ''
    request = send([9, address >> 8, address & 255, length >> 8, length & 255])
    if control == 'negative':
        setup, request = '', ''
    elif control == 'positive':
        setup = send([12,0x78,0,0,16,*PATTERN])
        request = send([0x15,0x78,0,0,16])
    receive = """    CALL MAIN_SUB_RECV
    JP NC,_b85a_receive
"""
    if control == 'negative':
        receive = ''
    elif control == 'positive':
        receive = """    LD B,008h
_b85a_pair:
    LD A,00Bh
    OUT (0FFh),A
    LD C,001h
    CALL MAIN_SUB_WAIT_SET
    JP C,_b85a_timeout
    LD A,00Ah
    OUT (0FFh),A
    IN A,(0FCh)
    LD A,00Dh
    OUT (0FFh),A
    LD C,001h
    CALL MAIN_SUB_WAIT_CLEAR
    JP C,_b85a_timeout
    IN A,(0FCh)
    LD A,00Ch
    OUT (0FFh),A
    DJNZ _b85a_pair
"""
    return prefix + setup + '''    IN A,(040h)
    IN A,(040h)
''' + request + '''    LD A,002h
    LD (0DF52h),A
_b85a_receive:
''' + receive + '''    LD A,003h
    LD (0DF52h),A
    JP _b85a_done
_b85a_timeout:
    LD A,001h
    LD (0DF52h),A
_b85a_done:
    LD A,001h
    LD (0DF53h),A
    RET
'''

def main():
    p=argparse.ArgumentParser(); p.add_argument('outdir'); p.add_argument('--row', type=int, choices=range(1,len(ARMS)+1), required=True); p.add_argument('--control', choices=('negative','positive')); a=p.parse_args()
    text=boot(a.row,a.control); builder.b16_boot=lambda _: text
    sys.argv=[sys.argv[0],a.outdir,'--inject-b16-row','1']; builder.main()
if __name__=='__main__': main()
