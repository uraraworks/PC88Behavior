#!/usr/bin/env python3
"""m6i-b G6のROM同一性・相互差異・サイズ・命令境界を検査する。"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys


REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import build_m6ib_measure_rom as m6ib  # noqa: E402
sys.path.insert(0, str(REPO))
import src.build_main_rom as mainrom  # noqa: E402
sys.path.insert(0, str(REPO / "src" / "l3_service"))
import make_subrom as subrom  # noqa: E402


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def same_tree(left: pathlib.Path, right: pathlib.Path) -> bool:
    return all((left / name).read_bytes() == (right / name).read_bytes()
               for name in m6ib.EXPECTED_SIZES)


def main_instruction_boundaries_valid(outdir: pathlib.Path, work: pathlib.Path,
                                      arm: str) -> tuple[bool, bool]:
    """main介入部の両端がアセンブラの発行単位境界にあり、成果物と一致する。"""
    work.mkdir(parents=True, exist_ok=True)
    kwargs = {"enable_main_sub_read": True}
    if arm != "control":
        kwargs[f"inject_m6ib_{arm.lower()}"] = True
    text = mainrom.build_combined_asm(work, 0, False, **kwargs)
    rom, asm = mainrom.assemble(text, work)
    if rom != (outdir / "N88.ROM").read_bytes():
        return False, False
    boundaries = {0, len(asm.code)}
    for addr, data, _line_no, _raw in asm.listing:
        boundaries.add(addr)
        boundaries.add(addr + len(data))
    start = asm.labels.get("MAIN_SUB_LINK_START")
    end = asm.labels.get("MAIN_SUB_LINK_END")
    boundary_ok = (
        start in boundaries
        and end in boundaries
        and start is not None
        and end is not None
        and start <= end == len(asm.code)
        and end - start <= mainrom.MAIN_SUB_LINK_MAX_SIZE
        and rom[mainrom.ROM_VERSION_RESERVED_ADDR] == mainrom.FILL
    )
    allocation_ok = True
    if arm != "control":
        expected = {
            0xE009: "M6IB_FRAME_COUNT",
            0xE00A: "M6IB_STAGE",
            0xE00B: "M6IB_MARK_B",
            0xE00C: "M6IB_MARK_C",
        }
        for addr, owner in expected.items():
            names = {name for name, value in asm.symtab.items() if value == addr}
            allocation_ok &= names == {owner}
    return boundary_ok, allocation_ok


def sub_instruction_boundaries_valid(outdir: pathlib.Path, arm: str,
                                     inject_boundary_fault: bool) -> bool:
    """subの実アセンブラ区間を使い、フェッチ窓跨ぎと窓外到達を検査する。"""
    kwargs = {}
    if arm != "control":
        kwargs[f"inject_m6ib_{arm.lower()}"] = True
    rom, used = subrom.build(**kwargs)
    asm = subrom._LAST_ASM
    artifact = (outdir / "DISK.ROM").read_bytes()
    if artifact[:used] != bytes(rom)[:used]:
        return False
    boundary = subrom.SUB_ROM_FETCH_WINDOW
    if inject_boundary_fault:
        operands = {pos for pos, _name, _kind in asm.fixups}
        pos, _width = next(
            (pos, width) for pos, width in asm.instr_spans
            if width >= 2 and pos not in operands
        )
        boundary = pos + 1
    return (
        not subrom.find_fetch_window_straddles(asm, boundary)
        and not subrom.find_out_of_window_blocks(asm, boundary)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", required=True, type=pathlib.Path)
    ap.add_argument("--fault", choices=("size", "instruction-boundary"),
                    help="検出力確認専用: 実成果物サイズまたは実命令区間の境界を壊す")
    args = ap.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)

    m6ia_dir = args.work_dir / "m6ia-a0"
    control_dir = args.work_dir / "control"
    run([sys.executable, str(REPO / "tools" / "build_m6ia_measure_rom.py"),
         str(m6ia_dir), "--arm", "A0", "--work-dir", str(args.work_dir / "asm-a0")])
    run([sys.executable, str(REPO / "tools" / "build_m6ib_measure_rom.py"),
         str(control_dir), "--arm", "control", "--work-dir", str(args.work_dir / "asm-control")])

    dirs: dict[str, pathlib.Path] = {"control": control_dir}
    for arm in ("B1", "B2", "B5"):
        outdir = args.work_dir / arm.lower()
        run([sys.executable, str(REPO / "tools" / "build_m6ib_measure_rom.py"),
             str(outdir), "--arm", arm, "--work-dir", str(args.work_dir / f"asm-{arm.lower()}")])
        dirs[arm] = outdir

    if args.fault == "size":
        target = dirs["B1"] / "DISK.ROM"
        target.write_bytes(target.read_bytes()[:-1])

    control_matches = same_tree(m6ia_dir, control_dir)
    hashes = {name: m6ib.rom_set_sha256(path) for name, path in dirs.items()}
    mutually_distinct = len(set(hashes.values())) == len(hashes)
    size_gate = all(m6ib.sizes_valid(path) for path in dirs.values())
    boundary_results = []
    allocation_results = []
    for arm, outdir in dirs.items():
        main_boundary, allocation = main_instruction_boundaries_valid(
            outdir, args.work_dir / f"verify-main-{arm.lower()}", arm)
        boundary_results.append(main_boundary)
        allocation_results.append(allocation)
        boundary_results.append(sub_instruction_boundaries_valid(
            outdir, arm,
            inject_boundary_fault=(args.fault == "instruction-boundary" and arm == "B1")))
    instruction_boundary_gate = all(boundary_results)
    ram_allocation_gate = all(allocation_results)
    passed = (control_matches and mutually_distinct and size_gate
              and instruction_boundary_gate and ram_allocation_gate)
    payload = {
        "gate": "rom_nonempty",
        "passed": passed,
        "control_matches_m6ia_a0": control_matches,
        "all_rom_sets_mutually_distinct": mutually_distinct,
        "size_gate": size_gate,
        "instruction_boundary_gate": instruction_boundary_gate,
        "ram_allocation_gate": ram_allocation_gate,
        "fault_injection": args.fault,
        "sha256": hashes,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
