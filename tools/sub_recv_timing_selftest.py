#!/usr/bin/env python3
"""0x16の定常受信2バイトを、生成命令から待ち成立時のT数で比較する。"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'src/l3_service/make_subrom.py'


def assemble(path):
    spec = importlib.util.spec_from_file_location('subrom_timing', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = mod.build_subrom()
    a.resolve()
    return a


def cycles(a, fault=False):
    code = bytearray(a.code)
    if fault:
        # 受信CALL先にCALL/RETを追加し、他の命令とI/O順を保つ。
        call = a.labels["_general_load_byte"]
        assert code[call] == 0xCD
        target = code[call + 1] | code[call + 2] << 8
        wrapper = len(code)
        code.extend((0xCD, target & 255, target >> 8, 0xC9))
        code[call + 1:call + 3] = bytes((wrapper & 255, wrapper >> 8))
    pc = start = a.labels['_general_load_check']
    stack = []
    af_stack = []
    A, B, D, E, z, carry = 0, 0x16, 0x08, 0x00, False, False
    t = 0
    io = []
    instructions = []
    for _ in range(200):
        op = code[pc]
        instructions.append(op)
        pc += 1
        if op == 0x1B: E = (E - 1) & 255; D = (D - (E == 255)) & 255; t += 6
        elif op == 0x7A: A = D; t += 4
        elif op == 0x7B: A = E; t += 4
        elif op == 0x7C: raise AssertionError('想定外のLD A,H')
        elif op == 0x7D: raise AssertionError('想定外のLD A,L')
        elif op == 0x7F: t += 4
        elif op == 0x78: A = B; t += 4
        elif op == 0xB3: A |= E; z = A == 0; carry = False; t += 4
        elif op == 0x1F: carry, A = bool(A & 1), (A >> 1) | (int(carry) << 7); t += 4
        elif op == 0xFE: z = A == code[pc]; carry = A < code[pc]; pc += 1; t += 7
        elif op == 0xE6: A &= code[pc]; z = A == 0; carry = False; pc += 1; t += 7
        elif op == 0x3E: A = code[pc]; pc += 1; t += 7
        elif op == 0xF5: af_stack.append((A, z, carry)); t += 11
        elif op == 0xF1: A, z, carry = af_stack.pop(); t += 10
        elif op == 0x77: t += 7
        elif op == 0x23: t += 6
        elif op == 0xDB:
            port = code[pc]; pc += 1; io.append(('in', port))
            A = (1 if pc - 2 == a.labels['WAIT_FE_RECV_DATA_READY_LOOP'] else 0) if port == 0xFE else 0x42
            t += 11
        elif op == 0xD3: io.append(('out', code[pc], A)); pc += 1; t += 11
        elif op in (0xC3, 0xCA, 0xCD):
            target = code[pc] | code[pc + 1] << 8; pc += 2
            if op == 0xCD: stack.append(pc); pc = target; t += 17
            else:
                if op == 0xC3 or z: pc = target
                t += 10
        elif op in (0x18, 0x20, 0x28, 0x30):
            offset = code[pc]; pc += 1
            take = op == 0x18 or (op == 0x20 and not z) or (op == 0x28 and z) or (op == 0x30 and not carry)
            if take: pc += offset if offset < 128 else offset - 256
            t += 12 if take else 7
        elif op == 0xD7: stack.append(pc); pc = 0x10; t += 11
        elif op == 0xC9: pc = stack.pop(); t += 10
        else: raise AssertionError(f'未対応命令 {op:02x} at {pc-1:04x}')
        if pc == start and not stack:
            assert not af_stack
            return t, io, instructions
    raise AssertionError('受信ループが一周しない')


def main():
    old_source = subprocess.check_output(['git', 'show', '97430aa:src/l3_service/make_subrom.py'], cwd=ROOT)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'baseline.py'
        path.write_bytes(old_source)
        old = assemble(path)
        current = assemble(SOURCE)
    baseline, old_io, old_instructions = cycles(old)
    actual, new_io, new_instructions = cycles(current)
    assert old_io == new_io, 'I/Oの順序または値が異なる'
    assert old_instructions == new_instructions, '命令の順序が異なる'
    assert actual <= baseline, f'受信が遅い: {actual} > {baseline} T/2バイト'
    fault, fault_io, _ = cycles(current, fault=True)
    assert fault_io == new_io and fault > baseline, 'CALL/RET故障を検出できない'
    print(f'PASS: 0x16定常受信 {actual}/2 T/バイト、基準 {baseline}/2、故障 {fault}/2')


if __name__ == '__main__':
    main()
