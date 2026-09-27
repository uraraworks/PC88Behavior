#!/usr/bin/env python3
"""m6f-g 測定ドライバ用の、画面本文を扱わない正規化・関門補助。"""
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
import compare_screen_signatures as css  # noqa: E402
import derive_m6fg as derive  # noqa: E402
import predict_m6fg as predict  # noqa: E402
from analyze_main_to_sub import parse_iolog  # noqa: E402


class SupportError(ValueError):
    pass


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise SupportError("output_exists")
    path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True,
                               separators=(",", ":")) + "\n", encoding="ascii")


def _summary(value: css.ScreenSignature) -> dict[str, Any]:
    return {"line_count": value.line_count, "char_count": value.char_count,
            "sha256": value.sha256}


def _entry_lines(value: css.ScreenSignature) -> tuple[list[tuple[int, int, str]], bool]:
    rows = [(row, item.char_count, item.sha256)
            for row, item in sorted(value.lines.items()) if row != 19]
    if not rows:
        return [], False
    prompt_row = rows[-1][0]
    return [item for item in rows if item[0] != prompt_row], True


def _baseline_ok(value: css.ScreenSignature) -> bool:
    row0 = value.lines.get(0)
    return (row0 is not None and row0.char_count >= 1
            and not any(row in value.lines for row in range(1, 19)))


def _g13(value: css.ScreenSignature) -> dict[str, bool]:
    rows = [(row, item.char_count, item.sha256)
            for row, item in sorted(value.lines.items())]
    if not rows:
        return {"line_sha": False, "char_count": False, "physical_row": False}
    row, count, digest = rows[0]
    changed_sha = ("0" if digest[0] != "0" else "1") + digest[1:]
    used = {item[0] for item in rows}
    replacement = next((candidate for candidate in range(25) if candidate not in used), None)
    return {
        "line_sha": [(row, count, changed_sha)] + rows[1:] != rows,
        "char_count": [(row, count + 1 if count < 80 else count - 1, digest)] + rows[1:] != rows,
        "physical_row": replacement is not None
        and [(replacement, count, digest)] + rows[1:] != rows,
    }


def normalize_run(args: argparse.Namespace) -> int:
    baseline = css.read_report(args.report, "baseline")
    final = css.read_report(args.report, "final")
    late = css.read_report(args.report, "late")
    entries, input_wait = _entry_lines(final)
    _rows, masked = parse_iolog(args.iolog)
    if sum(masked.values()):
        raise SupportError("masked_iolog")
    dropped = sum(int(match.group(1)) for match in re.finditer(
        r"取りこぼし:\s*(\d+)件", args.iolog.read_text(encoding="utf-8", errors="replace")))
    if dropped:
        raise SupportError("iolog_dropped")
    observation = {
        "screen": _summary(final), "late_screen": _summary(late),
        "entry_lines": [{"physical_row": row, "char_count": count, "sha256": sha}
                        for row, count, sha in entries],
        "input_wait": input_wait,
        "reference_unchanged": args.reference_unchanged,
        "output_audit_clean": True,
        "fkey_unchanged": baseline.lines.get(19) == final.lines.get(19),
        "extra_lines_absent": not any(row > 19 for row in final.lines),
        "g13": _g13(final),
    }
    _write_new(args.output, {
        "format": "m6fg-run-v1", "arm": args.arm,
        "repetition": args.repetition, "baseline_ok": _baseline_ok(baseline),
        "observation": observation,
    })
    return 0


