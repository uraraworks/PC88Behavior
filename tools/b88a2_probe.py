#!/usr/bin/env python3
"""事前登録した入力からサブ CPU 用プローブを生成する。"""
import argparse
import json
from pathlib import Path

from b88a2_arms import arms

ORIGIN = 0x7800
RESULT = 0x7700


def word(n):
    return bytes((n & 255, n >> 8))


def generate(arm):
    code = bytearray()
    labels = {}
    fixes = []
    def emit(value):
        code.extend(bytes.fromhex(value))
    def label(name):
        labels[name] = ORIGIN + len(code)
    def ref(op, name):
        emit(op)
        fixes.append((len(code), name))
        code.extend(b'\0\0')
    def store(address, value):
        emit('3e %02x 32' % value)
        code.extend(word(address))

    variant = arm.get('variant', 'base')
    supplement = 'kind' in arm
    if supplement:
        from b88a1_arms import inputs, memory_inputs
        registers = inputs(arm)
    else:
        from b88_summarize import inputs
        registers = inputs(arm)
    emit('f3 31 00 7e')
    emit({0: 'ed 46', 1: 'ed 56', 2: 'ed 5e'}[arm.get('im', 1)])
    # 入力先と結果領域を既知の状態にする。
    for address, value in ((0x6000, variant == 'mem_de'),
                           (0x6100, variant == 'mem_hl'),
                           (0x6200, 0), (0x6300, 0),
                           (RESULT, 0), (RESULT + 1, 0)):
        store(address, int(value))
    if supplement:
        for address, value in memory_inputs(arm).items():
            store(address, value)
        label('prepare')
        if arm['kind'] == 'read':
            command = arm['command']
            steps = [(0x07d6, arm.get('ready_a', 0)), (0x035b, registers['A']),
                     (0x02a4, command[0])] + [(0x0020, v) for v in command[1:8]] + [(0x02a7, command[8])]
            for i, (address, value) in enumerate(steps):
                emit('3e %02x' % value)
                # EI は CALL/JP の直前。遅延中と入口到達時を別々に観測する。
                if address == 0x02a7:
                    ref('21', f'step_done_{i}')
                    emit('e5')
                emit('fb' if arm.get('iff') == 'ei' else 'f3')
                label(f'step_{i}')
                emit('c3' if address == 0x02a7 else 'cd')
                code.extend(word(address))
                label(f'step_done_{i}')
        label('prepared')
    if arm['mode'] == 'jp':
        ref('21', 'returned')
        emit('e5')
    emit('01'); code.extend(word(registers['BC']))
    emit('11'); code.extend(word(registers['DE']))
    # AF を最後に復元して入力フラグを維持する。
    emit('21'); code.extend(word(registers['A'] << 8 | registers['F']))
    emit('e5 f1')
    emit('21'); code.extend(word(registers['HL']))
    label('start')
    emit('32'); code.extend(word(RESULT))
    emit('fb' if arm.get('iff') == 'ei' else 'f3')
    label('invoke')
    target = arm['address']
    if target is None:
        ref('cd', 'negative' if arm['name'] == 'negative' else 'positive')
    elif arm['mode'] == 'rst':
        emit('%02x' % (0xc7 + target))
    else:
        emit('c3' if arm['mode'] == 'jp' else 'cd')
        code.extend(word(target))
    label('returned')
    # 戻り直後の SP と全レジスタを退避し、退避後に完了印を置く。
    emit('f3')
    emit('ed 73'); code.extend(word(RESULT + 2))
    emit('f5 c5 d5 e5')
    for offset in (4, 6, 8, 10):
        emit('e1 22'); code.extend(word(RESULT + offset))
    store(RESULT + 1, 0xa5)
    emit('c3 c1 00')
    label('negative')
    emit('c9')
    label('positive')
    emit('3c 32 00 64 c9')
    for offset, name in fixes:
        code[offset:offset + 2] = word(labels[name])
    if ORIGIN + len(code) > 0x7d00:
        raise ValueError('プローブがスタック領域に重なります')
    return bytes(code), labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('arm', choices=[a['name'] for a in arms()])
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    arm = next(a for a in arms() if a['name'] == args.arm)
    probe, labels = generate(arm)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'b88_sub.bin').write_bytes(probe)
    (args.output / 'b88_labels.json').write_text(json.dumps(labels, indent=2) + '\n')


if __name__ == '__main__':
    main()
