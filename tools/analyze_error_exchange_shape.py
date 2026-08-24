#!/usr/bin/env python3
"""エラー経路のFDC分岐を軸にmain⇔sub交換runの形だけを比較する。

入力は ``conform_l3.sh`` の no_disk / unreadable_disk で生成される生iolog。
出力は方向、長さ、件数、位置、公開FDC分類だけで、データ値は出さない。
交換側のパーサはvalue列をイベントへ格納せず、既知要求形式との位置別一致を
真偽へ変換した後はvalue文字列も保持しない。

FDCのコマンド名・unit/head・ST0/ST1/ST3分類は
``compare_l3_entry_fdc.py`` の既存分類を再利用する。
終了コードは解析成功=0、解析不能=2。
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import cmp_io  # noqa: E402
import compare_drive_request_runs as drive_runs  # noqa: E402
import compare_l3_entry_fdc as entry_fdc  # noqa: E402
import analyze_write_path as awp  # noqa: E402


# valueは正規表現で認識するが、ShapeEventには入れない。
ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+"
    r"([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2}|--)\s+([0-9A-Fa-f]{4})\s*$"
)
FIXED8_TOKENS = tuple(
    None if value is None else f"{value:02X}" for value in drive_runs.FIXED8
)


@dataclass(frozen=True)
class ShapeEvent:
    seq: int
    clock: int
    frame: int
    direction: str
    # 生値ではなく「既知固定形式の各位置に一致するか」だけを持つ。
    fixed8_position_mask: int = field(repr=False, compare=False)


@dataclass(frozen=True)
class ShapeRun:
    direction: str
    length: int
    start_clock: int
    end_clock: int
    start_frame: int
    end_frame: int
    request_class: str | None


@dataclass(frozen=True)
class FdcCommandShape:
    name: str
    unit_head: str
    statuses: tuple[str, ...]
    clock: int


def parse_shape_events(path: Path) -> list[ShapeEvent]:
    """交換イベントを読む。返却構造にvalueを持つフィールドは存在しない。"""
    events: list[ShapeEvent] = []
    with cmp_io._open_iolog(str(path)) as fp:
        for line in fp:
            match = ROW_RE.match(line)
            if not match:
                continue
            seq_s, clock_s, frame_s, cpu, kind, port, value_token, pc = match.groups()
            port, pc = port.upper(), pc.upper()
            if cpu != "main":
                continue
            if kind == "OUT" and port == "00FD" and pc in m2s.SEND_PCS:
                direction = "main→sub"
                token = value_token.upper()
                mask = 0
                if token != "--":
                    for pos, expected in enumerate(FIXED8_TOKENS):
                        if expected is None or token == expected:
                            mask |= 1 << pos
            elif kind == "IN" and port == "00FC" and (
                pc in m2s.RECV_HANDSHAKE_PCS or pc in m2s.RECV_BULK_PCS
            ):
                direction = "sub→main"
                mask = 0
            else:
                continue
            events.append(ShapeEvent(int(seq_s), int(clock_s), int(frame_s),
                                     direction, mask))
    events.sort(key=lambda event: (event.clock, event.seq))
    return events


def classify_request(events: list[ShapeEvent]) -> str | None:
    if not events or events[0].direction != "main→sub":
        return None
    if len(events) == 8:
        fixed = all(
            event.fixed8_position_mask & (1 << pos)
            for pos, event in enumerate(events)
        )
        if fixed:
            return "固定8バイト要求（1.11/1.23節・交換#3形式）"
        return "8バイト要求（既知固定形式とは不一致）"
    if len(events) == 2:
        return "2バイト要求（交換#4等と同長、値形式未分類）"
    return "既知要求形式に未分類"


def exchange_runs(path: Path) -> list[ShapeRun]:
    events = parse_shape_events(path)
    if not events:
        raise ValueError("main⇔sub交換イベントが無い")
    grouped: list[list[ShapeEvent]] = []
    for event in events:
        if grouped and grouped[-1][-1].direction == event.direction:
            grouped[-1].append(event)
        else:
            grouped.append([event])
    return [
        ShapeRun(group[0].direction, len(group), group[0].clock,
                 group[-1].clock, group[0].frame, group[-1].frame,
                 classify_request(group))
        for group in grouped
    ]


def fdc_shapes(path: Path) -> list[FdcCommandShape]:
    """既存FDC分類器を値なしの不変構造へ直ちに射影する。"""
    _names, commands, _rows = entry_fdc.command_names(path)
    shapes: list[FdcCommandShape] = []
    for command in commands:
        params = command.param_values or []
        if command.opcode not in (0x03, 0x08) and params:
            unit = entry_fdc.drive_head(params[0])
        else:
            unit = "対象外"
        statuses = tuple(
            f"{field_name}={entry_fdc.describe_status(field_name, value)}"
            for field_name, value in entry_fdc.status_fields(command)
            if field_name in ("ST0", "ST1", "ST3")
        )
        shapes.append(FdcCommandShape(awp.NAMES[command.opcode], unit,
                                      statuses, command.clock))
    return shapes


def fdc_divergence(official: list[FdcCommandShape], mixed: list[FdcCommandShape]) -> int:
    common = min(len(official), len(mixed))
    for pos in range(common):
        if official[pos].name != mixed[pos].name:
            return pos
    if len(official) != len(mixed):
        return common
    raise ValueError("FDCコマンド種別列が全長一致し、分岐軸を定義できない")


def request_axis(runs: list[ShapeRun], clock: int) -> int:
    candidates = [
        pos for pos, run in enumerate(runs)
        if run.direction == "main→sub" and run.start_clock <= clock
    ]
    if not candidates:
        raise ValueError("FDC分岐以前のmain→sub要求runが無い")
    return candidates[-1]


def next_response(runs: list[ShapeRun], axis: int) -> tuple[int, ShapeRun] | None:
    for pos in range(axis + 1, len(runs)):
        if runs[pos].direction == "sub→main":
            return pos, runs[pos]
    return None


def run_cell(runs: list[ShapeRun], pos: int) -> str:
    if pos < 0 or pos >= len(runs):
        return "—"
    run = runs[pos]
    extra = f"、{run.request_class}" if run.request_class else ""
    return f"{run.direction} 長さ={run.length}{extra}"


def command_cell(command: FdcCommandShape | None) -> str:
    if command is None:
        return "列終端"
    statuses = "、".join(command.statuses) if command.statuses else "結果分類なし"
    return f"{command.name}、unit/head={command.unit_head}、{statuses}"


def structural_prefix(a: list[ShapeRun], b: list[ShapeRun]) -> int:
    common = min(len(a), len(b))
    for pos in range(common):
        if (a[pos].direction, a[pos].length) != (b[pos].direction, b[pos].length):
            return pos
    return common


def build_report(official_path: Path, mixed_path: Path, label: str,
                 before: int, after: int) -> str:
    official_runs = exchange_runs(official_path)
    mixed_runs = exchange_runs(mixed_path)
    official_fdc = fdc_shapes(official_path)
    mixed_fdc = fdc_shapes(mixed_path)
    divergence = fdc_divergence(official_fdc, mixed_fdc)
    official_command = official_fdc[divergence] if divergence < len(official_fdc) else None
    mixed_command = mixed_fdc[divergence] if divergence < len(mixed_fdc) else None
    axis_clock_off = official_command.clock if official_command else official_fdc[-1].clock
    axis_clock_mix = mixed_command.clock if mixed_command else mixed_fdc[-1].clock
    axis_off = request_axis(official_runs, axis_clock_off)
    axis_mix = request_axis(mixed_runs, axis_clock_mix)
    response_off = next_response(official_runs, axis_off)
    response_mix = next_response(mixed_runs, axis_mix)
    prefix = structural_prefix(official_runs, mixed_runs)

    lines = [
        f"# エラー交換構造: {label}", "",
        "軸: FDCコマンド種別の最初の分岐以前で最後に始まったmain→sub要求runを相対位置0とする。",
        f"FDCコマンド種別の一致prefix: {divergence}件",
        f"FDC分岐位置: {divergence + 1}件目",
        f"公式FDC分類: {command_cell(official_command)}",
        f"混成FDC分類: {command_cell(mixed_command)}",
        f"交換run構造の先頭一致prefix: {prefix}件（公式{len(official_runs)}件／混成{len(mixed_runs)}件）",
        "",
    ]
    req_off, req_mix = official_runs[axis_off], mixed_runs[axis_mix]
    if (req_off.direction, req_off.length, req_off.request_class) == (
        req_mix.direction, req_mix.length, req_mix.request_class
    ):
        lines.append(
            f"分岐直前の共通要求: main→sub 長さ={req_off.length}、{req_off.request_class}"
        )
    else:
        lines.append("分岐直前の要求形: 公式・混成で不一致")
        lines.append(f"  公式: {run_cell(official_runs, axis_off)}")
        lines.append(f"  混成: {run_cell(mixed_runs, axis_mix)}")
    if response_off:
        response_pos, response = response_off
        lines.append(
            f"公式の分岐後応答run: sub→main 長さ={response.length}（相対位置+{response_pos - axis_off}）"
        )
    else:
        lines.append("公式の分岐後応答run: 観測窓内になし")
    if response_mix:
        response_pos, response = response_mix
        lines.append(
            f"同じ軸で混成が行う応答run: sub→main 長さ={response.length}（相対位置+{response_pos - axis_mix}）"
        )
    else:
        lines.append("同じ軸で混成が行う応答run: 観測窓内になし")

    lines.extend(["", "## 分岐軸前後のrun列", "", "| 相対位置 | 公式 | 混成 |", "|---:|---|---|"])
    for relative in range(-before, after + 1):
        lines.append(
            f"| {relative:+d} | {run_cell(official_runs, axis_off + relative)} | "
            f"{run_cell(mixed_runs, axis_mix + relative)} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official", required=True, type=Path)
    parser.add_argument("--mixed", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--before", type=int, default=4)
    parser.add_argument("--after", type=int, default=6)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.before < 0 or args.after < 0:
        print("解析不能: --before/--afterは0以上が必要", file=sys.stderr)
        return 2
    try:
        report = build_report(args.official, args.mixed, args.label,
                              args.before, args.after)
    except (OSError, ValueError, awp.SafeError):
        # 例外本文には入力値が含まれ得るため、情報境界上表示しない。
        print("解析不能: 入力不足または交換/FDC構造を分類できない", file=sys.stderr)
        return 2
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
