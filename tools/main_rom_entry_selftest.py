#!/usr/bin/env python3
"""固定入口の配置・起動セクタからのPIO/媒体読み書き・故障注入。"""
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import build_main_rom as build
import z80text
import make_l3_testdisk as diskgen


def assemble(work, name, text, origin):
    path = work / (name + '.asm')
    path.write_text(text)
    return z80text.Assembler().assemble(path)[origin:]


def boot_disk(work):
    boot = assemble(work, 'boot', '''
    ORG 0xC000
    LD SP,0xE500
    LD BC,2
    LD HL,0xC100
load:
    PUSH BC
    PUSH HL
    OR A
    CALL 0x369A
    POP HL
    POP BC
    JP C,failed
    INC H
    INC C
    LD A,C
    CP 10
    JR NZ,load
    JP 0xC100
failed:
    LD A,0xEE
    LD (0xDFFF),A
boot_failed:
    JR boot_failed
''', 0xC000)
    stage = ['    ORG 0xC100', '    LD A,1', '    LD (0xDFFE),A',
             '    LD HL,indirect_target', '    CALL 0x3391',
             '    LD A,(0xDFFD)', '    CP 0x39', '    JP NZ,failed',
             '    LD A,0x91', '    LD (0xDFFC),A', '    JP indirect_done',
             'indirect_target:', '    LD A,0x39', '    LD (0xDFFD),A',
             '    RET', 'indirect_done:']
    def send(value, first=False):
        stage.extend([f'    LD A,{value}', f'    CALL 0x{0x37C9 if first else 0x37D2:04X}',
                      '    JP C,failed'])
    # sub RAMへ256バイト。現行自作subは09未実装なので1.36cの15を使う。
    for i, v in enumerate((0x0C, 0x60, 0, 1, 0)):
        send(v, i == 0)
    stage += ['    LD B,0', 'fill:', '    LD A,B', '    XOR 0xA7',
              '    CALL 0x37D2', '    JP C,failed', '    DJNZ fill']
    for i, v in enumerate((0x15, 0x60, 0, 1, 0)):
        send(v, i == 0)
    stage += ['    LD HL,0xD100', '    LD B,0', 'receive:',
              '    CALL 0x3847', '    JP C,failed', '    LD (HL),A',
              '    INC HL', '    DJNZ receive', '    LD A,2', '    LD (0xDFFE),A']
    send(6, True)
    stage += ['    CALL 0x3847', '    JP C,failed', '    CP 0x80', '    JP NZ,failed']
    coords = ((0, 0, 10), (0, 1, 3), (20, 0, 8), (39, 1, 16))
    for i, (c, h, r) in enumerate(coords):
        stage += [f'    LD BC,{((c*2+h)<<8)|r}', f'    LD HL,0x{0xD200+i*256:04X}',
                  '    OR A', '    CALL 0x369A', '    JP C,failed']
    stage += ['    LD A,3', '    LD (0xDFFE),A', '    LD BC,0x0707',
              '    LD HL,0xD100', '    SCF', '    CALL 0x369A', '    JP C,failed',
              '    LD BC,0x0707', '    LD HL,0xD600', '    OR A', '    CALL 0x369A',
              '    JP C,failed']
    def probe(entry, af, bc, hl, address, enabled=False, target=None):
        stage.extend([f'    LD BC,0x{bc:04X}', '    LD DE,0x3456',
                      f'    LD HL,0x{hl:04X}' if target is None else f'    LD HL,{target}',
                      '    LD IX,0x789A', '    LD IY,0xBCDE',
                      '    LD SP,0xE500', f'    LD HL,0x{af:04X}',
                      '    PUSH HL', '    POP AF',
                      f'    LD HL,0x{hl:04X}' if target is None else f'    LD HL,{target}',
                      '    EI' if enabled else '    DI', f'    CALL 0x{entry:04X}',
                      '    PUSH AF', '    PUSH BC', '    PUSH DE', '    PUSH HL',
                      '    PUSH IX', '    PUSH IY', '    LD A,I', '    PUSH AF'])
        for i in range(7):
            stage.extend(['    POP HL', f'    LD (0x{address + i*2:04X}),HL'])
    probe(0x369A, 0x55D7, 0x0707, 0xD100, 0xD880, enabled=True)
    probe(0x3391, 0x55D7, 0x1234, 0, 0xD800, target='probe_target')
    probe(0x369A, 0x55D6, 0x000A, 0xDA00, 0xD810, enabled=True)
    probe(0x369A, 0x55D7, 0x8000, 0xDA00, 0xD820, enabled=True)
    probe(0x37C9, 0x06D7, 0x1234, 0x5678, 0xD830)
    probe(0x3847, 0x55D7, 0x1234, 0x5678, 0xD840, enabled=True)
    probe(0x37C9, 0x06D7, 0x1234, 0x5678, 0xD890)
    probe(0x3847, 0x55D7, 0x1234, 0x5678, 0xD8A0)
    probe(0x37C9, 0x0C57, 0x1234, 0x5678, 0xD850)
    probe(0x37D2, 0x6057, 0x1234, 0x5678, 0xD860)
    stage += ['    LD A,0xA5', '    LD (0xDFFF),A',
              'done:', '    JR done', 'failed:', '    LD A,0xEE',
              '    LD (0xDFFF),A', '    JR done', 'probe_target:', '    PUSH AF', '    PUSH HL',
              '    LD HL,4', '    ADD HL,SP', '    LD (0xD870),HL',
              '    POP HL', '    POP AF', '    RET']
    body = assemble(work, 'stage', '\n'.join(stage), 0xC100)
    assert len(boot) <= 256 and len(body) <= 2048
    payload = boot.ljust(256, b'\0') + body.ljust(2048, b'\0')
    disk = bytearray(diskgen.build_d88(16, 40, 2, content_rule='coord-header', disk_id=0x41))
    track = struct.unpack_from('<I', disk, 32)[0]
    for i in range(9):
        off = track + i * 272 + 16
        disk[off:off+256] = payload[i*256:(i+1)*256]
    return bytes(disk), coords


