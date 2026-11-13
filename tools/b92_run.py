#!/usr/bin/env python3
"""B92 の腕を独立起動し、外部の生記録を値なし集計へ渡す。"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from b92_summary import outside, summarize

ROOT = Path(__file__).resolve().parent.parent
VALUES = (0, 1, 2, 4, 8, 16, 32, 64, 128, 255)
RANGES = ((0xE60E, 0xE616), (0xE63D, 0xE640), (0xE6B0, 0xE6B4),
          (0xE6B8, 0xE6B9), (0xE6C0, 0xE6C2), (0xE6C4, 0xE6C5),
          (0xEABD, 0xEABD), (0xEACC, 0xEACD), (0xEB10, 0xEB11),
          (0xEC41, 0xEC42), (0xEC46, 0xEC46), (0xEF86, 0xEF86),
          (0xEF88, 0xEF89))
ADDRESSES = tuple(a for lo, hi in RANGES for a in range(lo, hi + 1)) + (0xE700,)


def empty_run(error=None):
    return dict(out=[], screen=[], returned=False, sp=None, frames=0,
                interventions=0, reached=False, complete=False, escaped=False,
                prior_out31=False, prior_e6c2=False, error=error)


def parse_log(path):
    """切断・重複・不正順序を欠測にする。エラーに生の行を混ぜない。"""
    result = empty_run()
    state, writes, start, finish = 'header', [], 0, 0
    for line in outside(path).read_text().splitlines():
        fields = line.split()
        if state == 'header':
            if fields != ['B92', '1']:
                raise ValueError('形式不正')
            state = 'waiting'
            continue
        if not fields:
            raise ValueError('形式不正')
        tag = fields[0]
        nums = [int(x) for x in fields[1:]]
        if tag == 'entry' and state == 'waiting' and len(nums) == 3:
            start, prior31, priorwork = nums
            if start < 0 or prior31 not in (0, 1) or priorwork not in (0, 1):
                raise ValueError('入口不正')
            result.update(reached=True, prior_out31=bool(prior31), prior_e6c2=bool(priorwork))
            state = 'active'
        elif tag == 'intervention' and state == 'active' and nums == [1] and not result['interventions'] and not result['out'] and not writes:
            result['interventions'] = 1
        elif tag == 'out' and state == 'active' and len(nums) == 2 and all(0 <= x <= 255 for x in nums):
            result['out'].append(nums)
        elif tag == 'write' and state == 'active' and len(nums) == 1 and 0 <= nums[0] <= 65535:
            writes.append(nums[0])
        elif tag == 'exit' and state == 'active' and len(nums) == 6:
            finish, returned, sp, dma, span, escaped = nums
            if (finish < start or returned not in (0, 1) or escaped not in (0, 1) or (returned and not escaped) or
                    not 0 <= dma <= 65535 or not 0 <= span <= 65536 or
                    (returned and not 0 <= sp <= 65535) or (not returned and sp != -1)):
                raise ValueError('出口不正')
            result.update(returned=bool(returned), sp=sp if returned else None,
                          frames=finish-start, escaped=bool(escaped),
                          screen=[a for a in writes if ((a-dma) & 65535) < span])
            state = 'exited'
        elif tag == 'end' and state in ('waiting', 'exited') and len(nums) == 4:
            end, reached, count, invalid = nums
            if (end < finish or reached != int(result['reached']) or
                    count != result['interventions'] or invalid not in (0, 1)):
                raise ValueError('末尾不正')
            result.update(complete=True, error='書込み先がRAMでない' if invalid else None)
            state = 'done'
        else:
            raise ValueError('形式不正')
    if state != 'done':
        raise ValueError('記録切断')
    return result


def run_one(front, core, rom, disks, directory, frames, address=None, value=None, entry=0x7071, extra=()):
    directory = outside(directory)
    directory.mkdir()
    cmd = [str(front), '--core', str(core), '--rom-dir', str(rom),
           '--frames', str(frames), '--out', str(directory/'trace'),
           '--b92-log', str(directory/'events'), '--b92-entry', f'{entry:04X}',
           '--screen-signature-only', '--screen-signature-at', f'end:{frames-1}']
    # 書込みや差分ファイルが別腕へ伝わらないよう媒体も毎回複製する。
    for i, disk in enumerate(disks[:2]):
        dest = directory/f'G5-{i+1}.d88'
        shutil.copyfile(disk, dest)
        cmd += ['--disk' if i == 0 else '--disk2', str(dest)]
    if address is not None:
        cmd += ['--intervene-before-rom-entry', f'{entry:04X}:{address:04X}={value:02X}']
    cmd += list(extra)
    with (directory/'stdout').open('w') as stdout, (directory/'stderr').open('w') as stderr:
        rc = subprocess.run(cmd, stdout=stdout, stderr=stderr).returncode
    if rc:
        return empty_run('ハーネス実行失敗')
    try:
        return parse_log(directory/'events')
    except (ValueError, OSError):
        return empty_run('生記録の欠落または形式不正')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output', help='新規のリポジトリ外ディレクトリ')
    args = ap.parse_args()
    try:
        out = outside(args.output)
        if out.exists():
            raise ValueError('出力先は新規にする')
        rom = Path(os.environ['PC88_REF_ROM_DIR']).resolve()
        if not rom.is_dir() or not os.environ.get('PC88_GAME_DIR'):
            raise ValueError('ROMとG5の環境変数が必要')
        frames = int(os.environ.get('B92_FRAMES', '2010'))
        if not 1 <= frames <= 10000000:
            raise ValueError('フレーム数不正')
        front = Path(os.environ.get('PC88_FRONTEND', ROOT/'tools/harness/frontend/q88measure')).resolve()
        candidates = sorted((ROOT.parent/'vendor/quasi88-libretro').glob('quasi88_libretro.*'))
        core = (Path(os.environ['PC88_CORE']) if 'PC88_CORE' in os.environ else candidates[0]).resolve()
        if not core.is_file() or not front.is_file():
            raise ValueError('ハーネス不在')
        os.umask(0o077)
        out.mkdir(parents=True)
        raw = out/'raw'
        raw.mkdir()
        with (raw/'stage.stderr').open('w') as stderr:
            staged = subprocess.run([str(ROOT/'tools/stage_game.sh'), 'G5', str(raw/'media')],
                                    stdout=subprocess.PIPE, stderr=stderr, text=True, check=True)
        disks = [outside(p) for p in staged.stdout.splitlines()]
        if not disks:
            raise ValueError('G5の媒体なし')
        data = {'baseline': [], 'arms': []}
        for n in range(2):
            data['baseline'].append(run_one(front, core, rom, disks, raw/f'baseline-{n+1}', frames))
        for addr in ADDRESSES:
            for value in VALUES:
                result = run_one(front, core, rom, disks, raw/f'{addr:04X}-{value:02X}', frames, addr, value)
                data['arms'].append(dict(address=addr, input=value, run=result))
            # 番地と件数だけ。ゲーム名や生の値を出さない。
            print(f'B92: {addr:04X} の10腕を完了', flush=True)
        (raw/'runs.json').write_text(json.dumps(data))
        (out/'summary.json').write_text(json.dumps(summarize(data), ensure_ascii=False, indent=2)+'\n')
        print('B92: 全腕の実行と値なし集計を完了（欠測は集計内に明示）')
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        ap.exit(1, 'B92: 準備または集計に失敗（生ログはリポジトリ外）\n')


if __name__ == '__main__':
    main()
