#!/usr/bin/env python3
"""
make_l3_testdisk.py — L3 検証用の自作 D88 ディスクイメージを作る

**公式ディスクの内容は一切含まない。** 全セクタの中身は下の
`sector_pattern()` という単純な式から機械的に生成する（ルールから
生成する。禁止事項4「ROM/ディスク由来のバイト列をダンプしない」に
対応する、CLAUDE.md「やってよいこと」のとおりの作り方）。

D88 はレトロPCエミュレータ界でよく使われる公開フォーマット
（quasi88 に限らず多数の実装がある）で、PC-88 の ROM/ディスクの
著作物ではない。フォーマットの構造（32バイトヘッダ + トラック
オフセット表 + セクタ毎の16バイトID + データ）は、
`vendor/quasi88-libretro`（GPLの第三者実装、公式ROM無関係）の
`src/image.c`・`src/fdc.c` を読んで確認した（`docs/spec/l3-subrom.md`
2.1節が pio.c を読んだのと同じ扱い）。
"""

import argparse
import pathlib
import struct
import sys

SECTOR_SIZE = 256
DEFAULT_SECTORS_PER_TRACK = 8
DEFAULT_CYLINDERS = 8    # テストに要る範囲だけ（本物の2Dは84トラック）
N_CODE = 0x01             # FDC の N パラメータ = 1 → 256バイト/セクタ

# D88 の1トラック分のヘッダ領域は16バイト固定なので、1トラックの容量
# (256*セクタ数 + 16*セクタ数) が大きくなりすぎると track_table の隣接
# エントリと衝突しうる。安全側で妥当な範囲だけ許可する。
MIN_SECTORS_PER_TRACK = 1
MAX_SECTORS_PER_TRACK = 26

# track_table は164エントリ固定（D88フォーマットの仕様）。片面(head=0)
# だけを使うので phys = cyl*2 が164を超えないシリンダ数だけ許可する。
MIN_CYLINDERS = 1
MAX_CYLINDERS = 82

DISK_PROTECT_FALSE = 0x00
DISK_TYPE_2D = 0x00
STATUS_NORMAL = 0x00
DISK_DELETED_FALSE = 0x00


def sector_pattern(cyl: int, sec: int) -> bytes:
    """このセクタの256バイトを機械的に生成する（ROM/ディスク由来ではない）。"""
    return bytes(((cyl * 97 + sec * 57 + i * 7 + 13) & 0xFF) for i in range(SECTOR_SIZE))


def build_track(cyl: int, sectors_per_track: int) -> bytes:
    body = bytearray()
    for sec in range(1, sectors_per_track + 1):
        hdr = bytearray(16)
        hdr[0] = cyl & 0xFF          # C
        hdr[1] = 0x00                # H
        hdr[2] = sec & 0xFF          # R
        hdr[3] = N_CODE               # N
        hdr[4] = sectors_per_track & 0xFF   # セクタ数(下位)
        hdr[5] = (sectors_per_track >> 8) & 0xFF  # セクタ数(上位)
        hdr[6] = 0x00                # density (0=倍密度相当)
        hdr[7] = DISK_DELETED_FALSE
        hdr[8] = STATUS_NORMAL
        # 9-13 reserved = 0
        size = SECTOR_SIZE
        hdr[14] = size & 0xFF
        hdr[15] = (size >> 8) & 0xFF
        body += hdr
        body += sector_pattern(cyl, sec)
    return bytes(body)


def build_d88(
    sectors_per_track: int = DEFAULT_SECTORS_PER_TRACK,
    n_cylinders: int = DEFAULT_CYLINDERS,
) -> bytes:
    """トラック表は「物理トラック番号 = シリンダ*2+ヘッド」で引かれる
    （vendor src/fdc.c `disk_now_track(i, ncn[i]*2+hd)`）。実測で確かめた
    ——最初は cyl をそのままトラック表の添字にしていたら、SEEK 先の
    シリンダとズレたトラックを読みに行っていた（No Data エラー）。
    片面ディスクなのでヘッド1側のスロットは未使用（オフセット0）のまま
    にする。"""
    tracks = {c: build_track(c, sectors_per_track) for c in range(n_cylinders)}
    header = bytearray(32)
    # header[0:17] name = 0 埋め、[17:26] reserved = 0
    header[26] = DISK_PROTECT_FALSE
    header[27] = DISK_TYPE_2D
    # header[28:32] = 総サイズ。あとで埋める

    track_table = bytearray(164 * 4)
    body = bytearray()
    offset = 32 + 164 * 4
    for c in range(n_cylinders):
        trk = tracks[c]
        phys = c * 2 + 0   # head=0
        struct.pack_into("<I", track_table, phys * 4, offset)
        body += trk
        offset += len(trk)
    total_size = offset
    struct.pack_into("<I", header, 28, total_size)

    return bytes(header) + bytes(track_table) + bytes(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outfile")
    ap.add_argument(
        "--sectors-per-track",
        type=int,
        default=DEFAULT_SECTORS_PER_TRACK,
        help=(
            "1トラックあたりのセクタ数 "
            f"(既定 {DEFAULT_SECTORS_PER_TRACK}。"
            f"{MIN_SECTORS_PER_TRACK}〜{MAX_SECTORS_PER_TRACK} の範囲で指定可)"
        ),
    )
    ap.add_argument(
        "--cylinders",
        type=int,
        default=DEFAULT_CYLINDERS,
        help=(
            "シリンダ数 "
            f"(既定 {DEFAULT_CYLINDERS}。"
            f"{MIN_CYLINDERS}〜{MAX_CYLINDERS} の範囲で指定可)"
        ),
    )
    args = ap.parse_args()

    n = args.sectors_per_track
    if not (MIN_SECTORS_PER_TRACK <= n <= MAX_SECTORS_PER_TRACK):
        print(
            f"エラー: --sectors-per-track は {MIN_SECTORS_PER_TRACK}〜"
            f"{MAX_SECTORS_PER_TRACK} の範囲で指定すること (指定値: {n})",
            file=sys.stderr,
        )
        return 1

    n_cyl = args.cylinders
    if not (MIN_CYLINDERS <= n_cyl <= MAX_CYLINDERS):
        print(
            f"エラー: --cylinders は {MIN_CYLINDERS}〜"
            f"{MAX_CYLINDERS} の範囲で指定すること (指定値: {n_cyl})",
            file=sys.stderr,
        )
        return 1

    data = build_d88(n, n_cyl)
    p = pathlib.Path(args.outfile)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    print(f"生成した: {p} ({len(data)} bytes, {n_cyl} シリンダ x {n} セクタ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
