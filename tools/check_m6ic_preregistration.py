#!/usr/bin/env python3
"""m6i-c の G3/G9 を凍結文書・設定・実装の相互照合で検査する。"""
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


def table_rows(body: str) -> dict[str, str]:
    result = {}
    for line in body.splitlines():
        match = re.match(r"\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|$", line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def extract(pattern: str, value: str, label: str) -> str:
    match = re.search(pattern, value)
    if not match:
        raise GateError(f"凍結表の値を読めない: {label}")
    return match.group(1)


def frozen_from_docs(prereg: str, addendum: str) -> dict[str, str]:
    table = table_rows(section(prereg, "### 測定前に凍結する", "## 4. 判定名"))
    def sha(label: str) -> str:
        match = SHA_RE.search(table.get(label, ""))
        if not match:
            raise GateError(f"凍結表のSHAを読めない: {label}")
        return match.group(0)
    gate_table = table_rows(section(addendum, "## 2. 直した観測定義", "## 3."))
    gate_value = gate_table.get("`gate_run_min_length`", "")
    return {
        "frozen": "yes",
        "read_issue_frame": extract(r"frame\s+(\d+)", table.get("通常READ発行", ""),
                                    "通常READ発行"),
        "arm_frames": extract(r"各腕(\d+)\s*frames", table.get("測定期限", ""),
                              "測定期限"),
        "repetitions": extract(r"各腕(\d+)走", table.get("反復数", ""), "反復数"),
        "timeout_limit": extract(r"^(\d+)$", table.get("timeout上限", ""),
                                 "timeout上限"),
        "gate_run_min_length": extract(r"(\d+)", gate_value,
                                       "gate_run_min_length"),
        "normal_media_sha256": sha("正常媒体SHA-256"),
        "sector1_sha256": sha("セクタ1 SHA-256"),
    }


def prereg_arms(text: str) -> tuple[str, ...]:
    body = section(text, "## 2. 腕（arm）", "## 3. 関門（gate）")
    arms = tuple(re.findall(r"^### (C[0-3]) `[^`]+`$", body, re.MULTILINE))
    if arms != ("C0", "C1", "C2", "C3"):
        raise GateError("事前登録の腕一覧を一意に抽出できない")
    return arms


def registered_judgments(prereg: str, addendum: str) -> set[str]:
    body = section(prereg, "## 4. 判定名", "## 5. 判定後の行き先")
    tokens = set(re.findall(r"`([a-z][a-z0-9_]+)`", body))
    gate_names = {"gate_failed", "gate_not_entered", "gate_never_released",
                  "gate_released_but_request_lost", "gate_released_and_request_ran",
                  "gate_observation_unusable"}
    wanted = {name for name in tokens if name in {"success", "failure", "unreached"}
              or name in gate_names or name.startswith("c")
              or name.startswith("m6i_c_")}
    add_body = section(addendum, "## 3. 関門 G8 の差し替え", "## 4.")
    wanted.update(name for name in re.findall(r"`([a-z][a-z0-9_]+)`", add_body)
                  if name in gate_names)
    return wanted


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise GateError(f"実装をロードできない: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise GateError(f"実装をロードできない: {path}") from exc
    return module


def check_g3(config: dict[str, list[str]], frozen: dict[str, str],
             m6ia_addendum: str, m6ia_prereg: str, m6ia_cfg: dict[str, list[str]],
             analyzer) -> None:
    if one(m6ia_cfg, "timeout_limit") != frozen["timeout_limit"]:
        raise GateError("G3不一致: timeout_limit")
    if any(one(m6ia_cfg, f"a{i}_frames") != frozen["arm_frames"] for i in range(5)):
        raise GateError("G3不一致: arm_frames")
    add_table = table_rows(m6ia_addendum)
    if extract(r"(\d+)", add_table.get("`timeout_limit`", ""), "m6i-a timeout") \
            != frozen["timeout_limit"]:
        raise GateError("G3不一致: m6i-a追補1 timeout_limit")
    frame_cell = next((value for key, value in add_table.items()
                       if key.startswith("`a0_frames`")), "")
    if extract(r"(\d+)", frame_cell, "m6i-a frames") != frozen["arm_frames"]:
        raise GateError("G3不一致: m6i-a追補1 frames")
    hashes = set(SHA_RE.findall(m6ia_prereg))
    if frozen["normal_media_sha256"] not in hashes:
        raise GateError("G3不一致: m6i-a正常媒体SHA-256")
    if frozen["sector1_sha256"] not in hashes:
        raise GateError("G3不一致: m6i-aセクタ1 SHA-256")
    if analyzer.m6ia.EXPECT_SHA.get(1) != frozen["sector1_sha256"]:
        raise GateError("G3不一致: m6i-a解析器セクタ1 SHA-256")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=REPO / "tools/m6ic_frozen.tsv")
    ap.add_argument("--prereg", type=Path,
                    default=REPO / "docs/notes/m6i-c-b5-b6a0-divergence-preregistration.md")
    ap.add_argument("--addendum", type=Path,
                    default=REPO / "docs/notes/m6i-c-addendum1-gate-observation.md")
    ap.add_argument("--m6ia-addendum", type=Path,
                    default=REPO / "docs/notes/m6i-a-addendum1-frozen-values.md")
    ap.add_argument("--m6ia-prereg", type=Path,
                    default=REPO / "docs/notes/m6i-a-main-sub-link-preregistration.md")
    ap.add_argument("--m6ia-config", type=Path,
                    default=REPO / "tests/conformance/m6ia_g8.tsv")
    args = ap.parse_args()
    try:
        config = load_tsv(args.config)
        prereg = read(args.prereg)
        addendum = read(args.addendum)
        frozen = frozen_from_docs(prereg, addendum)
        allowed = set(frozen) | {"c0_rom_set_sha256", "c1_rom_set_sha256",
                                "arm", "judgment"}
        if set(config) != allowed:
            raise GateError("設定キーに不足または余分がある")
        for key, expected in frozen.items():
            if one(config, key) != expected:
                raise GateError(f"G9不一致: {key}")
        for key in ("c0_rom_set_sha256", "c1_rom_set_sha256"):
            if not SHA_RE.fullmatch(one(config, key)):
                raise GateError(f"G9不一致: {key}")
        arms = prereg_arms(prereg)
        if tuple(config.get("arm", ())) != arms:
            raise GateError("G9不一致: 腕一覧")
        judge = load_module(REPO / "tools/judge_m6ic.py", "m6ic_judge_gate")
        build = load_module(REPO / "tools/build_m6ic_measure_rom.py", "m6ic_build_gate")
        analyzer = load_module(REPO / "tools/analyze_m6ic.py", "m6ic_analyzer_gate")
        if tuple(judge.ARMS) != arms or tuple(build.ARMS) != arms \
                or tuple(analyzer.ARMS) != arms:
            raise GateError("G9不一致: 実装の腕一覧")
        configured = tuple(config.get("judgment", ()))
        if len(configured) != len(set(configured)):
            raise GateError("G9不一致: 判定名の重複")
        if set(configured) != set(judge.REGISTERED):
            raise GateError("G9不一致: 実装の判定名一覧")
        if registered_judgments(prereg, addendum) != set(configured):
            raise GateError("G9不一致: 文書の判定名一覧")
        check_g3(config, frozen, read(args.m6ia_addendum), read(args.m6ia_prereg),
                 load_tsv(args.m6ia_config), analyzer)
    except GateError as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    print("G3/G9 preregistration gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
