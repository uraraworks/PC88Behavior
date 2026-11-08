#!/usr/bin/env python3
"""N側ROMの欠落・入口破損とBASICの継続動作を自作ROMで検査する。"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import compare_screen_signatures as sig
import l4_listkw_measure as harness

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/asm'))
sys.path.insert(0, str(ROOT/'tools/harness'))
sys.path.insert(0, str(ROOT/'src'))
import z80text
import memmap
from ext1_run import parse_intlog_main


def execute(rom, work, commands, snapshots=(), key=None):
    report, log = work/'screen.tsv', work/'memory.log'
    args = [str(harness.FRONT), '--core', str(harness.find_core()), '--rom-dir', str(rom),
            '--screen-signature-only', '--out', str(report), '--mem-write-log', str(log),
            '--mem-write-range', 'E000-E004', '--mem-write-from-frame', '0',
            '--int-log', str(work/'interrupt.log'), '--io-log', str(work/'io.log')]
    at = 100
    capture = {}
    for index, cmd in enumerate(commands):
        args += ['--type-at', str(at), '--type', cmd+'\n']
        at += (len(cmd)+1)*12+300
        if index in snapshots:
            capture[index] = f's{index}'
            args += ['--screen-signature-at', f's{index}:{at-80}']
    if key is not None:
        args += ['--type-at', str(at+300), '--type', key]
        at += 1200
    if not capture:
        args += ['--screen-signature-at', f'end:{at}']
    args += ['--frames', str(at+400)]
    p = subprocess.run(args, capture_output=True,
                       env=dict(os.environ, M6FH_LONG_TYPING='1', TMPDIR=str(work)), timeout=240)
    if p.returncode:
        details = p.stderr.decode(errors='replace').splitlines()
        raise ValueError(f'自作ROMの実行に失敗 (終了コード {p.returncode}): '+
                         (details[-1] if details else '詳細なし'))
    text = log.read_text()
    if '取りこぼし: 0件' not in text:
        raise ValueError('メモリ記録が欠落')
    values = {}
    for line in text.splitlines():
        m = re.fullmatch(r'\s*\d+\s+\d+\s+[0-9A-F]{4}\s+(E00[0-4])\s+([0-9A-F]{2})', line)
        if m:
            values[int(m[1],16)] = int(m[2],16)
    screens = {i: sig.read_report(report, name) for i, name in capture.items()}
    return values, screens


def has_line(screen, candidates):
    for row, item in screen.lines.items():
        for body in candidates:
            digest = hashlib.sha256(f'{row}\t{body}\n'.encode()).hexdigest()
            if item == sig.LineSignature(len(body), digest):
                return True
    return False


def run():
    with tempfile.TemporaryDirectory(prefix='l4-nrom-') as temp:
        work = Path(temp)
        original = work/'normal'
        subprocess.run([sys.executable, str(ROOT/'src/build_main_rom.py'), str(original)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        missing, broken = work/'missing', work/'broken'
        shutil.copytree(original, missing)
        shutil.copytree(original, broken)
        (missing/'N88N.ROM').unlink()
        path = broken/'N88N.ROM'
        data = bytearray(path.read_bytes())
        data[0x38] ^= 1
        path.write_bytes(data)
        vals, _ = execute(original, work, ['print 1', 'poke &he000,165'])
        if vals.get(0xe000) != 165:
            raise ValueError('通常起動後の完了印なし')
        for line in (work/'io.log').read_text().splitlines():
            match = re.match(r'\s*\d+\s+\d+\s+\d+\s+main\s+OUT\s+0031\s+([0-9A-F]{2})\b', line)
            if match and int(match[1], 16) & 4:
                raise ValueError('N側命令の前にN側が選択された')
        print('起動と通常命令ではN側を選択しない: OK', flush=True)
        for name, rom, err, executed in (('normal',original,0,False),
                                         ('missing',missing,5,True),
                                         ('broken',broken,5,True)):
            vals, _ = execute(rom, work, ['clear 200,&hdfff','new',
                'poke &he000,0:poke &he001,0', '10 poke &he001,42',
                '20 end', 'delete 10', 'delete 20' if name == 'normal' else 'delete 10',
                'poke &he000,err', 'run'])
            if vals.get(0xe000) != err or (vals.get(0xe001) == 42) != executed:
                raise ValueError(name+' DELETE検出/行生存が不一致')
            # 検出中継内のN側選択OUTを数え、2回目には検出しないことを確認。
            probe_out = memmap.CONSTANTS['MM_N_PROBE'] + 3
            probe_count = 0
            for line in (work/'io.log').read_text().splitlines():
                match = re.fullmatch(r'\s*\d+\s+\d+\s+\d+\s+main\s+OUT\s+0031\s+([0-9A-F]{2})\s+([0-9A-F]{4})\s*', line)
                if match and int(match[2], 16) == probe_out and int(match[1], 16) & 4:
                    probe_count += 1
            if probe_count != (3 if name == 'normal' else 1):
                raise ValueError(name+' 検出回数が不一致')
            print(name+' DELETE: OK', flush=True)
        commands = ['clear 200,&hdfff', 'new', 'poke &he001,0:poke &he003,0',
                    '10 rem nlistmark', '20 poke &he001,42:end',
                    'cls:print "nprintmark"', 'cls:list', 'run', 'new',
                    '10 a$=inkey$:if a$="" then 10',
                    '20 poke &he003,asc(a$):end', 'run']
        vals, screens = execute(missing, work, commands, snapshots=(5,6), key='a')
        if vals.get(0xe001) != 42 or vals.get(0xe003) != 97:
            raise ValueError('RUN/INKEY$が不一致')
        if not has_line(screens[5], ['nprintmark','NPRINTMARK']):
            raise ValueError('PRINTの結果署名が不一致')
        candidates = [f'10{space}{body}' for space in (' ', '  ')
                      for body in ('rem nlistmark','REM NLISTMARK','REM nlistmark')]
        if not has_line(screens[6], candidates):
            raise ValueError('LISTの結果署名が不一致')
        print('欠落時 PRINT・RUN・LIST・INKEY$: OK', flush=True)

        # 長いN側コードで実際にIM2を受け、複製したハンドラから復帰する。
        irqrom = work/'interrupt'
        shutil.copytree(original, irqrom)
        src = work/'irq.asm'
        src.write_text('''    ORG 0x7600
    CALL test_loop
    RET
test_loop:
    LD HL,0xE600
    LD (HL),0x55
    LD DE,0xE601
    LD BC,255
    LDIR
    LD BC,0
loop:
    DEC BC
    LD A,B
    OR C
    JR NZ,loop
    LD A,1
    RET
''')
        probe = z80text.Assembler().assemble(src)[0x7600:]
        path = irqrom/'N88N.ROM'
        image = bytearray(path.read_bytes())
        image[0x7600:0x7600+len(probe)] = probe
        path.write_bytes(image)
        vals, _ = execute(irqrom, work, ['clear 200,&hdfff', 'new',
            'poke &he000,0', '10 delete 20', '20 end', 'run', 'poke &he000,165'])
        ints = parse_intlog_main(work/'interrupt.log')
        active = [i for i in ints if i[3] == '2' and 0x7600 <= int(i[5],16) < 0x7600+len(probe)]
        if vals.get(0xe000) != 165 or not active or any(int(i[6],16) >= 0x8000 for i in active):
            raise ValueError('N側実行中のIM2往復を確認できない')
        print(f'N側実行中のIM2往復: OK ({len(active)}回)', flush=True)

        vals, _ = execute(original, work, ['clear 200,&hdfff', 'new',
            'poke &he000,0', '10 rem x', 'out 49,57', 'delete 10', 'poke &he000,165'])
        values = []
        for line in (work/'io.log').read_text().splitlines():
            m = re.match(r'\s*\d+\s+\d+\s+\d+\s+main\s+OUT\s+0031\s+([0-9A-F]{2})\b', line)
            if m:
                values.append(int(m[1],16))
        try:
            tail = values[values.index(0x39):]
        except ValueError:
            raise ValueError('OUT 31hの値が記録されない')
        if vals.get(0xe000) != 165 or 0x3d not in tail or tail[-1] != 0x39 or 0x19 in tail:
            raise ValueError('OUT 31hとN側中継の写しが不一致')
        print('OUT 31h後の写しとN側往復: OK', flush=True)


if __name__ == '__main__':
    try:
        run()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('N ROM自己検査: '+str(exc), file=sys.stderr)
        raise SystemExit(1)
