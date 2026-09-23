#!/usr/bin/env python3
"""m6i-e G4の成果物同一性・6バイト直交・ROMサイズを検査する。"""
from __future__ import annotations

import argparse
import pathlib
import sys
from collections import defaultdict

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import build_m6ib_measure_rom as m6ib  # noqa: E402

COMMON_ROMS = tuple(
    name for name in m6ib.EXPECTED_SIZES if name not in ("N88.ROM", "DISK.ROM")
)
E0_INSERT = bytes((0xDB, 0xFE, 0xE6, 0x08, 0x28, 0xFA))
E2_INSERT = bytes((0xDB, 0xFE, 0, 0, 0, 0))
E3_INSERT = bytes(6)


def read(directory: pathlib.Path, name: str) -> bytes | None:
    try:
        return (directory / name).read_bytes()
    except OSError:
        return None


def digest(directory: pathlib.Path) -> str:
    try:
        return m6ib.rom_set_sha256(directory)
    except OSError:
        return "unavailable"


def frozen_c0(path: pathlib.Path) -> str | None:
    rows: dict[str, list[str]] = defaultdict(list)
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            fields = raw.split("\t")
            if len(fields) == 2:
                rows[fields[0]].append(fields[1])
    except (OSError, UnicodeError):
        return None
    values = rows.get("c0_rom_set_sha256", [])
    return values[0] if len(values) == 1 else None


def difference(left: bytes | None, right: bytes | None) -> list[int]:
    if left is None or right is None or len(left) != len(right):
        return []
    return [i for i, (a, b) in enumerate(zip(left, right)) if a != b]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for arm in ("e0", "e1", "e2", "e3"):
        ap.add_argument(f"{arm}_dir", type=pathlib.Path)
    ap.add_argument("--m6ic-c0-dir", required=True, type=pathlib.Path)
    ap.add_argument("--m6ic-c2-dir", required=True, type=pathlib.Path)
    ap.add_argument("--m6ic-config", type=pathlib.Path,
                    default=REPO / "tools" / "m6ic_frozen.tsv")
    args = ap.parse_args()
    dirs = {arm: getattr(args, f"{arm.lower()}_dir") for arm in ("E0", "E1", "E2", "E3")}
    main = {arm: read(path, "N88.ROM") for arm, path in dirs.items()}
    disk = {arm: read(path, "DISK.ROM") for arm, path in dirs.items()}
    pair_names = (("E0", "E2"), ("E0", "E3"), ("E2", "E3"))
    pair_diffs = {pair: difference(disk[pair[0]], disk[pair[1]]) for pair in pair_names}
    regions = [set(value) for value in pair_diffs.values()]
    insertion_region = set().union(*regions)
    contiguous = bool(insertion_region) and insertion_region == set(range(min(insertion_region), min(insertion_region) + 6))
    position = min(insertion_region) if contiguous else None

    e1, e3 = disk["E1"], disk["E3"]
    # E1は6バイト短い論理コードを固定長ROMへ再アセンブルしたもの。挿入を
    # 跨ぐ相対分岐の変位1バイトずつだけは再配置で変わるため、それ以外を照合する。
    pre_diffs = (difference(e1[:position], e3[:position])
                 if position is not None and e1 is not None and e3 is not None else [])
    shifted_diffs = ([position + i for i, (a, b) in enumerate(
        zip(e1[position:-6], e3[position + 6:])) if a != b]
        if position is not None and e1 is not None and e3 is not None else [])
    shifted = (position is not None and e1 is not None and e3 is not None
               and len(e1) == len(e3)
               and len(pre_diffs) == 1 and len(shifted_diffs) == 1)
    checks = {
        "m6ic_c0_frozen_match": digest(args.m6ic_c0_dir) == frozen_c0(args.m6ic_config),
        "all_mains_identical": all(value is not None and value == main["E0"] for value in main.values()),
        "main_matches_m6ic_c0": main["E0"] == read(args.m6ic_c0_dir, "N88.ROM"),
        "e1_disk_matches_m6ic_c2": disk["E1"] == read(args.m6ic_c2_dir, "DISK.ROM"),
        "e0_disk_matches_m6ic_c0": disk["E0"] == read(args.m6ic_c0_dir, "DISK.ROM"),
        "insertions_share_six_byte_region": contiguous and all(
            set(value) <= insertion_region for value in pair_diffs.values()),
        "e0_insertion_matches_registered": position is not None and disk["E0"] is not None and disk["E0"][position:position + 6] == E0_INSERT,
        "e2_insertion_matches_registered": position is not None and disk["E2"] is not None and disk["E2"][position:position + 6] == E2_INSERT,
        "e3_insertion_matches_registered": position is not None and disk["E3"] is not None and disk["E3"][position:position + 6] == E3_INSERT,
        "e1_e3_shifted_match": shifted,
        "common_roms_identical": all(read(dirs["E0"], name) is not None and read(path, name) == read(dirs["E0"], name) for name in COMMON_ROMS for path in dirs.values()),
        "all_sizes_valid": all(path.is_dir() and m6ib.sizes_valid(path) for path in dirs.values()),
    }
    for arm, path in dirs.items():
        print(f"{arm.lower()}_rom_set_sha256={digest(path)}")
    for pair, values in pair_diffs.items():
        label = f"{pair[0].lower()}_{pair[1].lower()}"
        location = "unavailable" if not values else f"{min(values)}-{max(values)}"
        print(f"{label}_difference_count={len(values)}")
        print(f"{label}_difference_position={location}")
    for name, result in checks.items():
        print(f"{name}={'OK' if result else 'NG'}")
    passed = all(checks.values())
    print(f"passed={'true' if passed else 'false'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
