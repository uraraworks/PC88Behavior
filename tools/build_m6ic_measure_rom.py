#!/usr/bin/env python3
"""m6i-c C0〜C3のROM一式を、m6i-b成果物の組み合わせで生成する。"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys


REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import build_m6ib_measure_rom as m6ib  # noqa: E402

ARMS = ("C0", "C1", "C2", "C3")
BASE_ARMS = {"C0": "B5", "C1": "B6-A0"}
COMMON_ROMS = tuple(
    name for name in m6ib.EXPECTED_SIZES if name not in ("N88.ROM", "DISK.ROM")
)


def build_m6ib(outdir: pathlib.Path, work_dir: pathlib.Path, arm: str) -> None:
    """既存ビルダーだけを使って m6i-b の基底腕を生成する。"""
    subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_m6ib_measure_rom.py"),
         str(outdir), "--arm", arm, "--work-dir", str(work_dir)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def copy_rom_set(outdir: pathlib.Path, c0_dir: pathlib.Path,
                 c1_dir: pathlib.Path, arm: str) -> None:
    """C0/C1の実成果物を選択コピーし、混成腕を作る。"""
    if not all((c0_dir / name).read_bytes() == (c1_dir / name).read_bytes()
               for name in COMMON_ROMS):
        raise SystemExit("C0/C1の共通ROMが一致しない")
    outdir.mkdir(parents=True, exist_ok=True)
    main_source = c0_dir if arm == "C2" else c1_dir
    disk_source = c1_dir if arm == "C2" else c0_dir
    sources = {"N88.ROM": main_source, "DISK.ROM": disk_source}
    sources.update({name: c0_dir for name in COMMON_ROMS})
    for name, source_dir in sources.items():
        shutil.copyfile(source_dir / name, outdir / name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--work-dir", required=True, type=pathlib.Path)
    args = ap.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    if args.arm in BASE_ARMS:
        build_m6ib(args.outdir, args.work_dir / "m6ib", BASE_ARMS[args.arm])
    else:
        c0_dir = args.work_dir / "source-c0"
        c1_dir = args.work_dir / "source-c1"
        build_m6ib(c0_dir, args.work_dir / "build-c0", BASE_ARMS["C0"])
        build_m6ib(c1_dir, args.work_dir / "build-c1", BASE_ARMS["C1"])
        copy_rom_set(args.outdir, c0_dir, c1_dir, args.arm)

    if not m6ib.sizes_valid(args.outdir):
        raise SystemExit("ROM一式のファイル集合またはサイズが所定構成と一致しない")
    print(f"arm={args.arm}")
    print("build_completed=true")
    print(f"rom_set_sha256={m6ib.rom_set_sha256(args.outdir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
