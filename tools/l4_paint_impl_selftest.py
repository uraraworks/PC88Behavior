#!/usr/bin/env python3
"""自作PAINTの同色通路・タイル内境界色・分割訪問ビットを手計算で検査。公式ROM不要。"""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

import l4_paint_measure as paint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='paint-impl-', dir=args.work_dir) as temp:
        work = Path(temp)
        rom = work / 'rom'
        with (work / 'build.log').open('w') as log:
            subprocess.run([sys.executable, str(paint.kw.REPO / 'src/build_main_rom.py'), str(rom)],
                           stdout=log, stderr=log, check=True)
        frame = paint.lm.L((10, 10), (20, 50), 7, 'b')
        tile = bytes((255, 170, 170))  # 絶対Xが偶数なら7、奇数なら1
        arms = [
            paint.arm('impl-same', paint.PRE + [frame,
                paint.lm.L((11, 30), (19, 30), 5), paint.P((15, 12), 5, 7, probe=True)], wait=3000),
            paint.arm('impl-tile', paint.PRE + [frame] + paint.tile_defs('t$', tile) + [
                paint.P((15, 12), tile=tile, b=7, probe=True)], wait=3000),
        ]
        records = paint.measure(rom, False, arms, work)
        for record in records:
            aid = record['arm']['id']
            expected = {(x, y): 7 for y in range(10, 51) for x in range(10, 21)
                        if x in (10, 20) or y in (10, 50)}
            expected.update({(x, y): (5 if aid == 'impl-same' else (7 if x % 2 == 0 else 1))
                             for y in range(11, 50) for x in range(11, 20)})
            assert record['gate'], (aid, '関門')
            for obs in record['obs']:
                got = paint.lm.from_spans(obs['spans'])
                differences = [(xy, expected.get(xy, 0), got.get(xy, 0))
                               for xy in sorted(set(expected) | set(got))
                               if expected.get(xy, 0) != got.get(xy, 0)]
                assert not differences, (aid, '画素', len(differences), differences[:8])
                assert list(obs['res'].values()) == [[0, 15, 12]], (aid, 'ERR/LP')
            print(f'OK {aid}: 手計算451画素・2走一致')


if __name__ == '__main__':
    main()
