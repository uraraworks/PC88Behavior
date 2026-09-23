#!/usr/bin/env python3
"""m6i-e E0〜E3のROM一式を、m6i-c成果物から生成する。"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import build_m6ib_measure_rom as m6ib  # noqa: E402

ARMS = ("E0", "E1", "E2", "E3")


def build_m6ic(outdir: pathlib.Path, work_dir: pathlib.Path, arm: str) -> None:
    subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_m6ic_measure_rom.py"),
         str(outdir), "--arm", arm, "--work-dir", str(work_dir)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def replace_sub(outdir: pathlib.Path, flag: str) -> None:
    subprocess.run(
        [sys.executable, str(REPO / "src" / "l3_service" / "make_subrom.py"),
         str(outdir), flag],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--work-dir", required=True, type=pathlib.Path)
    args = ap.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    source = args.work_dir / "m6ic-source"
    build_m6ic(source, args.work_dir / "m6ic-build",
               "C2" if args.arm == "E1" else "C0")
    args.outdir.mkdir(parents=True, exist_ok=True)
    for name in m6ib.EXPECTED_SIZES:
        shutil.copyfile(source / name, args.outdir / name)
    if args.arm == "E2":
        replace_sub(args.outdir, "--inject-m6ie-single-read")
    elif args.arm == "E3":
        replace_sub(args.outdir, "--inject-m6ie-nops-only")

    if not m6ib.sizes_valid(args.outdir):
        raise SystemExit("ROM一式のファイル集合またはサイズが所定構成と一致しない")
    print(f"arm={args.arm}")
    print("build_completed=true")
    print(f"rom_set_sha256={m6ib.rom_set_sha256(args.outdir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
