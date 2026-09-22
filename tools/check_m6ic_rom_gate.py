#!/usr/bin/env python3
"""m6i-c G4の凍結値・要因直交・ROMサイズを検査する。"""
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


def load_frozen(path: pathlib.Path) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = defaultdict(list)
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        fields = raw.split("\t")
        if len(fields) != 2 or not all(fields):
            raise ValueError(f"TSV形式不正: {path}:{number}")
        rows[fields[0]].append(fields[1])
    return dict(rows)


def frozen_one(rows: dict[str, list[str]], key: str) -> str:
    values = rows.get(key, [])
    if len(values) != 1:
        raise ValueError(f"{key} は1件でなければならない")
    return values[0]


def same(left: pathlib.Path, right: pathlib.Path, name: str) -> bool:
    try:
        return (left / name).read_bytes() == (right / name).read_bytes()
    except OSError:
        return False


def safe_hash(outdir: pathlib.Path) -> str | None:
    try:
        return m6ib.rom_set_sha256(outdir)
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("c0_dir", type=pathlib.Path)
    ap.add_argument("c1_dir", type=pathlib.Path)
    ap.add_argument("c2_dir", type=pathlib.Path)
    ap.add_argument("c3_dir", type=pathlib.Path)
    ap.add_argument("--config", type=pathlib.Path,
                    default=REPO / "tools" / "m6ic_frozen.tsv")
    args = ap.parse_args()
    dirs = {"C0": args.c0_dir, "C1": args.c1_dir,
            "C2": args.c2_dir, "C3": args.c3_dir}

    try:
        frozen = load_frozen(args.config)
        expected_c0 = frozen_one(frozen, "c0_rom_set_sha256")
        expected_c1 = frozen_one(frozen, "c1_rom_set_sha256")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"config=NG ({exc})")
        print("passed=false")
        return 1

    hashes = {arm: safe_hash(outdir) for arm, outdir in dirs.items()}
    checks = {
        "c0_frozen_match": hashes["C0"] == expected_c0,
        "c1_frozen_match": hashes["C1"] == expected_c1,
        "c2_main_matches_c0": same(dirs["C2"], dirs["C0"], "N88.ROM"),
        "c2_disk_matches_c1": same(dirs["C2"], dirs["C1"], "DISK.ROM"),
        "c3_main_matches_c1": same(dirs["C3"], dirs["C1"], "N88.ROM"),
        "c3_disk_matches_c0": same(dirs["C3"], dirs["C0"], "DISK.ROM"),
        "main_variant_count_is_2": len({
            (outdir / "N88.ROM").read_bytes()
            for outdir in dirs.values() if (outdir / "N88.ROM").is_file()
        }) == 2 and all((outdir / "N88.ROM").is_file() for outdir in dirs.values()),
        "disk_variant_count_is_2": len({
            (outdir / "DISK.ROM").read_bytes()
            for outdir in dirs.values() if (outdir / "DISK.ROM").is_file()
        }) == 2 and all((outdir / "DISK.ROM").is_file() for outdir in dirs.values()),
        "common_roms_identical": all(
            same(dirs["C0"], outdir, name)
            for name in COMMON_ROMS for outdir in dirs.values()
        ),
        "all_sizes_valid": all(
            outdir.is_dir() and m6ib.sizes_valid(outdir) for outdir in dirs.values()
        ),
    }
    print(f"c0_rom_set_sha256={hashes['C0'] or 'unavailable'}")
    print(f"c1_rom_set_sha256={hashes['C1'] or 'unavailable'}")
    for name, result in checks.items():
        print(f"{name}={'OK' if result else 'NG'}")
    passed = all(checks.values())
    print(f"passed={'true' if passed else 'false'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
