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
ADD2_ARMS = ("L80", "L85", "L90", "L95", "L96'")
ADD3_PRINT_ARMS = ("P79", "P80", "P81")
ADD3_FILES_ARMS = ("L81", "L86", "L91", "L90'")
ADD3_PRINT_CANDIDATES = ("wrap_then_newline_blank", "wrap_absorbs_newline")
ADD3_SUFFIXES = ("T2", "T3", "W")
SCROLL_ROWS = 19
WAIT_ROWS = 1
ADD2_TRAILING_ROWS = (1, 2, 3)
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


def add2_candidate_ids() -> tuple[str, ...]:
    return tuple(f"{candidate}_T{trailing_rows}"
                 for candidate in candidate_ids()
                 for trailing_rows in ADD2_TRAILING_ROWS)


def add3_candidate_ids() -> tuple[str, ...]:
    return tuple(f"{candidate}_{suffix}"
                 for candidate in candidate_ids() for suffix in ADD3_SUFFIXES)


def _add2_candidate_parts(candidate_id: str) -> tuple[str, int]:
    match = re.fullmatch(r"(.+)_T([123])", candidate_id)
    if match is None or match.group(1) not in candidate_ids():
        raise PredictionError("追補2候補ID形式")
    return match.group(1), int(match.group(2))


def _add3_candidate_parts(candidate_id: str) -> tuple[str, str]:
    match = re.fullmatch(r"(.+)_(T2|T3|W)", candidate_id)
    if match is None or match.group(1) not in candidate_ids():
        raise PredictionError("追補3候補ID形式")
    return match.group(1), match.group(2)


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


def _manifest(path: Path, addendum2: bool = False,
              addendum3: bool = False) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PredictionError("manifest読取失敗") from exc
    if addendum2 and addendum3:
        raise PredictionError("追補モード重複")
    expected_format = ("m6fe-add3-scenario-v1" if addendum3 else
                       "m6fe-add2-scenario-v1" if addendum2 else
                       "m6fe-scenario-v1")
    if not isinstance(value, dict) or value.get("format") != expected_format:
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


def _visible_entry_lines(lines: list[str], trailing_rows: int = WAIT_ROWS) -> list[SignedLine]:
    # 出力後の行を末尾に置いた時点の19行スクロール領域をモデル化する。
    if trailing_rows not in ADD2_TRAILING_ROWS:
        raise PredictionError("末尾行数範囲")
    visible = (lines + [""] * trailing_rows)[-SCROLL_ROWS:]
    entry_count = max(0, len(visible) - trailing_rows)
    return [_hash_line(row, visible[row]) for row in range(entry_count)]


def predict_candidate(manifest: dict[str, Any], arm_id: str,
                      candidate_id: str, trailing_rows: int = WAIT_ROWS) -> list[SignedLine]:
    layout, name_rule, type_rule, size_rule = _candidate_parts(candidate_id)
    media = _arm_media(manifest, arm_id)
    items = []
    for entry in media["entries"]:
        if not isinstance(entry, dict):
            raise PredictionError("エントリ形式")
        items.append(_entry_text(entry, name_rule, type_rule, size_rule))
    return _visible_entry_lines(_layout_lines(items, layout), trailing_rows)


def predict_add2_candidate(manifest: dict[str, Any], arm_id: str,
                           candidate_id: str) -> list[SignedLine]:
    base_id, trailing_rows = _add2_candidate_parts(candidate_id)
    if arm_id not in ADD2_ARMS:
        raise PredictionError("追補2腕ID")
    return predict_candidate(manifest, arm_id, base_id, trailing_rows)


def predict_add3_candidate(manifest: dict[str, Any], arm_id: str,
                           candidate_id: str) -> list[SignedLine]:
    base_id, suffix = _add3_candidate_parts(candidate_id)
    if arm_id not in ADD3_FILES_ARMS:
        raise PredictionError("追補3 FILES腕ID")
    layout, name_rule, type_rule, size_rule = _candidate_parts(base_id)
    media = _arm_media(manifest, arm_id)
    items = [_entry_text(entry, name_rule, type_rule, size_rule)
             for entry in media["entries"]]
    lines = _layout_lines(items, layout)
    # _W は、最後の出力行そのものが80桁のときだけ、直後の改行による
    # 空行を含めてT3とする。固定セル候補も実際に80桁かを本文メモリ内で
    # 判定するので、表へ本文は出ない。
    # 署名器は行末空白を落とすので、固定セルの満杯行は署名上76桁等に
    # 見える。したがって_Wの「80桁ちょうど」は、正規化後の文字数でなく
    # 配置前のセル数（G5=5件、G4=4件）から判定する。
    full_row = ((layout == "G5" and bool(items) and len(items) % 5 == 0)
                or (layout == "G4" and bool(items) and len(items) % 4 == 0)
                or (layout == "PACK" and bool(lines) and len(lines[-1]) == 80))
    trailing_rows = (2 if suffix == "T2" else 3 if suffix == "T3"
                     else 3 if full_row else 2)
    return _visible_entry_lines(lines, trailing_rows)


def _print_lines(length: int, candidate_id: str) -> list[SignedLine]:
    if candidate_id not in ADD3_PRINT_CANDIDATES or length not in (79, 80, 81):
        raise PredictionError("追補3 PRINT予測")
    body = "A" * length
    rows: list[tuple[int, str]] = [(0, body[:80])]
    if length == 79:
        rows.append((1, "B"))
    elif length == 80:
        rows.append((2 if candidate_id == "wrap_then_newline_blank" else 1, "B"))
    else:
        rows.extend(((1, body[80:]), (2, "B")))
    return [_hash_line(row, text) for row, text in rows]


