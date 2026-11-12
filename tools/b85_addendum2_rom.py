#!/usr/bin/env python3
"""B85 追補2: 受信値を保存せず、観測上限まで読み続ける自作 main。"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import build_main_rom as builder

ARMS = [(0x7800,0x7801,1), (0x7800,0x7810,16), (0x7800,0x7900,256), (0x5000,0x5010,16), (0x7800,0x7800,16), (0x7810,0x7800,16)]
def pattern(n):
    return bytes((0x31 + 7*i) & 255 for i in range(n))
PATTERN = pattern(16)

def boot(row, control=None):
    address, end, size = ARMS[row-1]
    prefix = builder.b16_boot(1).split('    JP _b16_done')[0].replace('_b16_', '_b85a_')
    def send(seq):
        return ''.join(f'    LD A,0{v:02X}h\n    CALL {"MAIN_SUB_SEND" if i == 0 else "MAIN_SUB_SEND_REQUEST_CONT"}\n    JP C,_b85a_timeout\n' for i,v in enumerate(seq))
    setup = send([12, address >> 8, address & 255, size >> 8, size & 255]) + f"""    LD A,031h
    LD (0DF55h),A
    LD DE,0{size:04X}h
_b85a_pattern_loop:
    LD A,(0DF55h)
    PUSH DE
    CALL MAIN_SUB_SEND_REQUEST_CONT
    POP DE
    JP C,_b85a_timeout
    LD A,(0DF55h)
    ADD A,007h
    LD (0DF55h),A
    DEC DE
    LD A,D
    OR E
    JP NZ,_b85a_pattern_loop
"""
    request = send([9, address >> 8, address & 255, end >> 8, end & 255])
    if control == 'negative':
        setup, request = '', ''
    elif control == 'positive':
        setup = send([12,0x78,0,0,16,*PATTERN])
        request = send([0x15,0x78,0,0,16])
    receive = """    PUSH HL
    CALL MAIN_SUB_RECV
    POP HL
    JP C,_b85a_received_end
    INC HL
    LD A,H
    OR L
    JR NZ,_b85a_check_cap
    LD A,001h
    LD (0DF54h),A
    JP _b85a_receive
_b85a_check_cap:
    LD A,(0DF54h)
    OR A
    JP Z,_b85a_receive
    LD A,004h
    LD (0DF52h),A
    JP _b85a_done
_b85a_received_end:
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
''' + request + '''    XOR A
    LD (0DF54h),A
    LD HL,0000h
    LD A,002h
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
