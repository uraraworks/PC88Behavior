#!/usr/bin/env python3
"""自作ROMだけでINKEY$の長押しと短打を検査。本文・比較値は出力しない。"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

import l4_inkey_measure as ik


def run(rom, hold, work):
    # 先頭8文字だけでなく、取得した全文字の長さ・文字をBASIC側で検査する。
    lines = ['new', '10 c=0:b=0', '20 for j=1 to 10000:a$=inkey$',
             '30 if a$="" then 70', '40 c=c+1',
             '50 if len(a$)<>1 then b=b+1:goto 70',
             '60 if asc(a$)<>97 then b=b+1', '70 next',
             '80 print "iks";c;b', '90 print "ikd";1', '100 end', 'cls', 'run']
    args = [str(ik.kw.FRONT), '--core', str(ik.kw.find_core()), '--rom-dir', str(rom)]
    at = 100
    for line in lines:
        args += ['--key-hold', '4', '--key-gap', '8', '--type-at', str(at), '--type', line+'\n']
        if line == 'run':
            origin = at + len(line)*12
        at += (len(line)+1)*12+240
    capture = origin+18000
    screen = work/'repeat.bin'
    args += ['--key-hold', str(hold), '--key-gap', '8', '--type-at', str(origin+600),
             '--type', 'a', '--vram-dump', str(screen), '--vram-dump-at', str(capture),
             '--frames', str(capture+10)]
    p = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL,
                       env=dict(os.environ, M6FH_LONG_TYPING='1'), timeout=240)
    try:
        if p.returncode or not screen.exists():
            return False
        rows, _ = ik.extract(screen.read_bytes())
        if len(rows) != 2 or rows[-1] != ['ikd', 1]:
            return False
        stats = rows[0]
        return (len(stats) == 3 and stats[0] == 'iks' and stats[2] == 0
                and (stats[1] == 1 if hold == 4 else stats[1] >= 2))
    finally:
        screen.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom-dir', type=Path, required=True, help='ビルド済みの自作ROM')
    args = parser.parse_args()
    failures = 0
    with tempfile.TemporaryDirectory(prefix='inkey-repeat-') as tmp:
        for hold in (4, 160):
            for round_id in (1, 2):
                passed = run(args.rom_dir, hold, Path(tmp))
                failures += not passed
                print(f'hold={hold} round={round_id}: {"OK" if passed else "NG"}', flush=True)
    return int(failures != 0)


if __name__ == '__main__':
    raise SystemExit(main())
