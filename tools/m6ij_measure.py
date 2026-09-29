#!/usr/bin/env python3
"""m6i-j: G0〜G4を起動前に、各走の関門を保存前に検査する。"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import analyze_m6ij as analyzer
import check_m6ij_after as aftercheck
import check_m6ij_disk as diskcheck
import compare_screen_signatures as screens
import m6ij_script as script
from make_m6ij_disk import build
from m6fh_body import BodyError, Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


class GateError(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def frozen(path: Path) -> dict[str, str]:
    rows = [x.split("\t") for x in path.read_text(encoding="ascii").splitlines()]
    if any(len(row) != 2 for row in rows) or len({r[0] for r in rows}) != len(rows):
        raise GateError("G1")
    return dict(rows)


def g0() -> None:
    files = ("m6ij_script.py", "make_m6ij_disk.py", "check_m6ij_disk.py",
             "check_m6ij_after.py", "analyze_m6ij.py", "m6ij_measure.py")
    forbidden = ("make_n88_blank" + "_disk", "vendor", "private", "m7eb", "image.c")
    for filename in files:
        tree = ast.parse((HERE / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [x.name for x in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(any(bad in name for bad in forbidden) for name in names):
                raise GateError("G0")


def preflight(config: Path, work: Path) -> tuple[dict, dict[tuple[str, str], bytes]]:
    if work.exists():
        raise GateError("work_exists")
    g0()
    cfg = frozen(config)
    manifest = script.manifest()
    if sha(script.canonical(manifest)) != cfg.get("manifest_sha256"):
        raise GateError("G1")
    for filename in ("m6ij_script.py", "make_m6ij_disk.py", "analyze_m6ij.py",
                     "check_m6ij_disk.py", "check_m6ij_after.py", "m6ij_measure.py"):
        if sha((HERE / filename).read_bytes()) != cfg.get(filename + "_sha256"):
            raise GateError("G1")
    if len(script.AXES)**4 != 625 or tuple(manifest["axes"]) != script.AXES:
        raise GateError("G1")
    media = {}
    for arm in script.ARMS:
        body = script.body(arm)
        if diskcheck.check_body(arm, body):
            raise GateError("G2_body")
        if sha(body) != cfg.get(f"body_{arm}_sha256"):
            raise GateError("G1")
        for kind in ("B0", "B1"):
            data = build(kind, arm)
            if diskcheck.inspect(data, kind, arm):
                raise GateError("G2_disk")
            if sha(data) != cfg.get(f"media_{arm}_{kind}_sha256"):
                raise GateError("G1")
            media[arm, kind] = data
    if len({(arm, rep) for arm in script.ARMS for rep in (1, 2)}) != 16:
        raise GateError("G4")
    return manifest, media


def default_core() -> str:
    proc = subprocess.run(["bash", "-c", 'REPO="$1"; source "$REPO/tools/lib_l3_measure.sh"; find_l3_core',
                           "m6ij", str(ROOT)], capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def allowed_media_diff(before: bytes, after: bytes, arm: str) -> bool:
    a, b = Image(before), Image(after)
    if set(a.sectors) != set(b.sectors):
        return False
    valid_body = len(script.body(arm))
    for coord in a.sectors:
        kind = analyzer.location(coord)
        if kind == "fat":
            aa, bb = bytes(a.sector_prefix(coord, 160)), bytes(b.sector_prefix(coord, 160))
        elif kind == "directory":
            aa, bb = bytes(a.sector(*coord)), bytes(b.sector(*coord))
        elif kind == "body":
            linear = coord[0]*32 + coord[1]*16 + coord[2]-1
            if 72*8 <= linear < 72*8+8:
                idx = linear-72*8
            elif 71*8 <= linear < 71*8+8:  # l3-disk-format 2.5節: 72 から番号の小さい方へ（m6i-j 6回目で 72→71 を確認）
                idx = 8+linear-71*8
            else:
                idx = -1
            if 0 <= idx < (valid_body+255)//256:
                limit = min(256, valid_body-idx*256)
                aa, bb = bytes(a.sector_prefix(coord, limit)), bytes(b.sector_prefix(coord, limit))
            else:
                aa, bb = bytes(a.sector(*coord)), bytes(b.sector(*coord))
        else:
            aa, bb = bytes(a.sector(*coord)), bytes(b.sector(*coord))
        if aa != bb and kind not in ("fat", "directory", "body"):
            return False
        if aa != bb and kind == "body" and not (0 <= idx < (valid_body+255)//256):
            return False
    return True


def audit_result(value: dict) -> None:
    if set(value) != {"schema", "judgment", "unread_send_judgment", "frontend_launch_count", "candidates", "observations"}:
        raise GateError("output_audit")
    if value["judgment"] not in script.JUDGMENTS or value["schema"] != 1:
        raise GateError("output_audit")
    if value["unread_send_judgment"] not in ("unread_send_rule_unique", "inconclusive_unread_send"):
        raise GateError("output_audit")
    if set(value["candidates"]) != {"0", "1", "2", "3"} or any(
        any(candidate not in script.AXES for candidate in values)
        for values in value["candidates"].values()):
        raise GateError("output_audit")
    for arm, obs in value["observations"].items():
        if arm not in script.ARMS or set(obs) != {"arm", "send_runs", "sub_receive_count",
                                                 "unread_send_count", "unread_send", "writes", "order"}:
            raise GateError("output_audit")
        if obs["unread_send_count"] != len(obs["unread_send"]):
            raise GateError("output_audit")
        for item in obs["unread_send"]:
            if set(item) not in ({"position", "classification", "gap_length", "previous", "next"},
                                 {"position", "classification", "gap_length", "previous", "next", "control_value"}):
                raise GateError("output_audit")
            if type(item["position"]) is not int or item["position"] < 1 or item["classification"] not in (
                    "inside_data", "between_control", "boundary"):
                raise GateError("output_audit")
            if type(item["gap_length"]) is not int or item["gap_length"] < 1:
                raise GateError("output_audit")
            if ("control_value" in item) != (item["classification"] == "between_control"):
                raise GateError("output_audit")
            if "control_value" in item and (type(item["control_value"]) is not int or not 0 <= item["control_value"] <= 255):
                raise GateError("output_audit")
            for side in ("previous", "next"):
                neighbor = item[side]
                if neighbor is None:
                    continue
                if set(neighbor) not in ({"position", "classification"},
                                         {"position", "classification", "control_value"}):
                    raise GateError("output_audit")
                if type(neighbor["position"]) is not int or neighbor["position"] < 1 or neighbor["classification"] not in (
                        "control", "data", "other"):
                    raise GateError("output_audit")
                if ("control_value" in neighbor) != (neighbor["classification"] == "control"):
                    raise GateError("output_audit")
                if "control_value" in neighbor and (type(neighbor["control_value"]) is not int or not 0 <= neighbor["control_value"] <= 255):
                    raise GateError("output_audit")
        if any(not set(run) <= {"length", "first_control"} for run in obs["send_runs"]):
            raise GateError("output_audit")
        if any(set(write) != {"control", "drive", "track", "r", "coord", "location",
                              "data_match_count", "body_index", "response_count", "count_order"}
               for write in obs["writes"]):
            raise GateError("output_audit")
        if any(set(row) != {"direction", "drive", "coord", "location", "main_send_lengths",
                            "first_control", "fdc_result_count"} for row in obs["order"]):
            raise GateError("output_audit")


def run_one(arm: str, rep: int, media: bytes, frontend: Path, core: str,
            rom: Path, reference: bytes, stage: Path) -> dict:
    run = stage / f"{arm}-r{rep}"
    run.mkdir()
    refpath, target = run / "reference.d88", run / "target.d88"
    refpath.write_bytes(reference)
    refpath.chmod(0o444)
    target.write_bytes(media)
    report, log = run / "signatures.tsv", run / "events.iolog.txt"
    end_frame = script.TYPE_FRAME + 8*len(script.keys(arm))
    if script.SWAP_FRAME >= script.TYPE_FRAME or end_frame >= script.FRAMES-500:
        raise GateError("G4")
    args = [str(frontend), "--core", core, "--rom-dir", str(rom),
            "--disk", str(refpath), "--save-to-disk-image",
            "--frames", str(script.FRAMES), "--io-log", str(log),
            "--io-log-from-frame", str(script.TYPE_FRAME),
            "--screen-signature-only", "--screen-signature-at", "baseline:1100",
            "--screen-signature-at", f"final:{script.FRAMES-500}",
            "--screen-signature-at", f"late:{script.FRAMES-1}",
            "--out", str(report), "--type-at", "300", "--type", "\\n",
            "--type-at", str(script.TYPE_FRAME), "--type", script.keys(arm).replace("\n", "\\n")]
    if arm.startswith("J-D1"):
        args += ["--swap-disk1", str(target), "--swap-disk1-at", str(script.SWAP_FRAME)]
    else:
        args += ["--disk2", str(target)]
    env = dict(os.environ, M6FH_LONG_TYPING="1")
    try:
        proc = subprocess.run(args, capture_output=True, timeout=900, env=env)
    except subprocess.TimeoutExpired:
        raise GateError("run_timeout") from None
    if proc.returncode or not report.is_file() or not log.is_file():
        raise GateError("frontend")
    if arm.startswith("J-D1"):
        expected_event = (f"event\tswap_disk1\tframe={script.SWAP_FRAME}\tsuccess=1").encode()
        if expected_event not in proc.stderr or str(target).encode() not in proc.stderr:
            raise GateError("G4_swap")
    if sha(refpath.read_bytes()) != sha(reference):
        raise GateError("reference_changed")
    if not allowed_media_diff(media, target.read_bytes(), arm):
        raise GateError("media_diff")
    if not aftercheck.inspect(target.read_bytes(), arm,
                              "B1" if arm.endswith("-O") else "B0"):
        raise GateError("saved_body")
    baseline = screens.read_report(report, "baseline")
    final = screens.read_report(report, "final")
    late = screens.read_report(report, "late")
    if final != late or baseline.lines.get(19) != final.lines.get(19):
        raise GateError("screen_completion")
    result = analyzer.analyze(analyzer.load(log), arm)
    if any(row["drive"] != int(arm[3]) for row in result["order"]):
        raise GateError("drive")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path(os.environ.get("PC88_M6IJ_WORK", "")))
    ap.add_argument("--result", type=Path)
    ap.add_argument("--arms", help="自己検査用の腕選択")
    args = ap.parse_args()
    launches = 0
    test = os.environ.get("M6IJ_TEST_MODE") == "1"
    try:
        if str(args.work) in ("", "."):
            raise GateError("work_missing")
        if args.arms and not test:
            raise GateError("arms_test_only")
        arms = script.ARMS if not args.arms else tuple(args.arms.split(","))
        if not arms or len(set(arms)) != len(arms) or any(a not in script.ARMS for a in arms):
            raise GateError("arms_invalid")
        resultpath = args.result or args.work / "result.json"
        if resultpath.exists():
            raise GateError("result_exists")
        if resultpath.parent.resolve() != args.work.resolve():
            raise GateError("result_outside_work")
        config = Path(os.environ.get("M6IJ_TEST_FROZEN", HERE / "m6ij_frozen.tsv")) if test else HERE / "m6ij_frozen.tsv"
        manifest, media = preflight(config, args.work)
        if not test:
            subprocess.run([sys.executable, str(HERE / "m6ij_selftest.py"), "--preflight"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        rom = Path(os.environ.get("M6IJ_TEST_ROM_DIR" if test else "PC88_REF_ROM_DIR", ""))
        reference_path = Path(os.environ.get("M6IJ_TEST_REFERENCE", "")) if test else (
            Path(os.environ.get("PC88_REF_DISK_DIR", "")) / "N88_FE.D88")
        if not rom.is_dir() or not reference_path.is_file():
            raise GateError("reference_missing")
        reference = reference_path.read_bytes()
        frontend = Path(os.environ.get("M6IJ_FRONTEND", HERE / "harness/frontend/q88measure"))
        if not frontend.is_file():
            raise GateError("frontend_missing")
        core = os.environ.get("M6IJ_TEST_CORE", "") if test else default_core()
        if not core:
            raise GateError("core_missing")
        observations = {}
        with tempfile.TemporaryDirectory(prefix="m6ij-") as temp:
            stage = Path(temp)
            for arm in arms:
                runs = []
                kind = "B1" if arm.endswith("-O") else "B0"
                for rep in (1, 2):
                    launches += 1
                    runs.append(run_one(arm, rep, media[arm, kind], frontend,
                                        core, rom, reference, stage))
                if runs[0] != runs[1]:
                    raise GateError("repeat_mismatch")
                observations[arm] = runs[0]
        candidates = analyzer.axis_values({a: x["writes"] for a, x in observations.items()})
        verdict = (analyzer.judgment(candidates) if len(arms) == 8 else "inconclusive_axis_confounded")
        if verdict == "m6i_j_main_write_send_unique" and analyzer.confounded(
                {a: x["writes"] for a, x in observations.items()}, candidates):
            verdict = "inconclusive_axis_confounded"
        result = {"schema": 1, "judgment": verdict,
                  "unread_send_judgment": analyzer.unread_judgment(observations),
                  "frontend_launch_count": launches,
                  "candidates": candidates, "observations": observations}
        audit_result(result)
        args.work.mkdir(parents=True)
        resultpath.parent.mkdir(parents=True, exist_ok=True)
        resultpath.write_bytes(script.canonical(result))
        print(json.dumps({"judgment": verdict, "frontend_launch_count": launches}, separators=(",", ":")))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, screens.SignatureInputError,
            BodyError) as exc:
        reason = str(exc) if isinstance(exc, (GateError, analyzer.GateError)) else type(exc).__name__
        print(json.dumps({"judgment": "gate_failed", "reason": reason,
                          "frontend_launch_count": launches}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
