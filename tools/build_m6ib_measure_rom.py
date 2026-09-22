#!/usr/bin/env python3
"""m6i-b B0〜B6の介入ROM一式を、登録済みフラグだけで生成する。"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import subprocess
import sys


REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import src.build_main_rom as mainrom  # noqa: E402
sys.path.insert(0, str(REPO / "tools"))
import build_m6ia_measure_rom as m6ia  # noqa: E402

EXPECTED_SIZES = {
    "N88.ROM": 0x8000,
    "DISK.ROM": 0x2000,
    "FONT.ROM": 0x1000,
    "N88_0.ROM": 0x2000,
    "N88_1.ROM": 0x2000,
    "N88_2.ROM": 0x2000,
    "N88_3.ROM": 0x2000,
}
B6_BRANCHES = ("B6-A0", "B6-A1", "B6-A2", "B6-A4-cont", "B6-A4-pair", "B6-A5")
ARMS = ("B0", "B1", "B2", "B3", "B4", "B5") + B6_BRANCHES


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


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label}の差し替え対象が一意でない")
    return text.replace(old, new)


def _b6_boot(branch: str) -> str:
    tag = B6_BRANCHES.index(branch) + 1
    init = mainrom.M6IB_INIT.replace(
        "    RET\n", f"    LD A,{tag:03X}h\n    LD (M6IB_BRANCH_TAG),A\n    RET\n")
    prefix = mainrom.M6IB_COMMON_EQU + "M6IB_BRANCH_TAG          EQU 0E00Dh\n" + init + """
MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,(M6IB_STAGE)
    OR A
    JR NZ,_m6ib_b6_wait
    XOR A
    CALL MAIN_SUB_SEND
    RET C
    LD A,001h
    LD (M6IB_MARK_B),A
    XOR A
    CALL MAIN_SUB_SEND
    RET C
    LD A,007h
    CALL MAIN_SUB_SEND_CONT
    RET C
    CALL MAIN_SUB_RECV
    RET C
    LD A,001h
    LD (M6IB_MARK_C),A
    LD (M6IB_STAGE),A
_m6ib_b6_wait:
    LD A,(M6IB_FRAME_COUNT)
    CP 037h
    JR Z,_m6ib_b6_run
    INC A
    LD (M6IB_FRAME_COUNT),A
    RET
_m6ib_b6_run:
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
"""
    if branch != "B6-A5":
        return prefix + """    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET
"""

    a5_boot_body, a5_helpers = m6ia.BOOT_A5.split("; PUSH順", 1)
    loop = a5_boot_body.split("    LD HL,00C8h", 1)[1]
    return prefix + "    LD HL,00C8h" + loop + "; PUSH順" + a5_helpers


def assemble_main_for_arm(work: pathlib.Path, arm: str):
    """腕専用mainを組み、ROMと実アセンブラ情報を返す。"""
    work.mkdir(parents=True, exist_ok=True)
    kwargs = {"enable_main_sub_read": True}
    if arm in ("B1", "B2", "B3", "B4", "B5"):
        kwargs[f"inject_m6ib_{arm.lower()}"] = True
    elif arm in B6_BRANCHES:
        kwargs["inject_m6ib_b5"] = True
        kwargs["inject_main_sub_cont_fault"] = arm == "B6-A4-cont"
        kwargs["inject_main_sub_pair_fault"] = arm == "B6-A4-pair"
    elif arm != "B0":
        raise SystemExit(f"未知の腕: {arm}")

    combined = mainrom.build_combined_asm(work, 0, False, **kwargs)
    generated = work / "main_sub_read_gen.asm"
    text = generated.read_text(encoding="utf-8")
    if arm in B6_BRANCHES:
        text = _replace_once(text, mainrom.M6IB_BOOT_B5, _b6_boot(arm), arm)
        if arm == "B6-A1":
            text = _replace_once(text, m6ia.SECTOR_OLD, m6ia.SECTOR_NEW, arm)
        generated.write_text(text, encoding="utf-8")
    return mainrom.assemble(combined, work)


def _base_cli_arm(arm: str) -> list[str]:
    if arm == "B0":
        return ["--enable-main-sub-read"]
    if arm in ("B1", "B2", "B3", "B4", "B5"):
        return [f"--inject-m6ib-{arm.lower()}"]
    # B6はB5と同じmain前置きを使うが、前置き後に停止するB5専用sub介入は
    # 引き継がない。m6i-aの枝を通常のsub経路で再走する。
    flags = ["--enable-main-sub-read"]
    if arm == "B6-A4-cont":
        flags.append("--inject-main-sub-cont-fault")
    elif arm == "B6-A4-pair":
        flags.append("--inject-main-sub-pair-fault")
    return flags


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--work-dir", required=True, type=pathlib.Path)
    args = ap.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(REPO / "src" / "build_main_rom.py"),
           str(args.outdir), "--work-dir", str(args.work_dir / "base"),
           *_base_cli_arm(args.arm)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rom, asm = assemble_main_for_arm(args.work_dir / "main", args.arm)
    (args.outdir / "N88.ROM").write_bytes(rom)

    if not sizes_valid(args.outdir):
        raise SystemExit("ROM一式のファイル集合またはサイズが所定構成と一致しない")

    print(f"arm={args.arm}")
    print("build_completed=true")
    print(f"main_sub_link_size={asm.labels['MAIN_SUB_LINK_END'] - asm.labels['MAIN_SUB_LINK_START']}")
    print(f"rom_set_sha256={rom_set_sha256(args.outdir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
