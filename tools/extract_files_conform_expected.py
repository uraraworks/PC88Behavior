#!/usr/bin/env python3
"""m6f-e の3観測JSONから FILES 適合試験用の行署名だけを抽出する。"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import predict_m6fe  # noqa: E402


BASE_ARMS = (
    "L0", "L1", "L4", "L5", "L6", "L11", "L96",
    "D-omit", "D-1", "D-2", "D-expr", "E-0", "E-3", "E-str", "N-wait",
)
ADD2_ARMS = ("L80", "L85", "L90", "L95", "L96'")
ADD3_ARMS = ("L81", "L86", "L91", "L90'")
# m6f-g: 種別の印(0xA0=ピリオド・0x01=アスタリスク、docs/spec/l4-basic.md
# 第3.12版11.1節規則3)と、大きさ3桁(100・158単位)。
G_ARMS = ("G-P", "G-B", "G-M", "G-Z1", "G-Z2")
G_FORMAT = "m6fg-observations-v1"
FORMATS = (
    "m6fe-observations-v1",
    "m6fe-add2-observations-v1",
    "m6fe-add3-observations-v1",
)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
EXPECTATIONS = {
    "L0": "media:L0", "L1": "media:L1", "L4": "media:L4",
    "L5": "media:L5", "L6": "media:L6", "L11": "media:L11",
    "L96": "media:L96", "D-omit": "drive:1", "D-1": "drive:1",
    "D-2": "drive:2", "D-expr": "drive_expr:2", "E-0": "error:70",
    "E-3": "error:70", "E-str": "error:13", "N-wait": "wait_then:L1",
    "L80": "media:L80", "L85": "media:L85", "L90": "media:L90",
    "L95": "media:L95", "L96'": "media:L96p", "L81": "media:L81",
    "L86": "media:L86", "L91": "media:L91", "L90'": "media:L90p",
    "G-P": "mark:2E", "G-B": "mark:2A", "G-M": "mixed:2E2A",
    "G-Z1": "size:100", "G-Z2": "size:158",
}


class ExtractError(ValueError):
    pass


def fail(reason: str) -> None:
    # 入力値や画面由来値を例外へ反射しない。
    raise ExtractError(reason)


def load_one(path: pathlib.Path, expected_format: str,
             wanted_arms: tuple[str, ...]) -> dict[str, tuple[tuple[int, int, str], ...]]:
    try:
        root = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail("input_read")
    if not isinstance(root, dict) or root.get("format") != expected_format:
        fail("input_format")
    arms = root.get("arms")
    if not isinstance(arms, dict) or not set(wanted_arms).issubset(arms):
        fail("arm_set")
    result: dict[str, tuple[tuple[int, int, str], ...]] = {}
    for arm in wanted_arms:
        runs = arms.get(arm)
        if not isinstance(runs, list) or len(runs) != 2:
            fail("run_count")
        parsed_runs = []
        for run in runs:
            if not isinstance(run, dict) or not isinstance(run.get("entry_lines"), list):
                fail("entry_lines")
            parsed = []
            seen = set()
            for item in run["entry_lines"]:
                if not isinstance(item, dict) or set(item) != {
                        "physical_row", "char_count", "sha256"}:
                    fail("line_fields")
                row, count, digest = item["physical_row"], item["char_count"], item["sha256"]
                if (not isinstance(row, int) or isinstance(row, bool) or row < 0 or row > 24
                        or row in seen or not isinstance(count, int) or isinstance(count, bool)
                        or count < 0 or count > 80 or not isinstance(digest, str)
                        or SHA256_RE.fullmatch(digest) is None):
                    fail("line_value")
                seen.add(row)
                parsed.append((row, count, digest))
            if parsed != sorted(parsed):
                fail("line_order")
            parsed_runs.append(tuple(parsed))
        if parsed_runs[0] != parsed_runs[1]:
            fail("two_runs_differ")
        result[arm] = parsed_runs[0]
    return result


def error_signature(number: int) -> tuple[tuple[int, int, str], ...]:
    return tuple((line.physical_row, line.char_count, line.sha256)
                 for line in predict_m6fe.predict_error(number))


def validate_relations(values: dict[str, tuple[tuple[int, int, str], ...]]) -> None:
    if values["E-0"] != error_signature(70) or values["E-3"] != error_signature(70):
        fail("error_70_signature")
    if values["E-str"] != error_signature(13):
        fail("error_13_signature")
    if values["N-wait"] != values["L1"]:
        fail("wait_l1_signature")
    if values["D-omit"] != values["D-1"]:
        fail("default_drive_signature")
    if values["D-expr"] != values["D-2"]:
        fail("drive_expression_signature")
    if values["D-1"] == values["D-2"]:
        fail("drive_signatures_not_distinct")


def load_g(path: pathlib.Path) -> dict[str, tuple[tuple[int, int, str], ...]]:
    """m6f-g の単一観測JSON(G_FORMAT)から5腕ぶんの行署名を取り出す。"""
    return load_one(path, G_FORMAT, G_ARMS)


def validate_g_relations(values: dict[str, tuple[tuple[int, int, str], ...]]) -> None:
    if values["G-P"] == values["G-B"]:
        fail("g_mark_signatures_not_distinct")
    if values["G-Z1"] == values["G-Z2"]:
        fail("g_size_signatures_not_distinct")


def render_arm_block(arm: str, rows: tuple[tuple[int, int, str], ...]) -> list[str]:
    return [f"arm\t{arm}\t{EXPECTATIONS[arm]}\t-\t{len(rows)}\t-"] + [
        f"row\t{arm}\t-\t{row}\t{count}\t{digest}" for row, count, digest in rows]


def render(values: dict[str, tuple[tuple[int, int, str], ...]]) -> str:
    lines = [
        "# files-conform-expected-v1",
        "# kind\\tarm\\texpectation\\tphysical_row\\tchar_count\\tsha256",
    ]
    for arm in BASE_ARMS + ADD2_ARMS + ADD3_ARMS:
        lines.extend(render_arm_block(arm, values[arm]))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_observations", type=pathlib.Path)
    parser.add_argument("add2_observations", type=pathlib.Path)
    parser.add_argument("add3_observations", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    try:
        values: dict[str, tuple[tuple[int, int, str], ...]] = {}
        for path, fmt, arms in zip(
                (args.base_observations, args.add2_observations, args.add3_observations),
                FORMATS, (BASE_ARMS, ADD2_ARMS, ADD3_ARMS)):
            values.update(load_one(path, fmt, arms))
        validate_relations(values)
        if args.output.exists():
            fail("output_exists")
        args.output.write_text(render(values), encoding="ascii", newline="")
    except ExtractError as exc:
        print(f"NG {exc}", file=sys.stderr)
        return 1
    print("OK files_conform_expected extracted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
