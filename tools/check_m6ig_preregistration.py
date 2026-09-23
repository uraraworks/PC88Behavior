#!/usr/bin/env python3
"""m6i-g の G3/G9 を事前登録・m6i-c凍結値・実装と相互照合する。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLAIN_SUBROM_SHA256 = "d8b2e64bc27465f955fd308719228f21b06aa07fd780081a88124a52e6d76070"
ARMS = ("G-N", "G-L0", "G-L1", "G-L2")
ISSUE_FRAMES = {"G-N": 6, "G-L0": 60, "G-L1": 60, "G-L2": 60}
EXPECTED_STATES = {
    "G-N": (0, 0, 0), "G-L0": (0, 0, 0),
    "G-L1": (1, 1, 0), "G-L2": (1, 1, 1),
}


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


def keyed(rows: dict[str, list[str]], key: str, parse) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in rows.get(key, []):
        arm, sep, raw = value.partition(":")
        if sep != ":" or arm in result:
            raise GateError(f"G9不一致: {key}")
        try:
            result[arm] = parse(raw)
        except (TypeError, ValueError) as exc:
            raise GateError(f"G9不一致: {key}") from exc
    return result


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


def document_arms(prereg: str) -> tuple[tuple[str, ...], dict[str, int], dict[str, tuple[int, int, int]]]:
    try:
        body = prereg.split("## 2. 腕（arm）", 1)[1].split("## 3. 関門（gate）", 1)[0]
    except IndexError as exc:
        raise GateError("事前登録の腕表を抽出できない") from exc
    found: list[tuple[str, int, tuple[int, int, int]]] = []
    pattern = re.compile(
        r"^\|\s*(G-(?:N|L[0-2]))\s*\|.*?\|\s*(\d+)\s*\|\s*`a=(\d),b=(\d),c=(\d)`\s*\|$",
        re.MULTILINE)
    for match in pattern.finditer(body):
        found.append((match.group(1), int(match.group(2)),
                      tuple(map(int, match.groups()[2:]))))
    return (tuple(row[0] for row in found),
            {row[0]: row[1] for row in found},
            {row[0]: row[2] for row in found})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=REPO / "tools/m6ig_frozen.tsv")
    ap.add_argument("--prereg", type=Path, default=REPO / "docs/notes/m6i-g-clean-preamble-boundary-preregistration.md")
    ap.add_argument("--m6ic-config", type=Path, default=REPO / "tools/m6ic_frozen.tsv")
    args = ap.parse_args()
    try:
        config = load_tsv(args.config)
        old = load_tsv(args.m6ic_config)
        prereg = args.prereg.read_text(encoding="utf-8")
        singleton = {"frozen", "arm_frames", "repetitions", "timeout_limit",
                     "normal_media_sha256", "sector1_sha256", "plain_subrom_sha256"}
        if set(config) != singleton | {"arm", "issue_frame", "expected_state", "judgment"}:
            raise GateError("設定キーに不足または余分がある")
        for key in ("frozen", "arm_frames", "repetitions", "timeout_limit",
                    "normal_media_sha256", "sector1_sha256"):
            if one(config, key) != one(old, key):
                raise GateError(f"G3不一致: {key}")
        if one(config, "plain_subrom_sha256") != PLAIN_SUBROM_SHA256:
            raise GateError("G9不一致: 素のsub ROM SHA-256")

        sys.path.insert(0, str(REPO))
        import src.l3_service.make_subrom as subrom
        plain, _used = subrom.build()
        if hashlib.sha256(bytes(plain)).hexdigest() != PLAIN_SUBROM_SHA256:
            raise GateError("G9不一致: 素のsub ROM生成物")

        doc_arms, doc_frames, doc_states = document_arms(prereg)
        frames = keyed(config, "issue_frame", int)
        states = keyed(config, "expected_state", lambda value: tuple(map(int, value.split(","))))
        if tuple(config.get("arm", ())) != ARMS or doc_arms != ARMS:
            raise GateError("G9不一致: 腕一覧")
        if frames != ISSUE_FRAMES or doc_frames != ISSUE_FRAMES:
            raise GateError("G9不一致: 発行フレーム")
        if states != EXPECTED_STATES or doc_states != EXPECTED_STATES:
            raise GateError("G9不一致: 期待状態")

        build = load_module(REPO / "tools/build_m6ig_measure_rom.py", "m6ig_build_gate")
        analyzer = load_module(REPO / "tools/analyze_m6ig.py", "m6ig_analyzer_gate")
        judge = load_module(REPO / "tools/judge_m6ig.py", "m6ig_judge_gate")
        if tuple(build.ARMS) != ARMS or tuple(analyzer.ARMS) != ARMS or tuple(judge.ARMS) != ARMS:
            raise GateError("G9不一致: 実装の腕一覧")
        if analyzer.ISSUE_FRAMES != ISSUE_FRAMES or analyzer.EXPECTED_STATES != EXPECTED_STATES:
            raise GateError("G9不一致: 解析器の発行フレームまたは期待状態")
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
