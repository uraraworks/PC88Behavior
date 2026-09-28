#!/usr/bin/env python3
"""m6f-j の起動前関門と6腕×2走を実行する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import check_m6fj_disk as disk_check
import compare_screen_signatures as css
import m6fj_judge as judge
import m6fj_read as reader
import m6fj_script as script
from make_m6fj_disk import MEDIA, build

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


class GateError(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def frozen(path: Path) -> dict[str, str]:
    rows = [x.split("\t") for x in path.read_text(encoding="ascii").splitlines()]
    if any(len(row) != 2 for row in rows) or len({row[0] for row in rows}) != len(rows):
        raise GateError("G3")
    return dict(rows)


def preflight(path: Path, work: Path, test_mode: bool = False) -> tuple[dict, dict[str, bytes]]:
    if work.exists():
        raise GateError("G8")
    values = frozen(path)
    doc = script.manifest()
    raw = script.canonical(doc)
    if sha(raw) != values.get("manifest_sha256"):
        raise GateError("G3")
    if sha(judge.candidate_bytes()) != values.get("candidates_sha256"):
        raise GateError("G3")
    if sha((HERE / "m6fj_script.py").read_bytes()) != values.get("script_sha256"):
        raise GateError("G3")
    if sha((HERE / "m6fj_judge.py").read_bytes()) != values.get("judge_sha256"):
        raise GateError("G3")
    if sha((HERE / "m6fj_read.py").read_bytes()) != values.get("reader_sha256"):
        raise GateError("G3")
    script.validate(doc)
    if test_mode and os.environ.get("M6FJ_TEST_UPPERCASE"):
        bad = json.loads(raw)
        bad["arms"][0]["name"] = "QSB"
        try:
            script.validate(bad)
        except ValueError:
            raise GateError("G3") from None
    media = {name: build(name) for name in MEDIA}
    for name, image in media.items():
        if disk_check.inspect(image, name):
            raise GateError("G9")
        if sha(image) != values.get(f"media_{name}_sha256"):
            raise GateError("G3")
    if len({(arm["id"], rep) for arm in doc["arms"] for rep in (1, 2)}) != 12:
        raise GateError("G8")
    return doc, media


def entry_lines(screen: css.ScreenSignature) -> list[dict]:
    # 最終の入力待ち行とファンクションキー行を除く。
    rows = [(row, item) for row, item in sorted(screen.lines.items()) if row != 19]
    if rows:
        rows.pop()
    return [{"physical_row": row, "char_count": item.char_count, "sha256": item.sha256}
            for row, item in rows]


def run_one(arm: str, rep: int, media: bytes, frontend: Path, core: str,
            rom: Path, reference: bytes, stage: Path) -> dict:
    run = stage / f"{arm}-r{rep}"
    run.mkdir()
    drive1, drive2 = run / "drive1.d88", run / "drive2.d88"
    drive1.write_bytes(reference)
    if arm != "J-6":
        drive2.write_bytes(media)
    before = reader.inspect(media, arm)
    report, iolog = run / "signatures.tsv", run / "iolog.txt"
    args = [str(frontend), "--core", core, "--rom-dir", str(rom), "--disk", str(drive1),
            "--save-to-disk-image", "--frames", "8000", "--io-log", str(iolog), "--io-log-from-frame", "650",
            "--screen-signature-only", "--screen-signature-at", "baseline:600",
            "--screen-signature-at", "final:7700", "--screen-signature-at", "late:8000",
            "--out", str(report), "--type-at", "300", "--type", "\\n",
            "--type-at", "700", "--type", script.keystrokes(arm).replace("\n", "\\n")]
    if arm == "J-6":
        insert = run / "insert.d88"
        insert.write_bytes(media)
        args.extend(["--expect-disk2-empty", "--insert-disk2", str(insert),
                     "--insert-disk2-at", "1200", "--screen-signature-at", "preinsert:1100"])
        drive2 = insert
    else:
        args.extend(["--disk2", str(drive2)])
    try:
        proc = subprocess.run(args, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise GateError("run_timeout") from None
    if proc.returncode or not report.is_file() or not iolog.is_file():
        raise GateError("run_failed")
    if drive1.read_bytes() != reference:
        raise GateError("G5")
    baseline = css.read_report(report, "baseline")
    final = css.read_report(report, "final")
    late = css.read_report(report, "late")
    if not any(row != 19 for row in final.lines):
        raise GateError("G5")
    if baseline.lines.get(19) != final.lines.get(19) or final != late:
        raise GateError("G5")
    after = reader.inspect(drive2.read_bytes(), arm)
    if after["g8_max_position"] > 159:
        raise GateError("G8")
    if arm in ("J-1", "J-2"):
        target = next((entry for entry in after["entries"] if entry["name"] == script.NAMES[arm]), None)
        if target is not None and target["bytes9_15"][0] != 0:
            raise GateError("G6")
        if after.get("body_read_max_position", -1) > after.get("body_read_limit", len(script.body(arm))):
            raise GateError("G7")
    final_lines = entry_lines(final)
    pre_lines = entry_lines(css.read_report(report, "preinsert")) if arm == "J-6" else None
    observation = judge.classify(arm, before, after, final_lines, pre_lines)
    observation["screen_lines"] = final_lines
    observation["screen_sha256"] = final.sha256
    if pre_lines is not None:
        observation["preinsert_screen_lines"] = pre_lines
    observation["entries"] = after["entries"]
    observation["g8_max_position"] = after["g8_max_position"]
    return observation


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path(os.environ.get("PC88_M6FJ_WORK", "")))
    ap.add_argument("--result", type=Path, default=Path(os.environ["PC88_M6FJ_RESULT"])
                    if os.environ.get("PC88_M6FJ_RESULT") else None)
    ap.add_argument("--keep-images", action="store_true")
    args = ap.parse_args()
    launches = 0
    test = os.environ.get("M6FJ_TEST_MODE") == "1"
    config = Path(os.environ.get("M6FJ_TEST_FROZEN", HERE / "m6fj_frozen.tsv")) if test else HERE / "m6fj_frozen.tsv"
    try:
        if str(args.work) in ("", "."):
            raise GateError("work_missing")
        result = args.result or args.work / "result.json"
        if result.exists():
            raise GateError("result_exists")
        doc, media = preflight(config, args.work, test)
        if not test:
            # G1: 起動より前に合成検査を実行する。
            subprocess.run(["bash", str(HERE / "make_m6fc_blank_disk_selftest.sh")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            subprocess.run([sys.executable, str(HERE / "m6fj_selftest.py"), "--preflight"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        rom = Path(os.environ.get("M6FJ_TEST_ROM_DIR" if test else "PC88_REF_ROM_DIR", ""))
        ref_dir = Path(os.environ.get("M6FJ_TEST_DISK_DIR" if test else "PC88_REF_DISK_DIR", ""))
        if not rom.is_dir() or not ref_dir.is_dir():
            raise GateError("reference_missing")
        reference = (ref_dir / "N88_FE.D88").read_bytes()
        frontend = Path(os.environ.get("M6FJ_FRONTEND", HERE / "harness/frontend/q88measure"))
        if not frontend.is_file():
            raise GateError("frontend_missing")
        core = os.environ.get("M6FJ_TEST_CORE", "") if test else os.environ.get("M6FJ_CORE", "")
        if not core:
            raise GateError("core_missing")
        arms = {}
        with tempfile.TemporaryDirectory(prefix="m6fj-") as temp:
            stage = Path(temp)
            for arm in script.ARMS:
                runs = []
                for rep in (1, 2):
                    launches += 1
                    runs.append(run_one(arm, rep, media[script.MEDIA[arm]], frontend, core,
                                        rom, reference, stage))
                if runs[0] != runs[1]:
                    raise GateError("G5")
                arms[arm] = runs
            if (ref_dir / "N88_FE.D88").read_bytes() != reference:
                raise GateError("G5")
            if args.keep_images:
                args.work.mkdir(parents=True)
                for path in stage.glob("*/drive2.d88"):
                    shutil.copyfile(path, args.work / (path.parent.name + ".d88"))
        derived = judge.combine(arms)
        args.work.mkdir(parents=True, exist_ok=True)
        result.parent.mkdir(parents=True, exist_ok=True)
        with result.open("x", encoding="ascii") as out:
            json.dump({"schema": 1, "frontend_launch_count": launches, "observations": arms,
                       "judgment": derived}, out, sort_keys=True, separators=(",", ":"))
            out.write("\n")
        print(json.dumps({"judgment": derived["overall"], "frontend_launch_count": launches},
                         separators=(",", ":")))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, css.SignatureInputError) as exc:
        reason = str(exc) if isinstance(exc, GateError) else type(exc).__name__
        print(json.dumps({"judgment": "gate_failed", "reason": reason,
                          "frontend_launch_count": launches}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
