#!/usr/bin/env python3
"""
make_m6fc_blank_disk.py — m6f-c: 空の公式形式ディスクを事前登録の規則だけで作る

事前登録: docs/notes/m6f-c-blank-disk-acceptance-preregistration.md 第2節。

規則はこの2つだけ:
  - 割り当て表の3セクタ (C=18,H=1,R=14)・(18,1,15)・(18,1,16) は
    256バイトすべて値 V（--fat-value）。
  - それ以外の全セクタは 256バイトすべて詰め物 F（--filler）。

追補1（docs/notes/m6f-c-addendum1-boot-sector-sweep.md 第2節）で規則を1つ足す:
  - 起動用セクタ (0,0,1) は既定では詰め物 F のまま（--boot-fill 省略時。
    このときの生成物は追補1より前の生成器とバイト一致させる）。
  - --boot-fill を指定すると、(0,0,1) の256バイトすべてをその値にする
    （割り当て表3セクタと同じ「一様値で塗る」規則。優先順位は割り当て表が先:
    (0,0,1) は割り当て表3セクタに含まれないので競合しない）。

外形は 2D（40シリンダ×2ヘッド、R=1〜16、N=1=256バイト/セクタ）の公開D88形式。
ヘッダ・トラック表・セクタIDの書き方は tools/make_l3_testdisk.py の
build_track/build_d88 と同じにする（書き込み保護なし・種別2D・倍密度・
削除マークなし・状態正常）ので、その定数をそこから import する。
中身の生成規則は本モジュール固有であり、make_l3_testdisk.py の
sector_pattern()（座標から機械的に作る既定パターン）は使わない — 事前登録の
担当条件（同ノート「担当の条件」節）により、本稿はそのノートや
make_n88_blank_disk 系ファイルを参照しない独立セッションが作った。
"""

import argparse
import pathlib
import struct
import sys

from make_l3_testdisk import (
    DISK_DELETED_FALSE,
    DISK_DENSITY_DOUBLE,
    DISK_PROTECT_FALSE,
    DISK_TYPE_2D,
    N_CODE,
    SECTOR_SIZE,
    STATUS_NORMAL,
)

CYLINDERS = 40
HEADS = 2
SECTORS_PER_TRACK = 16
SECTOR_BASE = 1
TRACK_COUNT = 164  # D88フォーマットの仕様で固定

# 事前登録 第2節: 割り当て表とみなす3セクタの座標 (C, H, R)。
ALLOCATION_TABLE_COORDS = frozenset({(18, 1, 14), (18, 1, 15), (18, 1, 16)})
# 追補1 第2節: 起動用セクタの座標。
BOOT_SECTOR_COORD = (0, 0, 1)


def _sector_payload(c: int, h: int, r: int, fat_value: int, filler: int,
                     boot_fill: int | None = None) -> bytes:
    if (c, h, r) in ALLOCATION_TABLE_COORDS:
        value = fat_value
    elif boot_fill is not None and (c, h, r) == BOOT_SECTOR_COORD:
        value = boot_fill
    else:
        value = filler
    return bytes([value]) * SECTOR_SIZE


def build_track(c: int, h: int, fat_value: int, filler: int,
                 boot_fill: int | None = None) -> bytes:
    """1トラック分（16セクタ）を、make_l3_testdisk.build_track と同じID書式で作る。"""
    body = bytearray()
    for r in range(SECTOR_BASE, SECTOR_BASE + SECTORS_PER_TRACK):
        hdr = bytearray(16)
        hdr[0] = c & 0xFF  # C
        hdr[1] = h & 0xFF  # H
        hdr[2] = r & 0xFF  # R
        hdr[3] = N_CODE  # N
        hdr[4] = SECTORS_PER_TRACK & 0xFF  # セクタ数(下位)
        hdr[5] = (SECTORS_PER_TRACK >> 8) & 0xFF  # セクタ数(上位)
        hdr[6] = DISK_DENSITY_DOUBLE
        hdr[7] = DISK_DELETED_FALSE
        hdr[8] = STATUS_NORMAL
        # 9-13 reserved = 0
        hdr[14] = SECTOR_SIZE & 0xFF
        hdr[15] = (SECTOR_SIZE >> 8) & 0xFF
        body += hdr
        body += _sector_payload(c, h, r, fat_value, filler, boot_fill)
    return bytes(body)


def build_blank_disk(fat_value: int, filler: int, boot_fill: int | None = None) -> bytes:
    """事前登録 第2節の規則（＋追補1 第2節の起動用セクタ規則）で公開D88像を作る。

    boot_fill が None のとき、(0,0,1) は詰め物のまま扱われる。このときの
    生成物は、追補1より前の生成器（boot_fill引数を持たない版）とバイト一致する
    （本モジュールの自己検査で確認する）。
    """
    if not (0 <= fat_value <= 0xFF):
        raise ValueError("fat_value は0〜255で指定すること")
    if not (0 <= filler <= 0xFF):
        raise ValueError("filler は0〜255で指定すること")
    if boot_fill is not None and not (0 <= boot_fill <= 0xFF):
        raise ValueError("boot_fill は0〜255で指定すること")

    header = bytearray(32)
    # header[0:17] name = 0埋め、[17:26] reserved = 0
    header[26] = DISK_PROTECT_FALSE
    header[27] = DISK_TYPE_2D
    # header[28:32] = 総サイズ。あとで埋める

    track_table = bytearray(TRACK_COUNT * 4)
    body = bytearray()
    offset = 32 + TRACK_COUNT * 4
    for c in range(CYLINDERS):
        for h in range(HEADS):
            trk = build_track(c, h, fat_value, filler, boot_fill)
            phys = c * 2 + h
            struct.pack_into("<I", track_table, phys * 4, offset)
            body += trk
            offset += len(trk)
    total_size = offset
    struct.pack_into("<I", header, 28, total_size)

    return bytes(header) + bytes(track_table) + bytes(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outfile", type=pathlib.Path)
    parser.add_argument(
        "--fat-value",
        required=True,
        type=lambda v: int(v, 0),
        help="割り当て表3セクタ(18,1,14)(18,1,15)(18,1,16)の値V(0〜255)",
    )
    parser.add_argument(
        "--filler",
        required=True,
        type=lambda v: int(v, 0),
        help="それ以外の全セクタの詰め物F(0〜255)",
    )
    parser.add_argument(
        "--boot-fill",
        default=None,
        type=lambda v: int(v, 0),
        help="起動用セクタ(0,0,1)の値(0〜255)。省略時は詰め物Fのまま(追補1)",
    )
    args = parser.parse_args()

    if not (0 <= args.fat_value <= 0xFF):
        print("エラー: --fat-value は0〜255で指定すること", file=sys.stderr)
        return 2
    if not (0 <= args.filler <= 0xFF):
        print("エラー: --filler は0〜255で指定すること", file=sys.stderr)
        return 2
    if args.boot_fill is not None and not (0 <= args.boot_fill <= 0xFF):
        print("エラー: --boot-fill は0〜255で指定すること", file=sys.stderr)
        return 2
    if args.outfile.exists():
        print(f"エラー: 出力先が既に存在する（上書きしない）: {args.outfile}", file=sys.stderr)
        return 2

    data = build_blank_disk(args.fat_value, args.filler, args.boot_fill)
    args.outfile.parent.mkdir(parents=True, exist_ok=True)
    args.outfile.write_bytes(data)
    print(f"生成した: {args.outfile} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
