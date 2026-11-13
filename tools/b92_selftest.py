#!/usr/bin/env python3
"""自作ROM・自作起動セクタによるB92の結合検査（公式データ不要）。"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from b2_make_boot_probe import build_disk
from b92_run import ROOT, VALUES, empty_run, parse_log, run_one
from b92_summary import summarize


def fixture(work):
    romdir = work/'rom'
    romdir.mkdir()
    sector = bytearray()
    patches, labels = [], {}

    def emit(code):
        sector.extend(bytes.fromhex(code))

    def ref(op, name):
        emit(op)
        patches.append((len(sector), name))
        sector.extend(b'\0\0')

    emit('f3 31 00 b0 3e 00 d3 31')
    # ROM側初期値をRAMが上書きしてからJP。早過ぎる介入なら陽性は失敗する。
    emit('3e ad 32 c2 e6 32 0e e6')
    ref('21', 'first_return')
    emit('e5 c3 00 10')
    labels['first_return'] = 0x9000 + len(sector)
    emit('3a c2 e6 32 00 a0')
    # 同じ入口へもう一度入り、二度目には書き換わらないことを確認する。
    emit('3e ad 32 c2 e6')
    ref('21', 'second_return')
    emit('e5 c3 00 10')
    labels['second_return'] = 0x9000 + len(sector)
    emit('3a c2 e6 32 01 a0 f3 76 18 fd')
    for offset, label in patches:
        sector[offset:offset+2] = labels[label].to_bytes(2, 'little')
    sector += bytes(256-len(sector))
    (work/'boot.bin').write_bytes(sector)
    media = work/'games'
    media.mkdir()
    # 名前が出力へ漏れないことも確認するための自作名。
    disk = build_disk(bytes(sector), 'none')
    (media/'B92_SYNTHETIC_PRIVATE_NAME.d88').write_bytes(disk)
    digest = hashlib.sha256(disk).hexdigest()[:16]
    (media/'games.tsv').write_text(f'G5\t1\t{digest}\n')
    rom = bytearray(0x8000)
    rom[:3] = bytes.fromhex('c3 00 01')
    # 自作ローダが起動セクタ像をRAMへ置く。FDCの自己検査ではない。
    boot = bytes.fromhex(
        'f3 31 00 b0 3e 00 d3 31 '
        '3e 00 d3 51 3e 4e d3 50 3e 18 d3 50 3e 07 d3 50 '
        '3e 00 d3 50 3e 13 d3 50 '
        '3e 80 d3 68 3e 00 d3 64 3e f3 d3 64 '
        '3e ad 32 c2 e6 32 0e e6 cd 00 10 '
        '21 00 03 11 00 90 01 00 01 ed b0 c3 00 90')
    rom[0x100:0x100+len(boot)] = boot
    # D88に載せた同一のセクタをROMの自作ローダへ埋め込む。
    offset = int.from_bytes(disk[32:36], 'little') + 16
    assert disk[offset:offset+256] == sector
    rom[0x300:0x400] = disk[offset:offset+256]
    routine = bytes.fromhex('3a c2 e6 d3 7e 32 00 f3 3a 0e e6 d3 7d 32 01 f3 c9')
    rom[0x1000:0x1000+len(routine)] = routine
    (romdir/'N88.ROM').write_bytes(rom)
    (romdir/'DISK.ROM').write_bytes(bytes.fromhex('18 fe') + bytes(0x7fe))
    return romdir, media


def main():
    work, core = map(Path, sys.argv[1:])
    front = ROOT/'tools/harness/frontend/q88measure'
    rom, media = fixture(work)
    env = dict(os.environ, PC88_GAME_DIR=str(media))
    staged = subprocess.run([str(ROOT/'tools/stage_game.sh'), 'G5', str(work/'staged')],
                            env=env, capture_output=True, text=True, check=True)
    assert 'B92_SYNTHETIC_PRIVATE_NAME' not in staged.stdout + staged.stderr
    disks = [Path(x) for x in staged.stdout.splitlines()]
    data = dict(baseline=[], arms=[])
    for i in range(2):
        data['baseline'].append(run_one(front, core, rom, disks, work/f'base{i}', 2, entry=0x1000))
    for addr in (0xE6C2, 0xE700):
        for value in VALUES:
            directory = work/f'{addr:04X}-{value:02X}'
            extra = ('--mem-write-log', str(directory/'markers'), '--mem-write-range', 'A000-A001')
            run = run_one(front, core, rom, disks, directory, 2, addr, value, 0x1000, extra)
            assert run['complete'] and run['reached'] and run['returned'], '自作入口の区間採取失敗'
            assert run['interventions'] == 1 and run['prior_out31'] and run['prior_e6c2']
            assert run['sp'] == 0xB000 and run['frames'] == 0
            assert run['out'] == [[0x7E, value if addr == 0xE6C2 else 173], [0x7D, 173]]
            assert run['screen'] == [0xF300, 0xF301], 'テキスト書込み範囲の検査失敗'
            markers = []
            for line in (directory/'markers').read_text().splitlines():
                m = re.fullmatch(r'\s*\d+\s+\d+\s+([0-9A-F]{4})\s+(A00[01])\s+([0-9A-F]{2})\s*', line)
                if m:
                    markers.append((int(m[2], 16), int(m[3], 16)))
            assert markers == [(0xA000, value if addr == 0xE6C2 else 173), (0xA001, 173)], '一回限りの介入検査失敗'
            data['arms'].append(dict(address=addr, input=value, run=run))
    report = summarize(data)
    assert report['基準安定']
    assert all(x['OUT値一致'] == [True, True] and x['画面件数変化'] == 0 and not x['画面範囲変化']
               for x in report['腕']['E700'].values())
    assert all({k: v for k, v in arm['run'].items() if k != 'interventions'} ==
               {k: v for k, v in data['baseline'][0].items() if k != 'interventions'}
               for arm in data['arms'] if arm['address'] == 0xE700)
    assert all(x['OUT値一致'] == [False, True] for x in report['腕']['E6C2'].values())
    assert 'そのまま' in report['関係']['E6C2'][0]
    assert '定数（値はリポジトリ外）' in report['関係']['E700'][0]
    public = json.dumps(report, ensure_ascii=False)

    def detects_leak(text):
        return bool(re.search(r'(?<![0-9A-Za-z])(?:173|0x[Aa][Dd]|AD)(?![0-9A-Za-z])', text))

    assert not detects_leak(public)
    assert detects_leak(public + '\n173')  # 漏洩検出そのものの陽性対照
    # 未到達、記録切断、基準不一致を「変化なし」にしてしまわない。
    missing = run_one(front, core, rom, disks, work/'missing', 2, 0xE6C2, 1, 0x2000)
    assert missing['complete'] and not missing['reached'] and missing['interventions'] == 0
    broken = work/'truncated'
    broken.write_text((work/'base0/events').read_text().rsplit('end ', 1)[0])
    try:
        parse_log(broken)
        raise AssertionError('切断を検出しなかった')
    except ValueError:
        pass
    changed = copy.deepcopy(data)
    changed['baseline'][1]['out'][0][1] ^= 1
    assert not summarize(changed)['基準安定'] and summarize(changed)['関係']['E6C2'] is None
    changed = copy.deepcopy(data)
    changed['arms'][0]['run'] = empty_run('生記録の欠落または形式不正')
    assert summarize(changed)['関係']['E6C2'] is None
    # frontend の書式・重複・外部出力制約。エラー出力は画面へ流さない。
    dangling = work/'dangling'
    dangling.symlink_to(ROOT/'b92-forbidden')
    repo_link = work/'repo-link'
    repo_link.symlink_to(ROOT, target_is_directory=True)
    for extra in [
        ['--intervene-before-rom-entry', '1000:E6C2=100'],
        ['--intervene-before-rom-entry', '1000:E6C2=01junk'],
        ['--intervene-before-rom-entry', '1000:E6C2=01', '--intervene-before-rom-entry', '1000:E700=02'],
        ['--b92-log', str(ROOT/'tmp/b92-forbidden')],
        ['--b92-log', str(ROOT/'b92-forbidden')],
        ['--b92-log', str(dangling)],
        ['--b92-log', str(repo_link/'b92-forbidden')],
    ]:
        cmd = [str(front), '--core', str(core), '--rom-dir', str(rom), '--frames', '1'] + extra
        if '--b92-log' not in extra:
            cmd += ['--b92-log', str(work/'option-events')]
        assert subprocess.run(cmd, capture_output=True).returncode != 0
    (work/'summary.json').write_text(public)
    print('B92 結合検査: 自作ROM・起動セクタ、陽性10腕・陰性10腕・一回限り・値漏洩なし PASS')


if __name__ == '__main__':
    main()
