#!/usr/bin/env python3
"""KILL/NAME本体を合成セクタRAMに接続したZ80試験ROMを作る。"""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import memmap
sys.path.insert(0, str(ROOT / 'tools/asm'))
import z80text

ARMS = ('K-1', 'K-2', 'K-3', 'K-4', 'N-1', 'N-2', 'N-3', 'N-4', 'N-5', 'N-6',
        'chain', 'late', 'unused', 'deleted', 'drive1', 'upper', 'boundary', 'same', 'short')


def scenario(arm):
    # 16セクタ全部を比較する。配置済み以外の欄や160以降も固有値を持つ。
    image = bytearray(b'\xff' * 4096)
    image[12*256:13*256] = bytes(256)
    fat = bytearray(b'\xff' * 160)
    fat[74] = fat[75] = 0xa0
    fat[10], fat[20], fat[21], fat[30] = 0xc1, 21, 0xc3, 0xc0
    entries = [(b'qsa', 10), (b'qsb', 20), (b'QSU', 30)]
    for i, (name, unit) in enumerate(entries):
        # 9〜15は非一様。NAMEの10/11バイト目の破壊も捕捉する。
        image[i*16:i*16+16] = name.ljust(9, b' ') + bytes([0x80, unit, 0x13, 0x57, 0x9b, 0xdf, 0x42])
    command = {'K-1': 'kill "2:qsb"', 'K-2': 'kill "2:qsc"', 'K-3': 'kill "2:qsa"',
               'K-4': 'kill "2:qsu"', 'N-1': 'name "2:qsa" as "2:qsd"',
               'N-2': 'name "2:qsa" as "2:qsb"', 'N-3': 'name "2:qsc" as "2:qsd"',
               'N-4': 'name "2:qsa" as "2:qsd"', 'N-5': 'name "2:qsa" as "qsd"',
               'N-6': 'name "2:qsu" as "2:qsd"'}.get(arm, 'kill "2:qsb"')
    slot, chain, new = 1, [20, 21], b'qsd'
    error = {'K-2':53,'K-3':61,'K-4':53,'N-2':65,'N-3':53,'N-5':73,'N-6':53,
             'unused':53,'same':65}.get(arm, 0)
    drive = 1
    if arm in ('K-3', 'N-4'):
        image[12*256:13*256] = b'\x10' * 256
    if arm == 'chain':
        chain = [7,159,0]
        image[26] = 7
        fat[7], fat[159], fat[0] = 159,0,0xc0
        fat[20], fat[21] = 0xff,0xff
    if arm == 'late':
        target = bytes(image[16:32]); image[:12*256] = bytes(12*256)
        slot = 191
        image[slot*16:slot*16+16] = target
    if arm == 'unused':
        image[:16] = b'\xff' * 16
    if arm == 'deleted':
        image[0] = 0
    if arm == 'drive1':
        command = 'kill "1:qsb"'; drive = 0
    if arm == 'upper':
        command = 'NAME "2:QSU" AS "2:NEW"'; slot = 2; new = b'NEW'
    if arm == 'same':
        command = 'name "2:qsa" as "2:qsa"'
    if arm == 'short':
        command = 'name "2:qsa" as "2:x"'; slot = 0; new = b'x'
    if arm == 'boundary':
        command = 'killer "2:qsb"'
    for r in (14,15,16):
        off = (r-1)*256
        image[off:off+160] = fat
        image[off+160:off+256] = bytes((r*11+i)%256 for i in range(96))
    expect = image.copy()
    is_name = command[:4].lower() == 'name'
    if arm in ('N-1','N-4'):
        slot = 0
    if not error and arm != 'boundary':
        if is_name:
            expect[slot*16:slot*16+9] = new.ljust(9, b' ')
        else:
            expect[slot*16] = 0
            for r in (14,15,16):
                for unit in chain:
                    expect[(r-1)*256+unit] = 255
    writes = 0 if error or arm == 'boundary' else (1 if is_name else 4)
    return image, expect, command, error, writes, drive, is_name


