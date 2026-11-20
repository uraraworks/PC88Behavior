#!/usr/bin/env python3
"""自作ROMと合成相手だけで受信領域・WRITE・スタックを検査する。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/l3_service'))
from subrom_atn_selftest import CPU, sub


class Memory(bytearray):
    def __setitem__(self, key, value):
        if isinstance(key, int):
            self.writes.add(key)
        super().__setitem__(key, value)


class CheckedCPU(CPU):
    def __init__(self, rom, peer):
        super().__init__(rom, peer)
        self.mem = Memory(self.mem)
        self.mem.writes = set()
        self.min_sp = self.sp
        peer.cpu = self

    def push(self, value):
        super().push(value)
        self.min_sp = min(self.min_sp, self.sp)


class Peer:
    """PIOは立上り/解除に従う。FDCはコマンドごとの送受信数を検証する。"""
    def __init__(self, data):
        self.data = list(data)
        self.fe = 8
        self.reads = 0
        self.fdcs = []
        self.current = []
        self.remaining = 0
        self.results = 0
        self.irq = False

    def read(self, port):
        if port == 0xFE:
            return self.fe
        if port == 0xFC:
            assert self.data, '要求を越えて受信した'
            self.reads += 1
            return self.data.pop(0)
        if port == 0xFA:
            # FDC_WAITの最深点でも割込み4バイト分の余裕を検査する。
            if not self.irq:
                self.irq = True
                pc = self.cpu.pc
                self.cpu.push(pc)
                self.cpu.run(0x38, pc)
                self.irq = False
            return 0xC0 if self.results else 0x80
        if port == 0xFB:
            assert self.results
            self.results -= 1
            return 0
        assert port == 0xF8
        return 0

    def write(self, port, value):
        if port == 0xFF:
            if value == 0x0B:
                self.fe = 9
            elif value == 0x0D:
                self.fe = 8
        elif port == 0xFB:
            assert not self.results
            if not self.remaining:
                assert value in (0x0F, 8, 4, 0x45), value
                self.current = []
                self.remaining = {0x0F: 3, 8: 1, 4: 2, 0x45: 265}[value]
            self.current.append(value)
            self.remaining -= 1
            if not self.remaining:
                self.fdcs.append(self.current)
                self.results = {0x0F: 0, 8: 2, 4: 1, 0x45: 7}[self.current[0]]


def payload(n):
    return bytes((i * 73 + (i >> 8) * 19 + 37) & 255 for i in range(n))


def word(n):
    return [n >> 8, n & 255]


def main(fault=None):
    rom, used = sub.build()
    labels = sub._LAST_ASM.labels
    if fault:
        rom = bytearray(rom)
        if fault == 'game_buffer':
            pc = labels['_recv_dispatch_write_stream']
            assert rom[pc] == 0x21  # LD HL,nn
            rom[pc + 1:pc + 3] = bytes((0, 0x61))
        else:
            assert fault == 'fixed_entry_overlap'
            pc = labels['WRITE_NEXT']
            assert rom[pc:pc + 4] == bytes((0x23, 0x7D, 0xFE, 0x0B))
            rom[pc + 3] = 0xFF  # 7F0Bを飛び越さない故障
    # 配置の仕様を実装定数と独立に固定し、固定入口用の穴を含めて検査する。
    slots = list(range(0x7EC0, 0x7F0B)) + list(range(0x7F14, 0x7FC9))
    assert len(slots) == 256 and used <= 2048
    lowest_sp = sub.STACK
    for kind in (0x0C, 0x16):
        for addr, count in ((0x6000, 512), (0x6F80, 3840), (0x6001, 2), (0x6000, 0)):
            body = payload(count)
            request = [kind] + word(addr) + word(count) + list(body)
            following = [2, 1, 0, 2, 3]
            peer = Peer(request + following)
            cpu = CheckedCPU(rom, peer)
            cpu.mem[0x4000:0x7E80] = payload(0x3E80)
            before = bytes(cpu.mem[0x4000:0x7E80])
            cpu.run(0xC1, labels['_general_read_request'])
            assert not peer.data and peer.reads == len(request) + 5
            assert cpu.mem[sub.REQ_HDR + 1:sub.REQ_HDR + 5] == bytes(following[1:])
            expected = bytearray(before)
            expected[addr - 0x4000:addr - 0x4000 + count] = body
            assert cpu.mem[0x4000:0x7E80] == expected
            assert cpu.mem.writes <= set(range(addr, addr + count)) | set(range(0x7E80, 0x8000))
            lowest_sp = min(lowest_sp, cpu.min_sp)

    # 両領域を同じCPUへ続けてロードし、その後の5バイト要求まで走らせる。
    request = []
    for addr, count in ((0x6000, 512), (0x6F80, 3840)):
        request += [0x0C] + word(addr) + word(count) + list(payload(count))
    peer = Peer(request + [2, 1, 0, 2, 3])
    cpu = CheckedCPU(rom, peer)
    cpu.run(0xC1, labels['_general_read_request'])
    assert not peer.data and peer.reads == len(request) + 5
    assert cpu.mem[0x6000:0x6200] == payload(512)
    assert cpu.mem[0x6F80:0x7E80] == payload(3840)

    # 長い通常runでも16バイト以降は格納しない。窓位置と長さはFFで飽和。
    cpu = CheckedCPU(rom, Peer([]))
    for value in payload(600):
        cpu.r[7] = value
        cpu.push(0x7000)
        cpu.run(labels['HDR_STORE_AND_CHECK'], 0x7000)
    assert cpu.mem[sub.REQ_HDR:sub.REQ_HDR + 16] == payload(16)
    assert cpu.mem[sub.RUN_LEN] == cpu.mem[sub.WINDOW_RUN_POS] == 255
    assert cpu.mem.writes <= set(range(0x7E80, 0x7EC0)) | set(range(0x7FC9, 0x8000))

    # 0x02/0x0Eの通常ディスパッチでヘッダ、受信窓、起動バルクを保護する。
    for request, target in (([2, 1, 0, 2, 3], '_general_read_request'),
                            ([14, 2, 0, 2, 3, 0x60, 0], '_exchange14_prepare_first_read')):
        peer = Peer(request)
        cpu = CheckedCPU(rom, peer)
        cpu.mem[sub.POST_BULK_ACTIVE] = 1
        cpu.mem[0x4400:0x7400] = payload(0x3000)
        before = bytes(cpu.mem[0x4400:0x7400])
        cpu.run(labels['RECV_DISPATCH'], labels[target])
        assert not peer.data and cpu.mem[sub.REQ_HDR:sub.REQ_HDR + len(request)] == bytes(request)
        assert cpu.mem[sub.WINDOW_RUN_POS] == len(request)
        assert cpu.mem[sub.WINDOW_RUN_HEAD] == request[0]
        assert cpu.mem[0x4400:0x7400] == before
        assert cpu.mem.writes <= set(range(0x7E80, 0x8000))

    # 連続WRITE。D/T/Rと全256バイトをFDC出力で確認し、固定入口・ゲーム域を保護。
    for drive, track, sector in ((0, 6, 5), (1, 7, 16)):
        cpu = None
        for previous in (drive, 6):
            data = payload(256)
            peer = Peer([0x11, 1, drive, track, sector] + list(data))
            if cpu is None:
                cpu = CheckedCPU(rom, peer)
                cpu.mem[sub.POST_BULK_ACTIVE] = 1
            else:
                cpu.io, peer.cpu = peer, cpu
            cpu.mem[sub.WRITE_LAST_S] = previous
            cpu.mem[0x4000:0x7E80] = payload(0x3E80)
            before = bytes(cpu.mem[0x4000:0x7E80])
            cpu.run(labels['RECV_DISPATCH'], labels['IDLE_DISPATCH'])
            assert peer.reads == 261 and not peer.data and not peer.results
            assert [x[0] for x in peer.fdcs] == [0x0F, 8, 4, 0x45]
            write = peer.fdcs[-1]
            assert write[:9] == [0x45, drive | ((track & 1) << 2), track >> 1,
                                 track & 1, sector, 1, 16, 0x0E, 0xFF]
            assert bytes(write[9:]) == data
            assert bytes(cpu.mem[x] for x in slots) == data
            assert cpu.mem[0x4000:0x7E80] == before
            assert cpu.mem.writes <= set(range(0x7E80, 0x8000))
            assert not cpu.mem.writes & set(range(0x7F0B, 0x7F14))
            assert cpu.min_sp >= 0x7FC9
            assert cpu.mem[sub.WINDOW_RUN_POS] == 0
            lowest_sp = min(lowest_sp, cpu.min_sp)

    print(f'PASS: LOAD/paired LOAD→02、通常ヘッダ、WRITE256、作業域保護、最低SP={lowest_sp:04X}')


if __name__ == '__main__':
    main()
    for fault in ('game_buffer', 'fixed_entry_overlap'):
        try:
            main(fault)
        except AssertionError:
            pass
        else:
            raise AssertionError(f'故障を見逃した: {fault}')
    print('PASS: ゲーム領域への配置・固定入口への重なりの故障を検出')
