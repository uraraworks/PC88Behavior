#!/usr/bin/env python3
"""m6i-j 追補5。最初の WRITE の手前（P, S）と、sub 応答の位置だけを採る解析。

腕・打鍵・媒体・走は追補3・4（m6ij_add3）をそのまま使い、解析だけを差し替える。
出力してよいのは制御バイト（P を含む run の先頭バイト）と件数と真偽だけ。
WRITE のデータ部・READ で返る値・一般の値列は出力しない。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import analyze_write_path as fdc
import compare_screen_signatures as screens
import m6ij_add3 as a3
from m6fh_body import BodyError

HERE = Path(__file__).resolve().parent
FILES = ("m6ij_add5.py", "measure_m6ij_add5.sh", "m6ij_add5_selftest.py",
         "m6ij_add5_selftest.sh")
LEAK = "ZQSCREENLEAK7F3D1A9E"
P_VALUE = 0x14
JUDGMENTS = ("first_write_prefixed_by_14_D", "first_write_other_prefix", "inconclusive")
_orig_analyze = a3.analyze


class GateError(ValueError):
    pass


def _count(rows, cpu, kind, port, low, high) -> int:
    return sum(1 for e in rows if e.cpu == cpu and e.kind == kind and e.port == port
               and low < e.clock < high)


def analyze5(rows, arm: str, coords, directory_r: int) -> dict:
    """1走の観測。G1・G3 は追補3の analyze（H1・H3）と exchanges（全単射）を再利用する。"""
    base = _orig_analyze(rows, arm, coords, directory_r)  # exchanges が通らなければ ValueError
    drive = int(arm[3]) - 1
    commands = [c for c in fdc.parse_commands(rows) if c.opcode in (5, 6)]
    # sub 受信の run（間に sub OUT $FB/$FD が無い連続）。1.36節の切り方。
    run_of: dict[int, int] = {}
    members: dict[int, list] = {}
    run_id = 0
    in_run = False
    for e in rows:
        if e.cpu != "sub":
            continue
        if e.kind == "OUT" and e.port in ("00FB", "00FD"):
            in_run = False
        elif e.kind == "IN" and e.port == "00FC":
            if not in_run:
                run_id += 1
                in_run = True
            run_of[e.clock] = run_id
            members.setdefault(run_id, []).append(e)
    incoming = [e for e in rows if e.cpu == "sub" and e.kind == "IN" and e.port == "00FC"]
    first = None
    later = []
    write_index = 0
    for index, c in enumerate(commands):
        if c.opcode != 5:
            continue
        write_index += 1
        before = [e for e in incoming if e.clock < c.clock]
        if len(before) < (263 if write_index == 1 else 262):
            continue
        prev = commands[index - 1] if index else None
        s_event, e11 = before[-262], before[-261]
        if write_index == 1:
            # 最初の WRITE より前に WRITE は無いので、手前の受信は制御だけ（データ部を含まない）。
            if prev is None or any(x.opcode == 5 for x in commands[:index]):
                continue
            p_event = before[-263]
            members_run = members[run_of[p_event.clock]]
            first = {
                "p_is_14": p_event.value == P_VALUE,
                "s_is_d": s_event.value == drive,
                "run_head": members_run[0].value,
                "p_pos_in_run": members_run.index(p_event),
                "run_len": len(members_run),
                "d_read_end_to_p": _count(rows, "sub", "OUT", "00FD", prev.end_clock, p_event.clock)
                if prev.end_clock < p_event.clock else 0,
                "read_end_before_p": prev.end_clock < p_event.clock,
                "d_p_to_11": _count(rows, "sub", "OUT", "00FD", p_event.clock, e11.clock),
                "d_s_to_11": _count(rows, "sub", "OUT", "00FD", s_event.clock, e11.clock),
            }
        else:
            ordered = prev is not None and prev.end_clock < s_event.clock
            later.append({
                "s_is_06": s_event.value == 6,
                "prev_is_write": prev is not None and prev.opcode == 5,
                "prev_end_before_s": ordered,
                "d_s_to_11": _count(rows, "sub", "OUT", "00FD", s_event.clock, e11.clock),
                "d_prev_end_to_s": _count(rows, "sub", "OUT", "00FD", prev.end_clock, s_event.clock)
                if ordered else 0,
            })
    return {"arm": arm, "failed": [x for x in base["failed"] if x in ("H1", "H3")],
            "first_write": first, "later": later}


def _dist(values) -> dict[str, int]:
    return {str(k): v for k, v in sorted(Counter(values).items())}


def assess(runs_by_arm: dict[str, list[dict]], launches: int) -> dict:
    """観測から判定を作る純関数（自己検査と本番で共有）。"""
    g1 = all(not r["failed"] for runs in runs_by_arm.values() for r in runs)
    g2 = all(len(runs) == 2 and runs[0] == runs[1] for runs in runs_by_arm.values())
    g3 = True  # analyze5 が通った時点で load・exchanges は成立している
    all_runs = [r for runs in runs_by_arm.values() for r in runs]
    found = bool(all_runs) and all(r["first_write"] is not None for r in all_runs)
    firsts = [r["first_write"] for r in all_runs if r["first_write"] is not None]
    later = [x for r in all_runs for x in r["later"]]
    prefixed = found and all(f["p_is_14"] and f["s_is_d"] for f in firsts)
    if not (g1 and g2 and g3 and found):
        judgment = "inconclusive"
    else:
        judgment = "first_write_prefixed_by_14_D" if prefixed else "first_write_other_prefix"
    summary = {
        "first_p_is_14": _dist(f["p_is_14"] for f in firsts),
        "first_s_is_d": _dist(f["s_is_d"] for f in firsts),
        "first_run_head": _dist(f["run_head"] for f in firsts),
        "first_p_pos_in_run": _dist(f["p_pos_in_run"] for f in firsts),
        "first_run_len": _dist(f["run_len"] for f in firsts),
        "first_d_read_end_to_p": _dist(f["d_read_end_to_p"] for f in firsts),
        "first_d_p_to_11": _dist(f["d_p_to_11"] for f in firsts),
        "first_d_s_to_11": _dist(f["d_s_to_11"] for f in firsts),
        "later_count": len(later),
        "later_s_is_06": _dist(x["s_is_06"] for x in later),
        "later_prev_is_write": _dist(x["prev_is_write"] for x in later),
        "later_d_s_to_11": _dist(x["d_s_to_11"] for x in later),
        "later_d_prev_end_to_s": _dist(x["d_prev_end_to_s"] for x in later),
    }
    return {"schema": 5, "judgment": judgment, "frontend_launch_count": launches,
            "gates": {"G1": g1, "G2": g2, "G3": g3, "first_write_found": found},
            "summary": summary,
            "observations": {arm: runs[0] for arm, runs in runs_by_arm.items()}}


FIRST_KEYS = {"p_is_14", "s_is_d", "run_head", "p_pos_in_run", "run_len", "d_read_end_to_p",
              "read_end_before_p", "d_p_to_11", "d_s_to_11"}
LATER_KEYS = {"s_is_06", "prev_is_write", "prev_end_before_s", "d_s_to_11", "d_prev_end_to_s"}


def _number(v, hi=1_000_000) -> bool:
    return type(v) is int and 0 <= v <= hi


def audit_result(result: dict) -> None:
    """許可リスト方式。想定外の欄・型・値域はすべて拒否する。"""
    if set(result) != {"schema", "judgment", "frontend_launch_count", "gates", "summary",
                       "observations"} or result["schema"] != 5 or result["judgment"] not in JUDGMENTS:
        raise GateError("output_audit")
    if set(result["gates"]) != {"G1", "G2", "G3", "first_write_found"} or any(
            type(v) is not bool for v in result["gates"].values()):
        raise GateError("output_audit")
    for key, value in result["summary"].items():
        if key == "later_count":
            if not _number(value):
                raise GateError("output_audit")
        elif type(value) is not dict or any(
                not (k in ("True", "False") or (k.isdigit() and int(k) < 1_000_000)) or not _number(v)
                for k, v in value.items()):
            raise GateError("output_audit")
    for arm, obs in result["observations"].items():
        if arm not in a3.ARMS or set(obs) != {"arm", "failed", "first_write", "later"} or obs["arm"] != arm:
            raise GateError("output_audit")
        if any(x not in ("H1", "H3") for x in obs["failed"]):
            raise GateError("output_audit")
        f = obs["first_write"]
        if f is not None:
            if set(f) != FIRST_KEYS or any(type(f[k]) is not bool for k in
                                           ("p_is_14", "s_is_d", "read_end_before_p")):
                raise GateError("output_audit")
            if not _number(f["run_head"], 255) or any(not _number(f[k]) for k in
                    ("p_pos_in_run", "run_len", "d_read_end_to_p", "d_p_to_11", "d_s_to_11")):
                raise GateError("output_audit")
        if type(obs["later"]) is not list:
            raise GateError("output_audit")
        for x in obs["later"]:
            if set(x) != LATER_KEYS or any(type(x[k]) is not bool for k in
                    ("s_is_06", "prev_is_write", "prev_end_before_s")) or any(
                    not _number(x[k]) for k in ("d_s_to_11", "d_prev_end_to_s")):
                raise GateError("output_audit")


def frozen5(path: Path) -> dict[str, str]:
    rows = [line.split("\t") for line in path.read_text(encoding="ascii").splitlines()]
    cfg = dict(rows)
    if any(len(r) != 2 for r in rows) or set(cfg) != {f"{f}_sha256" for f in FILES} or len(cfg) != len(rows):
        raise GateError("G1_frozen")
    for filename in FILES:
        if a3.sha((HERE / filename).read_bytes()) != cfg[f"{filename}_sha256"]:
            raise GateError("G1_frozen")
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path(os.environ.get("PC88_M6IJ_ADD5_WORK", "")))
    ap.add_argument("--arms", help="自己検査専用")
    args = ap.parse_args()
    launches = 0
    test = os.environ.get("M6IJ_ADD5_TEST_MODE") == "1"
    try:
        if str(args.work) in ("", "."):
            raise GateError("work_missing")
        if args.arms and not test:
            raise GateError("arms_test_only")
        arms = a3.ARMS if args.arms is None else tuple(args.arms.split(","))
        if not arms or len(set(arms)) != len(arms) or any(a not in a3.ARMS for a in arms):
            raise GateError("arms_invalid")
        frozen5(Path(os.environ["M6IJ_ADD5_TEST_FROZEN"]) if test and "M6IJ_ADD5_TEST_FROZEN" in os.environ
                else HERE / "m6ij_add5_frozen.tsv")
        a3.preflight(HERE / "m6ij_add3_frozen.tsv", args.work)
        if not test:
            subprocess.run([sys.executable, str(HERE / "m6ij_add5_selftest.py")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        rom = Path(os.environ.get("M6IJ_ADD5_TEST_ROM_DIR" if test else "PC88_REF_ROM_DIR", ""))
        reference_path = (Path(os.environ.get("M6IJ_ADD5_TEST_REFERENCE", "")) if test
                          else Path(os.environ.get("PC88_REF_DISK_DIR", "")) / "N88_FE.D88")
        if not rom.is_dir() or not reference_path.is_file():
            raise GateError("reference_missing")
        reference = reference_path.read_bytes()
        frontend = Path(os.environ.get("M6IJ_ADD5_FRONTEND", HERE / "harness/frontend/q88measure"))
        if not frontend.is_file():
            raise GateError("frontend_missing")
        core = os.environ.get("M6IJ_ADD5_TEST_CORE", "") if test else a3.default_core()
        if not core:
            raise GateError("core_missing")
        a3.analyze = analyze5  # 解析だけを差し替える（腕・打鍵・媒体・走は追補3のまま）
        runs_by_arm: dict[str, list[dict]] = {}
        args.work.mkdir(parents=True)
        with tempfile.TemporaryDirectory(prefix="runs-", dir=args.work) as temp:
            for arm in arms:
                runs_by_arm[arm] = []
                for rep in (1, 2):
                    launches += 1
                    runs_by_arm[arm].append(a3.run_one(arm, rep, Path(temp), frontend, core, rom, reference, test))
        result = assess(runs_by_arm, launches)
        audit_result(result)
        (args.work / "result.json").write_bytes(a3.canonical(result))
        print(json.dumps({"judgment": result["judgment"], "gates": result["gates"],
                          "frontend_launch_count": launches}, separators=(",", ":")))
        return 0
    except (OSError, ValueError, BodyError, fdc.SafeError, screens.SignatureInputError,
            subprocess.CalledProcessError, a3.GateError) as exc:
        reason = str(exc) if isinstance(exc, (GateError, a3.GateError)) else type(exc).__name__
        print(json.dumps({"judgment": "inconclusive", "reason": reason,
                          "frontend_launch_count": launches}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
