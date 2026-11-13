#!/usr/bin/env python3
"""公式データ不要。自作ROM・起動セクタによる B93 結合自己検査。"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from b92_selftest import fixture
from b2_make_boot_probe import build_disk
from b93_run import ROOT, run_one
from b93_summary import VALUES, collect, difference, io_headers, read_run, summarize


def main():
    core = Path(sys.argv[1]).resolve()
    front = Path(os.environ.get('PC88_FRONTEND', ROOT/'tools/harness/frontend/q88measure')).resolve()
    with tempfile.TemporaryDirectory(prefix='b93-fixture-') as tmp:
        work = Path(tmp)
        rom, media = fixture(work)
        p = rom/'N88.ROM'
        data = bytearray(p.read_bytes())
        # 二度呼ぶ。同じ戻り条件でも R 介入は初回だけ。
        sector = bytearray(bytes.fromhex(
            'f3 31 00 b0 3e 00 d3 31 '
            'cd 71 70 ed 5f d3 7f '
            'cd 71 70 ed 5f d3 7e c3 0d 3e'))
        sector += bytes(0xa0-len(sector))
        sector += bytes.fromhex('3e 55 d3 7c c9')
        sector += bytes(256-len(sector))
        data[0x300:0x400] = sector
        # RAM の寄り道後、R を既知値にして帰る。入口で介入する誤実装を検出する。
        data[0x7071:0x7079] = bytes.fromhex('cd a0 90 3e b5 ed 4f c9')
        data[0x3e0d:0x3e11] = bytes.fromhex('00 c3 80 30')
        data[0x3080:0x3084] = bytes.fromhex('f3 76 18 fd')
        p.write_bytes(data)
        # sub は RAM へ移りポーリングする。ROM/RAM の分類も検査する。
        sub = bytearray(0x800)
        sub[:15] = bytes.fromhex('f3 21 20 00 11 00 40 01 04 00 ed b0 c3 00 40')
        sub[0x20:0x24] = bytes.fromhex('db f8 18 fc')
        (rom/'DISK.ROM').write_bytes(sub)
        disk = build_disk(bytes(sector), 'none')
        (media/'B92_SYNTHETIC_PRIVATE_NAME.d88').write_bytes(disk)
        (media/'games.tsv').write_text(f'G5\t1\t{hashlib.sha256(disk).hexdigest()[:16]}\n')
        env = dict(os.environ, PC88_GAME_DIR=str(media), PC88_REF_ROM_DIR=str(rom),
                   PC88_CORE=str(core), PC88_FRONTEND=str(front), B93_FRAMES='3', PYTHONDONTWRITEBYTECODE='1')
        env.pop('Q88MEASURE_FAULT_BOUNDARY', None)
        staged = subprocess.run([str(ROOT/'tools/stage_game.sh'), 'G5', str(work/'staged')],
                                env=env, capture_output=True, text=True, check=True)
        assert 'B92_SYNTHETIC_PRIVATE_NAME' not in staged.stdout+staged.stderr
        disks = [Path(x) for x in staged.stdout.splitlines()]
        raw = work/'raw'; raw.mkdir()
        runs = {}
        for name, val in [('base1', None), ('base2', None)] + [(v, int(v, 16)) for v in VALUES]:
            d = raw/name
            assert run_one(front, core, rom, disks, d, 3, val,
                           extra=('--io-log', str(d/'io'), '--sub-cpu-mode', '2')) == 0
            run = read_run(d, 3)
            assert run['entry'] and run['returned']
            assert run['interventions'] == int(val is not None)
            # 自作値だけを検査。R の下位7bitが2進み、bit7が保存される。
            observed = {int(m[1], 16): int(m[2], 16) for m in re.finditer(
                r'^\s*\d+\s+\d+\s+\d+\s+main\s+OUT\s+00(7[EF])\s+([0-9A-F]{2})\s+',
                (d/'io').read_text(), re.M)}
            assert observed[0x7f] == (0x38 if val is None else (val & 0x80) | ((val+2) & 0x7f))
            # 専用ストリームと既存 io-log の見出しが一致することを照合する。
            legacy = list(re.finditer(r'^\s*\d+\s+\d+\s+\d+\s+(main|sub)\s+(IN|OUT)\s+00([0-9A-F]{2})\s+[0-9A-F]{2}\s+([0-9A-F]{4})\s*$',
                                      (d/'io').read_text(), re.M))
            for cpu, label in enumerate(('main', 'sub')):
                expected = [((str(int(m[2] == 'IN')), m[3], m[4]), 1) for m in legacy if m[1] == label]
                assert difference(io_headers(d/'events', cpu), expected) is None
            assert observed[0x7e] == (0x38 | (0 if val is None else val & 0x80)), '二度目も介入している'
            assert all(f == 0 for f in run['targets'].values())
            assert not re.search(r' 3080 ', (d/'timeline').read_text()), '任意fetchの対照不成立'
            assert run['last'][0] == 0 and run['last'][1] == 2
            assert run['final']['CPU位置'] == {'main': 'ROM', 'sub': 'RAM'}
            assert run['final']['待機ポート候補'] == {'main': None, 'sub': 'F8'}
            assert run['stop_snapshot'][0]['フレーム'] == 1
            assert disks[0].read_bytes() == disk
            runs[name] = run
        report = collect(raw, 3)
        assert report['基準2回一致']
        assert all(r['介入効果の比較可能'] for r in report['腕'].values())
        public = json.dumps(report, ensure_ascii=False)
        secrets = ('B92_SYNTHETIC_PRIVATE_NAME', 'B5', 'B8', '7071', '90A0')
        def leaked(s):
            return any(x in s for x in secrets)
        assert not leaked(public)
        assert leaked(public+' B5'), '漏洩検出の陽性対照'
        for d in raw.iterdir():
            text = (d/'events').read_text()
            assert 'B5' not in text and 'B8' not in text and 'out ' not in text
        # 反復の分割、長さのみの差、最初の差、巨大件数を展開せず検査。
        assert difference([('x', 3)], [('x', 1), ('x', 2)]) is None
        assert difference([('x', 3)], [('x', 4)]) == 4
        assert difference([('x', 10**12), ('y', 1)], [('x', 10**12), ('z', 1)]) == 10**12+1
        assert difference([], [('x', 1)]) == 1
        # 基準が変動、または未介入なら比較を有効にしない。
        changed = work/'changed'; shutil.copytree(raw/'base2', changed)
        (changed/'timeline').write_text((changed/'timeline').read_text().replace('7071', '7072', 1))
        unstable = summarize([runs['base1'], read_run(changed, 3)], {'00': runs['00']})
        assert not unstable['基準2回一致'] and not unstable['腕']['00']['介入効果の比較可能']
        assert not summarize([runs['base1'], runs['base2']], {'00': runs['base1']})['腕']['00']['介入効果の比較可能']
        assert summarize([None, runs['base2']], {})['基準2回一致'] is None
        assert summarize([runs['base1'], runs['base2']], {})['腕']['00']['状態'] == '欠測'
        # 切断・重複・欠落・不正フレームを欠測として扱う。
        broken = work/'broken'; shutil.copytree(raw/'00', broken)
        original = (broken/'events').read_text()
        for text in (original.rsplit('end ', 1)[0], original.replace('intervention 1', 'intervention 1\nintervention 1'),
                     original.replace('frame 1 ', 'frame 9 '),
                     original.replace('io 0 0 0 31 0106 1\n', ''), original+'junk\n'):
            (broken/'events').write_text(text)
            try:
                read_run(broken, 3)
            except ValueError:
                pass
            else:
                raise AssertionError('不正記録を受理した')
        (broken/'events').write_text(original)
        original_timeline = (broken/'timeline').read_text()
        (broken/'timeline').write_text('')
        try:
            read_run(broken, 3)
        except ValueError:
            pass
        else:
            raise AssertionError('境界切断を受理した')
        (broken/'timeline').write_text(original_timeline)
        with (broken/'timeline').open('a') as f:
            f.write('# limit reached: dropped=1\n')
        try:
            read_run(broken, 3)
        except ValueError:
            pass
        else:
            raise AssertionError('境界欠落を受理した')
        # 対象未到達と30F未帰還。
        assert run_one(front, core, rom, disks, work/'missing', 2, 0, entry=0x2000) == 0
        assert not read_run(work/'missing', 2)['entry']
        data[0x7071:0x7074] = bytes.fromhex('c3 71 70')
        p.write_bytes(data)
        assert run_one(front, core, rom, disks, work/'timeout', 32, 0) == 0
        timeout = read_run(work/'timeout', 32)
        assert timeout['entry'] and not timeout['returned'] and timeout['interventions'] == 0
        data[0x7071:0x7079] = bytes.fromhex('cd a0 90 3e b5 ed 4f c9')
        p.write_bytes(data)
        # 専用オプションの書式、旧オプションとの混同、出力先を検査。
        link = work/'repo-link'; link.symlink_to(ROOT, target_is_directory=True)
        dangling = work/'dangling'; dangling.symlink_to(ROOT/'b93-forbidden')
        for args in [
            ['--intervene-r-after-rom-return', '7071=100'],
            ['--intervene-r-after-rom-return', '7071=01junk'],
            ['--intervene-r-after-rom-return', '8000=01'],
            ['--intervene-r-after-rom-return', '7071=01', '--intervene-r-after-rom-return', '7071=02'],
            ['--b93-entry', '1000', '--intervene-r-after-rom-return', '7071=01'],
            ['--intervene-before-rom-entry', '7071:FFFF=01'],
            ['--b93-log', str(ROOT/'b93-forbidden')],
            ['--b93-log', str(link/'b93-forbidden')],
            ['--b93-log', str(dangling)],
        ]:
            cmd = [str(front), '--core', str(core), '--rom-dir', str(rom), '--frames', '1']+args
            if '--b93-log' not in args:
                cmd += ['--b93-log', str(work/'bad-option-events')]
            assert subprocess.run(cmd, capture_output=True, env=env).returncode != 0
        assert subprocess.run([str(front), '--intervene-r-after-rom-return', '7071=00'], capture_output=True).returncode != 0
        # 実走と同じシェル入口・全11腕・再集計も自作媒体だけで実行する。
        cli = work/'cli'
        completed = subprocess.run([str(ROOT/'tools/b93_run.sh'), str(cli)], env=env, capture_output=True, text=True)
        assert completed.returncode == 0, 'ランナー入口の自己検査失敗'
        assert 'B92_SYNTHETIC_PRIVATE_NAME' not in completed.stdout+completed.stderr
        summary = (cli/'summary.json').read_text()
        assert all(x['状態'] == '有効' for x in json.loads(summary)['腕'].values())
        assert not leaked(summary)
        assert subprocess.run([sys.executable, str(ROOT/'tools/b93_summary.py'), str(cli)], env=env, capture_output=True).returncode == 0
        assert (cli/'summary.json').read_text() == summary
        assert subprocess.run([str(ROOT/'tools/b93_run.sh'), str(cli)], env=env, capture_output=True).returncode != 0
        assert subprocess.run([str(ROOT/'tools/b93_run.sh'), str(ROOT/'b93-forbidden')], env=env, capture_output=True).returncode != 0
        (cli/'raw/00/status').write_text('1\n')
        assert collect(cli/'raw', 3)['腕']['00']['状態'] == '欠測'
    print('B93 自己検査: 自作ROM/媒体、9腕、陰性、一回限り、到達、I/O、値なし集計 PASS')


if __name__ == '__main__':
    main()
