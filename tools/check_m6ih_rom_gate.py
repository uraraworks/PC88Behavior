#!/usr/bin/env python3
"""m6i-h G4のsub無改変、main直交、無固定待ち、ROMサイズを検査する。"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import src.build_main_rom as mainrom  # noqa: E402
import src.l3_service.make_subrom as subrom  # noqa: E402
sys.path.insert(0, str(REPO / "tools"))
import build_m6ib_measure_rom as m6ib  # noqa: E402
import build_m6ih_measure_rom as m6ih  # noqa: E402

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


def no_frame_wait_and_matches(directory: pathlib.Path, work: pathlib.Path, arm: str,
                              b4_main: bytes | None) -> bool:
    """ラベルで起動部を切り、listingの命令列と原文の双方で0xE009参照を拒否する。

    M6IB_FRAME_COUNTはEQUとして共通表に残るため、シンボルの存在自体ではなく、
    MAIN_SUB_READ_BOOT_ONCE..MAIN_SUB_LINK_ENDにある各命令のオペランド
    (little endian 09 E0)とlisting原文のシンボル参照を調べる。成果物との
    一致も同時に確認するので、別mainへの差替えでは検査を迂回できない。
    """
    try:
        artifact = read(directory, "N88.ROM")
        if arm == "H-W":
            # 自己検査では既知の待ちありmainを同じ解析経路へ通す。
            rom, asm = m6ib.assemble_main_for_arm(work / "b4-control", "B4")
        else:
            rom, asm = m6ih.assemble_main_for_arm(work / "intended", arm)
        if artifact != rom:
            # 陰性対照のB4差替えも、単なる不一致だけでなくB4自身のラベル表と
            # コード列を検査し、フレーム番地参照・waitラベルを実際に検出する。
            if artifact != b4_main:
                return False
            rom, asm = m6ib.assemble_main_for_arm(work / "b4-control", "B4")
        start = asm.labels["MAIN_SUB_READ_BOOT_ONCE"]
        end = asm.labels["MAIN_SUB_LINK_END"]
    except (OSError, KeyError, SystemExit):
        return False
    rows = [(addr, data, raw) for addr, data, _line, raw in asm.listing
            if start <= addr < end]
    frame_ref = any(b"\x09\xe0" in data or "M6IB_FRAME_COUNT" in raw
                    for _addr, data, raw in rows)
    wait_label = any(start <= value < end and "wait" in name.lower()
                     for name, value in asm.labels.items())
    return artifact == rom and start < end and bool(rows) and not frame_ref and not wait_label


def retry_allocation_valid(config: pathlib.Path, work: pathlib.Path) -> bool:
    try:
        address = int(cfg_one(config, "retry_marker_address") or "", 0)
        _rom, asm = m6ih.assemble_main_for_arm(work, "H-B")
    except (ValueError, OSError, SystemExit):
        return False
    names = {name for name, value in asm.symtab.items() if value == address}
    retry_writes = [raw for _addr, _data, _line, raw in asm.listing
                    if "(M6IH_MARK_RETRY),A" in raw]
    return address == 0xE00D and names == {"M6IH_MARK_RETRY"} and len(retry_writes) == 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("h_n", "h_w", "h_a", "h_b"):
        ap.add_argument(f"{name}_dir", type=pathlib.Path)
    ap.add_argument("--m6ib-b0-dir", required=True, type=pathlib.Path)
    ap.add_argument("--m6ib-b4-dir", required=True, type=pathlib.Path)
    ap.add_argument("--work-dir", required=True, type=pathlib.Path)
    ap.add_argument("--config", type=pathlib.Path, default=REPO / "tools/m6ih_frozen.tsv")
    args = ap.parse_args()
    dirs = {"H-N": args.h_n_dir, "H-W": args.h_w_dir,
            "H-A": args.h_a_dir, "H-B": args.h_b_dir}
    plain, _used = subrom.build()
    plain_bytes = bytes(plain)
    disks = {arm: read(path, "DISK.ROM") for arm, path in dirs.items()}
    mains = {arm: read(path, "N88.ROM") for arm, path in dirs.items()}
    checks = {
        "plain_subrom_frozen_match": hashlib.sha256(plain_bytes).hexdigest()
                                      == cfg_one(args.config, "plain_subrom_sha256"),
        "all_disks_identical": all(value is not None and value == disks["H-N"]
                                  for value in disks.values()),
        "disks_match_plain_subrom": all(value == plain_bytes for value in disks.values()),
        "common_roms_identical": all(
            read(path, name) is not None and read(path, name) == read(dirs["H-N"], name)
            for name in COMMON_ROMS for path in dirs.values()),
        "all_mains_distinct": all(value is not None for value in mains.values())
                              and len(set(mains.values())) == 4,
        "mains_match_m6ib_sources": (mains["H-N"] == read(args.m6ib_b0_dir, "N88.ROM")
                                     and mains["H-W"] == read(args.m6ib_b4_dir, "N88.ROM")),
        "new_mains_have_no_frame_wait": all(
            no_frame_wait_and_matches(dirs[arm], args.work_dir / arm, arm,
                                      read(args.m6ib_b4_dir, "N88.ROM"))
            for arm in ("H-A", "H-B")),
        "retry_marker_allocation": retry_allocation_valid(
            args.config, args.work_dir / "retry-allocation"),
        "all_sizes_valid": all(path.is_dir() and m6ib.sizes_valid(path)
                               for path in dirs.values()),
    }
    for name, result in checks.items():
        print(f"{name}={'OK' if result else 'NG'}")
    passed = all(checks.values())
    print(f"passed={'true' if passed else 'false'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
