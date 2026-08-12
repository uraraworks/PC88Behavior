#!/usr/bin/env python3
"""FDCの読み取りセクタ座標列を、値を表示せずに比較する。

入力は q88measure --io-log の7列/8列形式。sub CPUの $FB コマンド
フェーズをμPD765/8272の公開コマンド長に従って追跡し、READ TRACK、
READ DATA、READ DELETED DATAのC/H/Rを内部だけで抽出する。

重要な情報境界:
  - C/H/Rとコマンド/パラメータ値は比較器の内部でだけ扱う。
  - 標準出力、例外、診断文に値を一切含めない。
  - 出力は件数、一致長、不一致位置、frame/seq、種別、分岐点前後だけ。

終了コード: 完全一致0 / 不一致1 / 入力・解析エラー2
"""

from __future__ import annotations

import argparse
import gzip
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


FDC_DATA_PORT = "00FB"
MASKED_VALUE = "--"

# コマンド下位5ビット -> パラメータ数。MT/MFM/SK等の修飾ビットは除く。
# μPD765/8272公開仕様のコマンドフェーズ長だけを使う。
PARAM_COUNTS = {
    0x02: 8,  # READ TRACK
    0x03: 2,  # SPECIFY
    0x04: 1,  # SENSE DRIVE STATUS
    0x05: 8,  # WRITE DATA
    0x06: 8,  # READ DATA
    0x07: 1,  # RECALIBRATE
    0x08: 0,  # SENSE INTERRUPT STATUS
    0x09: 8,  # WRITE DELETED DATA
    0x0A: 1,  # READ ID
    0x0C: 8,  # READ DELETED DATA
    0x0D: 5,  # FORMAT TRACK
    0x0F: 2,  # SEEK
    0x11: 8,  # SCAN EQUAL
    0x19: 8,  # SCAN LOW OR EQUAL
    0x1D: 8,  # SCAN HIGH OR EQUAL
}
READ_COORD_COMMANDS = {0x02, 0x06, 0x0C}
HOST_TO_FDC_DATA_COMMANDS = {0x05, 0x09, 0x0D, 0x11, 0x19, 0x1D}
NO_RESULT_COMMANDS = {0x03, 0x07, 0x0F}


class SafeError(Exception):
    """生行や値を文面に含めない解析エラー。"""


@dataclass(frozen=True)
class Event:
    seq: int
    clock: int | None
    frame: int
    cpu: str
    kind: str
    port: str
    value: int | None
    pc: str


@dataclass(frozen=True)
class SectorAccess:
    # 座標は比較専用。reprを無効化し、誤って例外表示へ流れにくくする。
    coordinate: tuple[int, int, int]
    seq: int
    clock: int | None
    frame: int

    def __repr__(self) -> str:
        return "SectorAccess(<redacted>)"


def open_iolog(path: Path) -> TextIO:
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def parse_iolog(path: Path) -> dict[str, list[Event]]:
    """値を内部で読むが、生行・値をエラー文へ含めない。"""
    events: dict[str, list[Event]] = {"main": [], "sub": []}
    section: str | None = None
    found = set()
    with open_iolog(path) as stream:
        for lineno, raw in enumerate(stream, start=1):
            stripped = raw.strip()
            if stripped == "# main":
                section = "main"
                found.add(section)
                continue
            if stripped == "# sub":
                section = "sub"
                found.add(section)
                continue
            if not stripped or stripped.startswith("#") or section is None:
                continue
            fields = stripped.split()
            if len(fields) == 7:
                seq_s, frame_s, cpu, kind, port, value_s, pc = fields
                clock_s = None
            elif len(fields) == 8:
                seq_s, clock_s, frame_s, cpu, kind, port, value_s, pc = fields
            else:
                raise SafeError(f"入力書式エラー: {lineno}行目の列数が不正")
            if cpu not in ("main", "sub") or kind not in ("IN", "OUT"):
                raise SafeError(f"入力書式エラー: {lineno}行目の種別が不正")
            try:
                seq = int(seq_s)
                frame = int(frame_s)
                clock = int(clock_s) if clock_s is not None else None
                value = None if value_s == MASKED_VALUE else int(value_s, 16)
                int(port, 16)
                int(pc, 16)
            except ValueError as exc:
                raise SafeError(f"入力書式エラー: {lineno}行目の数値形式が不正") from exc
            events[section].append(
                Event(seq, clock, frame, cpu, kind, port.upper().zfill(4), value, pc.upper())
            )
    if "main" not in found or "sub" not in found:
        raise SafeError("入力書式エラー: main/sub節が揃っていない")
    return events


def require_value(event: Event) -> int:
    if event.value is None:
        raise SafeError("座標抽出不能: FDCコマンドフェーズの値が利用できない")
    return event.value


