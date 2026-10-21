#!/usr/bin/env python3
"""自作媒体だけで、論理保護・D88保護と書き込み復帰を実Z80で検査する。

根拠: l4-basic 第15・24節、l3-disk-format 第3・4節。
D88ヘッダの公開形式: https://boukichi.github.io/HuDisk/DISK.html
画面本文・公式ROM・公式媒体・凍結期待値は入力にも出力にも使わない。
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'tools'), str(REPO / 'src')]
import build_blank_data_disk as blank
import memmap

MARK = memmap.addresses()['MM_EXT_BANK_ST_VAL0']
MEDIA = [('logical', True, False), ('header', False, True),
         ('both', True, True), ('none', False, False)]
OPS = {
    'open-default': 'open "f1own" for output as #1:close #1',
    'open-explicit': 'open "1:f" for output as #1:close #1',
    'print': 'open "1:f" for output as #1:print #1,"wp":close #1',
    'close': 'open "1:f" for output as #1:close #1',
    'save': 'save "1:wp",a',
    'kill': 'kill "1:f"',
}


def sector(image, c, h, r):
    pos = struct.unpack_from('<I', image, 32 + (c * 2 + h) * 4)[0]
    count = struct.unpack_from('<H', image, pos + 4)[0]
    for _ in range(count):
        if tuple(image[pos:pos + 3]) == (c, h, r):
            return pos + 16
        pos += 16 + struct.unpack_from('<H', image, pos + 14)[0]
    raise ValueError('自作媒体のセクタ欠落')


def medium(logical, header):
    image = bytearray(blank.build())
    # 名前fの空ファイル。16Bのエントリ、単位72、終端C0は公開規則から作る。
    pos = sector(image, 18, 1, 1)
    image[pos:pos + 16] = b'f        ' + bytes([0, 72]) + b'\xff' * 5
    for r in (14, 15, 16):
        image[sector(image, 18, 1, r) + 72] = 0xc0
    if logical:
        pos = sector(image, 18, 1, 13)
        image[pos:pos + 256] = b'\x10' * 256
    image[0x1a] = 0x10 if header else 0
    return bytes(image)


def run_case(rom, work, core, logical, header, operation, *, swapped=False):
    work.mkdir(parents=True, exist_ok=True)
    image = medium(logical, header)
    disk = work / 'disk.d88'
    disk.write_bytes(image)
    command = OPS[operation]
    frames, start = (18000, 13000) if swapped else (6500, 3000)
    if swapped:
        # 開いてから保護媒体へ交換。PRINTは既存255文字に1文字足して実WRITEを強制。
        command = 'print #1,"b";' if operation == 'print' else 'close #1'
    program = (f'10 on error goto 100\n20 poke {MARK},1:{command}\n'
               f'30 poke {MARK},2:stop\n'
               f'100 poke {MARK + 1},err:poke {MARK},3:resume 200\n200 stop\n')
    args = ['nice', '-n', '10', str(REPO / 'tools/harness/frontend/q88measure'),
            '--core', str(core), '--rom-dir', str(rom), '--disk', str(disk),
            '--save-to-disk-image', '--frames', str(frames),
            '--screen-signature-only', '--screen-signature-at', f'final:{frames}',
            '--out', str(work / 'signature.tsv'), '--mem-write-log', str(work / 'mem.log'),
            '--mem-write-range', f'{MARK:04x}-{MARK + 1:04x}',
            '--io-log', str(work / 'late-io.log'), '--io-log-from-frame', str(frames - 5),
            '--key-hold', '2', '--key-gap', '2', '--type-at', '100',
            '--type', program.replace('\n', '\\n')]
    if swapped:
        initial = work / 'initial.d88'
        initial.write_bytes(medium(False, False))
        args[args.index('--disk') + 1] = str(initial)
        setup = 'open "1:f" for output as #1:print #1,'
        setup += 'string$(255,65);' if operation == 'print' else '"a";'
        args += ['--type-at', '1900', '--type', setup + '\\n',
                 '--swap-disk1', str(disk), '--swap-disk1-at', '12000']
    args += ['--type-at', str(start), '--type', 'goto 10\\n']
    env = {k: v for k, v in os.environ.items() if not k.startswith('PC88_REF_')}
    with (work / 'stdout.log').open('w') as out, (work / 'stderr.log').open('w') as err:
        rc = subprocess.run(args, cwd=work, env=env, stdout=out, stderr=err,
                            timeout=120).returncode
    if rc:
        raise RuntimeError(f'エミュレータ実行失敗 rc={rc}')
    log = (work / 'mem.log').read_text()
    dropped = re.search(r'^# 取りこぼし: (\d+)件', log, re.M)
    if dropped is None or int(dropped[1]):
        raise RuntimeError('完了印の記録に取りこぼし')
    values = {}
    for line in log.splitlines():
        m = re.match(r'\s*\d+\s+\d+\s+[0-9a-fA-F]{4}\s+([0-9a-fA-F]{4})\s+([0-9a-fA-F]{2})', line)
        if m:
            values[int(m[1], 16)] = int(m[2], 16)
    # 遅い区間のPCだけをまとめる。ポートの値列や画面本文は報告しない。
    pcs = {}
    for line in (work / 'late-io.log').read_text().splitlines():
        fields = line.split()
        if len(fields) == 8 and fields[0].isdigit():
            key = fields[3] + ':' + fields[7]
            pcs[key] = pcs.get(key, 0) + 1
    result = dict(operation=operation, swapped=swapped, state=values.get(MARK, 0),
                  error=values.get(MARK + 1, 0), unchanged=disk.read_bytes() == image,
                  late_pc=pcs)
    (work / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def negative_rom(good, bad):
    shutil.copytree(good, bad, dirs_exist_ok=True)
    path = bad / 'N88_2.ROM'
    image = bytearray(path.read_bytes())
    guard = bytes.fromhex('cb 77 28 04 3e 3d 37 c9')
    if image.count(guard) != 1:
        raise RuntimeError('保護分岐の故障注入点が一意でない')
    pos = image.index(guard)
    image[pos:pos + len(guard)] = bytes(len(guard))
    path.write_bytes(image)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work-dir', type=Path,
                    default=REPO / 'tmp/f1-wp-impl-work/selftest')
    ap.add_argument('--rom-dir', type=Path)
    ap.add_argument('--observe', action='store_true', help='修正前の結果も判定を隠さず記録する')
    ap.add_argument('--skip-negative', action='store_true')
    args = ap.parse_args()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    core = next((REPO.parent / 'vendor/quasi88-libretro').glob('quasi88_libretro.*'))
    rom = args.rom_dir.resolve() if args.rom_dir else work / 'rom'
    if not args.rom_dir:
        with (work / 'build.log').open('w') as log:
            subprocess.run([sys.executable, str(REPO / 'src/build_main_rom.py'), str(rom),
                            '--work-dir', str(work / 'asm')], check=True, stdout=log, stderr=log)
    results = []
    for tag, logical, header in MEDIA:
        for operation in OPS:
            result = run_case(rom, work / tag / operation, core, logical, header, operation)
            protected = logical or header
            passed = ((result['state'], result['error']) == ((3, 61) if protected else (2, 0)))
            passed &= result['unchanged'] if protected else not result['unchanged']
            result.update(media=tag, passed=passed)
            results.append(result)
            print(f'{tag}/{operation}: ' + ('OK' if passed else 'NG') +
                  f" state={result['state']} err={result['error']} unchanged={result['unchanged']}", flush=True)
    for operation in ('print', 'close'):
        result = run_case(rom, work / 'swapped-header' / operation, core,
                          False, True, operation, swapped=True)
        result.update(media='swapped-header', passed=(result['state'], result['error']) == (3, 61)
                      and result['unchanged'])
        results.append(result)
        print(f'交換後header/{operation}: ' + ('OK' if result['passed'] else 'NG'), flush=True)
    if not args.skip_negative:
        bad = work / 'negative-rom'
        negative_rom(rom, bad)
        result = run_case(bad, work / 'negative' / 'open-default', core,
                          False, True, 'open-default')
        result.update(media='negative-header', passed=result['state'] == 1 and result['error'] == 0
                      and result['unchanged'])
        results.append(result)
        print('陰性対照（保護分岐なし、開始後に未完了）: ' + ('OK' if result['passed'] else 'NG'), flush=True)
    (work / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    return 0 if args.observe or all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'NG: {exc}', file=sys.stderr)
        sys.exit(1)
