#!/usr/bin/env python3
"""m6f-h の凍結値を再計算して照合する。"""
from pathlib import Path
import argparse
import sys
import make_m6fh_frozen as frozen


def check(path: Path) -> bool:
    return path.read_text(encoding='ascii') == '\n'.join(frozen.lines())+'\n'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, default=frozen.HERE/'m6fh_frozen.tsv')
    a = p.parse_args()
    try:
        if not check(a.config):
            raise ValueError
    except (OSError, UnicodeError, ValueError):
        print('gate_failed: preregistration_mismatch', file=sys.stderr)
        return 1
    print('m6f-h preregistration: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
