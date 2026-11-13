#!/usr/bin/env python3
"""INKEY$の取りこぼし・重複の実Z80検査（公式ROM不要）。"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import l4_inkey_measure as ik

sys.path.insert(0, str(ik.kw.REPO / 'tools/asm'))
import z80text
sys.path.insert(0, str(ik.kw.REPO / 'src'))
import memmap


def fast_rom(rom, asm_dir, work):
    """BASIC解析の重さを除いた、実ルーチンの短周期ドライバ。

    自作ROMの通常起動後、レイアウト用のゼロ埋め領域に置いたドライバへ移る。
    生産コードのS9C_POLL/INIT/TRYとバンクはそのまま使う。
    """
    assembler = z80text.Assembler()
    assembler.assemble(asm_dir / 'n88_main_gen.asm')
    labels = assembler.labels
    source = memmap.asm_prelude() + f'''
    ORG {{start}}
    DI
    LD HL,fast_name
    LD DE,MM_IDENT_BUF
    LD BC,7
    LDIR
    CALL {labels['S9C_INIT']}
    XOR A
    LD (MM_IK_TEST_SEEN),A
fast_wait:
    CALL fast_read
    LD A,(MM_RUN_STR_TMP_LEN)
    OR A
    JR Z,fast_wait
    LD BC,1024
fast_drain:
    PUSH BC
    CALL fast_read
    POP BC
    DEC BC
    LD A,B
    OR C
    JR NZ,fast_drain
    LD HL,fast_bad
    LD A,(MM_IK_TEST_SEEN)
    CP 1
    JR NZ,fast_show
    LD A,(MM_IK_TEST_CHAR)
    CP 97
    JR NZ,fast_show
    LD HL,fast_good
fast_show:
    PUSH HL
    LD HL,MM_TEXT_BASE
    LD B,80
fast_clear:
    LD (HL),32
    LD DE,120
    ADD HL,DE
    LD (HL),32
    OR A
    SBC HL,DE
    INC HL
    DJNZ fast_clear
    POP HL
    LD DE,MM_TEXT_BASE
    LD BC,8
    LDIR
    LD HL,fast_done
    LD DE,MM_TEXT_BASE+120
    LD BC,5
    LDIR
fast_stop:
    JP fast_stop
fast_read:
    LD (MM_IK_TEST_POLL),A            ; 周期の検査専用。返却値には使わない。
    CALL {labels['S9C_POLL']}
    CALL {labels['S9C_TRY_INKEY']}
    LD A,(MM_RUN_STR_TMP_LEN)
    OR A
    RET Z
    LD HL,MM_IK_TEST_SEEN
    INC (HL)
    ; 飽和させ、256回の重複が1回へ巻き戻って合格しないようにする。
    JR NZ,fast_counted
    DEC (HL)
fast_counted:
    LD A,(MM_RUN_STR_TMP_BUF)
    LD (MM_IK_TEST_CHAR),A
    RET
fast_name:
    DB "INKEY",0,0
fast_good:
    DB "iks 1 97"
fast_bad:
    DB "iks 0 0"
    DB 32
fast_done:
    DB "ikd 1"
'''
    path = work / 'fast.asm'
    path.write_text(source.format(start=0))
    size = len(z80text.Assembler().assemble(path))
    target = work / 'fast-rom'
    shutil.copytree(rom, target)
    image = bytearray((target / 'N88.ROM').read_bytes())
    # ビルドと同じくレイアウト用DSだけを空きとし、ゼロの命令も保護する。
    occupied = bytearray(len(image))
    for addr, chunk, _, raw in assembler.listing:
        if addr == labels['AEL_ROM_LAYOUT_PAD'] and raw.strip().upper().startswith('DS '):
            continue
        occupied[addr:addr + len(chunk)] = b'\1' * len(chunk)
    # N中継はlistingの後に注入される。ゼロを含むため全体を予約する。
    relay = assembler.symtab['MM_N_RELAY_SOURCE']
    occupied[relay:relay + 92] = b'\1' * 92
    occupied[0x79D6:0x79D8] = b'\1\1'
    assert image[0x79D7] == ord('4')
    start = next((i for i in range(len(image) - size + 1)
                  if not any(occupied[i:i + size]) and
                  image[i:i + size] == bytes(size)), None)
    if start is None:
        raise RuntimeError('検査ドライバ用の連続空き領域がない')
    path.write_text(source.format(start=start))
    driver = z80text.Assembler().assemble(path)[start:]
    assert len(driver) == size
    image[start:start+len(driver)] = driver
    entry = labels['STEADY_WAIT']
    image[entry:entry+3] = bytes((0xC3, start & 255, start >> 8))
    (target / 'N88.ROM').write_bytes(image)
    return target


def run_fast(rom, hold, offset, work):
    screen = work / 'fast.bin'
    clock = work / 'fast-clock.txt'
    poll_addr = f"{memmap.addresses()['MM_IK_TEST_POLL']:04X}"
    args = [str(ik.kw.FRONT), '--core', str(ik.kw.find_core()), '--rom-dir', str(rom),
            '--key-hold', str(hold), '--key-gap', '8', '--type-at', str(offset), '--type', 'a',
            '--mem-write-log', str(clock), '--mem-write-range', f'{poll_addr}-{poll_addr}',
            '--mem-write-from-frame', '590',
            '--vram-dump', str(screen), '--vram-dump-at', str(offset+200),
            '--frames', str(offset+210)]
    proc = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL, timeout=180)
    try:
        if proc.returncode:
            return False, 'capture', None
        samples = [int(m[1]) for line in clock.read_text().splitlines()
                   if (m := re.fullmatch(rf'\s*\d+\s+(\d+)\s+[0-9A-F]+\s+{poll_addr}\s+[0-9A-F]+', line))]
        count = sum(590 <= frame < 600 for frame in samples)
        # 打鍵前10フレームを実測。高期間（約0.1フレーム）より速いことも関門。
        if count <= 100:
            return False, 'too-slow', None
        period = 10 / count
        rows, _ = ik.extract(screen.read_bytes())
        ok = rows == [['iks', 1, 97], ['ikd', 1]]
        return ok, '' if ok else 'values' if ['ikd', 1] in rows else 'missing', period
    finally:
        screen.unlink(missing_ok=True)
        clock.unlink(missing_ok=True)


def variants():
    result = []
    for n in range(9):
        body = '20 a$=inkey$' + ':x=x+1' * n
        # 80桁の入力上限を越えず、代入がIFの分岐で飛ばされないようにする。
        tail = ':if a$="" then 20'
        lines = [body + tail] if len(body + tail) < 80 else [body, '25 if a$="" then 20']
        result.append((f'add-{n}', lines))
    for n in (1, 8, 32, 128):
        result.append((f'for-{n}', [f'20 for k=1 to {n}:next',
                                  '25 a$=inkey$:if a$="" then 20']))
    result.append(('two-line', ['20 a$=inkey$', '25 if a$="" then 20']))
    return result


def program(body):
    # 取得後も十分長く読み続け、押下の重複・リピートの誤発火を検出する。
    return ['new', '10 x=0:c=0:v=0', *body,
            '30 c=c+1:v=asc(a$)', '40 for j=1 to 200:a$=inkey$',
            '50 if a$<>"" then c=c+1', '60 next',
            '70 print "iks";c;v', '80 print "ikd";1', '90 end', 'cls', 'run']


def run(rom, body, hold, offset, work):
    args = [str(ik.kw.FRONT), '--core', str(ik.kw.find_core()), '--rom-dir', str(rom)]
    at = 100
    for line in program(body):
        args += ['--key-hold', '4', '--key-gap', '8', '--type-at', str(at), '--type', line + '\n']
        if line == 'run':
            origin = at + len(line) * 12
        at += (len(line) + 1) * 12 + 240
    start = origin + offset
    capture = origin + 2400
    screen = work / 'screen.bin'
    before = work / 'before.bin'
    args += ['--key-hold', str(hold), '--key-gap', '8', '--type-at', str(start), '--type', 'a',
             '--vram-dump', str(before), '--vram-dump-at', str(start - 1),
             '--vram-dump', str(screen), '--vram-dump-at', str(capture),
             '--frames', str(capture + 10)]
    proc = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL,
                          env=dict(os.environ, M6FH_LONG_TYPING='1'), timeout=180)
    try:
        if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
            return False, 'capture'
        waiting, _ = ik.extract(ik.dumped(before, start - 1).read_bytes())
        rows, _ = ik.extract(ik.dumped(screen, capture).read_bytes())
        if waiting:
            return False, 'not-waiting'
        ok = rows == [['iks', 1, 97], ['ikd', 1]]
        return ok, ('' if ok else 'values' if ['ikd', 1] in rows else 'missing')
    finally:
        for path in work.glob('*.bin'):
            path.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom-dir', type=Path, help='事前にビルドした自作ROM（陰性対照用）')
    parser.add_argument('--expect-failure', action='store_true')
    parser.add_argument('--asm-dir', type=Path, help='--rom-dir と同時にビルドした中間asm')
    parser.add_argument('--fast-only', action='store_true', help='短周期の実ルーチン検査だけを実行')
    parser.add_argument('--out', type=Path, help='組み合わせ別の真偽だけを保存')
    args = parser.parse_args()
    if args.expect_failure and args.rom_dir is None:
        parser.error('--expect-failure には自作ROMの --rom-dir が必要')
    if args.rom_dir is not None and args.asm_dir is None:
        parser.error('--rom-dir には対応する --asm-dir が必要')
    expected = [['iks', 1, 97], ['ikd', 1]]
    assert ik.extract(ik.sf.screen_of(expected))[0] == expected
    assert [['iks', 2, 97], ['ikd', 1]] != expected
    with tempfile.TemporaryDirectory(prefix='inkey-robust-') as tmp:
        work = Path(tmp)
        ik.known_difference_selftest(work)
        rom = args.rom_dir or work / 'rom'
        if args.rom_dir is None:
            proc = subprocess.run([os.sys.executable, str(ik.kw.REPO / 'src/build_main_rom.py'),
                                   str(rom), '--work-dir', str(work / 'asm')], capture_output=True)
            if proc.returncode:
                raise RuntimeError('自作ROM一時ビルド失敗')
        records = []
        fast = fast_rom(rom, args.asm_dir or work / 'asm', work)
        for hold in (4, 2):
            passed = 0
            for offset in range(600, 608):
                ok, reason, period = run_fast(fast, hold, offset, work)
                records.append(dict(variant='fast', hold=hold, offset=offset, passed=ok, reason=reason,
                                    frames_per_poll=period))
                passed += ok
                if not ok:
                    print(f'NG fast hold={hold} offset={offset} ({reason})', flush=True)
            print(f'fast hold={hold}: {passed}/8', flush=True)
        for name, body in ([] if args.fast_only else variants()):
            assert all(len(line) < 80 for line in program(body))
            for hold in (4, 2):
                passed = 0
                for offset in range(600, 608):
                    ok, reason = run(rom, body, hold, offset, work)
                    records.append(dict(variant=name, hold=hold, offset=offset, passed=ok, reason=reason))
                    passed += ok
                    if not ok:
                        print(f'NG {name} hold={hold} offset={offset} ({reason})', flush=True)
                print(f'{name} hold={hold}: {passed}/8', flush=True)
        if args.out:
            args.out.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
        failures = sum(not r['passed'] for r in records)
        print(f'頑健性: {len(records)-failures}/{len(records)}、失敗={failures}', flush=True)
        if args.expect_failure:
            # 全走行の失敗や採取失敗を検出力ありと誤判定しない。
            return int(not (0 < failures < len(records) and
                           all(r['reason'] in ('', 'values', 'missing') for r in records)))
        return int(failures != 0)


if __name__ == '__main__':
    raise SystemExit(main())
