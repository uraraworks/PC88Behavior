#!/usr/bin/env bash
# 仕様1.36cの0x09を、自作main→本番subの実Z80実行で検査する。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
for name in ${!PC88_REF_@}; do unset "$name"; done
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* | head -1)}"
# 古いコアにはスナップショットがない。固定済み上流と自前パッチから
# 一時コアを作り、既存のvendorや他の作業には手を加えない。
SYMS="$(nm "$CORE" 2>/dev/null || true)"
if [[ "$SYMS" != *retro_q88h_sub_snapshot_config* || "$SYMS" != *retro_q88h_sub_rom_read_config* ]]; then
  CORE_TREE="$WORK/core"
  mkdir -p "$CORE_TREE"
  git -C "$VENDOR" archive b5a0e044a914c9a6b8d7b2dd2ddd152f93d35687 | \
    tar -xf - -C "$CORE_TREE" --exclude='src/z80-debug.c' \
      --exclude='src/LIBRETRO/pseudo_bios.h' --exclude='src/font.h'
  cp "$REPO"/tools/harness/core/* "$CORE_TREE/src/"
  for patch in "$REPO"/tools/patches/*.patch; do
    git -C "$CORE_TREE" apply --whitespace=nowarn "$patch"
  done
  printf '{ global: *; };\n' > "$CORE_TREE/link.T"
  platform=()
  if [[ "$(uname -s)" == Darwin ]]; then platform=(platform=osx); fi
  if ! make -s -C "$CORE_TREE" "${platform[@]}" -j4 >"$WORK/build.log" 2>&1; then
    cat "$WORK/build.log" >&2
    exit 1
  fi
  CORE="$(ls "$CORE_TREE"/quasi88_libretro.* | head -1)"
fi
make -s -C "$REPO/tools/harness/frontend"
python3 - "$REPO" "$WORK" "$CORE" <<'PY'
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys

repo, work, core = map(Path, sys.argv[1:])
sys.path[:0] = [str(repo), str(repo / 'tools/asm')]
from src.l3_service import make_subrom as sub
import z80text

assert not any(k.startswith('PC88_REF_') for k in os.environ)
rom, used = sub.build()
assert used <= sub.SUB_ROM_FETCH_WINDOW
assert sub._LAST_ASM.labels['FDC_OUT'] == 0x08
assert sub._LAST_ASM.labels['FDC_IN'] == 0x20
assert sub._LAST_ASM.labels['IRQ_HANDLER'] == 0x38
assert sub._LAST_ASM.labels['SUB_REQUEST_RETURN'] == 0xc1
# mainの通信部分だけを使う。別担当のmain生成器・BASICには依存しない。
source = (repo / 'src/l3_main/main_sub_read.asm').read_text()
primitives = source[source.index('MAIN_SUB_WAIT_SET:'):source.index('; PAIR陰性対照用。')]
pattern = bytes((i * 7 + 13) & 255 for i in range(0x3b00))

# 故障版は0x09で受け取った終端だけを1増やす。本番ソースは変更しない。
original = Path(sub.__file__).read_text()
site = '    a.cp_n(0x09)\n    a.jr_z("_general_range_send")'
assert original.count(site) == 1
fault_path = work / 'fault_sub.py'
fault_path.write_text(original.replace(site,
    '    a.cp_n(0x09)\n    a.jr_nz("_req09_no_fault")\n'
    '    a.inc_de()  # 自己検査の終端+1故障\n'
    '    a.label("_req09_no_fault")\n    a.jr_z("_general_range_send")'))
spec = importlib.util.spec_from_file_location('req09_fault_sub', fault_path)
fault = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fault)
fault_rom, _ = fault.build()


def run(name, start, end, request=9, broken=False):
    case = work / name
    case.mkdir()
    # 0x4000..0x7AFFへ0x0Cで模様を書く。状態ページとスタックには書かない。
    header = bytes((12, 0x40, 0, len(pattern) >> 8, len(pattern) & 255))
    command = bytes((request, start >> 8, start & 255, end >> 8, end & 255))
    def data(label, values):
        return label + ':\n' + '\n'.join(
            '    DB ' + ','.join(str(x) for x in values[i:i+32])
            for i in range(0, len(values), 32)) + '\n'
    program = '''    ORG 0
    DI
    LD SP,0FFF0h
    XOR A
    CALL MAIN_SUB_SEND
    JP C,FAIL
    LD HL,PAYLOAD
    LD BC,PAYLOAD_END-PAYLOAD
    CALL SEND_RUN
    LD HL,COMMAND
    LD BC,5
    CALL SEND_RUN
RECEIVE:
    CALL MAIN_SUB_RECV
    JR C,DONE
    LD (09000h),A
    JR RECEIVE
DONE:
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
    JR SEND_ADVANCE
SEND_NEXT:
    LD A,(HL)
    PUSH BC
    CALL MAIN_SUB_SEND_CONT
    POP BC
    JP C,FAIL
SEND_ADVANCE:
    INC HL
    DEC BC
    LD A,B
    OR C
    JR NZ,SEND_NEXT
    RET
MAIN_SUB_TIMEOUT_LIMIT EQU 65535
''' + primitives + data('PAYLOAD', header + pattern) + 'PAYLOAD_END:\n' + data('COMMAND', command)
    if request == 0x15:
        program = program.replace('    CALL MAIN_SUB_RECV\n    JR C,DONE\n    LD (09000h),A',
                                  '    LD HL,09000h\n    CALL MAIN_SUB_RECV_PAIR\n    JR C,DONE')
    asm_path = case / 'main.asm'
    asm_path.write_text(program)
    main = z80text.Assembler().assemble(asm_path)
    assert len(main) <= 0x8000
    (case / 'N88.ROM').write_bytes(main + bytes(0x8000 - len(main)))
    active_rom = fault_rom if broken else rom
    (case / 'DISK.ROM').write_bytes(active_rom)
    # 自作subのRAMのみのスナップショット。1件目送信中の状態を内容照合に使う。
    # 以後のSENDは状態・戻り番地が同じで、RAMへは同じ値しか書かない。
    args = [str(repo / 'tools/harness/frontend/q88measure'), '--core', str(core),
            '--rom-dir', str(case), '--frames', '3000', '--sub-cpu-mode', '2',
            '--mem-write-log', str(case / 'mem'), '--mem-write-range', '9000-9003']
    if request == 9:
        args += ['--sub-snapshot', str(case / 'snap'), '--sub-snapshot-at-fc', '0']
    result = subprocess.run(args, capture_output=True, timeout=120)
    assert result.returncode == 0, f'{name}: 実行器失敗 rc={result.returncode}'
    received = bytearray()
    done = failed = False
    for line in (case / 'mem').read_text().splitlines():
        match = re.fullmatch(r'\s*\d+\s+\d+\s+[0-9A-Fa-f]+\s+(900[0123])\s+([0-9A-Fa-f]{2})\s*', line)
        if match:
            addr, value = int(match[1], 16), int(match[2], 16)
            if addr == 0x9000 or (request == 0x15 and addr == 0x9001):
                received.append(value)
            elif addr == 0x9002:
                done = value == 1
            else:
                failed = value != 0
    assert done and not failed, f'{name}: 完了せず、または送信失敗'
    if request == 9:
        snapshot = (case / 'snap').read_bytes()
        assert len(snapshot) >= 8 + 0x4000
        memory = bytearray([255]) * 0x10000
        memory[:0x800] = active_rom[:0x800]
        memory[0x4000:0x8000] = snapshot[8:8+0x4000]
        # 書き込み自体も独立した模様で検証する（スナップショット同士の比較ではない）。
        assert memory[0x4000:0x7b00] == pattern, f'{name}: 0x0C書込み不一致'
        # 自己検査のコアはsubの32KB空間を上位にもミラーする。
        memory[0x8000:] = memory[:0x8000]
        length = ((end - start) & 0xffff) or 65536
        expected = bytes(memory[(start+i) & 0xffff] for i in range(length))
    else:
        length = end if end >= 2 else 0
        expected = pattern[start-0x4000:start-0x4000+length]
    return len(received) == length and received == expected, len(received)


# 送出終了直後にATNを短く出すmain。旧経路はRFDが上がったままなので
# mainが待たずにATNを解除し、subが次の要求を見失う。
def check_short_atn():
    old = original.replace('    a.out_imm(0xFF, PH_RECV_START_CLR)  # 第235版: 要求待ちはRFDを下げる\n', '')
    gate = ('        a.label("_request_wait_atn")\n'
            '        a.in_port(P_PIO_C)\n'
            '        a.and_a(FE_BIT_IDLE_RECV)\n'
            '        a.jr_z("_request_wait_atn")       # ATNを確認してから受信準備を上げる\n')
    assert old.count(gate) == 1 and old != original
    # RFDを先に上げた要求待ちを故障注入し、ATN取りこぼしを再現する。
    site = '    a.label("_general_range_send")\n'
    assert old.count(site) == 1
    old = old.replace(site, site + '    a.out_imm(0xFF, PH_RECV_START_SET)  # 故障: 送出中にRFDを上げたまま\n')
    path = work / 'old_rfd_sub.py'
    path.write_text(old)
    spec = importlib.util.spec_from_file_location('old_rfd_sub', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old_rom, _ = module.build()
    program = '''    ORG 0
    DI
    LD SP,0FFF0h
    XOR A
    CALL MAIN_SUB_SEND
    JP C,FAIL
    CALL REQUEST
    CALL RECEIVE_4095
    LD A,00Bh
    OUT (0FFh),A
    LD C,1
    CALL MAIN_SUB_WAIT_SET
    JP C,FAIL
    LD A,00Ah
    OUT (0FFh),A
    IN A,(0FCh)
    LD (09000h),A
    LD A,00Dh
    OUT (0FFh),A
FINAL_WAIT:
    IN A,(0FEh)
    AND 1
    JR NZ,FINAL_WAIT
    LD A,00Ch
    OUT (0FFh),A
    LD A,00Fh
    OUT (0FFh),A
FAST_WAIT:
    IN A,(0FEh)
    AND 2
    JR Z,FAST_WAIT
    LD A,00Eh
    OUT (0FFh),A
    LD A,9
    OUT (0FDh),A
    LD A,9
    OUT (0FFh),A
    LD C,4
    CALL MAIN_SUB_WAIT_SET
    JP C,FAIL
    LD A,8
    OUT (0FFh),A
    XOR A
    CALL MAIN_SUB_SEND_CONT
    JP C,FAIL
    XOR A
    CALL MAIN_SUB_SEND_CONT
    JP C,FAIL
    LD A,010h
    CALL MAIN_SUB_SEND_CONT
    JP C,FAIL
    XOR A
    CALL MAIN_SUB_SEND_CONT
    JP C,FAIL
    CALL RECEIVE_4096
    LD A,1
    LD (09002h),A
STOP:
    JR STOP
FAIL:
    LD A,1
    LD (09003h),A
    JR STOP
REQUEST:
    LD A,9
    CALL MAIN_SUB_SEND
    JP C,FAIL
    XOR A
    CALL MAIN_SUB_SEND_CONT
    JP C,FAIL
    XOR A
    CALL MAIN_SUB_SEND_CONT
    JP C,FAIL
    LD A,010h
    CALL MAIN_SUB_SEND_CONT
    JP C,FAIL
    XOR A
    CALL MAIN_SUB_SEND_CONT
    JP C,FAIL
    RET
RECEIVE_4095:
    LD HL,4095
COUNT_LOOP:
    PUSH HL
    CALL MAIN_SUB_RECV
    JP C,FAIL
    LD (09000h),A
    POP HL
    DEC HL
    LD A,H
    OR L
    JR NZ,COUNT_LOOP
    RET
RECEIVE_4096:
    LD B,010h
OUTER:
    PUSH BC
    LD B,0
INNER:
    PUSH BC
    CALL MAIN_SUB_RECV
    JP C,FAIL
    LD (09000h),A
    POP BC
    DJNZ INNER
    POP BC
    DJNZ OUTER
    RET
MAIN_SUB_TIMEOUT_LIMIT EQU 65535
''' + primitives
    for name, image, expected in (('short_atn', rom, True), ('short_atn_fault', old_rom, False)):
        case = work / name
        case.mkdir()
        path = case / 'main.asm'
        path.write_text(program)
        main = z80text.Assembler().assemble(path)
        (case / 'N88.ROM').write_bytes(main + bytes(0x8000 - len(main)))
        (case / 'DISK.ROM').write_bytes(image)
        args = [str(repo / 'tools/harness/frontend/q88measure'), '--core', str(core),
                '--rom-dir', str(case), '--frames', '1500', '--sub-cpu-mode', '2',
                '--mem-write-log', str(case / 'mem'), '--mem-write-range', '9000-9003']
        result = subprocess.run(args, capture_output=True, timeout=120)
        assert result.returncode == 0, f'{name}: 実行器失敗'
        writes = []
        for line in (case / 'mem').read_text().splitlines():
            match = re.fullmatch(r'\s*\d+\s+\d+\s+[0-9A-Fa-f]+\s+(900[023])\s+([0-9A-Fa-f]{2})\s*', line)
            if match:
                writes.append((int(match[1], 16), int(match[2], 16)))
        values = bytes(value for addr, value in writes if addr == 0x9000)
        done = (0x9002, 1) in writes
        if expected:
            assert done and len(values) == 8192 and values[:4096] == values[4096:], f'{name}: 完了または内容不一致 {len(values)}'
        else:
            assert not done and len(values) == 4096, f'{name}: 旧経路の停止を再現できない {len(values)}'
    print('短いATN・0x09連続要求・旧経路故障注入: PASS', flush=True)

check_short_atn()

arms = [('one', 0x5000, 0x5001), ('sixteen', 0x5000, 0x5010),
        ('page', 0x5000, 0x5100), ('full', 0x5000, 0x5000),
        ('wrap', 0xff00, 0x0010), ('odd', 0x50ff, 0x5110)]
for name, start, end in arms:
    passed, count = run(name, start, end)
    assert passed, f'{name}: 受信長または内容が不一致（受信{count}件）'
    passed, count = run(name + '_fault', start, end, broken=True)
    fault_length = ((end - start + 1) & 0xffff) or 65536
    assert count == fault_length, f'{name}: 故障版が意図した受信長でない'
    assert not passed, f'{name}: 終端+1故障を検出できない'
    print(f'0x09 {name}: 長さ・全内容・終端+1故障 PASS', flush=True)
for length in (0, 1, 16, 256):
    passed, count = run(f'req15_{length}', 0x5000, length, request=0x15)
    assert passed, f'0x15 長さ{length}: 不一致（受信{count}件）'
print(f'l3_sub_req09_selftest: PASS（使用{used}B、空き{2048-used}B）')
PY
