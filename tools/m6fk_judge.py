#!/usr/bin/env python3
"""m6f-k の行署名・媒体差から、事前登録の全候補を判定する。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import m6fk_script as script

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


def candidate_ids() -> dict[str, list[str]]:
    from itertools import product
    screens = ("ok_line", "no_line", "other")
    errors = [name for name in predictions() if name.startswith("error_")]
    result = {"K-1": ["/".join(x) for x in product(
        ("first_byte_00_rest_kept", "all_ff", "other"), ("units_freed", "units_kept", "other"), screens)],
        "N-1": ["/".join(x) for x in product(
        ("same_slot_name_only", "same_slot_other_fields_changed", "new_slot", "other"), screens)],
        "N-5": ["renamed_on_drive2"] + errors + ["other"]}
    for arm in ("K-2", "K-3", "N-2", "N-3", "N-4"):
        result[arm] = errors + ["no_error_media_unchanged", "other"]
    for arm in ("K-4", "N-6"):
        result[arm] = ["case_insensitive", "error_53_unchanged", "other"]
    return result


def candidate_bytes() -> bytes:
    return script.canonical({"candidates": candidate_ids(), "screens": predictions()})


def match_screen(lines: list[dict]) -> list[str]:
    observed = tuple((x["physical_row"], x["char_count"], x["sha256"]) for x in lines)
    return [name for name, signature in predictions().items() if observed == signature]


def classify(arm: str, before: dict, after: dict, lines: list[dict], changes: dict) -> dict:
    import m6fk_read as reader
    matches = match_screen(lines)
    screen = next((x for x in matches if x in ("ok_line", "no_line")), "other")
    old = [x["fields"] for x in before["entries"]]
    new = [x["fields"] for x in after["entries"]]
    unchanged = changes["media_unchanged"]
    fat_same = before["fat_0_159"] == after["fat_0_159"]
    errors_matched = [x for x in matches if x.startswith("error_")]
    external_same = not (changes["structure_changed"] or
                        any(x["changed"] for x in changes["body_sectors"]+changes["marker_sectors"]))
    slots_same = not any(x["changed"] for x in changes["unplaced_slots"])
    def deleted(slot):
        return new[slot] == [0]+old[slot][1:]
    def renamed(slot):
        return new[slot] == list(b"qsd".ljust(9, b" "))+old[slot][9:]
    def others_same(slot):
        return all(old[i] == new[i] for i in range(3) if i != slot)
    if arm == "K-1":
        entry = ("first_byte_00_rest_kept" if deleted(1) else
                 "all_ff" if new[1] == [255]*16 else "other")
        freed = before["fat_0_159"][:]
        for unit in reader.units(before, 1):
            freed[unit] = 255
        unit_kind = ("units_freed" if after["fat_0_159"] == freed else
                     "units_kept" if fat_same else "other")
        if not (external_same and slots_same and others_same(1)):
            entry = "other"
        candidates = ["/".join((entry, unit_kind, screen))]
    elif arm in ("K-2", "K-3", "N-2", "N-3", "N-4"):
        candidates = errors_matched if unchanged and errors_matched else (
            ["no_error_media_unchanged"] if unchanged and screen != "other" else ["other"])
    elif arm in ("K-4", "N-6"):
        changed = (new[2][0] in (0, 255) and new[2] != old[2]) if arm == "K-4" else (new[2][:9] == list(b"qsd".ljust(9, b" ")))
        candidates = (["case_insensitive"] if changed and others_same(2) and external_same and slots_same else
                      ["error_53_unchanged"] if unchanged and "error_53" in matches else ["other"])
    elif arm in ("N-1", "N-5"):
        kind = "other"
        if external_same and others_same(0):
            if slots_same and fat_same and renamed(0):
                kind = "same_slot_name_only"
            elif slots_same and new[0][:9] == list(b"qsd".ljust(9, b" ")) and new[0][9:] != old[0][9:]:
                kind = "same_slot_other_fields_changed"
        if external_same and new[0][0] == 0 and (bool(changes["_renamed_slots"]) or
                any(record[:9] == list(b"qsd".ljust(9, b" ")) for record in new[1:])):
            # 新名の内部照合と旧枠の削除。未配置枠の値は出力しない。
            kind = "new_slot"
        if arm == "N-1":
            candidates = ["/".join((kind, screen))]
        else:
            candidates = (["renamed_on_drive2"] if kind == "same_slot_name_only" else
                          errors_matched if unchanged and errors_matched else ["other"])
    else:
        raise ValueError("腕ID")
    return dict(candidates=candidates, media_unchanged=unchanged)


def combine(arms: dict[str, list[dict]]) -> dict:
    judgments = {}
    for arm, runs in arms.items():
        if len(runs) != 2:
            judgments[arm] = f"inconclusive_{arm}"
            continue
        common = set(runs[0]["candidates"]) & set(runs[1]["candidates"])
        judgments[arm] = next(iter(common)) if runs[0] == runs[1] and len(common) == 1 else f"inconclusive_{arm}"
    return {"format": "m6fk-derived-v1", "judgments": judgments,
            "overall": "classified" if judgments and all(not x.startswith("inconclusive") for x in judgments.values()) else "inconclusive"}
