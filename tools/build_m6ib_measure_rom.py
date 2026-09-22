#!/usr/bin/env python3
"""m6i-b B1/B2/B5の介入ROM一式を、登録済みフラグだけで生成する。"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import subprocess
import sys


REPO = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_SIZES = {
    "N88.ROM": 0x8000,
    "DISK.ROM": 0x2000,
    "FONT.ROM": 0x1000,
    "N88_0.ROM": 0x2000,
    "N88_1.ROM": 0x2000,
    "N88_2.ROM": 0x2000,
    "N88_3.ROM": 0x2000,
}


def rom_set_sha256(outdir: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for name in sorted(EXPECTED_SIZES):
        data = (outdir / name).read_bytes()
        digest.update(name.encode("ascii") + b"\0")
        digest.update(data)
    return digest.hexdigest()


def sizes_valid(outdir: pathlib.Path) -> bool:
    """ROM集合と各ファイル長を、成果物そのものから検査する。"""
    actual = {path.name for path in outdir.iterdir() if path.is_file()}
    return actual == set(EXPECTED_SIZES) and all(
        (outdir / name).stat().st_size == expected
        for name, expected in EXPECTED_SIZES.items()
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--arm", required=True, choices=("control", "B1", "B2", "B5"))
    ap.add_argument("--work-dir", required=True, type=pathlib.Path)
    args = ap.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(REPO / "src" / "build_main_rom.py"),
           str(args.outdir), "--enable-main-sub-read", "--work-dir", str(args.work_dir)]
    if args.arm != "control":
        cmd.append(f"--inject-m6ib-{args.arm.lower()}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not sizes_valid(args.outdir):
        raise SystemExit("ROM一式のファイル集合またはサイズが所定構成と一致しない")

    print(f"arm={args.arm}")
    print("build_completed=true")
    print(f"rom_set_sha256={rom_set_sha256(args.outdir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
