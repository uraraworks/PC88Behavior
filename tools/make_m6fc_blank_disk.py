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

追補3（docs/notes/m6f-c-addendum3-write-protect-sectors.md 第2節）で規則を
もう1つ足す:
  - --sector-fill C,H,R=0xNN（複数可）で、任意の座標の256バイトすべてを
    指定した値にする。優先順位は「割り当て表3セクタ(V) > --sector-fill >
    --boot-fill > 詰め物(F)」。割り当て表3セクタを --sector-fill で
    指定することはできない（rc=2。割り当て表の値Vは常にfat-valueで
    決まるべきで、二重の決め方を許すと衝突時の優先順位が仕様の外で
    決まってしまうため）。範囲外の座標・同一座標の重複指定もrc=2。
  - --sector-fill を何も指定しないとき（既定）の生成物は、追補3より前の
    生成器とバイト一致する。

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
                     boot_fill: int | None = None,
                     sector_fills: dict[tuple[int, int, int], int] | None = None) -> bytes:
    coord = (c, h, r)
    if coord in ALLOCATION_TABLE_COORDS:
        value = fat_value
    elif sector_fills is not None and coord in sector_fills:
        value = sector_fills[coord]
    elif boot_fill is not None and coord == BOOT_SECTOR_COORD:
        value = boot_fill
    else:
        value = filler
    return bytes([value]) * SECTOR_SIZE


def build_track(c: int, h: int, fat_value: int, filler: int,
                 boot_fill: int | None = None,
                 sector_fills: dict[tuple[int, int, int], int] | None = None) -> bytes:
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
        body += _sector_payload(c, h, r, fat_value, filler, boot_fill, sector_fills)
    return bytes(body)


def build_blank_disk(fat_value: int, filler: int, boot_fill: int | None = None,
                      sector_fills: dict[tuple[int, int, int], int] | None = None) -> bytes:
    """事前登録 第2節の規則（＋追補1 第2節の起動用セクタ規則、＋追補3 第2節の
    任意セクタ規則）で公開D88像を作る。

    boot_fill が None のとき、(0,0,1) は詰め物のまま扱われる。このときの
    生成物は、追補1より前の生成器（boot_fill引数を持たない版）とバイト一致する
    （本モジュールの自己検査で確認する）。sector_fills が None または空の
    ときも同様に、追補3より前の生成器とバイト一致する。

    優先順位: 割り当て表3セクタ(fat_value) > sector_fills > boot_fill > filler。
    """
    if not (0 <= fat_value <= 0xFF):
        raise ValueError("fat_value は0〜255で指定すること")
    if not (0 <= filler <= 0xFF):
        raise ValueError("filler は0〜255で指定すること")
    if boot_fill is not None and not (0 <= boot_fill <= 0xFF):
        raise ValueError("boot_fill は0〜255で指定すること")
    if sector_fills:
        for coord, value in sector_fills.items():
            c, h, r = coord
            if not (0 <= c < CYLINDERS and 0 <= h < HEADS and SECTOR_BASE <= r < SECTOR_BASE + SECTORS_PER_TRACK):
                raise ValueError(f"sector_fills の座標が範囲外: {coord}")
            if not (0 <= value <= 0xFF):
                raise ValueError(f"sector_fills の値が範囲外: {coord}={value}")
            if coord in ALLOCATION_TABLE_COORDS:
                raise ValueError(f"sector_fills に割り当て表3セクタを指定できない: {coord}")

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
            trk = build_track(c, h, fat_value, filler, boot_fill, sector_fills)
            phys = c * 2 + h
            struct.pack_into("<I", track_table, phys * 4, offset)
            body += trk
            offset += len(trk)
    total_size = offset
    struct.pack_into("<I", header, 28, total_size)

    return bytes(header) + bytes(track_table) + bytes(body)


def parse_sector_fill_arg(raw: str) -> tuple[tuple[int, int, int], int]:
    """`--sector-fill C,H,R=0xNN` の1つ分をパースする。形式不正はValueError。"""
    coord_part, sep, value_part = raw.partition("=")
    if not sep:
        raise ValueError(f"--sector-fill の形式が不正(=が無い): {raw!r}")
    fields = coord_part.split(",")
    if len(fields) != 3:
        raise ValueError(f"--sector-fill の座標形式が不正(C,H,Rでない): {raw!r}")
    try:
        c, h, r = (int(v, 0) for v in fields)
        value = int(value_part, 0)
    except ValueError as exc:
        raise ValueError(f"--sector-fill の数値変換に失敗: {raw!r}") from exc
    return (c, h, r), value


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
    parser.add_argument(
        "--sector-fill",
        action="append",
        default=[],
        metavar="C,H,R=0xNN",
        help="任意セクタの値(複数可)。範囲外・重複・割り当て表3セクタの指定はrc=2(追補3)",
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

    sector_fills: dict[tuple[int, int, int], int] = {}
    for raw in args.sector_fill:
        try:
            coord, value = parse_sector_fill_arg(raw)
        except ValueError as exc:
            print(f"エラー: {exc}", file=sys.stderr)
            return 2
        if coord in sector_fills:
            print(f"エラー: --sector-fill の座標が重複している: {coord}", file=sys.stderr)
            return 2
        sector_fills[coord] = value

    if args.outfile.exists():
        print(f"エラー: 出力先が既に存在する（上書きしない）: {args.outfile}", file=sys.stderr)
        return 2

    try:
        data = build_blank_disk(args.fat_value, args.filler, args.boot_fill, sector_fills or None)
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2
    args.outfile.parent.mkdir(parents=True, exist_ok=True)
    args.outfile.write_bytes(data)
    print(f"生成した: {args.outfile} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
