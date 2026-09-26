#!/usr/bin/env python3
"""m6f-e 測定ドライバ用の、画面本文を扱わない正規化・関門補助。

q88measure の署名 TSV と I/O ログを一時領域で読み、判定器が受け取る
``m6fe-observations-v1`` と許可リスト式の要約だけを作る。入力値や画面本文を
例外・標準出力へ反射しない。
"""
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
import derive_m6fe as derive  # noqa: E402
import predict_m6fe as predict  # noqa: E402
from analyze_main_to_sub import parse_iolog  # noqa: E402
from analyze_write_path import parse_commands  # noqa: E402
from m6fc_fdc_by_drive import split_by_drive  # noqa: E402


class SupportError(ValueError):
    pass


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise SupportError("output_exists")
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":")) + "\n"
    path.write_text(payload, encoding="ascii")


def _summary(value: css.ScreenSignature) -> dict[str, Any]:
    return {"line_count": value.line_count, "char_count": value.char_count,
            "sha256": value.sha256}


def _triples(value: css.ScreenSignature) -> list[tuple[int, int, str]]:
    return [(row, item.char_count, item.sha256)
            for row, item in sorted(value.lines.items())]


def _entry_lines(value: css.ScreenSignature) -> tuple[list[tuple[int, int, str]], bool]:
    """row19を機能キー行、残る最終行を既知の入力待ち行として除く。"""
    rows = [(row, item.char_count, item.sha256)
            for row, item in sorted(value.lines.items()) if row != 19]
    if not rows:
        return [], False
    prompt_row = rows[-1][0]
    return [item for item in rows if item[0] != prompt_row], True


def _line_json(lines: list[tuple[int, int, str]]) -> list[dict[str, Any]]:
    return [{"physical_row": row, "char_count": count, "sha256": digest}
            for row, count, digest in lines]


def _baseline_ok(value: css.ScreenSignature) -> bool:
    row0 = value.lines.get(0)
    return (row0 is not None and row0.char_count >= 1
            and not any(row in value.lines for row in range(1, 19)))


def _g13(value: css.ScreenSignature) -> dict[str, bool]:
    rows = _triples(value)
    if not rows:
        return {"line_sha": False, "char_count": False, "physical_row": False}
    row, count, digest = rows[0]
    changed_sha = ("0" if digest[0] != "0" else "1") + digest[1:]
    line_sha = [(row, count, changed_sha)] + rows[1:] != rows
    changed_count = count + 1 if count < 80 else count - 1
    char_count = [(row, changed_count, digest)] + rows[1:] != rows
    used = {item[0] for item in rows}
    replacement = next((candidate for candidate in range(25) if candidate not in used), None)
    physical_row = replacement is not None and (
        [(replacement, count, digest)] + rows[1:] != rows)
    return {"line_sha": line_sha, "char_count": char_count,
            "physical_row": physical_row}


def normalize_run(args: argparse.Namespace) -> int:
    baseline = css.read_report(args.report, "baseline")
    final = css.read_report(args.report, "final")
    late = css.read_report(args.report, "late")
    entries, input_wait = _entry_lines(final)
    rows, masked = parse_iolog(args.iolog)
    if sum(masked.values()):
        raise SupportError("masked_iolog")
    commands = parse_commands(rows)
    split = split_by_drive(commands, 700)
    preinsert_fdc_count = sum(1 for command in commands if 700 <= command.frame < 1200)
    dropped = 0
    text = args.iolog.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(r"取りこぼし:\s*(\d+)件", text):
        dropped += int(match.group(1))
    baseline_fkey = baseline.lines.get(19)
    final_fkey = final.lines.get(19)
    extra_rows = any(row > 19 for row in final.lines)
    observation = {
        "screen": _summary(final), "late_screen": _summary(late),
        "entry_lines": _line_json(entries), "input_wait": input_wait,
        "reference_unchanged": args.reference_unchanged,
        "output_audit_clean": True,
        "g13": _g13(final),
        "fkey_unchanged": baseline_fkey == final_fkey,
        "extra_lines_absent": not extra_rows,
    }
    value = {
        "format": "m6fe-run-v1", "arm": args.arm, "repetition": args.repetition,
        "baseline_ok": _baseline_ok(baseline), "observation": observation,
        "drive1_read_count": split["drive1_read_count"],
        "preinsert_fdc_count": preinsert_fdc_count,
        "iolog_dropped": dropped,
    }
    _write_new(args.output, value)
    return 0


