#!/usr/bin/env python3
"""m6f-h の媒体・打鍵・予測表の凍結値を生成する。既存表は上書きしない。"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

import m6fh_script as script

HERE = Path(__file__).resolve().parent
SINGLETONS = {'frozen': 'yes', 'repetitions': '2', 'reference_disk': 'N88_FE.D88',
              'run_timeout_seconds': '600', 'boot_return_frame': str(script.BOOT_FRAME),
              'stimulus_frame': str(script.STIMULUS_FRAME)}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def media_sha() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / 'blank.d88'
        subprocess.run([sys.executable, str(HERE/'make_m6fc_blank_disk.py'), str(target),
                        '--fat-value', '0xFF', '--filler', '0xFF', '--sector-fill', '18,1,13=0x00'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return sha(target.read_bytes())


def lines() -> list[str]:
    out = [f'{k}\t{v}' for k,v in SINGLETONS.items()]
    out += [f'media_sha256\t{media_sha()}', f'prediction_sha256\t{script.prediction_digest()}']
    for arm in script.ARMS:
        out += [f'arm\t{arm}', f'frames\t{arm}:{script.FRAMES[arm]}',
                f'keystroke_sha256\t{arm}:{sha(script.keystrokes(arm).encode("ascii"))}']
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=HERE/'m6fh_frozen.tsv')
    args = p.parse_args()
    try:
        with args.out.open('x', encoding='ascii') as f:
            f.write('\n'.join(lines())+'\n')
    except (OSError, subprocess.CalledProcessError):
        print('凍結表作成失敗', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
