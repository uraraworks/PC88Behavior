#!/usr/bin/env python3
"""sub-rom-entry第4版の確定範囲だけを実Z80で検査する。公式素材は使わない。"""
import os
from pathlib import Path
import re
import subprocess
import struct
import sys

repo, work, core = map(Path, sys.argv[1:])
sys.path[:0] = [str(repo), str(repo / 'tools/asm')]
from src.l3_service import make_subrom as sub
import z80text

assert not any(k.startswith('PC88_REF_') for k in os.environ)
rom, used = sub.build()
a = sub._LAST_ASM
public = {0x10: 'RECV_BYTE', 0x18: 'SEND_BYTE', 0x20: 'FDC_OUT',
          0xed: 'ENTRY_REQUEST', 0x2a7: 'FDC_OUT', 0x2b4: 'ENTRY_CALCULATE',
          0x35b: 'ENTRY_F7', 0x48f: 'ENTRY_READY', 0x7d6: 'ENTRY_SEEK',
          0x263: 'ENTRY_FDC_RESULT', 0x6a6: 'ENTRY_RECV_FOUR'}


def check_layout(image):
    assert image[0x2db:0x2dd] == bytes((0xd6, 0x07))
    for addr, target in public.items():
        assert image[addr] == 0xc3, f'{addr:04X}: JP入口なし'
        assert int.from_bytes(image[addr+1:addr+3], 'little') == a.labels[target]
        assert a.labels[target] < 0x800
    assert image[0x2a4:0x2a7] == bytes((0x32, 0x0c, 0x7f))
    for addr in (0x10, 0x18, 0x20):
        assert addr + 3 <= (addr & ~7) + 8
    assert not sub.find_fetch_window_straddles(a)
    assert not sub.find_out_of_window_blocks(a)
    assert a.labels['PIN_0263'] == 0x263 and a.labels['PIN_06A6'] == 0x6a6
    assert used <= 0x800


check_layout(rom)
# 新入口と06A6から呼ぶ受信ルーチンには、IFF/IMを変更する命令を置かない。
# 0263のEI腕はFDCの保留IRQを受理し得るため、外部割込みによるIFF解除と
# 入口自身の副作用を分け、無割込み時の保存は全到達命令でも確認する。
interrupt_neutral = [
    (a.labels['ENTRY_FDC_RESULT'], len(a.code)),
    (a.labels['RECV_BYTE'], a.labels['SEND_BYTE']),
    (a.labels['WAIT_FE_RECV_DATA_READY'], a.labels['WAIT_FE_RECV_DATA_READY'] + 7),
    (a.labels['WAIT_FE_RECV_ACK_DONE'], a.labels['WAIT_FE_RECV_ACK_DONE'] + 7),
]
neutral_instructions = [text for kind, pc, size, text in a._emit_asm
                        if kind == 'instr' and any(lo <= pc < hi for lo, hi in interrupt_neutral)]
assert not any(text in ('DI', 'EI') or text.startswith('IM ') for text in neutral_instructions)
# 入口回避の分岐をPIO待ちに挟まない。条件・1周の命令列を独立した定数で検査。
waits = {
    'WAIT_FE_RECV_DATA_READY': (1, 0x28),
    'WAIT_FE_RECV_ACK_DONE': (1, 0x20),
    'WAIT_FE_SEND_RECV_READY': (2, 0x28),
    'WAIT_FE_SEND_ACK_DONE': (4, 0x28),
    'WAIT_FE_SEND_STATUS_CLEAR': (4, 0x20),
}
for options in ({}, {'fast_no_disk_response_ready': True}, {'early_response_after': 5},
                *({f'inject_m6ib_b{i}': True} for i in range(1, 6))):
    variant, variant_used = sub.build(**options)
    layout = sub._LAST_ASM
    assert variant_used <= 0x800
    for name, (mask, branch) in waits.items():
        pc = layout.labels[name]
        assert variant[pc:pc+7] == bytes((0xdb,0xfe,0xe6,mask,branch,0xfa,0xc9))
    assert variant[0x2db:0x2dd] == bytes((0xd6, 0x07))
    for addr, target in public.items():
        assert variant[addr] == 0xc3
        assert int.from_bytes(variant[addr+1:addr+3], 'little') == layout.labels[target]
