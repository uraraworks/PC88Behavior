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
import memmap
import compare_screen_signatures as sig
import make_l3_testdisk as diskgen


def assemble(work, name, text, origin):
    path = work / (name + '.asm')
    path.write_text(text)
    return z80text.Assembler().assemble(path)[origin:]


def boot_disk(work, screen_source=None):
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
    body = assemble(work, 'stage', screen_source or '\n'.join(stage), 0xC100)
    assert len(boot) <= 256 and len(body) <= 2048
    payload = boot.ljust(256, b'\0') + body.ljust(2048, b'\0')
    disk = bytearray(diskgen.build_d88(16, 40, 2, content_rule='coord-header', disk_id=0x41))
    track = struct.unpack_from('<I', disk, 32)[0]
    for i in range(9):
        off = track + i * 272 + 16
        disk[off:off+256] = payload[i*256:(i+1)*256]
    return bytes(disk), coords


def execute(work, rom, disk, tag, screen=False, keyboard=False):
    image = work / (tag + '.d88')
    image.write_bytes(disk)
    log = work / (tag + '.memory')
    cores = sorted((ROOT.parent / 'vendor/quasi88-libretro').glob('quasi88_libretro.*'))
    core = next(p for p in cores if p.suffix in ('.dylib', '.so', '.dll'))
    cmd = [str(ROOT/'tools/harness/frontend/q88measure'), '--core', str(core),
           '--rom-dir', str(rom), '--disk', str(image), '--frames', '1200',
           '--mem-write-log', str(log), '--mem-write-range', 'D100-DFFF',
           '--screen-signature-only', '--screen-signature-at', 'end:1199', '--out', str(work/(tag+'.report'))]
    if keyboard:
        cmd += ['--io-log', str(work/(tag+'.io'))]
        for row in range(12):
            cmd += ['--key-matrix', f'{row}:{row % 8}:0:1200']
    if screen:
        cmd += ['--io-log', str(work/(tag+'.io')), '--expect-exec', '0xED36']
    result = subprocess.run(cmd, capture_output=True, timeout=180)
    hook_missing = screen and 'NG: exec ED36' in result.stderr.decode()
    if result.returncode and not (result.returncode == 1 and hook_missing):
        raise AssertionError(f'{tag}: 実行失敗 rc={result.returncode}: {result.stderr.decode()[-500:]}')
    values = {'hook': screen and not hook_missing}
    assert '取りこぼし: 0件' in log.read_text(), 'メモリ記録が欠落'
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
            "long_table": "    ORG 0x20\n    NOP\nTABLE: DB " + ",".join(map(str, range(240))) + "\nBODY: RET\n",
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
            if name == 'long_table':
                start = obj.labels['TABLE']
                assert rom[0x20] == 0xC3 and rom[start:start+240] == bytes(range(240))
            if name == 'relative':
                # 近傍の候補は既存JRを範囲外にする。JR自身より前へ戻る必要がある。
                assert rom[0x90] == 0x18 and rom[0x103] == 0x18
        print('PASS: 命令先頭・連続表の回避・JP代替・相対分岐限界の再配置', flush=True)
    finally:
        build.PINNED_ENTRIES = saved


