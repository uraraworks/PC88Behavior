#!/usr/bin/env python3
"""エラー応答候補・no_disk相補介入を同じ計測ハーネスで扱う。

公式側から保持するのは交換runの方向/長さ、FDCコマンド名列、画面の
行数・文字数・SHA-256だけである。交換値、FDC生値、画面本文は結果へ
保存しない。候補と結果の対応は全走完了後のsummary.tsvで初めて表示する。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import itertools
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
import analyze_no_disk_timing as no_disk_timing  # noqa: E402
import check_l3_screen_output as screen  # noqa: E402


@dataclass(frozen=True)
class AbstractResult:
    exchange: tuple[tuple[str, int], ...]
    fdc: tuple[str, ...]
    screen_line_count: int
    screen_char_count: int
    screen_sha256: str
    artifacts: tuple[tuple[str, int, str], ...] = ()


@dataclass(frozen=True)
class InterventionEvidence:
    run: int
    mode: str
    matched: int
    expected_matched: int
    applied: int
    expected_applied: int
    changed: int

    @property
    def complete(self) -> bool:
        return (self.matched == self.expected_matched
                and self.applied == self.expected_applied
                and self.changed == self.expected_applied)


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
    request_length: int | None = None


class SearchError(RuntimeError):
    pass


def common_prefix(a: tuple, b: tuple) -> int:
    for pos, (left, right) in enumerate(zip(a, b)):
        if left != right:
            return pos
    return min(len(a), len(b))


def compare_result(reference: AbstractResult, actual: AbstractResult,
                   ordinal: int, elapsed: float = 0.0,
                   request_axis: int | None = None) -> CandidateMetrics:
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
        request_length=extract_request_length(actual.exchange, request_axis),
    )


def extract_request_length(exchange: tuple[tuple[str, int], ...], axis: int | None,
                           fault: str | None = None) -> int | None:
    """校正済み+0の要求長。faultはselftest専用の故障注入。"""
    if axis is None:
        return None
    if fault == "previous":
        axis -= 1
    if fault == "constant":
        return 6
    if axis < 0 or axis >= len(exchange):
        return None
    direction, length = exchange[axis]
    return length if direction == "main→sub" else None


def metric_vector(metric: CandidateMetrics) -> tuple:
    return (
        metric.exchange_prefix, metric.exchange_exact,
        metric.fdc_prefix, metric.fdc_exact,
        metric.screen_lines_match, metric.screen_chars_match,
        metric.screen_sha256_match, metric.screen_line_count,
        metric.screen_char_count, metric.screen_sha256,
        metric.request_length,
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
        artifacts=artifact_digests(iolog),
    )


ARTIFACT_STREAMS = (
    ("main_IN_00FC", "main", "IN", "00FC"),
    ("main_IN_00FD", "main", "IN", "00FD"),
    ("sub_OUT_00FC", "sub", "OUT", "00FC"),
    ("sub_OUT_00FD", "sub", "OUT", "00FD"),
)
MAX_INTERVENTIONS = 64
NO_DISK_WINDOW = (("main→sub", 2), ("sub→main", 256),
                  ("main→sub", 1), ("sub→main", 1))


def no_disk_target_runs(exchange: tuple[tuple[str, int], ...]) -> tuple[tuple[int, ...],
                                                                         tuple[int, ...]]:
    """校正窓と同形の全出現から256/1バイト応答run位置を返す。"""
    response256 = []
    response1 = []
    for start in range(max(0, len(exchange) - len(NO_DISK_WINDOW))):
        if (exchange[start:start + 4] == NO_DISK_WINDOW
                and exchange[start + 4][0] == "main→sub"):
            response256.append(start + 1)
            response1.append(start + 3)
    return tuple(response256), tuple(response1)


def run_context_sha256(exchange: tuple[tuple[str, int], ...], run: int) -> str:
    """対象run直前までの構造prefixを値なしの同定指紋にする。"""
    if run < 0 or run >= len(exchange):
        raise SearchError(f"run {run}が交換列の範囲外")
    digest = hashlib.sha256()
    digest.update(f"runs-before={run}\n".encode("ascii"))
    for direction, length in exchange[:run]:
        digest.update(direction.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(length).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def no_disk_target_specs(calibration: dict) -> dict[str, dict]:
    """校正軸の-3/-1だけを、方向・長さ・文脈指紋付きで同定する。"""
    exchange = result_from_json(calibration["legacy_mixed"]).exchange
    axis = int(calibration["axis_mixed"])
    positions = {"response256": axis - 3, "response1": axis - 1}
    expected = {"response256": ("sub→main", 256),
                "response1": ("sub→main", 1)}
    specs = {}
    recorded_specs = calibration.get("target_specs") or {}
    for name, run in positions.items():
        recorded = calibration.get(f"target_{name}")
        if recorded is not None and int(recorded) != run:
            raise SearchError(f"{name}の記録位置が校正軸からの相対位置と一致しない")
        if run < 0 or run >= len(exchange) or exchange[run] != expected[name]:
            raise SearchError(f"{name}の方向/長さが校正軸の記録と一致しない")
        derived = {
            "run": run, "direction": expected[name][0], "length": expected[name][1],
            "context_sha256": run_context_sha256(exchange, run),
        }
        if name in recorded_specs and recorded_specs[name] != derived:
            raise SearchError(f"{name}の保存済み同定指紋が校正交換列と一致しない")
        specs[name] = derived
    return specs


def verify_run_identity(exchange: tuple[tuple[str, int], ...], spec: dict) -> None:
    """同形の別runを含め、校正対象以外への位置ずれを拒否する。"""
    run = int(spec["run"])
    expected = (str(spec["direction"]), int(spec["length"]))
    if run < 0 or run >= len(exchange) or exchange[run] != expected:
        raise SearchError(f"介入対象run {run}の方向/長さが校正値と一致しない")
    if run_context_sha256(exchange, run) != spec["context_sha256"]:
        raise SearchError(f"介入対象run {run}の文脈指紋が校正値と一致しない")


def artifact_digests(iolog: Path) -> tuple[tuple[str, int, str], ...]:
    """対象列を値を保持せず件数とSHA-256へ射影する。"""
    states = {
        (cpu, kind, port): [name, 0, hashlib.sha256()]
        for name, cpu, kind, port in ARTIFACT_STREAMS
    }
    with shape.cmp_io._open_iolog(str(iolog)) as fp:
        for line in fp:
            match = shape.ROW_RE.match(line)
            if not match:
                continue
            _seq, _clock, _frame, cpu, kind, port, value, _pc = match.groups()
            state = states.get((cpu, kind, port.upper()))
            if state is None:
                continue
            state[1] += 1
            state[2].update(value.upper().encode("ascii"))
            state[2].update(b"\n")
    return tuple((name, int(count), digest.hexdigest())
                 for name, count, digest in states.values())


def artifacts_changed(control: AbstractResult, intervention: AbstractResult) -> bool:
    return control.artifacts != intervention.artifacts


def artifact_difference_names(control: AbstractResult,
                              intervention: AbstractResult) -> list[str]:
    left = {name: (count, digest) for name, count, digest in control.artifacts}
    right = {name: (count, digest) for name, count, digest in intervention.artifacts}
    return sorted(name for name in left.keys() | right.keys()
                  if left.get(name) != right.get(name))


def ineffective_intervention_arms(arms: dict[str, AbstractResult]) -> list[str]:
    """対照と成果物が同一の介入armを列挙する（帰属禁止関門）。"""
    control = arms["control"]
    return [name for name, result in arms.items()
            if name != "control" and not artifacts_changed(control, result)]


def exchange_value_events(path: Path):
    """交換列を逐次走査する。呼出側は値を保存・表示しない。"""
    with shape.cmp_io._open_iolog(str(path)) as fp:
        for line in fp:
            match = shape.ROW_RE.match(line)
            if not match:
                continue
            _seq, _clock, _frame, cpu, kind, port, value, pc = match.groups()
            port, pc = port.upper(), pc.upper()
            if cpu != "main":
                continue
            if kind == "OUT" and port == "00FD" and pc in shape.m2s.SEND_PCS:
                yield "main→sub", value.upper()
            elif kind == "IN" and port == "00FC" and (
                    pc in shape.m2s.RECV_HANDSHAKE_PCS or pc in shape.m2s.RECV_BULK_PCS):
                yield "sub→main", value.upper()


def first_exchange_difference(official_path: Path, mixed_path: Path,
                              axis_official: int, axis_mixed: int) -> dict:
    """先頭からの最初の構造/値差を、値そのものを残さず位置へ射影する。"""
    sentinel = object()
    run_off = run_mix = -1
    prev_off = prev_mix = None
    for event_pos, (off, mix) in enumerate(itertools.zip_longest(
            exchange_value_events(official_path), exchange_value_events(mixed_path),
            fillvalue=sentinel)):
        if off is not sentinel and off[0] != prev_off:
            run_off += 1
            prev_off = off[0]
        if mix is not sentinel and mix[0] != prev_mix:
            run_mix += 1
            prev_mix = mix[0]
        if off != mix:
            kind = "structure" if (off is sentinel or mix is sentinel
                                    or off[0] != mix[0]) else "value"
            rel_off = run_off - axis_official if off is not sentinel else None
            rel_mix = run_mix - axis_mixed if mix is not sentinel else None
            return {
                "position_base": 0,
                "event_position": event_pos,
                "kind": kind,
                "official_run_position": run_off if off is not sentinel else None,
                "mixed_run_position": run_mix if mix is not sentinel else None,
                "relative_to_axis_official": rel_off,
                "relative_to_axis_mixed": rel_mix,
                "runs_before_axis_official": -rel_off if rel_off is not None and rel_off < 0 else 0,
                "runs_before_axis_mixed": -rel_mix if rel_mix is not None and rel_mix < 0 else 0,
                "before_relative_minus4_official": rel_off is not None and rel_off < -4,
                "before_relative_minus4_mixed": rel_mix is not None and rel_mix < -4,
            }
    raise SearchError("公式と混成の交換列が値・構造とも全長一致")


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
        artifacts=tuple((str(item[0]), int(item[1]), str(item[2]))
                        for item in value.get("artifacts", ())),
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


INTERVENTION_LINE_RE = re.compile(
    r"交換介入slot(\d+) run=(\d+) matched=(\d+) applied=(\d+) changed=(\d+)"
)
SUB_INTERRUPT_LINE_RE = re.compile(
    r"sub割り込み介入 first=(\d+) last=(\d+) mode=(\d+) "
    r"matched=(\d+) suppressed=(\d+) accepted=(\d+)"
)
READY_HANDOFF_LINE_RE = re.compile(
    r"応答準備handoff介入 run=(\d+) mode=(\d+) action=(\d+) "
    r"matched=(\d+) count=(\d+)"
)


def sub_interrupt_receipt(iolog: Path) -> dict[str, int] | None:
    path = iolog.with_suffix(".stderr.txt")
    if not path.is_file():
        return None
    found = None
    with path.open("r", encoding="utf-8", errors="strict") as fp:
        for line in fp:
            match = SUB_INTERRUPT_LINE_RE.search(line)
            if match:
                keys = ("first_run", "last_run", "mode", "matched_checks",
                        "suppressed_checks", "accepted_in_window")
                found = dict(zip(keys, map(int, match.groups())))
    return found


def response_ready_handoff_receipt(iolog: Path) -> dict[str, int] | None:
    path = iolog.with_suffix(".stderr.txt")
    if not path.is_file():
        return None
    found = None
    with path.open("r", encoding="utf-8", errors="strict") as fp:
        for line in fp:
            match = READY_HANDOFF_LINE_RE.search(line)
            if match:
                keys = ("run", "mode", "action", "matched", "count")
                found = dict(zip(keys, map(int, match.groups())))
    return found


def metric_source_sha256(*paths: Path) -> str:
    """arm固有の入力ファイルを、内容を露出しない指紋へまとめる。"""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as fp:
            for block in iter(lambda: fp.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def inject_clock_shift(paths: tuple[Path, ...], *, after_clock: int,
                       delta: int) -> None:
    """self-check arm用に、生ログの基準直後だけを既知量ずらす。

    エミュレータの状態や交換値は変えず、各armログから時間指標を読み直して
    いることだけを故障注入で検査する。呼出側が一時runディレクトリを破棄する。
    """
    if delta <= 0:
        raise SearchError("clock故障注入量は正でなければならない")
    for path in paths:
        rewritten = []
        with path.open("r", encoding="utf-8", errors="strict") as fp:
            for line in fp:
                fields = line.split()
                if fields and fields[0].isdigit() and len(fields) >= 2:
                    try:
                        clock = int(fields[1])
                    except ValueError:
                        pass
                    else:
                        if clock > after_clock:
                            fields[1] = str(clock + delta)
                            line = " ".join(fields) + "\n"
                rewritten.append(line)
        path.write_text("".join(rewritten), encoding="utf-8")


def run_frontend(command: list[str], iolog: Path, timeout: int) -> dict[int, tuple[int, int, int, int]]:
    stderr = iolog.with_suffix(".stderr.txt")
    stderr.unlink(missing_ok=True)
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
    receipts: dict[int, tuple[int, int, int, int]] = {}
    with stderr.open("r", encoding="utf-8", errors="strict") as fp:
        for line in fp:
            match = INTERVENTION_LINE_RE.search(line)
            if match:
                slot, run, matched, applied, changed = map(int, match.groups())
                receipts[slot] = (run, matched, applied, changed)
    return receipts


def measure_once(*, official: bool, candidate: int | None, frames: int,
                 timeout: int, state_dir: Path, tag: str, rom_source: Path,
                 disk_source: Path, core: Path, frontend: Path,
                 break_error_response_bit6: bool = False,
                 scenario: str = "unreadable_disk",
                 interventions: tuple[str, ...] = ()) -> tuple[AbstractResult, dict[int, tuple[int, int, int, int]]]:
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
    if scenario == "unreadable_disk":
        subprocess.run([sys.executable, str(REPO / "tools/make_l3_testdisk.py"),
                        str(disk_b)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, check=True)
        media = run_dir / "media.m3u"
        media.write_text(f"{disk_a}\n{disk_b}\n", encoding="utf-8")
    elif scenario == "no_disk":
        media = disk_a
    else:
        raise SearchError(f"未知のscenario: {scenario}")
    iolog = run_dir / "run.iolog.txt"
    report = run_dir / "run.report.txt"
    command = [
        str(frontend), "--core", str(core), "--rom-dir", str(rom_dir),
        "--disk", str(media), "--frames", str(frames),
        "--io-log", str(iolog), "--out", str(report),
        "--type-at", "300", "--type", r"\n",
        "--type-at", "700", "--type", r"FILES 2\n",
    ]
    for intervention in interventions:
        command += ["--exchange-intervention", intervention]
    try:
        receipts = run_frontend(command, iolog, timeout)
        return abstract_result(iolog, report), receipts
    finally:
        # 公式値や画面本文を含み得る生ファイルは再開状態へ残さない。
        shutil.rmtree(run_dir, ignore_errors=True)


def calibration_gate(official_log: Path, mixed_log: Path,
                     scenario: str) -> tuple[int, int]:
    official_runs = shape.exchange_runs(official_log)
    mixed_runs = shape.exchange_runs(mixed_log)
    prefix = shape.structural_prefix(official_runs, mixed_runs)
    official_fdc = shape.fdc_shapes(official_log)
    mixed_fdc = shape.fdc_shapes(mixed_log)
    divergence = shape.fdc_divergence(official_fdc, mixed_fdc)
    axis_off = shape.request_axis(official_runs, official_fdc[divergence].clock)
    axis_mix = shape.request_axis(mixed_runs, mixed_fdc[divergence].clock)
    if scenario == "unreadable_disk":
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
    else:
        expected_pre = (("main→sub", 2), ("sub→main", 256),
                        ("main→sub", 1), ("sub→main", 1))
        try:
            off_pre = tuple((r.direction, r.length)
                            for r in official_runs[axis_off - 4:axis_off])
            mix_pre = tuple((r.direction, r.length)
                            for r in mixed_runs[axis_mix - 4:axis_mix])
            off_zero = official_runs[axis_off]
            mix_zero = mixed_runs[axis_mix]
        except IndexError as exc:
            raise SearchError("no_disk校正窓が相対-4〜+0へ届かない") from exc
        expected = (prefix == 36 and off_pre == expected_pre and mix_pre == expected_pre
                    and (off_zero.direction, off_zero.length) == ("main→sub", 5)
                    and (mix_zero.direction, mix_zero.length) == ("main→sub", 6))
        if not expected:
            raise SearchError(
                f"no_disk関門不成立（構造prefix={prefix}、-4〜-1同形と+0の5対6={expected}）")
    return axis_off, axis_mix


def calibration_measure(args: argparse.Namespace, official: bool,
                        tag: str, *, with_intlog: bool = False,
                        sub_interrupt_intervention: str | None = None,
                        response_ready_handoff: tuple[int, str] | None = None
                        ) -> tuple[AbstractResult, Path, Path, Path, Path | None]:
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
    if args.scenario == "unreadable_disk":
        subprocess.run([sys.executable, str(REPO / "tools/make_l3_testdisk.py"), str(disk_b)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        media = run_dir / "media.m3u"
        media.write_text(f"{disk_a}\n{disk_b}\n", encoding="utf-8")
    else:
        media = disk_a
    iolog, report = run_dir / "run.iolog.txt", run_dir / "run.report.txt"
    intlog = run_dir / "run.intlog.txt" if with_intlog else None
    command = [str(args.frontend), "--core", str(args.core), "--rom-dir", str(rom_dir),
               "--disk", str(media), "--frames", str(args.frames),
               "--io-log", str(iolog), "--out", str(report),
               "--type-at", "300", "--type", r"\n",
               "--type-at", "700", "--type", r"FILES 2\n"]
    if intlog is not None:
        command += ["--int-log", str(intlog)]
    if sub_interrupt_intervention is not None:
        command += ["--sub-interrupt-intervention", sub_interrupt_intervention]
    if response_ready_handoff is not None:
        run, mode = response_ready_handoff
        command += ["--response-ready-handoff", f"{run}:{mode}"]
    run_frontend(command, iolog, args.timeout)
    if intlog is not None and not intlog.is_file():
        raise SearchError("割り込み受理ログが生成されなかった")
    return abstract_result(iolog, report), run_dir, iolog, report, intlog


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
        official, off_dir, off_log, _, _ = calibration_measure(args, True, "cal-official")
        paths.append(off_dir)
        mixed, mix_dir, mix_log, _, _ = calibration_measure(args, False, "cal-mixed-legacy")
        paths.append(mix_dir)
        axis_official, axis_mixed = calibration_gate(off_log, mix_log, args.scenario)
        first_difference = first_exchange_difference(
            off_log, mix_log, axis_official, axis_mixed)
        response256_runs, response1_runs = no_disk_target_runs(mixed.exchange)
        if args.scenario == "no_disk" and (
                axis_mixed - 3 not in response256_runs
                or axis_mixed - 1 not in response1_runs):
            raise SearchError("校正軸の-3/-1を全区間の同形窓から再同定できない")
        calibration = {
            "version": 4, "scenario": args.scenario, "frames": args.frames,
            "official": result_to_json(official),
            "legacy_mixed": result_to_json(mixed),
            "axis_official": axis_official,
            "axis_mixed": axis_mixed,
            "first_exchange_difference": first_difference,
            "target_response256": axis_mixed - 3 if args.scenario == "no_disk" else None,
            "target_response1": axis_mixed - 1 if args.scenario == "no_disk" else None,
            "target_response256_runs": list(response256_runs) if args.scenario == "no_disk" else None,
            "target_response1_runs": list(response1_runs) if args.scenario == "no_disk" else None,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        if args.scenario == "no_disk":
            calibration["target_specs"] = no_disk_target_specs(calibration)
        (args.state_dir / "calibration.json").write_text(
            json.dumps(calibration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        for path in paths:
            shutil.rmtree(path, ignore_errors=True)
    elapsed = time.monotonic() - started
    if args.scenario == "no_disk":
        print(f"OK: frames={args.frames}で相対-4〜-1同形・+0の5対6を再現")
    else:
        print(f"OK: frames={args.frames}で構造prefix=38・相対+6の6対2を再現")
    print(f"calibration_seconds={elapsed:.1f}")
    print("first_exchange_difference="
          f"event:{first_difference['event_position']} "
          f"kind:{first_difference['kind']} "
          f"relative_official:{first_difference['relative_to_axis_official']} "
          f"relative_mixed:{first_difference['relative_to_axis_mixed']}")
    print(f"projected_search_seconds_jobs_{args.jobs}={elapsed / 2 * 256 / args.jobs:.0f}")
    next_mode = "attribute" if args.scenario == "no_disk" else "search"
    print(f"次: 同じ--frames/--scenarioで{next_mode}を実行する")
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
    if args.scenario == "no_disk":
        calibration = json.loads((args.state_dir / "calibration.json").read_text(encoding="utf-8"))
        rom_candidate = None
        target_runs = (int(no_disk_target_specs(calibration)["response1"]["run"]),)
        interventions = tuple(f"{run}:replace-first:{candidate}" for run in target_runs)
        if len(interventions) > MAX_INTERVENTIONS:
            raise SearchError("同形窓の出現数が介入slot上限を超えた")
        request_axis = int(calibration["axis_mixed"])
    else:
        rom_candidate = candidate
        interventions = ()
        request_axis = None
    actual, _receipts = measure_once(
        official=False, candidate=rom_candidate, frames=args.frames, timeout=args.timeout,
        state_dir=args.state_dir, tag=f"candidate-{ordinal:03d}",
        rom_source=args.rom_source, disk_source=args.disk_source,
        core=args.core, frontend=args.frontend, scenario=args.scenario,
        interventions=interventions)
    return compare_result(reference, actual, ordinal, time.monotonic() - started,
                          request_axis=request_axis)


def write_summary(state_dir: Path, order: list[int],
                  metrics: list[CandidateMetrics]) -> tuple[str, list[int]]:
    by_ordinal = {metric.ordinal: metric for metric in metrics}
    status, selected = classify_results(metrics)
    output = state_dir / "summary.tsv"
    with output.open("w", encoding="utf-8") as fp:
        fp.write("candidate\texchange_prefix\texchange_exact\tfdc_prefix\tfdc_exact\t"
                 "screen_lines_match\tscreen_chars_match\tscreen_sha256_match\t"
                 "screen_line_count\tscreen_char_count\tscreen_sha256\trequest_length_at_plus0\n")
        for ordinal, candidate in sorted(enumerate(order), key=lambda item: item[1]):
            metric = by_ordinal[ordinal]
            fp.write(f"{candidate}\t{metric.exchange_prefix}\t{int(metric.exchange_exact)}\t"
                     f"{metric.fdc_prefix}\t{int(metric.fdc_exact)}\t"
                     f"{int(metric.screen_lines_match)}\t{int(metric.screen_chars_match)}\t"
                     f"{int(metric.screen_sha256_match)}\t{metric.screen_line_count}\t"
                     f"{metric.screen_char_count}\t{metric.screen_sha256}\t"
                     f"{metric.request_length if metric.request_length is not None else ''}\n")
    return status, [order[ordinal] for ordinal in selected]


def search(args: argparse.Namespace) -> int:
    prepare_args(args)
    calibration_path = args.state_dir / "calibration.json"
    if not calibration_path.exists():
        raise SearchError("先にcalibrateを実行する")
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    if int(calibration["frames"]) != args.frames:
        raise SearchError("calibrateとsearchの--framesが一致しない")
    if calibration.get("scenario", "unreadable_disk") != args.scenario:
        raise SearchError("calibrateとsearchの--scenarioが一致しない")
    if args.scenario == "no_disk" and int(calibration.get("version", 0)) < 3:
        raise SearchError("成果物ハッシュ/全同形窓を持つ新版でcalibrateをやり直す必要がある")
    if args.scenario == "no_disk" and args.target != "response1":
        raise SearchError("256バイト応答は総当たりせず、先にprobe256を実行する")
    reference = result_from_json(calibration["official"])

    order_path = args.state_dir / "candidate-order.json"
    if order_path.exists():
        order_state = json.loads(order_path.read_text(encoding="utf-8"))
        if (int(order_state.get("frames", -1)) != args.frames
                or order_state.get("reference_sha256") != reference.screen_sha256
                or order_state.get("scenario", "unreadable_disk") != args.scenario):
            raise SearchError("候補順ファイルが現在のcalibrationと一致しない")
        order = [int(value) for value in order_state["order"]]
    else:
        seed = secrets.randbits(64)
        order = list(range(256))
        random.Random(seed).shuffle(order)
        order_path.write_text(json.dumps({
            "seed": seed, "order": order, "frames": args.frames,
            "reference_sha256": reference.screen_sha256, "scenario": args.scenario,
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


def load_no_disk_calibration(args: argparse.Namespace) -> tuple[dict, AbstractResult]:
    prepare_args(args)
    path = args.state_dir / "calibration.json"
    if not path.exists():
        raise SearchError("先にno_diskのcalibrateを実行する")
    calibration = json.loads(path.read_text(encoding="utf-8"))
    if calibration.get("scenario") != "no_disk" or int(calibration["frames"]) != args.frames:
        raise SearchError("calibrationのscenario/framesが現在の指定と一致しない")
    if int(calibration.get("version", 0)) < 3 or "first_exchange_difference" not in calibration:
        raise SearchError("成果物ハッシュ/先頭差異を持つ新版でcalibrateをやり直す必要がある")
    return calibration, result_from_json(calibration["official"])


def attribution_kind(lengths: dict[str, int | None]) -> str:
    """相補表を解釈する。5/6以外や対照変化は曖昧として止める。"""
    if lengths.get("control") != 6 or any(v not in (5, 6) for v in lengths.values()):
        return "invalid"
    hit256 = lengths["response256"] == 5
    hit1 = lengths["response1"] == 5
    hit_both = lengths["both"] == 5
    if hit256 and not hit1 and hit_both:
        return "response256"
    if hit1 and not hit256 and hit_both:
        return "response1"
    if hit256 and hit1 and hit_both:
        return "both_independent"
    if not hit256 and not hit1 and hit_both:
        return "interaction_only"
    return "inconsistent"


def attribution_outcome(measured: list[tuple[str, CandidateMetrics, AbstractResult,
                                              tuple[InterventionEvidence, ...]]]
                        ) -> tuple[str, list[str]]:
    """介入不成立と、成立した無影響という有効な帰属結論を分離する。"""
    arms = {name: actual for name, _metric, actual, _evidence in measured}
    ineffective = ineffective_intervention_arms(arms)
    if ineffective:
        return "intervention_ineffective", ineffective
    metrics = [metric_vector(metric) for _name, metric, _actual, _evidence in measured]
    if len(set(metrics)) == 1:
        return "intervention_effective_no_metric_change", []
    lengths = {name: metric.request_length
               for name, metric, _actual, _evidence in measured}
    return attribution_kind(lengths), []


def attribution_exit_code(result: str) -> int:
    """帰属結果のCLI終了コード。無影響は有効結論なので成功とする。"""
    if result == "intervention_ineffective":
        return 2
    if result in ("intervention_effective_no_metric_change",
                  "response1", "response256"):
        return 0
    return 1


def run_intervention_arm(args: argparse.Namespace, reference: AbstractResult,
                         calibration: dict, ordinal: int, name: str,
                         interventions: tuple[str, ...]) -> tuple[CandidateMetrics, AbstractResult,
                                                                  tuple[InterventionEvidence, ...]]:
    started = time.monotonic()
    actual, receipts = measure_once(
        official=False, candidate=None, frames=args.frames, timeout=args.timeout,
        state_dir=args.state_dir, tag=f"{args.mode}-{ordinal}",
        rom_source=args.rom_source, disk_source=args.disk_source,
        core=args.core, frontend=args.frontend, scenario="no_disk",
        interventions=interventions)
    target_specs = no_disk_target_specs(calibration)
    specs_by_run = {int(spec["run"]): spec for spec in target_specs.values()}
    evidence = []
    for slot, intervention in enumerate(interventions):
        run = int(intervention.split(":", 1)[0])
        if run not in specs_by_run:
            raise SearchError(f"介入対象run {run}は校正軸の-3/-1ではない")
        verify_run_identity(actual.exchange, specs_by_run[run])
        _run_s, mode, _value = intervention.split(":")
        expected_matched = actual.exchange[run][1]
        expected_applied = (expected_matched if mode.endswith("all") else
                            1 if mode.endswith("first") else
                            max(0, expected_matched - 1))
        if slot not in receipts:
            raise SearchError(f"介入slot{slot}の実行証跡が無い")
        observed_run, matched, applied, changed = receipts[slot]
        item = InterventionEvidence(run, mode, matched, expected_matched,
                                    applied, expected_applied, changed)
        if observed_run != run or not item.complete:
            raise SearchError(
                f"介入slot{slot}の適用回数不一致"
                f"（matched={matched}/{expected_matched}, "
                f"applied={applied}/{expected_applied}, changed={changed}/{expected_applied}）")
        evidence.append(item)
    metric = compare_result(reference, actual, ordinal, time.monotonic() - started,
                            request_axis=int(calibration["axis_mixed"]))
    return metric, actual, tuple(evidence)


def attribute_no_disk(args: argparse.Namespace) -> int:
    calibration, reference = load_no_disk_calibration(args)
    target_specs = no_disk_target_specs(calibration)
    # 全区間の同形窓へ広げると、先行窓への介入が後続run列を変え、校正時の
    # 絶対位置が別runを指し得る。帰属対象は校正軸に結び付いた-3/-1だけにする。
    targets256 = (int(target_specs["response256"]["run"]),)
    targets1 = (int(target_specs["response1"]["run"]),)
    specs256 = tuple(f"{run}:xor-all:1" for run in targets256)
    specs1 = tuple(f"{run}:xor-all:1" for run in targets1)
    if len(specs256) + len(specs1) > MAX_INTERVENTIONS:
        raise SearchError("同形窓の出現数が介入slot上限を超えた")
    arms = [
        ("control", ()),
        ("response256", specs256),
        ("response1", specs1),
        ("both", specs256 + specs1),
    ]
    expected_arm_runs = {name: len(interventions) for name, interventions in arms}
    measured = []
    for ordinal, (name, interventions) in enumerate(arms):
        metric, actual, evidence = run_intervention_arm(
            args, reference, calibration, ordinal, name, interventions)
        measured.append((name, metric, actual, evidence))
    control_actual = measured[0][2]
    result, ineffective = attribution_outcome(measured)
    for name, metric, actual, evidence in measured:
        changed = name == "control" or artifacts_changed(control_actual, actual)
        event_summary = (",".join(
            f"{item.matched}/{item.expected_matched}:"
            f"{item.applied}/{item.expected_applied}"
            for item in evidence) if evidence else "control")
        delta_names = (artifact_difference_names(control_actual, actual)
                       if name != "control" else [])
        print(f"arm={name} request_length_at_plus0={metric.request_length} "
              f"exchange_prefix={metric.exchange_prefix} fdc_prefix={metric.fdc_prefix} "
              f"screen={int(metric.screen_lines_match)}/"
              f"{int(metric.screen_chars_match)}/{int(metric.screen_sha256_match)} "
              f"intervention_runs={len(evidence)}/{expected_arm_runs[name]} "
              f"intervention_events={event_summary} "
              f"artifact_differences={','.join(delta_names) if delta_names else '-'} "
              f"artifact_changed={int(changed) if name != 'control' else 'control'} "
              f"intervention_verified={int(changed) if name != 'control' else 'control'}")
    lengths = {name: metric.request_length for name, metric, _actual, _evidence in measured}
    out = {
        "version": 3, "scenario": "no_disk", "frames": args.frames,
        "result": result, "request_lengths": lengths,
        "metrics": {name: asdict(metric) for name, metric, _actual, _evidence in measured},
        "artifacts": {
            name: [{"name": stream, "count": count, "sha256": digest}
                   for stream, count, digest in actual.artifacts]
            for name, _metric, actual, _evidence in measured
        },
        "artifact_changed_from_control": {
            name: (None if name == "control" else artifacts_changed(control_actual, actual))
            for name, _metric, actual, _evidence in measured
        },
        "artifact_differences_from_control": {
            name: ([] if name == "control" else
                   artifact_difference_names(control_actual, actual))
            for name, _metric, actual, _evidence in measured
        },
        "intervention_evidence": {
            name: [asdict(item) | {"complete": item.complete} for item in evidence]
            for name, _metric, _actual, evidence in measured
        },
        "first_exchange_difference": calibration["first_exchange_difference"],
        "intervention_scope": {
            "response256": {"runs": list(targets256), "occurrences": len(targets256),
                            "mode": "xor-all", "mask": 1},
            "response1": {"runs": list(targets1), "occurrences": len(targets1),
                          "mode": "xor-all", "mask": 1},
        },
    }
    (args.state_dir / "attribution.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"result={result}")
    if ineffective:
        print("測定失敗: 介入が成果物へ届かず、帰属の結論を出せないarm="
              + ",".join(ineffective))
        return attribution_exit_code(result)
    if result == "intervention_effective_no_metric_change":
        print("有効結論: 介入は成立し、-3/-1応答内容は+0要求長・交換prefix・"
              "FDC prefix・画面指標に無影響だった")
        return attribution_exit_code(result)
    if result == "response1":
        print("次: --scenario no_disk --target response1 search")
        return attribution_exit_code(result)
    if result == "response256":
        print("次: --scenario no_disk probe256（256バイト総当たりは禁止）")
        return attribution_exit_code(result)
    return attribution_exit_code(result)


def timing_no_disk(args: argparse.Namespace) -> int:
    calibration, _reference = load_no_disk_calibration(args)
    json_out = args.state_dir / "timing.json"
    report_out = args.state_dir / "timing-report.txt"
    if json_out.exists() or report_out.exists():
        raise SearchError("timing出力が既にあるため上書きしない")
    paths: list[Path] = []
    try:
        paths.append(args.state_dir / "runs" / "timing-official")
        _off, off_dir, off_io, _off_report, off_int = calibration_measure(
            args, True, "timing-official", with_intlog=True)
        paths[-1] = off_dir
        paths.append(args.state_dir / "runs" / "timing-mixed")
        _mix, mix_dir, mix_io, _mix_report, mix_int = calibration_measure(
            args, False, "timing-mixed", with_intlog=True)
        paths[-1] = mix_dir
        axis_off, axis_mix = calibration_gate(off_io, mix_io, "no_disk")
        if (axis_off, axis_mix) != (int(calibration["axis_official"]),
                                    int(calibration["axis_mixed"])):
            raise SearchError("timing再測定の校正軸位置が保存済みcalibrationと一致しない")
        if off_int is None or mix_int is None:
            raise SearchError("timing解析に必要な割り込み受理ログが無い")
        result = no_disk_timing.compare(
            off_io, off_int, mix_io, mix_int, axis_off, axis_mix)
        json_out.write_text(json.dumps(no_disk_timing.compact_result(result),
                                      ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        report_out.write_text("\n".join(no_disk_timing.report_lines(result)) + "\n",
                              encoding="utf-8")
        if args.verbose:
            (args.state_dir / "timing-verbose.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (args.state_dir / "timing-report-verbose.txt").write_text(
                "\n".join(no_disk_timing.report_lines(result, verbose=True)) + "\n",
                encoding="utf-8")
    finally:
        # 生値・画面本文・私物パスを含み得る一時成果物は集約後に残さない。
        for path in paths:
            shutil.rmtree(path, ignore_errors=True)
    print(f"result=timing_measured")
    print("割り込み件数、論理位置の相対到達clock、$FE確定bitの遷移位相・間隔、"
          "軸直前1バイト応答の2間隔を記録")
    print("summary=timing-report.txt（--state-dir直下）")
    if args.verbose:
        print("verbose=timing-report-verbose.txt, timing-verbose.json")
    return 0


def interrupt_artifact(actual: AbstractResult, timing: dict) -> str:
    """値を含まないI/O指紋・受理件数・相対到達clockの成果物指紋。"""
    payload = {
        "io": actual.artifacts,
        "interrupt_counts": timing["mixed"]["interrupt_counts"],
        "logical_arrival": timing["mixed"]["logical_arrival_from_reference"],
        "one_byte_response": timing["mixed"]["one_byte_response"],
    }
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def interrupt_attribute_no_disk(args: argparse.Namespace) -> int:
    calibration, reference = load_no_disk_calibration(args)
    output = args.state_dir / "sub-interrupt-attribution-v2.json"
    if output.exists():
        raise SearchError("sub割り込み帰属出力が既にあるため上書きしない")
    axis_off = int(calibration["axis_official"])
    axis_mix = int(calibration["axis_mixed"])
    first_run, last_run = axis_mix - 1, axis_mix
    clock_shift = 257
    arms = (("control", None, 0),
            ("suppress", f"{first_run}:{last_run}:suppress", 0),
            ("delay_one", f"{first_run}:{last_run}:delay-one", 0),
            ("clock_shift_257", None, clock_shift))
    paths: list[Path] = []
    rows = []
    try:
        off, off_dir, off_io, _off_report, off_int = calibration_measure(
            args, True, "interrupt-official", with_intlog=True)
        paths.append(off_dir)
        if off_int is None:
            raise SearchError("公式側の割り込み受理ログが無い")
        for ordinal, (name, intervention, injected_shift) in enumerate(arms):
            actual, run_dir, iolog, _report, intlog = calibration_measure(
                args, False, f"interrupt-{name}", with_intlog=True,
                sub_interrupt_intervention=intervention)
            paths.append(run_dir)
            if intlog is None:
                raise SearchError(f"{name} armの割り込み受理ログが無い")
            runs = shape.exchange_runs(iolog)
            if axis_mix >= len(runs) or runs[axis_mix].direction != "main→sub":
                raise SearchError(f"{name} armが保存済み+0交換軸へ届かなかった")
            if injected_shift:
                reference_clock = runs[axis_mix - 4].start_clock
                inject_clock_shift((iolog, intlog), after_clock=reference_clock,
                                   delta=injected_shift)
                # clock以外の指標も、故障注入後の同じarm入力から読み直す。
                actual = abstract_result(iolog, _report)
            timing = no_disk_timing.compare(
                off_io, off_int, iolog, intlog, axis_off, axis_mix)
            receipt = sub_interrupt_receipt(iolog)
            if intervention is not None and (receipt is None or
                    receipt["matched_checks"] == 0 or receipt["suppressed_checks"] == 0):
                raise SearchError(f"{name} armの介入証跡が不成立")
            metric = compare_result(reference, actual, ordinal,
                                    request_axis=axis_mix)
            rows.append({
                "arm": name,
                "metrics": asdict(metric),
                "sub_interrupt_counts": timing["mixed"]["interrupt_counts"]["sub"],
                "logical_arrival_mixed_minus_official":
                    timing["differences"]["logical_arrival_mixed_minus_official"],
                "one_byte_response_mixed_minus_official":
                    timing["differences"]["one_byte_response_mixed_minus_official"],
                "receipt": receipt,
                "artifact_fingerprint": interrupt_artifact(actual, timing),
                "metric_source_sha256": metric_source_sha256(iolog, intlog, _report),
                "diagnostic_clock_shift": injected_shift or None,
            })
    finally:
        for path in paths:
            shutil.rmtree(path, ignore_errors=True)
    control = rows[0]
    control_vector = (metric_vector(CandidateMetrics(**control["metrics"])),
                      control["sub_interrupt_counts"],
                      control["logical_arrival_mixed_minus_official"])
    changed_metrics = []
    expected_shifted = {
        key: value + clock_shift
        for key, value in control["logical_arrival_mixed_minus_official"].items()
    }
    diagnostic = rows[-1]
    if diagnostic["logical_arrival_mixed_minus_official"] != expected_shifted:
        raise SearchError("clock故障注入armでarrival_deltaが既知量どおり動かない")
    for row in rows:
        row["artifact_changed"] = (None if row["arm"] == "control" else
                                    row["artifact_fingerprint"] !=
                                    control["artifact_fingerprint"])
        vector = (metric_vector(CandidateMetrics(**row["metrics"])),
                  row["sub_interrupt_counts"],
                  row["logical_arrival_mixed_minus_official"])
        if (row["arm"] not in ("control", "clock_shift_257")
                and vector != control_vector):
            changed_metrics.append(row["arm"])
    result = ("intervention_changed" if changed_metrics else
              "intervention_effective_no_metric_change")
    output.write_text(json.dumps({
        "version": 2, "scenario": "no_disk", "result": result,
        "scope": {"first_run": first_run, "last_run": last_run,
                  "relative_to_axis": [-1, 0]},
        "metric_recalculation_check": {
            "arm": "clock_shift_257", "injected_clock_shift": clock_shift,
            "arrival_delta_changed_by_expected_amount": True,
        },
        "arms": rows,
        "interpretation_limit": (
            "一致しても『抑止すると一致する』まで。公式subが同じ抑止機序を持つとはいえない。"),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        m = row["metrics"]
        print(f"arm={row['arm']} request_length_at_plus0={m['request_length']} "
              f"exchange_prefix={m['exchange_prefix']} fdc_prefix={m['fdc_prefix']} "
              f"screen={int(m['screen_lines_match'])}/{int(m['screen_chars_match'])}/"
              f"{int(m['screen_sha256_match'])} "
              f"sub_interrupts={row['sub_interrupt_counts']['calibration_window']}/"
              f"{row['sub_interrupt_counts']['axis_near']} "
              f"arrival_delta={row['logical_arrival_mixed_minus_official']} "
              f"metric_source={row['metric_source_sha256'][:12]} "
              f"artifact_changed={row['artifact_changed'] if row['arm'] != 'control' else 'control'}")
    print(f"result={result}")
    print("注: 一致しても『抑止すると一致する』までで、公式の機序は断定しない")
    return 0


READY_SHIFT_SWEEP = tuple(range(-5, 9))


def validate_ready_shift(requested: int, applied: int, control_clock: int,
                         ready_clock: int, *, fault: int = 0) -> int:
    """指定・コア証跡・実測clock差の三者一致関門。faultはselftest専用。"""
    effective = ready_clock - control_clock + fault
    if applied != requested or effective != requested:
        raise SearchError(
            f"応答準備shift不一致 requested={requested} applied={applied} effective={effective}")
    return effective


def response_timing_artifact(actual: AbstractResult, timing: dict) -> str:
    payload = {
        "io": actual.artifacts,
        "logical_arrival": timing["mixed"]["logical_arrival_from_reference"],
        "one_byte_response": timing["mixed"]["one_byte_response"],
    }
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def ready_sweep_no_disk(args: argparse.Namespace) -> int:
    """無効と判明した旧数値掃引を結論生成前に停止する。"""
    raise SearchError(
        "ready-sweepは廃止: 既定cpu_timing=0ではstate0予算がPIO handoffを支配せず、"
        "数値shiftを実効clockへ反映できない。ready-handoff-probeを使うこと")


READY_HANDOFF_ARMS = (
    ("handoff_now", "now", 1),
    ("defer_once", "defer-once", 2),
)


def ready_handoff_probe_no_disk(args: argparse.Namespace) -> int:
    """軸直前応答を支配するPIO C handoffへ離散介入する。"""
    calibration, reference = load_no_disk_calibration(args)
    output = args.state_dir / "response-ready-handoff-probe.json"
    if output.exists():
        raise SearchError("応答準備handoff probe出力が既にあるため上書きしない")
    axis_off = int(calibration["axis_official"])
    axis_mix = int(calibration["axis_mixed"])
    target = int(no_disk_target_specs(calibration)["response1"]["run"])
    paths: list[Path] = []
    rows = []
    try:
        _off, off_dir, off_io, _off_report, off_int = calibration_measure(
            args, True, "ready-sweep-official", with_intlog=True)
        paths.append(off_dir)
        if off_int is None:
            raise SearchError("公式armの割り込み受理ログが無い")
        arms = [("control", None, None), *READY_HANDOFF_ARMS,
                ("clock_shift_257", None, None)]
        for ordinal, (name, mode_text, mode_value) in enumerate(arms):
            actual, run_dir, iolog, report, intlog = calibration_measure(
                args, False, f"ready-{name}", with_intlog=True,
                response_ready_handoff=(target, mode_text)
                if mode_text is not None else None)
            paths.append(run_dir)
            if intlog is None:
                raise SearchError(f"{name} armの割り込み受理ログが無い")
            if name == "clock_shift_257":
                runs = shape.exchange_runs(iolog)
                inject_clock_shift((iolog, intlog),
                                   after_clock=runs[axis_mix - 4].start_clock,
                                   delta=257)
                actual = abstract_result(iolog, report)
            timing = no_disk_timing.compare(
                off_io, off_int, iolog, intlog, axis_off, axis_mix)
            receipt = response_ready_handoff_receipt(iolog)
            if mode_text is not None and (receipt is None or
                    receipt["mode"] != mode_value or receipt["count"] != 1 or
                    receipt["matched"] < 1):
                raise SearchError(f"{name} armがPIO handoff作用点へ一度だけ届いていない")
            if name == "handoff_now" and receipt["action"] not in (0, 1):
                raise SearchError("handoff_now armの作用種別が不正")
            if name == "defer_once" and receipt["action"] != 2:
                raise SearchError("defer_once armが実際のhandoffを抑止していない")
            metric = compare_result(reference, actual, ordinal,
                                    request_axis=axis_mix)
            rows.append({
                "arm": name, "handoff_mode": mode_text,
                "metrics": asdict(metric),
                "ready_clock": timing["mixed"]["one_byte_response"][
                    "main_wait_until_sub_ready"],
                "logical_arrival_mixed_minus_official":
                    timing["differences"]["logical_arrival_mixed_minus_official"],
                "receipt": receipt,
                "artifact_fingerprint": response_timing_artifact(actual, timing),
                "metric_source": metric_source_sha256(
                    iolog, intlog, report, iolog.with_suffix(".stderr.txt")),
            })
    finally:
        for path in paths:
            shutil.rmtree(path, ignore_errors=True)
    control = rows[0]
    ineffective = []
    for row in rows[1:]:
        row["artifact_changed"] = (
            row["artifact_fingerprint"] != control["artifact_fingerprint"])
        if row["handoff_mode"] is not None:
            row["observed_ready_clock_delta"] = (
                row["ready_clock"] - control["ready_clock"])
            if not row["artifact_changed"]:
                ineffective.append(row["arm"])
    diagnostic = rows[-1]
    expected_diagnostic = {
        key: value + 257
        for key, value in control["logical_arrival_mixed_minus_official"].items()
    }
    if diagnostic["logical_arrival_mixed_minus_official"] != expected_diagnostic:
        raise SearchError("clock_shift_257陽性対照が全arrival_deltaを+257動かさない")
    if not diagnostic["artifact_changed"]:
        raise SearchError("clock_shift_257陽性対照で成果物が変化しない")
    if len({row["metric_source"] for row in rows}) != len(rows):
        raise SearchError("arm別metric_sourceが一意でなく、入力流用の疑いがある")
    defer = next(row for row in rows if row["arm"] == "defer_once")
    result = ("handoff_controls_ready_wait"
              if defer["artifact_changed"] and
              defer["observed_ready_clock_delta"] != 0
              else "handoff_probe_ineffective")
    output.write_text(json.dumps({
        "version": 1, "scenario": "no_disk", "result": result,
        "probe": {
            "arms": ["control", "handoff_now", "defer_once"],
            "rationale": (
                "cpu_timing=0で待ちを支配するPIO Cのmain→sub切替を、"
                "対象読出しで即時化／次の切替1回抑止する離散介入")},
        "positive_control": "clock_shift_257",
        "ineffective_arms": ineffective,
        "arms": rows,
        "interpretation_limit": (
            "数値clock shiftは指定していない。PIO handoffが応答準備間隔を動かすかだけを判定し、"
            "要求長が動いても公式と同じ機序だとは言わない。"),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"result={result} probe=pio-handoff positive_control=clock_shift_257")
    return 0 if result == "handoff_controls_ready_wait" else 2


def probe_no_disk_256(args: argparse.Namespace) -> int:
    calibration, reference = load_no_disk_calibration(args)
    targets = (int(no_disk_target_specs(calibration)["response256"]["run"]),)
    if len(targets) > MAX_INTERVENTIONS:
        raise SearchError("同形窓の出現数が介入slot上限を超えた")
    arms = [
        ("control", ()),
        ("first", tuple(f"{run}:xor-first:1" for run in targets)),
        ("tail", tuple(f"{run}:xor-tail:1" for run in targets)),
        ("all", tuple(f"{run}:xor-all:1" for run in targets)),
    ]
    order = list(range(len(arms)))
    random.SystemRandom().shuffle(order)
    measured: dict[str, CandidateMetrics] = {}
    for run_ordinal, arm_index in enumerate(order):
        name, interventions = arms[arm_index]
        metric, _actual, _evidence = run_intervention_arm(
            args, reference, calibration, run_ordinal, name, interventions)
        measured[name] = metric
        print(f"run={run_ordinal + 1}/4 request_length_at_plus0={metric.request_length} "
              f"exchange_prefix={metric.exchange_prefix} fdc_prefix={metric.fdc_prefix} "
              f"screen={int(metric.screen_lines_match)}/"
              f"{int(metric.screen_chars_match)}/{int(metric.screen_sha256_match)}")
    out = args.state_dir / "probe256.tsv"
    with out.open("w", encoding="utf-8") as fp:
        fp.write("scope\trequest_length_at_plus0\texchange_prefix\tfdc_prefix\t"
                 "screen_lines_match\tscreen_chars_match\tscreen_sha256_match\t"
                 "screen_line_count\tscreen_char_count\tscreen_sha256\n")
        for name, _ in arms:
            m = measured[name]
            fp.write(f"{name}\t{m.request_length}\t{m.exchange_prefix}\t{m.fdc_prefix}\t"
                     f"{int(m.screen_lines_match)}\t{int(m.screen_chars_match)}\t"
                     f"{int(m.screen_sha256_match)}\t{m.screen_line_count}\t"
                     f"{m.screen_char_count}\t{m.screen_sha256}\n")
    print(f"summary={out}")
    print("注: 応答run長256は校正済みで全arm不変。first/tail/allで値の効く粒度を比較する")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("calibrate", "attribute", "timing",
                                         "interrupt-attribute",
                                         "ready-sweep", "ready-handoff-probe",
                                         "probe256", "search"))
    parser.add_argument("--scenario", choices=("unreadable_disk", "no_disk"),
                        default="unreadable_disk")
    parser.add_argument("--target", choices=("response1", "response256"),
                        default="response1")
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--frames", required=True, type=int)
    parser.add_argument("--jobs", type=int, default=1,
                        help="searchの同時実行数（既定1）")
    parser.add_argument("--timeout", type=int, default=120,
                        help="各走の秒上限（既定120）")
    parser.add_argument("--verbose", action="store_true",
                        help="timingでのみ全量遷移列を別ファイルへ保存")
    parser.add_argument("--core", type=Path)
    parser.add_argument("--frontend", type=Path)
    args = parser.parse_args()
    if args.frames <= 700 or args.jobs <= 0 or args.timeout <= 0:
        parser.error("--framesは701以上、--jobs/--timeoutは1以上が必要")
    try:
        if args.mode == "calibrate":
            return calibrate(args)
        if args.mode == "attribute":
            if args.scenario != "no_disk":
                raise SearchError("attributeは--scenario no_disk専用")
            return attribute_no_disk(args)
        if args.mode == "timing":
            if args.scenario != "no_disk":
                raise SearchError("timingは--scenario no_disk専用")
            return timing_no_disk(args)
        if args.mode == "interrupt-attribute":
            if args.scenario != "no_disk":
                raise SearchError("interrupt-attributeは--scenario no_disk専用")
            return interrupt_attribute_no_disk(args)
        if args.mode == "ready-sweep":
            if args.scenario != "no_disk":
                raise SearchError("ready-sweepは--scenario no_disk専用")
            return ready_sweep_no_disk(args)
        if args.mode == "ready-handoff-probe":
            if args.scenario != "no_disk":
                raise SearchError("ready-handoff-probeは--scenario no_disk専用")
            return ready_handoff_probe_no_disk(args)
        if args.mode == "probe256":
            if args.scenario != "no_disk":
                raise SearchError("probe256は--scenario no_disk専用")
            return probe_no_disk_256(args)
        return search(args)
    except (OSError, ValueError, SearchError, subprocess.SubprocessError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