def execute(work, rom, disk, tag):
    image = work / (tag + '.d88')
    image.write_bytes(disk)
    log = work / (tag + '.memory')
    cores = sorted((ROOT.parent / 'vendor/quasi88-libretro').glob('quasi88_libretro.*'))
    core = next(p for p in cores if p.suffix in ('.dylib', '.so', '.dll'))
    cmd = [str(ROOT/'tools/harness/frontend/q88measure'), '--core', str(core),
           '--rom-dir', str(rom), '--disk', str(image), '--frames', '1200',
           '--mem-write-log', str(log), '--mem-write-range', 'D100-DFFF',
           '--screen-signature-only', '--screen-signature-at', 'end:1199', '--out', str(work/(tag+'.report'))]
    result = subprocess.run(cmd, capture_output=True, timeout=180)
    if result.returncode:
        raise AssertionError(f'{tag}: 実行失敗 rc={result.returncode}: {result.stderr.decode()[-500:]}')
    values = {}
    for line in log.read_text().splitlines():
        m = re.fullmatch(r'\s*\d+\s+\d+\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})', line)
        if m:
            values[int(m[1], 16)] = int(m[2], 16)
    return values


def placement_cases(work):
    """表の途中・命令先頭・既存JRの限界を、縮小した独立入力で検査。"""
    saved = build.PINNED_ENTRIES
    try:
        build.PINNED_ENTRIES = {0x100: "BODY"}
        cases = {
            "instruction": "    ORG 0xF0\n" + "    NOP\n" * 20 + "BODY: RET\n",
            "table": "    ORG 0xE0\n    NOP\nTABLE: DB " + ",".join(map(str, range(48))) + "\nBODY: RET\n",
            "relative": "    ORG 0x90\n    JR BODY\n" + "    NOP\n" * 126 + "BODY: RET\n",
        }
        for name, source in cases.items():
            path = work / (name + '.asm')
            path.write_text(source)
            rom, obj = build.assemble_pinned(path)
            build.check_pinned_entries(rom, obj)
            if name == 'table':
                start = obj.labels['TABLE']
                assert rom[start:start+48] == bytes(range(48))
            if name == 'relative':
                # 近傍の候補は既存JRを範囲外にする。JR自身より前へ戻る必要がある。
                assert rom[0x90] == 0x18 and rom[0x103] == 0x18
        print('PASS: 命令先頭・連続表の回避・相対分岐限界の再配置', flush=True)
    finally:
        build.PINNED_ENTRIES = saved