def screen_disk(work, values):
    """汚した全25行と非既定の窓から7071を呼ぶ。ED36は自作のRETだけ。"""
    source = memmap.asm_prelude() + '''
    ORG 0xC100
    DI
    LD SP,0xE500
    LD A,0xC9
    LD (0xED36),A
    LD HL,MM_TEXT_BASE
    LD DE,MM_TEXT_BASE+1
    LD BC,2999
    LD (HL),0x5A
    LDIR
    XOR A
    LD (MM_SCR_MODE),A
    LD A,40
    LD (MM_SCR_COLS),A
    LD HL,0x0503
    LD (MM_SCR_WTOP),HL
    LD A,7
    LD (MM_SCR_MAXROW),A
    LD (MM_VAR_ROW),A
    LD (MM_VAR_COL),A
'''
    for addr, value in zip((0xE6C0, 0xE6C1, 0xE6C4, 0xE6C5), values):
        source += f'    LD A,{value}\n    LD (0x{addr:04X}),A\n'
    source += '''
    LD A,7
    LD (0xEF86),A
    LD (0xEF87),A
    XOR A
    OUT (0xE6),A               ; 戻り直後の割り込み受理を防ぐ
    LD A,0xA1
    OUT (0x10),A               ; 自作プローブの開始印
    LD A,0x96
    LD IX,0x1234
    LD IY,0x5678
    DI
    CALL 0x7071
    PUSH AF
    PUSH HL
    LD A,I
    DI                         ; 採取後の検査中は割り込みを禁止
    PUSH AF
    POP HL
    LD A,L                     ; P/V は IFF2、A は I レジスタの値
    LD (0xDF2E),A
    POP HL
    POP AF
    PUSH AF
    LD (0xDF20),BC
    LD (0xDF22),DE
    LD (0xDF24),HL
    LD (0xDF26),IX
    LD (0xDF28),IY
    POP HL
    LD (0xDF2A),HL
    LD A,(0xEF86)
    LD (0xDF2C),A
    LD A,(0xEF87)
    LD (0xDF2D),A
    LD A,0xA2
    OUT (0x10),A               ; 戻り印（この間だけのI/Oを検査）
    LD HL,0
    ADD HL,SP
    LD (0xDFF8),HL
    LD HL,MM_TEXT_BASE
    LD DE,0xD100
    LD BC,3000
    LDIR                       ; 本文を出力せず、全バイトを内部比較する
'''
    states = ('MM_SCR_COLS', 'MM_SCR_MAXROW', 'MM_SCR_WTOP', 'MM_SCR_WN',
              'MM_SCR_MODE', 'MM_SCR_P30', 'MM_SCR_P31',
              'MM_VAR_ROW', 'MM_VAR_COL', 'MM_VAR_ROWBASE', 'MM_VAR_ROWBASE+1')
    for i, state in enumerate(states):
        source += f'    LD A,({state})\n    LD (0x{0xDF00+i:04X}),A\n'
    # 入口+1故障の実走でも、画面状態を設定しないRETを完了扱いしない。
    source += '''
    LD A,(MM_SCR_MODE)
    CP 3
    JR NZ,screen_done
    LD A,0xA5
    LD (0xDFFF),A
screen_done:
    JR screen_done
'''
    return boot_disk(work, source)[0]


def read_io(path):
    text = path.read_text()
    assert '取りこぼし: 0件' in text and not re.search(r'取りこぼし: [1-9]', text)
    events = []
    for line in text.splitlines():
        m = re.fullmatch(r'\s*\d+\s+\d+\s+\d+\s+main\s+(IN|OUT)\s+'
                         r'([0-9A-F]{4})\s+([0-9A-F]{2})\s+([0-9A-F]{4})', line)
        if m:
            events.append((m[1], int(m[2], 16), int(m[3], 16), int(m[4], 16)))
    return events


def mode_outputs(cols, rows, color):
    """移設した実装の表を読まず、既存WIDTHの仕様から期待列を作る。"""
    p31, length, params = ((0x39, 2999, (0xCE, 0x98, 0x6F, 0x58, 0x13)) if rows == 25
                          else (0x19, 2399, (0xCE, 0x93, 0x73, 0x38, 0x13)))
    return [(0x31, p31), (0x30, 0x20 | (cols == 80) | (0 if color else 2)),
            (0x51, 0), (0x68, 0xA0), (0x64, 0xC8), (0x64, 0xF3),
            (0x65, length & 255), (0x65, 0x80 | (length >> 8)),
            *[(0x50, p | (0x40 if color and i == 4 else 0)) for i, p in enumerate(params)],
            (0x51, 0x43), (0x68, 0xE4), (0x51, 0x20)]


