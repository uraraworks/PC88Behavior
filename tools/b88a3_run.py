#!/usr/bin/env python3
"""B88 追補3の全腕を独立ROM置き場で各2走し、値なし集計まで行う。"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from b88a3_arms import arms
from b88a3_arms import inputs
from b88a3_boot import ROOT, write_arm, own_main
from b88a3_build import build
from b88_run import dump, child_limits, clean_run as base_clean
from b88a3_summarize import summarize_run, report


def clean_run(directory):
    base_clean(directory)
    (directory / 'extra').unlink(missing_ok=True)
    (directory / 'media.d88').unlink(missing_ok=True)
    (directory / 'media2.d88').unlink(missing_ok=True)
    (directory / 'fixture.bin').unlink(missing_ok=True)


def run_one(directory, arm, core, front, own_sub, frames, timeout, fault=None, fixture=None, test_iff2=None):
    directory.mkdir(parents=True)
    romdir = directory / 'rom'
    romdir.mkdir()
    data, labels = write_arm(directory, arm, fault)
    ref = os.environ.get('PC88_REF_ROM_DIR')
    if ref:
        if fault or fixture or test_iff2 is not None:
            raise ValueError('故障注入は自作ROM専用です')
        files = [p for p in Path(ref).iterdir() if p.is_file() and p.suffix.upper() == '.ROM']
        if not {'N88.ROM', 'DISK.ROM'} <= {p.name.upper() for p in files}:
            raise ValueError('公式ROM一式が不足しています')
        for p in files:
            shutil.copyfile(p, romdir / p.name.upper())
    else:
        sub = bytearray(own_sub)
        if fixture:
            # ブートが終わった境界でのみ自作の対照コードを配置する。
            patch = bytearray()
            for address, code in fixture.items():
                if not 0 <= address < address + len(code) <= len(sub):
                    raise ValueError('対照コード範囲不正')
                patch += address.to_bytes(2, 'little') + len(code).to_bytes(2, 'little') + code
            (directory / 'fixture.bin').write_bytes(patch)
        (romdir / 'N88.ROM').write_bytes(own_main(data))
        (romdir / 'DISK.ROM').write_bytes(sub)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('B88_', 'B88A1_', 'B88A2_', 'B88A3_', 'Q88MEASURE_FAULT_'))}
    env.update({'B88_CAPTURE': str(directory / 'capture'),
                'B88_START': f"{labels['sub']['invoke']:x}",
                'B88_RETURN': f"{labels['sub']['returned']:x}",
                'B88_BOOT': f"{labels['main']['BOOT']:x}",
                'B88_DONE': f"{labels['main']['DONE']:x}",
                'B88_FAIL': f"{labels['main']['FAIL']:x}",
                'B88_RECEIVE': f"{labels['main']['RECEIVE_RESULT'] + 3:x}",
                'B88A3_TARGET': f"{arm['address'] if arm['address'] is not None else labels['sub']['negative' if arm['name'] == 'negative' else 'positive']:x}",
                'B88A3_READ': str(int(arm['kind'] == 'result')),
                'B88A3_SENT': ','.join(str(v) for v in arm.get('sent', ())),
                'B88A3_STEPS': ','.join(f"{labels['sub'][f'step_{i}']:x}:{labels['sub'][f'step_done_{i}']:x}" for i in range(9)) if arm['kind'] == 'result' else '',
                'B88A3_CAPTURE': str(directory / 'extra'),
                'B88A3_MEDIA': str(directory / 'media.d88'),
                'B88A3_MEDIA2': str(directory / 'media2.d88'),
                'B88A3_DISK1': str(int(arm.get('disk1', True))),
                'B88A3_DISK2': str(int(arm.get('disk2', False))),
                'B88A3_PREPARE': f"{labels['sub']['prepare']:x}",
                'B88A3_PREPARED': f"{labels['sub']['prepared']:x}",
                'B88A3_INPUT_HL': f"{inputs(arm)['HL']:x}",
                'B88A3_COOP_SENT': f"{labels['main'].get('COOP_SENT', 0xffff):x}",
                'B88A3_MEDIA_PC': f"{labels['main']['MEDIA_READY']:x}",
                'B88A3_LANDING': f"{labels['sub']['landing']:x}",
                'B88A3_PREREAD': f"{labels['main'].get('PRE_READ_DONE', 0xffff):x}",
                'B88A3_COOP_PAIR': f"{labels['main']['COOP_PAIR_SENT']:x}",
                'B88A3_COOP_BYTE2': f"{labels['main'].get('COOP_BYTE2', 0xffff):x}",
                'B88A3_REPLY_DONE': f"{labels['main']['COOP_REPLY_DONE']:x}",
                'B88A3_COOP_BYTE': f"{labels['main'].get('COOP_BYTE', 0xffff):x}"})
    if test_iff2 is not None:
        if test_iff2 not in (0, 1): raise ValueError('IFF2対照不正')
        env['B88A3_TEST_IFF2'] = str(test_iff2)
    if fixture:
        env['B88A3_FIXTURE'] = str(directory / 'fixture.bin')
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
    selected = [a for a in arms() if re.search(os.environ.get('B88A3_FILTER', ''), a['name'])]
    if not selected:
        parser.error('実行する腕がありません')
    frames = int(os.environ.get('B88A3_FRAMES', '2010' if os.environ.get('PC88_REF_ROM_DIR') else '120'))
    timeout = int(os.environ.get('B88A3_TIMEOUT', '120'))
    if not 1 <= frames <= 10000 or not 1 <= timeout <= 600:
        parser.error('フレーム数または時間上限が範囲外です')
    os.umask(0o077)
    out.mkdir(parents=True)
    dump(out / 'manifest.json', {'方式': '公式' if os.environ.get('PC88_REF_ROM_DIR') else '自作',
         '腕': [a['name'] for a in selected], '反復': 2, 'フレーム上限': frames,
         '実時間上限': timeout})
    try:
        core, front = build(out)
        sub = None
        if not os.environ.get('PC88_REF_ROM_DIR'):
            from b88a3_fixture import build as build_sub
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
                print(f'B88追補3: {index}/{len(selected)}腕（各2走）', flush=True)
        report(out)
        print('B88追補3: summary.json に値なし集計を作成', flush=True)
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
        print('B88追補3: 実行失敗。出力先の状態・ビルド記録を確認してください', file=sys.stderr)
        sys.exit(1)
