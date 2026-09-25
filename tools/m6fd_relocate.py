#!/usr/bin/env python3
"""
m6fd_relocate.py — m6f-d §4.2: 公式形式の媒体から自作ファイルを読み解き、
新しい媒体へ別の名前・別の単位で組み直す付け替えの器具。

事前登録: docs/notes/m6f-d-disk-rules-preregistration.md §4.2、
仕様書: docs/spec/l3-disk-format.md 第2版（§1.2 エントリ・§2 割り当て表）。

規則（仮説 H1〜H3、事前登録 §3。本器具はこれをそのまま実装するだけで、
規則そのものの正しさは自己検査 tools/m6fd_relocate_selftest.sh の合成媒体で
確かめる。公式ROM・公式ディスクは使わない）:
  H1: 単位 k は8セクタ（半トラック）。線形番号 L=(C×2+H)×16+(R-1) が
      8k〜8k+7 のセクタ。
  H2: 単位 k の割り当て表の値 T[k] が160未満なら次の単位の番号。160以上
      ならその単位が最後で、値は終端の値e。
  H3: エントリの10バイト目（0始まり）がファイルの最初の単位の番号。

出力の制限（CLAUDE.md 禁止事項・m6f-d §0.1）: 標準出力・標準エラーには、
写したバイトも割り当て表の値も出さない。成功時は生成先パスと鎖の長さだけ、
失敗時は理由の種類だけを出す。
"""

from __future__ import annotations

import argparse
import pathlib
import struct
import sys

from make_m6fc_blank_disk import ALLOCATION_TABLE_COORDS, build_blank_disk

CYLINDERS = 40
HEADS = 2
SECTORS_PER_TRACK = 16
SECTOR_BASE = 1
SECTOR_SIZE = 256
SECTOR_HEADER_SIZE = 16
D88_HEADER_SIZE = 32
TRACK_COUNT = 164
TRACK_TABLE_SIZE = TRACK_COUNT * 4
TRACK_BYTES = SECTORS_PER_TRACK * (SECTOR_HEADER_SIZE + SECTOR_SIZE)

ENTRY_LENGTH = 16
NAME_FIELD_LENGTH = 9
NAME_PAD = 0x20
UNUSED_ENTRY_BYTE = 0xFF

UNIT_SECTORS = 8
UNIT_COUNT = 160  # 2Dの媒体の割り当て単位数(m6f-c C4相当、m6f-dで確定)

FAT_COORDS = (18, 1, 14), (18, 1, 15), (18, 1, 16)
DIRECTORY_COORDS = tuple((18, 1, r) for r in range(1, 13))

WRITE_PROTECT_COORD = (18, 1, 13)
WRITE_PROTECT_UNLOCKED = 0x00


class RelocateError(Exception):
    """付け替え失敗の基底クラス。CLIは理由の種類（クラス名）だけを出す。"""


class EntryNotFoundError(RelocateError):
    pass


class ChainLengthMismatchError(RelocateError):
    pass


class ChainCycleError(RelocateError):
    pass


class ChainRangeError(RelocateError):
    pass


class ChainUndefinedError(RelocateError):
    pass


class InvalidArgumentError(RelocateError):
    pass


# --- D88像の座標⇔オフセット(m6f-c/m6f-dの生成器と同じ固定外形が前提) -------

def _sector_data_offset(c: int, h: int, r: int) -> int:
    if not (0 <= c < CYLINDERS and 0 <= h < HEADS and SECTOR_BASE <= r < SECTOR_BASE + SECTORS_PER_TRACK):
        raise InvalidArgumentError(f"座標が範囲外: ({c},{h},{r})")
    phys = c * 2 + h
    return (D88_HEADER_SIZE + TRACK_TABLE_SIZE + phys * TRACK_BYTES
            + (r - SECTOR_BASE) * (SECTOR_HEADER_SIZE + SECTOR_SIZE) + SECTOR_HEADER_SIZE)


def _read_sector(img: bytes, c: int, h: int, r: int) -> bytes:
    off = _sector_data_offset(c, h, r)
    return bytes(img[off:off + SECTOR_SIZE])


def _write_sector(img: bytearray, c: int, h: int, r: int, data: bytes) -> None:
    if len(data) != SECTOR_SIZE:
        raise InvalidArgumentError("セクタの書き込みデータ長が256バイトでない")
    off = _sector_data_offset(c, h, r)
    img[off:off + SECTOR_SIZE] = data


def _linear_to_coord(linear: int) -> tuple[int, int, int]:
    c = linear // (HEADS * SECTORS_PER_TRACK)
    rem = linear % (HEADS * SECTORS_PER_TRACK)
    h = rem // SECTORS_PER_TRACK
    r = (rem % SECTORS_PER_TRACK) + SECTOR_BASE
    return c, h, r


def _unit_to_coords(unit: int) -> list[tuple[int, int, int]]:
    base = unit * UNIT_SECTORS
    return [_linear_to_coord(base + j) for j in range(UNIT_SECTORS)]


# --- H3: エントリを名前で探す --------------------------------------------

