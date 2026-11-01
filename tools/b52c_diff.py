#!/usr/bin/env python3
"""サブ RAM の差を模様の番号だけで示す。"""
import sys
from b38_sub_snapshot_compare import read


def compare(control, subject, length):
    pattern = [(i * 3 + 0x41) & 255 for i in range(length)]
    for offset, (a, b) in enumerate(zip(control[0], subject[0])):
        if a != b:
            matches = [f'p{i}' for i, value in enumerate(pattern) if value == b]
            yield f'changed {offset + 0x4000:04X} {" ".join(matches) if matches else "?"}'


def main():
    try:
        if len(sys.argv) != 4 or sys.argv[3] not in ('1', '2', '3', '4', '5'):
            raise ValueError()
        length = (8, 16, 8, 256, 0)[int(sys.argv[3]) - 1]
        print('\n'.join(compare(read(sys.argv[1]), read(sys.argv[2]), length)), end='')
        return 0
    except (OSError, ValueError):
        print('スナップショットを比較できません', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
