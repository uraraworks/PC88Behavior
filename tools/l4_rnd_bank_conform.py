#!/usr/bin/env python3
"""第16節のQを実Z80とR_D予測器で照合する。自作試験ROMのみを使用。"""
from fractions import Fraction
from pathlib import Path
import random
import re
import sys
import tempfile

import l4_bank_dup_equ
import l4_rnd_measure as rnd
import l4_sqr_bank_conform as harness

sys.path.insert(0, str(harness.REPO / 'tools/asm'))
import z80text

# 合成ROMではSAVEを呼ばないため、捕捉域を結果の格納に使う。
OUT_BASE = harness.memmap.addresses()["MM_S2_CAPTURE_BASE"]


def mbf_bytes(number):
    return rnd.mbf.mbf4_bytes(*number.as_single_or_double_pair())


def check_batch(kind, cases, work):
    # 実装本体を再記述せず、mbf_single.asmとbank0.asmをそのまま連結する。
    single = harness.MBF_SINGLE_ASM.read_text()
    double = harness.MBF_DOUBLE_ASM.read_text()
    resident = single + '\n' + double
    bank = l4_bank_dup_equ.strip_dup_equ(resident, harness.BANK0_ASM.read_text())
    if kind == 'mul':
        load = 'LD DE,MBF_OPA\n    LD BC,8\n    LDIR'
        entry = 'MBF_MUL'
    elif kind == 'state':
        load = ('LD DE,RND_X\n    LD BC,6\n    LDIR\n    '
                'LD DE,MBF_OPA\n    LD BC,4\n    LDIR')
        entry = 'RND_IMPL'
    else:
        load = 'LD DE,RND_ACC3\n    LD BC,4\n    LDIR'
        entry = 'RND_U32_FRACTION'
    result_size = 6 if kind == 'state' else 4
    save_state = ''
    if kind == 'state':
        save_state = ('LD A,(RND_INDEX)\n    LD (DE),A\n    INC DE\n    '
                      'LD A,(RND_COUNT)\n    LD (DE),A\n    INC DE')
    prefix = harness.memmap.asm_prelude() + f'''ORG 0
    DI
    LD SP,MM_STACK_TOP
    LD HL,VECTORS
    LD DE,MM_S2_CAPTURE_BASE
    LD BC,{len(cases)}
check_loop:
    PUSH BC
    PUSH DE
    {load}
    PUSH HL
    CALL {entry}
    POP HL
    POP DE
    PUSH HL
    LD HL,MBF_RES
    LD BC,4
    LDIR
    {save_state}
    POP HL
    POP BC
    DEC BC
    LD A,B
    OR C
    JR NZ,check_loop
check_done:
    JR check_done
'''
    vectors = b''.join(case[0] for case in cases)
    tail = '\nORG 0x7000\nVECTORS:\nDB ' + ','.join(str(x) for x in vectors) + '\n'
    source = work / 'check.asm'
    source.write_text(prefix + resident + '\n' + bank + tail)
    asm = z80text.Assembler()
    asm.assemble(source)
    for equ, label in [('RND_FIN_AWAY_ADDR', 'FIN_ACC_TO_SINGLE_AWAY'),
                       ('AEL_MUL_ADDR', 'MBF_MUL')]:
        bank = re.sub(rf'^{equ} EQU 0x1787.*$',
                      f'{equ} EQU 0x{asm.labels[label]:04X}', bank, flags=re.M)
    source.write_text(prefix + resident + '\n' + bank + tail)
    code = z80text.Assembler().assemble(source)
    assert len(code) <= 0x8000
    rom = work / 'rom'
    rom.mkdir(exist_ok=True)
    (rom / 'N88.ROM').write_bytes(code + bytes(0x8000 - len(code)))
    (rom / 'DISK.ROM').write_bytes(bytes([0x18, 0xFE]) + bytes(0x7FE))
    mem = harness.run_and_collect(rom, result_size * len(cases), work, 500, out_base=OUT_BASE)
    for i, (_, want) in enumerate(cases):
        got = bytes(mem.get(OUT_BASE + result_size * i + j, 0) for j in range(result_size))
        if got != want:
            raise AssertionError(f'{kind} #{i}: {got.hex()} != {want.hex()}')