def check_screen(work, tag, result, values, obj):
    assert result.get(0xDFFF) == 0xA5, '7071: 復帰・状態設定が未完了'
    assert result.get('hook'), '7071: RAMのED36が未実行'
    assert (result.get(0xDFF8), result.get(0xDFF9)) == (0, 0xE5), '7071: RET後のSP不一致'
    assert [result.get(0xDF20+i) for i in range(14)] == [0, 0, 0x80, 0xFF, 0x16, 0xE6, 0x34, 0x12, 0x78, 0x56, 0x54, 0x96, 1, 1], '7071: 戻りレジスタ・カーソル不一致'
    assert 0xDF2E in result and result[0xDF2E] & 4, '7071: DI呼出しからIFF=1で戻らない'
    expected = (b' ' * 80 + bytes((0x80, 0xE8)) * 20) * 25
    assert bytes(result.get(0xD100+i, 0) for i in range(3000)) == expected, '7071: CLSの文字・属性域が不一致'
    state = [80, 24, 0, 25, 3, (values[0] & 0xFC) | 1, 0x21, 0, 0, 0xC8, 0xF3]
    assert [result.get(0xDF00+i) for i in range(len(state))] == state, '7071: 画面作業域が不一致'
    assert sig.read_report(work/(tag+'.report'), 'end').char_count == 0, '7071: 画面に文字が残る'
    events = read_io(work/(tag+'.io'))
    starts = [i for i, e in enumerate(events) if e[:3] == ('OUT', 0x10, 0xA1)]
    ends = [i for i, e in enumerate(events) if e[:3] == ('OUT', 0x10, 0xA2)]
    assert len(starts) == len(ends) == 1 and starts[0] < ends[0], '7071: 呼出区間が不正'
    events = events[starts[0]+1:ends[0]]
    expected_io = mode_outputs(80, 25, True)
    expected_io[0] = (0x31, 0x21)
    expected_io[1] = (0x30, (values[0] & 0xFC) | 1)
    expected_io[4:6] = [(0x64, values[2]), (0x64, values[3])]
    expected_io.insert(2, (0x40, values[1] | 8))
    expected_io.append((0x40, values[1] & 0xF7))
    actual = [(p, v) for kind, p, v, _ in events if kind == 'OUT' and p not in (0x71, 0x32)]
    assert actual == expected_io, '7071: OUTの順序・RAM値との関係が不一致'
    # バンク中継のI/Oとは区別し、ED36から戻った後の11DF相当を厳密に4回確認。
    restore = obj.labels['ENTRY_7071_RESTORE']
    tail = events[-12:]
    for i in range(4):
        triple = tail[3*i:3*i+3]
        assert [(k, p) for k, p, _, _ in triple] == [('IN', 0x71), ('OUT', 0x71), ('OUT', 0x71)], '7071: 復帰I/Oの回数・順序が不一致'
        assert len({v for _, _, v, _ in triple}) == 1, '7071: IN 71の値を保持していない'
        assert [pc for _, _, _, pc in triple] == [restore, restore+2, restore+4], '7071: 復帰処理の発行元が不一致'
    assert sum(restore <= pc < restore+6 for _, _, _, pc in events) == 12


def screen_cases(work, rom, obj, code):
    # 上位ビット、カラー/桁ビット、同期bit3、DMAの上下を独立に振る。
    arms = ((0xA6, 0xD3, 0xC8, 0xF3), (0x59, 0x2C, 0x24, 0xD2),
            (0xFF, 0xFF, 0xA5, 0xE1), (0, 0, 0x5A, 0xC6))
    for i, values in enumerate(arms):
        tag = f'screen-{i}'
        observed = execute(work, rom, screen_disk(work, values), tag, screen=True)
        check_screen(work, tag, observed, values, obj)
    hook_call = obj.labels['ENTRY_7071_RETURN'] - 3
    assert code[hook_call:hook_call+3] == b'\xCD\x36\xED', 'ED36はRAM番地へのCALLが必要'
    assert code[obj.labels['ENTRY_7071_RET']:obj.labels['ENTRY_7071_RET']+2] == b'\xFB\xC9', 'EI・RETが必要'
    faults = {
        'hook': (hook_call, bytes(3), 'ED36'),
        'cls': (hook_call-3, bytes(3), 'CLS'),
        'restore-count': (obj.labels['ENTRY_7071_RETURN'], bytes(3), '復帰'),
        'restore-value': (obj.labels['ENTRY_7071_RESTORE']+2, b'\xAF\x00', '復帰'),
        'p30-mask': (obj.labels['wb_wa_30store']-3, b'\xE6\x00', '画面作業域'),
        'dma-low': (obj.labels['wb_wa_dma_low']-3, b'\x3E\xC8\x00', 'OUT'),
        'p31': (obj.labels['wb_wa_31']-1, b'\xFF', '画面作業域'),
        'ret': (obj.labels['ENTRY_7071_RET'], b'\x76', '未完了'),
        'ei': (obj.labels['ENTRY_7071_RET'], b'\x00', 'IFF'),
        'cursor': (obj.labels['ENTRY_7071_CURSOR']+3, bytes(3), 'カーソル'),
        'registers': (obj.labels['ENTRY_7071_REGS'], bytes(3), 'レジスタ'),
    }
    for name, (address, replacement, reason) in faults.items():
        tag = 'screen-fault-'+name
        broken = work/tag
        shutil.copytree(rom, broken)
        mutated = bytearray(code)
        mutated[address:address+len(replacement)] = replacement
        (broken/'N88.ROM').write_bytes(mutated)
        values = arms[1]
        observed = execute(work, broken, screen_disk(work, values), tag, screen=True)
        if name == 'ei':
            assert 0xDF2E in observed and not (observed[0xDF2E] & 4), '7071: EIなしの陰性対照がIFF=0を示さない'
        try:
            check_screen(work, tag, observed, values, obj)
        except AssertionError as exc:
            assert reason in str(exc), f'{name}: 意図と違う理由で失敗: {exc}'
        else:
            raise AssertionError(f'7071: {name}故障を見逃した')
    print('PASS: 7071のRAM値4組・OUT列・25行CLS・ED36/RET・10種の故障注入', flush=True)


