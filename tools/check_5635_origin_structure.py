#!/usr/bin/env python3
"""m7daの5635件構造を、値を含まない合成座標JSONで検査する。

入力はREAD長、ポート別プリアンブル件数、および定常部の
``{"port": "FC|FD", "coord": 非負整数}`` 列である。coordは媒体値ではなく、
44セクタ連続窓内の0-based位置だけを表す。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


EXPECTED_READ_LENGTHS = [1, 14, 16, 16, 2]
SECTOR_SIZE = 256
SKIPPED_SECTORS = 5
PREAMBLE_PER_PORT = 3
PORTS = ("FC", "FD")


class StructureError(Exception):
    pass


def load_fixture(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StructureError(f"JSONを読めない: {exc}") from exc
    if not isinstance(data, dict):
        raise StructureError("JSONの根はobjectでなければならない")
    return data


def validate(data: dict) -> dict[str, int]:
    reads = data.get("read_lengths")
    if reads != EXPECTED_READ_LENGTHS:
        raise StructureError(
            f"READ長が期待と異なる: 件数={len(reads) if isinstance(reads, list) else '不正'}"
        )
    selected_sectors = sum(reads) - SKIPPED_SECTORS
    if selected_sectors != 44:
        raise StructureError(f"選択セクタ数が44でない: {selected_sectors}")

    preamble = data.get("preamble_per_port")
    if preamble != {"FC": PREAMBLE_PER_PORT, "FD": PREAMBLE_PER_PORT}:
        raise StructureError("ポート別プリアンブル件数が3+3でない")

    regular = data.get("regular")
    if not isinstance(regular, list):
        raise StructureError("regularが配列でない")
    payload_bytes = selected_sectors * SECTOR_SIZE
    if len(regular) != payload_bytes:
        raise StructureError(
            f"定常イベント数が44セクタ分でない: {len(regular)}/{payload_bytes}"
        )

    ports: list[str] = []
    coords: list[int] = []
    for index, event in enumerate(regular):
        if not isinstance(event, dict):
            raise StructureError(f"regular[{index}]がobjectでない")
        port = event.get("port")
        coord = event.get("coord")
        if port not in PORTS or not isinstance(coord, int) or isinstance(coord, bool):
            raise StructureError(f"regular[{index}]のport/coordが不正")
        ports.append(port)
        coords.append(coord)

    expected_ports = [PORTS[i & 1] for i in range(payload_bytes)]
    if ports != expected_ports:
        first = next(i for i, (a, b) in enumerate(zip(ports, expected_ports)) if a != b)
        raise StructureError(f"FC→FD交互配置が崩れた: regular[{first}]")

    port_counts = Counter(ports)
    if port_counts != Counter({"FC": 5632, "FD": 5632}):
        raise StructureError(f"定常部のポート別件数が5632+5632でない: {dict(port_counts)}")

    expected_coords = list(range(1, payload_bytes)) + [payload_bytes - 1]
    if coords != expected_coords:
        first = next(i for i, (a, b) in enumerate(zip(coords, expected_coords)) if a != b)
        raise StructureError(f"順序座標または末尾重複が崩れた: regular[{first}]")

    if len(set(coords)) != payload_bytes - 1 or coords[-1] != coords[-2]:
        raise StructureError("末尾1位置の直前座標重複を確認できない")

    return {
        "selected_sectors": selected_sectors,
        "payload_bytes": payload_bytes,
        "regular_fc": port_counts["FC"],
        "regular_fd": port_counts["FD"],
        "total_fc": port_counts["FC"] + preamble["FC"],
        "total_fd": port_counts["FD"] + preamble["FD"],
        "tail_duplicates": 1,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("fixture", type=Path)
    args = ap.parse_args()
    try:
        result = validate(load_fixture(args.fixture))
    except StructureError as exc:
        print(f"NG: {exc}", file=sys.stderr)
        return 1
    print(
        "OK: 選択={selected_sectors}セクタ 定常={payload_bytes}件 "
        "FC={regular_fc}+3={total_fc} FD={regular_fd}+3={total_fd} "
        "末尾重複={tail_duplicates}件".format(**result)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
