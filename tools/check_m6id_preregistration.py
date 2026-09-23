#!/usr/bin/env python3
"""m6i-d の G3/G7 を事前登録・追補・凍結表・実装間で照合する。"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NEW_OVERALL = {
    "m6i_d_only_b5_unverified",
    "m6i_d_multiple_arms_unverified",
    "m6i_d_no_arm_unverified",
}


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


def judgment_tokens(body: str) -> set[str]:
    tokens = set(re.findall(r"`([a-z][a-z0-9_]+)`", body))
    return {name for name in tokens if name in {"gate_failed", "unreached"}
            or name.startswith("arm_gate_") or name.startswith("control_")
            or name.startswith("m6i_d_") or name.startswith("m6i_b_b2_b4_")}


def prereg_judgments(prereg: str, addendum: str) -> set[str]:
    body = section(prereg, "## 4. 判定名", "## 5. 判定後の行き先")
    addendum_body = section(addendum, "## 3. 直し方", "## 4. 行き先の対応")
    addendum_names = judgment_tokens(addendum_body)
    if not NEW_OVERALL <= addendum_names:
        raise GateError("追補1の新しい総合判定名を確認できない")
    original = judgment_tokens(body)
    superseded = {name for name in original
                  if name.startswith("m6i_d_")
                  and name.endswith("_never_released")}
    return (original - superseded) | NEW_OVERALL


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=REPO / "tools/m6id_frozen.tsv")
    ap.add_argument("--prereg", type=Path,
                    default=REPO / "docs/notes/m6i-d-gate-release-audit-preregistration.md")
    ap.add_argument("--addendum", type=Path,
                    default=REPO / "docs/notes/m6i-d-addendum1-unverified-arms.md")
    ap.add_argument("--addendum2", type=Path,
                    default=REPO / "docs/notes/m6i-d-addendum2-pc-anchored-observation.md")
    ap.add_argument("--m6ib-config", type=Path, default=REPO / "tools/m6ib_frozen.tsv")
    args = ap.parse_args()
    try:
        config = load_tsv(args.config)
        m6ib = load_tsv(args.m6ib_config)
        prereg = read(args.prereg)
        addendum = read(args.addendum)
        addendum2 = read(args.addendum2)
        scalar_keys = {"frozen", "arm_frames", "repetitions",
                       "normal_media_sha256"}
        if set(config) != scalar_keys | {"arm", "gate_label", "judgment"}:
            raise GateError("設定キーに不足または余分がある")
        if one(config, "frozen") != "yes":
            raise GateError("G7不一致: frozen")
        frame = one(config, "arm_frames")
        if any(one(m6ib, key) != frame for key in
               ("b0_b4_frames", "b5_frames", "b6_a0_a4_frames")):
            raise GateError("G3不一致: arm_frames")
        for key in ("repetitions", "normal_media_sha256"):
            if one(config, key) != one(m6ib, key):
                raise GateError(f"G3不一致: {key}")
        if "各腕2走" not in prereg \
                or "m6i-b の凍結値をそのまま使う" not in prereg:
            raise GateError("事前登録の凍結記述を確認できない")

        arms = ("D-B0", "D-B1", "D-B2", "D-B3", "D-B4", "D-B5", "D-B6-A0")
        arm_body = section(prereg, "## 2. 腕（arm）", "## 3. 関門（gate）")
        if not all(name in arm_body for name in ("D-B0", "D-B1〜D-B5", "D-B6-A0")):
            raise GateError("事前登録の腕一覧を確認できない")
        if tuple(config.get("arm", ())) != arms:
            raise GateError("G7不一致: 腕一覧")
        judge = load_module(REPO / "tools/judge_m6id.py", "m6id_judge_gate")
        analyzer = load_module(REPO / "tools/analyze_m6id.py", "m6id_analyzer_gate")
        if tuple(judge.ARMS) != arms or tuple(analyzer.ARMS) != arms:
            raise GateError("G7不一致: 実装の腕一覧")
        expected_gate_rows = tuple(
            f"{arm}={label or '-'}"
            for arm, label in analyzer.GATE_LABELS.items()
        )
        if tuple(config.get("gate_label", ())) != expected_gate_rows:
            raise GateError("G7不一致: ゲートラベル対応")
        if not all(label in addendum2 for label in analyzer.ALL_GATE_LABELS) \
                or "D-B0, D-B6-A0" not in addendum2 \
                or "gate_run_min_length" not in addendum2:
            raise GateError("追補2のゲートラベル対応を確認できない")
        try:
            for arm in arms:
                analyzer.gate_address_for_arm(arm, args.config)
        except (OSError, UnicodeError, ValueError, SystemExit) as exc:
            raise GateError("G7不一致: sub ROMのゲートラベル") from exc
        judgments = tuple(config.get("judgment", ()))
        if len(judgments) != len(set(judgments)):
            raise GateError("G7不一致: 判定名の重複")
        if set(judgments) != set(judge.REGISTERED):
            raise GateError("G7不一致: 実装の判定名一覧")
        if set(judgments) != prereg_judgments(prereg, addendum):
            raise GateError("G7不一致: 文書の判定名一覧")
    except GateError as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    print("G3/G7 preregistration gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