def predict_print_candidate(arm_id: str, candidate_id: str) -> list[SignedLine]:
    if arm_id not in ADD3_PRINT_ARMS:
        raise PredictionError("追補3 PRINT腕ID")
    return _print_lines(int(arm_id[1:]), candidate_id)


def predict_add4_print_candidate(arm_id: str, candidate_id: str) -> list[SignedLine]:
    """追補4用。腕と候補は追補3と同じで、表示文字だけを小文字にする。"""
    if arm_id not in ADD3_PRINT_ARMS or candidate_id not in ADD3_PRINT_CANDIDATES:
        raise PredictionError("追補4 PRINT予測")
    length = int(arm_id[1:])
    body = "a" * length
    rows: list[tuple[int, str]] = [(0, body[:80])]
    if length == 79:
        rows.append((1, "b"))
    elif length == 80:
        rows.append((2 if candidate_id == "wrap_then_newline_blank" else 1, "b"))
    else:
        rows.extend(((1, body[80:]), (2, "b")))
    return [_hash_line(row, text) for row, text in rows]


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


def _render_add2_subset(manifest: dict[str, Any], trailing_values: Iterable[int]) -> bytes:
    out = ["record\tcandidate_id\tarm\tphysical_row\tchar_count\tsha256"]
    selected = tuple(trailing_values)
    if (not selected or len(set(selected)) != len(selected)
            or any(value not in ADD2_TRAILING_ROWS for value in selected)):
        raise PredictionError("末尾行数一覧")
    selected_ids = tuple(f"{base}_T{value}"
                         for base in candidate_ids() for value in selected)
    for candidate_id in selected_ids:
        for arm in ADD2_ARMS:
            lines = predict_add2_candidate(manifest, arm, candidate_id)
            for line in lines:
                out.append(f"row\t{candidate_id}\t{arm}\t{line.physical_row}\t{line.char_count}\t{line.sha256}")
            out.append(f"summary\t{candidate_id}\t{arm}\t-\t{len(lines)}\t{_whole_digest(lines)}")
    return ("\n".join(out) + "\n").encode("ascii")


def render_add2_candidates(manifest: dict[str, Any]) -> bytes:
    return _render_add2_subset(manifest, ADD2_TRAILING_ROWS)


def render_add3_print_candidates() -> bytes:
    out = ["record\tcandidate_id\tarm\tphysical_row\tchar_count\tsha256"]
    for candidate_id in ADD3_PRINT_CANDIDATES:
        for arm in ADD3_PRINT_ARMS:
            lines = predict_print_candidate(arm, candidate_id)
            for line in lines:
                out.append(f"row\t{candidate_id}\t{arm}\t{line.physical_row}\t{line.char_count}\t{line.sha256}")
            out.append(f"summary\t{candidate_id}\t{arm}\t-\t{len(lines)}\t{_whole_digest(lines)}")
    return ("\n".join(out) + "\n").encode("ascii")


def render_add4_print_candidates() -> bytes:
    out = ["record\tcandidate_id\tarm\tphysical_row\tchar_count\tsha256"]
    for candidate_id in ADD3_PRINT_CANDIDATES:
        for arm in ADD3_PRINT_ARMS:
            lines = predict_add4_print_candidate(arm, candidate_id)
            for line in lines:
                out.append(f"row\t{candidate_id}\t{arm}\t{line.physical_row}\t{line.char_count}\t{line.sha256}")
            out.append(f"summary\t{candidate_id}\t{arm}\t-\t{len(lines)}\t{_whole_digest(lines)}")
    return ("\n".join(out) + "\n").encode("ascii")


def render_add3_candidates(manifest: dict[str, Any]) -> bytes:
    out = ["record\tcandidate_id\tarm\tphysical_row\tchar_count\tsha256"]
    for candidate_id in add3_candidate_ids():
        for arm in ADD3_FILES_ARMS:
            lines = predict_add3_candidate(manifest, arm, candidate_id)
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
    ap.add_argument("--addendum2", action="store_true")
    ap.add_argument("--addendum3", action="store_true")
    ap.add_argument("--addendum4", action="store_true")
    ap.add_argument("--print-predictions", action="store_true")
    ap.add_argument("--trailing-rows", type=int, choices=ADD2_TRAILING_ROWS)
    args = ap.parse_args()
    try:
        if sum((args.addendum2, args.addendum3, args.addendum4)) > 1:
            raise PredictionError("追補モード重複")
        manifest = _manifest(args.manifest, args.addendum2,
                             args.addendum3 or args.addendum4)
        if args.addendum4:
            if (not args.print_predictions or args.errors_for_arm is not None
                    or args.arms != ",".join(LAYOUT_ARMS)
                    or args.trailing_rows is not None):
                raise PredictionError("追補4引数")
            payload = render_add4_print_candidates()
        elif args.addendum3:
            if (args.errors_for_arm is not None or args.arms != ",".join(LAYOUT_ARMS)
                    or args.trailing_rows is not None):
                raise PredictionError("追補3引数")
            payload = (render_add3_print_candidates() if args.print_predictions
                       else render_add3_candidates(manifest))
        elif args.print_predictions:
            raise PredictionError("PRINT予測は追補3専用")
        elif args.addendum2:
            if args.errors_for_arm is not None or args.arms != ",".join(LAYOUT_ARMS):
                raise PredictionError("追補2引数")
            trailing = ADD2_TRAILING_ROWS if args.trailing_rows is None else (args.trailing_rows,)
            payload = render_add2_candidates(manifest) if len(trailing) == 3 else _render_add2_subset(manifest, trailing)
        elif args.trailing_rows is not None:
            raise PredictionError("末尾行数は追補2専用")
        elif args.errors_for_arm is not None:
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
