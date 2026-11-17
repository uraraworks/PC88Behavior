"""固定入口を機械語から計時。FEの各応答を最初の読取りで返す擬似サブ。"""
import argparse
from pathlib import Path
from keyboard_3080_timing import idle_cycles


def link_cycles(rom, entry):
    m = bytearray(65536)
    m[:len(rom)] = rom
    pc, sp = entry, 0xe500
    a, f, b, c, d, e, h, l = 6, 0, 0, 0, 0, 0, 0, 0
    t, depth, last_control = 0, 0, 0
    def word(p): return m[p] | m[(p+1)&65535] << 8
    def push(v):
        nonlocal sp
        sp -= 2; m[sp:sp+2] = v.to_bytes(2, 'little')
    def pop():
        nonlocal sp
        v = word(sp); sp += 2; return v
    for _ in range(10000):
        op = m[pc]; pc += 1
        if op in (0xf5, 0xc5, 0xd5, 0xe5):
            push({0xf5:(a<<8)|f, 0xc5:(b<<8)|c, 0xd5:(d<<8)|e, 0xe5:(h<<8)|l}[op]); t += 11
        elif op in (0xf1, 0xc1, 0xd1, 0xe1):
            v = pop(); t += 10
            if op == 0xf1: a, f = v>>8, v&255
            elif op == 0xc1: b, c = v>>8, v&255
            elif op == 0xd1: d, e = v>>8, v&255
            else: h, l = v>>8, v&255
        elif op in (0x3e, 0x0e, 0x06):
            v = m[pc]; pc += 1; t += 7
            if op == 0x3e: a = v
            elif op == 0x0e: c = v
            else: b = v
        elif op in (0x21, 0x11):
            v = word(pc); pc += 2; t += 10
            if op == 0x21: h, l = v>>8, v&255
            else: d, e = v>>8, v&255
        elif op == 0x39:
            v = ((h<<8)|l) + sp; h, l = (v>>8)&255, v&255; t += 11
        elif op == 0x23: v = ((h<<8)|l)+1; h, l = (v>>8)&255, v&255; t += 6
        elif op == 0x7e: a = m[(h<<8)|l]; t += 7
        elif op == 0x7d: a = l; t += 4
        elif op == 0x7c: a = h; t += 4
        elif op == 0x6f: l = a; t += 4
        elif op == 0x32: m[word(pc)] = a; pc += 2; t += 13
        elif op == 0x3a: a = m[word(pc)]; pc += 2; t += 13
        elif op in (0xaf, 0xb7, 0xa1, 0xe6, 0xf6, 0xfe):
            if op == 0xaf: a = 0; v = a; cost = 4
            elif op == 0xb7: v = a; cost = 4
            elif op == 0xa1: a &= c; v = a; cost = 4
            else:
                n = m[pc]; pc += 1; cost = 7
                if op == 0xe6: a &= n; v = a
                elif op == 0xf6: a |= n; v = a
                else: v = (a-n)&255
            f = (0x40 if v == 0 else 0) | (0x80 if v&128 else 0) | (1 if op == 0xfe and a < n else 0); t += cost
        elif op == 0xd3:
            port = m[pc]; pc += 1; t += 11
            if port == 0xff: last_control = a
        elif op == 0xdb:
            port = m[pc]; pc += 1; t += 11
            a = (0 if last_control == 0x0d else 7) if port == 0xfe else 0x80
        elif op == 0xcd: target = word(pc); pc += 2; push(pc); pc = target; depth += 1; t += 17
        elif op in (0xc3, 0xca, 0xc2, 0xda, 0xd2):
            target = word(pc); pc += 2; t += 10
            if op == 0xc3 or (op == 0xca and f&0x40) or (op == 0xc2 and not f&0x40) or (op == 0xda and f&1) or (op == 0xd2 and not f&1): pc = target
        elif op in (0x20, 0x28, 0x38, 0x18, 0x10):
            off = m[pc]; pc += 1
            if op == 0x10: b = (b-1)&255
            take = op == 0x18 or (op == 0x20 and not f&0x40) or (op == 0x28 and f&0x40) or (op == 0x38 and f&1) or (op == 0x10 and b)
            if take: pc += off if off < 128 else off-256
            t += (13 if take else 8) if op == 0x10 else (12 if take else 7)
        elif op in (0xc9, 0xc0, 0xd8):
            take = op == 0xc9 or (op == 0xc0 and not f&0x40) or (op == 0xd8 and f&1)
            t += (10 if op == 0xc9 else (11 if take else 5))
            if take:
                if depth == 0: return t
                pc = pop(); depth -= 1
        elif op == 0x00: t += 4
        else: raise AssertionError(f'未対応命令 {op:02X} at {pc-1:04X}')
    raise AssertionError(f'{entry:04X} が戻らない')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('rom', type=Path)
    p.add_argument('--baseline', action='store_true', help='調整前の値を表示')
    args = p.parse_args()
    rom = args.rom.read_bytes()
    # 通信入口は即応答の擬似サブで数える。公式の最頻値(B98)は実サブ込みなので、
    # 目標は「擬似サブでの旧所要 + (公式 - 自作) の実サブでの差」。3847 は自作が長いので +4T(IFF検査用NOP)だけ。
    cases = [('3080 EFFE=0', idle_cycles(rom), 3016),
             ('3080 解放後', idle_cycles(rom, True), 3016)]
    cases += [(f'{entry:04X}', link_cycles(rom, entry), target)
              for entry, target in ((0x37d2, 345 + 176), (0x37c9, 572 + 210), (0x3847, 438 + 4))]
    print('入口 | 所要T | 目標との差 | 判定')
    for name, actual, target in cases:
        ok = abs(actual-target) <= 8
        print(f'{name} | {actual} | {actual-target:+d} | {"PASS" if ok else "FAIL"}')
    if not args.baseline:
        assert all(abs(actual-target) <= 8 for _, actual, target in cases)


if __name__ == '__main__':
    main()