def main():
    mul = []
    # 起動列の積2000個を予測器から作り、積だけを既存MBF_MULで照合する。
    state = rnd.RDState()
    for _ in range(2000):
        a = rnd.encode_single_away(Fraction(rnd.RA_MULTIPLIERS[state.index]))
        y = rnd.expected_binop_away('*', state.number, a)
        mul.append((mbf_bytes(state.number) + mbf_bytes(a), mbf_bytes(y)))
        state.rnd()
    # 偶数仮数で真のhalf-tieになる積。両符号・8乗数を含める。
    ties = 0
    for n in rnd.RA_MULTIPLIERS:
        a = rnd.encode_single_away(Fraction(n))
        for sign in (0, 1):
            for m in range(0x800000, 0x1000000, 0x80000):
                product = m * a.mant
                shift = product.bit_length() - 24
                if product % (1 << shift) == 1 << (shift - 1):
                    x = rnd.mbf.GwNum('single', sign=sign, exp=128, mant=m)
                    y = rnd.expected_binop_away('*', x, a)
                    mul.append((mbf_bytes(x) + mbf_bytes(a), mbf_bytes(y)))
                    ties += 1
    assert ties > 0
    # 全32bitを使う変換: 0、最小値、低位Eだけの値、真のタイ、桁繰上げ。
    values = {0, 1, 2, 127, 128, 255, 256, 0xFFFFFF, 0x1000000,
              0x1000001, 0x1000003, 0x80000000, 0x80000040,
              0x80000080, 0xFFFFFF7F, 0xFFFFFF80, 0xFFFFFFFF}
    rng = random.Random(88)
    values.update(rng.getrandbits(32) for _ in range(1000))
    fraction = [(v.to_bytes(4, 'big'), mbf_bytes(rnd.encode_single_away(
        Fraction(v, 1 << 32)))) for v in sorted(values)]
    states = []
    samples = [rnd.encode_single_away(Fraction(0xcfc752, 1 << 24)),
               rnd.encode_single_away(Fraction(0)),
               rnd.mbf.GwNum('single', sign=0, exp=95, mant=0xdbe6fd),
               rnd.mbf.GwNum('single', sign=0, exp=195, mant=0xad78ed)]
    # 未観測の周期補正溢れも、自作のmod 2^24判断どおりになるか確認する。
    wraps = 0
    for _ in range(2000):
        x = rnd.mbf.GwNum('single', sign=0, exp=128,
                         mant=rng.randrange(0x800000, 0x1000000))
        a = rnd.encode_single_away(Fraction(rnd.RA_MULTIPLIERS[1]))
        y = rnd.expected_binop_away('*', x, a)
        packed = (y.mant & 0x7fffff) | (y.sign << 23)
        r = int.from_bytes((packed ^ 0x4f).to_bytes(3, 'little'), 'big')
        if r + 0xff01 >= 1 << 24:
            samples.append(x)
            wraps += 1
    assert wraps > 0
    for x in samples:
        for index, count in [(0, 0), (1, 170), (4, 169), (7, 170)]:
            for arg in (0, 1, -x.exact()):
                state = rnd.RDState()
                state.number, state.index, state.count = x, index, count
                result = state.rnd(arg)
                want = mbf_bytes(rnd.encode_single_away(result))
                want += bytes([state.index, state.count])
                argument = rnd.encode_single_away(Fraction(arg))
                source = mbf_bytes(x) + bytes([index, count]) + mbf_bytes(argument)
                states.append((source, want))
    with tempfile.TemporaryDirectory(prefix='l4-rnd-q-') as temp:
        root = Path(temp)
        for kind, cases in [('mul', mul), ('u32', fraction), ('state', states)]:
            for start in range(0, len(cases), 400):
                work = root / f'{kind}-{start}'
                work.mkdir()
                check_batch(kind, cases[start:start+400], work)
            print(f'OK {kind}: {len(cases)}件、Q一致')
    print(f'OK 積の真のhalf-tie {ties}件、補正溢れの状態 {wraps}件')


if __name__ == '__main__':
    main()
