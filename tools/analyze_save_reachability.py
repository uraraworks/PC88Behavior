#!/usr/bin/env python3
"""SAVE 到達点と WRITE 専用受信位相を、データ値を表示せず比較する。

公式一式と「公式main + 自作sub」の生 iolog を入力にする。内部では要求runの
先頭値とFDCコマンドを分類するが、標準出力へ出すのは件数、長さ、フレーム、
公開FDCコマンド名、位相の一致数だけである。$FB/$FC/$FD の値は出さない。

WRITE run の公式位相（m7bz実測）は次の通り。

* 位置1..5: 1バイトごとに RECV 完了→再アーム
* 位置6..261: 2バイト一組。偶数位置では完了を出さず、次の奇数位置を
  直接受信してから完了→再アーム（最終261だけは再アームしない）

終了コードは、指定された期待件数・長さ・位相から1件でも外れれば1。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_record_boundaries as arb  # noqa: E402
import analyze_write_path as awp  # noqa: E402


DATA_PORTS = {"00FB", "00FC", "00FD"}
FF_FINISH = 0x0C
FF_REARM = 0x0B


def require_unredacted(rows: list[m2s.Ev], label: str) -> None:
    masked = [e for e in rows if e.port in DATA_PORTS and e.value is None]
    if masked:
        raise ValueError(f"{label}: データポートに伏せ字が{len(masked)}件あり解析不能")


def sub_runs(rows: list[m2s.Ev]) -> tuple[list[m2s.Ev], list[list[int]]]:
    sub = [e for e in rows if e.cpu == "sub"]
    return sub, arb.window_a_runs(sub, arb.sub_fc_indices(sub))


def between(sub: list[m2s.Ev], run: list[int], pos: int) -> list[m2s.Ev]:
    """1-origin の pos の IN $FC 後から次の IN $FC 前まで。"""
    start = run[pos - 1] + 1
    if pos < len(run):
        end = run[pos]
    else:
        # 最終位置は後続runまで広げない。窓(a)を閉じる最初のFDC出力または
        # sub→main出力までで切り、後続処理の再アームを誤算入しない。
        end = next(
            (i for i in range(start, len(sub))
             if sub[i].kind == "OUT" and sub[i].port in {"00FB", "00FD"}),
            len(sub),
        )
    return sub[start:end]


def has_ff(events: list[m2s.Ev], value: int) -> bool:
    return any(e.kind == "OUT" and e.port == "00FF" and e.value == value for e in events)


def phase_counts(sub: list[m2s.Ev], runs: list[list[int]]) -> dict[str, tuple[int, int]]:
    stats = {k: [0, 0] for k in ("single", "pair_first", "pair_second", "final")}
    for run in runs:
        if len(run) != 261:
            continue
        for pos in range(1, 6):
            evs = between(sub, run, pos)
            stats["single"][1] += 1
            stats["single"][0] += has_ff(evs, FF_FINISH) and has_ff(evs, FF_REARM)
        for pos in range(6, 261, 2):
            evs = between(sub, run, pos)
            stats["pair_first"][1] += 1
            stats["pair_first"][0] += not has_ff(evs, FF_FINISH) and not has_ff(evs, FF_REARM)
        for pos in range(7, 261, 2):
            evs = between(sub, run, pos)
            stats["pair_second"][1] += 1
            stats["pair_second"][0] += has_ff(evs, FF_FINISH) and has_ff(evs, FF_REARM)
        evs = between(sub, run, 261)
        stats["final"][1] += 1
        stats["final"][0] += has_ff(evs, FF_FINISH) and not has_ff(evs, FF_REARM)
    return {k: (v[0], v[1]) for k, v in stats.items()}


def fdc_summary(rows: list[m2s.Ev]) -> tuple[list[awp.Command], int, int]:
    cmds = awp.parse_commands(rows)
    reads = sum(c.opcode == 0x06 for c in cmds)
    writes = sum(c.opcode in awp.WRITE_OPCODES for c in cmds)
    return cmds, reads, writes


def opcode_prefix(a: list[awp.Command], b: list[awp.Command]) -> int:
    n = min(len(a), len(b))
    return next((i for i in range(n) if a[i].opcode != b[i].opcode), n)


def candidate_pair(
    off_sub: list[m2s.Ev], off_runs: list[list[int]],
    mix_sub: list[m2s.Ev], mix_runs: list[list[int]],
) -> tuple[int, int, int]:
    """混成末尾runと同じ先頭値で、公式側の最初の長runを対応づける。"""
    if not mix_runs:
        raise ValueError("混成に受信runが無い")
    mixed = mix_runs[-1]
    head = mix_sub[mixed[0]].value
    official = next(
        (r for r in off_runs if len(r) >= 20 and off_sub[r[0]].value == head), None
    )
    if official is None:
        raise ValueError("混成末尾runと同じ先頭種別の公式長runが無い")
    predecessor = len(mix_runs[-2]) if len(mix_runs) >= 2 else 0
    return len(official), len(mixed), predecessor


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--official", required=True, type=Path)
    ap.add_argument("--mixed", required=True, type=Path)
    ap.add_argument("--expected-official-writes", required=True, type=int)
    ap.add_argument("--expected-mixed-writes", required=True, type=int)
    ap.add_argument("--expected-mixed-run-length", required=True, type=int)
    ap.add_argument("--expected-opcode-prefix", required=True, type=int)
    args = ap.parse_args()

    try:
        official, _ = m2s.parse_iolog(args.official)
        mixed, _ = m2s.parse_iolog(args.mixed)
        require_unredacted(official, "公式")
        require_unredacted(mixed, "混成")
        off_sub, off_runs = sub_runs(official)
        mix_sub, mix_runs = sub_runs(mixed)
        off_cmds, off_reads, off_writes = fdc_summary(official)
        mix_cmds, mix_reads, mix_writes = fdc_summary(mixed)
        prefix = opcode_prefix(off_cmds, mix_cmds)
        off_len, mix_len, predecessor = candidate_pair(
            off_sub, off_runs, mix_sub, mix_runs
        )
        phases = phase_counts(off_sub, off_runs)
    except (ValueError, awp.SafeError) as ex:
        print(f"解析不能: {ex}", file=sys.stderr)
        return 2

    first_write = next((c.frame for c in off_cmds if c.opcode in awp.WRITE_OPCODES), None)
    print(f"公式FDC\t総数={len(off_cmds)}\tREAD={off_reads}\tWRITE={off_writes}"
          f"\tWRITE初出frame={first_write if first_write is not None else '--'}")
    print(f"混成FDC\t総数={len(mix_cmds)}\tREAD={mix_reads}\tWRITE={mix_writes}")
    print(f"FDCコマンド種別共通prefix\t{prefix}件")
    print(f"SAVE候補run\t直前run長={predecessor}\t公式長={off_len}\t混成長={mix_len}")
    for key, label in (
        ("single", "位置1..5の単発完了"),
        ("pair_first", "位置6..260偶数の対内継続"),
        ("pair_second", "位置7..259奇数の対完了再アーム"),
        ("final", "位置261の完了・再アームなし"),
    ):
        good, total = phases[key]
        print(f"公式WRITE位相\t{label}\t{good}/{total}")

    failures = []
    if off_writes != args.expected_official_writes:
        failures.append("公式WRITE件数")
    if mix_writes != args.expected_mixed_writes:
        failures.append("混成WRITE件数")
    if off_len != 261 or mix_len != args.expected_mixed_run_length:
        failures.append("SAVE候補run長")
    if predecessor != 2:
        failures.append("SAVE候補直前run長")
    if prefix != args.expected_opcode_prefix:
        failures.append("FDCコマンド種別prefix")
    if any(good != total or total == 0 for good, total in phases.values()):
        failures.append("公式WRITE受信位相")
    if failures:
        print("NG: " + "、".join(failures))
        return 1
    print("OK: SAVE到達点とWRITE専用受信位相が期待どおり")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
