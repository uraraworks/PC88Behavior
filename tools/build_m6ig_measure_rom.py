#!/usr/bin/env python3
"""m6i-g の4腕を、m6i-b成果物の選択コピーだけで生成する。"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import build_m6ib_measure_rom as m6ib  # noqa: E402
import build_m6ic_measure_rom as m6ic  # noqa: E402

ARMS = ("G-N", "G-L0", "G-L1", "G-L2")
MAIN_SOURCE = {"G-N": "B0", "G-L0": "B1", "G-L1": "B4", "G-L2": "B5"}


def build_m6ib(outdir: pathlib.Path, work_dir: pathlib.Path, arm: str) -> None:
    subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_m6ib_measure_rom.py"),
         str(outdir), "--arm", arm, "--work-dir", str(work_dir)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--work-dir", required=True, type=pathlib.Path)
    args = ap.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    plain = args.work_dir / "source-b0"
    source_arm = MAIN_SOURCE[args.arm]
    source = plain if source_arm == "B0" else args.work_dir / f"source-{source_arm.lower()}"
    build_m6ib(plain, args.work_dir / "build-b0", "B0")
    if source != plain:
        build_m6ib(source, args.work_dir / f"build-{source_arm.lower()}", source_arm)

    # C2の選択規則は「mainを第1引数、DISKを第2引数」なので、そのまま再利用する。
    m6ic.copy_rom_set(args.outdir, source, plain, "C2")
    if not m6ib.sizes_valid(args.outdir):
        raise SystemExit("ROM一式のファイル集合またはサイズが所定構成と一致しない")
    print(f"arm={args.arm}")
    print("build_completed=true")
    print(f"rom_set_sha256={m6ib.rom_set_sha256(args.outdir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
