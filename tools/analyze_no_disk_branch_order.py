#!/usr/bin/env python3
"""no_disk の FDC 55件目と交換 +0 を共通clock上で順序付ける。

出力へ交換/FDCの生値、PC、絶対clockは残さない。各armの相対clock、
clock差、間にある記録イベント数、および混成FDCが属する交換runだけを返す。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_error_exchange_shape as shape  # noqa: E402
import analyze_no_disk_timing as timing  # noqa: E402
import analyze_sub_proto as sub_proto  # noqa: E402


class OrderError(ValueError):
    pass


EXPECTED_DIVERGENCE = 54  # 0 origin = 55件目


def _clock_stream(iolog: Path, intlog: Path | None) -> list[tuple[int, str]]:
    timing.require_no_drops(iolog)
    rows, _masked = shape.m2s.parse_iolog(iolog)
    events = [(row.clock, row.cpu) for row in rows]
    if intlog is not None:
        timing.require_no_drops(intlog)
        ints = sub_proto.parse_intlog(intlog)
        events.extend((event.clock, event.cpu)
                      for cpu in ("main", "sub") for event in ints[cpu])
    events.sort()
    if not events:
        raise OrderError("共通clock付きイベントが無い")
    clocks = [clock for clock, _cpu in events]
    if len(clocks) != len(set(clocks)):
        raise OrderError("main/subまたはio/int間でclockが重複し、共通時計でない")
    cpus = {cpu for _clock, cpu in events}
    if cpus != {"main", "sub"}:
        raise OrderError("共通clock列がmain/subの両方を貫いていない")
    if not any(events[pos - 1][1] != events[pos][1]
               for pos in range(1, len(events))):
        raise OrderError("共通clock列でmain/subの交差を確認できない")
    return events


def _event_gap(events: list[tuple[int, str]], left: int, right: int) -> int:
    lo, hi = sorted((left, right))
    return sum(lo < clock < hi for clock, _cpu in events)


def _arm(iolog: Path, intlog: Path | None, axis: int,
         command: shape.FdcCommandShape) -> dict:
    runs = shape.exchange_runs(iolog)
    if axis < 4 or axis >= len(runs):
        raise OrderError("交換軸が相対-4〜+0へ届かない")
    exchange = runs[axis]
    if exchange.direction != "main→sub":
        raise OrderError("交換+0がmain→subでない")
    anchor = runs[axis - 4].start_clock
    fdc_clock = command.clock
    exchange_clock = exchange.start_clock
    if fdc_clock < exchange_clock:
        order = "fdc_first"
    elif exchange_clock < fdc_clock:
        order = "exchange_first"
    else:
        raise OrderError("FDC分岐と交換+0が同一clockになっている")
    events = _clock_stream(iolog, intlog)
    return {
        "order": order,
        "fdc_clock_from_anchor": fdc_clock - anchor,
        "exchange_clock_from_anchor": exchange_clock - anchor,
        "clock_distance": abs(fdc_clock - exchange_clock),
        "events_strictly_between": _event_gap(events, fdc_clock, exchange_clock),
        "shared_clock": {
            "unique_across_streams": True,
            "covers_main_and_sub": True,
            "main_sub_interleaving_observed": True,
            "includes_intlog": intlog is not None,
        },
    }


def _mixed_association(iolog: Path, axis: int,
                       command: shape.FdcCommandShape) -> dict:
    runs = shape.exchange_runs(iolog)
    request_positions = [pos for pos, run in enumerate(runs)
                         if run.direction == "main→sub"
                         and run.start_clock <= command.clock]
    if not request_positions:
        return {"exchange_run_relative_to_plus0": None,
                "phase": "before_any_request", "received_events": 0,
                "run_length": None}
    pos = request_positions[-1]
    run = runs[pos]
    rows = shape.parse_shape_events(iolog)
    received = sum(event.direction == "main→sub"
                   and run.start_clock <= event.clock <= min(command.clock,
                                                              run.end_clock)
                   for event in rows)
    if run.start_clock <= command.clock <= run.end_clock:
        phase = "during_run"
    else:
        phase = "after_run_before_next_request"
    return {
        "exchange_run_relative_to_plus0": pos - axis,
        "phase": phase,
        "received_events": received,
        "run_length": run.length,
    }


def analyze(official_iolog: Path, mixed_iolog: Path,
            official_intlog: Path | None = None,
            mixed_intlog: Path | None = None) -> dict:
    official_runs = shape.exchange_runs(official_iolog)
    mixed_runs = shape.exchange_runs(mixed_iolog)
    prefix = shape.structural_prefix(official_runs, mixed_runs)
    official_fdc = shape.fdc_shapes(official_iolog)
    mixed_fdc = shape.fdc_shapes(mixed_iolog)
    divergence = shape.fdc_divergence(official_fdc, mixed_fdc)
    if divergence != EXPECTED_DIVERGENCE:
        raise OrderError("FDC分岐が55件目でない")
    off_cmd, mix_cmd = official_fdc[divergence], mixed_fdc[divergence]
    if off_cmd.name != "SENSE DRIVE STATUS" or mix_cmd.name != "READ DATA":
        raise OrderError("55件目が公式SENSE DRIVE STATUS／混成READ DATAでない")
    # 交換+0はFDC clockから逆算しない。構造prefixの直後として独立に置く。
    # request_axis(command.clock)を使うと「FDCが先」の入力で直前runへ軸が
    # 移り、調べたい順序を前提としてしまうためである。
    axis_off = prefix
    axis_mix = prefix
    expected = (prefix == 36
                and (official_runs[axis_off].direction,
                     official_runs[axis_off].length) == ("main→sub", 5)
                and (mixed_runs[axis_mix].direction,
                     mixed_runs[axis_mix].length) == ("main→sub", 6))
    if not expected:
        raise OrderError("交換分岐がprefix36・+0の5対6でない")
    result = {
        "schema": "pc88-no-disk-branch-order-v1",
        "fdc_divergence_ordinal": divergence + 1,
        "exchange_prefix": prefix,
        "official": _arm(official_iolog, official_intlog, axis_off, off_cmd),
        "mixed": _arm(mixed_iolog, mixed_intlog, axis_mix, mix_cmd),
        "mixed_fdc_association": _mixed_association(mixed_iolog, axis_mix,
                                                     mix_cmd),
        "information_boundary": (
            "交換/FDC生値・PC・絶対clockは保存しない。相対clock、間隔、"
            "件数、方向、run相対位置、公開FDC分類だけを保存する。"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official", required=True, type=Path)
    parser.add_argument("--mixed", required=True, type=Path)
    parser.add_argument("--official-intlog", type=Path)
    parser.add_argument("--mixed-intlog", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.official, args.mixed, args.official_intlog,
                         args.mixed_intlog)
    except (OSError, ValueError, shape.awp.SafeError) as exc:
        print(f"解析不能: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    for name in ("official", "mixed"):
        arm = result[name]
        print(f"{name}: order={arm['order']} clock_distance="
              f"{arm['clock_distance']} events_between="
              f"{arm['events_strictly_between']}")
    assoc = result["mixed_fdc_association"]
    relative = assoc["exchange_run_relative_to_plus0"]
    relative_text = "none" if relative is None else f"{relative:+d}"
    print("mixed_read_data: exchange_run="
          f"{relative_text} "
          f"phase={assoc['phase']} received={assoc['received_events']}/"
          f"{assoc['run_length']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