for addr in (*public, 0x2a4, 0x2db):
    broken = bytearray(rom)
    broken[addr:addr+4] = bytes((0,)) + broken[addr:addr+3]
    try:
        check_layout(broken)
    except AssertionError:
        pass
    else:
        raise AssertionError(f'{addr:04X}: 配置+1故障が通過')
print('配置・RST枠・フェッチ窓・全入口の配置+1故障: PASS', flush=True)

source = (repo / 'src/l3_main/main_sub_read.asm').read_text()
primitives = source[source.index('MAIN_SUB_WAIT_SET:'):source.index('; PAIR陰性対照用。')]
# 受信後のDAC解除まで待つ相手でも成立することを同時検査。
primitives = primitives.replace(
    '    OUT (0FFh),A\n    IN A,(0FEh)\n    OR A\n    RET',
    '    OUT (0FFh),A\n    LD C,4\n    CALL MAIN_SUB_WAIT_CLEAR\n    RET C\n    OR A\n    RET', 2)
disk = work / 'own.d88'
subprocess.run([sys.executable, str(repo / 'tools/make_l3_testdisk.py'), str(disk),
                '--cylinders', '40', '--double-sided', '--sectors-per-track', '16'],
               check=True, capture_output=True)


def assemble(path, source):
    path.write_text(source)
    return z80text.Assembler().assemble(path)


def data(name, values):
    return name + ':\n' + '\n'.join('    DB ' + ','.join(map(str, values[i:i+32]))
                                    for i in range(0, len(values), 32)) + '\n'


