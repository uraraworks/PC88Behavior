#!/usr/bin/env python3
"""B85 観測窓と受信・終端スナップショットを自作プローブに追加する。"""
import sys
import b85_build_rom as b

original = b.boot
def boot(row, fault=False):
    text = original(row, fault)
    text = text.replace('    LD A,00Fh\n    CALL MAIN_SUB_SEND_REQUEST_CONT\n    JP C,_b85_timeout\n', '    LD A,00Fh\n    CALL MAIN_SUB_SEND_REQUEST_CONT\n    JP C,_b85_timeout\n    IN A,(040h)\n    IN A,(040h)\n')
    text = text.replace('    JP _b85_done\n_b85_timeout:', '''    JP _b85_observe
_b85_timeout:''')
    text = text.replace('_b85_done:\n', '''_b85_observe:
    LD B,020h
_b85_receive:
    PUSH BC
    CALL MAIN_SUB_RECV
    POP BC
    JP C,_b85_done
    LD A,(0DF51h)
    INC A
    LD (0DF51h),A
    DJNZ _b85_receive
    LD A,002h
    LD (0DF52h),A
_b85_done:
    IN A,(0FCh)
''')
    text = text.replace('    LD (0DF50h),A\n    LD (0DF52h),A', '    LD (0DF50h),A\n    LD (0DF51h),A\n    LD (0DF52h),A', 1)
    return text
b.boot = boot
b.main()
