#!/usr/bin/env python3
"""m6f-j の行署名・媒体差から、事前登録の全候補を判定する。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import m6fj_script as script

ERROR_TABLE = Path(__file__).resolve().parent.parent / "src/l4_basic/errors.asm"


def errors() -> dict[int, str]:
    raw = ERROR_TABLE.read_text(encoding="utf-8")
    return {int(number): message for number, message in
            re.findall(r'^ERR_MSG_(\d+):\s*\n\s*DB "([^"]+)",0', raw, re.M)}


def signed(row: int, content: str) -> tuple[int, int, str]:
    return row, len(content), hashlib.sha256(f"{row}\t{content}\n".encode("utf-8")).hexdigest()


def predictions() -> dict[str, tuple[tuple[int, int, str], ...]]:
    result = {"ok_line": (signed(0, "Ok"),), "no_line": ()}
    for number, message in errors().items():
        result[f"error_{number}"] = (signed(0, message),)
    return result


def candidate_bytes() -> bytes:
    rows = ["candidate_id\tphysical_row\tchar_count\tsha256"]
    for name, signatures in predictions().items():
        for row, count, digest in signatures:
            rows.append(f"{name}\t{row}\t{count}\t{digest}")
        if not signatures:
            rows.append(f"{name}\t-\t0\t{hashlib.sha256(b'').hexdigest()}")
    return ("\n".join(rows) + "\n").encode("ascii")


def match_screen(lines: list[dict]) -> list[str]:
    observed = tuple((x["physical_row"], x["char_count"], x["sha256"]) for x in lines)
    return [name for name, signature in predictions().items() if observed == signature]


def allocated(before: dict, after: dict) -> list[int]:
    a, b = before["fat_0_159"], after["fat_0_159"]
    return [unit for unit in range(160) if a[unit] == 0xff and b[unit] != 0xff]


def classify(arm: str, before: dict, after: dict, lines: list[dict], preinsert_lines=None) -> dict:
    matches = match_screen(lines)
    old = before["entries"]
    new = after["entries"]
    media_unchanged = before["entries"] == after["entries"] and before["fat_0_159"] == after["fat_0_159"]
    units = allocated(before, after)
    candidates = []
    if arm == "J-1":
        candidates = [x for x in matches if x in ("ok_line", "no_line")]
        if not candidates:
            candidates = ["other"]
    elif arm == "J-2":
        target = script.NAMES[arm]
        new_hits = [x for x in new if x["name"] == target]
        old_hit = next((x for x in old if x["name"] == target), None)
        if media_unchanged:
            candidates = [x for x in matches if x.startswith("error_")]
        elif old_hit and len(new_hits) == 1:
            slot = new_hits[0]["position"]
            if slot == old_hit["position"]:
                candidates = ["overwrite_same_slot_frees_old" if after["fat_0_159"][10] == 0xff
                              else "overwrite_same_slot_keeps_old"]
            else:
                candidates = ["overwrite_new_slot"]
        if not candidates:
            candidates = ["other"]
    elif arm == "J-3":
        # 割り当て順は新エントリの鎖をたどり、集合とともに記録する。
        entry = next((x for x in new if x["name"] == script.NAMES[arm]), None)
        sequence = []
        if entry:
            unit = entry["bytes9_15"][1]
            seen = set()
            while unit < 160 and unit not in seen:
                seen.add(unit)
                sequence.append(unit)
                value = after["fat_0_159"][unit]
                if 0xc0 <= value <= 0xc8:
                    break
                unit = value
        first = next(x for x in [72, 73] + [y for y in range(160) if y not in (72, 73, 74, 75)]
                     if before["fat_0_159"][x] == 0xff)
        lowest = next(x for x in range(160) if before["fat_0_159"][x] == 0xff)
        candidates = (["first_free_in_2_5_order"] if sequence and sequence[0] == first else []) + (
            ["lowest_free_number"] if sequence and sequence[0] == lowest else [])
        if not candidates:
            candidates = ["other"]
        return {"candidates": candidates, "allocated_units": sequence,
                "newly_used_units": units, "media_unchanged": media_unchanged}
    elif arm in ("J-4", "J-5"):
        candidates = [x for x in matches if x.startswith("error_")] if media_unchanged else []
        if not candidates:
            candidates = ["other"]
    elif arm == "J-6":
        if preinsert_lines is None:
            raise ValueError("挿入前署名なし")
        pre = match_screen(preinsert_lines or [])
        pre_errors = [x for x in pre if x.startswith("error_")]
        new_entry = any(x["name"] == script.NAMES[arm] and x not in old for x in new)
        if pre_errors:
            candidates = pre_errors
        elif not new_entry:
            candidates = ["stuck"]
        elif not any(x.startswith("error_") for x in matches):
            candidates = ["waits_for_media"]
        else:
            candidates = ["other"]
    else:
        raise ValueError("腕ID")
    result = {"candidates": candidates, "media_unchanged": media_unchanged,
              "newly_used_units": units}
    if arm in ("J-1", "J-2"):
        result["body_matches_2_6"] = after.get("body_matches_2_6")
        result["body_read_max_position"] = after.get("body_read_max_position", -1)
        result["body_read_limit"] = after.get("body_read_limit", len(script.body(arm)))
    return result


def combine(arms: dict[str, list[dict]]) -> dict:
    judgments = {}
    bodies = {}
    for arm in script.ARMS:
        if arm not in arms:
            continue
        runs = arms[arm]
        common = set(runs[0]["candidates"]) & set(runs[1]["candidates"])
        same = runs[0] == runs[1]
        judgments[arm] = next(iter(common)) if same and len(common) == 1 else f"inconclusive_{arm}"
        if arm in ("J-1", "J-2"):
            bodies[arm] = ("body_matches_2_6" if same and runs[0].get("body_matches_2_6")
                           else f"inconclusive_{arm}" if not same else "body_other")
    return {"format": "m6fj-derived-v1", "judgments": judgments,
            "body_judgments": bodies,
            "overall": "classified" if all(not x.startswith("inconclusive") for x in judgments.values()) else "inconclusive"}
