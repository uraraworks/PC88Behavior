#!/usr/bin/env python3
"""m6f-k の起動前関門と10腕×2走を実行する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import check_m6fk_disk as disk_check
import compare_screen_signatures as css
import m6fk_judge as judge
import m6fk_read as reader
import m6fk_script as script
from check_l3_entry_screen import reached_signature_prompt
from make_m6fk_disk import MEDIA, build

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FROZEN_FILES = ("m6fk_script.py", "m6fk_judge.py", "m6fk_read.py", "m6fk_measure.py",
                "make_m6fk_disk.py", "check_m6fk_disk.py", "m6fk_selftest.py",
                "m6fk_selftest.sh", "measure_m6fk.sh", "check_l3_entry_screen.py")


class GateError(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def default_core(repo: Path = ROOT) -> str:
    # 共通ライブラリの探索規則をそのまま使う。
    proc = subprocess.run(
        ["bash", "-c", 'REPO="$1"; source "$REPO/tools/lib_l3_measure.sh"; find_l3_core',
         "m6fk", str(repo)], capture_output=True, text=True, check=True)
    return proc.stdout.strip()


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
    for name in FROZEN_FILES:
        if sha((HERE / name).read_bytes()) != values.get(f"file_{name}_sha256"):
            raise GateError("G3")
    script.validate(doc)
    if test_mode and os.environ.get("M6FK_TEST_UPPERCASE"):
        bad = json.loads(raw)
        bad["arms"][0]["command"] = bad["arms"][0]["command"].upper()
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
    if len({(arm["id"], rep) for arm in doc["arms"] for rep in (1, 2)}) != 20:
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
    drive2.write_bytes(media)
    report, iolog = run / "signatures.tsv", run / "iolog.txt"
    args = [str(frontend), "--core", core, "--rom-dir", str(rom), "--disk", str(drive1),
            "--disk2", str(drive2), "--save-to-disk-image", "--frames", str(script.FRAMES[arm]),
            "--io-log", str(iolog), "--io-log-from-frame", "650",
            "--screen-signature-only", "--screen-signature-at", "baseline:600",
            "--screen-signature-at", "final:7700", "--screen-signature-at", "late:8000",
            "--screen-signature-at", "ready:8600",
            "--out", str(report), "--type-at", "300", "--type", "\\n",
            "--type-at", "700", "--type", script.keystrokes(arm).replace("\n", "\\n"),
            "--type-at", "8100", "--type", script.READY_COMMAND + "\\n"]
    try:
        proc = subprocess.run(args, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise GateError("run_timeout") from None
    if proc.returncode or not report.is_file() or not iolog.is_file():
        raise GateError("run_failed")
    baseline = css.read_report(report, "baseline")
    final = css.read_report(report, "final")
    late = css.read_report(report, "late")
    if not any(row != 19 for row in final.lines):
        raise GateError("G5")
    if baseline.lines.get(19) != final.lines.get(19) or final != late:
        raise GateError("G5")
    if not reached_signature_prompt(report, script.READY_COMMAND):
        raise GateError("G11")
    # G11通過まで測定後媒体には触れない。
    if drive1.read_bytes() != reference:
        raise GateError("G5")
    before, after, changes = reader.compare(media, drive2.read_bytes(), arm)
    if after["g8_max_position"] > 159:
        raise GateError("G8")
    final_lines = entry_lines(final)
    observation = judge.classify(arm, before, after, final_lines, changes)
    observation.update(reader.safe_result(before, after, changes))
    observation["screen_lines"] = final_lines
    observation["screen_sha256"] = final.sha256
    observation["g11_input_ready"] = True

    return observation


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path(os.environ.get("PC88_M6FK_WORK", "")))
    ap.add_argument("--result", type=Path, default=Path(os.environ["PC88_M6FK_RESULT"])
                    if os.environ.get("PC88_M6FK_RESULT") else None)
    ap.add_argument("--arms", help="実行する腕ID（例: K-1,N-1）")
    args = ap.parse_args()
    launches = 0
    test = os.environ.get("M6FK_TEST_MODE") == "1"
    config = Path(os.environ.get("M6FK_TEST_FROZEN", HERE / "m6fk_frozen.tsv")) if test else HERE / "m6fk_frozen.tsv"
    try:
        selected = script.ARMS if args.arms is None else tuple(args.arms.split(","))
        if not selected or len(selected) != len(set(selected)) or any(arm not in script.ARMS for arm in selected):
            raise GateError("arms_invalid")
        if str(args.work) in ("", "."):
            raise GateError("work_missing")
        result = args.result or args.work / "result.json"
        if args.work.resolve().is_relative_to(ROOT) or result.resolve().is_relative_to(ROOT):
            raise GateError("output_inside_repository")
        if result.exists():
            raise GateError("result_exists")
        doc, media = preflight(config, args.work, test)
        if not test:
            # G1: 起動より前に合成検査を実行する。
            subprocess.run(["bash", str(HERE / "make_m6fc_blank_disk_selftest.sh")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            subprocess.run([sys.executable, str(HERE / "m6fk_selftest.py"), "--preflight"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        rom = Path(os.environ.get("M6FK_TEST_ROM_DIR" if test else "PC88_REF_ROM_DIR", ""))
        ref_dir = Path(os.environ.get("M6FK_TEST_DISK_DIR" if test else "PC88_REF_DISK_DIR", ""))
        if not rom.is_dir() or not ref_dir.is_dir():
            raise GateError("reference_missing")
        reference = (ref_dir / "N88_FE.D88").read_bytes()
        frontend = Path(os.environ.get("M6FK_FRONTEND", HERE / "harness/frontend/q88measure"))
        if not frontend.is_file():
            raise GateError("frontend_missing")
        core = os.environ.get("M6FK_TEST_CORE", "") if test else os.environ.get("M6FK_CORE", "")
        if not core:
            core = default_core()
        if not core:
            raise GateError("core_missing")
        arms = {}
        with tempfile.TemporaryDirectory(prefix="m6fk-") as temp:
            stage = Path(temp)
            for arm in selected:
                runs = []
                for rep in (1, 2):
                    launches += 1
                    runs.append(run_one(arm, rep, media[script.MEDIA[arm]], frontend, core,
                                        rom, reference, stage))
                arms[arm] = runs
            if (ref_dir / "N88_FE.D88").read_bytes() != reference:
                raise GateError("G5")
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