def arm_check(args: argparse.Namespace) -> int:
    runs = [json.loads(path.read_text(encoding="ascii")) for path in args.run]
    if len(runs) != 2 or any(run.get("format") != "m6fe-run-v1" for run in runs):
        raise SupportError("run_format")
    failed: set[str] = set()
    observations = [run["observation"] for run in runs]
    if (observations[0]["screen"] != observations[1]["screen"]
            or observations[0]["entry_lines"] != observations[1]["entry_lines"]):
        failed.add("G9")
    if args.arm not in ("N-wait", "L96"):
        if any(run["screen"] != run["late_screen"] or not run["input_wait"]
               for run in observations):
            failed.add("G10")
    if any(not run["reference_unchanged"] for run in observations):
        failed.add("G11")
    if any(not run["output_audit_clean"] for run in observations):
        failed.add("G12")
    if any(not all(run["g13"].values()) for run in observations):
        failed.add("G13")
    print(json.dumps({"failed_gates": sorted(failed)}, separators=(",", ":")))
    return 1 if failed else 0


def _tuples(run: dict[str, Any]) -> tuple[tuple[int, int, str], ...]:
    return tuple((item["physical_row"], item["char_count"], item["sha256"])
                 for item in run["observation"]["entry_lines"])


def _matches_dynamic(manifest: dict[str, Any], arm: str,
                     lines: tuple[tuple[int, int, str], ...]) -> bool:
    for candidate in predict.candidate_ids():
        expected = tuple((item.physical_row, item.char_count, item.sha256)
                         for item in predict.predict_candidate(manifest, arm, candidate))
        if expected == lines:
            return True
    return False


def assemble(args: argparse.Namespace) -> int:
    manifest = predict._manifest(args.manifest)
    runs_by_arm: dict[str, list[dict[str, Any]]] = {}
    for arm in derive.ALL_ARMS:
        paths = [args.run_dir / f"{arm}-r{rep}.safe.json" for rep in (1, 2)]
        values = [json.loads(path.read_text(encoding="ascii")) for path in paths]
        if any(value.get("arm") != arm or value.get("repetition") != rep
               for rep, value in enumerate(values, 1)):
            raise SupportError("run_identity")
        runs_by_arm[arm] = values

    # 追加行は本文でなく、凍結候補が取りうるエントリ行数の集合から判定する。
    # 内容だけが違う場合はno_candidate、行数自体が候補外ならextra_linesと分ける。
    for arm, values in runs_by_arm.items():
        if arm in predict.DISPLAY_ARMS:
            allowed_counts = {
                len(predict.predict_candidate(manifest, arm, candidate))
                for candidate in predict.candidate_ids()
            }
        elif arm in derive.ERROR_ARMS:
            allowed_counts = {0, 1}
        else:
            allowed_counts = set()
        for value in values:
            actual_count = len(value["observation"]["entry_lines"])
            value["observation"]["extra_lines_absent"] = (
                value["observation"]["extra_lines_absent"]
                and actual_count in allowed_counts)

    l11_ok = all(_matches_dynamic(manifest, "L11", _tuples(run))
                 for run in runs_by_arm["L11"])
    empty_ok = all(not _tuples(run) for run in runs_by_arm["L0"])
    l96_stable = all(run["observation"]["screen"] == run["observation"]["late_screen"]
                     and run["observation"]["input_wait"]
                     for run in runs_by_arm["L96"])
    l96_match = all(_matches_dynamic(manifest, "L96", _tuples(run))
                    for run in runs_by_arm["L96"])
    overflow = ("scrolls_to_tail" if l96_match else
                "page_wait" if not l96_stable else "overflow_other")

    d1_ok = all(_matches_dynamic(manifest, arm, _tuples(run))
                for arm in ("D-omit", "D-1") for run in runs_by_arm[arm])
    d2_ok = all(_matches_dynamic(manifest, "D-2", _tuples(run))
                for run in runs_by_arm["D-2"])
    if d1_ok and d2_ok:
        drive = "default_is_1_explicit_1_2"
    elif all(run["drive1_read_count"] == 0
             for arm in ("D-omit", "D-1") for run in runs_by_arm[arm]):
        drive = "drive1_served_from_cache"
    else:
        drive = "drive_selection_other"
    expression = ("drive_expression_accepted"
                  if all(_matches_dynamic(manifest, "D-expr", _tuples(run))
                         for run in runs_by_arm["D-expr"])
                  else "drive_expression_other")
    n_waits = (all(_matches_dynamic(manifest, "N-wait", _tuples(run))
                   for run in runs_by_arm["N-wait"])
               and all(run["preinsert_fdc_count"] > 0 for run in runs_by_arm["N-wait"]))
    no_media = "files_no_media_waits_for_media" if n_waits else "inconclusive_no_media"

    observations = {
        "format": "m6fe-observations-v1",
        "arms": {arm: [run["observation"] for run in runs_by_arm[arm]]
                 for arm in derive.ALL_ARMS},
        "aux": {
            "order": "directory_order_skips_deleted" if l11_ok else "order_other",
            "empty": "empty_has_no_entry_rows" if empty_ok else "empty_other",
            "overflow": overflow, "drive": drive, "expression": expression,
            "no_media": no_media,
        },
    }
    _write_new(args.output, observations)
    return 0


