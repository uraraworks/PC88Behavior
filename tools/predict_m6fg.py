#!/usr/bin/env python3
"""m6f-g の候補画面をメモリ内だけで組み立て、行署名表を作る。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


MARK_ARMS = ("G-P", "G-B")
SIZE_ARMS = ("G-Z1", "G-Z2")
ALL_ARMS = ("G-P", "G-B", "G-M", "G-Z1", "G-Z2")
SHA_RE = re.compile(r"[0-9a-f]{64}")


class PredictionError(ValueError):
    pass


@dataclass(frozen=True)
class SignedLine:
    physical_row: int
    char_count: int
    sha256: str


def mark_candidate_ids() -> tuple[str, ...]:
    marks = tuple(f"mark_{value:02X}" for value in range(0x20, 0x7F))
    return marks + tuple(value + "_nosize" for value in marks) + ("hidden",)


def _manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PredictionError("manifest読取") from exc
    if (not isinstance(value, dict) or value.get("format") != "m6fg-scenario-v1"
            or not isinstance(value.get("media"), dict)
            or not isinstance(value.get("arms"), list)):
        raise PredictionError("manifest形式")
    return value


def _entries(manifest: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    if arm not in ALL_ARMS:
        raise PredictionError("腕ID")
    media = manifest["media"].get(arm)
    if not isinstance(media, dict) or not isinstance(media.get("entries"), list):
        raise PredictionError("媒体定義")
    return media["entries"]


def _candidate(candidate: str) -> tuple[str | None, bool, bool]:
    if candidate == "hidden":
        return None, False, True
    match = re.fullmatch(r"mark_([0-9A-F]{2})(_nosize)?", candidate)
    if match is None or candidate not in mark_candidate_ids():
        raise PredictionError("候補ID")
    return chr(int(match.group(1), 16)), match.group(2) is None, False


def _entry_text(entry: dict[str, Any], candidate: str | None = None) -> str | None:
    name = entry.get("name")
    file_type = entry.get("type")
    units = entry.get("units")
    if (not isinstance(name, str) or not name.isascii() or not 1 <= len(name) <= 9
            or not isinstance(file_type, int) or isinstance(file_type, bool)
            or not isinstance(units, list) or not units):
        raise PredictionError("エントリ形式")
    if file_type == 0x80:
        mark, show_size, hidden = ".", True, False
    elif file_type == 0x00:
        mark, show_size, hidden = " ", True, False
    elif candidate is not None:
        mark, show_size, hidden = _candidate(candidate)
    else:
        raise PredictionError("種別候補不足")
    if hidden:
        return None
    padded = name.ljust(9)
    text = padded[:6] + mark + padded[6:]
    if show_size:
        text += " " + str(len(units))
    return text


def _layout(items: list[str]) -> list[str]:
    if any(len(item) > 16 for item in items):
        raise PredictionError("セル超過")
    return ["".join(item.ljust(16) for item in items[index:index + 5]).rstrip()
            for index in range(0, len(items), 5)]


def _hash_line(row: int, body: str) -> SignedLine:
    raw = f"{row}\t{body}\n".encode("utf-8")
    return SignedLine(row, len(body), hashlib.sha256(raw).hexdigest())


def _signed(items: list[str]) -> list[SignedLine]:
    return [_hash_line(row, body) for row, body in enumerate(_layout(items))]


def predict_mark(manifest: dict[str, Any], arm: str, candidate: str) -> list[SignedLine]:
    if arm not in MARK_ARMS:
        raise PredictionError("印腕")
    items = [_entry_text(entry, candidate) for entry in _entries(manifest, arm)]
    return _signed([item for item in items if item is not None])


def predict_size(manifest: dict[str, Any], arm: str) -> list[SignedLine]:
    if arm not in SIZE_ARMS:
        raise PredictionError("大きさ腕")
    items = [_entry_text(entry) for entry in _entries(manifest, arm)]
    return _signed([item for item in items if item is not None])


def predict_mixed(manifest: dict[str, Any], p_candidate: str,
                  b_candidate: str) -> list[SignedLine]:
    items: list[str] = []
    for entry in _entries(manifest, "G-M"):
        candidate = p_candidate if entry.get("type") == 0xA0 else (
            b_candidate if entry.get("type") == 0x01 else None)
        item = _entry_text(entry, candidate)
        if item is not None:
            items.append(item)
    return _signed(items)


def _whole(lines: Iterable[SignedLine]) -> str:
    digest = hashlib.sha256()
    for line in lines:
        digest.update(f"{line.physical_row}\t{line.char_count}\t{line.sha256}\n".encode("ascii"))
    return digest.hexdigest()


def render_candidates(manifest: dict[str, Any]) -> bytes:
    out = ["record\tcandidate_id\tarm\tphysical_row\tchar_count\tsha256"]
    for arm in MARK_ARMS:
        for candidate in mark_candidate_ids():
            lines = predict_mark(manifest, arm, candidate)
            for line in lines:
                out.append(f"row\t{candidate}\t{arm}\t{line.physical_row}\t{line.char_count}\t{line.sha256}")
            out.append(f"summary\t{candidate}\t{arm}\t-\t{len(lines)}\t{_whole(lines)}")
    for arm in SIZE_ARMS:
        lines = predict_size(manifest, arm)
        for line in lines:
            out.append(f"row\tsize_min_digits\t{arm}\t{line.physical_row}\t{line.char_count}\t{line.sha256}")
        out.append(f"summary\tsize_min_digits\t{arm}\t-\t{len(lines)}\t{_whole(lines)}")
    return ("\n".join(out) + "\n").encode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    try:
        payload = render_candidates(_manifest(args.manifest))
        digest = hashlib.sha256(payload).hexdigest()
        if (args.expected_sha256 is not None
                and (not SHA_RE.fullmatch(args.expected_sha256)
                     or args.expected_sha256 != digest)):
            raise PredictionError("凍結SHA")
        if args.output.exists():
            raise PredictionError("出力先")
        args.output.write_bytes(payload)
        print(f"sha256={digest}")
        return 0
    except (OSError, PredictionError):
        print("predict_m6fg_error=PredictionError", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
