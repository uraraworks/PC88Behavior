#!/usr/bin/env python3
"""m7dm: run長6偏りをプロトコル軸(Y2/Y3/Y4)で説明する規則探索。

m7dlで事前登録したY1(要求種別、1.36節の`analyze_request_kinds.py`)は、
本稿の対象(main視点SEND run)と1.36節の対象(sub視点受信run)の1:1対応検証で
不成立と判明したため使わない(`verify_correspondence()`参照)。残る
Y2(対応するsub側FDCアクセス件数)・Y3(往復の位置)・Y4(run直後のFDCコマンド
種別)を評価する。値は一切使わない。
"""
from __future__ import annotations

import bisect
import sys
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import analyze_boot_exchange as boot  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_record_boundaries as arb  # noqa: E402
import analyze_run_cutter_attribution as attrib  # noqa: E402
import analyze_write_path as awp  # noqa: E402
import boundary_match_rule_search as bmrs  # noqa: E402

CONDITIONS = bmrs.CONDITIONS
READ_OPCODE = 0x06
FDC_CATEGORIES = ("READ", "WRITE", "なし", "その他")


def verify_correspondence(rows: list) -> dict:
    """本稿対象(main視点SEND run)と1.36節対象(sub視点受信run)が1:1対応するか
    を、件数とrun長の対応(位置順)だけで検証する。値は使わない。"""
    main_runs, _main_rows = attrib.current_send.main_send_runs(rows)
    sub_rows = [e for e in rows if e.cpu == "sub"]
    fc_idx = arb.sub_fc_indices(sub_rows)
    sub_runs = arb.window_a_runs(sub_rows, fc_idx)
    n = min(len(main_runs), len(sub_runs))
    match = sum(1 for i in range(n) if len(main_runs[i]) == len(sub_runs[i]))
    return {
        "main_runs": len(main_runs),
        "sub_runs": len(sub_runs),
        "count_equal": len(main_runs) == len(sub_runs),
        "compared": n,
        "length_match": match,
        "match_rate": (match / n) if n else None,
    }


def categorize_cmd(cmd) -> str:
    if cmd is None:
        return "なし"
    if cmd.opcode == READ_OPCODE:
        return "READ"
    if cmd.opcode in awp.WRITE_OPCODES:
        return "WRITE"
    return "その他"


@dataclass
class ProtocolInstance:
    indicator: str
    condition: str
    run_len: int
    category: str
    fdc_count: int
    next_cmd_kind: str
    ordinal: int
    boot_round: int | None
    label: bool = field(init=False)

    def __post_init__(self) -> None:
        self.label = self.category == "boundary_match"


def _boot_round_ranges(rows: list) -> dict[tuple[int, int], int]:
    tx = m2s.classify_transactions(rows)
    runs2 = boot.group_runs(tx)
    boot_runs, bulk_run = boot.split_boot_and_bulk(runs2)
    pairing_input = boot_runs + ([bulk_run] if bulk_run is not None else [])
    rounds = boot.pair_rounds(pairing_input)
    ranges: dict[tuple[int, int], int] = {}
    for i, (send_run, _resp_run) in enumerate(rounds):
        ranges[(send_run.lo, send_run.hi)] = i
    return ranges


