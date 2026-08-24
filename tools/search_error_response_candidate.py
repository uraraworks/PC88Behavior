#!/usr/bin/env python3
"""unreadable_disk の1バイト・エラー応答候補を乱順並列探索する。

公式側から保持するのは交換runの方向/長さ、FDCコマンド名列、画面の
行数・文字数・SHA-256だけである。交換値、FDC生値、画面本文は結果へ
保存しない。候補と結果の対応は全走完了後のsummary.tsvで初めて表示する。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import re
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import analyze_error_exchange_shape as shape  # noqa: E402
import check_l3_screen_output as screen  # noqa: E402


@dataclass(frozen=True)
class AbstractResult:
    exchange: tuple[tuple[str, int], ...]
    fdc: tuple[str, ...]
    screen_line_count: int
    screen_char_count: int
    screen_sha256: str


@dataclass(frozen=True)
class CandidateMetrics:
    ordinal: int
    exchange_prefix: int
    exchange_exact: bool
    fdc_prefix: int
    fdc_exact: bool
    screen_lines_match: bool
    screen_chars_match: bool
    screen_sha256_match: bool
    screen_line_count: int
    screen_char_count: int
    screen_sha256: str
    elapsed_seconds: float


class SearchError(RuntimeError):
    pass


def common_prefix(a: tuple, b: tuple) -> int:
    for pos, (left, right) in enumerate(zip(a, b)):
        if left != right:
            return pos
    return min(len(a), len(b))


def compare_result(reference: AbstractResult, actual: AbstractResult,
                   ordinal: int, elapsed: float = 0.0) -> CandidateMetrics:
    exchange_prefix = common_prefix(reference.exchange, actual.exchange)
    fdc_prefix = common_prefix(reference.fdc, actual.fdc)
    return CandidateMetrics(
        ordinal=ordinal,
        exchange_prefix=exchange_prefix,
        exchange_exact=reference.exchange == actual.exchange,
        fdc_prefix=fdc_prefix,
        fdc_exact=reference.fdc == actual.fdc,
        screen_lines_match=reference.screen_line_count == actual.screen_line_count,
        screen_chars_match=reference.screen_char_count == actual.screen_char_count,
        screen_sha256_match=reference.screen_sha256 == actual.screen_sha256,
        screen_line_count=actual.screen_line_count,
        screen_char_count=actual.screen_char_count,
        screen_sha256=actual.screen_sha256,
        elapsed_seconds=round(elapsed, 3),
    )


def metric_vector(metric: CandidateMetrics) -> tuple:
    return (
        metric.exchange_prefix, metric.exchange_exact,
        metric.fdc_prefix, metric.fdc_exact,
        metric.screen_lines_match, metric.screen_chars_match,
        metric.screen_sha256_match, metric.screen_line_count,
        metric.screen_char_count, metric.screen_sha256,
    )


def exact_match(metric: CandidateMetrics) -> bool:
    return (metric.exchange_exact and metric.fdc_exact
            and metric.screen_lines_match and metric.screen_chars_match
            and metric.screen_sha256_match)


def rank(metric: CandidateMetrics) -> tuple[int, int, int]:
    screen_matches = sum((metric.screen_lines_match, metric.screen_chars_match,
                          metric.screen_sha256_match))
    return metric.exchange_prefix, metric.fdc_prefix, screen_matches


def classify_results(metrics: list[CandidateMetrics]) -> tuple[str, list[int]]:
    """found/not_found/insensitive と最良ordinal列を返す。"""
    if not metrics:
        return "not_found", []
    if len(metrics) >= 2 and len({metric_vector(m) for m in metrics}) == 1:
        return "insensitive", []
    found = [m.ordinal for m in metrics if exact_match(m)]
    if found:
        return "found", found
    best_rank = max(rank(m) for m in metrics)
    return "not_found", [m.ordinal for m in metrics if rank(m) == best_rank]


def abstract_result(iolog: Path, report: Path) -> AbstractResult:
    runs = shape.exchange_runs(iolog)
    fdcs = shape.fdc_shapes(iolog)
    sig = screen.signature(screen.read_screen(report))
    return AbstractResult(
        exchange=tuple((run.direction, run.length) for run in runs),
        fdc=tuple(command.name for command in fdcs),
        screen_line_count=sig.line_count,
        screen_char_count=sig.char_count,
        screen_sha256=sig.sha256,
    )


def result_to_json(result: AbstractResult) -> dict:
    value = asdict(result)
    value["exchange"] = [list(item) for item in result.exchange]
    value["fdc"] = list(result.fdc)
    return value


def result_from_json(value: dict) -> AbstractResult:
    return AbstractResult(
        exchange=tuple((str(item[0]), int(item[1])) for item in value["exchange"]),
        fdc=tuple(str(item) for item in value["fdc"]),
        screen_line_count=int(value["screen_line_count"]),
        screen_char_count=int(value["screen_char_count"]),
        screen_sha256=str(value["screen_sha256"]),
    )


def copy_roms(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    copied = 0
    for path in source.glob("*.ROM"):
        if path.is_file():
            shutil.copy2(path, destination / path.name)
            copied += 1
    if not copied:
        raise SearchError("ROMディレクトリに*.ROMが無い")


def discover_core() -> Path:
    vendor = REPO.parent / "vendor" / "quasi88-libretro"
    found = sorted(vendor.glob("quasi88_libretro.*"))
    if not found:
        raise SearchError("コアが無い。先にtools/setup_harness.shを実行する")
    return found[0]


def check_external_state_dir(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO)
    except ValueError:
        pass
    else:
        raise SearchError("生ログを一時作成するため--state-dirはリポジトリ外を指定する")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def run_frontend(command: list[str], iolog: Path, timeout: int) -> None:
    stderr = iolog.with_suffix(".stderr.txt")
    for attempt in range(1, 5):
        iolog.unlink(missing_ok=True)
        try:
            with stderr.open("a", encoding="utf-8") as err:
                completed = subprocess.run(command, stdout=subprocess.DEVNULL,
                                           stderr=err, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise SearchError(f"q88measureが{timeout}秒でタイムアウト") from exc
        if completed.returncode == 0:
            break
        if attempt == 4:
            raise SearchError("q88measureが4回とも失敗")
    if not iolog.is_file():
        raise SearchError("I/Oログが生成されなかった")
    with iolog.open("r", encoding="utf-8", errors="strict") as fp:
        if any(re.match(r"^# 取りこぼし: [1-9][0-9]*件", line) for line in fp):
            raise SearchError("I/Oログに取りこぼしがある")


def measure_once(*, official: bool, candidate: int | None, frames: int,
                 timeout: int, state_dir: Path, tag: str, rom_source: Path,
                 disk_source: Path, core: Path, frontend: Path,
                 break_error_response_bit6: bool = False) -> AbstractResult:
    """独立ROM・媒体・作業ディレクトリで1走し、値なし結果だけ返す。"""
    run_dir = state_dir / "runs" / tag
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    rom_dir = run_dir / "rom"
    copy_roms(rom_source, rom_dir)
    if not official:
        generator = [sys.executable, str(REPO / "src/l3_service/make_subrom.py"),
                     str(rom_dir)]
        if candidate is not None:
            generator += ["--error-response-candidate", str(candidate)]
        if break_error_response_bit6:
            generator += ["--break-error-response-bit6"]
        subprocess.run(generator, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, check=True)

    disk_a = run_dir / "a.d88"
    disk_b = run_dir / "b.d88"
    shutil.copy2(disk_source, disk_a)
    subprocess.run([sys.executable, str(REPO / "tools/make_l3_testdisk.py"),
                    str(disk_b)], stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE, check=True)
    playlist = run_dir / "media.m3u"
    playlist.write_text(f"{disk_a}\n{disk_b}\n", encoding="utf-8")
    iolog = run_dir / "run.iolog.txt"
    report = run_dir / "run.report.txt"
    command = [
        str(frontend), "--core", str(core), "--rom-dir", str(rom_dir),
        "--disk", str(playlist), "--frames", str(frames),
        "--io-log", str(iolog), "--out", str(report),
        "--type-at", "300", "--type", r"\n",
        "--type-at", "700", "--type", r"FILES 2\n",
    ]
    try:
        run_frontend(command, iolog, timeout)
        return abstract_result(iolog, report)
    finally:
        # 公式値や画面本文を含み得る生ファイルは再開状態へ残さない。
        shutil.rmtree(run_dir, ignore_errors=True)


def calibration_gate(official_log: Path, mixed_log: Path) -> None:
    official_runs = shape.exchange_runs(official_log)
    mixed_runs = shape.exchange_runs(mixed_log)
    prefix = shape.structural_prefix(official_runs, mixed_runs)
    official_fdc = shape.fdc_shapes(official_log)
    mixed_fdc = shape.fdc_shapes(mixed_log)
    divergence = shape.fdc_divergence(official_fdc, mixed_fdc)
    axis_off = shape.request_axis(official_runs, official_fdc[divergence].clock)
    axis_mix = shape.request_axis(mixed_runs, mixed_fdc[divergence].clock)
    try:
        off = official_runs[axis_off + 6]
        mix = mixed_runs[axis_mix + 6]
    except IndexError as exc:
        raise SearchError("短縮窓が+6まで届かず、妥当性を確認できない") from exc
    expected = (off.direction == "main→sub" and off.length == 6
                and mix.direction == "main→sub" and mix.length == 2)
    if prefix != 38 or not expected:
        raise SearchError(
            f"短縮窓の関門不成立（構造prefix={prefix}、+6既知差={expected}）")


def calibration_measure(args: argparse.Namespace, official: bool,
                        tag: str) -> tuple[AbstractResult, Path, Path, Path]:
    """関門用に生ログを一時保持するmeasure_once相当。"""
    run_dir = args.state_dir / "runs" / tag
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    rom_dir = run_dir / "rom"
    copy_roms(args.rom_source, rom_dir)
    if not official:
        subprocess.run([sys.executable, str(REPO / "src/l3_service/make_subrom.py"),
                        str(rom_dir)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, check=True)
    disk_a, disk_b = run_dir / "a.d88", run_dir / "b.d88"
    shutil.copy2(args.disk_source, disk_a)
    subprocess.run([sys.executable, str(REPO / "tools/make_l3_testdisk.py"), str(disk_b)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    playlist = run_dir / "media.m3u"
    playlist.write_text(f"{disk_a}\n{disk_b}\n", encoding="utf-8")
    iolog, report = run_dir / "run.iolog.txt", run_dir / "run.report.txt"
    command = [str(args.frontend), "--core", str(args.core), "--rom-dir", str(rom_dir),
               "--disk", str(playlist), "--frames", str(args.frames),
               "--io-log", str(iolog), "--out", str(report),
               "--type-at", "300", "--type", r"\n",
               "--type-at", "700", "--type", r"FILES 2\n"]
    run_frontend(command, iolog, args.timeout)
    return abstract_result(iolog, report), run_dir, iolog, report


def prepare_args(args: argparse.Namespace) -> None:
    if os.environ.get("PC88_ERROR_RESPONSE_OPT_IN") != "1":
        raise SearchError("実測にはPC88_ERROR_RESPONSE_OPT_IN=1が必要")
    rom_env = os.environ.get("PC88_REF_ROM_DIR")
    disk_env = os.environ.get("PC88_REF_DISK_DIR")
    if not rom_env or not disk_env:
        raise SearchError("PC88_REF_ROM_DIR / PC88_REF_DISK_DIRが未設定")
    args.rom_source = Path(rom_env)
    args.disk_source = Path(disk_env) / "N88_FE.D88"
    if not args.disk_source.is_file():
        raise SearchError("参照媒体が無い")
    args.state_dir = check_external_state_dir(args.state_dir)
    args.core = args.core.resolve() if args.core else discover_core()
    args.frontend = (args.frontend or REPO / "tools/harness/frontend/q88measure").resolve()
    if not args.frontend.is_file():
        raise SearchError("q88measureが無い。先にtools/setup_harness.shを実行する")


def calibrate(args: argparse.Namespace) -> int:
    prepare_args(args)
    if ((args.state_dir / "progress.jsonl").exists()
            or (args.state_dir / "candidate-order.json").exists()):
        raise SearchError("探索開始済みのstate-dirへcalibrationを上書きできない")
    started = time.monotonic()
    paths: list[Path] = []
    try:
        official, off_dir, off_log, _ = calibration_measure(args, True, "cal-official")
        paths.append(off_dir)
        mixed, mix_dir, mix_log, _ = calibration_measure(args, False, "cal-mixed-legacy")
        paths.append(mix_dir)
        calibration_gate(off_log, mix_log)
        calibration = {
            "version": 1, "frames": args.frames,
            "official": result_to_json(official),
            "legacy_mixed": result_to_json(mixed),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        (args.state_dir / "calibration.json").write_text(
            json.dumps(calibration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        for path in paths:
            shutil.rmtree(path, ignore_errors=True)
    elapsed = time.monotonic() - started
    print(f"OK: frames={args.frames}で構造prefix=38・相対+6の6対2を再現")
    print(f"calibration_seconds={elapsed:.1f}")
    print(f"projected_search_seconds_jobs_{args.jobs}={elapsed / 2 * 256 / args.jobs:.0f}")
    print("次: 同じ--framesでsearchを実行する")
    return 0


def load_progress(path: Path) -> dict[int, CandidateMetrics]:
    found: dict[int, CandidateMetrics] = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        value = json.loads(line)
        if value.get("status") == "ok":
            found[int(value["ordinal"])] = CandidateMetrics(**value["metrics"])
    return found


def append_progress(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        fp.flush()
        os.fsync(fp.fileno())


def worker(args: argparse.Namespace, reference: AbstractResult,
           ordinal: int, candidate: int) -> CandidateMetrics:
    started = time.monotonic()
    actual = measure_once(
        official=False, candidate=candidate, frames=args.frames, timeout=args.timeout,
        state_dir=args.state_dir, tag=f"candidate-{ordinal:03d}",
        rom_source=args.rom_source, disk_source=args.disk_source,
        core=args.core, frontend=args.frontend)
    return compare_result(reference, actual, ordinal, time.monotonic() - started)


def write_summary(state_dir: Path, order: list[int],
                  metrics: list[CandidateMetrics]) -> tuple[str, list[int]]:
    by_ordinal = {metric.ordinal: metric for metric in metrics}
    status, selected = classify_results(metrics)
    output = state_dir / "summary.tsv"
    with output.open("w", encoding="utf-8") as fp:
        fp.write("candidate\texchange_prefix\texchange_exact\tfdc_prefix\tfdc_exact\t"
                 "screen_lines_match\tscreen_chars_match\tscreen_sha256_match\t"
                 "screen_line_count\tscreen_char_count\tscreen_sha256\n")
        for ordinal, candidate in sorted(enumerate(order), key=lambda item: item[1]):
            metric = by_ordinal[ordinal]
            fp.write(f"{candidate}\t{metric.exchange_prefix}\t{int(metric.exchange_exact)}\t"
                     f"{metric.fdc_prefix}\t{int(metric.fdc_exact)}\t"
                     f"{int(metric.screen_lines_match)}\t{int(metric.screen_chars_match)}\t"
                     f"{int(metric.screen_sha256_match)}\t{metric.screen_line_count}\t"
                     f"{metric.screen_char_count}\t{metric.screen_sha256}\n")
    return status, [order[ordinal] for ordinal in selected]


def search(args: argparse.Namespace) -> int:
    prepare_args(args)
    calibration_path = args.state_dir / "calibration.json"
    if not calibration_path.exists():
        raise SearchError("先にcalibrateを実行する")
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    if int(calibration["frames"]) != args.frames:
        raise SearchError("calibrateとsearchの--framesが一致しない")
    reference = result_from_json(calibration["official"])

    order_path = args.state_dir / "candidate-order.json"
    if order_path.exists():
        order_state = json.loads(order_path.read_text(encoding="utf-8"))
        if (int(order_state.get("frames", -1)) != args.frames
                or order_state.get("reference_sha256") != reference.screen_sha256):
            raise SearchError("候補順ファイルが現在のcalibrationと一致しない")
        order = [int(value) for value in order_state["order"]]
    else:
        seed = secrets.randbits(64)
        order = list(range(256))
        random.Random(seed).shuffle(order)
        order_path.write_text(json.dumps({
            "seed": seed, "order": order, "frames": args.frames,
            "reference_sha256": reference.screen_sha256,
        }) + "\n", encoding="utf-8")
    if sorted(order) != list(range(256)):
        raise SearchError("候補順ファイルが0〜255の置換でない")

    progress_path = args.state_dir / "progress.jsonl"
    completed = load_progress(progress_path)
    if any(not 0 <= ordinal < 256 for ordinal in completed):
        raise SearchError("進捗ファイルのordinalが範囲外")
    pending = [(ordinal, candidate) for ordinal, candidate in enumerate(order)
               if ordinal not in completed]
    print(f"再開状態: 完了={len(completed)} 未完了={len(pending)} jobs={args.jobs}")
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(worker, args, reference, ordinal, candidate): ordinal
                   for ordinal, candidate in pending}
        for future in concurrent.futures.as_completed(futures):
            ordinal = futures[future]
            try:
                metric = future.result()
            except Exception as exc:  # 候補値は途中表示しない。
                append_progress(progress_path, {"ordinal": ordinal, "status": "error",
                                                "error": type(exc).__name__})
                print(f"run={ordinal + 1:03d}/256 status=error ({type(exc).__name__})")
                continue
            completed[ordinal] = metric
            append_progress(progress_path, {"ordinal": ordinal, "status": "ok",
                                            "metrics": asdict(metric)})
            done = len(completed)
            elapsed = time.monotonic() - started
            newly_done = done - (256 - len(pending))
            rate = elapsed / max(1, newly_done)
            eta = rate * (256 - done) / args.jobs
            print(f"run={ordinal + 1:03d}/256 exchange_prefix={metric.exchange_prefix} "
                  f"fdc_prefix={metric.fdc_prefix} "
                  f"screen={int(metric.screen_lines_match)}/"
                  f"{int(metric.screen_chars_match)}/{int(metric.screen_sha256_match)} "
                  f"eta_seconds={eta:.0f}")

    if len(completed) != 256:
        print(f"未完了: {256 - len(completed)}件。再実行すると成功済みを飛ばして再開する")
        return 2
    metrics = [completed[ordinal] for ordinal in range(256)]
    status, selected = write_summary(args.state_dir, order, metrics)
    print(f"result={status}")
    print("best_candidates=" + (",".join(map(str, selected)) if selected else "none"))
    print(f"summary={args.state_dir / 'summary.tsv'}")
    if status == "insensitive":
        print("検査不能: 全候補が同じ指標。候補介入または指標計算を点検する")
        return 2
    if status == "not_found":
        print("完全一致候補は見つからなかった")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("calibrate", "search"))
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--frames", required=True, type=int)
    parser.add_argument("--jobs", type=int, default=1,
                        help="searchの同時実行数（既定1）")
    parser.add_argument("--timeout", type=int, default=120,
                        help="各走の秒上限（既定120）")
    parser.add_argument("--core", type=Path)
    parser.add_argument("--frontend", type=Path)
    args = parser.parse_args()
    if args.frames <= 700 or args.jobs <= 0 or args.timeout <= 0:
        parser.error("--framesは701以上、--jobs/--timeoutは1以上が必要")
    try:
        return calibrate(args) if args.mode == "calibrate" else search(args)
    except (OSError, ValueError, SearchError, subprocess.SubprocessError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
