#!/usr/bin/env python3
"""交換#4応答の生成源を、値を表示せずに分類する。

生のI/Oログを内部で比較し、応答・直前READ DATA・直前要求・FDC結果の
位置別同一/相違と一致件数だけを出力する。値や同値グループの内容は出さない。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from cmp_fdc_sectors import Event, SafeError, parse_iolog, require_value


@dataclass
class ReadTransfer:
    data: list[int]
    result: list[int]
    end_clock: int


def exchange4(events: list[Event]) -> tuple[list[int], list[int], int]:
    incoming = [e for e in events if e.port == "00FC" and e.kind == "IN"]
    response = incoming[4:260]
    if len(response) != 256:
        raise SafeError("交換#4抽出不能: main IN $FCの5件目から256件が無い")
    response_clock = response[0].clock or 0
    # main→subデータは$FD。交換#4は直前2件要求と確定済みなので、応答開始前の
    # 最後の2件を採る（値による境界判定はしない）。
    outgoing = [e for e in events
                if e.port == "00FD" and e.kind == "OUT" and (e.clock or 0) < response_clock]
    request = outgoing[-2:]
    if len(request) != 2:
        raise SafeError("交換#4抽出不能: 応答直前の2件要求が無い")
    return ([require_value(e) for e in request],
            [require_value(e) for e in response], response_clock)


def read_transfers(events: list[Event]) -> list[ReadTransfer]:
    fb = [e for e in events if e.port == "00FB"]
    transfers: list[ReadTransfer] = []
    index = 0
    while index < len(fb):
        event = fb[index]
        if event.kind != "OUT" or (require_value(event) & 0x1F) not in (0x02, 0x06, 0x0C):
            index += 1
            continue
        if index + 8 >= len(fb) or any(e.kind != "OUT" for e in fb[index:index + 9]):
            index += 1
            continue
        index += 9
        incoming: list[Event] = []
        while index < len(fb) and fb[index].kind == "IN":
            incoming.append(fb[index])
            index += 1
        if len(incoming) >= 263:
            values = [require_value(e) for e in incoming]
            transfers.append(ReadTransfer(values[:256], values[256:263], incoming[262].clock or 0))
    return transfers


def latest_transfer(events: list[Event], response_clock: int) -> ReadTransfer:
    candidates = [t for t in read_transfers(events) if t.end_clock <= response_clock]
    if not candidates:
        raise SafeError("交換#4抽出不能: 応答直前のREAD DATA転送が無い")
    return candidates[-1]


def retained_state(events: list[Event], response_clock: int) -> list[int]:
    """応答前の直近SEEK対象と直近SENSE INTERRUPT STATUSのPCNを返す。"""
    fb = [e for e in events if e.port == "00FB" and (e.clock or 0) < response_clock]
    seek_target: int | None = None
    pcn: int | None = None
    for index, event in enumerate(fb):
        if event.kind != "OUT":
            continue
        opcode = require_value(event) & 0x1F
        if opcode == 0x0F and index + 2 < len(fb) and all(e.kind == "OUT" for e in fb[index:index + 3]):
            seek_target = require_value(fb[index + 2])
        if opcode == 0x08:
            incoming: list[Event] = []
            cursor = index + 1
            while cursor < len(fb) and fb[cursor].kind == "IN":
                incoming.append(fb[cursor])
                cursor += 1
            if len(incoming) >= 2:
                pcn = require_value(incoming[1])
    if seek_target is None or pcn is None:
        raise SafeError("保持状態抽出不能: 直近SEEK対象またはPCNが無い")
    return [seek_target, pcn]


def groups(values: list[int]) -> int:
    return len(set(values))


def relation(label: str, left: list[int], right: list[int]) -> None:
    count = min(len(left), len(right))
    marks = [left[i] == right[i] for i in range(count)]
    prefix = 0
    while prefix < count and marks[prefix]:
        prefix += 1
    print(f"{label}: 比較位置={count} 一致件数={sum(marks)} 一致プレフィックス={prefix} "
          f"左同値グループ={groups(left[:count])} 右同値グループ={groups(right[:count])}")
    print(f"{label}位置別: " + " ".join(f"{i + 1}:{'同一' if same else '相違'}" for i, same in enumerate(marks)))


def summarize(label: str, path: Path) -> tuple[list[int], list[int], ReadTransfer]:
    parsed = parse_iolog(path)
    request, response, clock = exchange4(parsed["main"])
    transfer = latest_transfer(parsed["sub"], clock)
    state = retained_state(parsed["sub"], clock)
    print(f"{label}: 要求長={len(request)} 応答長={len(response)} READデータ長={len(transfer.data)} "
          f"READ結果長={len(transfer.result)} 応答同値グループ={groups(response)}")
    relation(f"{label}/応答対READデータ", response, transfer.data)
    relation(f"{label}/応答先頭対要求各位置", [response[0]] * len(request), request)
    relation(f"{label}/応答先頭対READ結果各位置", [response[0]] * len(transfer.result), transfer.result)
    relation(f"{label}/応答先頭対保持状態(SEEK対象,PCN)", [response[0]] * len(state), state)
    return request, response, transfer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("official", type=Path)
    parser.add_argument("mixed", type=Path)
    parser.add_argument("--alternate", type=Path)
    args = parser.parse_args()
    try:
        _, official_response, official_transfer = summarize("公式", args.official)
        _, mixed_response, mixed_transfer = summarize("混成", args.mixed)
        relation("公式対混成/交換#4応答", official_response, mixed_response)
        relation("公式対混成/直前READデータ", official_transfer.data, mixed_transfer.data)
        if args.alternate:
            _, alternate_response, alternate_transfer = summarize("媒体差替", args.alternate)
            relation("媒体差替連動/交換#4応答", official_response, alternate_response)
            relation("媒体差替連動/直前READデータ", official_transfer.data, alternate_transfer.data)
    except SafeError as exc:
        print(str(exc))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