def make_rom(out, arm, fault):
    image, expected, command, error, writes, drive, is_name = scenario(arm)
    bank = (ROOT/'src/ext_bank/bank2.asm').read_text(encoding='utf-8')
    substitutions = {
        's2_read:\n    LD A,(S2_DRIVE)\n    LD IX,BANK2_READ_CHR_ADDR\n    JP BANK2_MAIN_CALL_ADDR': 's2_read:\n    JP T_READ',
        's2_write:\n    JP s2_write_stream': 's2_write:\n    JP T_WRITE',
    }
    for name, addr in (('skip','SKIP_SPACES'), ('peek','PEEK_CHAR'), ('adv','ADV_PTR'), ('end','AT_END')):
        substitutions[f's2_{name}:\n    LD IX,BANK2_{addr}_ADDR\n    JP BANK2_MAIN_CALL_ADDR'] = f's2_{name}:\n    JP T_{name.upper()}'
    if fault == 'release':
        substitutions['    CALL s2_release_chain\n    ; ERR53/61'] = '    NOP\n    ; ERR53/61'
    if fault == 'tail':
        substitutions['k2_write_old:\n'] = 'k2_write_old:\n    LD A,0\n    LD (S2_BUF+11),A\n'
    if fault == 'protect':
        substitutions['k2_name:\n'] = 'k2_name:\n    JP s2_protected\n'
    for old, new in substitutions.items():
        if bank.count(old) != 1:
            raise ValueError('置換点不一致')
        bank = bank.replace(old, new)
    matcher = 0 if arm == 'boundary' else (12 if is_name else 11)
    entry = 'EXT_BANK2_NAME_ENTRY' if is_name else 'EXT_BANK2_KILL_ENTRY'
    invocation = '' if arm == 'boundary' else f'    CALL {entry}\n'
    protected_reads = 0 if is_name or arm == 'boundary' else 1
    harness = f'''
    ORG 0
    JP T_START
    ORG 0100h
T_PASS EQU 0E304h
T_FAIL EQU 0E303h
T_WRITES EQU 0E301h
T_PROTECT_READS EQU 0E302h
T_START:
    LD SP,0F000h
    XOR A
    LD (T_PASS),A
    LD (T_FAIL),A
    LD (T_WRITES),A
    LD (T_PROTECT_READS),A
    LD (S2_ERROR_FLAG),A
    LD (S2_DONE),A
    LD HL,T_COMMAND
    LD (K2_CUR_PTR),HL
    LD HL,T_COMMAND_END
    LD (K2_LINE_END),HL
    LD HL,T_BEFORE
    LD DE,09000h
    LD BC,4096
    LDIR
    CALL EXT_BANK2_DISK_MATCH
    CP {matcher}
    JP NZ,T_BAD1
{invocation}    LD A,(S2_ERROR_FLAG)
    CP {int(error != 0)}
    JP NZ,T_BAD2
'''
    if error:
        harness += f'    LD A,(S2_ERROR_KIND)\n    CP {error}\n    JP NZ,T_BAD3\n'
    harness += f'''
    LD A,(S2_DONE)
    CP {int(not error and arm != 'boundary')}
    JP NZ,T_BAD4
    LD A,(T_WRITES)
    CP {writes}
    JP NZ,T_BAD5
    LD A,(T_PROTECT_READS)
    CP {protected_reads}
    JP NZ,T_BAD6
    LD HL,09000h
    LD DE,T_EXPECTED
    LD BC,4096
T_COMPARE:
    LD A,(DE)
    CP (HL)
    JP NZ,T_BAD7
    INC HL
    INC DE
    DEC BC
    LD A,B
    OR C
    JR NZ,T_COMPARE
    LD A,1
    LD (T_PASS),A
T_HALT:
    JR T_HALT
T_READ:
    LD A,(S2_DRIVE)
    CALL T_ADDRESS
    RET C
    LD HL,09000h
    ADD HL,BC
    LD DE,S2_BUF
    LD BC,256
    LDIR
    OR A
    RET
T_WRITE:
    PUSH HL
    CALL T_ADDRESS
    POP HL
    RET C
    LD DE,09000h
    EX DE,HL
    ADD HL,BC
    EX DE,HL
    LD BC,256
    LDIR
    LD A,(T_WRITES)
    INC A
    LD (T_WRITES),A
    OR A
    RET
T_ADDRESS:
    CP {drive}
    JR NZ,T_IO_BAD
    LD A,D
    CP 37
    JR NZ,T_IO_BAD
    LD A,E
    CP 1
    JR C,T_IO_BAD
    CP 17
    JR NC,T_IO_BAD
    CP 13
    JR NZ,T_NOT_PROTECT
    LD A,(T_PROTECT_READS)
    INC A
    LD (T_PROTECT_READS),A
T_NOT_PROTECT:
    LD A,E
    DEC A
    LD B,A
    LD C,0
    OR A
    RET
T_IO_BAD:
    LD A,8
    LD (T_FAIL),A
    SCF
    RET
T_SKIP:
    CALL T_PEEK
    CP ' '
    RET NZ
    CALL T_ADV
    JR T_SKIP
T_PEEK:
    LD HL,(K2_CUR_PTR)
    LD DE,(K2_LINE_END)
    OR A
    SBC HL,DE
    LD A,0
    RET Z
    LD HL,(K2_CUR_PTR)
    LD A,(HL)
    RET
T_ADV:
    LD HL,(K2_CUR_PTR)
    INC HL
    LD (K2_CUR_PTR),HL
    RET
T_END:
    LD HL,(K2_CUR_PTR)
    LD DE,(K2_LINE_END)
    OR A
    SBC HL,DE
    RET
T_BAD1: LD A,1
    JR T_BAD
T_BAD2: LD A,2
    JR T_BAD
T_BAD3: LD A,3
    JR T_BAD
T_BAD4: LD A,4
    JR T_BAD
T_BAD5: LD A,5
    JR T_BAD
T_BAD6: LD A,6
    JR T_BAD
T_BAD7: LD A,7
T_BAD:
    LD (T_FAIL),A
    JP T_HALT
    ORG 01800h
T_COMMAND:
    DB {','.join(str(x) for x in command.encode('ascii'))}
T_COMMAND_END:
    ORG 02000h
T_BEFORE:
'''
    def data(values):
        return ''.join('    DB '+','.join(str(x) for x in values[i:i+32])+'\n' for i in range(0,len(values),32))
    program=(ROOT/'src/l4_basic/program.asm').read_text(encoding='utf-8')
    direct=program[program.index('_bhl_direct:\n'):].split('\n; ---------------------------------------------------------------------',1)[0]
    if fault == 'prompt':
        direct=direct.replace('    XOR A\n    LD (SAVE_DONE_FLAG),A', '    LD A,1')
    harness=harness.replace('    LD A,1\n    LD (T_PASS),A', '    CALL _bhl_direct\n    OR A\n    JP NZ,T_BAD4\n    LD A,1\n    LD (T_PASS),A')
    harness=harness.replace('    ORG 01800h', 'SAVE_DONE_FLAG EQU 0E24Bh\n; 直接モードの入口が呼ぶ数値の入力時検査(バンク3)は、ここでは「問題なし(CF=0)」で返す。\nEXT_BANK_CALL:\n    OR A\n    RET\nBASIC_RUN_DIRECT:\n    RET\n'+direct+'\n    ORG 01800h')
    source = harness + data(image) + '    ORG 04000h\nT_EXPECTED:\n' + data(expected) + bank
    out.mkdir()
    asm = out/'killname_test.asm'
    asm.write_text(memmap.asm_prelude() + source,encoding='utf-8')
    code = z80text.Assembler().assemble(asm)
    if len(code)>0x8000:
        raise ValueError('試験ROM超過')
    rom = bytearray(0x8000); rom[:len(code)] = code
    (out/'N88.ROM').write_bytes(rom)
    sub = bytearray(0x800); sub[:2] = bytes((0x18,0xfe))
    (out/'DISK.ROM').write_bytes(sub)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('out',type=Path); ap.add_argument('arm',choices=ARMS)
    ap.add_argument('fault',choices=('normal','release','tail','protect','prompt'))
    args = ap.parse_args()
    make_rom(args.out,args.arm,args.fault)
