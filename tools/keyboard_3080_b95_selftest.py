#!/usr/bin/env python3
"""自作ROMの3080を直接呼び、修飾・同時押し・未定義キーを検査する。"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import main_rom_entry_selftest as h

SOURCE = '''    ORG 0xC100
    DI
    LD SP,0xE500
    XOR A
    OUT (0xE6),A
    LD HL,0xE6CB
    LD B,29
clear:
    LD (HL),A
    INC HL
    DJNZ clear
    LD HL,0xEFF9
    LD B,7
clear_event:
    LD (HL),A
    INC HL
    DJNZ clear_event
    LD (0xD110),A
    LD HL,0xD080
    LD (0xE6CB),HL
    XOR A
    LD (0xD080),A
    LD (0xD081),A
    LD (0xD082),A
    LD A,15
    LD (0xD083),A
    LD HL,0xD1F0
    LD (0xD084),HL
    LD A,0xC3
    LD (0xECDF),A
    LD HL,hook
    LD (0xECE0),HL
    LD A,77
    LD (0xE6CF),A
    LD B,32
loop:
    PUSH BC
    DI
    CALL 0x3080
    DI
    POP BC
    DJNZ loop
    LD A,(0xE6CF)
    LD (0xD120),A
    LD A,(0xEFF9)
    LD (0xD121),A
    LD A,0xA5
    LD (0xDFFF),A
stop:
    JR stop
hook:
    LD (0xD124),HL
    LD HL,0
    ADD HL,SP
    LD (0xD122),HL
    LD HL,(0xD124)
    PUSH AF
    PUSH HL
    LD HL,0xD110
    INC (HL)
    LD E,(HL)
    LD D,0
    LD HL,0xD130
    ADD HL,DE
    POP DE
    POP AF
    LD (HL),A
    RET
'''

def check(result, count, sequence, chars, timer=None):
    assert result.get(0xDFFF) == 0xA5
    for address, expected in ((0xD122, 0xF2), (0xD123, 0xE4)):
        assert [value for addr, value in result['writes'] if addr == address] == [expected] * count, 'フック入口SP'
    assert result.get(0xD110, 0) == count, ('hook', result.get(0xD110), count)
    assert [result.get(0xD131+i) for i in range(count)] == sequence
    assert result.get(0xD080, 0) == len(chars), ('ring', result.get(0xD080), chars)
    assert [result.get(0xD1F1+i) for i in range(len(chars))] == chars
    if timer is not None:
        assert result.get(0xD120) == timer and result.get(0xD121) == 0


def main():
    with tempfile.TemporaryDirectory(prefix='b95-') as temp:
        work = Path(temp)
        rom, asm = work/'rom', work/'asm'
        subprocess.run([sys.executable, str(h.ROOT/'src/build_main_rom.py'), str(rom),
                        '--work-dir', str(asm)], check=True, stdout=subprocess.DEVNULL)
        cycles = h.idle_cycles((rom/'N88.ROM').read_bytes())
        assert cycles < 3016, f'3080 キーなし {cycles} T'
        print(f'PASS: 3080 キーなし {cycles} T', flush=True)
        obj = h.z80text.Assembler()
        obj.assemble(asm/'n88_main_gen.asm')
        disk = h.boot_disk(work, SOURCE)[0]
        def run(tag, keys, image=rom):
            return h.execute(work, image, disk, tag, keyboard=tuple(keys))
        for row, bit in ((8,4), (8,5), (8,6), (8,7), (10,7)):
            check(run(f'mod-{row}-{bit}', [(row,bit)]), 0, [], [], 77)
        check(run('shift-a', [(8,6),(2,1)]), 1, [17], [65,65])
        check(run('kana-a', [(8,5),(2,1)]), 1, [17], [0xC1,0xC1])
        check(run('shift-1', [(8,6),(0,1)]), 1, [1], [49,49])
        check(run('valid-and-zero', [(2,1),(10,0)]), 1, [17], [97,97])
        check(run('multi', [(2,2),(0,1),(2,1)]), 3, [1,17,18], [49,97,98,98])
        for row, bit in ((9,1),(10,0),(11,0)):
            check(run(f'zero-{row}-{bit}', [(row,bit)]), 0, [], [], 77)
        broken = work/'broken'
        shutil.copytree(rom, broken)
        code = bytearray((broken/'N88.ROM').read_bytes())
        pos = obj.labels['ENTRY_3080_DECODE']
        # CALL IK_DECODE_MAIN 後の JR Z を除去して０を通す。
        assert code[pos+3:pos+5] == bytes((0xB7,0x28))
        code[pos+4:pos+6] = b'\x00\x00'
        (broken/'N88.ROM').write_bytes(code)
        try:
            check(run('negative', [(8,6)], broken), 0, [], [], 77)
        except AssertionError:
            print('PASS: 陰性対照（修飾キーの除外を故障注入）')
        else:
            raise AssertionError('陰性対照を検出できない')
        print('PASS: 修飾キー・同時押し・表の0・リピート')

if __name__ == '__main__':
    main()
