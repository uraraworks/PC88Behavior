#!/usr/bin/env python3
"""n1用の自作ROMを生成する。外部ROMは参照しない。"""
import argparse
import pathlib
from make_ext_rom_test import asm, build_disk


def build(out, variant='normal', interrupts=True):
    out.mkdir(parents=True, exist_ok=True)
    (out / 'N80.ROM').unlink(missing_ok=True)
    # 9000hで走るコードを1000hからコピーする。
    src = '''
        ORG 9000h
        DI
        LD SP,0ff00h
        IN A,(30h)
        LD (0c100h),A
        IN A,(31h)
        LD (0c101h),A
        LD A,0a1h
        OUT (31h),A
        LD (0c102h),A
        LD A,(0100h)
        LD (0c110h),A
        LD A,(5fffh)
        LD (0c111h),A
        LD A,(6000h)
        LD (0c112h),A
        LD A,(7fffh)
        LD (0c113h),A
        XOR A
        OUT (32h),A
        OUT (71h),A
        LD A,(6000h)
        LD (0c114h),A
        LD A,(7fffh)
        LD (0c115h),A
        LD A,(0c102h)
        OR 04h
        OUT (31h),A
        LD A,(0100h)
        LD (0c116h),A
        LD A,(3fffh)
        LD (0c117h),A
        LD A,(5fffh)
        LD (0c118h),A
        LD A,(6000h)
        LD (0c119h),A
        LD A,(7fffh)
        LD (0c11ah),A
'''
    if interrupts:
        src += '''
        XOR A
        LD (0c120h),A
        LD (0c121h),A
        LD A,2
        OUT (0e4h),A
        OUT (0e6h),A
        IM 1
        EI
        LD BC,0
WAIT1:
        DEC BC
        LD A,B
        OR C
        JR NZ,WAIT1
        DI
'''
    src += '''
        LD A,(0c102h)
        OUT (31h),A
        LD A,(0100h)
        LD (0c11bh),A
        LD A,(6000h)
        LD (0c11ch),A
        LD A,(7fffh)
        LD (0c11dh),A
        LD A,1
        OUT (71h),A
        LD A,(6000h)
        LD (0c11eh),A
        LD A,(7fffh)
        LD (0c11fh),A
        LD A,05ah
        LD (0c122h),A
DONE:   JR DONE
'''
    code = asm(src)[0x9000:]
    boot = asm('''
        ORG 0000h
        JP 0400h
        ORG 0400h
        DI
        LD SP,0ff00h
        LD HL,1000h
        LD DE,9000h
        LD BC,%d
        LDIR
        JP 9000h
    ''' % len(code))
    isr = asm('''
        ORG 0038h
        PUSH AF
        PUSH HL
        LD A,2
        OUT (0e4h),A
        LD HL,0c120h
        INC (HL)
        POP HL
        POP AF
        EI
        RETI
    ''')[0x38:]
    def rom(n):
        b = bytearray([n] * 0x8000)
        b[:len(boot)] = boot
        b[0x100] = n
        b[0x38:0x38+len(isr)] = isr
        if n == 0x22:
            b[0x3f] = 0x21  # ISR counter C121
        b[0x1000:0x1000+len(code)] = code
        return b
    main, nrom = rom(0x11), rom(0x22)
    if variant == 'changed':
        for p in (0x100, 0x3fff, 0x5fff, 0x6000, 0x7fff): nrom[p] = 0x33
    (out/'N88.ROM').write_bytes(main)
    (out/'DISK.ROM').write_bytes(build_disk())
    (out/'N88_0.ROM').write_bytes(bytes([0x44])*0x2000)
    if variant != 'missing':
        if variant == 'short': nrom = nrom[:0x4000]
        if variant == 'long': nrom += b'\x55'
        (out/'N80.ROM').write_bytes(nrom)

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('outdir',type=pathlib.Path)
    p.add_argument('--variant',choices=['normal','missing','changed','short','long'],default='normal')
    a=p.parse_args(); build(a.outdir,a.variant,a.variant in ('normal','changed','long'))
