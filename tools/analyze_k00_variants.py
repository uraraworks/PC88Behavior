#!/usr/bin/env python3
"""K00の終端列A/Bと、subが保持できる履歴状態を値非開示で対応づける。

入力はリポジトリ外に置いた未伏せ字iologを想定する。データポート値は内部で
先頭種別と終端構造の分類にだけ使い、標準出力・出力ファイル・例外文へは出さない。
出力するのはK00等の記号、公開FDCコマンドの有無・完走件数、列A/Bだけである。
"""
from __future__ import annotations

import argparse
import bisect
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_record_boundaries as arb  # noqa: E402
import analyze_write_path as awp  # noqa: E402

DATA_PORTS = {"00FB", "00FC", "00FD"}
READ_DATA = 0x06
SPECIFY = 0x03


class SafeError(Exception):
    pass


@dataclass
class Sample:
    label: str
    variant: str
    k00_ordinal: int
    epoch_k00_ordinal: int
    run_ordinal: int
    previous_kind: str
    specify_done: bool
    read_done: bool
    read_done_count: int
    fdc_command_count: int


def require_raw(rows) -> None:
    if any(e.port in DATA_PORTS and e.value is None for e in rows):
        raise SafeError("データポートに伏せ字があるため解析不可")


def closing_signature(sub_rows, run: list[int]) -> tuple:
    """最後の受信直後から最初のFB/FD OUTまでを、値非開示の構造へ変換する。"""
    out = []
    for e in sub_rows[run[-1] + 1:]:
        if e.kind != "OUT":
            continue
        if e.port == "00FF":
            out.append(("FF", e.value))
        elif e.port == "00F8":
            out.append(("F8", None))
        elif e.port == "00FC":
            out.append(("FC", None))
        elif e.port == "00FB":
            # コマンド語は公開オペコードだけを分類に使う。
            out.append(("FB", e.value & 0x1F))
            break
        elif e.port == "00FD":
            out.append(("FD", None))
            break
    return tuple(out)


SIG_A = (("FF", 0x0D), ("FF", 0x0C), ("F8", None), ("F8", None),
         ("FB", SPECIFY))
SIG_B = (("FF", 0x0D), ("FF", 0x0C), ("FF", 0x81), ("FF", 0x08),
         ("FF", 0x0A), ("FF", 0x0C), ("FF", 0x0E), ("FF", 0x09),
         ("FC", None), ("FD", None))


def command_end_clocks(rows, commands) -> list[int]:
    """次のコマンド開始前までに観測したFBイベントの末尾clock。"""
    fb = [e for e in rows if e.cpu == "sub" and e.port == "00FB"]
    fb_clocks = [e.clock for e in fb]
    starts = [c.clock for c in commands]
    ends = []
    for i, start in enumerate(starts):
        lo = bisect.bisect_left(fb_clocks, start)
        hi = (bisect.bisect_left(fb_clocks, starts[i + 1])
              if i + 1 < len(starts) else len(fb))
        ends.append(fb[hi - 1].clock if hi > lo else start)
    return ends


