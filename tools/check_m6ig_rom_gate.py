#!/usr/bin/env python3
"""m6i-g G4のsub無改変・main直交・ROMサイズを検査する。"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import src.l3_service.make_subrom as subrom  # noqa: E402
sys.path.insert(0, str(REPO / "tools"))
import build_m6ib_measure_rom as m6ib  # noqa: E402
import build_m6ig_measure_rom as m6ig  # noqa: E402

COMMON_ROMS = tuple(name for name in m6ib.EXPECTED_SIZES
                    if name not in ("N88.ROM", "DISK.ROM"))


def read(directory: pathlib.Path, name: str) -> bytes | None:
    try:
        return (directory / name).read_bytes()
    except OSError:
        return None


def cfg_one(path: pathlib.Path, key: str) -> str | None:
    try:
        values = [fields[1] for raw in path.read_text(encoding="utf-8").splitlines()
                  if len(fields := raw.split("\t")) == 2 and fields[0] == key]
    except (OSError, UnicodeError):
        return None
    return values[0] if len(values) == 1 else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("g_n", "g_l0", "g_l1", "g_l2"):
        ap.add_argument(f"{name}_dir", type=pathlib.Path)
    for arm in ("b0", "b1", "b4", "b5"):
        ap.add_argument(f"--m6ib-{arm}-dir", required=True, type=pathlib.Path)
    ap.add_argument("--config", type=pathlib.Path, default=REPO / "tools/m6ig_frozen.tsv")
    args = ap.parse_args()
    dirs = {"G-N": args.g_n_dir, "G-L0": args.g_l0_dir,
            "G-L1": args.g_l1_dir, "G-L2": args.g_l2_dir}
    refs = {"B0": args.m6ib_b0_dir, "B1": args.m6ib_b1_dir,
            "B4": args.m6ib_b4_dir, "B5": args.m6ib_b5_dir}
    plain, _used = subrom.build()
    plain_bytes = bytes(plain)
    frozen_sha = cfg_one(args.config, "plain_subrom_sha256")
    disks = {arm: read(path, "DISK.ROM") for arm, path in dirs.items()}
    mains = {arm: read(path, "N88.ROM") for arm, path in dirs.items()}
    checks = {
        "plain_subrom_frozen_match": hashlib.sha256(plain_bytes).hexdigest() == frozen_sha,
        "all_disks_identical": all(value is not None and value == disks["G-N"]
                                      for value in disks.values()),
        "disks_match_plain_subrom": all(value == plain_bytes for value in disks.values()),
        "common_roms_identical": all(
            read(path, name) is not None and read(path, name) == read(dirs["G-N"], name)
            for name in COMMON_ROMS for path in dirs.values()),
        "all_mains_distinct": all(value is not None for value in mains.values())
                              and len(set(mains.values())) == 4,
        "mains_match_m6ib_sources": all(
            mains[arm] == read(refs[source], "N88.ROM")
            for arm, source in m6ig.MAIN_SOURCE.items()),
        "all_sizes_valid": all(path.is_dir() and m6ib.sizes_valid(path)
                               for path in dirs.values()),
    }
    for arm, path in dirs.items():
        try:
            digest = m6ib.rom_set_sha256(path)
        except OSError:
            digest = "unavailable"
        print(f"{arm.lower().replace('-', '_')}_rom_set_sha256={digest}")
    for name, result in checks.items():
        print(f"{name}={'OK' if result else 'NG'}")
    passed = all(checks.values())
    print(f"passed={'true' if passed else 'false'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
