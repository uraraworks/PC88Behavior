#!/usr/bin/env python3
"""単精度FINの各段を第5.1.1節のGW規則と照合する。公式ROM・凍結値は使わない。

既存の数値ハーネスで自作Z80コードを実行し、整数の倍精度化、表の展開、
倍精度の指数適用、CSDの狭めを別々に比較する。計測用の複写だけを挿入し、
srcは変更しない。出力は件数と段名のみ。中間値の記録は自作の計算値である。
"""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path

import l4_mbf_conform as harness


SCRATCH = 0xB800
STAGE_LEN = 9
OUT_LEN = 5 + 3 * STAGE_LEN
STAGES = ("integer", "table", "scale", "narrow")


def vectors():
    # 対象2定数、指数の上下と仮数の近傍、正符号の対照。
    cases = [(sign * acc, exponent)
             for sign in (-1, 1)
             for acc in (1, 9, 10, 11, 99, 101, 999999, 1000001, 1234567)
             for exponent in range(-38, 32)
             if exponent != 0]
    # 小数点による正味指数の計算も同じ段で確認する。
    result = [(f"{acc}e{exponent:+d}", abs(acc), exponent, int(acc < 0))
              for acc, exponent in cases
              if abs(Fraction(acc) * Fraction(10) ** exponent) < Fraction(2) ** 126]
    result.extend((f"{sign}{digits}e{exponent:+d}", acc, exponent - places, int(bool(sign)))
                  for sign in ("", "-")
                  for digits, acc, places in ((".1", 1, 1), ("1.01", 101, 2),
                                               (".999999", 999999, 6))
                  for exponent in (-20, -10, -1, 1, 10, 20)
                  if exponent != places)
    return result


def snapshot(prefix, slot):
    fields = [f"{prefix}_SIGN", f"{prefix}_EXP"] + [f"{prefix}_M{i}" for i in range(6, -1, -1)]
    lines = ["    PUSH AF"]
    for offset, field in enumerate(fields):
        lines.extend((f"    LD A,({field})", f"    LD ({SCRATCH + slot * STAGE_LEN + offset}),A"))
    lines.append("    POP AF")
    return "\n".join(lines) + "\n"


def instrument(source):
    start = source.index("_fin_scale_nonzero_exact:\n")
    end = source.index("_finXF_overflow:\n", start)
    section = source[start:end]
    for instruction, prefix, slot, count in (
        ("    CALL UDWORD_TO_DOUBLE\n", "DA", 0, 1),
        ("    CALL DBL_TABLE_LOOKUP\n", "DB", 1, 2),
    ):
        if section.count(instruction) != count:
            raise RuntimeError(f"計測点が変わった: {instruction.strip()}")
        section = section.replace(instruction, instruction + snapshot(prefix, slot))
    instruction = "    CALL DBL_TO_SINGLE_CSD\n"
    if section.count(instruction) != 1:
        raise RuntimeError("CSDの計測点が変わった")
    section = section.replace(instruction, snapshot("DA", 2) + instruction)
    return source[:start] + section + source[end:]


def unpack_stage(raw):
    sign, exponent = raw[:2]
    return sign, exponent, int.from_bytes(raw[2:], "big")


def double_parts(value):
    return harness.oracle.encode_mbf(value, 56)


def predictions(acc, exponent, sign):
    oracle = harness.oracle
    integer = Fraction(acc) * (-1 if sign else 1)
    table = oracle._pow10_as_double(abs(exponent))
    scaled = oracle._round_to_double(integer * table if exponent > 0 else integer / table)
    double = oracle.GwNum.from_fraction(scaled, "double")
    narrow = harness.gwnum_bytes(oracle.force_to_single(double)) + bytes([0])
    return double_parts(integer), double_parts(table), double_parts(scaled), narrow


def run(workdir, frames):
    workdir.mkdir(parents=True, exist_ok=True)
    source = instrument(harness.load_mbf_src(None))
    original_driver = harness.build_driver_asm

    def stage_driver(op, count, mbf_src):
        driver = original_driver(op, count, mbf_src)
        copy = []
        for offset in range(3 * STAGE_LEN):
            copy.extend((f"    LD A,({SCRATCH + offset})", "    LD (DE),A", "    INC DE"))
        marker = "    DEC BC\n"
        return driver.replace(marker, "\n".join(copy) + "\n" + marker, 1)

    cases = vectors()
    mismatches = {stage: 0 for stage in STAGES}
    records = []
    # 最終値のみの既存ドライバとも照合し、計測用複写の影響を検出する。
    plain_mismatches = 0
    try:
        for start in range(0, len(cases), 96):
            chunk = cases[start:start + 96]
            inputs = [(case[0],) for case in chunk]
            stage_work = workdir / f"stages-{start}"
            stage_work.mkdir(exist_ok=True)
            harness.build_driver_asm = stage_driver
            rom = harness.assemble_rom("fin", inputs, source, stage_work)
            memory = harness.run_and_collect(rom, len(chunk) * OUT_LEN, stage_work, frames)
            harness.build_driver_asm = original_driver
            plain_work = workdir / f"plain-{start}"
            plain_work.mkdir(exist_ok=True)
            rom = harness.assemble_rom("fin", inputs, harness.load_mbf_src(None), plain_work)
            plain = harness.run_and_collect(rom, len(chunk) * 5, plain_work, frames)
            for index, (text, acc, exponent, sign) in enumerate(chunk):
                base = harness.OUT_BASE + index * OUT_LEN
                raw = bytes(memory[base + offset] for offset in range(OUT_LEN))
                plain_raw = bytes(plain[harness.OUT_BASE + index * 5 + offset] for offset in range(5))
                plain_mismatches += raw[:5] != plain_raw
                actual = tuple(unpack_stage(raw[5 + slot * STAGE_LEN:5 + (slot + 1) * STAGE_LEN])
                               for slot in range(3)) + (raw[:5],)
                expected = predictions(acc, exponent, sign)
                agreement = dict(zip(STAGES, (a == b for a, b in zip(actual, expected))))
                for stage, agrees in agreement.items():
                    mismatches[stage] += not agrees
                records.append(dict(literal=text, actual=[list(v) if isinstance(v, tuple) else v.hex()
                                                          for v in actual],
                                    model=[list(v) if isinstance(v, tuple) else v.hex() for v in expected],
                                    agreement=agreement))
    finally:
        harness.build_driver_asm = original_driver
    summary = dict(count=len(cases), mismatches=mismatches, instrumentation_mismatches=plain_mismatches)
    (workdir / "stages.json").write_text(json.dumps(dict(summary=summary, records=records), indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return int(any(mismatches.values()) or plain_mismatches != 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--frames", type=int, default=3000)
    args = parser.parse_args()
    return run(args.workdir.resolve(), args.frames)


if __name__ == "__main__":
    raise SystemExit(main())