def keyboard_disk(work):
    source = """    ORG 0xC100
    DI
    LD SP,0xE500
    XOR A
    OUT (0xE6),A
"""
    for row in range(12):
        source += f'    LD A,{row+0x30}\n    LD (0x{0xE6D0+row:04X}),A\n'
    source += """    LD A,2
    LD (0xE6CF),A
    LD A,0xA1
    OUT (0x10),A
    LD BC,0x1234
    LD DE,0x5678
    LD IX,0x9ABC
    LD IY,0xDEF0
    DI
    CALL 0x3080
    PUSH AF
    PUSH HL
    LD A,I
    DI
    PUSH AF
    POP HL
    LD A,L
    LD (0xDF2E),A
    POP HL
    LD (0xDF24),HL
    LD (0xDF20),BC
    LD (0xDF22),DE
    LD (0xDF26),IX
    LD (0xDF28),IY
    POP HL
    LD (0xDF2A),HL
    LD A,0xA2
    OUT (0x10),A
    LD HL,0xE6D0
    LD DE,0xD100
    LD BC,24
    LDIR
    LD A,(0xEFF9)
    LD (0xDF32),A
    LD A,(0xE6CF)
    LD (0xDF33),A
    DI
    CALL 0x3080
    DI
    LD A,(0xEFF9)
    LD (0xDF34),A
    LD A,(0xE6CF)
    LD (0xDF35),A
    CALL 0x3080
    DI
    LD A,(0xEFF9)
    LD (0xDF36),A
    LD A,(0xE6CF)
    LD (0xDF37),A
    LD A,(0xE6C3)
    LD (0xDF30),A
    LD A,(0xEFFF)
    LD (0xDF31),A
    LD A,0xA5
    LD (0xDFFF),A
finished:
    JR finished
"""
    return boot_disk(work, source)[0]


def check_keyboard(work, tag, result):
    assert result.get(0xDFFF) == 0xA5, '3080: 復帰失敗'
    expected = [1 << (r % 8) for r in range(12)]
    assert [result.get(0xD100+r) for r in range(12)] == expected, '3080: 入力値'
    assert [result.get(0xD10C+r) for r in range(12)] == [r+0x30 for r in range(12)], '3080: 前回値'
    assert [result.get(0xDF20+i) for i in range(12)] == [0x34,0x12,0x78,0x56,0,0xF0,0xBC,0x9A,0xF0,0xDE,0x50,7], '3080: レジスタ'
    assert result.get(0xDF2E, 0) & 4, '3080: IFF'
    assert result.get(0xDF30) == 7 and result.get(0xDF31) == 0, '3080: E6C3/EFFF'
    assert [result.get(0xDF32+i) for i in range(6)] == [255,1,4,4,255,3], '3080: リピート'
    events = read_io(work/(tag+'.io'))
    start = next(i for i, e in enumerate(events) if e[:3] == ('OUT', 0x10, 0xA1))
    end = next(i for i, e in enumerate(events) if e[:3] == ('OUT', 0x10, 0xA2))
    actual = [(k,p,v) for k,p,v,_ in events[start+1:end]]
    wanted = [('OUT',0xE4,1),('OUT',0x51,0x80),('OUT',0x50,0x16),('OUT',0x50,1)]
    wanted += [('IN',r, 0xFF ^ expected[r]) for r in reversed(range(12))]
    wanted += [('OUT',0xE4,7)]
    assert actual == wanted, '3080: I/O列'


