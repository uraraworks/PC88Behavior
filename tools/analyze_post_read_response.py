#!/usr/bin/env python3
"""m7bl: 起動時バルク後のREAD完了に続く1/1/1/256バイト交換を解析する。

入力は値を伏せていない生iologに限る。起動時高速バルクの末尾は
``analyze_main_to_sub.classify_transactions`` が分類する ``BULK_RECV`` の
最終イベントで決め、その後最初の READ DATA（FDC結果263件）を
``analyze_write_path.parse_commands`` で選ぶ。伏せ字検査は
``analyze_request_kinds.check_unredacted`` を再利用する。

既定出力は記号版である。末尾交換の3個のプロトコル値だけを表示し、最後の
256バイトは件数・方向・相対位置だけを表示して値を一切出さない。
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_request_kinds as ark  # noqa: E402
import analyze_write_path as awp  # noqa: E402

Ev = m2s.Ev


class AnalysisError(Exception):
    pass


@dataclass
class Observation:
    label: str
    start_position: int
    recv_after_read: int
    ack: int
    trigger: int
    send_count: int


def read_end_clock(rows: list[Ev]) -> int:
    """起動時バルク後、最初の結果263件READ DATAの末尾clockを返す。"""
    tx = m2s.classify_transactions(rows)
    bulk = [e for e in tx if m2s.tx_kind(e) == "BULK_RECV"]
    if not bulk:
        raise AnalysisError("起動時高速バルク(BULK_RECV)が見つからない")
    bulk_end = bulk[-1].clock

    commands = awp.parse_commands(rows)
    reads = [
        c for c in commands
        if c.clock > bulk_end and c.opcode == 0x06 and c.result_bytes == 263
    ]
    if not reads:
        raise AnalysisError("バルク後のFDC結果263件READ DATAが見つからない")
    read = reads[0]

    fb = [e for e in rows if e.cpu == "sub" and e.port == "00FB"]
    starts = [i for i, e in enumerate(fb) if e.clock == read.clock and e.kind == "OUT"]
    if len(starts) != 1:
        raise AnalysisError("READ DATA開始イベントを一意に対応付けられない")
    end_i = starts[0] + read.nparam + read.result_bytes
    if end_i >= len(fb) or fb[end_i].kind != "IN":
        raise AnalysisError("READ DATAのFDC結果末尾を対応付けられない")
    return fb[end_i].clock


def matches_tail(payload: list[Ev], i: int) -> bool:
    """位置iから IN1/OUT1/IN1/OUT256 ($FC/$FD) が続くかを値なしで判定。"""
    if i + 259 > len(payload):
        return False
    directions = [e.kind for e in payload[i:i + 259]]
    return (
        directions[:3] == ["IN", "OUT", "IN"]
        and all(k == "OUT" for k in directions[3:259])
    )


def analyze(rows: list[Ev], label: str) -> Observation:
    end_clock = read_end_clock(rows)
    commands = awp.parse_commands(rows)
    next_command = min((c.clock for c in commands if c.clock > end_clock), default=None)
    payload = [
        e for e in rows
        if e.cpu == "sub"
        and e.clock > end_clock
        and (next_command is None or e.clock < next_command)
        and ((e.kind == "IN" and e.port == "00FC")
             or (e.kind == "OUT" and e.port == "00FD"))
    ]
    starts = [i for i in range(len(payload)) if matches_tail(payload, i)]
    if len(starts) != 1:
        raise AnalysisError(
            f"READ後の受信1/送信1/受信1/送信256を一意に検出できない"
            f"(候補={len(starts)}, payload={len(payload)}件)"
        )
    i = starts[0]
    assert payload[i].value is not None
    assert payload[i + 1].value is not None
    assert payload[i + 2].value is not None
    return Observation(
        label=label,
        start_position=i + 1,
        recv_after_read=payload[i].value,
        ack=payload[i + 1].value,
        trigger=payload[i + 2].value,
        send_count=256,
    )


def render(obs: list[Observation]) -> str:
    lines = [
        "# READ完了後の応答（記号版）",
        "",
        "基準: 起動時高速バルク後、最初のREAD DATAのFDC結果263件目の直後",
        "位置: 基準後のsubデータイベント（IN $FC / OUT $FD）を1始まりで数える",
        "",
    ]
    for o in obs:
        lines.extend([
            f"## {o.label}",
            f"検出開始位置: {o.start_position}",
            f"受信1 (sub IN $FC): 0x{o.recv_after_read:02X}",
            f"送信1 ack (sub OUT $FD): 0x{o.ack:02X}",
            f"受信1 trigger (sub IN $FC): 0x{o.trigger:02X}",
            f"送信データ (sub OUT $FD): {o.send_count}件（値は非出力）",
            "起動条件: trigger受信の直後に256件送信を開始",
            "",
        ])
    for name, values in (
        ("READ完了後受信値", {o.recv_after_read for o in obs}),
        ("ack値", {o.ack for o in obs}),
        ("trigger値", {o.trigger for o in obs}),
    ):
        rendered = ", ".join(f"0x{v:02X}" for v in sorted(values))
        lines.append(f"{name}の相異数: {len(values)} ({rendered})")
    deterministic = all(len({getattr(o, f) for o in obs}) == 1 for f in (
        "recv_after_read", "ack", "trigger", "send_count"
    ))
    lines.append(f"条件間一致: {'一致' if deterministic else '不一致'}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iolog", nargs="+", required=True, type=Path)
    ap.add_argument("--label", nargs="+", required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if len(args.iolog) != len(args.label):
        print("--iolog と --label の数が違う", file=sys.stderr)
        return 2

    observations: list[Observation] = []
    try:
        for path, label in zip(args.iolog, args.label):
            rows, _masked = m2s.parse_iolog(path)
            ark.check_unredacted(rows)
            observations.append(analyze(rows, label))
    except (ark.UnanalyzableError, awp.SafeError, AnalysisError) as ex:
        msg = f"解析不可: {ex}"
        print(msg, file=sys.stderr)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(msg + "\n", encoding="utf-8")
        return 3

    report = render(observations)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
