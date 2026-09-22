#!/usr/bin/env python3
"""m6i-b の G3/G9 を、凍結文書・設定・実装の相互照合で検査する。"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHA_RE = re.compile(r"[0-9a-f]{64}")


class GateError(Exception):
    pass


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise GateError(f"読めない: {path}") from exc


def load_tsv(path: Path) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = defaultdict(list)
    for number, raw in enumerate(read(path).splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        fields = raw.split("\t")
        if len(fields) != 2 or not all(fields):
            raise GateError(f"TSV形式不正: {path}:{number}")
        rows[fields[0]].append(fields[1])
    return dict(rows)


def one(rows: dict[str, list[str]], key: str) -> str:
    values = rows.get(key, [])
    if len(values) != 1:
        raise GateError(f"{key} は1件でなければならない")
    return values[0]


def section(text: str, start: str, end: str | None) -> str:
    try:
        body = text.split(start, 1)[1]
        return body if end is None else body.split(end, 1)[0]
    except IndexError as exc:
        raise GateError(f"節を抽出できない: {start}") from exc


def frozen_from_prereg(text: str) -> dict[str, str]:
    body = section(text, "### 測定前に凍結する", "## 4. 判定名")
    table = {}
    for line in body.splitlines():
        match = re.match(r"\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|$", line)
        if match:
            table[match.group(1)] = match.group(2)
    def sha(label: str) -> str:
        found = SHA_RE.search(table.get(label, ""))
        if not found:
            raise GateError(f"凍結表のSHAを読めない: {label}")
        return found.group(0)
    screen = table.get("画面ベースライン", "")
    screen_counts = re.search(r"(\d+)行、(\d+)文字", screen)
    if not screen_counts:
        raise GateError("画面ベースラインを読めない")
    values = {
        "frozen": "yes",
        "read_issue_frame": number(table, "B1〜B5の通常READ発行", r"frame\s+(\d+)"),
        "b0_b4_frames": number(table, "B0〜B4の測定期限", r"(\d+)\s*frames"),
        "b5_frames": number(table, "B5の測定期限", r"(\d+)\s*frames"),
        "b6_a0_a4_frames": number(table, "B6 A0/A1/A2/A4各枝", r"各(\d+)\s*frames"),
        "b6_a5_frames": number(table, "B6 A5", r"(\d+)\s*frames"),
        "b6_a5_reads": number(table, "B6 A5", r"通常READ\s*(\d+)回"),
        "repetitions": number(table, "反復数", r"各腕・各枝(\d+)走"),
        "timeout_limit": number(table, "timeout上限", r"^(\d+)$"),
        "normal_media_sha256": sha("正常媒体SHA-256"),
        "blank_media_sha256": sha("空媒体SHA-256"),
        "sector1_sha256": sha("セクタ1 SHA-256"),
        "sector2_sha256": sha("セクタ2 SHA-256"),
        "a5_registers": strip_code(table.get("A5保存対象", "")),
        "key_scenario": strip_code(table.get("キー場面", "")),
        "screen_line_count": screen_counts.group(1),
        "screen_char_count": screen_counts.group(2),
        "screen_sha256": sha("画面ベースライン"),
    }
    return values


def number(table: dict[str, str], label: str, pattern: str) -> str:
    match = re.search(pattern, table.get(label, ""))
    if not match:
        raise GateError(f"凍結表の値を読めない: {label}")
    return match.group(1)


def strip_code(value: str) -> str:
    match = re.fullmatch(r"`([^`]+)`", value.strip())
    if not match:
        raise GateError(f"コード値を読めない: {value}")
    return match.group(1)


def prereg_arms(text: str) -> tuple[str, ...]:
    body = section(text, "## 2. 腕（arm）", "## 3. 関門（gate）")
    basic = re.findall(r"^### (B[0-5]) `", body, re.MULTILINE)
    b6_body = section(body, "### B6 `m6ia_reach_replay`", None)
    branch_names = set(re.findall(r"A(?:0|1|2|4-cont|4-pair|5)", b6_body))
    branches = [f"B6-{name}" for name in
                ("A0", "A1", "A2", "A4-cont", "A4-pair", "A5")
                if name in branch_names]
    result = tuple(basic + branches)
    if len(result) != 12:
        raise GateError("事前登録の実行腕を一意に抽出できない")
    return result


def explicit_judgments(text: str) -> set[str]:
    body = section(text, "## 4. 判定名", "## 5. 判定後の行き先")
    values = set(re.findall(r"^- `([^`]+)`:", body, re.MULTILINE))
    if not values:
        raise GateError("事前登録の判定名を抽出できない")
    return values


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise GateError(f"実装をロードできない: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise GateError(f"実装をロードできない: {path}") from exc
    return module


def check_g3(config: dict[str, list[str]], frozen: dict[str, str],
             addendum_text: str, m6ia_text: str, m6ia_cfg: dict[str, list[str]],
             analyzer) -> None:
    # 追補1が正典として明記する m6ia_g8.tsv と、追補本文の表をともに確認する。
    addendum_table = dict(re.findall(
        r"^\| `([^`]+)` \| ([^|]+?) \|", addendum_text, re.MULTILINE))
    frame_range = re.search(
        r"^\| `a0_frames`〜`a4_frames` \| ([^|]+?) \|", addendum_text,
        re.MULTILINE)
    if frame_range:
        addendum_table["a0_frames"] = frame_range.group(1)
    required = {"timeout_limit", "a0_frames", "a5_frames", "a5_registers",
                "key_scenario", "screen_line_count", "screen_char_count", "screen_sha256"}
    if not required <= set(addendum_table):
        raise GateError("m6i-a追補1の凍結表が不足")
    pairs = {
        "timeout_limit": "timeout_limit", "a5_frames": "b6_a5_frames",
        "a5_registers": "a5_registers", "key_scenario": "key_scenario",
        "screen_line_count": "screen_line_count", "screen_char_count": "screen_char_count",
        "screen_sha256": "screen_sha256",
    }
    for m6ia_key, m6ib_key in pairs.items():
        actual = one(m6ia_cfg, m6ia_key)
        if actual != frozen[m6ib_key]:
            raise GateError(f"G3不一致: {m6ib_key} != m6ia_g8.{m6ia_key}")
    for index in range(5):
        if one(m6ia_cfg, f"a{index}_frames") != frozen["b0_b4_frames"]:
            raise GateError(f"G3不一致: a{index}_frames")
    # 追補本文で省略されたSHA表記も、正典TSVの先頭・末尾と一致させる。
    for key in required:
        shown = addendum_table[key].strip().strip("`")
        actual = one(m6ia_cfg, key)
        if "…" in shown:
            prefix, suffix = shown.split("…", 1)
            if not (actual.startswith(prefix) and actual.endswith(suffix)):
                raise GateError(f"G3不一致: 追補1 {key}")
        elif key == "a0_frames":
            if shown != actual or any(one(m6ia_cfg, f"a{i}_frames") != shown for i in range(5)):
                raise GateError("G3不一致: 追補1 a0_frames〜a4_frames")
        elif shown != actual:
            raise GateError(f"G3不一致: 追補1 {key}")
    # 媒体と通常READ期待値は m6i-a 本体の登録値にも存在しなければならない。
    registered_hashes = set(SHA_RE.findall(m6ia_text))
    hash_keys = ("normal_media_sha256", "blank_media_sha256",
                 "sector1_sha256", "sector2_sha256")
    if {frozen[key] for key in hash_keys} != registered_hashes:
        raise GateError("G3不一致: m6i-a媒体または通常READ SHA-256")
    if getattr(analyzer.m6ia, "EXPECT_SHA", None) != {1: frozen["sector1_sha256"],
                                                      2: frozen["sector2_sha256"]}:
        raise GateError("G3不一致: m6i-a解析器の通常READ SHA-256")
    if getattr(analyzer, "SCREEN_EXPECTED", None) != (
            int(frozen["screen_line_count"]), int(frozen["screen_char_count"]),
            frozen["screen_sha256"]):
        raise GateError("G3不一致: m6i-b解析器の画面署名")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=REPO / "tools/m6ib_frozen.tsv")
    ap.add_argument("--prereg", type=Path, default=REPO / "docs/notes/m6i-b-first-request-timing-preregistration.md")
    ap.add_argument("--m6ia-addendum", type=Path, default=REPO / "docs/notes/m6i-a-addendum1-frozen-values.md")
    ap.add_argument("--m6ia-prereg", type=Path, default=REPO / "docs/notes/m6i-a-main-sub-link-preregistration.md")
    ap.add_argument("--m6ia-config", type=Path, default=REPO / "tests/conformance/m6ia_g8.tsv")
    args = ap.parse_args()
    try:
        config = load_tsv(args.config)
        prereg_text = read(args.prereg)
        frozen = frozen_from_prereg(prereg_text)
        allowed_keys = set(frozen) | {"arm", "judgment"}
        if set(config) != allowed_keys:
            raise GateError("設定キーに不足または余分がある")
        for key, expected in frozen.items():
            if one(config, key) != expected:
                raise GateError(f"G9不一致: {key}")
        arms = prereg_arms(prereg_text)
        if tuple(config.get("arm", ())) != arms:
            raise GateError("G9不一致: 腕一覧")
        judge = load_module(REPO / "tools/judge_m6ib_first_request.py", "m6ib_judge_gate")
        build = load_module(REPO / "tools/build_m6ib_measure_rom.py", "m6ib_build_gate")
        analyzer = load_module(REPO / "tools/analyze_m6ib_first_request.py", "m6ib_analyzer_gate")
        if tuple(judge.ARMS) != arms or tuple(build.ARMS) != arms:
            raise GateError("G9不一致: 実装の腕一覧")
        configured_judgments = tuple(config.get("judgment", ()))
        if len(configured_judgments) != len(set(configured_judgments)):
            raise GateError("G9不一致: 判定名の重複")
        if set(judge.REGISTERED) != set(configured_judgments):
            raise GateError("G9不一致: 実装の判定名一覧")
        if not explicit_judgments(prereg_text) <= set(configured_judgments):
            raise GateError("G9不一致: 事前登録の判定名一覧")
        check_g3(config, frozen, read(args.m6ia_addendum), read(args.m6ia_prereg),
                 load_tsv(args.m6ia_config), analyzer)
    except GateError as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    print("G3/G9 preregistration gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