def _find_entry(src_image: bytes, src_name: bytes) -> tuple[tuple[int, int, int], int, bytes]:
    """トラック18の割り当て表3セクタ以外を走査し、名前欄が一致する最初の
    エントリを返す。戻り値は (座標, セクタ内オフセット, 16バイトのエントリ本体)。"""
    if not (1 <= len(src_name) <= NAME_FIELD_LENGTH):
        raise InvalidArgumentError("src_name の長さは1〜9バイトで指定すること")
    padded = src_name + bytes([NAME_PAD]) * (NAME_FIELD_LENGTH - len(src_name))

    for h in range(HEADS):
        for r in range(SECTOR_BASE, SECTOR_BASE + SECTORS_PER_TRACK):
            coord = (18, h, r)
            if coord in ALLOCATION_TABLE_COORDS:
                continue
            sector = _read_sector(src_image, *coord)
            for offset in range(0, SECTOR_SIZE, ENTRY_LENGTH):
                entry = sector[offset:offset + ENTRY_LENGTH]
                if len(entry) < ENTRY_LENGTH:
                    continue
                if entry[0] in (UNUSED_ENTRY_BYTE, 0x00):
                    continue  # 未使用・削除済みのエントリは名前欄として見ない
                if entry[0:NAME_FIELD_LENGTH] == padded:
                    return coord, offset, bytes(entry)
    raise EntryNotFoundError(f"エントリが見つからない: 名前欄長{len(src_name)}")


# --- H1・H2: 鎖をたどる -----------------------------------------------------

def _read_fat_table(src_image: bytes) -> bytes:
    """T は (18,1,14)（事前登録 §4.2）。"""
    return _read_sector(src_image, *FAT_COORDS[0])


def _walk_chain(fat: bytes, start_unit: int) -> tuple[list[int], int]:
    """H2 で鎖をたどる。戻り値は (鎖の単位番号の並び, 終端の値e)。
    循環・範囲外・未定義(0xFF)はそれぞれ拒否する(事前登録 §4.2)。"""
    units: list[int] = []
    visited: set[int] = set()
    k = start_unit
    while True:
        if not (0 <= k < UNIT_COUNT):
            raise ChainRangeError(f"単位番号が範囲外: {k}")
        if k in visited:
            raise ChainCycleError(f"鎖が循環している: 単位{k}")
        visited.add(k)
        units.append(k)
        if len(units) > UNIT_COUNT:
            raise ChainCycleError("鎖が単位数を超えて続いている")
        value = fat[k]
        if value == UNUSED_ENTRY_BYTE:
            raise ChainUndefinedError(f"割り当て表の値が未定義(0xFF): 単位{k}")
        if value < UNIT_COUNT:
            k = value
            continue
        return units, value


# --- 本体 -------------------------------------------------------------------

def relocate(src_image: bytes, *, src_name: bytes, dst_name: bytes,
             dst_units: list[int], dst_slot: tuple[int, int, int, int] = (18, 1, 1, 0),
             break_link_at: int | None = None, override_start: int | None = None,
             dir_fill: str | None = None) -> bytes:
    if not (1 <= len(dst_name) <= NAME_FIELD_LENGTH):
        raise InvalidArgumentError("dst_name の長さは1〜9バイトで指定すること")
    if dir_fill is not None and dir_fill not in ("00", "FF"):
        raise InvalidArgumentError(f"dir_fill が不正: {dir_fill!r}")
    for u in dst_units:
        if not (0 <= u < UNIT_COUNT):
            raise InvalidArgumentError(f"dst_units の単位番号が範囲外: {u}")
    if len(set(dst_units)) != len(dst_units):
        raise InvalidArgumentError("dst_units に重複がある")
    if break_link_at is not None and not (0 <= break_link_at < UNIT_COUNT):
        raise InvalidArgumentError(f"break_link_at が範囲外: {break_link_at}")
    if override_start is not None and not (0 <= override_start < UNIT_COUNT):
        raise InvalidArgumentError(f"override_start が範囲外: {override_start}")
    dst_c, dst_h, dst_r, dst_off = dst_slot
    if dst_off < 0 or dst_off + ENTRY_LENGTH > SECTOR_SIZE or dst_off % ENTRY_LENGTH != 0:
        raise InvalidArgumentError(f"dst_slot のオフセットが不正: {dst_off}")

    # H3: エントリを探し、H2で鎖をたどる。
    _coord, _off, entry = _find_entry(src_image, src_name)
    start_unit = entry[10]
    fat = _read_fat_table(src_image)
    units, terminal_value = _walk_chain(fat, start_unit)

    if len(units) != len(dst_units):
        raise ChainLengthMismatchError(
            f"鎖の長さがdst_unitsと一致しない: 鎖={len(units)} dst_units={len(dst_units)}")

    # 事前登録 §4.2: 新しい媒体は B0(全FF、(18,1,13)だけ0x00)を土台にする。
    new_image = bytearray(build_blank_disk(0xFF, 0xFF, sector_fills={WRITE_PROTECT_COORD: WRITE_PROTECT_UNLOCKED}))

    # 割り当て表: T[dst_i] = dst_(i+1)、最後は元の終端の値eをそのまま。3セクタとも同じ。
    fat_updates: dict[int, int] = {}
    for i, unit in enumerate(dst_units):
        if i + 1 < len(dst_units):
            fat_updates[unit] = dst_units[i + 1]
        else:
            fat_updates[unit] = terminal_value

    for coord in FAT_COORDS:
        sector = bytearray(SECTOR_SIZE)  # 土台は全FF
        sector[:] = bytes([0xFF]) * SECTOR_SIZE
        for pos, value in fat_updates.items():
            sector[pos] = value
        _write_sector(new_image, *coord, bytes(sector))

    # 各単位の8セクタを写す。
    for src_unit, dst_unit in zip(units, dst_units):
        src_coords = _unit_to_coords(src_unit)
        dst_coords = _unit_to_coords(dst_unit)
        for sc, dc in zip(src_coords, dst_coords):
            payload = _read_sector(src_image, *sc)
            _write_sector(new_image, *dc, payload)

    # dir_fill='00': ディレクトリの12セクタを全0x00にする(エントリを置くセクタも含む)。
    if dir_fill == "00":
        zero = bytes(SECTOR_SIZE)
        for coord in DIRECTORY_COORDS:
            _write_sector(new_image, *coord, zero)

    # エントリを配置する(ディレクトリのゼロ埋めの後)。
    new_entry = bytearray(ENTRY_LENGTH)
    padded_name = dst_name + bytes([NAME_PAD]) * (NAME_FIELD_LENGTH - len(dst_name))
    new_entry[0:NAME_FIELD_LENGTH] = padded_name
    new_entry[9] = entry[9]
    new_entry[10] = override_start if override_start is not None else dst_units[0]
    new_entry[11:16] = entry[11:16]

    dst_sector = bytearray(_read_sector(new_image, dst_c, dst_h, dst_r))
    dst_sector[dst_off:dst_off + ENTRY_LENGTH] = new_entry
    _write_sector(new_image, dst_c, dst_h, dst_r, bytes(dst_sector))

    # break_link_at: 陰性対照用に鎖を切る(3セクタとも)。
    if break_link_at is not None:
        for coord in FAT_COORDS:
            sector = bytearray(_read_sector(new_image, *coord))
            sector[break_link_at] = UNUSED_ENTRY_BYTE
            _write_sector(new_image, *coord, bytes(sector))

    return bytes(new_image)


