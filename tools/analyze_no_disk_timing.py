#!/usr/bin/env python3
"""no_disk の +0 分岐軸前後を、値を残さず時間構造だけで比較する。

出力へ残すのは割り込み件数、共通基準からの相対 clock、確定済みの
$FE bit0..3 の変化ラベル、イベント間隔だけである。交換値、$FE の生値、
PC、割り込みレベルは出力構造へ入れない。
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_error_exchange_shape as shape  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_sub_proto as sub_proto  # noqa: E402


class TimingError(ValueError):
    pass


DROP_RE = re.compile(r"^# 取りこぼし:\s*(\d+)件")
CONFIRMED_FE_BITS = (0, 1, 2, 3)
LOGICAL_POSITIONS = (-3, -2, -1, 0)
MAIN_RECV_BEFORE_PCS = frozenset(
    pc for pc, label in m2s.WAIT_LOOP_PCS.items() if label.startswith("RECV前"))


@dataclass(frozen=True)
class Bounds:
    reference: int
    pre_axis_start: int
    axis_clock: int
    window_end: int
    near_start: int


def require_no_drops(path: Path) -> None:
    dropped = 0
    with shape.cmp_io._open_iolog(str(path)) as fp:
        for line in fp:
            match = DROP_RE.match(line)
            if match:
                dropped += int(match.group(1))
    if dropped:
        raise TimingError(f"ログに取りこぼしがあるため不採用（{dropped}件）")


def bounds(runs: list[shape.ShapeRun], axis: int) -> Bounds:
    if axis < 4 or axis >= len(runs):
        raise TimingError("校正軸が相対-4〜+0へ届かない")
    return Bounds(
        reference=runs[axis - 4].start_clock,
        pre_axis_start=runs[axis - 4].start_clock,
        axis_clock=runs[axis].start_clock,
        window_end=runs[axis].end_clock,
        near_start=runs[axis - 1].start_clock,
    )


def in_range(clock: int, start: int, end: int, *, inclusive_end: bool = False) -> bool:
    return start <= clock <= end if inclusive_end else start <= clock < end


def interrupt_counts(intlog: Path, b: Bounds, *, fault_constant: bool = False) -> dict:
    require_no_drops(intlog)
    events = sub_proto.parse_intlog(intlog)
    result: dict[str, dict[str, int]] = {}
    for cpu in ("main", "sub"):
        calibration_window = sum(
            in_range(event.clock, b.pre_axis_start, b.window_end, inclusive_end=True)
            for event in events[cpu])
        near_axis = sum(in_range(event.clock, b.near_start, b.window_end,
                                 inclusive_end=True)
                        for event in events[cpu])
        if fault_constant:
            # selftest専用。実測CLIからは指定できない。
            calibration_window = near_axis = 0
        result[cpu] = {"calibration_window": calibration_window,
                       "axis_near": near_axis}
    return result


def logical_arrivals(runs: list[shape.ShapeRun], axis: int,
                     b: Bounds) -> dict[str, int]:
    return {f"{relative:+d}": runs[axis + relative].start_clock - b.reference
            for relative in LOGICAL_POSITIONS}


def fe_transition_summary(rows: list[m2s.Ev], b: Bounds, cpu: str,
                          *, fault_shift: int = 0) -> dict:
    samples = [row for row in rows
               if row.cpu == cpu and row.kind == "IN" and row.port == "00FE"
               and in_range(row.clock, b.pre_axis_start, b.axis_clock)]
    if any(row.value is None for row in samples):
        raise TimingError("$FE が伏せ字のため確定済みビット遷移を比較できない")
    transitions = []
    previous = None
    previous_clock = None
    for row in samples:
        projected = tuple((int(row.value) >> bit) & 1 for bit in CONFIRMED_FE_BITS)
        if previous is not None and projected != previous:
            changes = []
            for index, bit in enumerate(CONFIRMED_FE_BITS):
                if projected[index] != previous[index]:
                    changes.append(f"bit{bit}{'up' if projected[index] else 'down'}")
            transitions.append({
                "changes": changes,
                "phase_from_reference": row.clock - b.reference + fault_shift,
                "interval_from_previous_fe": row.clock - int(previous_clock),
            })
        previous = projected
        previous_clock = row.clock
    return {"fe_reads": len(samples), "transition_count": len(transitions),
            "transitions": transitions}


def one_byte_response_timing(rows: list[m2s.Ev], runs: list[shape.ShapeRun],
                             axis: int) -> dict[str, int]:
    response = runs[axis - 1]
    if response.direction != "sub→main" or response.length != 1:
        raise TimingError("軸直前が1バイト応答runでない")
    read_clock = response.start_clock
    lower = runs[axis - 2].end_clock
    waits = [row.clock for row in rows
             if row.cpu == "main" and row.kind == "IN" and row.port == "00FE"
             and row.pc in MAIN_RECV_BEFORE_PCS
             and lower < row.clock < read_clock]
    prepared = [row.clock for row in rows
                if row.cpu == "sub" and row.kind == "OUT" and row.port == "00FD"
                and lower < row.clock < read_clock]
    if not waits or not prepared:
        raise TimingError("軸直前1バイト応答の待ち開始またはsub準備を同定できない")
    wait_start = waits[0]
    ready_clock = prepared[-1]
    if not wait_start <= ready_clock <= read_clock:
        raise TimingError("軸直前1バイト応答の時間順序が不正")
    return {
        "main_wait_until_sub_ready": ready_clock - wait_start,
        "sub_ready_until_main_read": read_clock - ready_clock,
    }


def summarize_run(iolog: Path, intlog: Path, axis: int, *,
                  fault_constant_counts: bool = False,
                  fault_shift_phase: int = 0) -> dict:
    require_no_drops(iolog)
    runs = shape.exchange_runs(iolog)
    b = bounds(runs, axis)
    rows, _masked = m2s.parse_iolog(iolog)
    return {
        "interrupt_counts": interrupt_counts(
            intlog, b, fault_constant=fault_constant_counts),
        "logical_arrival_from_reference": logical_arrivals(runs, axis, b),
        "fe_handshake": {
            cpu: fe_transition_summary(rows, b, cpu, fault_shift=fault_shift_phase)
            for cpu in ("main", "sub")
        },
        "one_byte_response": one_byte_response_timing(rows, runs, axis),
    }


def numeric_delta(left: dict, right: dict) -> dict:
    return {key: int(right[key]) - int(left[key]) for key in left}


def compare(official_iolog: Path, official_intlog: Path, mixed_iolog: Path,
            mixed_intlog: Path, axis_official: int, axis_mixed: int, *,
            fault_constant_counts: bool = False,
            fault_shift_phase_mixed: int = 0) -> dict:
    official = summarize_run(
        official_iolog, official_intlog, axis_official,
        fault_constant_counts=fault_constant_counts)
    mixed = summarize_run(
        mixed_iolog, mixed_intlog, axis_mixed,
        fault_constant_counts=fault_constant_counts,
        fault_shift_phase=fault_shift_phase_mixed)
    return {
        "schema": "pc88-no-disk-timing-v1",
        "official": official,
        "mixed": mixed,
        "differences": {
            "interrupt_counts_mixed_minus_official": {
                cpu: numeric_delta(official["interrupt_counts"][cpu],
                                   mixed["interrupt_counts"][cpu])
                for cpu in ("main", "sub")
            },
            "logical_arrival_mixed_minus_official": numeric_delta(
                official["logical_arrival_from_reference"],
                mixed["logical_arrival_from_reference"]),
            "one_byte_response_mixed_minus_official": numeric_delta(
                official["one_byte_response"], mixed["one_byte_response"]),
            "fe_sequence_equal": {
                cpu: official["fe_handshake"][cpu] == mixed["fe_handshake"][cpu]
                for cpu in ("main", "sub")
            },
        },
        "information_boundary": (
            "交換値・$FE生値・PC・割り込みlevel・絶対clockは保存しない。"
            "確定済みbit0..3の変化ラベル、件数、共通基準からの位相、間隔のみ。"
        ),
    }


def compact_positions(positions: list[int]) -> str:
    if not positions:
        return "なし"
    groups = []
    start = previous = positions[0]
    for value in positions[1:]:
        if value == previous + 1:
            previous = value
            continue
        groups.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = value
    groups.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(groups)


def periodic_summary(transitions: list[dict]) -> dict:
    """変化ラベル/間隔列を周期・件数・逸脱位置へ圧縮する。"""
    keys = [(tuple(item["changes"]), item["interval_from_previous_fe"])
            for item in transitions]
    n = len(keys)
    if not keys:
        return {"count": 0, "period": 0, "deviation_positions": []}
    max_period = min(64, max(1, n // 2))
    candidates = []
    for period in range(1, max_period + 1):
        baseline = []
        deviations = []
        for residue in range(period):
            values = keys[residue::period]
            common = max(set(values), key=lambda value: (values.count(value), value))
            baseline.append(common)
        for index, value in enumerate(keys):
            if value != baseline[index % period]:
                deviations.append(index)
        candidates.append((len(deviations), period, deviations))
    _count, period, deviations = min(candidates)
    return {"count": n, "period": period,
            "deviation_positions": deviations}


def transition_difference_positions(left: list[dict], right: list[dict]) -> list[int]:
    sentinel = object()
    return [index for index, (a, b) in enumerate(itertools.zip_longest(
        left, right, fillvalue=sentinel)) if a != b]


def compact_result(result: dict) -> dict:
    """既定JSONから全遷移列を外し、差を取りこぼさない要約へ置換する。"""
    value = copy.deepcopy(result)
    for cpu in ("main", "sub"):
        off = result["official"]["fe_handshake"][cpu]["transitions"]
        mix = result["mixed"]["fe_handshake"][cpu]["transitions"]
        value["official"]["fe_handshake"][cpu]["summary"] = periodic_summary(off)
        value["mixed"]["fe_handshake"][cpu]["summary"] = periodic_summary(mix)
        value["official"]["fe_handshake"][cpu].pop("transitions", None)
        value["mixed"]["fe_handshake"][cpu].pop("transitions", None)
        value["differences"].setdefault("fe_transition_difference_positions", {})[
            cpu] = transition_difference_positions(off, mix)
    return value


def report_lines(result: dict, *, verbose: bool = False) -> list[str]:
    off, mix, diff = result["official"], result["mixed"], result["differences"]
    lines = ["# no_disk +0前後 時間構造比較", ""]
    for cpu in ("main", "sub"):
        o = off["interrupt_counts"][cpu]
        m = mix["interrupt_counts"][cpu]
        lines.append(
            f"割り込み受理 {cpu}: 校正窓 公式{o['calibration_window']}件／混成{m['calibration_window']}件、"
            f"軸近傍 公式{o['axis_near']}件／混成{m['axis_near']}件")
    lines.append("同じ論理位置への到達clock差（混成-公式、相対基準）: " + ", ".join(
        f"{pos}={delta}" for pos, delta in
        diff["logical_arrival_mixed_minus_official"].items()))
    for cpu in ("main", "sub"):
        o = off["fe_handshake"][cpu]
        m = mix["fe_handshake"][cpu]
        positions = transition_difference_positions(o["transitions"], m["transitions"])
        if (o["fe_reads"] != m["fe_reads"] or
                o["transition_count"] != m["transition_count"] or positions):
            osum, msum = periodic_summary(o["transitions"]), periodic_summary(m["transitions"])
            lines.append(
                f"$FE {cpu}差: 読み 公式{o['fe_reads']}／混成{m['fe_reads']}、"
                f"遷移 公式{o['transition_count']}／混成{m['transition_count']}、"
                f"差異位置={compact_positions(positions)}")
            lines.append(
                f"  公式要約: 周期{osum['period']}、件数{osum['count']}、"
                f"逸脱位置={compact_positions(osum['deviation_positions'])}")
            lines.append(
                f"  混成要約: 周期{msum['period']}、件数{msum['count']}、"
                f"逸脱位置={compact_positions(msum['deviation_positions'])}")
        if verbose:
            for label, summary in (("公式", o), ("混成", m)):
                cells = [
                    f"{'+'.join(item['changes'])}@位相{item['phase_from_reference']}"
                    f"/間隔{item['interval_from_previous_fe']}"
                    for item in summary["transitions"]
                ]
                lines.append(f"  {label}遷移列（全量）: {'; '.join(cells) if cells else 'なし'}")
    o = off["one_byte_response"]
    m = mix["one_byte_response"]
    lines.append(
        "軸直前1バイト応答: main待機→sub準備 "
        f"公式{o['main_wait_until_sub_ready']}／混成{m['main_wait_until_sub_ready']} clock、"
        "sub準備→main読取 "
        f"公式{o['sub_ready_until_main_read']}／混成{m['sub_ready_until_main_read']} clock")
    lines.extend(["", "情報境界: " + result["information_boundary"]])
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-iolog", required=True, type=Path)
    parser.add_argument("--official-intlog", required=True, type=Path)
    parser.add_argument("--mixed-iolog", required=True, type=Path)
    parser.add_argument("--mixed-intlog", required=True, type=Path)
    parser.add_argument("--axis-official", required=True, type=int)
    parser.add_argument("--axis-mixed", required=True, type=int)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verbose", action="store_true",
                        help="遷移列の全量を出す（既定は差分要約のみ）")
    args = parser.parse_args()
    try:
        result = compare(args.official_iolog, args.official_intlog,
                         args.mixed_iolog, args.mixed_intlog,
                         args.axis_official, args.axis_mixed)
        text = "\n".join(report_lines(result, verbose=args.verbose)) + "\n"
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        if args.json_out:
            args.json_out.write_text(
                json.dumps(result if args.verbose else compact_result(result),
                           ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    except (OSError, TimingError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