def numeric_regression(rom, work):
    # 演算単体の既存検査に加え、今回ずれた配布ROMのDFIN/DFOUTを通す。
    from l4_nrom_selftest import execute as execute_basic, has_line
    commands = [
        'cls:print 1.25#+2.5#',
        'cls:print 123456789.125#',
        'cls:print -0.0001220703125#',
        'poke &he000,-(1.25#*2.5#=3.125#)',
        'poke &he001,-(1#/8#=0.125#)',
        'poke &he002,-(3.75#-2.5#=1.25#)',
    ]
    values, screens = execute_basic(rom, work, commands, (0, 1, 2))
    for i, expected in enumerate((' 3.75', ' 123456789.125', '-.0001220703125')):
        assert has_line(screens[i], [expected]), f'配布ROMの倍精度入出力{i}が不一致'
    assert all(values.get(0xE000+i) == 1 for i in range(3))
    print('PASS: 配置後の配布ROMで倍精度入出力・四則演算', flush=True)


def main():
    assert not any(k.startswith('PC88_REF_') for k in os.environ)
    with tempfile.TemporaryDirectory(prefix='main-entry-') as temp:
        work = Path(temp)
        placement_cases(work)
        rom, asmwork = work/'rom', work/'asm'
        subprocess.run([sys.executable, str(ROOT/'src/build_main_rom.py'), str(rom),
                        '--work-dir', str(asmwork)], check=True, stdout=subprocess.DEVNULL)
        obj = z80text.Assembler()
        obj.assemble(asmwork/'n88_main_gen.asm')
        code = (rom/'N88.ROM').read_bytes()
        build.check_pinned_entries(code, obj)
        print('PASS: 5入口のJP・飛び先・listing非重複', flush=True)
        disk, coords = boot_disk(work)
        result = execute(work, rom, disk, 'normal')
        assert result.get(0xDFFF) == 0xA5, f'完了印なし stage={result.get(0xDFFE)} result={result.get(0xDFFF)}'
        assert result.get(0xDFFD) == 0x39 and result.get(0xDFFC) == 0x91
        print('PASS: 3391からHLのコードへ飛び、RETで呼び出し元へ復帰', flush=True)
        def check_registers(values):
            def word(addr):
                return values.get(addr, 0) | (values.get(addr+1, 0) << 8)
            def check(addr, af, bc, de, hl, iff=None):
                got = [word(addr+i*2) for i in range(7)]
                expected = [0xBCDE, 0x789A, hl, de, bc, af]
                assert got[1:] == expected, f'{addr:04X}: レジスタ {got[1:]} != {expected}'
                if iff is not None:
                    assert bool(got[0] & 4) == iff, f'{addr:04X}: IFF不一致'
            check(0xD880, 0x0100, 0x0707, 0xD200, 0xD100, False)
            check(0xD810, 0x0100, 0x000A, 0xDB00, 0xDA00, False)
            check(0xD820, 0x0193, 0x8000, 0xDA00, 0xEF60, False)
            check(0xD830, 0x0682, 0x1234, 0x3456, 0x5678, False)
            check(0xD840, 0x80D7, 0x1234, 0x3456, 0x5678, True)
            check(0xD8A0, 0x80D7, 0x1234, 0x3456, 0x5678, False)
            check(0xD850, 0x0C02, 0x1234, 0x3456, 0x5678, False)
            check(0xD860, 0x6057, 0x1234, 0x3456, 0x5678, False)
            target = word(0xD806)
            check(0xD800, 0x55D7, 0x1234, 0x3456, target, False)
            assert 0xC100 <= target < 0xC900 and word(0xD870) == 0xE4FE
        check_registers(result)
        print('PASS: 各入口の戻りレジスタ・フラグ・IFF', flush=True)
        broken = work/'fault-register'
        shutil.copytree(rom, broken)
        mutated = bytearray(code)
        mutated[obj.labels['ENTRY_369A_ADVANCE']] = 0
        (broken/'N88.ROM').write_bytes(mutated)
        observed = execute(work, broken, disk, 'fault-register')
        try:
            check_registers(observed)
        except AssertionError:
            pass
        else:
            raise AssertionError('369AのDE故障を見逃した')
        print('PASS: 369AのDE故障を検出', flush=True)
        broken = work/'fault-3847-di'
        shutil.copytree(rom, broken)
        mutated = bytearray(code)
        stub = obj.labels['AEL_ROM_LAYOUT_PAD'] + 92
        assert stub + 4 < 0x79D7 and code[stub:stub+4] == bytes(4)
        target = obj.labels['ENTRY_3847']
        mutated[stub:stub+4] = bytes((0xF3, 0xC3, target & 255, target >> 8))
        mutated[0x3848:0x384A] = struct.pack('<H', stub)
        (broken/'N88.ROM').write_bytes(mutated)
        observed = execute(work, broken, disk, 'fault-3847-di')
        assert observed.get(0xDFFF) == 0xA5
        assert not (observed.get(0xD840, 0) & 4), '3847のDI故障を見逃した'
        try:
            check_registers(observed)
        except AssertionError:
            pass
        else:
            raise AssertionError('3847のDI故障を見逃した')
        print('PASS: 3847入口のDI故障を検出', flush=True)
        pattern = bytes((i ^ 0xA7) for i in [0] + list(range(255, 0, -1)))
        def data(start):
            return bytes(result.get(start+i, 0) for i in range(256))
        assert data(0xD100) == pattern
        print('PASS: 0C→37C9(15)→37D2×4→3847×256', flush=True)
        for i, (c, h, r) in enumerate(coords):
            assert data(0xD200+i*256)[:4] == bytes((0x41, c, h, r))
            assert data(0xD200+i*256) == diskgen.coord_header_pattern(0x41, c, h, r)
        assert data(0xD600) == pattern
        print('PASS: 369Aの両面・遠方座標4件と書込み読戻し256B', flush=True)
        for address in build.PINNED_ENTRIES:
            broken = work/f'fault-{address:04X}'
            shutil.copytree(rom, broken)
            mutated = bytearray(code)
            mutated[address:address+4] = b'\xC9' + code[address:address+3]
            (broken/'N88.ROM').write_bytes(mutated)
            try:
                build.check_pinned_entries(mutated, obj)
            except SystemExit:
                pass
            else:
                raise AssertionError('配置検査が入口+1を見逃した')
            observed = execute(work, broken, disk, f'fault-{address:04X}')
            assert observed.get(0xDFFF) != 0xA5, f'{address:04X}: 故障を実走で見逃した'
        print('PASS: 全5入口+1の故障を配置検査・実走で拒否', flush=True)
        numeric_regression(rom, work)
        pad = 0x79D7 - obj.labels['AEL_ROM_LAYOUT_PAD']
        print(f'PASS: main予約前の空き={pad - 92}B（N中継92Bを除く）、末尾={0x8000-len(obj.code)}B')


if __name__ == '__main__':
    main()
