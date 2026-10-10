#!/usr/bin/env python3
"""型別配列の利用者を自作BASICと数値印だけで検査する。公式ROMは使わない。"""
from pathlib import Path
import argparse
import subprocess
import sys
import tempfile
from unittest.mock import patch
import l4_dim_measure as dim

REPO = Path(__file__).resolve().parents[1]


def cases():
    step, arm = dim.step, dim.arm
    result = []
    for name, suffix in [('int', '%'), ('single', '!'), ('double', '#')]:
        a = 'a'+suffix
        b = 'b'+suffix
        result.append(arm('impl-swap-'+name, [
            step([f'dim {a}(2,2)', f'{a}(1,2)=3', f'{a}(2,1)=7',
                  f'swap {a}(1,2),{a}(2,1)'], error=0),
            step(value=f'{a}(1,2)', error=0, prediction=7),
            step([f'{b}=11', f'swap {a}(1,2),{b}'], error=0),
            step(value=f'{a}(1,2)', error=0, prediction=11),
            step(value=b, error=0, prediction=7)]))
    result.append(arm('impl-strings', [
        step(['dim a$(2,2)', 'a$(1,2)="xy"', 'a$(2,1)="z"',
              'swap a$(1,2),a$(2,1)'], error=0),
        step(value='len(a$(1,2))', error=0, prediction=1),
        step(['b$="abcd"', 'swap b$,a$(2,1)'], error=0),
        step(value='len(b$)', error=0, prediction=2),
        step(value='len(a$(2,1))', error=0, prediction=4),
        step('a$(1,2)=""', error=0),
        step(value='len(a$(2,1))', error=0, prediction=4),
        step(['erase a$', 'dim a$(2,2)'], error=0),
        step(value='len(a$(2,1))', error=0, prediction=0)]))
    result.append(arm('impl-read', [
        step(['dim a%(2,2),b!(2),c#(2),d$(2)',
              'read a%(1,2),b!(1),c#(1),d$(1),z%'], error=0),
        step(value='a%(1,2)', error=0, prediction=3),
        step(value='b!(1)*4', error=0, prediction=13),
        step(value='c#(1)*2', error=0, prediction=9),
        step(value='len(d$(1))', error=0, prediction=2),
        step(value='z%', error=0, prediction=9)]))
    # DATAを実行しない位置へ置く。READの取得と変換を独立に検査する。
    result[-1]['data'] = 'data 2.5,3.25,4.5,xy,9'
    result.append(arm('impl-nested', [
        step(['dim a%(2,2),b%(2)', 'b%(1)=2', 'a%(2,1)=17',
              'a%(1,1)=a%(b%(1),1)', 'def fna%(x%)=a%(x%,1)'], error=0),
        step(value='fna%(b%(1))', error=0, prediction=17),
        step(value='a%(1,1)', error=0, prediction=17),
        step(['for j=0 to 2', 'b%(j)=j+3', 'next j'], error=0),
        step(value='b%(2)', error=0, prediction=5)]))
    result.append(arm('impl-hole', [
        step(['dim a%(99),b%(2,2)', 'b%(1,2)=19', 'a%=7',
              'b=fre(0)', 'erase a%', 'q=fre(0)-b'], error=0, prediction=209),
        step(value='b%(1,2)', error=0, prediction=19),
        step(value='a%', error=0, prediction=7),
        step(['dim a%(2,2)', 'b=fre(0)', 'erase a%', 'q=fre(0)-b'],
             error=0, prediction=29),
        step(value='b%(1,2)', error=0, prediction=19)]))
    result.append(arm('impl-expression-users', [
        step(['dim a%(3)', 'a%(0)=10:a%(1)=10:a%(2)=17:a%(3)=13',
              'screen 0,0', 'line (a%(0),a%(1))-(a%(2),a%(3)),7,b'], error=0),
        step(value='point(17,13)', error=0, prediction=7),
        step(['a%(0)=0', 'while a%(0)<3', 'a%(0)=a%(0)+1', 'wend'], error=0),
        step(value='a%(0)', error=0, prediction=3)]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom-dir', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='l4-array-impl-') as td:
        work = Path(td)
        rom = args.rom_dir
        if rom is None:
            rom = work/'rom'
            with (work/'build.log').open('w') as log:
                subprocess.run([sys.executable, str(REPO/'src/build_main_rom.py'),
                                str(rom), '--work-dir', str(work/'asm')],
                               stdout=log, stderr=log, check=True)
        failures = []
        original_lines = dim.program_lines
        def program_lines(case):
            lines = original_lines(case)
            if case.get('data'):
                lines[8000] = case['data']
            return lines
        for case in cases():
            with patch.object(dim, 'program_lines', program_lines):
                observation = dim.run_arm(rom, False, case, work)
            good = dim.valid(observation, case) and observation['errors'] == 0
            good = good and all(observation['probes'][str(i)] ==
                               [0, s['prediction'] or 0]
                               for i, s in enumerate(case['steps']))
            print(('OK ' if good else 'NG ')+case['id'], flush=True)
            if not good:
                print('数値印', observation['probes'], flush=True)
                failures.append(case['id'])
        return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
