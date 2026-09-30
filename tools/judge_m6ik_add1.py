#!/usr/bin/env python3
"""m6i-k 追補1: 6腕×2走の解釈と成否を別々に判定する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARMS = ("K-00", "K-01", "K-F0", "K-F1", "K-M1", "K-FR")
P1_ZERO = ("K-00", "K-F0")
P1_ONE = ("K-01", "K-F1", "K-M1", "K-FR")
INSTRUMENTS = (
    ("tools/measure_m6ik.sh", "f7b2836e0a0258e300c9f120e5968787eaa267fec4414e622c8d893c01a03862"),
    ("tools/analyze_m6ik.py", "f97f34bd1c81b005460540e0725facc170470d02a2d934b98ccb6bd20d1ab210"),
    ("tools/judge_m6ik.py", "c05101f689951180688f2abd026eb7079b56dc86ff3f10975a9ecee2a70103e9"),
    ("tools/check_m6ik_gates.py", "abab1a3ddbe2b218e248695413d3424d3aa17646bfef37ac7ad1663d64c2d5cc"),
    ("tools/m6ik_frozen.tsv", "024cb125a029af5d4f22c5003e8fa2dc0d5ab97262b9b920c323e7d6729347e5"),
    ("src/build_main_rom.py", "cc1eeba55f9d92edc81aad75f8c8f610b0f2e3bf454719d1dd5b087e4666e541"),
)
JUDGMENTS = (
    "m6i_k_conversion_by_17", "m6i_k_conversion_needs_both",
    "m6i_k_conversion_by_p1_after_17", "m6i_k_no_conversion",
    "m6i_k_other", "m6i_k_measurement_blind", "m6i_k_inconclusive", "gate_failed",
)
PREDICTIONS = ("m6i_k_conversion_by_17", "p1_success_split",
               "K-M1:split_by_drive", "pre_send_fd_count:0")


def frozen_text() -> str:
    lines = ["frozen\tyes", "source_commit\t3060a34"]
    lines += [f"instrument\t{path}\t{digest}" for path, digest in INSTRUMENTS]
    lines += [f"arm\t{arm}\t{'0x00' if arm in P1_ZERO else '0x01'}" for arm in ARMS]
    lines += [f"judgment\t{name}" for name in JUDGMENTS]
    lines += ["success_judgment\tp1_success_split", "success_judgment\tp1_success_other"]
    lines += [f"prediction\t{name}" for name in PREDICTIONS]
    return "\n".join(lines) + "\n"


def preflight(root: Path = ROOT) -> list[str]:
    """G11/G12。入力結果には一切触れない。"""
    failed = []
    for path, digest in INSTRUMENTS:
        try:
            if hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
                failed.append("G11")
        except OSError:
            failed.append("G11")
    try:
        if (root / "tools/m6ik_add1_frozen.tsv").read_text() != frozen_text():
            failed.append("G12")
    except OSError:
        failed.append("G12")
    return sorted(set(failed))


def arm_class(rows: list[dict]) -> str:
    if any(rows[i]["classification"] != "agree" or rows[i]["index_disagree"]
           for i in (0, 5)):
        return "control_failed"
    names = [row["classification"] for row in rows[1:5]]
    if len(set(names)) == 1 and names[0] in ("logical", "cylinder"):
        return names[0]
    drive1, drive2 = {names[0], names[3]}, {names[1], names[2]}
    if len(drive1) == len(drive2) == 1 and drive1 | drive2 == {"logical", "cylinder"}:
        return "split_by_drive"
    return "mixed"


def valid_run(run: object, arm: str) -> bool:
    if not isinstance(run, dict) or run.get("arm") != arm or run.get("dry_run") or \
            run.get("reached") is not True or run.get("requests_sent") != 6 or \
            type(run.get("pre_send_fd_count")) is not int or run["pre_send_fd_count"] < 0:
        return False
    rows = run.get("rows")
    if not isinstance(rows, list) or len(rows) != 6:
        return False
    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict) or type(row.get("row")) is not int or row["row"] != n or \
                row.get("classification") not in ("agree", "logical", "cylinder", "other", "no_read") or \
                row.get("success") not in ("success", "failed") or \
                type(row.get("index_disagree")) is not bool:
            return False
    return True


def judge(grouped: dict[str, list[dict]]) -> dict:
    results: dict[str, str] = {}
    success: dict[str, list[str]] = {}
    fd_counts: dict[str, int] = {}
    for arm in ARMS:
        runs = grouped.get(arm, [])
        if len(runs) != 2 or not all(valid_run(run, arm) for run in runs) or \
                json.dumps(runs[0], sort_keys=True) != json.dumps(runs[1], sort_keys=True):
            results[arm] = "unreached"
            continue
        rows = runs[0]["rows"]
        results[arm] = arm_class(rows)
        if arm != "K-FR" and results[arm] != "control_failed" and \
                any(row["index_disagree"] for row in rows):
            results[arm] = "unreached"
        success[arm] = [row["success"] for row in rows]
        fd_counts[arm] = runs[0]["pre_send_fd_count"]

    if len(grouped) != len(ARMS) or any(v == "unreached" for v in results.values()) or \
            any(results[a] == "control_failed" for a in ARMS if a != "K-FR"):
        overall = "m6i_k_inconclusive"
    elif any(row["classification"] != "other" or row["index_disagree"]
             for row in grouped["K-FR"][0]["rows"]):
        overall = "m6i_k_measurement_blind"
    elif results["K-F0"] == results["K-F1"] == "logical" and \
            results["K-00"] == results["K-01"] == "cylinder":
        overall = "m6i_k_conversion_by_17"
    elif results["K-F1"] == "logical" and results["K-F0"] == "cylinder" and \
            all(results[a] != "logical" for a in ("K-00", "K-01")):
        overall = "m6i_k_conversion_needs_both"
    elif any(results[a] == "logical" for a in ARMS[:4]) and \
            all(results[a] != "logical" for a in P1_ZERO):
        overall = "m6i_k_conversion_by_p1_after_17"
    elif all(results[a] == "cylinder" for a in ARMS[:4]):
        overall = "m6i_k_no_conversion"
    else:
        overall = "m6i_k_other"

    secondary = None
    if overall not in ("m6i_k_inconclusive", "m6i_k_measurement_blind"):
        secondary = ("p1_success_split" if all(success[a] == ["failed"] * 6 for a in P1_ZERO)
                     and all(success[a] == ["success"] * 6 for a in P1_ONE)
                     else "p1_success_other")
    m1 = (results.get("K-M1") == "split_by_drive" and
          [grouped["K-M1"][0]["rows"][i]["classification"] for i in (1, 4)]
          == ["logical", "logical"])
    return {"judgment": overall, "success_judgment": secondary, "arms": results,
            "success_by_arm": success, "m1_bit0_drive1": m1,
            "pre_send_fd_count_by_arm": fd_counts}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", action="append", type=Path, default=[])
    ap.add_argument("--gate", action="append", default=[], help="任意: G1〜G9=true/false")
    args = ap.parse_args()
    failed = preflight()
    if failed:
        print(json.dumps({"judgment": "gate_failed", "failed_gates": failed}))
        return 1
    if args.gate:
        gates = dict(item.split("=", 1) for item in args.gate if "=" in item)
        if len(args.gate) != 9 or set(gates) != {f"G{i}" for i in range(1, 10)} or \
                any(value not in ("true", "false") for value in gates.values()):
            print(json.dumps({"judgment": "gate_failed", "failed_gates": ["G1-G9"]}))
            return 1
        if any(value == "false" for value in gates.values()):
            print(json.dumps({"judgment": "gate_failed", "failed_gates": sorted(
                name for name, value in gates.items() if value == "false")}))
            return 1
    grouped: dict[str, list[dict]] = {}
    if len(args.result) != 12 or {path.name for path in args.result} != {
            f"{arm}-{n}.json" for arm in ARMS for n in (1, 2)}:
        print(json.dumps({"judgment": "m6i_k_inconclusive"}))
        return 0
    try:
        for path in args.result:
            run = json.loads(path.read_text())
            if not isinstance(run, dict) or run.get("arm") not in ARMS or \
                    path.name not in (f"{run['arm']}-1.json", f"{run['arm']}-2.json"):
                raise ValueError("invalid arm")
            grouped.setdefault(run["arm"], []).append(run)
    except (OSError, ValueError, TypeError):
        print(json.dumps({"judgment": "m6i_k_inconclusive"}))
        return 0
    print(json.dumps(judge(grouped), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