def _parse_dst_slot(raw: str) -> tuple[int, int, int, int]:
    fields = raw.split(",")
    if len(fields) != 4:
        raise InvalidArgumentError(f"--dst-slot の形式が不正(C,H,R,offsetでない): {raw!r}")
    try:
        return tuple(int(v, 0) for v in fields)  # type: ignore[return-value]
    except ValueError as exc:
        raise InvalidArgumentError(f"--dst-slot の数値変換に失敗: {raw!r}") from exc


def _parse_dst_units(raw: str) -> list[int]:
    try:
        return [int(v, 0) for v in raw.split(",") if v != ""]
    except ValueError as exc:
        raise InvalidArgumentError(f"--dst-units の数値変換に失敗: {raw!r}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", type=pathlib.Path)
    parser.add_argument("dst", type=pathlib.Path)
    parser.add_argument("--src-name", required=True)
    parser.add_argument("--dst-name", required=True)
    parser.add_argument("--dst-units", required=True, metavar="K1,K2,...")
    parser.add_argument("--dst-slot", default="18,1,1,0", metavar="C,H,R,offset")
    parser.add_argument("--break-link-at", default=None, type=lambda v: int(v, 0))
    parser.add_argument("--override-start", default=None, type=lambda v: int(v, 0))
    parser.add_argument("--dir-fill", default=None, choices=("00", "FF"))
    args = parser.parse_args()

    if args.dst.exists():
        print("エラー: 出力先が既に存在する（上書きしない）", file=sys.stderr)
        return 2

    try:
        src_image = args.src.read_bytes()
    except OSError as exc:
        print(f"エラー: 入力が読めない: {type(exc).__name__}", file=sys.stderr)
        return 2

    try:
        dst_units = _parse_dst_units(args.dst_units)
        dst_slot = _parse_dst_slot(args.dst_slot)
        new_image = relocate(
            src_image,
            src_name=args.src_name.encode("ascii"),
            dst_name=args.dst_name.encode("ascii"),
            dst_units=dst_units,
            dst_slot=dst_slot,
            break_link_at=args.break_link_at,
            override_start=args.override_start,
            dir_fill=args.dir_fill,
        )
        chain_length = len(dst_units)
    except RelocateError as exc:
        # 理由の種類(クラス名)だけを出す。メッセージ本文もバイト値は含まない設計だが、
        # 念のためクラス名を主にする。
        print(f"エラー: {type(exc).__name__}", file=sys.stderr)
        return 1
    except UnicodeEncodeError:
        print("エラー: InvalidArgumentError", file=sys.stderr)
        return 2

    args.dst.parent.mkdir(parents=True, exist_ok=True)
    args.dst.write_bytes(new_image)
    print(f"生成した: {args.dst}")
    print(f"鎖の長さ: {chain_length}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
