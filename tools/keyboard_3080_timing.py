"""キーなし・前回もキーなしの3080を機械語から実行し、T数を数える。"""
def idle_cycles(rom):
    m = bytearray(65536)
    m[:len(rom)] = rom
    pc, sp, a, b, c, de, hl, z, sign, t = 0x3080, 0xe500, 0, 0, 0, 0, 0, False, False, 0
    def word(p): return m[p] | m[p+1] << 8
    for _ in range(10000):
        op = m[pc]; pc += 1
        if op in (0xc5, 0xd5, 0xe5, 0xf5): sp -= 2; t += 11
        elif op in (0xc1, 0xd1, 0xe1, 0xf1):
            sp += 2; t += 10
        elif op == 0x3e: a = m[pc]; pc += 1; t += 7
        elif op == 0x0e: c = m[pc]; pc += 1; t += 7
        elif op == 0x06: b = m[pc]; pc += 1; t += 7
        elif op == 0x21: hl = word(pc); pc += 2; t += 10
        elif op == 0x11: de = word(pc); pc += 2; t += 10
        elif op == 0x32: m[word(pc)] = a; pc += 2; t += 13
        elif op == 0x3a: a = m[word(pc)]; pc += 2; t += 13
        elif op == 0xd3: pc += 1; t += 11
        elif op == 0xaf: a = 0; z = True; sign = False; t += 4
        elif op == 0xb7: z = a == 0; sign = bool(a & 128); t += 4
        elif op == 0x7e: a = m[hl]; t += 7
        elif op == 0x12: m[de] = a; t += 7
        elif op == 0x77: m[hl] = a; t += 7
        elif op == 0x47: b = a; t += 4
        elif op == 0x2f: a ^= 255; t += 4
        elif op == 0xa8: a ^= b; z = a == 0; sign = bool(a & 128); t += 4
        elif op == 0xa6: a &= m[hl]; z = a == 0; sign = bool(a & 128); t += 7
        elif op == 0xb6: a |= m[hl]; z = a == 0; sign = bool(a & 128); t += 7
        elif op == 0x2b: hl = (hl-1)&65535; t += 6
        elif op == 0x1b: de = (de-1)&65535; t += 6
        elif op == 0x0d: c = (c-1)&255; z = c == 0; sign = bool(c & 128); t += 4
        elif op == 0x0c: c = (c+1)&255; z = c == 0; sign = bool(c & 128); t += 4
        elif op == 0x79: a = c; t += 4
        elif op == 0x26: hl = (m[pc]<<8)|(hl&255); pc += 1; t += 7
        elif op == 0x67: hl = (a<<8)|(hl&255); t += 4
        elif op == 0x69: hl = (hl&0xff00)|c; t += 4
        elif op == 0x6f: hl = (hl&0xff00)|a; t += 4
        elif op == 0x19: hl = (hl+de)&65535; t += 11
        elif op == 0x23: hl = (hl+1)&65535; t += 6
        elif op == 0xfe: v = (a-m[pc])&255; pc += 1; z = v == 0; sign = bool(v & 128); t += 7
        elif op == 0xc3: pc = word(pc); t += 10
        elif op in (0xc2, 0xca, 0xf2):
            target = word(pc); pc += 2; t += 10
            if (op == 0xc2 and not z) or (op == 0xca and z) or (op == 0xf2 and not sign): pc = target
        elif op in (0x20, 0x28, 0x18, 0x10):
            off = m[pc]; pc += 1
            if op == 0x10: b = (b-1)&255
            take = op == 0x18 or (op == 0x20 and not z) or (op == 0x28 and z) or (op == 0x10 and b != 0)
            if take: pc += off if off < 128 else off-256
            t += (13 if take else 8) if op == 0x10 else (12 if take else 7)
        elif op == 0xed:
            sub = m[pc]; pc += 1
            if sub == 0x78: a = 255; z = False; sign = True; t += 12
            else: raise AssertionError(f'ED {sub:02X} at {pc-2:04X}')
        elif op == 0xfb: t += 4
        elif op == 0xc9: return t+10
        else: raise AssertionError(f'命令 {op:02X} at {pc-1:04X}')
    raise AssertionError('3080が戻らない')