def build_protocol_instances(rows: list, interrupts: dict, condition: str) -> list[ProtocolInstance]:
    current_runs, main_rows = attrib.current_send.main_send_runs(rows)
    anchors = attrib.anchor_send_runs(rows)
    _metrics, ff_bad, parity_bad = attrib.send_outcomes(current_runs, main_rows)
    all_fd = [idx for run in current_runs for idx in run]
    int_clocks = [e.clock for e in interrupts["main"]]

    cmds = awp.parse_commands(rows)
    cmd_clocks = [c.clock for c in cmds]

    ordered = sorted(current_runs, key=lambda r: main_rows[r[0]].clock)
    ordinal_of = {id(r): i for i, r in enumerate(ordered)}
    recv_clocks = sorted(
        e.clock for e in main_rows if e.kind == "IN" and e.port == "00FC"
    )

    def next_recv_clock(after: int) -> int:
        i = bisect.bisect_right(recv_clocks, after)
        return recv_clocks[i] if i < len(recv_clocks) else main_rows[-1].clock

    def next_run_start(run: list[int]) -> int | None:
        idx = ordinal_of[id(run)]
        if idx + 1 < len(ordered):
            return main_rows[ordered[idx + 1][0]].clock
        return None

    boot_ranges = _boot_round_ranges(rows) if condition == "d0-boot" else {}

    def boot_round_for(run: list[int]) -> int | None:
        if not boot_ranges:
            return None
        lo, hi = main_rows[run[0]].clock, main_rows[run[-1]].clock
        for (rlo, rhi), idx in boot_ranges.items():
            if rlo <= lo and hi <= rhi:
                return idx
        return None

    def fdc_count_for(run: list[int]) -> int:
        lo = main_rows[run[0]].clock
        hi = next_recv_clock(main_rows[run[-1]].clock)
        fa, fb = boot.fdc_window_counts(rows, lo, hi)
        return fa + fb

    def next_cmd_for(run: list[int]) -> str:
        end = main_rows[run[-1]].clock
        window_end = next_run_start(run)
        lo = bisect.bisect_right(cmd_clocks, end)
        hi = bisect.bisect_left(cmd_clocks, window_end) if window_end is not None else len(cmds)
        for c in cmds[lo:hi]:
            cat = categorize_cmd(c)
            if cat in ("READ", "WRITE"):
                return cat
        return "なし"

    instances: list[ProtocolInstance] = []
    for run, idx in ff_bad:
        cat = attrib.classify_send(run, idx, anchors, main_rows, int_clocks, all_fd)
        instances.append(ProtocolInstance(
            indicator="0f", condition=condition, run_len=len(run), category=cat,
            fdc_count=fdc_count_for(run), next_cmd_kind=next_cmd_for(run),
            ordinal=ordinal_of[id(run)], boot_round=boot_round_for(run),
        ))
    for run in parity_bad:
        cat = attrib.classify_send(run, None, anchors, main_rows, int_clocks, all_fd)
        instances.append(ProtocolInstance(
            indicator="parity", condition=condition, run_len=len(run), category=cat,
            fdc_count=fdc_count_for(run), next_cmd_kind=next_cmd_for(run),
            ordinal=ordinal_of[id(run)], boot_round=boot_round_for(run),
        ))
    return instances


def build_candidates(instances: list[ProtocolInstance]) -> dict[str, callable]:
    cands: dict[str, callable] = {}
    for n in sorted({i.fdc_count for i in instances}):
        cands[f"Y2_fdc={n}"] = (lambda n: (lambda i: i.fdc_count == n))(n)
    for thr in (1, 2, 5, 10):
        cands[f"Y2_fdc>={thr}"] = (lambda thr: (lambda i: i.fdc_count >= thr))(thr)
    cands["Y2_fdc==0"] = lambda i: i.fdc_count == 0
    for c in FDC_CATEGORIES:
        cands[f"Y4_next={c}"] = (lambda c: (lambda i: i.next_cmd_kind == c))(c)
    boot_rounds = sorted({i.boot_round for i in instances if i.boot_round is not None})
    for r in boot_rounds:
        cands[f"Y3_bootround={r}"] = (lambda r: (lambda i: i.boot_round == r))(r)
    cands["Y3_has_bootround"] = lambda i: i.boot_round is not None
    for thr in (5, 10, 20, 50, 100):
        cands[f"Y3_ordinal<{thr}"] = (lambda thr: (lambda i: i.ordinal < thr))(thr)
    return cands


def build_combo_candidates(instances: list[ProtocolInstance]) -> dict[str, callable]:
    """Y2×Y3, Y2×Y4, Y3×Y4 の3通りに限定する。"""
    combos: dict[str, callable] = {}
    for thr in (1, 2, 5, 10):
        for c in FDC_CATEGORIES:
            combos[f"Y5_fdc>={thr}&next={c}"] = (
                lambda thr, c: (lambda i: i.fdc_count >= thr and i.next_cmd_kind == c)
            )(thr, c)
    for thr in (1, 2, 5, 10):
        for ot in (5, 10, 20, 50, 100):
            combos[f"Y5_fdc>={thr}&ordinal<{ot}"] = (
                lambda thr, ot: (lambda i: i.fdc_count >= thr and i.ordinal < ot)
            )(thr, ot)
    for c in FDC_CATEGORIES:
        for ot in (5, 10, 20, 50, 100):
            combos[f"Y5_next={c}&ordinal<{ot}"] = (
                lambda c, ot: (lambda i: i.next_cmd_kind == c and i.ordinal < ot)
            )(c, ot)
    return combos


evaluate = bmrs.evaluate
observationally_equivalent = bmrs.observationally_equivalent
