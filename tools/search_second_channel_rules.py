#!/usr/bin/env python3
"""m7cy第2段: 候補規則を生成し、一致prefixだけを表示する。

公式・混成の値は比較器内部だけで扱い、値、最初の不一致値、前後窓は出力しない。
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402

OOB = -1  # byte範囲外の内部番兵。表示しない。


def prefix_length(base: list[int], candidate: list[int], fault: str | None = None) -> int:
    if fault == "779":
        return min(779, len(base), len(candidate))
    if fault == "match":
        return min(len(base), len(candidate))
    for i, (a, b) in enumerate(zip(base, candidate)):
        if a != b:
            return i
    return min(len(base), len(candidate))


def evaluator_selfcheck(fault: str | None = None) -> bool:
    base = [(i * 17 + 3) & 0xFF for i in range(900)]
    exact = list(base)
    extended = list(base)
    extended[820] ^= 1
    first_bad = list(base)
    first_bad[0] ^= 1
    return (prefix_length(base, exact, fault) == 900
            and prefix_length(base, extended, fault) == 820
            and prefix_length(base, first_bad, fault) == 0)


def load_values(path: Path, kind: str, port: str) -> list[int]:
    try:
        events = cmp_io.parse_iolog(str(path), "main")
    except (cmp_io.FormatError, OSError) as exc:
        raise ValueError(str(exc)) from exc
    selected = cmp_io.filter_port_kind(events, kind, port)
    if not selected:
        raise ValueError(f"main {kind} ${port[-2:]} が0件")
    values = []
    for event in selected:
        try:
            values.append(int(event.value, 16))
        except ValueError as exc:
            raise ValueError("伏せ字済みログは規則探索に使えない") from exc
    return values


def rol(v: int, n: int) -> int:
    return ((v << n) | (v >> (8 - n))) & 0xFF


def ror(v: int, n: int) -> int:
    return ((v >> n) | (v << (8 - n))) & 0xFF


def crc_update(crc: int, value: int, poly: int, reflected: bool) -> int:
    crc ^= value
    for _ in range(8):
        if reflected:
            crc = ((crc >> 1) ^ poly) if (crc & 1) else (crc >> 1)
        else:
            crc = (((crc << 1) & 0xFF) ^ poly) if (crc & 0x80) else ((crc << 1) & 0xFF)
    return crc & 0xFF


def cumulative(source: list[int], op: str, init: int, after: bool,
               poly: int = 0, reflected: bool = False) -> list[int]:
    state = init
    out = []
    for value in source:
        if not after:
            out.append(state)
        if op == "sum":
            state = (state + value) & 0xFF
        elif op == "xor":
            state ^= value
        else:
            state = crc_update(state, value, poly, reflected)
        if after:
            out.append(state)
    return out


def indexed(source: list[int], indexes: Iterable[int]) -> list[int]:
    return [source[i] if 0 <= i < len(source) else OOB for i in indexes]


def rule_candidates(first: list[int], current_second: list[int]) -> list[tuple[str, list[int]]]:
    n = len(first)
    interleaved = []
    for second, first_value in zip(current_second, first):
        interleaved.extend((second, first_value))
    rules: list[tuple[str, list[int]]] = [("現行規則", list(current_second))]
    for k in range(-4, 5):
        rules.append((f"位置(i{ k:+d})&FF", [((i + k) & 0xFF) for i in range(n)]))
    for k in range(-4, 5):
        rules.append((f"offset:D[2i+1{ k:+d}]", indexed(interleaved, (2*i+1+k for i in range(n)))))
    rules.extend([
        ("加工:補数", [(256-v) & 0xFF for v in first]),
        ("加工:ビット反転", [v ^ 0xFF for v in first]),
        ("加工:D+i", [(v+i) & 0xFF for i, v in enumerate(first)]),
    ])
    for constant in range(256):
        rules.append((f"加工:XOR定数{constant}", [v ^ constant for v in first]))
    for nrot in range(1, 8):
        rules.append((f"加工:ROL{nrot}", [rol(v, nrot) for v in first]))
        rules.append((f"加工:ROR{nrot}", [ror(v, nrot) for v in first]))
    for delta in (-4096, -2048, -512, 512, 2048, 4096):
        rules.append((f"別バッファ起点:byte{delta:+d}",
                      indexed(interleaved, (2*i+1+delta for i in range(n)))))
    rules.append(("対の入れ替え:第2へ第1", list(first)))
    for op in ("sum", "xor"):
        for init in (0, 255):
            for after in (False, True):
                rules.append((f"累積:{op}:init{init}:{'after' if after else 'before'}",
                              cumulative(first, op, init, after)))
    for poly in (0x07, 0x1D, 0x31, 0x9B):
        for init in (0, 255):
            for reflected in (False, True):
                for after in (False, True):
                    rules.append((f"累積:CRC8-poly{poly:02X}:init{init}:ref{int(reflected)}:"
                                  f"{'after' if after else 'before'}",
                                  cumulative(first, "crc", init, after, poly, reflected)))
    return rules


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("official", type=Path)
    ap.add_argument("mixed", type=Path)
    ap.add_argument("--pre", type=int, default=779)
    ap.add_argument("--bulk", type=int, default=5635)
    ap.add_argument("--fault-prefix-779", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--fault-always-match", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    fault = "779" if args.fault_prefix_779 else "match" if args.fault_always_match else None
    if not evaluator_selfcheck(fault):
        print("エラー: 判定器の合成陽性・陰性対照に失敗", file=sys.stderr)
        return 2
    if args.pre < 0 or args.bulk < 1:
        print("エラー: --preは0以上、--bulkは1以上", file=sys.stderr)
        return 2
    try:
        base_second = load_values(args.official, "IN", "00FC")
        target_second = load_values(args.mixed, "IN", "00FC")
        base_first = load_values(args.official, "IN", "00FD")
        target_first = load_values(args.mixed, "IN", "00FD")
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2
    if min(len(base_second), len(target_second)) < args.pre + args.bulk:
        print("エラー: 第2チャンネルが指定区間より短い", file=sys.stderr)
        return 2
    if len(base_first) != args.bulk or len(target_first) != args.bulk:
        print("エラー: 第1チャンネル件数が--bulkと一致しない", file=sys.stderr)
        return 2

    target_bulk_second = target_second[args.pre:args.pre + args.bulk]
    raw_rules = rule_candidates(target_first, target_bulk_second)
    unique: dict[tuple[int, ...], list[str]] = {}
    for label, candidate in raw_rules:
        unique.setdefault(tuple(candidate), []).append(label)
    print("判定器自己検査: 合成完全一致・伸長・先頭不一致を検出")
    print(f"列挙条件数: {len(raw_rules)}")
    print(f"重複除外後候補数: {len(unique)}")
    prefixes = []
    suffix = target_second[args.pre + args.bulk:]
    preamble = target_second[:args.pre]
    for candidate_tuple, labels in unique.items():
        full = preamble + list(candidate_tuple) + suffix
        prefix = prefix_length(base_second, full)
        prefixes.append(prefix)
        print(f"候補={'|'.join(labels)}\tprefix={prefix}")
    swapped_first = target_bulk_second
    swapped_prefix = prefix_length(base_first, swapped_first)
    print(f"陰性対照:対を入れ替えた第1チャンネルprefix={swapped_prefix}/{len(base_first)}")
    hist = Counter(prefixes)
    print("prefix度数: " + ", ".join(f"{p}:{n}" for p, n in sorted(hist.items())))
    print(f"最大prefix: {max(prefixes)}")
    print(f"779超候補数: {sum(p > 779 for p in prefixes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
