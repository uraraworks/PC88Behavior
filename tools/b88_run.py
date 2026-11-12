#!/usr/bin/env python3
"""全130腕を各2走。公式ROMはコピーのみ、内容をPythonで読み取らない。"""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys

from b88_arms import arms
from b88_boot import write_arm, own_main, ROOT
from b88_build import build
from b88_summarize import summarize_run, report

RAW_FILES = ('mem', 'capture', 'stderr', 'probe.bin', 'probe.d88')


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def child_limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))


def run_one(directory, arm, core, front, own_sub, frames, timeout, fault=None):
    directory.mkdir(parents=True)
    romdir = directory / 'rom'
    romdir.mkdir()
    data, labels = write_arm(directory, arm, fault)
    ref = os.environ.get('PC88_REF_ROM_DIR')
    if ref:
        source = Path(ref)
        files = [p for p in source.iterdir() if p.is_file() and p.suffix.upper() == '.ROM']
        names = {p.name.upper() for p in files}
        if not {'N88.ROM', 'DISK.ROM'} <= names:
            raise ValueError('公式ROM一式が不足しています')
        for p in files:
            shutil.copyfile(p, romdir / p.name.upper())
    else:
        (romdir / 'N88.ROM').write_bytes(own_main(data))
        (romdir / 'DISK.ROM').write_bytes(own_sub)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('B88_', 'Q88MEASURE_FAULT_'))}
    env.update({'B88_CAPTURE': str(directory / 'capture'),
                'B88_START': f"{labels['sub']['start'] + 3:x}",
                'B88_RETURN': f"{labels['sub']['returned']:x}",
                'B88_BOOT': f"{labels['main']['BOOT']:x}",
                'B88_DONE': f"{labels['main']['DONE']:x}",
                'B88_FAIL': f"{labels['main']['FAIL']:x}",
                'B88_RECEIVE': f"{labels['main']['RECEIVE_RESULT'] + 3:x}"})
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


def clean_run(directory):
    for name in RAW_FILES:
        (directory / name).unlink(missing_ok=True)
    shutil.rmtree(directory / 'rom', ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if out == ROOT or ROOT in out.parents or out.exists():
        parser.error('出力先にはリポジトリ外の未使用ディレクトリを指定してください')
    os.umask(0o077)
    out.mkdir(parents=True)
    selected = [a for a in arms() if re.search(os.environ.get('B88_FILTER', ''), a['name'])]
    if not selected: parser.error('実行する腕がありません')
    frames = int(os.environ.get('B88_FRAMES', '2010' if os.environ.get('PC88_REF_ROM_DIR') else '120'))
    timeout = int(os.environ.get('B88_TIMEOUT', '120'))
    if not 1 <= frames <= 10000 or not 1 <= timeout <= 600:
        parser.error('フレーム数または時間上限が範囲外です')
    dump(out / 'manifest.json', {'方式': '公式' if os.environ.get('PC88_REF_ROM_DIR') else '自作',
                                 '腕': [a['name'] for a in selected], '反復': 2, 'フレーム上限': frames})
    try:
        core, front = build(out)
        own_sub = None
        if not os.environ.get('PC88_REF_ROM_DIR'):
            sys.path.insert(0, str(ROOT))
            from src.l3_service.make_subrom import build as build_sub
            own_sub = build_sub()[0]
        for index, arm in enumerate(selected):
            for repeat in (1, 2):
                directory = out / 'raw' / arm['name'] / str(repeat)
                try:
                    run_one(directory, arm, core, front, own_sub, frames, timeout)
                    row, values = summarize_run(directory, arm)
                    dump(directory / 'row.json', row)
                    dump(directory / 'values.tmp', values)
                finally:
                    clean_run(directory)
            if (index + 1) % 10 == 0 or index + 1 == len(selected):
                print(f'B88: {index+1}/{len(selected)}腕（各2走）', flush=True)
        result = report(out)
        # 再集計用にも残すのは値なしの関係だけ。
        for name, row in result['腕'].items():
            p = out / 'raw' / name
            if p.exists(): dump(p / 'comparison.json', row['基準腕との一致'])
        print('B88: 値なし集計を作成', flush=True)
    finally:
        for path in (out / 'raw').glob('*/*/values.tmp'): path.unlink()
        for path in (out / 'raw').glob('*/*'):
            if path.is_dir(): clean_run(path)
        shutil.rmtree(out / 'build', ignore_errors=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError):
        print('B88: 実行に失敗しました。OUT内の状態・ビルド記録を確認してください', file=sys.stderr)
        sys.exit(1)
