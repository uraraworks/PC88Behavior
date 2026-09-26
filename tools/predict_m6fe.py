#!/usr/bin/env python3
"""m6f-e の54候補と E 腕 ERR 0..255 を、本文を残さず行署名化する。

入力は make_m6fe_disk.py が出した manifest JSON だけであり、同生成器を
import しない。画面本文は各行を組み立てた直後に SHA-256 へ縮約し、TSV・
標準出力・例外文へ出さない。

画面モデルの根拠（docs/spec の既存仕様だけ）:
  - CLS 後の表示領域先頭は row0=0 とする。l3-main.md 第16節 HOME/CLR の
    clear はファンクションキー行以外を消去し、カーソルを (0,0) へ置く。
  - 通常終了の既知の入力待ち行は、l4-basic.md 第1節の「出力の次の行」の
    Ok 行。本文は候補照合へ含めず、末尾スクロールの1行としてだけ数える。
  - 既定20行の最下行 row0=19 はファンクションキー表示専用で、スクロール
    範囲は19行。l3-main.md 第13節・第15節。
  - ERR の整数 PRINT は正数/0の前後に空白1つ。l4-basic.md 第2節。

ファンクションキー本文は l3-main.md 第13節で対象外なので予測しない。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


LAYOUTS = ("G5", "G4", "PACK")
NAMES = ("SPLIT63", "RAW9")
TYPES = ("80DOT_00BLANK", "80BLANK_00DOT", "BOTHBLANK")
SIZES = ("UNITS", "SECTORS", "NONE")
LAYOUT_ARMS = ("L0", "L1", "L4", "L5", "L6", "L11", "L96")
DISPLAY_ARMS = LAYOUT_ARMS + ("D-omit", "D-1", "D-2", "D-expr", "N-wait")
SCROLL_ROWS = 19
WAIT_ROWS = 1
SHA_RE = re.compile(r"[0-9a-f]{64}")


class PredictionError(ValueError):
    """入力形式エラー。入力値や画面本文は例外文へ含めない。"""


@dataclass(frozen=True)
class SignedLine:
    physical_row: int
    char_count: int
    sha256: str


def candidate_ids() -> tuple[str, ...]:
    return tuple(
        f"files_layout_rule_{layout}_{name}_{kind}_{size}"
        for layout in LAYOUTS for name in NAMES for kind in TYPES for size in SIZES
    )


def _candidate_parts(candidate_id: str) -> tuple[str, str, str, str]:
    prefix = "files_layout_rule_"
    if not candidate_id.startswith(prefix):
        raise PredictionError("候補ID形式")
    body = candidate_id[len(prefix):]
    for layout in LAYOUTS:
        for name in NAMES:
            for kind in TYPES:
                for size in SIZES:
                    if body == f"{layout}_{name}_{kind}_{size}":
                        return layout, name, kind, size
    raise PredictionError("候補ID未登録")


def _manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PredictionError("manifest読取失敗") from exc
    if not isinstance(value, dict) or value.get("format") != "m6fe-scenario-v1":
        raise PredictionError("manifest形式")
    if not isinstance(value.get("media"), dict) or not isinstance(value.get("arms"), list):
        raise PredictionError("manifest項目")
    return value


def _arm_media(manifest: dict[str, Any], arm_id: str) -> dict[str, Any]:
    arms = [arm for arm in manifest["arms"]
            if isinstance(arm, dict) and arm.get("id") == arm_id]
    if len(arms) != 1:
        raise PredictionError("腕IDが一意でない")
    arm = arms[0]
    media_id = arm.get("drive1") if arm_id in ("D-omit", "D-1") else arm.get("drive2")
    if arm_id == "N-wait":
        media_id = "L1"
    if not isinstance(media_id, str) or media_id not in manifest["media"]:
        raise PredictionError("腕の媒体参照")
    media = manifest["media"][media_id]
    if not isinstance(media, dict) or not isinstance(media.get("entries"), list):
        raise PredictionError("媒体定義")
    return media


def _uint(value: Any, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise PredictionError("整数範囲")
    return value


def _entry_text(entry: dict[str, Any], name_rule: str, type_rule: str,
                size_rule: str) -> str:
    name = entry.get("name")
    if not isinstance(name, str) or not name.isascii() or not 1 <= len(name) <= 9:
        raise PredictionError("名前形式")
    padded = name.ljust(9)
    file_type = _uint(entry.get("type"), 255)
    if file_type not in (0x00, 0x80):
        raise PredictionError("種別範囲")
    marks = {
        "80DOT_00BLANK": {0x80: ".", 0x00: " "},
        "80BLANK_00DOT": {0x80: " ", 0x00: "."},
        "BOTHBLANK": {0x80: " ", 0x00: " "},
    }
    mark = marks[type_rule][file_type]
    if name_rule == "SPLIT63":
        text = padded[:6] + mark + padded[6:]
    else:
        text = padded + mark
    if size_rule != "NONE":
        units = entry.get("units")
        terminal = _uint(entry.get("terminal"), 255)
        if not isinstance(units, list) or not units or terminal < 0xC1 or terminal > 0xC8:
            raise PredictionError("鎖形式")
        amount = len(units) if size_rule == "UNITS" else ((len(units) - 1) * 8 + terminal - 0xC0)
        text += " " + str(amount)
    return text


def _layout_lines(items: list[str], layout: str) -> list[str]:
    if layout in ("G5", "G4"):
        width, count = (16, 5) if layout == "G5" else (20, 4)
        if any(len(item) > width for item in items):
            raise PredictionError("固定セル超過")
        return ["".join(item.ljust(width) for item in items[i:i + count]).rstrip()
                for i in range(0, len(items), count)]
    lines: list[str] = []
    current = ""
    for item in items:
        proposed = item if not current else current + " " + item
        if len(proposed) <= 80:
            current = proposed
        else:
            if current:
                lines.append(current)
            current = item
    if current:
        lines.append(current)
    return lines


def _hash_line(row: int, body: str) -> SignedLine:
    encoded = f"{row}\t{body}\n".encode("utf-8")
    return SignedLine(row, len(body), hashlib.sha256(encoded).hexdigest())


def _visible_entry_lines(lines: list[str]) -> list[SignedLine]:
    # 入力待ち行を末尾に1行置いた時点の19行スクロール領域をモデル化する。
    visible = (lines + [""])[-SCROLL_ROWS:]
    entry_count = len(visible) - WAIT_ROWS
    return [_hash_line(row, visible[row]) for row in range(entry_count)]


def predict_candidate(manifest: dict[str, Any], arm_id: str,
                      candidate_id: str) -> list[SignedLine]:
    layout, name_rule, type_rule, size_rule = _candidate_parts(candidate_id)
    media = _arm_media(manifest, arm_id)
    items = []
    for entry in media["entries"]:
        if not isinstance(entry, dict):
            raise PredictionError("エントリ形式")
        items.append(_entry_text(entry, name_rule, type_rule, size_rule))
    return _visible_entry_lines(_layout_lines(items, layout))


def predict_error(error_number: int) -> list[SignedLine]:
    number = _uint(error_number, 255)
    # CLS後 row0=0、PRINT整数は正数/0の前後に空白1つ（l4-basic.md §2）。
    # ただし screen_signature.h の正規化は行末空白を落とすため、後置空白は
    # メモリ内の画面を署名化する時点で消える。
    return [_hash_line(0, " " + str(number))]


def _whole_digest(lines: Iterable[SignedLine]) -> str:
    h = hashlib.sha256()
    for line in lines:
        h.update(f"{line.physical_row}\t{line.char_count}\t{line.sha256}\n".encode("ascii"))
    return h.hexdigest()


def render_candidates(manifest: dict[str, Any], arms: Iterable[str]) -> bytes:
    out = ["record\tcandidate_id\tarm\tphysical_row\tchar_count\tsha256"]
    for candidate_id in candidate_ids():
        for arm in arms:
            lines = predict_candidate(manifest, arm, candidate_id)
            for line in lines:
                out.append(f"row\t{candidate_id}\t{arm}\t{line.physical_row}\t{line.char_count}\t{line.sha256}")
            out.append(f"summary\t{candidate_id}\t{arm}\t-\t{len(lines)}\t{_whole_digest(lines)}")
    return ("\n".join(out) + "\n").encode("ascii")


def render_errors(arm: str) -> bytes:
    out = ["record\tprediction_id\tarm\tphysical_row\tchar_count\tsha256"]
    for number in range(256):
        prediction_id = f"files_error_err_{number}"
        lines = predict_error(number)
        for line in lines:
            out.append(f"row\t{prediction_id}\t{arm}\t{line.physical_row}\t{line.char_count}\t{line.sha256}")
        out.append(f"summary\t{prediction_id}\t{arm}\t-\t1\t{_whole_digest(lines)}")
    return ("\n".join(out) + "\n").encode("ascii")


def _write_new(path: Path, payload: bytes) -> None:
    if path.exists():
        raise PredictionError("出力先が存在する")
    path.write_bytes(payload)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--arms", default=",".join(LAYOUT_ARMS))
    ap.add_argument("--errors-for-arm")
    ap.add_argument("--expected-sha256")
    args = ap.parse_args()
    try:
        manifest = _manifest(args.manifest)
        if args.errors_for_arm is not None:
            if not re.fullmatch(r"E-(0|3|str)", args.errors_for_arm):
                raise PredictionError("E腕形式")
            payload = render_errors(args.errors_for_arm)
        else:
            arms = tuple(args.arms.split(","))
            if not arms or len(set(arms)) != len(arms) or any(arm not in DISPLAY_ARMS for arm in arms):
                raise PredictionError("腕一覧")
            payload = render_candidates(manifest, arms)
        digest = hashlib.sha256(payload).hexdigest()
        if args.expected_sha256 is not None:
            if not SHA_RE.fullmatch(args.expected_sha256) or args.expected_sha256 != digest:
                raise PredictionError("凍結SHA不一致")
        _write_new(args.output, payload)
        print(f"sha256={digest}")
        return 0
    except (PredictionError, OSError):
        print("predict_m6fe_error=PredictionError", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
