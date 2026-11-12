#!/usr/bin/env python3
"""B86 の C000 起動セクタ方式を、自己完結する B88 二段ローダへ拡張。"""
import json
from pathlib import Path
import sys
import tempfile
from b88a2_probe import generate, word
from make_l3_testdisk import build_d88

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools/asm'))
import z80text


def assemble(source):
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / 'b88.asm'
        path.write_text(source)
        asm = z80text.Assembler()
        data = asm.assemble(path)
    return bytes(data[min(addr for addr, *_ in asm.listing):]), asm.labels


def table(name, values):
    return name + ':\n' + '\n'.join(' DB ' + ','.join(str(v) for v in values[i:i+24])
                                    for i in range(0, len(values), 24)) + '\n'


def generate_boot(arm, fault=None):
    probe, labels = generate(arm)
    # 自己検査専用。公式測定の run.sh からは指定しない。
    faults = {
        'restart': 'c3 00 78', 'hang': '18 fe',
        'same_write': '77 c9', 'restore': '34 35 c9',
        # SPECIFY と2引数。MSRを待ち、引数をコマンドとして数えないことを検査。
        'io': 'f5 3e 03 d3 fb db fa e6 80 28 fa 3e 5a d3 fb db fa e6 80 28 fa 3e 01 d3 fb f1 c9',
    }
    if fault in faults or isinstance(fault, bytes):
        patched = bytearray(probe)
        target = 0x7800 + len(patched)
        offset = labels['negative'] - 0x7800
        patched[offset:offset+3] = b'\xc3' + word(target)
        patched.extend(fault if isinstance(fault, bytes) else bytes.fromhex(faults[fault]))
        probe = bytes(patched)
    if 'kind' in arm and fault == 'prehang':
        patched = bytearray(probe)
        offset = labels['prepare'] - 0x7800
        patched[offset:offset+2] = bytes.fromhex('18 fe')
        probe = bytes(patched)
    if isinstance(fault, str) and fault.startswith('prehang-'):
        patched = bytearray(probe)
        offset = labels['step_' + fault.split('-')[1]] - 0x7800
        patched[offset:offset+2] = bytes.fromhex('18 fe')
        probe = bytes(patched)
    # 通信待ちはホスト側のフレーム数・実時間上限で制限する。
    # 最初の256バイトに通信プリミティブと後続2セクタのローダを置く。
    loader = ''' ORG 0C000h
 DI
 LD SP,0F000h
BOOT:
 LD (0CFF0h),A
 XOR A
 CALL SEND
 LD HL,READ_DISK
 LD B,5
 CALL RUN
 LD A,6
 CALL SEND
 CALL RECV
 CP 0C0h
 JP NZ,FAIL
 LD A,012h
 CALL SEND
 LD HL,0C100h
 LD B,0
LOAD:
 CALL PAIR
 DJNZ LOAD
 JP 0C100h
FAIL:
 LD (0CFF2h),A
 DI
 HALT
 JR FAIL
RUN:
 LD A,00Fh
 OUT (0FFh),A
RUN_NEXT:
 LD A,(HL)
 CALL CONT
 INC HL
 DJNZ RUN_NEXT
 RET
SEND:
 PUSH AF
 LD A,00Fh
 OUT (0FFh),A
 POP AF
CONT:
 PUSH AF
WAIT_SEND:
 IN A,(0FEh)
 AND 2
 JR Z,WAIT_SEND
 LD A,00Eh
 OUT (0FFh),A
 POP AF
 OUT (0FDh),A
 LD A,9
 OUT (0FFh),A
WAIT_ACK:
 IN A,(0FEh)
 AND 4
 JR Z,WAIT_ACK
 LD A,8
 OUT (0FFh),A
 IN A,(0FEh)
 RET
RECV:
 CALL RECV_FIRST
 PUSH AF
 CALL RECV_LAST
 POP AF
 RET
RECV_FIRST:
 LD A,00Bh
 OUT (0FFh),A
WAIT_DATA:
 IN A,(0FEh)
 AND 1
 JR Z,WAIT_DATA
 LD A,00Ah
 OUT (0FFh),A
 IN A,(0FCh)
 RET
RECV_LAST:
 LD A,00Dh
 OUT (0FFh),A
WAIT_CLEAR:
 IN A,(0FEh)
 AND 1
 JR NZ,WAIT_CLEAR
 RET
PAIR:
 CALL RECV_FIRST
 LD (HL),A
 INC HL
 CALL RECV_LAST
 IN A,(0FCh)
 LD (HL),A
 INC HL
 LD A,00Ch
 OUT (0FFh),A
 RET
READ_DISK:
 DB 2,2,0,0,2
'''
    # 単発 RECV も最後の 0C を必ず送る（PAIR は2位置目の後）。
    loader = loader.replace(' CALL RECV_LAST\n POP AF',
                            ' CALL RECV_LAST\n LD A,00Ch\n OUT (0FFh),A\n POP AF')
    boot, boot_labels = assemble(loader)
    if len(boot) > 256:
        raise ValueError('起動セクタ容量超過')
    constants = ''.join(f'{k} EQU {v}\n' for k, v in boot_labels.items())
    payload = bytes((12, 0x78, 0, len(probe) >> 8, len(probe) & 255)) + probe
    assert len(payload) <= 255
    cooperate = ''
    helpers = ''
    if arm.get('kind') in ('recv', 'send'):
        # CFFE/CFFF は器具専用同期印。入口到達／帰還境界のフックだけが立てる。
        cooperate = '''
WAIT_ENTRY:
 LD A,(0CFFEh)
 OR A
 JR Z,WAIT_ENTRY
'''
        if arm['kind'] == 'recv':
            cooperate += ''.join(f" LD A,{v}\n CALL COOPERATE_SEND\n" for v in arm.get('sent', (0x35,)))
            helpers = '''
COOPERATE_SEND:
 PUSH AF
COOP_SEND_WAIT:
 LD A,(0CFFFh)
 OR A
 JR NZ,COOP_SEND_SKIP
 IN A,(0FEh)
 AND 2
 JR Z,COOP_SEND_WAIT
 LD A,00Eh
 OUT (0FFh),A
 POP AF
 OUT (0FDh),A
 LD A,9
 OUT (0FFh),A
COOP_SEND_ACK:
 IN A,(0FEh)
 AND 4
 JR NZ,COOP_SENT
 LD A,(0CFFFh)
 OR A
 JR Z,COOP_SEND_ACK
 JR COOP_SEND_CLEAR
COOP_SEND_SKIP:
 POP AF
 RET
COOP_SENT:
 NOP
COOP_SEND_CLEAR:
 LD A,8
 OUT (0FFh),A
 IN A,(0FEh)
 RET
'''
        else:
            cooperate += ' CALL COOPERATE\n'
            helpers = '''
COOPERATE:
 LD A,00Bh
 OUT (0FFh),A
COOP_WAIT:
 IN A,(0FEh)
 AND 1
 JR NZ,COOP_DATA
 LD A,(0CFFFh)
 OR A
 JR Z,COOP_WAIT
 LD A,00Ah
 OUT (0FFh),A
 RET
COOP_DATA:
 LD A,00Ah
 OUT (0FFh),A
 IN A,(0FCh)
COOP_BYTE:
 LD (0CF20h),A
 CALL RECV_LAST
 LD A,00Ch
 OUT (0FFh),A
 JR COOPERATE
'''
    stage = constants + ''' ORG 0C100h
 {sync}
 LD HL,PAYLOAD
 LD B,PAYLOAD_END-PAYLOAD
 CALL RUN
 LD HL,EXECUTE
 LD B,3
 CALL RUN
 {cooperate}
 {fault}
 LD HL,READ_RESULT
 LD B,5
 CALL RUN
 LD HL,0CF00h
 LD B,12
RECEIVE_RESULT:
 CALL RECV
 LD (HL),A
 INC HL
 DJNZ RECEIVE_RESULT
DONE:
 LD (0CFF1h),A
 DI
 HALT
STOP:
 JR STOP
'''.replace('{fault}', 'LD HL,FAULT\n LD B,6\n CALL RUN' if fault == 'result' else '').replace(
        '{cooperate}', cooperate).replace('{sync}',
        'XOR A\n LD (0CFFEh),A\n LD (0CFFFh),A' if 'kind' in arm else '')
    stage += helpers
    stage += table('PAYLOAD', payload) + 'PAYLOAD_END:\n'
    stage += table('EXECUTE', (13, 0x78, 0))
    stage += table('READ_RESULT', (9, 0x77, 0, 0x77, 12))
    stage += table('FAULT', (12, 0x77, 4, 0, 1, 1))
    body, stage_labels = assemble(stage)
    if len(body) > 512:
        raise ValueError('後続セクタ容量超過')
    image = boot.ljust(256, b'\0') + body.ljust(512, b'\0')
    disk = bytearray(build_d88(sectors_per_track=16, n_cylinders=1, heads=2))
    offset = int.from_bytes(disk[0x20:0x24], 'little')
    for i in range(3):
        disk[offset+16:offset+272] = image[i*256:(i+1)*256]
        offset += 272
    return image, bytes(disk), {'main': {**boot_labels, **stage_labels}, 'sub': labels}


def own_main(sector):
    # B86 と同じ自作 IPL。初段だけを C000 へ置く。後続は実際に FDC で読む。
    rom = bytearray(0x8000)
    boot = bytes.fromhex('f3 31 00 f0 21 00 03 11 00 c0 01 00 01 ed b0 c3 00 c0')
    rom[:len(boot)] = boot
    rom[0x300:0x400] = sector[:256]
    return bytes(rom)


def write_arm(directory, arm, fault=None):
    data, disk, labels = generate_boot(arm, fault)
    (directory / 'probe.bin').write_bytes(data)
    (directory / 'probe.d88').write_bytes(disk)
    (directory / 'media.d88').write_bytes(build_d88(sectors_per_track=16, n_cylinders=1, heads=2, density=0x40, content_rule='coord-header', disk_id=0x42))
    (directory / 'labels.json').write_text(json.dumps(labels) + '\n')
    return data, labels
