#!/usr/bin/env python3
"""m6i-a/b/c/e/g/h全腕と自己検査構成を組むだけの一括確認（実走なし）。"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile

import build_m6ib_measure_rom as m6ib


REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=1, help="同時ビルド数（既定1）")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobsは1以上")
    cases = []
    for family in ("a", "b", "c", "e", "g", "h"):
        module = importlib.import_module(f"build_m6i{family}_measure_rom")
        for arm in module.ARMS:
            cases.append((f"m6i{family}-{arm}", Path(module.__file__),
                          ["--arm", arm], False))

    # 通常構成と、main側にコードを追加する自己検査の併用も組む。
    main_builder = REPO / "src/build_main_rom.py"
    for name, flags in (
        ("default", []),
        ("l4", ["--enable-l4-selftest"]),
        ("l4-no-read", ["--enable-l4-selftest", "--disable-main-sub-read"]),
        ("ext", ["--enable-ext-bank-selftest"]),
        ("vsync", ["--enable-vsync-regcheck"]),
        ("l4-ext-vsync", ["--enable-l4-selftest", "--enable-ext-bank-selftest",
                          "--enable-vsync-regcheck"]),
    ):
        cases.append((name, main_builder, flags, True))
    for flag in ("--enable-main-sub-read", "--inject-main-sub-wait-fault",
                 "--inject-main-sub-cont-fault", "--inject-main-sub-pair-fault",
                 *(f"--inject-m6ib-b{i}" for i in range(1, 6)),
                 "--inject-m6ih-a", "--inject-m6ih-b",
                 "--inject-m6ie-single-read", "--inject-m6ie-nops-only"):
        cases.append(("l4-" + flag[2:], main_builder,
                      [flag, "--enable-l4-selftest"], True))

    failed = []
    with tempfile.TemporaryDirectory(prefix="m6i-builds-") as tmp:
        def build_case(case):
            name, builder, flags, with_n = case
            work = Path(tmp) / name
            out = work / "rom"
            result = subprocess.run(
                [sys.executable, str(builder), str(out), "--work-dir",
                 str(work / "asm"), *flags], capture_output=True, text=True)
            sizes = dict(m6ib.EXPECTED_SIZES)
            if with_n:
                sizes["N88N.ROM"] = 0x8000
            valid = (result.returncode == 0 and out.is_dir()
                     and {p.name for p in out.iterdir() if p.is_file()} == set(sizes)
                     and all((out / file).stat().st_size == size
                             for file, size in sizes.items())
                     and (out / "N88.ROM").read_bytes()[0x79D7] == ord("4"))
            return name, valid, result.stdout + result.stderr

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for name, valid, detail in pool.map(build_case, cases):
                print(f"{'PASS' if valid else 'FAIL'}: {name}", flush=True)
                if not valid:
                    failed.append(name)
                    print(detail, file=sys.stderr)

        # CLIに自己検査フラグがないB6も、L4の表・照合器を含めて組む。
        # 実走せずmain/N双方の配置検査まで実施する。
        for arm in m6ib.B6_BRANCHES:
            name = "l4-" + arm
            work = Path(tmp) / name
            try:
                rom, asm = m6ib.assemble_main_for_arm(work, arm, enable_l4_selftest=True)
                m6ib.mainrom.build_n_rom(rom, asm, work, enable_l4_selftest=True)
            except (SystemExit, Exception) as exc:
                failed.append(name)
                print(f"FAIL: {name}: {exc}", flush=True)
            else:
                print(f"PASS: {name}", flush=True)
    total = len(cases) + len(m6ib.B6_BRANCHES)
    print(f"測定ROMビルド: {total - len(failed)}/{total} PASS")
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
