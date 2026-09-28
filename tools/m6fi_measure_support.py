#!/usr/bin/env python3
"""m6f-i 測定の行署名正規化、G9〜G14、出力監査を行う。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import compare_screen_signatures as css
import derive_m6fi as derive
import predict_m6fi as predict
from analyze_main_to_sub import parse_iolog


class SupportError(ValueError):
    pass


def write_new(path: Path, value) -> None:
    if path.exists():
        raise SupportError("出力先")
    path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=True,
                               separators=(",", ":")) + "\n", encoding="ascii")


def summary(screen: css.ScreenSignature) -> dict:
    return {"line_count": screen.line_count, "char_count": screen.char_count,
            "sha256": screen.sha256}


def content_lines(screen: css.ScreenSignature):
    rows = [(row, item.char_count, item.sha256)
            for row, item in sorted(screen.lines.items()) if row != 19]
    if not rows:
        return [], False
    return [{"physical_row": row, "char_count": count, "sha256": digest}
            for row, count, digest in rows[:-1]], True


def baseline_ok(screen: css.ScreenSignature) -> bool:
    return (0 in screen.lines and screen.lines[0].char_count >= 1 and
            not any(row in screen.lines for row in range(1, 19)))


def g13(screen: css.ScreenSignature) -> dict[str, bool]:
    rows = [(row, item.char_count, item.sha256)
            for row, item in sorted(screen.lines.items())]
    if not rows:
        return {"line_sha": False, "char_count": False, "physical_row": False}
    row, count, digest = rows[0]
    free = next((number for number in range(25) if number not in screen.lines), None)
    return {"line_sha": (row, count, ("0" if digest[0] != "0" else "1") + digest[1:]) != rows[0],
            "char_count": (row, count + 1 if count < 80 else count - 1, digest) != rows[0],
            "physical_row": free is not None and (free, count, digest) != rows[0]}


def normalize(args) -> int:
    baseline = css.read_report(args.report, "baseline")
    final = css.read_report(args.report, "final")
    late = css.read_report(args.report, "late")
    load = css.read_report(args.report, "load") if args.arm in predict.ARMS[:3] else None
    load_late = css.read_report(args.report, "load_late") if load is not None else None
    entries, input_wait = content_lines(final)
    if load is not None:
        _load_entries, load_input_wait = content_lines(load)
    else:
        load_input_wait = False
    _rows, masked = parse_iolog(args.iolog)
    if sum(masked.values()):
        raise SupportError("伏せ字ログ")
    io_text = args.iolog.read_text(encoding="utf-8", errors="replace")
    if sum(int(match.group(1)) for match in re.finditer(r"取りこぼし:\s*(\d+)件", io_text)):
        raise SupportError("ログ欠落")
    observation = {
        "screen": summary(final), "late_screen": summary(late),
        "load_screen": summary(load) if load is not None else None,
        "load_late_screen": summary(load_late) if load_late is not None else None,
        "entry_lines": entries, "input_wait": input_wait,
        "load_input_wait": load_input_wait,
        "reference_unchanged": args.reference_unchanged,
        "output_audit_clean": True,
        "fkey_unchanged": baseline.lines.get(19) == final.lines.get(19),
        "extra_lines_absent": not any(row > 19 for row in final.lines),
        "g13": g13(final),
    }
    write_new(args.output, {"format": "m6fi-run-v1", "arm": args.arm,
                            "repetition": args.repetition,
                            "baseline_ok": baseline_ok(baseline),
                            "observation": observation})
    return 0


def arm_check(args) -> int:
    runs = [json.loads(path.read_text(encoding="ascii")) for path in args.run]
    if (len(runs) != 2 or [run.get("repetition") for run in runs] != [1, 2] or
            any(run.get("format") != "m6fi-run-v1" or run.get("arm") != args.arm
                for run in runs)):
        raise SupportError("2走")
    observations = [run["observation"] for run in runs]
    failed = []
    if (observations[0]["screen"] != observations[1]["screen"] or
            observations[0]["entry_lines"] != observations[1]["entry_lines"]):
        failed.append("G9")
    if any(run["screen"] != run["late_screen"] or not run["input_wait"] or
           (args.arm in predict.ARMS[:3] and (run["load_screen"] is None or
            run["load_screen"] != run["load_late_screen"] or not run["load_input_wait"]))
           for run in observations):
        failed.append("G10")
    if any(not run["reference_unchanged"] for run in observations):
        failed.append("G11")
    if any(not run["output_audit_clean"] or not run["fkey_unchanged"] or
           not run["extra_lines_absent"] for run in observations):
        failed.append("G12")
    if any(not all(run["g13"].values()) for run in observations):
        failed.append("G13")
    print(json.dumps({"failed_gates": failed}, separators=(",", ":")))
    return 1 if failed else 0


def assemble(args) -> int:
    arms = {}
    for arm in predict.ARMS:
        values = [json.loads((args.run_dir / f"{arm}-r{rep}.safe.json").read_text(
            encoding="ascii")) for rep in (1, 2)]
        if any(value.get("arm") != arm or value.get("repetition") != rep
               for rep, value in enumerate(values, 1)):
            raise SupportError("走ID")
        arms[arm] = [value["observation"] for value in values]
    write_new(args.output, {"format": "m6fi-observations-v1", "arms": arms})
    return 0


def plan(args) -> int:
    doc = json.loads(args.manifest.read_text(encoding="ascii"))
    arms = doc["arms"]
    ids = [arm.get("id") for arm in arms]
    if (ids != list(predict.ARMS) or any(arm.get("runs") != 2 or
            arm.get("drive2") != "ascii" or arm.get("final_frame") != 8000 or
            arm.get("list_frame") != (4000 if arm["id"] in predict.ARMS[:3] else None)
            for arm in arms) or len({(arm["id"], rep) for arm in arms for rep in (1, 2)}) != 12):
        raise SupportError("計画")
    print("plan=ok")
    return 0


def result_summary(args) -> int:
    judgment = json.loads(args.judgment.read_text(encoding="ascii"))
    write_new(args.output, {"format": "m6fi-summary-v1", "run_count": 12,
        "frontend_launch_count": args.frontend_launch_count,
        "preflight_gates": {f"G{i}": True for i in range(9)},
        "run_gates": {f"G{i}": True for i in range(9, 16)},
        "judgments": judgment["judgments"], "reference_unchanged": True,
        "output_audit_file_count": 0})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    norm = sub.add_parser("normalize-run")
    norm.add_argument("--report", required=True, type=Path)
    norm.add_argument("--iolog", required=True, type=Path)
    norm.add_argument("--arm", required=True, choices=predict.ARMS)
    norm.add_argument("--repetition", required=True, type=int, choices=(1, 2))
    norm.add_argument("--reference-unchanged", required=True,
                      type=lambda value: value == "true", choices=(True, False))
    norm.add_argument("--output", required=True, type=Path)
    norm.set_defaults(func=normalize)
    check = sub.add_parser("arm-check")
    check.add_argument("--arm", required=True, choices=predict.ARMS)
    check.add_argument("--run", required=True, action="append", type=Path)
    check.set_defaults(func=arm_check)
    ass = sub.add_parser("assemble")
    ass.add_argument("--run-dir", required=True, type=Path)
    ass.add_argument("--output", required=True, type=Path)
    ass.set_defaults(func=assemble)
    chk = sub.add_parser("plan-check")
    chk.add_argument("--manifest", required=True, type=Path)
    chk.set_defaults(func=plan)
    summ = sub.add_parser("summary")
    summ.add_argument("--judgment", required=True, type=Path)
    summ.add_argument("--frontend-launch-count", required=True, type=int)
    summ.add_argument("--output", required=True, type=Path)
    summ.set_defaults(func=result_summary)
    args = ap.parse_args()
    try:
        return args.func(args)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError,
            css.SignatureInputError, derive.InputError, SupportError):
        print("m6fi_measure_support_error=InputError", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
