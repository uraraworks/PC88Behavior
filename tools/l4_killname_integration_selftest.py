#!/usr/bin/env python3
"""自作main/subと合成D88だけで直接モード・RUNからのKILL/NAMEを検査する。"""
from pathlib import Path
import argparse
import subprocess
import sys

import compare_screen_signatures as css
import killname_conform_check as check
import m6fk_judge as judge
import m6fk_read as reader
import m6fk_script as script
from make_m6fk_disk import build, offsets
from check_l3_entry_screen import reached_signature_prompt

ROOT = Path(__file__).resolve().parent.parent


def run(work: Path, core: str) -> None:
    rom = work/'integration-rom'
    with (work/'integration-build.log').open('w') as log:
        subprocess.run([sys.executable,str(ROOT/'src/build_main_rom.py'),str(rom)],
                       stdout=log,stderr=log,check=True)
    expected = check.load(ROOT/'tools/killname_conform_expected.tsv')
    frontend = ROOT/'tools/harness/frontend/q88measure'
    for arm in (*script.ARMS,'program'):
        path = work/('integration-'+arm); path.mkdir()
        before = build(script.MEDIA[arm] if arm in script.ARMS else 'KM')
        drive1 = path/'drive1.d88'; drive2 = path/'drive2.d88'
        drive1.write_bytes(build('KM')); drive2.write_bytes(before)
        command = (script.keystrokes(arm) if arm in script.ARMS else
                   '10 name "2:qsa" as "2:qsd"\n20 kill "2:qsb"\ncls:run\n')
        report = path/'signatures.tsv'
        args = [str(frontend),'--core',core,'--rom-dir',str(rom),'--disk',str(drive1),
                '--disk2',str(drive2),'--save-to-disk-image','--frames','8600',
                '--screen-signature-only','--screen-signature-at','final:7700',
                '--screen-signature-at','late:8000','--screen-signature-at','ready:8600','--out',str(report),
                '--type-at','300','--type','\\n','--type-at','700','--type',command.replace('\n','\\n'),
                '--type-at','8100','--type',script.READY_COMMAND+'\\n']
        with (path/'stdout').open('w') as out, (path/'stderr').open('w') as err:
            subprocess.run(args,stdout=out,stderr=err,check=True,timeout=60)
        final,late = (css.read_report(report,name) for name in ('final','late'))
        if final != late or drive1.read_bytes() != build('KM'):
            raise ValueError(arm+' 安定/他ドライブ')
        if not reached_signature_prompt(report,script.READY_COMMAND):
            raise ValueError(arm+' 入力待ち復帰')
        after = drive2.read_bytes()
        if arm == 'program':
            media = bytearray(before); off = offsets(media)
            position = off[(18,1,1)]
            media[position:position+9] = b'qsd'.ljust(9,b' ')
            media[position+16] = 0
            for sector in (14,15,16):
                media[off[(18,1,sector)]+20] = media[off[(18,1,sector)]+21] = 255
            if media != after:
                raise ValueError('RUN 媒体差')
        else:
            a,b,changes = reader.compare(before,after,arm)
            lines = check.entry_lines(final)
            if judge.classify(arm,a,b,lines,changes)['candidates'] != [expected[arm]]:
                raise ValueError(arm+' 媒体/エラー表示')
        if arm in ('K-1','N-1','N-4','program') and css.without_ready_prompt(final):
            raise ValueError(arm+' 成功後の表示')
    print('OK KILL/NAME main/sub: 全10腕・RUN、媒体・エラー表示・成功後Ok1回')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('work',type=Path); ap.add_argument('core')
    args = ap.parse_args()
    try:
        run(args.work,args.core)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print('NG '+str(exc),file=sys.stderr); raise SystemExit(1)