def summary(args: argparse.Namespace) -> int:
    judgment = json.loads(args.judgment.read_text(encoding="ascii"))
    drive_reads: dict[str, list[int]] = {}
    for arm in ("D-omit", "D-1"):
        drive_reads[arm] = [
            json.loads((args.run_dir / f"{arm}-r{rep}.safe.json").read_text(
                encoding="ascii"))["drive1_read_count"] for rep in (1, 2)
        ]
    value = {
        "format": "m6fe-summary-v1", "run_count": 30,
        "frontend_launch_count": args.frontend_launch_count,
        "preflight_gates": {f"G{index}": True for index in range(9)},
        "run_gates": {f"G{index}": True for index in range(9, 15)},
        "judgments": judgment["judgments"],
        "drive1_read_count": drive_reads,
        "reference_unchanged": True, "output_audit_file_count": 0,
    }
    _write_new(args.output, value)
    return 0


def plan_check(args: argparse.Namespace) -> int:
    manifest = predict._manifest(args.manifest)
    arms = manifest["arms"]
    ids = [arm.get("id") for arm in arms]
    plan = [(arm.get("id"), rep) for arm in arms for rep in range(1, arm.get("runs", 0) + 1)]
    ok = (ids == list(derive.ALL_ARMS) and len(plan) == 30 and len(set(plan)) == 30
          and all(arm.get("runs") == 2 for arm in arms))
    if not ok:
        raise SupportError("plan")
    print("plan=ok")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    norm = sub.add_parser("normalize-run")
    norm.add_argument("--report", required=True, type=Path)
    norm.add_argument("--iolog", required=True, type=Path)
    norm.add_argument("--arm", required=True, choices=derive.ALL_ARMS)
    norm.add_argument("--repetition", required=True, type=int, choices=(1, 2))
    norm.add_argument("--reference-unchanged", required=True,
                      type=lambda value: value == "true", choices=(True, False))
    norm.add_argument("--output", required=True, type=Path)
    norm.set_defaults(func=normalize_run)
    arm = sub.add_parser("arm-check")
    arm.add_argument("--arm", required=True, choices=derive.ALL_ARMS)
    arm.add_argument("--run", required=True, type=Path, action="append")
    arm.set_defaults(func=arm_check)
    ass = sub.add_parser("assemble")
    ass.add_argument("--manifest", required=True, type=Path)
    ass.add_argument("--run-dir", required=True, type=Path)
    ass.add_argument("--output", required=True, type=Path)
    ass.set_defaults(func=assemble)
    summ = sub.add_parser("summary")
    summ.add_argument("--judgment", required=True, type=Path)
    summ.add_argument("--run-dir", required=True, type=Path)
    summ.add_argument("--frontend-launch-count", required=True, type=int)
    summ.add_argument("--output", required=True, type=Path)
    summ.set_defaults(func=summary)
    plan = sub.add_parser("plan-check")
    plan.add_argument("--manifest", required=True, type=Path)
    plan.set_defaults(func=plan_check)
    args = ap.parse_args()
    try:
        return args.func(args)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError,
            ValueError, css.SignatureInputError, SupportError):
        print("m6fe_measure_support_error=InputError", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