def extract_sector_accesses(sub_events: list[Event]) -> list[SectorAccess]:
    """$FBのコマンドフェーズを追跡し、読み取りC/H/Rを内部抽出する。"""
    accesses: list[SectorAccess] = []
    mode = "command"
    opcode = -1
    remaining = 0
    params: list[int] = []
    command_event: Event | None = None

    def start_command(event: Event) -> None:
        nonlocal mode, opcode, remaining, params, command_event
        command_event = event
        opcode = require_value(event) & 0x1F
        remaining = PARAM_COUNTS.get(opcode, 0)
        params = []
        mode = "params" if remaining else "post"

    for event in sub_events:
        if event.port != FDC_DATA_PORT:
            continue

        if mode == "write_data":
            # 書込み/FORMAT/SCANの実行フェーズ。最初の結果IN以降はpost。
            if event.kind == "IN":
                mode = "post"
            continue

        if mode == "post":
            if event.kind == "IN":
                continue
            start_command(event)
            continue

        if mode == "command":
            if event.kind == "OUT":
                start_command(event)
            continue

        # params
        if event.kind != "OUT":
            # パラメータ途中で結果側へ遷移した場合は中断コマンドとして捨てる。
            mode = "post"
            continue
        params.append(require_value(event))
        remaining -= 1
        if remaining:
            continue

        if opcode in READ_COORD_COMMANDS:
            if len(params) < 4 or command_event is None:
                raise SafeError("座標抽出不能: 読み取りコマンドのパラメータ不足")
            # params[0]=unit/head、params[1:4]=C/H/R。値は表示層へ渡さない。
            accesses.append(
                SectorAccess(
                    (params[1], params[2], params[3]),
                    command_event.seq,
                    command_event.clock,
                    command_event.frame,
                )
            )

        if opcode in HOST_TO_FDC_DATA_COMMANDS:
            mode = "write_data"
        elif opcode in NO_RESULT_COMMANDS:
            mode = "command"
        else:
            mode = "post"

    return accesses


def fold_main(events: list[Event]) -> list[Event]:
    """mainの(kind,port,pc)連続runを畳み込み、各run先頭だけを返す。"""
    folded: list[Event] = []
    last_key = None
    for event in events:
        key = (event.kind, event.port, event.pc)
        if key != last_key:
            folded.append(event)
            last_key = key
    return folded


def boundary_clock(main_events: list[Event], divergence_index: int) -> int | None:
    folded = fold_main(main_events)
    zero_index = divergence_index - 1
    if zero_index >= len(folded):
        return None
    return folded[zero_index].clock


def side_of_boundary(access: SectorAccess | None, clock: int | None) -> str:
    if access is None or access.clock is None or clock is None:
        return "判定不能"
    return "前" if access.clock < clock else "後"


def first_mismatch(
    reference: list[SectorAccess], mixed: list[SectorAccess]
) -> tuple[int | None, str]:
    prefix = 0
    for ref_access, mixed_access in zip(reference, mixed):
        if ref_access.coordinate != mixed_access.coordinate:
            return prefix, "座標が違う"
        prefix += 1
    if len(reference) > len(mixed):
        return prefix, "基準側にしか無い"
    if len(mixed) > len(reference):
        return prefix, "混成側にしか無い"
    return None, "一致"


def print_location(label: str, access: SectorAccess | None) -> None:
    if access is None:
        print(f"{label}位置: なし")
    else:
        print(f"{label}位置: frame={access.frame} seq={access.seq}")


def compare(reference_path: Path, mixed_path: Path, divergence_index: int) -> int:
    reference_events = parse_iolog(reference_path)
    mixed_events = parse_iolog(mixed_path)
    reference = extract_sector_accesses(reference_events["sub"])
    mixed = extract_sector_accesses(mixed_events["sub"])

    mismatch_index, mismatch_kind = first_mismatch(reference, mixed)
    prefix = min(len(reference), len(mixed)) if mismatch_index is None else mismatch_index

    print(f"基準側抽出件数: {len(reference)}")
    print(f"混成側抽出件数: {len(mixed)}")
    print(f"座標列の一致プレフィックス長: {prefix}")
    if mismatch_index is None:
        print("最初の不一致位置: なし")
        print("不一致種別: 一致")
        print(f"分岐点{divergence_index}との位置関係: 該当なし")
        return 0

    ref_access = reference[mismatch_index] if mismatch_index < len(reference) else None
    mixed_access = mixed[mismatch_index] if mismatch_index < len(mixed) else None
    print(f"最初の不一致位置: {mismatch_index + 1}")
    print_location("基準側", ref_access)
    print_location("混成側", mixed_access)
    print(f"不一致種別: {mismatch_kind}")

    ref_side = side_of_boundary(
        ref_access, boundary_clock(reference_events["main"], divergence_index)
    )
    mixed_side = side_of_boundary(
        mixed_access, boundary_clock(mixed_events["main"], divergence_index)
    )
    if ref_side == mixed_side:
        relation = ref_side
    elif "判定不能" in (ref_side, mixed_side):
        relation = ref_side if mixed_side == "判定不能" else mixed_side
    else:
        relation = "前後にまたがる"
    print(f"分岐点{divergence_index}との位置関係: {relation}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FDC読み取り座標列を、座標値を表示せず集計比較する"
    )
    parser.add_argument("reference", type=Path)
    parser.add_argument("mixed", type=Path)
    parser.add_argument("--divergence-index", type=int, default=259)
    args = parser.parse_args()
    if args.divergence_index < 1:
        print("エラー: 分岐点indexは1以上でなければならない", file=sys.stderr)
        return 2
    try:
        return compare(args.reference, args.mixed, args.divergence_index)
    except (OSError, SafeError) as exc:
        # SafeErrorは値・生行を含まない。OSErrorもファイル内容を含まない。
        print(f"エラー: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