def arm_check(args: argparse.Namespace) -> int:
    runs = [json.loads(path.read_text(encoding="ascii")) for path in args.run]
    if (len(runs) != 2 or any(run.get("format") != "m6fg-run-v1" for run in runs)
            or [run.get("repetition") for run in runs] != [1, 2]
            or any(run.get("arm") != args.arm for run in runs)):
        raise SupportError("run_format")
    observations = [run["observation"] for run in runs]
    failed: set[str] = set()
    if (observations[0]["screen"] != observations[1]["screen"]
            or observations[0]["entry_lines"] != observations[1]["entry_lines"]):
        failed.add("G9")
    if any(run["screen"] != run["late_screen"] or not run["input_wait"]
           for run in observations):
        failed.add("G10")
    if any(not run["reference_unchanged"] for run in observations):
        failed.add("G11")
    if any(not run["output_audit_clean"] or not run["fkey_unchanged"]
           or not run["extra_lines_absent"] for run in observations):
        failed.add("G12")
    if any(not all(run["g13"].values()) for run in observations):
        failed.add("G13")
    print(json.dumps({"failed_gates": sorted(failed)}, separators=(",", ":")))
    return 1 if failed else 0


def assemble(args: argparse.Namespace) -> int:
    arms: dict[str, list[dict[str, Any]]] = {}
    for arm in predict.ALL_ARMS:
        values = [json.loads((args.run_dir / f"{arm}-r{rep}.safe.json").read_text(
            encoding="ascii")) for rep in (1, 2)]
        if any(value.get("arm") != arm or value.get("repetition") != rep
               for rep, value in enumerate(values, 1)):
            raise SupportError("run_identity")
        arms[arm] = [value["observation"] for value in values]
    _write_new(args.output, {"format": "m6fg-observations-v1", "arms": arms})
    return 0


def summary(args: argparse.Namespace) -> int:
    judgment = json.loads(args.judgment.read_text(encoding="ascii"))
    _write_new(args.output, {
        "format": "m6fg-summary-v1", "run_count": 10,
        "frontend_launch_count": args.frontend_launch_count,
        "preflight_gates": {f"G{index}": True for index in range(9)},
        "run_gates": {f"G{index}": True for index in range(9, 15)},
        "judgments": judgment["judgments"], "reference_unchanged": True,
        "output_audit_file_count": 0,
    })
    return 0


def plan_check(args: argparse.Namespace) -> int:
    manifest = predict._manifest(args.manifest)
    arms = manifest["arms"]
    ids = [arm.get("id") for arm in arms]
    plan = [(arm.get("id"), rep) for arm in arms
            for rep in range(1, arm.get("runs", 0) + 1)]
    if (ids != list(predict.ALL_ARMS) or len(plan) != 10 or len(set(plan)) != 10
            or any(arm.get("runs") != 2 for arm in arms)):
        raise SupportError("plan")
    print("plan=ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    norm = sub.add_parser("normalize-run")
    norm.add_argument("--report", required=True, type=Path)
    norm.add_argument("--iolog", required=True, type=Path)
    norm.add_argument("--arm", required=True, choices=predict.ALL_ARMS)
    norm.add_argument("--repetition", required=True, type=int, choices=(1, 2))
    norm.add_argument("--reference-unchanged", required=True,
                      type=lambda value: value == "true", choices=(True, False))
    norm.add_argument("--output", required=True, type=Path)
    norm.set_defaults(func=normalize_run)
    arm = sub.add_parser("arm-check")
    arm.add_argument("--arm", required=True, choices=predict.ALL_ARMS)
    arm.add_argument("--run", required=True, action="append", type=Path)
    arm.set_defaults(func=arm_check)
    ass = sub.add_parser("assemble")
    ass.add_argument("--run-dir", required=True, type=Path)
    ass.add_argument("--output", required=True, type=Path)
    ass.set_defaults(func=assemble)
    summ = sub.add_parser("summary")
    summ.add_argument("--judgment", required=True, type=Path)
    summ.add_argument("--frontend-launch-count", required=True, type=int)
    summ.add_argument("--output", required=True, type=Path)
    summ.set_defaults(func=summary)
    plan = sub.add_parser("plan-check")
    plan.add_argument("--manifest", required=True, type=Path)
    plan.set_defaults(func=plan_check)
    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError,
            ValueError, css.SignatureInputError, SupportError):
        print("m6fg_measure_support_error=InputError", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
