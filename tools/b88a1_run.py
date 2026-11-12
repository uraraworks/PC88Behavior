#!/usr/bin/env python3
"""B88 追補1の628腕を独立ROM置き場で各2走し、値なし集計まで行う。"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from b88a1_arms import arms, inputs
from b88_boot import ROOT, write_arm, own_main
from b88_build import build
from b88_run import dump, child_limits, clean_run as base_clean
from b88a1_summarize import summarize_run, report


def clean_run(directory):
    base_clean(directory)
    (directory / 'extra').unlink(missing_ok=True)


def run_one(directory, arm, core, front, own_sub, frames, timeout, fault=None, fixture=None):
    directory.mkdir(parents=True)
    romdir = directory / 'rom'
    romdir.mkdir()
    data, labels = write_arm(directory, arm, fault)
    ref = os.environ.get('PC88_REF_ROM_DIR')
    if ref:
        if fault or fixture:
            raise ValueError('故障注入は自作ROM専用です')
        files = [p for p in Path(ref).iterdir() if p.is_file() and p.suffix.upper() == '.ROM']
        if not {'N88.ROM', 'DISK.ROM'} <= {p.name.upper() for p in files}:
            raise ValueError('公式ROM一式が不足しています')
        for p in files:
            shutil.copyfile(p, romdir / p.name.upper())
    else:
        sub = bytearray(own_sub)
        if fixture:
            # 自作検査ルーチンの差し替え。公式ROMには適用できない。
            for address, code in fixture.items():
                sub[address:address + len(code)] = code
        (romdir / 'N88.ROM').write_bytes(own_main(data))
        (romdir / 'DISK.ROM').write_bytes(sub)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('B88_', 'B88A1_', 'Q88MEASURE_FAULT_'))}
    env.update({'B88_CAPTURE': str(directory / 'capture'),
                'B88_START': f"{labels['sub']['start'] + 3:x}",
                'B88_RETURN': f"{labels['sub']['returned']:x}",
                'B88_BOOT': f"{labels['main']['BOOT']:x}",
                'B88_DONE': f"{labels['main']['DONE']:x}",
                'B88_FAIL': f"{labels['main']['FAIL']:x}",
                'B88_RECEIVE': f"{labels['main']['RECEIVE_RESULT'] + 3:x}",
                'B88A1_CAPTURE': str(directory / 'extra'),
                'B88A1_MEDIA': str(directory / 'probe.d88'),
                'B88A1_DISK1': str(int(arm.get('disk1', True))),
                'B88A1_DISK2': str(int(arm.get('disk2', False))),
                'B88A1_PREPARE': f"{labels['sub']['prepare']:x}",
                'B88A1_PREPARED': f"{labels['sub']['prepared']:x}",
                'B88A1_INPUT_HL': f"{inputs(arm)['HL']:x}",
                'B88A1_COOP_SENT': f"{labels['main'].get('COOP_SENT', 0xffff):x}",
                'B88A1_COOP_BYTE': f"{labels['main'].get('COOP_BYTE', 0xffff):x}"})
    cmd = [str(front), '--core', str(core), '--rom-dir', str(romdir),
           '--disk', str(directory / 'probe.d88'), '--frames', str(frames),
           '--sub-cpu-mode', '2', '--mem-write-log', str(directory / 'mem'),
           '--mem-write-range', 'CF00-CFFF']
    ok = False
    try:
        with (directory / 'stderr').open('w') as err:
            result = subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=err,
                                    timeout=timeout, preexec_fn=child_limits)
        ok = result.returncode == 0
    except subprocess.TimeoutExpired:
        pass
    dump(directory / 'status.json', {'成功': ok})
    return labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if out == ROOT or ROOT in out.parents or out.exists():
        parser.error('出力先にはリポジトリ外の未使用ディレクトリを指定してください')
    selected = [a for a in arms() if re.search(os.environ.get('B88A1_FILTER', ''), a['name'])]
    if not selected:
        parser.error('実行する腕がありません')
    frames = int(os.environ.get('B88A1_FRAMES', '2010' if os.environ.get('PC88_REF_ROM_DIR') else '120'))
    timeout = int(os.environ.get('B88A1_TIMEOUT', '120'))
    if not 1 <= frames <= 10000 or not 1 <= timeout <= 600:
        parser.error('フレーム数または時間上限が範囲外です')
    os.umask(0o077)
    out.mkdir(parents=True)
    dump(out / 'manifest.json', {'方式': '公式' if os.environ.get('PC88_REF_ROM_DIR') else '自作',
         '腕': [a['name'] for a in selected], '反復': 2, 'フレーム上限': frames,
         '実時間上限': timeout})
    try:
        core, front = build(out, supplement=True)
        sub = None
        if not os.environ.get('PC88_REF_ROM_DIR'):
            sys.path.insert(0, str(ROOT))
            from src.l3_service.make_subrom import build as build_sub
            sub = build_sub()[0]
        for index, arm in enumerate(selected, 1):
            for repeat in (1, 2):
                directory = out / 'raw' / arm['name'] / str(repeat)
                try:
                    run_one(directory, arm, core, front, sub, frames, timeout)
                    row, values = summarize_run(directory, arm)
                    dump(directory / 'row.json', row)
                    dump(directory / 'values.tmp', values)
                finally:
                    clean_run(directory)
            if index % 20 == 0 or index == len(selected):
                print(f'B88追補1: {index}/{len(selected)}腕（各2走）', flush=True)
        report(out)
        print('B88追補1: summary.json に値なし集計を作成', flush=True)
    finally:
        for path in (out / 'raw').glob('*/*/values.tmp'):
            path.unlink()
        for path in (out / 'raw').glob('*/*'):
            if path.is_dir():
                clean_run(path)
        shutil.rmtree(out / 'build', ignore_errors=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError):
        print('B88追補1: 実行失敗。出力先の状態・ビルド記録を確認してください', file=sys.stderr)
        sys.exit(1)
