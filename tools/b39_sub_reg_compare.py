#!/usr/bin/env python3
"""B39 の生記録を値を表示せず比較する。"""
import pathlib
import re
import sys

REGS = ('AF', 'BC', 'DE', 'HL', 'IX', 'IY', 'PC', 'SP', 'AF1', 'BC1', 'DE1', 'HL1', 'I', 'R', 'IFF', 'IFF2', 'IM', 'HALT')

def read(path):
    events = {'C': [], 'F': [], 'R': [], 'I': []}
    with pathlib.Path(path).open(encoding='ascii') as f:
        if f.readline() != 'Q88REG1\n':
            raise ValueError('不正な記録')
        ended = False
        for line in f:
            if line == 'END\n':
                ended = True
                if f.read(1): raise ValueError('不正な記録')
                break
            parts = line.split()
            if len(parts) == 19 and parts[0] in ('C', 'F') and all(re.fullmatch(r'[0-9A-F]{4}', x) for x in parts[1:]):
                row = tuple(int(x, 16) for x in parts[1:])
                if parts[0] == 'C' and row[6] < 0x2000: raise ValueError('不正な記録')
                events[parts[0]].append(row)
            elif len(parts) == 3 and parts[0] == 'X' and all(re.fullmatch(r'[0-9A-F]{4}', x) for x in parts[1:]):
                pass
            elif len(parts) == 3 and parts[0] == 'O' and parts[1] in ('R', 'I') and re.fullmatch(r'[0-9A-F]{4}', parts[2]) and int(parts[2], 16) >= 0x2000:
                events[parts[1]].append(int(parts[2], 16))
            else:
                raise ValueError('不正な記録')
        if not ended: raise ValueError('不完全な記録')
    return events

def compare(a, b):
    lines = ['# 識別子: G1']
    def first(xs, ys, pred):
        return next((i for i, (x, y) in enumerate(zip(xs, ys)) if pred(x, y)), None)
    def index(n): return 'none' if n is None else str(n)
    for kind, label in (('C', 'cross'), ('F', 'fc')):
        x, y = a[kind], b[kind]
        lines.append(f'{label} count {len(x)} {len(y)}')
        if kind == 'C':
            n = first(x, y, lambda u, v: u[6] != v[6])
            lines.append(f'cross first-pc-differ {index(n)}')
        for j, name in enumerate(REGS):
            if name == 'R': continue
            n = first(x, y, lambda u, v: u[j] != v[j])
            if n is None: detail = 'none'
            elif kind == 'C': detail = f'{x[n][6]:04X}'
            else: detail = 'pc-same' if x[n][6] == y[n][6] else 'pc-differ'
            lines.append(f'{label} first-reg-differ {name} {index(n)} {detail}')
        if kind == 'F':
            eligible = lambda u, v: u[6] == v[6] and u[6] >= 0x2000
            for j, name in enumerate(REGS):
                if name == 'R': continue
                n = first(x, y, lambda u, v: eligible(u, v) and u[j] != v[j])
                lines.append(f'fc first-reg-differ-same-pc {name} {index(n)}')
            for name in ('BC', 'HL'):
                j = REGS.index(name)
                n = next((i for i in range(min(len(x), len(y), 76570) - 1, -1, -1)
                          if eligible(x[i], y[i]) and x[i][j] == y[i][j]), None)
                lines.append(f'fc last-reg-same-before {name} {index(n)}')
    for key, name in (('R', 'LD_A_R'), ('I', 'LD_A_I')):
        x, y = a[key], b[key]
        pc = lambda z: f'{z[0]:04X}' if z else 'none'
        lines.append(f'opcode {name} {len(x)} {len(y)} {pc(x)} {pc(y)}')
    return lines

def main():
    try:
        if len(sys.argv) != 3: raise ValueError('引数が不正')
        print('\n'.join(compare(read(sys.argv[1]), read(sys.argv[2]))))
    except Exception:
        print('比較できません', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__': sys.exit(main())