def run(entry, *, mode='CALL', fault=False, disk2=False, value=0x35, flags=1,
        expected_return=True, sweep=False, received=(0x81, 0x42, 0xe3, 0x24),
        iff=False, im=0, d=0x23, mutation=None):
    name = f'{entry:04x}_{mode}_{fault}_{disk2}_{value}_{flags}_{sweep}_{len(received)}_{iff}_{im}_{d}_{mutation}'
    case = work / name
    case.mkdir()
    target = entry + int(fault)
    transfer = f'    {mode} {target}\n'
    if mode == 'INDIRECT':
        transfer = '    LD HL,(002DBh)\n    CALL INDIRECT_CALL\n    JR RETURNED\nINDIRECT_CALL:\n    JP (HL)\n'
    elif mode == 'JP':
        transfer = f'    LD HL,RETURNED\n    PUSH HL\n    LD HL,03456h\n    JP {target}\n'
    elif mode == 'RST' and fault:
        # RSTのオペランドは8の倍数のみ。ROM側の入口を1ずらして同じRSTを実行。
        transfer = f'    RST {entry}\n'
    prepare = ''
    if entry == 0x263:
        # 起動で初期化済みのFDCへ自作媒体C=0,H=0,R=1,N=1のREAD DATA。
        # 本体256バイトだけを消費し、結果7バイトを公開入口へ残す。
        prepare = ''.join(f'    LD A,{v}\n    RST 020h\n'
                          for v in (0x46, 0, 0, 0, 1, 1, 1, 0x0e, 0xff))
        prepare += '''    LD B,0
READ_BODY:
    IN A,(0FAh)
    AND 0C0h
    CP 0C0h
    JR NZ,READ_BODY
    IN A,(0FBh)
    DJNZ READ_BODY
    IN A,(0F8h)
RESULT_READY:
    IN A,(0FAh)
    AND 0C0h
    CP 0C0h
    JR NZ,RESULT_READY
'''
    if entry == 0xed:
        prepare += ''.join(f'    LD A,{v}\n    LD ({0x7b00+i}),A\n'
                           for i, v in enumerate((0x31,0x82,0,0xff,0x55,0xa6)))
    if entry == 0xed and value == 0x12:
        prepare += '''    LD A,012h
    LD (07C1Bh),A
    LD A,051h
    LD (07C28h),A
    LD HL,05000h
    LD B,0
FILL_RESPONSE:
    LD A,L
    XOR 05Ah
    LD (HL),A
    INC HL
    DJNZ FILL_RESPONSE
'''
    if entry == 0x7d6:
        prepare += '    LD A,1\n    LD (07C32h),A\n'  # 既存ドライブ指定を無視して装置00
    probe = '    ORG 07800h\n' + prepare + '''
    LD A,0A5h
    LD (07F0Bh),A
    LD (07F0Ch),A
    LD (07F14h),A
    LD BC,01234h
    LD DE,02345h
    LD HL,03456h
    LD IX,04567h
    LD IY,05678h
    LD A,03Ah
    LD I,A
    LD HL,INPUT_AF
    PUSH HL
    POP AF
    LD HL,03456h
''' .replace('INPUT_AF', str((value << 8) | flags)).replace('LD DE,02345h', f'LD DE,{(d << 8) | 0x45}') + (
        f'    IM {im}\n    {"EI" if iff else "DI"}\n    NOP\n'
        if entry in (0x263, 0x6a6) else '') + transfer + '''RETURNED:
    LD (07A00h),BC
    LD (07A02h),DE
    LD (07A04h),HL
    LD (07A06h),IX
    LD (07A08h),IY
    LD (07A0Ah),SP
    PUSH AF
    POP HL
    LD (07A0Ch),HL
    LD A,(07F0Bh)
    LD (07A0Eh),A
    LD A,(07F0Ch)
    LD (07A0Fh),A
    LD A,I
    LD (07A10h),A
    LD HL,07A00h
    LD B,17
SEND_REPORT:
    LD A,(HL)
    RST 018h
    INC HL
    DJNZ SEND_REPORT
    JP 000C1h
'''
    report_size = 25 if entry == 0x263 else 17
    if entry == 0x263:
        probe = probe.replace('    LD HL,07A00h\n    LD B,17',
            '    LD HL,07F0Dh\n    LD DE,07A11h\n    LD BC,8\n    LDIR\n'
            '    LD HL,07A00h\n    LD B,25')
    if sweep:
        probe = probe.replace('    ORG 07800h\n',
            '    ORG 07800h\n    XOR A\n    LD (07A20h),A\n    LD (07A21h),A\nPROBE_START:\n')
        probe = probe.replace(f'    LD HL,{(value << 8) | flags}\n',
            '    LD A,(07A20h)\n    LD H,A\n    LD A,(07A21h)\n    LD L,A\n')
        probe = probe.replace('    JP 000C1h\n',
            '    LD A,(07A20h)\n    INC A\n    LD (07A20h),A\n    JP NZ,PROBE_START\n'
            '    LD A,(07A21h)\n    INC A\n    LD (07A21h),A\n    CP 2\n    JP NZ,PROBE_START\n'
            '    JP 000C1h\n')
    payload = assemble(case / 'probe.asm', probe)[0x7800:]
    # ORGを含むアセンブラの結果は原点分を含まない。
    assert len(payload) < 0x200
    commands = bytes((12, 0x78, 0, len(payload) >> 8, len(payload) & 255)) + payload
    commands += bytes((13, 0x78, 0))
    extra = ''
    if entry == 0x10:
        extra = '    LD A,06Dh\n    CALL MAIN_SUB_SEND\n    JP C,FAIL\n'
    if entry == 0x6a6:
        extra = ''.join(f'    LD A,{v}\n    CALL MAIN_SUB_SEND\n    JP C,FAIL\n'
                        for v in received)
    response_size = 0
    if entry == 0xed:
        params = {6: (), 9: (0x7b,0,0x7b,6), 0x15: (0x7b,0,0,6), 0x12: ()}[value]
        extra = ''.join(f'    LD A,{v}\n    CALL MAIN_SUB_SEND{"_CONT" if i else ""}\n    JP C,FAIL\n'
                        for i, v in enumerate(params))
        response_size = 1 if value == 6 else (256 if value == 0x12 else 6)
        if value in (0x12, 0x15):
            extra += ('    LD HL,09000h\n    CALL MAIN_SUB_RECV_PAIR\n    JP C,FAIL\n') * (response_size // 2)
        else:
            extra += ('    CALL MAIN_SUB_RECV\n    JP C,FAIL\n    LD (09000h),A\n') * response_size
    count = 17 * 512 if sweep else report_size + (entry == 0x18)
    main_source = '''    ORG 0
    DI
    LD SP,0FFF0h
    XOR A
    CALL MAIN_SUB_SEND
    JP C,FAIL
    LD HL,COMMANDS
    LD BC,COMMANDS_END-COMMANDS-3
    CALL SEND_RUN
    LD BC,3
    CALL SEND_RUN
''' + extra + f'    LD BC,{count}\n' + '''RECEIVE:
    PUSH BC
    CALL MAIN_SUB_RECV
    POP BC
    JP C,FAIL
    LD (09000h),A
    DEC BC
    LD A,B
    OR C
    JR NZ,RECEIVE
    LD A,1
    LD (09002h),A
STOP:
    JR STOP
FAIL:
    LD A,1
    LD (09003h),A
    JR STOP
SEND_RUN:
    LD A,(HL)
    PUSH BC
    CALL MAIN_SUB_SEND
    POP BC
    JP C,FAIL
    JR ADVANCE
SEND_NEXT:
    LD A,(HL)
    PUSH BC
    CALL MAIN_SUB_SEND_CONT
    POP BC
    JP C,FAIL
ADVANCE:
    INC HL
    DEC BC
    LD A,B
    OR C
    JR NZ,SEND_NEXT
    RET
MAIN_SUB_TIMEOUT_LIMIT EQU 65535
''' + primitives + data('COMMANDS', commands) + 'COMMANDS_END:\n'
    if entry == 0xed:
        # 00ED帰還後に通常の要求も送り、呼出し専用の終了状態が残らないことを確認。
        following = ''.join(f'    LD A,{v}\n    CALL MAIN_SUB_SEND{"_CONT" if i else ""}\n    JP C,FAIL\n'
                            for i, v in enumerate((9,0,0,0,2)))
        following += ('    CALL MAIN_SUB_RECV\n    JP C,FAIL\n    LD (09000h),A\n') * 2
        main_source = main_source.replace('    LD A,1\n    LD (09002h),A', following + '    LD A,1\n    LD (09002h),A')
    main = assemble(case / 'main.asm', main_source)
    (case / 'N88.ROM').write_bytes(main + bytes(0x8000-len(main)))
    image = bytearray(rom)
    if mode == 'INDIRECT' and fault:
        image[0x2db] += 1
    if mode == 'RST' and fault:
        image[entry:entry+4] = bytes((0,)) + image[entry:entry+3]
    if mutation == 'dispatch':
        image[a.labels['ENTRY_REQUEST']] = 0xc9
    elif mutation == 'return':
        # 正しい応答のあと、通常の要求待ちへ流す故障。
        for label in ('SUB_REQUEST_RETURN', 'REQUEST_DONE'):
            pc = a.labels[label]
            assert image[pc:pc+4] == bytes((0xf7, sub.ENTRY_REQUEST_ACTIVE & 255, 0xb7, 0xc0))
            image[pc+3] = 0
    elif mutation == 'flags':
        pc = a.labels['ENTRY_FDC_RESULT']
        pos = image.index(bytes((0xe6,0xc0)), pc)
        image[pos:pos+2] = bytes((0xf6,0))  # OR 0: 正常時のA=0を保ち、Hだけを壊す
    elif mutation == 'cylinder':
        pc = a.labels['ENTRY_SEEK']
        pos = image.index(bytes((0x7a,0x1f)), pc)
        image[pos+1] = 0  # D>>1を省く
    elif mutation == 'sense':
        pc = a.labels['ENTRY_SEEK']
        for kind, address, size, text in a._emit_asm:
            if address >= pc and text in ('JP FDC_SENSE_DRIVE_STATUS', 'JR FDC_SENSE_DRIVE_STATUS'):
                image[address] = 0xc9
                break
        else:
            raise AssertionError('SENSE DRIVE故障点なし')
    (case / 'DISK.ROM').write_bytes(image)
    args = [str(repo / 'tools/harness/frontend/q88measure'), '--core', str(core),
            '--rom-dir', str(case), '--frames', '600' if sweep else '120', '--sub-cpu-mode', '2',
            '--disk', str(disk), '--io-log', str(case / 'io'),
            '--mem-write-log', str(case / 'mem'), '--mem-write-range', '9000-9003']
    if disk2:
        args += ['--disk2', str(disk)]
    # 未帰還の陰性対照では回収地点（最初の報告送信）自体へ届かない。
    if entry in (0x263, 0x6a6) and expected_return and not fault:
        args += ['--sub-snapshot', str(case / 'snap'), '--sub-snapshot-at-fc', '0']
    result = subprocess.run(args, capture_output=True, timeout=120)
    if result.returncode:
        # 画面本文を表示せず、フロントエンドの診断だけを報告する。
        errors = [line for line in result.stderr.decode(errors='replace').splitlines()
                  if line.startswith('[q88measure]')]
        raise AssertionError(f'{name}: 実行器失敗 rc={result.returncode} {errors}')
    writes = []
    for line in (case / 'mem').read_text().splitlines():
        m = re.fullmatch(r'\s*\d+\s+\d+\s+[0-9a-fA-F]+\s+(900[0123])\s+([0-9a-fA-F]{2})\s*', line)
        if m:
            writes.append((int(m[1], 16), int(m[2], 16)))
    report = bytes(v for addr, v in writes if addr in (0x9000, 0x9001))
    done = (0x9002, 1) in writes
    events = []
    for line in (case / 'io').read_text().splitlines():
        m = re.match(r'\s*\d+\s+\d+\s+\d+\s+sub\s+(IN|OUT)\s+([0-9a-fA-F]{4})\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{4})', line)
        if m:
            events.append((m[1], int(m[2], 16)&255, int(m[3], 16), int(m[4],16)))
    # ロード/実行要求受信の最後(0D,78,00)に対応するDAC解除で起動I/Oを除く。
    starts = [i for i, e in enumerate(events) if e[:3] == ('OUT', 0xff, 0x0c)]
    assert len(starts) >= 1 + len(commands), f'{name}: プローブをロードできない'
    events = events[starts[len(commands)] + 1:]
    if fault or mutation:
        # 正常契約を満たさないことを後段の同じ判定で検証する。
        return done, report, events
    if not expected_return:
        assert not done and not report, f'{name}: 待機せず戻った'
        return done, report, events
    assert done and len(report) == count + response_size + (2 if entry == 0xed else 0), f'{name}: 完了/長さ不一致 {done}/{len(report)}'
    if entry in (0x263, 0x6a6):
        regs = struct.unpack('<18H', (case / 'snap').read_bytes()[-36:])
        # このコアの通常EI/DIはIFF欄で検査する。
        assert (regs[14], regs[16]) == (int(iff), im), f'{name}: IFF/IM不一致'
    return done, report, events


def validate(entry, done, report, events, value, flags, d=0x23):
    assert done
    if entry == 0xed:
        expected = (bytes((0x80,)) if value == 6 else
                    bytes(i ^ 0x5a for i in range(256)) if value == 0x12 else
                    bytes((0x31,0x82,0,0xff,0x55,0xa6)))
        assert report[-2:] == rom[:2], '帰還後の通常要求が失敗'
        report = report[:-2]
        assert report[:len(expected)] == expected, '要求応答がmainへ届かない'
        report = report[len(expected):]
    if entry == 0x263:
        assert len(report) == 25
        result = report[17:24]
        assert report[24] == 0xa5, '結果領域直後を破壊'
        report = report[:17]
        fdc = [(d,p,v) for d,p,v,_ in events if p in (0xfa,0xfb)]
        assert [v for d,p,v in fdc if d == 'OUT' and p == 0xfb] == [
            0x46,0,0,0,1,1,1,0x0e,0xff]
        reads = [v for d,p,v in fdc if d == 'IN' and p == 0xfb]
        assert len(reads) == 256 + 7 and result == bytes(reads[-7:])
        assert result[0] & 0xc0 == 0 and result[1:3] == b'\0\0', 'READ DATAが正常終了していない'
        assert [(d,p) for d,p,_ in fdc[-14:]] == [('IN',0xfa),('IN',0xfb)] * 7
        assert report[12:14] == bytes((0x54, 0)), '正常結果のA/フラグ不一致'
        assert report[15] == 0xa5, '結果領域直前を破壊'
    if entry == 0x6a6:
        assert report[:4] == bytes((0x42,0x81,0x24,0xe3))
        assert report[4:6] == bytes((0x56,0x34))
        assert report[12:14] == bytes((0x10,0x24))
        recv = [(d,p,v) for d,p,v,_ in events if p in (0xfc,0xff)]
        expected = []
        for v in (0x81,0x42,0xe3,0x24):
            expected += [('OUT',0xff,0x0b),('OUT',0xff,0x0a),('IN',0xfc,v),
                         ('OUT',0xff,0x0d),('OUT',0xff,0x0c)]
        assert recv[:len(expected)] == expected, '4バイト受信手順不一致'
    if entry == 0x18:
        assert sum(d == 'OUT' and p == 0xfd for d,p,_,_ in events) == 18
        assert report[0] == value
        report = report[1:]
    assert len(report) == 17
    assert report[10:12] == bytes((0, 0x80)), 'SP不一致'
    if entry in (0x10, 0x18, 0x20, 0x2a4, 0x2a7, 0x2b4, 0x35b, 0x263):
        assert report[:6] == bytes((0x34,0x12,0x45,0x23,0x56,0x34))
    if entry in (0x10, 0x18, 0x20, 0x2a4, 0x2a7, 0x2b4, 0x263, 0x6a6):
        assert report[6:10] == bytes((0x67,0x45,0x78,0x56))
        assert report[16] == 0x3a
    if entry == 0x10:
        assert report[13] == 0x6d
    if entry in (0x20, 0x2a4, 0x2a7):
        assert report[12:14] == bytes((flags, value)), 'AF不一致'
        assert report[15] == (value if entry == 0x2a4 else 0xa5)
        fdc = [(d,p,v) for d,p,v,pc in events if p in (0xfa,0xfb)]
        assert fdc and fdc[0][:2] == ('IN', 0xfa)
        assert [(d,p,v) for d,p,v in fdc if p == 0xfb] == [('OUT',0xfb,value)]
    if entry == 0x2b4:
        assert report[12:14] == bytes((0x44,0))
        assert not any(p in (0xf7,0xf8,0xfa,0xfb) for _,p,_,_ in events)
    if entry == 0x35b:
        outputs = [v for d,p,v,_ in events if d == 'OUT' and p == 0xf7]
        assert outputs == [report[13]]
        assert report[14] != 0xa5  # 書込値の関係そのものは仕様未確定
    if entry == 0x7d6:
        operations = [(p,v) for direction,p,v,_ in events
                      if direction == 'OUT' and p in (0xf8,0xfb)]
        assert operations == [(0xf8,7), (0xfb,15), (0xfb,0), (0xfb,d >> 1),
                              (0xfb,8), (0xfb,4), (0xfb,0)], 'シーク/FDC手順不一致'
    if entry == 0x48f:
        commands = [v for d,p,v,_ in events if d == 'OUT' and p == 0xfb]
        assert commands and commands == [4,1] * (len(commands)//2)


for entry in (*public, 0x2a4):
    value = 6 if entry == 0xed else (4 if entry in (0x20,0x2a4,0x2a7) else 0x35)
    flags = 1
    args = dict(value=value, flags=flags, disk2=entry == 0x48f)
    result = run(entry, **args)
    validate(entry, *result, value, flags)
    result = run(entry, fault=True, **args)
    try:
        validate(entry, *result, value, flags)
    except (AssertionError, IndexError):
        pass
    else:
        raise AssertionError(f'{entry:04X}: 入口+1故障を検出できない')
    print(f'{entry:04X}: RAMプローブ・レジスタ・I/O・入口+1故障 PASS', flush=True)
# ROM内のポインタをRAMプローブが読み、CALL経由で入口へ移る。
result = run(0x7d6, mode='INDIRECT', disk2=True)
validate(0x7d6, *result, 0x35, 1)
result = run(0x7d6, mode='INDIRECT', fault=True, disk2=True)
try:
    validate(0x7d6, *result, 0x35, 1)
except (AssertionError, IndexError):
    pass
else:
    raise AssertionError('02DB: ポインタ+1故障を検出できない')
print('02DB: 間接CALL・ポインタ+1故障 PASS', flush=True)
for entry in (0x10,0x18,0x20):
    value = 4 if entry == 0x20 else 0x35
    validate(entry, *run(entry, mode='RST', value=value), value, 1)
for entry in (0xed,0x2a7,0x48f,0x7d6):
    value = 6 if entry == 0xed else 4
    validate(entry, *run(entry, mode='JP', value=value, disk2=True), value, 1)
for entry in (0x48f,):
    _, _, events = run(entry, expected_return=False)
    assert sum(d == 'OUT' and p == 0xfb and v == 4 for d,p,v,_ in events) > 1
# 全A×F=00/01の確定範囲を一つのRAMプローブで連続検査する。
done, report, events = run(0x2b4, sweep=True)
for index in range(512):
    validate(0x2b4, done, report[index*17:(index+1)*17], events, index & 255, index >> 8)
print('02B4: 全256入力×F=00/01・全512回の保存レジスタ PASS', flush=True)
# 出力値とFの一般則は未確定なので、測定範囲内での入力非依存だけを検査。
baseline = None
for value in (0,1,0x35,0x80,0xff):
    for flags in (0,1,0x40,0xff):
        result = run(0x35b, value=value, flags=flags, mode='JP')
        validate(0x35b, *result, value, flags)
        if baseline is None:
            baseline = result[1]
        assert result[1] == baseline
print('035B: 既知20入力の戻り値一致・F7出力 PASS', flush=True)
for entry in (0x263, 0x6a6):
    for iff in (False, True):
        if entry == 0x263 and iff:
            continue  # 保留IRQのない命令経路は上の静的検査で確認
        for im in (0, 1, 2):
            if not iff and im == 0:
                continue  # 上の通常腕と同じ
            validate(entry, *run(entry, iff=iff, im=im), 0x35, 1)
_, _, events = run(0x6a6, received=(0x81,0x42,0xe3), expected_return=False)
assert sum(d == 'IN' and p == 0xfc for d,p,_,_ in events) == 3
assert sum(d == 'OUT' and p == 0xff and v == 0x0c for d,p,v,_ in events) == 3
print('0263/06A6: IFF・IM保存、06A6の3バイト待機 PASS', flush=True)
for entry in (0x20,0x2a4,0x2a7):
    validate(entry, *run(entry, value=0x80, flags=0xff), 0x80, 0xff)

# 00EDの要求応答とRET、0263のAND、07D6のシリンダ変換を個別に壊す。
for value in (6, 9, 0x12, 0x15):
    for mode in ('CALL', 'JP'):
        validate(0xed, *run(0xed, value=value, mode=mode, flags=0xff), value, 0xff)
    for mutation in ('dispatch', 'return'):
        result = run(0xed, value=value, mutation=mutation)
        try:
            validate(0xed, *result, value, 1)
        except (AssertionError, IndexError):
            pass
        else:
            raise AssertionError(f'00ED {value:02X}: {mutation}故障が通過')
print('00ED: 06/09/12/15応答・CALL/JP帰還・ディスパッチ/RET故障 PASS', flush=True)
for entry, mutation in ((0x263, 'flags'), (0x7d6, 'cylinder'), (0x7d6, 'sense')):
    result = run(entry, mutation=mutation)
    try:
        validate(entry, *result, 0x35, 1)
    except (AssertionError, IndexError):
        pass
    else:
        raise AssertionError(f'{entry:04X}: {mutation}故障が通過')
for d in (0, 1, 2, 0x4f, 0x80, 0xff):
    validate(0x7d6, *run(0x7d6, d=d), 0x35, 1, d=d)
print('0263/07D6: フラグ・SEEKシリンダ・SENSE順序の故障注入 PASS', flush=True)
print(f'sub_rom_entry_selftest: PASS（使用{used}B、残り{0x800-used}B）', flush=True)
