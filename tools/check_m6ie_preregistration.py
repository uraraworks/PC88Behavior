#!/usr/bin/env python3
"""m6i-e の G3/G9 を事前登録・m6i-c凍結値・実装と相互照合する。"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class GateError(Exception):
    pass


def load_tsv(path: Path) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = defaultdict(list)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise GateError(f"読めない: {path}") from exc
    for number, raw in enumerate(lines, 1):
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=REPO / "tools/m6ie_frozen.tsv")
    ap.add_argument("--prereg", type=Path,
                    default=REPO / "docs/notes/m6i-e-gate-harm-mechanism-preregistration.md")
    ap.add_argument("--m6ic-config", type=Path, default=REPO / "tools/m6ic_frozen.tsv")
    args = ap.parse_args()
    try:
        config = load_tsv(args.config)
        old = load_tsv(args.m6ic_config)
        prereg = args.prereg.read_text(encoding="utf-8")
        singleton = {"frozen", "read_issue_frame", "arm_frames", "repetitions",
                     "normal_media_sha256", "sector1_sha256", "insertion_e0",
                     "insertion_e1", "insertion_e2", "insertion_e3"}
        if set(config) != singleton | {"arm", "judgment"}:
            raise GateError("設定キーに不足または余分がある")
        for key in ("frozen", "read_issue_frame", "arm_frames", "repetitions",
                    "normal_media_sha256", "sector1_sha256"):
            if one(config, key) != one(old, key):
                raise GateError(f"G3不一致: {key}")
        if not (re.search(r"発行フレームが60", prereg)
                and "媒体SHA・セクタSHA・発行フレーム・測定期限・反復数が" in prereg
                and "m6i-c の凍結表と一致" in prereg):
            raise GateError("G3不一致: 事前登録の数値")
        build = load_module(REPO / "tools/build_m6ie_measure_rom.py", "m6ie_build_gate")
        analyzer = load_module(REPO / "tools/analyze_m6ie.py", "m6ie_analyzer_gate")
        judge = load_module(REPO / "tools/judge_m6ie.py", "m6ie_judge_gate")
        rom_gate = load_module(REPO / "tools/check_m6ie_rom_gate.py", "m6ie_rom_gate")
        arms = ("E0", "E1", "E2", "E3")
        if tuple(config.get("arm", ())) != arms or tuple(build.ARMS) != arms \
                or tuple(analyzer.ARMS) != arms or tuple(judge.ARMS) != arms:
            raise GateError("G9不一致: 腕一覧")
        insertions = {
            "insertion_e0": rom_gate.E0_INSERT.hex("-"),
            "insertion_e1": "none",
            "insertion_e2": rom_gate.E2_INSERT.hex("-"),
            "insertion_e3": rom_gate.E3_INSERT.hex("-"),
        }
        for key, value in insertions.items():
            if one(config, key) != value:
                raise GateError(f"G9不一致: {key}")
        configured = config.get("judgment", [])
        if len(configured) != len(set(configured)) or set(configured) != set(judge.REGISTERED):
            raise GateError("G9不一致: 判定名一覧")
        body = prereg.split("## 4. 判定名", 1)[1].split("## 5.", 1)[0]
        documented = set(re.findall(r"`([a-z][a-z0-9_]+)`", body))
        if set(judge.REGISTERED) - documented:
            raise GateError("G9不一致: 文書の判定名一覧")
    except (OSError, UnicodeError, IndexError, GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    print("G3/G9 preregistration gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