def keyboard_cases(work, rom, obj, code):
    disk = keyboard_disk(work)
    check_keyboard(work, 'keyboard', execute(work, rom, disk, 'keyboard', keyboard=True))
    for name, address, replacement in (
        ('input', obj.labels['ENTRY_3080_IN_05']+2, b'\x00'),
        ('output', obj.labels['ENTRY_3080_OUT'], b'\x00\x00'),
        ('ei', obj.labels['ENTRY_3080_RET'], b'\x00'),
    ):
        tag = 'keyboard-fault-'+name
        broken = work/tag
        shutil.copytree(rom, broken)
        mutated = bytearray(code)
        mutated[address:address+len(replacement)] = replacement
        (broken/'N88.ROM').write_bytes(mutated)
        observed = execute(work, broken, disk, tag, keyboard=True)
        try:
            check_keyboard(work, tag, observed)
        except AssertionError:
            pass
        else:
            raise AssertionError(f'3080: {name}故障を見逃した')
    print('PASS: 3080の入力・前回値・I/O・レジスタ・IFFと故障注入', flush=True)


def numeric_regression(rom, work, obj):
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
    for color in (0, 1):
        commands.append(f'console ,,,{color}')
        for cols in (40, 80):
            for rows in (20, 25):
                commands.append(f'width {cols},{rows}:cls')
    commands += ['poke &he003,-(peek(&hefba)=80)',
                 'poke &he004,-(peek(&hfffe)=57)']
    values, screens = execute_basic(rom, work, commands, (0, 1, 2))
    for i, expected in enumerate((' 3.75', ' 123456789.125', '-.0001220703125')):
        assert has_line(screens[i], [expected]), f'配布ROMの倍精度入出力{i}が不一致'
    assert all(values.get(0xE000+i) == 1 for i in range(3))
    print('PASS: 配置後の配布ROMで倍精度入出力・四則演算', flush=True)
    assert values.get(0xE003) == values.get(0xE004) == 1
    outputs = [(p, v) for kind, p, v, pc in read_io(work/'io.log')
               if kind == 'OUT' and obj.labels['SCREEN_MODE_APPLY'] <= pc < obj.labels['ENTRY_7071']]
    for color in (False, True):
        for cols in (40, 80):
            for rows in (20, 25):
                expected = mode_outputs(cols, rows, color)
                assert any(outputs[i:i+len(expected)] == expected for i in range(len(outputs))), '既存WIDTH/CONSOLEの出力列が変化'
    print('PASS: 既存WIDTH/CONSOLE/CLSの40・80桁/20・25行/白黒・カラー8設定', flush=True)


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
        print('PASS: 7入口のJP・飛び先・listing非重複', flush=True)
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
            probe_disk = screen_disk(work, (0xA6, 0xD3, 0xC8, 0xF3)) if address == 0x7071 else keyboard_disk(work) if address == 0x3080 else disk
            observed = execute(work, broken, probe_disk, f'fault-{address:04X}', keyboard=address == 0x3080)
            if address == 0x3080:
                try:
                    check_keyboard(work, f'fault-{address:04X}', observed)
                except AssertionError:
                    continue
                raise AssertionError('3080: 入口故障を見逃した')
            assert observed.get(0xDFFF) != 0xA5, f'{address:04X}: 故障を実走で見逃した'
        print('PASS: 全7入口+1の故障を配置検査・実走で拒否', flush=True)
        keyboard_cases(work, rom, obj, code)
        screen_cases(work, rom, obj, code)
        numeric_regression(rom, work, obj)
        pad = 0x79D7 - obj.labels['AEL_ROM_LAYOUT_PAD']
        print(f'PASS: main予約前の空き={pad - 92}B（N中継92Bを除く）、末尾={0x8000-len(obj.code)}B')


if __name__ == '__main__':
    main()
