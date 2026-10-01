#!/usr/bin/env python3
"""build_blank_data_disk.py — 空の N88-BASIC 2D データディスクを公開規則から生成する。

根拠: docs/spec/l3-disk-format.md 第4節（空のデータディスクの作り方）。
  - (18,1,14)(18,1,15)(18,1,16): 全バイト 0xFF、ただし位置 74・75 は 0xA0（2.5）
  - (18,1,13): 全バイト 0x00
  - それ以外の全セクタ: 全バイト 0xFF
  - 公式ROMで起動できる媒体は作らない: 起動用セクタ (0,0,1) は読めない形
    （データCRCエラー）にする（第4節、m6f-d D9）。
公式ROM・公式ディスクは入力にしない。外形と生成は tools/make_m6fc_blank_disk.py の
build_blank_disk を再利用する。出力は決定論的（毎回同じバイト列）。

使い方:
  tools/build_blank_data_disk.py OUT.D88      生成（既存なら上書きせず rc=2）
  tools/build_blank_data_disk.py --check      自己検査（独立のD88読み取りで規則を照合）
"""
import argparse
import hashlib
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from make_m6fc_blank_disk import build_blank_disk  # noqa: E402


def build() -> bytes:
    return build_blank_disk(
        0xFF, 0xFF,
        sector_fills={(18, 1, 13): 0x00},
        fat_positions={74: 0xA0, 75: 0xA0},
        boot_sector_mode="crc",
    )


def parse(image: bytes) -> dict:
    """独立の最小D88読み取り。{(C,H,R): (status, data)} を返す。"""
    if struct.unpack_from("<I", image, 28)[0] != len(image):
        raise ValueError("ヘッダの総サイズが実サイズと違う")
    sectors = {}
    for t in range(164):
        pos = struct.unpack_from("<I", image, 32 + t * 4)[0]
        if pos == 0:
            continue
        n = None
        count = 0
        while n is None or count < n:
            c, h, r = image[pos:pos + 3]
            n = struct.unpack_from("<H", image, pos + 4)[0]
            status = image[pos + 8]
            size = struct.unpack_from("<H", image, pos + 14)[0]
            sectors[(c, h, r)] = (status, image[pos + 16:pos + 16 + size])
            pos += 16 + size
            count += 1
    return sectors


def verify(image: bytes) -> list:
    errs = []
    try:
        s = parse(image)
    except (ValueError, struct.error) as e:
        return [str(e)]
    for c in range(40):
        for h in range(2):
            for r in range(1, 17):
                key = (c, h, r)
                if key not in s:
                    errs.append(f"セクタ欠落 {key}")
                    continue
                status, data = s[key]
                if len(data) != 256:
                    errs.append(f"長さ不正 {key}")
                    continue
                if key == (0, 0, 1):
                    if status == 0:
                        errs.append("起動用セクタが読める形になっている")
                    continue
                if status != 0:
                    errs.append(f"状態が正常でない {key}")
                if key == (18, 1, 13):
                    want = bytes(256)
                elif key in ((18, 1, 14), (18, 1, 15), (18, 1, 16)):
                    w = bytearray([0xFF]) * 256
                    w[74] = w[75] = 0xA0
                    want = bytes(w)
                else:
                    want = bytes([0xFF]) * 256
                if data != want:
                    errs.append(f"内容が規則と違う {key}")
    return errs


def _mutate(image: bytes, key, pos, val) -> bytes:
    img = bytearray(image)
    for t in range(164):
        p = struct.unpack_from("<I", img, 32 + t * 4)[0]
        if p == 0:
            continue
        for _ in range(16):
            if tuple(img[p:p + 3]) == key:
                img[p + 16 + pos] = val
                return bytes(img)
            p += 16 + 256
    raise AssertionError(key)


def check() -> int:
    a, b = build(), build()
    if a != b:
        print("NG: 決定性: 2回の生成が一致しない")
        return 1
    print("OK: 決定性: 2回の生成が一致する")
    errs = verify(a)
    if errs:
        print("NG: 規則照合:", errs[:3])
        return 1
    print("OK: 規則照合（全1280セクタ）")
    rc = 0
    cases = {
        "位置74を0xFFにする": _mutate(a, (18, 1, 14), 74, 0xFF),
        "(18,1,13)を壊す": _mutate(a, (18, 1, 13), 0, 0x01),
        "一般セクタを壊す": _mutate(a, (5, 0, 3), 7, 0x00),
    }
    boot_ok = bytearray(a)
    p = struct.unpack_from("<I", boot_ok, 32)[0]
    boot_ok[p + 8] = 0
    cases["起動用セクタを読める形にする"] = bytes(boot_ok)
    for name, img in cases.items():
        if verify(img):
            print(f"OK: 陰性対照: {name} を検出した")
        else:
            print(f"NG: 陰性対照: {name} を見逃した")
            rc = 1
    print("SHA-256", hashlib.sha256(a).hexdigest(), len(a), "bytes")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outfile", nargs="?", type=pathlib.Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        return check()
    if not args.outfile:
        ap.error("outfile か --check を指定すること")
    if args.outfile.exists():
        print(f"エラー: 出力先が既に存在する（上書きしない）: {args.outfile}", file=sys.stderr)
        return 2
    data = build()
    args.outfile.parent.mkdir(parents=True, exist_ok=True)
    args.outfile.write_bytes(data)
    print(f"生成した: {args.outfile} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
