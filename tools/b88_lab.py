#!/usr/bin/env python3
"""B88 サブプローブの通信試験用 main ROM を組み立てる。"""
import argparse
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools' / 'asm'))
import z80text
from b88_arms import arms
from b88_probe import generate


def main_rom(arm, inject_fault=False):
    probe, _ = generate(arm)
    source = (ROOT / 'src/l3_main/main_sub_read.asm').read_text()
    primitives = source[source.index('MAIN_SUB_WAIT_SET:'):source.index('; PAIR陰性対照用。')]
    payload = bytes((12, 0x78, 0, len(probe) >> 8, len(probe) & 255)) + probe
    def table(name, values):
        return name + ':\n' + '\n'.join('    DB ' + ','.join(str(v) for v in values[i:i+24]) for i in range(0, len(values), 24)) + '\n'
    text = '''    ORG 0
    DI
    LD SP,0FFF0h
    XOR A
    CALL MAIN_SUB_SEND
    JP C,FAIL
    LD HL,PAYLOAD
    LD BC,PAYLOAD_END-PAYLOAD
    CALL SEND_RUN
    LD HL,EXECUTE
    LD BC,3
    CALL SEND_RUN
    {fault_command}
    LD HL,READ_REQUEST
    LD BC,5
    CALL SEND_RUN
    LD B,12
RECEIVE:
    PUSH BC
    CALL MAIN_SUB_RECV
    POP BC
    JP C,FAIL
    LD (09000h),A
    DJNZ RECEIVE
    LD A,1
    LD (09002h),A
STOP:
    JR STOP
FAIL:
    LD A,1
    LD (09003h),A
    JR STOP
SEND_RUN:
    LD A,(HL)
    PUSH BC
    CALL MAIN_SUB_SEND
    POP BC
    JP C,FAIL
    JR SEND_ADVANCE
SEND_NEXT:
    LD A,(HL)
    PUSH BC
    CALL MAIN_SUB_SEND_CONT
    POP BC
    JP C,FAIL
SEND_ADVANCE:
    INC HL
    DEC BC
    LD A,B
    OR C
    JR NZ,SEND_NEXT
    RET
MAIN_SUB_TIMEOUT_LIMIT EQU 65535
'''.replace('{fault_command}', 'LD HL,FAULT\n    LD BC,6\n    CALL SEND_RUN' if inject_fault else '') + primitives + table('PAYLOAD', payload) + 'PAYLOAD_END:\n' + table('FAULT', (12, 0x77, 4, 0, 1, 1)) + table('EXECUTE', (13, 0x78, 0)) + table('READ_REQUEST', (9, 0x77, 0, 0x77, 12))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'main.asm'
        path.write_text(text)
        data = z80text.Assembler().assemble(path)
    if len(data) > 0x8000:
        raise ValueError('main ROM の容量超過')
    return data + bytes(0x8000 - len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('arm', choices=[a['name'] for a in arms()])
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    arm = next(a for a in arms() if a['name'] == args.arm)
    (args.output / 'N88.ROM').write_bytes(main_rom(arm))

if __name__ == '__main__':
    main()
