#!/usr/bin/env python3
"""m6f-c の測定結果(result JSON)と保存済み媒体(raw-dir/ARM-rN.d88)から、
事前登録 docs/notes/m6f-c-blank-disk-acceptance-preregistration.md 第5節の
C0〜C11 を機械導出する。

本稿の媒体は自作の生成器で作った既知値の集合なので（同ノート §0.1）、
result JSON の markers/reads/writes に加え、raw-dir に保存された段階2
（A腕）の媒体そのものを読んでよい。読むのは自作生成器が書いた構造への
上書き結果だけで、公式ROM・公式ディスクの中身は一切含まない。

導出器自身は本体セクタの中身（記録の文字列や中間語）を標準出力へ出さない。
出すのは座標・位置・事前登録で導出と定めた値（k・S・o・e・u 等）だけ。

解釈を加えた点（事前登録の文言に明示が無かったため、このセッションで
固定した約束事。報告に転記する）:
  - 結果JSONの見出しキーは記号「*」を避け `f_star` / `v_star` とする。
  - 「エントリの10〜15バイト目」はエントリ先頭からの0始まりオフセット
    10〜15（名前欄0〜8・属性9の後ろ）。事前登録 §5.1 の明確化（測定前）。
  - 「トラック18」はシリンダ18の両ヘッド（H=0,1）。同じく §5.1。
  - C7 の「A3・A4の6腕」は A3, A4-1, A4-3, A4-6, A4-10, A4-17 の6腕。
  - C9 の探索範囲はトラック18の全16セクタ（割り当て表3セクタを含む。
    エントリのバイト列 `Q`+3桁+空白5 等が割り当て表の一様値と一致する
    確率は事実上無いため、除外の要否は測定結果側で確認する）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from d88_read_sector import D88Error, D88Reader  # noqa: E402

CYLINDERS = 40
HEADS = 2
SECTORS_PER_TRACK = 16
ALL_COORDS = tuple(
    (c, h, r)
    for c in range(CYLINDERS)
    for h in range(HEADS)
    for r in range(1, SECTORS_PER_TRACK + 1)
)
TRACK18_COORDS = tuple((18, h, r) for h in range(HEADS) for r in range(1, SECTORS_PER_TRACK + 1))
FAT_SECTORS: tuple[tuple[int, int, int], ...] = ((18, 1, 14), (18, 1, 15), (18, 1, 16))
FAT_PRIMARY = FAT_SECTORS[0]
TRACK18_NON_FAT_COORDS = tuple(c for c in TRACK18_COORDS if c not in FAT_SECTORS)
BODY_RE = re.compile(rb"[0-9]{5}v")
UNDELETED_ENTRY_RE = re.compile(rb"Q[0-9]{3} {5}")
DELETED_ENTRY_RE = re.compile(rb"\x00[0-9]{3} {5}")
ENTRY_FIELD_OFFSETS = (10, 11, 12, 13, 14, 15)  # 0始まり。名前欄0〜8・属性9の後ろ
A4_ARMS = ("A4-1", "A4-3", "A4-6", "A4-10", "A4-17")
C6_ARMS = ("A3",) + A4_ARMS
C7_ARMS = ("A3",) + A4_ARMS
STAGE2_ARMS = ("A0", "A1", "A1b", "A2", "A3") + A4_ARMS + ("A5", "A5b", "A6")
ENTRY_NAME = {"A1b": b"QZ7A", "A3": b"QZ7B", "A6": b"q7l", **{a: b"QZ7B" for a in A4_ARMS}}
for _arm in A4_ARMS:
    ENTRY_NAME[_arm] = b"QZ7B"
STATUSES = ("derived", "ambiguous", "not_found")


class InputError(ValueError):
    pass


def _result(candidates: list[Any]) -> dict[str, Any]:
    seen: set[str] = set()
    unique: list[Any] = []
    for value in candidates:
        key = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if key not in seen:
            seen.add(key)
            unique.append(value)
    count = len(unique)
    out: dict[str, Any] = {
        "status": "not_found" if count == 0 else "derived" if count == 1 else "ambiguous",
        "candidate_count": count,
    }
    if count == 1:
        out["value"] = unique[0]
    return out


def _pos(coord: tuple[int, int, int], offset: int) -> dict[str, int]:
    return {"c": coord[0], "h": coord[1], "r": coord[2], "offset": offset}


def linear_number(c: int, h: int, r: int) -> int:
    return (c * 2 + h) * SECTORS_PER_TRACK + (r - 1)


def coord_of_linear(number: int) -> tuple[int, int, int]:
    r = number % SECTORS_PER_TRACK + 1
    phys = number // SECTORS_PER_TRACK
    c, h = divmod(phys, HEADS)
    return (c, h, r)


# --- 媒体読み取り ----------------------------------------------------------

def load_disk(path: Path) -> D88Reader:
    try:
        return D88Reader(path.read_bytes())
    except (OSError, D88Error) as exc:
        raise InputError(f"媒体読み取り: {exc}") from None


def sector(reader: D88Reader, coord: tuple[int, int, int]) -> bytes:
    try:
        return reader.read_sector(*coord)
    except D88Error as exc:
        raise InputError(f"セクタ読み取り: {exc}") from None


def find_body_sectors(reader: D88Reader) -> list[tuple[tuple[int, int, int], int]]:
    """[0-9]{5}v を含む全セクタを、中の最初の完全な通し番号でソートして返す。"""
    hits: list[tuple[tuple[int, int, int], int]] = []
    for coord in ALL_COORDS:
        payload = sector(reader, coord)
        match = BODY_RE.search(payload)
        if match:
            number = int(match.group(0)[:5])
            hits.append((coord, number))
    hits.sort(key=lambda item: item[1])
    return hits


def find_name(reader: D88Reader, name: bytes, coords: tuple[tuple[int, int, int], ...]) -> list[dict[str, int]]:
    if not name:
        return []
    hits: list[dict[str, int]] = []
    for coord in coords:
        payload = sector(reader, coord)
        start = 0
        while True:
            idx = payload.find(name, start)
            if idx < 0:
                break
            hits.append(_pos(coord, idx))
            start = idx + 1
    return hits


def changed_positions(reader: D88Reader, coord: tuple[int, int, int], v_star: int) -> dict[int, int]:
    payload = sector(reader, coord)
    return {i: b for i, b in enumerate(payload) if b != v_star}


# --- C0/C1: 起動の関門と空きの印 -------------------------------------------

def _run_tags(run: dict[str, Any]) -> set[str]:
    return {m["tag"] for m in run.get("markers", [])}


def boot_filler(runs_by_key: dict[tuple[str, int], dict[str, Any]]) -> dict[str, Any]:
    ff = [runs_by_key.get(("GB-FF", 1)), runs_by_key.get(("GB-FF", 2))]
    zz = [runs_by_key.get(("GB-00", 1)), runs_by_key.get(("GB-00", 2))]
    if all(r is not None and "bt" in _run_tags(r) for r in ff):
        return {"status": "derived", "value": 0xFF}
    if all(r is not None and "bt" in _run_tags(r) for r in zz):
        return {"status": "derived", "value": 0x00}
    return {"status": "m6f_c_boot_blocked"}


def _sw_status(run: dict[str, Any] | None) -> str:
    if run is None:
        return "none"
    tags = _run_tags(run)
    for tag in ("ok", "ng", "er"):
        if tag in tags:
            return tag
    return "none"


def free_mark(result: dict[str, Any]) -> dict[str, Any]:
    """事前登録 C1。V\\*(空きの印)を決める。ドライバもこの関数を使う。"""
    runs_by_key = {(r["arm"], r["repetition"]): r for r in result.get("runs", [])}
    vfree: list[int] = []
    disagreement: list[int] = []
    for v in range(256):
        s1 = _sw_status(runs_by_key.get((f"SW-{v:02X}", 1)))
        s2 = _sw_status(runs_by_key.get((f"SW-{v:02X}", 2)))
        if s1 != s2:
            disagreement.append(v)
            continue
        if s1 == "ok":
            vfree.append(v)
    out: dict[str, Any] = {"run_disagreement": disagreement}
    if not vfree:
        out["status"] = "not_found"
    elif len(vfree) == 1:
        out["status"] = "derived"
        out["value"] = vfree[0]
    else:
        out["status"] = "ambiguous"
        out["value"] = sorted(vfree)
        out["candidate_count"] = len(vfree)
    return out


# --- C2: 受け入れ -----------------------------------------------------------

def _rb_zero(run: dict[str, Any] | None) -> bool:
    if run is None:
        return False
    for m in run.get("markers", []):
        if m["tag"] == "rb" and m.get("numbers") == [0]:
            return True
    return False


def acceptance(runs_by_key: dict[tuple[str, int], dict[str, Any]]) -> dict[str, Any]:
    def both(arm: str, pred) -> bool:
        r1, r2 = runs_by_key.get((arm, 1)), runs_by_key.get((arm, 2))
        return r1 is not None and r2 is not None and pred(r1) and pred(r2)

    a1_ok = both("A1", lambda r: "ok" in _run_tags(r))
    a1b_ok = both("A1b", lambda r: "ok" in _run_tags(r) and r.get("name_counts", {}).get("QZ7A", 0) >= 1)
    a2_ok = both("A2", lambda r: "ld" in _run_tags(r))
    a3_ok = both("A3", _rb_zero)
    detail = {"A1": a1_ok, "A1b": a1b_ok, "A2": a2_ok, "A3": a3_ok}
    status = "accepted" if all(detail.values()) else "not_accepted"
    return {"status": status, "detail": detail}


# --- C3: 割り当て表3セクタの複製 -------------------------------------------

def replicas(reader: D88Reader, v_star: int) -> dict[str, Any]:
    per_sector = {c: changed_positions(reader, c, v_star) for c in FAT_SECTORS}
    values = list(per_sector.values())
    identical = all(v == values[0] for v in values)
    if identical:
        return {"status": "replicas_identical",
                "positions": sorted(values[0].keys())}
    diffs = []
    for c in FAT_SECTORS:
        if c == FAT_PRIMARY:
            continue
        keys = set(per_sector[FAT_PRIMARY]) ^ set(per_sector[c])
        diffs.append({"sector": {"c": c[0], "h": c[1], "r": c[2]}, "differing_offsets": sorted(keys)})
    return {"status": "replicas_differ", "differences": diffs}


# --- C4: 割り当て単位の大きさと位置の対応 -----------------------------------

def unit_mapping(p_positions: set[int], body_linear: list[int]) -> dict[str, Any]:
    if not body_linear:
        return {"status": "not_found", "candidate_count": 0}
    max_l = max(body_linear)
    candidates: list[dict[str, int]] = []
    for s in range(1, 33):
        for o in range(0, max_l + 1):
            ks = [(_l - o) // s for _l in body_linear]
            if any(k < 0 or k > 255 for k in ks):
                continue
            k_set = set(ks)
            if k_set != p_positions:
                continue
            counts: dict[int, int] = {}
            for k in ks:
                counts[k] = counts.get(k, 0) + 1
            if any(v > s for v in counts.values()):
                continue
            candidates.append({"s": s, "o": o})
    return _result(candidates)


# --- C5: 鎖 ------------------------------------------------------------------

def chain(t_bytes: bytes, k_sequence: list[int]) -> dict[str, Any]:
    mismatches = []
    for i in range(len(k_sequence) - 1):
        expect = t_bytes[k_sequence[i]]
        actual = k_sequence[i + 1]
        if expect != actual:
            mismatches.append({"index": i, "k": k_sequence[i], "expected_next": actual, "table_value": expect})
    status = "link_is_next_index" if not mismatches else "link_other"
    terminal = t_bytes[k_sequence[-1]] if k_sequence else None
    return {"status": status, "mismatches": mismatches, "terminal_value": terminal,
            "k_sequence": k_sequence}


# --- C6: 終端の値の規則 ------------------------------------------------------

def terminal_rule(entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """entries[arm] = {"e": int, "u": int}"""
    es = [v["e"] for v in entries.values()]
    us = [v["u"] for v in entries.values()]
    if len(set(es)) == 1:
        return {"status": "end_constant", "value": es[0], "detail": entries}
    diffs = {e - u for e, u in zip(es, us)}
    if len(set(us)) >= 2 and len(diffs) == 1:
        return {"status": "end_plus_used_sectors", "value": next(iter(diffs)), "detail": entries}
    return {"status": "end_other", "detail": entries}


# --- C7: エントリの先頭単位の欄 ---------------------------------------------

def entry_head_field(reader: D88Reader, entry_start: dict[str, int], k1: int) -> list[int]:
    coord = (entry_start["c"], entry_start["h"], entry_start["r"])
    payload = sector(reader, coord)
    base = entry_start["offset"]
    matches = []
    for j in ENTRY_FIELD_OFFSETS:
        pos = base + j
        if pos < len(payload) and payload[pos] == k1:
            matches.append(j)
    return matches


# --- C9: ディレクトリの広がり ------------------------------------------------

def directory_entries(reader: D88Reader) -> dict[str, list[dict[str, Any]]]:
    undeleted, deleted = [], []
    for coord in TRACK18_COORDS:
        payload = sector(reader, coord)
        for m in UNDELETED_ENTRY_RE.finditer(payload):
            undeleted.append({**_pos(coord, m.start()), "number": int(m.group(0)[1:4])})
        for m in DELETED_ENTRY_RE.finditer(payload):
            deleted.append({**_pos(coord, m.start()), "number": int(m.group(0)[1:4])})
    undeleted.sort(key=lambda x: x["number"])
    deleted.sort(key=lambda x: x["number"])
    return {"undeleted": undeleted, "deleted": deleted}


# --- 導出の統合 --------------------------------------------------------------

def consensus(name: str, first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    key1 = json.dumps(first, sort_keys=True, separators=(",", ":"))
    key2 = json.dumps(second, sort_keys=True, separators=(",", ":"))
    if key1 == key2:
        return first
    return {"status": "ambiguous", "candidate_count": 2, "run1": first, "run2": second}


def derive_a3_like(reader: D88Reader, v_star: int, arm: str) -> dict[str, Any]:
    """A3/A4系1走ぶんの導出材料(C3〜C7,C11の腕別部分)をまとめて返す。"""
    body = find_body_sectors(reader)
    body_linear = [linear_number(*coord) for coord, _num in body]
    p_positions = set(changed_positions(reader, FAT_PRIMARY, v_star).keys())
    rep = replicas(reader, v_star)
    mapping = unit_mapping(p_positions, body_linear)
    k_sequence: list[int] = []
    chain_result: dict[str, Any] | None = None
    if mapping["status"] == "derived":
        s, o = mapping["value"]["s"], mapping["value"]["o"]
        k_sequence = [(number - o) // s for number in body_linear]
        chain_result = chain(sector(reader, FAT_PRIMARY), k_sequence)
    entry_hits = find_name(reader, ENTRY_NAME.get(arm, b""), TRACK18_NON_FAT_COORDS)
    entry_head_matches: list[int] = []
    if k_sequence and entry_hits:
        union: set[int] = set()
        for hit in entry_hits:
            union |= set(entry_head_field(reader, hit, k_sequence[0]))
        entry_head_matches = sorted(union)
    body_in_track18 = any(coord[0] == 18 for coord, _num in body)  # §5.1: 両ヘッド
    return {
        "body": [{"c": c[0], "h": c[1], "r": c[2], "number": n} for c, n in body],
        "body_linear": body_linear, "p_positions": sorted(p_positions),
        "replicas": rep, "unit_mapping": mapping, "chain": chain_result,
        "k_sequence": k_sequence, "entry_hits": entry_hits,
        "entry_head_matches": entry_head_matches,
        "body_in_track18": body_in_track18,
    }


def write_count_in_range(run: dict[str, Any] | None, lo: int, hi: int) -> int:
    if run is None:
        return 0
    count = 0
    for w in run.get("writes", []):
        n = linear_number(w["c"], w["h"], w["r"])
        if lo <= n < hi:
            count += 1
    return count


def load_result(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        raise InputError("結果JSONの形式")
    return doc


def build(result: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
    runs_by_key = {(r["arm"], r["repetition"]): r for r in result.get("runs", [])}
    out: dict[str, Any] = {}

    out["C0"] = boot_filler(runs_by_key)
    if out["C0"]["status"] != "derived":
        return {"schema": 1, "derivations": out, "overall": "m6f_c_boot_blocked"}
    f_star = out["C0"]["value"]

    out["C1"] = free_mark(result)
    if out["C1"]["status"] == "not_found":
        return {"schema": 1, "derivations": out, "overall": "m6f_c_no_free_mark",
                "f_star": f_star}
    v_star = out["C1"]["value"] if out["C1"]["status"] == "derived" else min(out["C1"]["value"])

    out["C2"] = acceptance(runs_by_key)

    # 段階2の全腕を両走とも読み、腕単位でconsensusを取る。
    per_arm_reps: dict[str, list[dict[str, Any]]] = {}
    for arm in STAGE2_ARMS:
        reps = []
        for rep in (1, 2):
            path = raw_dir / f"{arm}-r{rep}.d88"
            if not path.exists():
                reps.append(None)
                continue
            reader = load_disk(path)
            reps.append(derive_a3_like(reader, v_star, arm))
        per_arm_reps[arm] = reps

    a3_reps = per_arm_reps["A3"]
    if all(r is not None for r in a3_reps):
        rep_keys = [json.dumps({k: v for k, v in r.items() if k != "entry_hits"},
                                sort_keys=True, separators=(",", ":")) for r in a3_reps]
        a3 = a3_reps[0] if rep_keys[0] == rep_keys[1] else None
    else:
        a3 = None

    if a3 is None:
        out["C3"] = {"status": "ambiguous", "candidate_count": 2, "reason": "run_disagreement_or_missing"}
        out["C4"] = {"status": "not_found", "candidate_count": 0}
        out["C5"] = None
        out["C6"] = {"status": "not_found", "candidate_count": 0}
        out["C7"] = {"status": "not_found", "candidate_count": 0}
        out["C8"] = {"status": "not_found", "candidate_count": 0}
        out["C9"] = {"a5": None, "a5b": None}
        out["C10"] = {"status": "not_found", "candidate_count": 0}
        out["C11"] = {"body_location": {}, "k1": None}
    else:
        out["C3"] = a3["replicas"]
        out["C4"] = a3["unit_mapping"]
        out["C5"] = a3["chain"]
        # C6: A3 + A4系。
        entries = {}
        for arm in C6_ARMS:
            reps = per_arm_reps[arm]
            if any(r is None or r["chain"] is None for r in reps):
                continue
            if reps[0]["chain"] != reps[1]["chain"]:
                continue
            e = reps[0]["chain"]["terminal_value"]
            k_last = reps[0]["chain"]["k_sequence"][-1]
            if a3["unit_mapping"]["status"] != "derived":
                continue
            s, o = a3["unit_mapping"]["value"]["s"], a3["unit_mapping"]["value"]["o"]
            lo, hi = k_last * s + o, k_last * s + o + s
            u1 = write_count_in_range(runs_by_key.get((arm, 1)), lo, hi)
            u2 = write_count_in_range(runs_by_key.get((arm, 2)), lo, hi)
            if u1 != u2:
                continue
            entries[arm] = {"e": e, "u": u1}
        out["C6"] = terminal_rule(entries) if len(entries) == len(C6_ARMS) else \
            {"status": "not_found", "candidate_count": 0, "detail": entries}

        # C7: A3 + A4系(C7_ARMS)で、両走一致した候補オフセット集合の共通部分。
        candidate_j: set[int] | None = None
        c7_detail: dict[str, Any] = {}
        c7_ok = True
        for arm in C7_ARMS:
            reps = per_arm_reps[arm]
            if any(r is None for r in reps):
                c7_ok = False
                break
            if reps[0]["entry_head_matches"] != reps[1]["entry_head_matches"]:
                c7_ok = False
                break
            matches = set(reps[0]["entry_head_matches"])
            c7_detail[arm] = sorted(matches)
            candidate_j = matches if candidate_j is None else (candidate_j & matches)
        if c7_ok and candidate_j:
            out["C7"] = _result([{"offset": j} for j in sorted(candidate_j)])
            out["C7"]["detail"] = c7_detail
        else:
            out["C7"] = {"status": "not_found", "candidate_count": 0, "detail": c7_detail}
        out["C11"] = {"body_location": {}, "k1": a3["k_sequence"][0] if a3["k_sequence"] else None}
        for arm in STAGE2_ARMS:
            reps = per_arm_reps[arm]
            values = {r["body_in_track18"] for r in reps if r is not None}
            if len(values) == 1:
                loc = "body_in_track18" if next(iter(values)) else "body_outside_track18"
            else:
                loc = None
            out["C11"]["body_location"][arm] = loc

        # C8: ディレクトリの始まり。A1b と A3 のエントリ位置を比べ、A6は別記録。
        def entry_position(arm: str) -> dict[str, int] | None:
            reps = per_arm_reps.get(arm)
            if not reps or any(r is None for r in reps):
                return None
            if reps[0]["entry_hits"] != reps[1]["entry_hits"] or len(reps[0]["entry_hits"]) != 1:
                return None
            return reps[0]["entry_hits"][0]

        pos_a1b, pos_a3, pos_a6 = entry_position("A1b"), entry_position("A3"), entry_position("A6")
        if pos_a1b is not None and pos_a3 is not None and pos_a1b == pos_a3:
            c8 = {"status": "derived", "value": pos_a1b}
        else:
            c8 = {"status": "not_found", "candidate_count": 0,
                  "a1b": pos_a1b, "a3": pos_a3}
        c8["a6"] = pos_a6
        c8["a6_matches_a1b_a3"] = (pos_a6 is not None and pos_a6 in (pos_a1b, pos_a3))
        out["C8"] = c8

        # C9: ディレクトリの広がり（A5・A5b）。
        allocated_union: set[int] = set()
        for arm in STAGE2_ARMS:
            reps = per_arm_reps[arm]
            if reps and all(r is not None for r in reps) and reps[0]["p_positions"] == reps[1]["p_positions"]:
                allocated_union |= set(reps[0]["p_positions"])

        def directory_extent_for(arm: str) -> dict[str, Any] | None:
            reps = per_arm_reps.get(arm)
            if not reps or any(r is None for r in reps):
                return None
            paths = [raw_dir / f"{arm}-r{rep}.d88" for rep in (1, 2)]
            entries = [directory_entries(load_disk(p)) for p in paths]
            if entries[0] != entries[1]:
                return None
            runs_er = [("er" in _run_tags(runs_by_key.get((arm, rep)))) for rep in (1, 2)]
            table_bytes = sector(load_disk(paths[0]), FAT_PRIMARY)
            remaining = {k for k in allocated_union if table_bytes[k] == v_star}
            if all(runs_er) and remaining:
                bound = "directory_bound"
            else:
                bound = "lower_bound_only"
            entry_sectors = sorted({(e["c"], e["h"], e["r"]) for e in entries[0]["undeleted"]})
            return {"entries": entries[0], "status": bound,
                    "entry_sectors": [{"c": c, "h": h, "r": r} for c, h, r in entry_sectors]}

        a5 = directory_extent_for("A5")
        a5b = directory_extent_for("A5b")
        c9: dict[str, Any] = {"a5": a5, "a5b": a5b}
        if a5b is not None:
            slots = {(e["c"], e["h"], e["r"]) for e in a5b["entries"]["undeleted"]}
            c9["a5b_deleted_slot_reused"] = len(slots) <= 1
        else:
            c9["a5b_deleted_slot_reused"] = None
        if a5 is not None:
            a5_alloc_changed = per_arm_reps["A5"][0]["p_positions"] if per_arm_reps.get("A5") else []
            c9["a5_allocation_changed_count"] = len(a5_alloc_changed)
        out["C9"] = c9

        # C10: FILESが読むセクタ（A1のiolog、初出順）。
        def files_reads(rep: int) -> list[dict[str, int]] | None:
            run = runs_by_key.get(("A1", rep))
            if run is None:
                return None
            seen: set[tuple[int, int, int]] = set()
            out_list: list[dict[str, int]] = []
            for r in run.get("reads", []):
                key = (r["c"], r["h"], r["r"])
                if key in seen:
                    continue
                seen.add(key)
                out_list.append({"c": r["c"], "h": r["h"], "r": r["r"]})
            return out_list

        r1, r2 = files_reads(1), files_reads(2)
        if r1 is not None and r1 == r2:
            out["C10"] = {"status": "derived", "value": r1}
        else:
            out["C10"] = {"status": "ambiguous" if r1 is not None else "not_found",
                          "candidate_count": 2 if r1 is not None else 0}

    out["overall"] = ("m6f_c_blank_disk_accepted"
                       if out["C1"]["status"] in ("derived", "ambiguous") and out["C2"]["status"] == "accepted"
                       else "m6f_c_blank_disk_not_accepted")
    return {"schema": 1, "derivations": out, "f_star": f_star, "v_star": v_star,
            "overall": out["overall"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", required=True, type=Path)
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        result = load_result(args.result)
        body = build(result, args.raw_dir)
        digest = hashlib.sha256(args.result.read_bytes()).hexdigest()
        body["input_sha256"] = digest
        text = json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
