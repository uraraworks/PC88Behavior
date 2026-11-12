#!/usr/bin/env python3
"""B86 の自作起動セクタと D88 像を生成する。値は自作入力のみ。"""
import argparse
from pathlib import Path
from b2_make_boot_probe import build_disk

TARGETS = {'369a': 0x369a, '37c9': 0x37c9, '37d2': 0x37d2,
           '3847': 0x3847, 'negative': 0xc0f0, 'positive': 0xc0e0}
ARMS = ('zero', 'a', 'bc', 'de', 'hl', 'flags', 'mem-hl-zero', 'mem-hl-one', 'mem-de-zero', 'mem-de-one')
def w(n): return bytes((n & 255, n >> 8))
def generate(target, arm, fault=False):
    # メモリの初期化・レジスタ設定はすべて CALL より前に行う。
    v = {'a': 0, 'bc': 0, 'de': 0, 'hl': 0, 'f': 0}
    for key in ('a', 'bc', 'de', 'hl'):
        if arm == key: v[key] = 1
    if arm == 'flags': v['f'] = 1
    if arm.startswith('mem-hl-'): v['hl'] = 0xd000
    if arm.startswith('mem-de-'): v['de'] = 0xd100
    code = bytearray(b'\xf3\x31\x00\xf0')  # DI; SP=F000
    for addr in (0xd000, 0xd100):
        value = int((arm == 'mem-hl-one' and addr == 0xd000) or (arm == 'mem-de-one' and addr == 0xd100))
        code += b'\x3e' + bytes([value]) + b'\x32' + w(addr)
    # 対象 RAM の事前写し。C100-EFFF を専用ポートへ順に送る。
    code += b'\x21\x00\xc1\x01\x00\x2f\xcd\x80\xc0'
    code += b'\x21' + w((v['a'] << 8) | v['f']) + b'\xe5\xf1'
    code += b'\x01' + w(v['bc']) + b'\x11' + w(v['de']) + b'\x21' + w(v['hl'])
    code += b'\xd3\x7f'  # 印: A とフラグを変えない
    code += b'\xcd' + w(TARGETS[target])
    code += b'\xd3\x7f'  # 戻りの印
    # PUSH はフラグを変えない。戻り時 HL, DE, BC, AF を専用領域に退避。
    code += b'\xe5\xd5\xc5\xf5'
    for addr in (0xc0c0, 0xc0c2, 0xc0c4, 0xc0c6):
        code += b'\xe1\x22' + w(addr)
    code += b'\xed\x73\xc8\xc0\x3e\xa5\x32\xca\xc0'
    code += b'\x21\x00\xc1\x01\x00\x2f\xcd\x80\xc0\xf3\x76\x18\xfd'
    if len(code) > 0xc0: raise ValueError('コードが記録域に重なる')
    sector = code + bytes(256-len(code))
    # LD A,(HL); OUT (7D),A; INC HL; DEC BC; LD A,B; OR C; JR NZ; RET
    sector[0x80:0x8a] = bytes.fromhex('7e d3 7d 23 0b 78 b1 20 f7 c9')
    # 陽性対照: RAM を変更し OUT を1回、キャリーを立てて戻る。
    positive = b'\x3e\x5a' + (b'\x00\x00\x00' if fault else b'\x32\x00\xd0') + b'\xd3\x7e\x37\xc9'
    sector[0xe0:0xe0+len(positive)] = positive
    sector[0xf0] = 0xc9
    return bytes(sector)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target', choices=TARGETS, required=True)
    p.add_argument('--arm', choices=ARMS, required=True)
    p.add_argument('--disk', type=Path, required=True)
    p.add_argument('--sector', type=Path)
    p.add_argument('--fault-no-write', action='store_true', help='自己検査専用')
    a = p.parse_args()
    if a.disk.exists() or (a.sector and a.sector.exists()): p.error('出力先が既に存在します')
    s = generate(a.target, a.arm, a.fault_no_write)
    a.disk.write_bytes(build_disk(s, 'none'))
    if a.sector: a.sector.write_bytes(s)
if __name__ == '__main__': main()
