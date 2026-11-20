#!/usr/bin/env python3
"""自作ROMだけで0x15のATN境界と容量圧縮の保存規約を検査する。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_subrom as sub


class CPU:
    """検査経路のZ80命令をバイト列から実行する。未知命令は失敗する。"""

    def __init__(self, rom, io=None):
        self.mem = bytearray(65536)
        self.mem[:len(rom)] = rom
        self.r = [0] * 8              # B,C,D,E,H,L,(HL),A
        self.f = 0
        self.pc, self.sp = 0, 0x7FFE
        self.io = io
        self.outputs = []

    def pair(self, i):
        return self.r[i] * 256 + self.r[i + 1]

    def put_pair(self, i, value):
        self.r[i:i + 2] = [(value >> 8) & 255, value & 255]

    def byte(self):
        v = self.mem[self.pc]
        self.pc = (self.pc + 1) & 65535
        return v

    def word(self):
        lo = self.byte()
        return lo | self.byte() << 8

    def read16(self, addr):
        return self.mem[addr] | self.mem[(addr + 1) & 65535] << 8

    def write16(self, addr, v):
        self.mem[addr] = v & 255
        self.mem[(addr + 1) & 65535] = v >> 8

    def push(self, v):
        self.sp = (self.sp - 2) & 65535
        self.write16(self.sp, v)

    def pop(self):
        v = self.read16(self.sp)
        self.sp = (self.sp + 2) & 65535
        return v

    def get(self, i):
        return self.mem[self.pair(4)] if i == 6 else self.r[i]

    def put(self, i, v):
        if i == 6:
            self.mem[self.pair(4)] = v
        else:
            self.r[i] = v

    def logic(self, value, half=0):
        self.r[7] = value & 255
        self.f = ((value & 0xA8) | (0x40 if value == 0 else 0)
                  | (4 if value.bit_count() % 2 == 0 else 0) | half)

    def cond(self, n):
        return (not self.f & 0x40, bool(self.f & 0x40),
                not self.f & 1, bool(self.f & 1))[n]

    def run(self, start, stop, limit=400000):
        self.pc = start
        for _ in range(limit):
            if self.pc == stop:
                return
            pc, op = self.pc, self.byte()
            if op == 0:
                pass
            elif 0x40 <= op < 0x80 and op != 0x76:
                self.put((op >> 3) & 7, self.get(op & 7))
            elif op & 0xC7 == 6:
                self.put((op >> 3) & 7, self.byte())
            elif op in (1, 0x11, 0x21, 0x31):
                v = self.word()
                if op == 0x31:
                    self.sp = v
                else:
                    self.put_pair((op >> 3) & 6, v)
            elif op in (3, 0x13, 0x23, 0x0B, 0x1B, 0x2B):
                i = (op >> 3) & 6
                self.put_pair(i, self.pair(i) + (-1 if op & 8 else 1))
            elif op == 0x3C:
                old, carry = self.r[7], self.f & 1
                self.logic((old + 1) & 255)
                self.f = ((self.f & ~5) | carry | (4 if old == 127 else 0)
                          | (0x10 if old & 15 == 15 else 0))
            elif op in (0x12, 0x1A):
                if op == 0x12:
                    self.mem[self.pair(2)] = self.r[7]
                else:
                    self.r[7] = self.mem[self.pair(2)]
            elif op in (0x22, 0x2A, 0x32, 0x3A):
                addr = self.word()
                if op == 0x22:
                    self.write16(addr, self.pair(4))
                elif op == 0x2A:
                    self.put_pair(4, self.read16(addr))
                elif op == 0x32:
                    self.mem[addr] = self.r[7]
                else:
                    self.r[7] = self.mem[addr]
            elif op in (0xE6, 0xB0, 0xB3, 0xB7, 0xAF, 0xA7):
                a = self.r[7]
                if op == 0xE6:
                    self.logic(a & self.byte(), 0x10)
                elif op == 0xAF:
                    self.logic(0)
                elif op == 0xA7:
                    self.logic(a, 0x10)
                else:
                    self.logic(a | self.get(op & 7))
            elif op in (0xFE, 0xB8):
                n, a = self.byte() if op == 0xFE else self.r[0], self.r[7]
                result = (a - n) & 255
                self.f = ((result & 0x80) | (n & 0x28) | 2
                          | (0x40 if a == n else 0) | (1 if a < n else 0)
                          | (0x10 if (a ^ n ^ result) & 16 else 0)
                          | (4 if (a ^ n) & (a ^ result) & 128 else 0))
            elif op in (7, 0x0F, 0x1F):
                a, carry = self.r[7], self.f & 1
                if op == 7:
                    bit, a = a >> 7, ((a << 1) | (a >> 7)) & 255
                else:
                    bit, a = a & 1, (a >> 1) | ((a & 1 if op == 15 else carry) << 7)
                self.r[7], self.f = a, (self.f & 0xC4) | (a & 0x28) | bit
            elif op == 0xCB:
                ext = self.byte()
                assert 0x80 <= ext <= 0xFF, (pc, ext)
                bit = 1 << ((ext >> 3) & 7)
                value = self.get(ext & 7)
                self.put(ext & 7, value | bit if ext >= 0xC0 else value & ~bit)
            elif op in (0xC5, 0xD5, 0xE5, 0xF5):
                self.push(self.r[7] << 8 | self.f if op == 0xF5 else self.pair((op >> 3) & 6))
            elif op in (0xC1, 0xD1, 0xE1, 0xF1):
                v = self.pop()
                if op == 0xF1:
                    self.r[7], self.f = v >> 8, v & 255
                else:
                    self.put_pair((op >> 3) & 6, v)
            elif op == 0xE3:
                v = self.read16(self.sp)
                self.write16(self.sp, self.pair(4))
                self.put_pair(4, v)
            elif op == 0xEB:
                de = self.pair(2)
                self.put_pair(2, self.pair(4))
                self.put_pair(4, de)
            elif op in (0xC3, 0xC2, 0xCA, 0xD2, 0xDA, 0xCD):
                target = self.word()
                if op == 0xCD:
                    self.push(self.pc)
                if op in (0xC3, 0xCD) or self.cond((op >> 3) & 3):
                    self.pc = target
            elif op in (0x18, 0x20, 0x28, 0x30, 0x38):
                delta = self.byte()
                if op == 0x18 or self.cond((op >> 3) & 3):
                    self.pc = (self.pc + (delta if delta < 128 else delta - 256)) & 65535
            elif op in (0xC9, 0xC0, 0xC8):
                if op == 0xC9 or self.cond((op >> 3) & 3):
                    self.pc = self.pop()
            elif op & 0xC7 == 0xC7:
                self.push(self.pc)
                self.pc = op & 0x38
            elif op == 0xE9:
                self.pc = self.pair(4)
            elif op == 0xED:
                assert self.byte() in (0x46, 0x56)  # IM 0/1
            elif op in (0xDB, 0xD3):
                port = self.byte()
                if op == 0xDB:
                    self.r[7] = self.io.read(port)
                else:
                    self.outputs.append((port, self.r[7]))
                    if self.io:
                        self.io.write(port, self.r[7])
            else:
                raise AssertionError(f'未対応命令 {op:02X} at {pc:04X}')
        raise AssertionError('実行上限（待ち合い）')


class Peer:
    """独立したmain側モデル。偶数境界ではATNを遅らせる腕も検査する。"""

    def __init__(self, cut=None, delay=0, first_ack=False, params=None):
        self.cut, self.delay, self.first_ack = cut, delay, first_ack
        self.data, self.fe, self.polls = [], 2, 0
        self.request = [0x0D, 0x70, 0]  # 打ち切った直後に別要求を実行
        self.receiving = False
        self.params = None if params is None else list(params)

    def read(self, port):
        if port == 0xFE:
            if self.fe == 0:
                self.polls += 1
                if self.polls > self.delay:
                    self.fe = 8 if len(self.data) == self.cut else 2
            return self.fe
        assert port == 0xFC and self.request
        if self.params is not None:
            return self.params.pop(0)
        return self.request.pop(0)

    def write(self, port, value):
        if port == 0xFD:
            self.data.append(value)
        elif port == 0xFF:
            if value == 9:
                self.fe = (8 | (4 if self.first_ack else 0)) if len(self.data) == self.cut else 4
            elif value == 8:
                self.fe, self.polls = 0, 0
            elif value == 0x0A and not self.receiving and len(self.data) == self.cut:
                self.fe, self.polls = 0, 0
            elif value == 0x0B:
                self.receiving, self.fe = True, 9
            elif value == 0x0D and self.receiving:
                self.fe = 0 if self.params is not None else 8
            elif value == 0x0C and self.params == []:
                self.params, self.receiving, self.fe = None, False, 2


def main():
    rom, used = sub.build()
    labels = sub._LAST_ASM.labels
    assert used <= 2048
    assert not sub.find_fetch_window_straddles(sub._LAST_ASM)
    assert not sub.find_out_of_window_blocks(sub._LAST_ASM)
    assert rom[0x29A:0x2A4] == bytes.fromhex('DB FA E6 80 28 FA DB FB C9 00')
    # ASM表記も独立した既存アセンブラで再組立てし、新規命令を含め全バイト照合。
    import z80text
    asm = z80text.Assembler()
    asm.lines = [z80text.parse_line(i, line) for i, line in
                 enumerate(sub.render_asm(sub._LAST_ASM).splitlines(), 1)]
    asm.pass1(asm.lines)
    asm.resolve_equs()
    asm.pass2(asm.lines)
    assert asm.code == rom[:used]
    # 四種類のインライン操作を全引数・複数のAFで検査。保存対象は全バイト比較。
    for operand in range(256):
        for af in (0, 0xFFFF, 0xA55A, 0x0181):
            cpu = CPU(rom)
            cpu.r = [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0, af >> 8]
            cpu.f = af & 255
            cpu.mem[0x7000:0x7002] = bytes((0xF7, operand))
            # 状態ページの移動先で全インライン引数を検査する。
            addr = sub.HDR_PTR | (operand & 63)
            cpu.mem[addr] = operand ^ 0xA5
            cpu.run(0x7000, 0x7002)
            mode = operand & 0xC0
            assert cpu.r[:6] == [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC]
            assert cpu.sp == 0x7FFE
            expected = (operand ^ 0xA5) if mode in (0, 0xC0) else (operand & 63 if mode == 64 else af >> 8)
            assert cpu.r[7] == expected
            if mode == 0xC0:
                assert cpu.f == ((expected & 0xA8) | (64 if not expected else 0)
                                 | (4 if expected.bit_count() % 2 == 0 else 0))
            else:
                assert cpu.f == af & 255
            assert cpu.mem[addr] == (af >> 8 if mode == 128 else operand ^ 0xA5)
            assert cpu.outputs == ([(255, operand & 63)] if mode == 64 else [])
    # 06A6: HLを使わないF=10設定でも全レジスタ・SPを保持する。
    for values in ([0, 0, 0, 0], [255, 128, 32, 255], [1, 2, 3, 4]):
        peer = Peer()
        peer.request = list(values)
        cpu = CPU(rom, peer)
        cpu.put_pair(4, 0xABCD)
        cpu.push(0x7000)
        cpu.run(0x6A6, 0x7000)
        assert cpu.r[:4] == list(values) and cpu.pair(4) == 0xABCD
        assert (cpu.r[7], cpu.f, cpu.sp) == (values[-1], 0x10, 0x7FFE)
    # 0/2/4だけを進める圧縮判定。未使用の状態値も含め全256値で照合する。
    advance = labels['_advance_boot_read_pair_stage']
    stage_start = rom.rfind(bytes((0xF7, sub.BOOT_READ_PAIR_STAGE & 63, 0xFE, 5)),
                           advance - 16, advance)
    assert stage_start >= 0
    for stage in range(256):
        cpu = CPU(rom)
        cpu.mem[sub.BOOT_READ_PAIR_STAGE] = stage
        cpu.run(stage_start, labels['_boot_read_pair_stage_done'])
        assert cpu.mem[sub.BOOT_READ_PAIR_STAGE] == stage + (stage in (0, 2, 4))
    pattern = bytes((i * 7 + 13) & 255 for i in range(4096))
    for length, cut in [(4096, n) for n in (1, 2, 255, 256, 257, 4095, 4096)] + [(n, None) for n in (0, 1, 16, 256, 512)]:
        expected = cut if cut is not None else length - length % 2
        for delay in (0, 7):
            for first_ack in (False, True):
                peer = Peer(cut if cut is not None else expected, delay, first_ack)
                cpu = CPU(rom, peer)
                cpu.mem[0x5000:0x6000] = pattern
                cpu.r[0] = 0x15
                cpu.put_pair(4, 0x5000)
                cpu.put_pair(2, length + 1)
                cpu.run(labels['_general_load_check'], 0x7000)
                assert bytes(peer.data) == pattern[:expected], (length, cut, delay)
                assert not peer.request and cpu.sp == 0x8000
    # 00EDからの要求にも同じ打ち切りを適用し、CALL元のスタックへ正しく戻す。
    for cut in (1, 256, None):
        peer = Peer(cut, delay=7, params=[0x50, 0, 0x10, 0])
        cpu = CPU(rom, peer)
        cpu.mem[0x5000:0x6000] = pattern
        cpu.r[7] = 0x15
        cpu.push(0x7000)
        cpu.run(0xED, 0x7000)
        assert bytes(peer.data) == (pattern[:cut] if cut is not None else pattern)
        assert cpu.sp == 0x7FFE and cpu.mem[sub.ENTRY_REQUEST_ACTIVE] == 0
    # 通常読み応答のBはFE bit1=1。ATNがあっても従来の2件を完了する。
    for b in range(256):
        if not b & 2:
            continue
        peer = Peer(1, first_ack=True)
        cpu = CPU(rom, peer)
        cpu.mem[0x5000:0x5002] = pattern[:2]
        cpu.r[0], cpu.r[1] = b, 0xA5
        cpu.put_pair(2, 0x1357)
        cpu.put_pair(4, 0x5000)
        cpu.push(0x7000)
        cpu.run(labels['SEND_BUFFER_PAIR'], 0x7000)
        assert bytes(peer.data) == pattern[:2]
        assert cpu.pair(0) == b * 256 + 0xA5 and cpu.pair(2) == 0x1357
        assert cpu.pair(4) == 0x5002 and cpu.sp == 0x7FFE
    # ATN検査を無効化した故障版は256件で次要求へ戻れない。
    broken = bytearray(rom)
    site = labels['_request15_next_pair'] + 2
    assert broken[site:site + 2] == bytes((0xE6, 10))
    broken[site + 1] = 2
    peer = Peer(256, delay=7)
    cpu = CPU(broken, peer)
    cpu.r[0] = 0x15
    cpu.put_pair(4, 0x5000)
    cpu.put_pair(2, 4097)
    try:
        cpu.run(labels['_general_load_check'], 0x7000, limit=40000)
    except AssertionError as exc:
        assert str(exc) == '実行上限（待ち合い）'
    else:
        raise AssertionError('ATN無視故障を検出できない')
    print(f'PASS: 状態アクセス1024条件・06A6・ATN全境界/遅延・次要求・通常応答128条件・故障検出（{used}/2048B）')


if __name__ == '__main__':
    main()
