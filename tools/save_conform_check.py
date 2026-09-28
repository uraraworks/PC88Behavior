#!/usr/bin/env python3
"""SAVE ,A の固定観測、D88、行署名を本文なしで照合する。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import compare_screen_signatures as css
import m6fj_read as reader
import m6fj_script as script
from make_m6fj_disk import build

ARMS = script.ARMS
HEX = re.compile(r"[0-9a-f]{64}\Z")


class CheckError(ValueError):
    pass


def fail() -> None:
    raise CheckError("形式")


def fields(observation: dict, arm: str) -> dict[str, str]:
    if observation.get("g8_max_position") != 159:
        fail()
    entries = observation.get("entries")
    if not isinstance(entries, list):
        fail()
    normalized = []
    for entry in entries:
        if set(entry) != {"name", "position", "bytes9_15"}:
            fail()
        name, position, tail = entry["name"], entry["position"], entry["bytes9_15"]
        if (not isinstance(name, str) or re.fullmatch(r"[a-z]{1,9}", name) is None
                or type(position) is not int or not 0 <= position < 192
                or not isinstance(tail, list) or len(tail) != 7
                or any(type(x) is not int or not 0 <= x <= 255 for x in tail)):
            fail()
        normalized.append(f"{name}:{position}:{bytes(tail).hex()}")
    lines = observation.get("screen_lines")
    if not isinstance(lines, list):
        fail()
    signature = []
    for line in lines:
        if set(line) != {"physical_row", "char_count", "sha256"}:
            fail()
        row, count, digest = line["physical_row"], line["char_count"], line["sha256"]
        if (type(row) is not int or not 0 <= row <= 18 or type(count) is not int
                or not 0 <= count <= 80 or not isinstance(digest, str) or not HEX.fullmatch(digest)):
            fail()
        signature.append(f"{row}:{count}:{digest}")
    if signature != sorted(signature, key=lambda s: int(s.split(":")[0])):
        fail()
    result = {"entries": ",".join(normalized), "screen": ",".join(signature)}
    if arm in ("J-1", "J-2"):
        if type(observation.get("body_matches_2_6")) is not bool:
            fail()
        result["body_matches_2_6"] = str(observation["body_matches_2_6"]).lower()
    if arm == "J-6":
        pre = observation.get("preinsert_screen_lines")
        if pre != []:
            fail()
        result["preinsert_empty"] = "true"
    return result


def expected_fat(arm: str) -> bytes:
    # 観測JSONはFAT列を出さない。自作B0/B1/B2/BP/BFと2走一致した
    # 割当単位・上書き判定から、仕様にある0〜159だけを固定する。
    before = bytearray(reader.inspect(build(script.MEDIA[arm]), arm)["fat_0_159"])
    if arm in ("J-1", "J-2", "J-3", "J-6"):
        before[72] = 0xc1
    if arm == "J-2":
        before[10] = 0xff
    return bytes(before)


def freeze(base: Path, add: Path) -> str:
    roots = [json.loads(p.read_text(encoding="ascii")) for p in (base, add)]
    rows = ["# save-conform-expected-v1", "# arm\tfield\tvalue"]
    for arm in ARMS:
        root = roots[0 if arm in ARMS[:3] else 1]
        runs = root.get("observations", {}).get(arm)
        if root.get("schema") != 1 or not isinstance(runs, list) or len(runs) != 2 or runs[0] != runs[1]:
            fail()
        values = fields(runs[0], arm)
        classifications = {"J-1": "no_line", "J-2": "overwrite_same_slot_frees_old",
                           "J-3": "first_free_in_2_5_order", "J-4": "error_61",
                           "J-5": "error_68", "J-6": "waits_for_media"}
        if runs[0].get("candidates") != [classifications[arm]]:
            fail()
        if arm in ("J-1", "J-2") and runs[0].get("body_matches_2_6") is not True:
            fail()
        if arm in ("J-4", "J-5") and runs[0].get("media_unchanged") is not True:
            fail()
        if arm in ("J-1", "J-2", "J-3") and not runs[0].get("newly_used_units") == [72]:
            fail()
        if arm in ("J-1", "J-2", "J-3", "J-6"):
            values["newly_used_units"] = "72"
        else:
            values["newly_used_units"] = ""
            values["media_unchanged"] = "true"
        values["fat_0_159"] = expected_fat(arm).hex()
        for key, value in values.items():
            rows.append(f"{arm}\t{key}\t{value}")
    return "\n".join(rows) + "\n"


def load(path: Path) -> dict[str, dict[str, str]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if lines[:2] != ["# save-conform-expected-v1", "# arm\tfield\tvalue"]:
        fail()
    result = {arm: {} for arm in ARMS}
    for line in lines[2:]:
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] not in result or parts[1] in result[parts[0]]:
            fail()
        arm, key, value = parts
        if key not in {"entries", "screen", "body_matches_2_6", "preinsert_empty",
                       "newly_used_units", "media_unchanged", "fat_0_159"}:
            fail()
        result[arm][key] = value
    for arm, values in result.items():
        keys = {"entries", "screen", "newly_used_units", "fat_0_159"}
        if arm in ("J-1", "J-2"):
            keys.add("body_matches_2_6")
        if arm in ("J-4", "J-5"):
            keys.add("media_unchanged")
        if arm == "J-6":
            keys.add("preinsert_empty")
        if set(values) != keys or not re.fullmatch(r"[0-9a-f]{320}", values["fat_0_159"]):
            fail()
    return result


def screen_rows(report: Path, snapshot: str) -> str:
    sig = css.read_report(report, snapshot)
    rows = [(row, item) for row, item in sorted(sig.lines.items()) if row != 19]
    if rows:
        rows.pop()  # 入力待ち行は公式ROMと自作ROMで異なる。
    return ",".join(f"{row}:{item.char_count}:{item.sha256}" for row, item in rows)


def compare(arm: str, expected: dict[str, str], image: Path, report: Path, before: Path) -> bool:
    after_bytes = image.read_bytes()
    before_bytes = before.read_bytes()
    actual = reader.inspect(after_bytes, arm)
    if arm in ("J-1", "J-2") and type(actual.get("body_matches_2_6")) is not bool:
        return False
    values = fields({**actual, "screen_lines": [] ,
                     "preinsert_screen_lines": []} if arm == "J-6" else
                    {**actual, "screen_lines": []}, arm)
    if arm in ("J-1", "J-2") and actual.get("body_read_max_position", 999) > len(script.body(arm)):
        return False
    before_value = reader.inspect(before_bytes, arm)
    values["fat_0_159"] = bytes(actual["fat_0_159"]).hex()
    values["newly_used_units"] = ",".join(str(i) for i in range(160)
        if before_value["fat_0_159"][i] == 255 and actual["fat_0_159"][i] != 255)
    if arm in ("J-4", "J-5"):
        values["media_unchanged"] = str(before_bytes == after_bytes).lower()
    values["screen"] = screen_rows(report, "final")
    if screen_rows(report, "late") != values["screen"]:
        return False
    if arm == "J-6":
        values["preinsert_empty"] = str(screen_rows(report, "preinsert") == "").lower()
    return values == expected


def verify_j1_image(expected: dict[str, str], image: Path) -> bool:
    actual = reader.inspect(image.read_bytes(), "J-1")
    if actual.get("body_matches_2_6") is not True:
        return False
    return (fields({**actual, "screen_lines": []}, "J-1")["entries"] == expected["entries"]
            and bytes(actual["fat_0_159"]).hex() == expected["fat_0_159"])


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("base", type=Path); p.add_argument("add", type=Path); p.add_argument("output", type=Path)
    p = sub.add_parser("validate"); p.add_argument("expected", type=Path)
    p = sub.add_parser("compare")
    p.add_argument("expected", type=Path); p.add_argument("arm", choices=ARMS)
    p.add_argument("image", type=Path); p.add_argument("report", type=Path); p.add_argument("before", type=Path)
    p = sub.add_parser("verify-j1-image")
    p.add_argument("expected", type=Path); p.add_argument("image", type=Path)
    a = ap.parse_args()
    try:
        if a.mode == "freeze":
            if a.output.exists():
                fail()
            a.output.write_text(freeze(a.base, a.add), encoding="ascii")
        elif a.mode == "validate":
            load(a.expected)
        elif a.mode == "verify-j1-image":
            ok = verify_j1_image(load(a.expected)["J-1"], a.image)
            print(f"J-1像\t{'OK' if ok else 'NG'}")
            return 0 if ok else 1
        else:
            ok = compare(a.arm, load(a.expected)[a.arm], a.image, a.report, a.before)
            print(f"{a.arm}\t{'OK' if ok else 'NG'}")
            return 0 if ok else 1
        print("OK")
        return 0
    except (OSError, ValueError, TypeError, KeyError, IndexError, UnicodeError, css.SignatureInputError):
        print("NG 形式", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
