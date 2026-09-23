#!/usr/bin/env python3
"""m6i-hの4腕を、m6i-b成果物の組替えまたは新規mainで生成する。"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import src.build_main_rom as mainrom  # noqa: E402
sys.path.insert(0, str(REPO / "tools"))
import build_m6ib_measure_rom as m6ib  # noqa: E402
import build_m6ig_measure_rom as m6ig  # noqa: E402

ARMS = ("H-N", "H-W", "H-A", "H-B")
MAIN_SOURCE = {"H-N": "B0", "H-W": "B4"}


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def assemble_main_for_arm(work: pathlib.Path, arm: str):
    """H-A/H-Bのmainとラベル・listingをG4検査用に再生成する。"""
    if arm not in ("H-A", "H-B"):
        raise SystemExit(f"新規mainではない腕: {arm}")
    work.mkdir(parents=True, exist_ok=True)
    combined = mainrom.build_combined_asm(
        work, 0, False, enable_main_sub_read=True,
        inject_m6ih_a=arm == "H-A", inject_m6ih_b=arm == "H-B")
    return mainrom.assemble(combined, work)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--work-dir", required=True, type=pathlib.Path)
    args = ap.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)

    if args.arm in MAIN_SOURCE:
        # H-N/H-Wは新しく組まず、登録済みm6i-b成果物をそのまま組み替える。
        plain = args.work_dir / "source-b0"
        source_arm = MAIN_SOURCE[args.arm]
        source = plain if source_arm == "B0" else args.work_dir / "source-b4"
        m6ig.build_m6ib(plain, args.work_dir / "build-b0", "B0")
        if source != plain:
            m6ig.build_m6ib(source, args.work_dir / "build-b4", "B4")
        # m6i-gと同じC2選択規則（mainを第1、DISK等を第2引数）を再利用する。
        m6ig.m6ic.copy_rom_set(args.outdir, source, plain, "C2")
    else:
        flag = "--inject-m6ih-a" if args.arm == "H-A" else "--inject-m6ih-b"
        run([sys.executable, str(REPO / "src/build_main_rom.py"), str(args.outdir),
             flag, "--work-dir", str(args.work_dir / "base")])

    if not m6ib.sizes_valid(args.outdir):
        raise SystemExit("ROM一式のファイル集合またはサイズが所定構成と一致しない")
    print(f"arm={args.arm}")
    print("build_completed=true")
    print(f"rom_set_sha256={m6ib.rom_set_sha256(args.outdir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
