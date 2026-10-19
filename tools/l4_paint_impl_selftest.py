#!/usr/bin/env python3
"""自作PAINTの同色通路・タイル・閉矩形への縮小・不足時の無描画を手計算で検査。公式ROM不要。"""
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
            subprocess.run([sys.executable, str(paint.kw.REPO / 'src/build_main_rom.py'), str(rom),
                            '--work-dir', str(work / 'asm')],
                           stdout=log, stderr=log, check=True)
        frame = paint.lm.L((10, 10), (20, 50), 7, 'b')
        tile = bytes((255, 170, 170))  # 絶対Xが偶数なら7、奇数なら1
        arms = [
            paint.arm('impl-same', paint.PRE + [frame,
                paint.lm.L((11, 30), (19, 30), 5), paint.P((15, 12), 5, 7, probe=True)], wait=3000),
            paint.arm('impl-tile', paint.PRE + [frame] + paint.tile_defs('t$', tile) + [
                paint.P((15, 12), tile=tile, b=7, probe=True)], wait=3000),
        ]
        # DIM後は全画面用ビットを置けない。同色の横線も通過し、
        # 境界色を含むタイルでも閉矩形の全成分が埋まることを検査する。
        low = paint.PRE + [paint.X('dim a(5500)', None)]
        arms += [
            paint.arm('impl-low-same', low + [frame,
                paint.lm.L((11, 30), (19, 30), 5), paint.P((15, 12), 5, 7, probe=True)], wait=3000),
            paint.arm('impl-low-tile', low + [frame] + paint.tile_defs('t$', tile) + [
                paint.P((15, 12), tile=tile, b=7, probe=True)], wait=3000),
            # 候補の右辺に、開始点の十字線からは見えない穴。閉矩形と誤認してはいけない。
            paint.arm('impl-low-gap', low + [frame, paint.lm.pset(20, 40, 0),
                paint.P((15, 12), 5, 7, probe=True)], wait=3000),
            paint.arm('impl-low-full', low + [paint.P((15, 12), 5, 7, probe=True)], wait=3000),
            # 左端は画面の壁。それ以外の3辺で閉じればx=0も成分に含める。
            paint.arm('impl-low-edge', low + [
                paint.lm.L((0, 10), (20, 10), 7), paint.lm.L((0, 50), (20, 50), 7),
                paint.lm.L((20, 10), (20, 50), 7), paint.P((15, 12), 5, 7, probe=True)], wait=3000),
        ]
        records = paint.measure(rom, False, arms, work)
        for record in records:
            aid = record['arm']['id']
            expected = {(x, y): 7 for y in range(10, 51) for x in range(10, 21)
                        if x in (10, 20) or y in (10, 50)}
            err = 0
            if aid.endswith('-gap'):
                del expected[20, 40]
                err = 7
            elif aid.endswith('-full'):
                expected = {}
                err = 7
            elif aid.endswith('-edge'):
                expected = {(x, y): 7 for x in range(21) for y in (10, 50)}
                expected.update({(20, y): 7 for y in range(11, 50)})
                expected.update({(x, y): 5 for x in range(20) for y in range(11, 50)})
            else:
                expected.update({(x, y): ((7 if x % 2 == 0 else 1) if aid.endswith('-tile') else 5)
                                 for y in range(11, 50) for x in range(11, 20)})
            assert record['gate'], (aid, '関門')
            for obs in record['obs']:
                got = paint.lm.from_spans(obs['spans'])
                differences = [(xy, expected.get(xy, 0), got.get(xy, 0))
                               for xy in sorted(set(expected) | set(got))
                               if expected.get(xy, 0) != got.get(xy, 0)]
                assert not differences, (aid, '画素', len(differences), differences[:8])
                assert list(obs['res'].values()) == [[err, 15, 12]], (aid, 'ERR/LP')
            print(f'OK {aid}: 手計算{len(expected)}画素・ERR {err}・2走一致')


if __name__ == '__main__':
    main()