def collect_one(path: Path, label: str, reset_at: int = -1) -> list[Sample]:
    rows, _ = m2s.parse_iolog(path)
    require_raw(rows)
    sub_rows = [e for e in rows if e.cpu == "sub"]
    runs = arb.window_a_runs(sub_rows, arb.sub_fc_indices(sub_rows))
    if not runs:
        return []

    heads = sorted({sub_rows[r[0]].value for r in runs})
    symbols = {value: f"K{i:02d}" for i, value in enumerate(heads)}
    if "K00" not in symbols.values():
        return []

    commands = awp.parse_commands(rows)
    cmd_ends = command_end_clocks(rows, commands)
    samples = []
    k00_n = 0
    epoch_k00_n = 0
    in_reset_epoch = False
    for run_i, run in enumerate(runs):
        run_frame = sub_rows[run[0]].frame
        now_reset_epoch = reset_at >= 0 and run_frame >= reset_at
        if now_reset_epoch and not in_reset_epoch:
            epoch_k00_n = 0
            in_reset_epoch = True
        if symbols[sub_rows[run[0]].value] != "K00":
            continue
        k00_n += 1
        epoch_k00_n += 1
        start_clock = sub_rows[run[0]].clock
        epoch_start = reset_at if now_reset_epoch else -1
        completed = [(c, end) for c, end in zip(commands, cmd_ends)
                     if c.frame >= epoch_start and end < start_clock]
        sig = closing_signature(sub_rows, run)
        if sig == SIG_A:
            variant = "A"
        elif sig == SIG_B:
            variant = "B"
        else:
            variant = "未知"
        if run_i == 0:
            prev = "なし"
        elif sub_rows[runs[run_i - 1][0]].frame < epoch_start:
            prev = "リセット境界"
        else:
            prev = symbols[sub_rows[runs[run_i - 1][0]].value]
        reads = [c for c, _ in completed
                 if c.opcode == READ_DATA and c.result_bytes >= 263]
        samples.append(Sample(
            label=label,
            variant=variant,
            k00_ordinal=k00_n,
            epoch_k00_ordinal=epoch_k00_n,
            run_ordinal=run_i + 1,
            previous_kind=prev,
            specify_done=any(c.opcode == SPECIFY for c, _ in completed),
            read_done=bool(reads),
            read_done_count=len(reads),
            fdc_command_count=len(completed),
        ))
    return samples


def predicted(sample: Sample) -> dict[str, str]:
    return {
        "K00通番（初回=A、以後=B）": "A" if sample.k00_ordinal == 1 else "B",
        "リセット後通番（各epoch初回=A、以後=B）": "A" if sample.epoch_k00_ordinal == 1 else "B",
        "直前run（K05ならB、それ以外=A）": "B" if sample.previous_kind == "K05" else "A",
        "SPECIFY履歴（未発行=A、発行済み=B）": "B" if sample.specify_done else "A",
        "READ完走履歴（未完走=A、完走済み=B）": "B" if sample.read_done else "A",
        "FDC履歴（コマンド0件=A、1件以上=B）": "B" if sample.fdc_command_count else "A",
    }


def report(samples: list[Sample]) -> str:
    lines = [
        "# K00変種とsub観測可能状態", "",
        "| 条件 | 列 | K00通番 | epoch内通番 | run通番 | 直前run | SPECIFY済み | READ DATA完走済み | 完走READ数 | 既完了FDCコマンド数 |",
        "|---|---:|---:|---:|---:|---|---|---|---:|---:|",
    ]
    for s in samples:
        lines.append(
            f"| {s.label} | {s.variant} | {s.k00_ordinal} | {s.epoch_k00_ordinal} | {s.run_ordinal} | "
            f"{s.previous_kind} | {'はい' if s.specify_done else 'いいえ'} | "
            f"{'はい' if s.read_done else 'いいえ'} | {s.read_done_count} | "
            f"{s.fdc_command_count} |"
        )
    lines.extend(["", f"K00標本数: {len(samples)}", "", "## 候補規則", ""])
    names = list(predicted(samples[0]).keys()) if samples else []
    for name in names:
        errors = sum(predicted(s)[name] != s.variant for s in samples)
        lines.append(f"- {name}: 例外{errors}件")
    unknown = sum(s.variant == "未知" for s in samples)
    lines.extend(["", f"未知の終端列: {unknown}件", ""])
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iolog", nargs="+", required=True, type=Path)
    ap.add_argument("--label", nargs="+", required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--reset-at", nargs="+", type=int,
                    help="各iologのリセットframe。リセット無しは-1")
    args = ap.parse_args()
    if len(args.iolog) != len(args.label):
        print("iologとlabelの件数が違う", file=sys.stderr)
        return 2
    reset_at = args.reset_at or [-1] * len(args.iolog)
    if len(reset_at) != len(args.iolog):
        print("reset-atとiologの件数が違う", file=sys.stderr)
        return 2
    try:
        samples = []
        for path, label, reset in zip(args.iolog, args.label, reset_at):
            samples.extend(collect_one(path, label, reset))
        text = report(samples)
    except (SafeError, awp.SafeError) as ex:
        print(f"解析不可: {ex}", file=sys.stderr)
        return 3
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
