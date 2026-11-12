#!/usr/bin/env python3
"""自作媒体の種別 0x80 拒否とプログラムの保持を検査する。"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
import l4_t9_mergechain_measure as t9
import l4_t7_autorenum_measure as base

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='l4-binary-type-') as tmp:
        work = Path(tmp)
        rom = Path(os.environ.get('PC88_BINARY_TYPE_ROM', work / 'rom'))
        if 'PC88_BINARY_TYPE_ROM' not in os.environ:
            p = subprocess.run([sys.executable, str(ROOT / 'src/build_main_rom.py'), str(rom), '--work-dir', str(work / 'asm')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if p.returncode: raise ValueError('ROMビルド')
        original_disks = t9.disks
        saved = work / 'saved.d88'
        original_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            if path.name == 'b.d88' and not saved.exists():
                shutil.copyfile(path, saved)
            return original_unlink(path, *args, **kwargs)
        def plan(name):
            prefix = [('type','clear 200,&hdfff'),('type','new')]
            if name == 'prepare':
                prefix += [('type','10 poke &he010,77:end'),('type','cls:locate 0,5'),('type','save "2:x",a'),('snap2','save')]
                op = 'rem'
            else:
                command = {'ref':'error 59','load':'load "2:x"','run':'run"2:x"','chain':'chain"2:x"','reject_merge':'merge "2:x"','control':'load "2:x"','control_run':'run"2:x"'}[name]
                prefix += [('type','10 poke &he010,11:end'),('type','20 poke &he011,22:end'),
                           ('type','30 on error goto 90:'+command+':end'),('type','90 poke &he012,err:end')]
                op = command if name in ('run','ref','control_run') else 'goto 30'
            prefix += [('type','for i=&he000 to &he048:poke i,0:next'),('type','poke &he000,151')]
            if name not in ('prepare','ref'):
                prefix += [('type','for i=0 to 511:poke &he100+i,peek(&h8400+i):next')] + [('snap',f'wait{i}') for i in range(5)]
            prefix += [('type','cls:locate 0,5'),('snap','before'),('type',op),('snap2','operation'),('type','poke &he002,1')]
            if name not in ('prepare','ref'):
                prefix += [('type','for i=0 to 511:poke &he013,-(peek(&he100+i)<>peek(&h8400+i)):next')] + [('snap',f'compare{i}') for i in range(5)] + [('type','goto 10'),('type','goto 20')]
            prefix += [('type','poke &he001,163')]
            return prefix, op
        t9.plan = plan
        Path.unlink = unlink
        d = work / 'prepare'; d.mkdir()
        try: t9.capture(rom, 'prepare', d)
        finally: Path.unlink = original_unlink
        image = bytearray(saved.read_bytes())
        pos = struct.unpack_from('<I', image, 32 + (18*2+1)*4)[0]
        if tuple(image[pos:pos+3]) != (18,1,1) or image[pos+16:pos+17].lower() != b'x' or image[pos+25] != 0:
            raise ValueError('保存したディレクトリ')
        binary = work / 'binary.d88'
        image[pos+25] = 0x80
        binary.write_bytes(image)
        selected = [saved]
        def disks(directory, official=False):
            args = original_disks(directory, False)
            shutil.copyfile(selected[0], directory / 'b.d88')
            return args
        t9.disks = disks
        def run(name):
            d = work / name; d.mkdir()
            return t9.capture(rom, name, d)
        ref = base.response(run('ref')['screen']['operationa'])
        for name in ('load','run','chain','reject_merge','control','control_run'):
            selected[0] = saved if name in ('control','control_run') else binary
            result = run(name)
            marks = [x for x in result['writes'] if x[0] in (0xe010,0xe011)]
            if name in ('control','control_run'):
                ok = (0xe010,77) in marks and (0xe010,11) not in marks
            else:
                ok = ((name == 'run' and base.response(result['screen']['operationa']) == ref) or (0xe012,59) in result['writes']) and marks == [(0xe010,11),(0xe011,22)] and [v for a,v in result['writes'] if a == 0xe013] == [0]*512
            if not ok: print('判定詳細:', [x for x in result['writes'] if x[0] in (0xe010,0xe011,0xe012)], len([1 for a,v in result['writes'] if a==0xe013]), any(v for a,v in result['writes'] if a==0xe013))
            print(f"{name}: {'OK' if ok else 'NG'}")
            if not ok: raise ValueError(name)
    return 0

if __name__ == '__main__':
    try: raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(f'NG: {exc}')
        raise SystemExit(1)
