#!/usr/bin/env python3
"""G5 の基準2回と R 介入9腕を独立起動し、値なし集計を作る。"""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from b92_run import ROOT
from b92_summary import outside
from b93_summary import VALUES, collect


def run_one(front, core, rom, disks, directory, frames, value=None, entry=0x7071, extra=()):
    d = outside(directory)
    d.mkdir()
    cmd = [str(front), '--core', str(core), '--rom-dir', str(rom), '--frames', str(frames),
           '--out', str(d/'trace'), '--b93-log', str(d/'events'), '--b93-entry', f'{entry:04X}',
           '--boundary-timeline', str(d/'timeline'), '--boundary-timeline-limit', '1000000000',
           '--screen-signature-only', '--screen-signature-at', f'end:{frames-1}']
    for i, src in enumerate(disks[:2]):
        dst = d/f'disk{i}.d88'
        shutil.copyfile(src, dst)
        cmd += ['--disk' if i == 0 else '--disk2', str(dst)]
    if value is not None:
        cmd += ['--intervene-r-after-rom-return', f'{entry:04X}={value:02X}']
    cmd += list(extra)
    with (d/'stdout').open('w') as out, (d/'stderr').open('w') as err:
        rc = subprocess.run(cmd, stdout=out, stderr=err).returncode
    (d/'status').write_text(f'{rc}\n')
    return rc


def main():
    if len(sys.argv) != 2:
        raise ValueError('出力先を指定')
    out = outside(sys.argv[1])
    if out.exists():
        raise ValueError('出力先は新規にする')
    rom = Path(os.environ['PC88_REF_ROM_DIR']).resolve()
    core = Path(os.environ['PC88_CORE']).resolve()
    front = Path(os.environ.get('PC88_FRONTEND', ROOT/'tools/harness/frontend/q88measure')).resolve()
    frames = int(os.environ.get('B93_FRAMES', '36000'))
    if (not os.environ.get('PC88_GAME_DIR') or not rom.is_dir() or not core.is_file() or
            not front.is_file() or not 1 <= frames <= 10000000 or os.environ.get('Q88MEASURE_FAULT_BOUNDARY')):
        raise ValueError('実行設定不正')
    library = ctypes.CDLL(str(core))
    if library.retro_q88h_b93_version() != 2:
        raise ValueError('B93パッチ未適用')
    os.umask(0o077)
    out.mkdir(parents=True)
    (out/'config.json').write_text(json.dumps({'format': 2, 'frames': frames})+'\n')
    raw = out/'raw'
    raw.mkdir()
    with (raw/'stage.stderr').open('w') as err:
        staged = subprocess.run([str(ROOT/'tools/stage_game.sh'), 'G5', str(raw/'media')],
                                stdout=subprocess.PIPE, stderr=err, text=True, check=True)
    disks = [outside(p) for p in staged.stdout.splitlines()]
    if not 1 <= len(disks) <= 2 or not all(p.is_file() for p in disks):
        raise ValueError('媒体不正')
    for name, value in [('base1', None), ('base2', None)] + [(v, int(v, 16)) for v in VALUES]:
        rc = run_one(front, core, rom, disks, raw/name, frames, value)
        print(f'B93: {name} ' + ('実行完了' if rc == 0 else '実行失敗（欠測）'), flush=True)
    summary = collect(raw, frames)
    (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print('B93: 全11腕と値なし集計を完了（欠測は集計内に明示）')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, AttributeError, subprocess.SubprocessError):
        sys.exit('B93: 準備または実行に失敗（詳細は外部記録）')
