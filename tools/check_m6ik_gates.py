#!/usr/bin/env python3
"""エミュレータ起動前の m6i-k G3/G4/G5/G6 を検査する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from d88_read_sector import D88Reader  # noqa: E402
from check_m6ik_preregistration import EXPECTED  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*argv: str) -> None:
    subprocess.run(argv, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def default_build(source: Path, out: Path) -> dict[str, str]:
    rom = out / "rom"
    run(sys.executable, str(source / "src/build_main_rom.py"), str(rom),
        "--work-dir", str(out / "build"))
    return {p.name: digest(p) for p in rom.iterdir() if p.is_file()}


def gate(args: argparse.Namespace) -> dict[str, object]:
    a, b = args.work / "a.d88", args.work / "b.d88"
    if digest(a) != EXPECTED["disk_a_sha256"][0] or digest(b) != EXPECTED["disk_b_sha256"][0]:
        raise ValueError("G3:disk_sha")
    readers = [D88Reader(a.read_bytes()), D88Reader(b.read_bytes())]
    for drive, track, sector in ((0, 37, 13), (1, 37, 13), (1, 1, 1), (0, 1, 1)):
        reader = readers[drive]
        if reader.read_sector(track >> 1, track & 1, sector) == reader.read_sector(track, 0, sector):
            raise ValueError("G3:coordinate_not_distinct")
    source = args.sub_rom
    if not source.is_file():
        raise ValueError("G4:sub_missing")
    source_sha = digest(source)
    if args.dry_run and source_sha != EXPECTED["plain_subrom_sha256"][0]:
        raise ValueError("G4:dry_sub_sha")
    arm_hashes = {}
    for arm in ("K-00", "K-01", "K-F0", "K-F1", "K-M1", "K-FR"):
        rom = args.work / ("rom-" + arm)
        if digest(rom / "DISK.ROM") != source_sha:
            raise ValueError("G4:sub_copy")
        arm_hashes[arm] = digest(rom / "N88.ROM")
    f1 = (args.work / "rom-K-F1/N88.ROM").read_bytes()
    fr = (args.work / "rom-K-FR/N88.ROM").read_bytes()
    diffs = [i for i, (x, y) in enumerate(zip(f1, fr)) if x != y]
    if len(f1) != len(fr) or len(diffs) != 1 or f1[diffs[0]] != 0 or fr[diffs[0]] != 0x3C:
        raise ValueError("G5:FR_difference")
    baseline_root = args.work / "g6-baseline-root"
    baseline = baseline_root / "PC88Behavior"
    baseline.mkdir(parents=True)
    (baseline_root / "vendor").symlink_to(REPO.parent / "vendor", target_is_directory=True)
    with subprocess.Popen(["git", "-C", str(REPO), "archive", "9518294"],
                          stdout=subprocess.PIPE) as archive:
        subprocess.run(["tar", "-x", "-C", str(baseline)], stdin=archive.stdout,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if archive.wait():
            raise ValueError("G6:archive")
    base_hashes = default_build(baseline, args.work / "g6-base")
    if args.dry_run:
        current = REPO
        g6_mode = "試走"
    else:
        current_root = args.work / "g6-current-root"
        current = current_root / "PC88Behavior"
        current.mkdir(parents=True)
        (current_root / "vendor").symlink_to(REPO.parent / "vendor", target_is_directory=True)
        with subprocess.Popen(["git", "-C", str(REPO), "archive", "HEAD"],
                              stdout=subprocess.PIPE) as archive:
            subprocess.run(["tar", "-x", "-C", str(current)], stdin=archive.stdout,
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if archive.wait():
                raise ValueError("G6:archive_current")
        g6_mode = "HEAD"
    current_hashes = default_build(current, args.work / "g6-current")
    if base_hashes != current_hashes:
        raise ValueError("G6:default_output_changed")
    return {"disk_a_sha256": digest(a), "disk_b_sha256": digest(b),
            "sub_sha256": source_sha, "g4_mode": "試走" if args.dry_run else "公式照合",
            "arm_main_sha256": arm_hashes,
            "fr_difference_positions": len(diffs), "g6_mode": g6_mode,
            "g6_output_sha256": base_hashes}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--sub-rom", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        result = gate(args)
        (args.work / "gates.json").write_text(json.dumps(result, sort_keys=True) + "\n")
        print("m6i-k G3/G4/G5/G6: OK")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
