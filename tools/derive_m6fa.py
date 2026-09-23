#!/usr/bin/env python3
"""m6f-aの14個の疎なD88差分から、事前登録D1〜D7を機械導出する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ARMS = tuple(f"F{i}" for i in range(7))
DERIVATIONS = tuple(f"D{i}" for i in range(1, 8))
NAME_A = b"QZ7A"
NAME_B = b"QZ7B"
NAME_LONG = b"QZ7ABC"


class InputError(ValueError):
    pass


Pos = tuple[int, int, int, int]
Sector = tuple[int, int, int]


@dataclass
class DiffView:
    new: dict[Pos, int]
    old: dict[Pos, int]
    old_uniform: dict[Sector, int]
    changed_counts: dict[Sector, int]
    sector_sizes: dict[Sector, int]


def parse_diff(doc: object) -> DiffView:
    if not isinstance(doc, dict) or doc.get("schema") != 1 \
            or not isinstance(doc.get("changes"), list):
        raise InputError("差分JSONの形式")
    new: dict[Pos, int] = {}
    old: dict[Pos, int] = {}
    old_uniform: dict[Sector, int] = {}
    counts: dict[Sector, int] = {}
    sizes: dict[Sector, int] = {}
    for sector in doc["changes"]:
        if not isinstance(sector, dict):
            raise InputError("セクタ差分の形式")
        try:
            key = (int(sector["c"]), int(sector["h"]), int(sector["r"]))
            # 本測定のD88Readerは256バイトセクタだけを対象とする。生差分には
            # 事前登録§1-3で許可されていない不変メタデータを足さない。
            size = 256
            ranges = sector["ranges"]
        except (KeyError, TypeError, ValueError):
            raise InputError("セクタ差分の項目") from None
        if key in sizes or size <= 0 or not isinstance(ranges, list):
            raise InputError("セクタ差分の重複または長さ")
        sizes[key] = size
        if "old_uniform" in sector:
            try:
                raw_old = bytes.fromhex(sector["old_uniform"])
            except (TypeError, ValueError):
                raise InputError("セクタ一様旧値の形式") from None
            if len(raw_old) != 1:
                raise InputError("セクタ一様旧値は1バイト")
            old_uniform[key] = raw_old[0]
        count = 0
        for span in ranges:
            try:
                start, length = int(span["offset"]), int(span["length"])
                new_bytes = bytes.fromhex(span["new"])
                old_field = span["old"]
            except (KeyError, TypeError, ValueError):
                raise InputError("変更区間の形式") from None
            if length <= 0 or start < 0 or start + length > size or len(new_bytes) != length:
                raise InputError("変更区間の範囲")
            if old_field != "withheld":
                raise InputError("区間の旧値は伏せる")
            for index, value in enumerate(new_bytes, start):
                pos = (*key, index)
                if pos in new:
                    raise InputError("変更位置の重複")
                new[pos] = value
                if key in old_uniform:
                    old[pos] = old_uniform[key]
                count += 1
        counts[key] = count
        if key in old_uniform and (count < 8 or len({old[pos] for pos in old if pos[:3] == key}) != 1):
            raise InputError("セクタ一様旧値の開示条件")
    if doc.get("changed_sectors") != len(counts) or doc.get("changed_bytes") != len(new):
        raise InputError("差分JSONの集計値")
    return DiffView(new, old, old_uniform, counts, sizes)


def _sector_values(view: DiffView, sector: Sector) -> dict[int, int]:
    return {pos[3]: value for pos, value in view.new.items() if pos[:3] == sector}


def _sector_dict(sector: Sector) -> dict[str, int]:
    return {"c": sector[0], "h": sector[1], "r": sector[2]}


def _pos_dict(pos: Pos) -> dict[str, int]:
    return {**_sector_dict(pos[:3]), "offset": pos[3]}


def _advance(pos: Pos, amount: int, sizes: dict[Sector, int]) -> Pos | None:
    c, h, r, offset = pos
    for _ in range(amount):
        size = sizes.get((c, h, r), 256)
        offset += 1
        if offset >= size:
            r += 1
            offset = 0
    return c, h, r, offset


def _distance(a: Pos, b: Pos, sizes: dict[Sector, int]) -> int | None:
    if a[:2] != b[:2] or (b[2], b[3]) <= (a[2], a[3]):
        return None
    if a[2] == b[2]:
        return b[3] - a[3]
    total = sizes.get(a[:3], 256) - a[3]
    for r in range(a[2] + 1, b[2]):
        total += sizes.get((a[0], a[1], r), 256)
    return total + b[3]


def _find(view: DiffView, needle: bytes, sectors: set[Sector] | None = None) -> list[Pos]:
    hits: list[Pos] = []
    for start, value in sorted(view.new.items()):
        if value != needle[0] or (sectors is not None and start[:3] not in sectors):
            continue
        positions = [_advance(start, i, view.sector_sizes) for i in range(len(needle))]
        if all(pos is not None and view.new.get(pos) == want
               for pos, want in zip(positions, needle)):
            hits.append(start)
    return hits


def _unique(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for value in values:
        key = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if key not in seen:
            seen.add(key); out.append(value)
    return out


def _result(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = _unique(candidates)
    count = len(candidates)
    out: dict[str, Any] = {"status": "not_found" if count == 0 else
                           "derived" if count == 1 else "ambiguous",
                           "candidate_count": count}
    if count == 1:
        out["value"] = candidates[0]
    return out


def derive_repetition(views: dict[str, DiffView]) -> dict[str, dict[str, Any]]:
    if set(views) != set(ARMS):
        raise InputError("腕の不足または余分")
    f1, f2, f3, f4, f5, f6 = (views[f"F{i}"] for i in range(1, 7))

    # D1: 3腕共通で、F1/F2の疎な新値列の相違がちょうど1位置。
    common = set(f1.changed_counts) & set(f2.changed_counts) & set(f3.changed_counts)
    d1_sectors = []
    for sector in sorted(common):
        a, b = _sector_values(f1, sector), _sector_values(f2, sector)
        if sum(a.get(k) != b.get(k) for k in set(a) | set(b)) == 1:
            d1_sectors.append(sector)
    d1 = _result([{"sector": _sector_dict(x)} for x in d1_sectors])

    # D2: F1中の全出現を候補とする。F1/F2唯一の違いが、少なくとも1候補の
    # 4文字目に一致することを追加条件にする（同名が2箇所なら曖昧のまま）。
    d2_positions: list[Pos] = []
    for sector in d1_sectors:
        a, b = _sector_values(f1, sector), _sector_values(f2, sector)
        differences = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
        names = _find(f1, NAME_A, {sector})
        if len(differences) == 1 and any(pos[3] + 3 == differences[0] for pos in names):
            d2_positions.extend(names)
    d2 = _result([{"sector": _sector_dict(x[:3]), "name_offset": x[3]}
                  for x in d2_positions])

    # D3: F4の第1名がD2位置にあり、同じトラック上の後続QZ7Bまでの通し距離。
    d3_values: list[dict[str, Any]] = []
    f4_a, f4_b = set(_find(f4, NAME_A)), _find(f4, NAME_B)
    for start in d2_positions:
        if start not in f4_a:
            continue
        for other in f4_b:
            distance = _distance(start, other, f4.sector_sizes)
            if distance is not None:
                d3_values.append({"entry_length": distance})
    d3 = _result(d3_values)
    entry_lengths = [int(x["entry_length"]) for x in _unique(d3_values)]

    # D4: F3に現れる6文字名の末尾まで、F1の4文字名直後が一様なら候補。
    d4_values: list[dict[str, Any]] = []
    long_names = _find(f3, NAME_LONG, set(d1_sectors))
    for start in d2_positions:
        for long_start in long_names:
            endpoint = _advance(long_start, len(NAME_LONG) - 1, f3.sector_sizes)
            if endpoint is None:
                continue
            length = _distance(start, endpoint, f1.sector_sizes)
            if length is None or length < 5:
                continue
            positions = [_advance(start, i, f1.sector_sizes) for i in range(4, length + 1)]
            values = [f1.new.get(pos) for pos in positions if pos is not None]
            if len(values) == length - 3 and None not in values and len(set(values)) == 1:
                d4_values.append({"padding_value": f"{values[0]:02X}",
                                  "name_field_length": length + 1})
    d4 = _result(d4_values)

    # D5: F1とF5の最終値を、相手側区間の一様旧値からのみ補って比較する。
    d5_values: list[dict[str, Any]] = []
    for start in d2_positions:
        for entry_length in entry_lengths:
            for i in range(entry_length):
                pos = _advance(start, i, f1.sector_sizes)
                if pos is None:
                    continue
                value1 = f1.new.get(pos, f5.old.get(pos))
                value5 = f5.new.get(pos, f1.old.get(pos))
                if value1 is not None and value5 is not None and value1 != value5:
                    d5_values.append({"position": _pos_dict(pos),
                                      "value": f"{value5:02X}"})
    d5 = _result(d5_values)

    # D6: 候補エントリ長の全位置について、開示可能な旧値が一様な場合だけ採る。
    d6_values: list[dict[str, Any]] = []
    d6_withheld = False
    for start in d2_positions:
        for entry_length in entry_lengths:
            positions = [_advance(start, i, f1.sector_sizes) for i in range(entry_length)]
            values = [f1.old.get(pos) for pos in positions if pos is not None]
            if len(values) == entry_length and None not in values and len(set(values)) == 1:
                d6_values.append({"unused_entry_value": f"{values[0]:02X}"})
            elif len(positions) == entry_length \
                    and all(pos is not None and pos in f1.new for pos in positions):
                d6_withheld = True
    d6 = _result(d6_values)
    if d6["status"] == "not_found" and d6_withheld:
        d6["reason"] = "old_values_withheld"

    # D7（追補1）: F1/F6共通変更、全D1候補を除外、F6の変更数が多い。
    d7_sectors = [sector for sector in sorted(set(f1.changed_counts) & set(f6.changed_counts))
                  if sector not in set(d1_sectors)
                  and f6.changed_counts[sector] > f1.changed_counts[sector]]
    d7_withheld = any(sector not in f6.old_uniform for sector in d7_sectors)
    d7_values = [{"sector": _sector_dict(x),
                  "empty_value": f"{f6.old_uniform[x]:02X}"}
                 for x in d7_sectors if x in f6.old_uniform]
    d7 = _result([] if d7_withheld else d7_values)
    if d7["status"] == "not_found" and d7_withheld:
        d7["reason"] = "old_values_withheld"
    return {"D1": d1, "D2": d2, "D3": d3, "D4": d4,
            "D5": d5, "D6": d6, "D7": d7}


def load_all(raw_dir: Path) -> tuple[list[dict[str, object]], str]:
    digest = hashlib.sha256()
    runs: list[dict[str, object]] = []
    for repetition in (1, 2):
        views = {}
        for arm in ARMS:
            path = raw_dir / f"{arm}-r{repetition}.diff.json"
            raw = path.read_bytes()
            digest.update(f"{arm}:{repetition}\n".encode("ascii") + raw)
            views[arm] = parse_diff(json.loads(raw))
        runs.append({"repetition": repetition,
                     "derivations": derive_repetition(views)})
    return runs, digest.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        runs, digest = load_all(args.raw_dir)
        body = json.dumps({"schema": 1, "runs": runs, "input_sha256": digest},
                          ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        if args.output:
            args.output.write_text(body, encoding="utf-8")
        else:
            sys.stdout.write(body)
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
