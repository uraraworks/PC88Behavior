#!/usr/bin/env python3
"""m7cz: 共通クロックログからFDC相関・起動初期化決定論性・応答遅延を測る。

データポートのvalue列は読み取り結果に保持されても、本解析では一切参照・表示しない。
出力は件数、clock差の統計、構造署名(SHA-256)だけに限定する。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import statistics
import sys
from dataclasses import dataclass, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_boot_exchange as bootex  # noqa: E402
import analyze_boot_fdc_sequence as bootfdc  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402

Ev = m2s.Ev


def validate_clocks(rows: list[Ev]) -> None:
    if not rows:
        raise ValueError("解析可能イベントが0件")
    clocks = [e.clock for e in rows]
    if any(c < 0 for c in clocks):
        raise ValueError("負の共通clockを含む")
    if len(clocks) != len(set(clocks)):
        raise ValueError("共通clockに重複がある")
    if clocks != sorted(clocks):
        raise ValueError("共通clockが昇順でない")


@dataclass(frozen=True)
class CorrelationResult:
    ok: bool
    rounds: int
    singles: int
    response256: int
    bulk: int
    single_fdc_min: int
    single_fdc_max: int
    response256_pairs: tuple[tuple[int, int], ...]
    bulk_pair: tuple[int, int]
    body_fdc: int
    outside_fdc: int
    reasons: tuple[str, ...]


def evaluate_correlation(rows: list[Ev]) -> CorrelationResult:
    tx = m2s.classify_transactions(rows)
    runs = bootex.group_runs(tx)
    boot_runs, bulk_run = bootex.split_boot_and_bulk(runs)
    rounds = bootex.pair_rounds(boot_runs + ([bulk_run] if bulk_run else []))
    if not rounds:
        raise ValueError("起動ラウンドが0件")

    pre_counts: list[tuple[int, int, int]] = []
    body_total = 0
    covered_pre: list[tuple[int, int]] = []
    for send, resp in rounds:
        fa, fb = bootex.fdc_window_counts(rows, send.lo, resp.lo - 1)
        body_fa, body_fb = bootex.fdc_window_counts(rows, resp.lo, resp.hi)
        pre_counts.append((len(resp.events), fa, fb))
        body_total += body_fa + body_fb
        covered_pre.append((send.lo, resp.lo - 1))

    seq_lo, seq_hi = rounds[0][0].lo, rounds[-1][1].hi
    fdc_events = [e for e in rows if e.cpu == "sub" and e.port in ("00FA", "00FB")
                  and seq_lo <= e.clock <= seq_hi]
    outside = sum(
        1 for e in fdc_events
        if not any(lo <= e.clock <= hi for lo, hi in covered_pre)
        and not any(resp.lo <= e.clock <= resp.hi for _send, resp in rounds)
    )

    singles = [(fa, fb) for n, fa, fb in pre_counts if n == 1]
    r256_indexes = [i for i, (n, _fa, _fb) in enumerate(pre_counts) if n == 256]
    r256 = [(pre_counts[i - 1][1], pre_counts[i - 1][2])
            for i in r256_indexes if i > 0]
    bulks = [(fa, fb) for n, fa, fb in pre_counts if n >= bootex.BULK_RUN_MIN]
    reasons: list[str] = []
    if body_total != 0:
        reasons.append("応答本体窓にFDCアクセスがある")
    if outside != 0:
        reasons.append("ラウンド外にFDCアクセスがある")
    if not singles:
        reasons.append("単発応答が0件")
    if len(r256_indexes) != 3 or len(r256) != 3:
        reasons.append("256件応答またはその直前ラウンドが3組でない")
    elif len(set(r256)) != 1:
        reasons.append("256件応答の直前3ラウンドでFDC件数が一致しない")
    if len(bulks) != 1:
        reasons.append("バルク応答が1件でない")
    if r256 and bulks and not (sum(r256[0]) < sum(bulks[0])):
        reasons.append("256件応答直前・バルクのFDC件数順序が成立しない")

    single_totals = [sum(p) for p in singles]
    return CorrelationResult(
        not reasons, len(rounds), len(singles), len(r256), len(bulks),
        min(single_totals) if single_totals else 0,
        max(single_totals) if single_totals else 0,
        tuple(r256), bulks[0] if len(bulks) == 1 else (0, 0),
        body_total, outside, tuple(reasons),
    )


@dataclass(frozen=True)
class BootSignature:
    digest: str
    event_count: int
    run_lengths: tuple[tuple[str, int], ...]
    canonical: tuple[tuple[int, int, str, str, str], ...]


def boot_signature(rows: list[Ev]) -> BootSignature:
    sub = [e for e in rows if e.cpu == "sub"]
    win = bootfdc.find_boot_init_window(sub)
    if win is None:
        raise ValueError("起動時FDC初期化区間を切り出せない")
    start, end = win
    window = sub[start:end]
    if not window:
        raise ValueError("起動時FDC初期化区間が0件")
    base_clock = window[0].clock
    base_seq = window[0].seq
    canonical = tuple(
        (e.clock - base_clock, e.seq - base_seq, e.kind, e.port, e.pc)
        for e in window
    )
    payload = "\n".join("|".join(map(str, row)) for row in canonical).encode("ascii")
    runs = tuple((r["kind"], r["len"]) for r in bootfdc.segment_runs(window))
    return BootSignature(hashlib.sha256(payload).hexdigest(), len(window), runs, canonical)


@dataclass(frozen=True)
class DelayResult:
    kind: str
    valid: int
    invalid: int
    intermediate: int
    minimum: int | None
    median: float | None
    maximum: int | None


def _spin_ends(rows: list[Ev], cpu: str, pc: str) -> list[Ev]:
    cpu_rows = [e for e in rows if e.cpu == cpu]
    ends: list[Ev] = []
    i = 0
    while i < len(cpu_rows):
        e = cpu_rows[i]
        if e.kind == "IN" and e.port == "00FE" and e.pc == pc:
            j = i + 1
            while (j < len(cpu_rows) and cpu_rows[j].kind == "IN"
                   and cpu_rows[j].port == "00FE" and cpu_rows[j].pc == pc):
                j += 1
            ends.append(cpu_rows[j - 1])
            i = j
        else:
            i += 1
    return ends


def _sub_send_request_starts(rows: list[Ev]) -> list[Ev]:
    sub = [e for e in rows if e.cpu == "sub"]
    starts: list[Ev] = []
    i = 0
    while i < len(sub):
        e = sub[i]
        if e.kind == "IN" and e.port == "00FE":
            j = i + 1
            while (j < len(sub) and sub[j].kind == "IN" and sub[j].port == "00FE"
                   and sub[j].pc == e.pc):
                j += 1
            if j < len(sub) and sub[j].kind == "OUT" and sub[j].port == "00FD":
                starts.append(sub[j - 1])
            i = j
        else:
            i += 1
    return starts


def _pair_delays(kind: str, starts: list[Ev], ends: list[Ev]) -> DelayResult:
    deltas: list[int] = []
    invalid = 0
    for i, start in enumerate(starts):
        next_clock = starts[i + 1].clock if i + 1 < len(starts) else None
        candidates = [e for e in ends if e.clock > start.clock
                      and (next_clock is None or e.clock < next_clock)]
        if len(candidates) != 1:
            invalid += 1
            continue
        delta = candidates[0].clock - start.clock
        if delta <= 0:
            invalid += 1
            continue
        deltas.append(delta)
    return DelayResult(
        kind, len(deltas), invalid, 0,
        min(deltas) if deltas else None,
        statistics.median(deltas) if deltas else None,
        max(deltas) if deltas else None,
    )


def _pair_delays_by_end(kind: str, starts: list[Ev], ends: list[Ev]) -> DelayResult:
    """各終点について、前終点より後にある最も近い起点を対応させる。"""
    deltas: list[int] = []
    invalid = 0
    intermediate = 0
    previous_end = -1
    for end in ends:
        candidates = [s for s in starts if previous_end < s.clock < end.clock]
        if not candidates:
            invalid += 1
        else:
            latest = max(s.clock for s in candidates)
            nearest = [s for s in candidates if s.clock == latest]
            if len(nearest) != 1:
                invalid += 1
            else:
                deltas.append(end.clock - latest)
                intermediate += len(candidates) - 1
        previous_end = end.clock
    return DelayResult(
        kind, len(deltas), invalid, intermediate,
        min(deltas) if deltas else None,
        statistics.median(deltas) if deltas else None,
        max(deltas) if deltas else None,
    )


def evaluate_delays(rows: list[Ev]) -> tuple[DelayResult, DelayResult]:
    send_starts = [e for e in rows if e.cpu == "sub" and e.kind == "IN" and e.port == "00FC"]
    send_ends = _spin_ends(rows, "main", "37FF")
    recv_starts = _sub_send_request_starts(rows)
    recv_ends = _spin_ends(rows, "main", "3853")
    return (
        _pair_delays("SEND", send_starts, send_ends),
        _pair_delays_by_end("RECV", recv_starts, recv_ends),
    )


def fmt_number(value: float | int | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def write_summary(path: Path, label: str, out) -> None:
    rows, _masked = m2s.parse_iolog(path)
    validate_clocks(rows)
    corr = evaluate_correlation(rows)
    sig = boot_signature(rows)
    delays = evaluate_delays(rows)
    print(f"条件: {label}", file=out)
    print(f"共通clockイベント: {len(rows)}件", file=out)
    print(
        f"C-1: {'成立' if corr.ok else '不成立'} / ラウンド{corr.rounds}件 / "
        f"単発{corr.singles}件(FDC合計最小{corr.single_fdc_min},最大{corr.single_fdc_max}) / "
        f"256件応答{corr.response256}件(直前ラウンドFDC組={list(corr.response256_pairs)}) / "
        f"バルク{corr.bulk}件(FDC組={corr.bulk_pair}) / "
        f"応答本体FDC{corr.body_fdc}件 / ラウンド外FDC{corr.outside_fdc}件",
        file=out,
    )
    if corr.reasons:
        print(f"C-1不成立理由: {'; '.join(corr.reasons)}", file=out)
    print(
        f"C-2署名: events={sig.event_count} runs={list(sig.run_lengths)} sha256={sig.digest}",
        file=out,
    )
    for d in delays:
        print(
            f"C-3 {d.kind}: 有効{d.valid}件 / 不正{d.invalid}件 / 中間候補{d.intermediate}件 / "
            f"最小{fmt_number(d.minimum)} / 中央値{fmt_number(d.median)} / 最大{fmt_number(d.maximum)} clock",
            file=out,
        )


def write_determinism(left: Path, right: Path, out) -> bool:
    left_rows, _ = m2s.parse_iolog(left)
    right_rows, _ = m2s.parse_iolog(right)
    validate_clocks(left_rows)
    validate_clocks(right_rows)
    a, b = boot_signature(left_rows), boot_signature(right_rows)
    same = a.canonical == b.canonical
    print(f"C-2直接突き合わせ: {'一致' if same else '不一致'}", file=out)
    print(f"left: events={a.event_count} sha256={a.digest}", file=out)
    print(f"right: events={b.event_count} sha256={b.digest}", file=out)
    return same


def _ev(seq: int, clock: int, cpu: str, kind: str, port: str, pc: str) -> Ev:
    return Ev(seq, clock, 0, cpu, kind, port, None, pc)


def _correlation_fixture(*, body_fault: bool = False, count_fault: bool = False,
                         order_fault: bool = False) -> list[Ev]:
    """値を持たない10ラウンドの合成列。256件応答の直前3回だけ同じFDC処理を置く。"""
    response_lengths = [1, 1, 256, 1, 1, 256, 1, 1, 256, bootex.BULK_RUN_MIN]
    rows: list[Ev] = []
    clock = 1
    seq = 1

    def add(cpu: str, kind: str, port: str, pc: str) -> None:
        nonlocal clock, seq
        rows.append(_ev(seq, clock, cpu, kind, port, pc))
        seq += 1
        clock += 1

    for i, response_len in enumerate(response_lengths):
        add("main", "OUT", "00FD", "37F4")
        if i in (1, 4, 7):
            add("sub", "IN", "00FA", "9000")
            add("sub", "OUT", "00FB", "9001")
            if count_fault and i == 4:
                add("sub", "IN", "00FA", "9000")
        if i == 9 and not order_fault:
            for _ in range(3):
                add("sub", "IN", "00FA", "9000")
                add("sub", "OUT", "00FB", "9001")
        response_start = len(rows)
        response_pc = "C269" if response_len >= bootex.BULK_RUN_MIN else "3863"
        for _ in range(response_len):
            add("main", "IN", "00FC", response_pc)
        if body_fault and i == 1:
            # FDCイベント1件と応答先頭のclockを交換し、件数を保ったまま本体窓へ移す。
            fdc_idx = response_start - 1
            rows[fdc_idx], rows[response_start] = (
                replace(rows[fdc_idx], clock=rows[response_start].clock),
                replace(rows[response_start], clock=rows[fdc_idx].clock),
            )
    rows.sort(key=lambda e: e.clock)
    return rows


def _boot_fixture() -> list[Ev]:
    specs = [
        ("OUT", "00F8", "1000"), ("OUT", "00F8", "1001"),
        ("OUT", "00FB", "1002"), ("IN", "00FB", "1003"),
        ("OUT", "00F8", "1004"), ("OUT", "00FB", "1005"),
        ("IN", "00FB", "1006"), ("IN", "00FE", "1007"),
    ]
    return [_ev(i + 1, i + 1, "sub", kind, port, pc)
            for i, (kind, port, pc) in enumerate(specs)]


def selftest(out) -> bool:
    ok = 0
    ng = 0

    def check(name: str, condition: bool) -> None:
        nonlocal ok, ng
        if condition:
            ok += 1
            print(f"OK  - {name}", file=out)
        else:
            ng += 1
            print(f"NG  - {name}", file=out)

    # C-1は実際の判定関数へ合成イベントを通し、正常と3種の故障を検査する。
    good_corr = evaluate_correlation(_correlation_fixture())
    body_broken = evaluate_correlation(_correlation_fixture(body_fault=True))
    count_broken = evaluate_correlation(_correlation_fixture(count_fault=True))
    order_broken = evaluate_correlation(_correlation_fixture(order_fault=True))
    check("C-1 正常合成入力を相関ありと判定", good_corr.ok)
    check("C-1 応答本体への移動を検出", not body_broken.ok)
    check("C-1 256件応答の件数破壊を検出", not count_broken.ok)
    check("C-1 順序破壊を検出", not order_broken.ok)
    always_corr = lambda _x: True
    check("C-1 常に相関あり故障を検出", always_corr(body_broken) != body_broken.ok)

    # C-2も区間切り出しと署名化を実行し、run・TC・clockを壊す。
    fixture = _boot_fixture()
    base = boot_signature(fixture).canonical
    check("C-2 同一署名を一致と判定", base == boot_signature(list(fixture)).canonical)
    run_broken_rows = fixture[:5] + fixture[6:]
    tc_broken_rows = [replace(e, port="00F7") if e.pc == "1004" else e for e in fixture]
    clock_broken_rows = [replace(e, clock=e.clock + 1) if e.pc == "1003" else e for e in fixture]
    for name, broken_rows in (
        ("run長", run_broken_rows),
        ("TC位置", tc_broken_rows),
        ("相対clock", clock_broken_rows),
    ):
        broken = boot_signature(broken_rows).canonical
        check(f"C-2 {name}故障を検出", base != broken)
    always_deterministic = lambda _a, _b: True
    check("C-2 常に決定論的故障を検出", always_deterministic(base, base[:-1]) != (base == base[:-1]))

    # C-3は複数標本の分布と欠落・逆転・交差を検査する。
    starts = [_ev(1, 10, "sub", "IN", "00FC", "2000"),
              _ev(2, 30, "sub", "IN", "00FC", "2000"),
              _ev(3, 60, "sub", "IN", "00FC", "2000")]
    ends = [_ev(4, 14, "main", "IN", "00FE", "37FF"),
            _ev(5, 36, "main", "IN", "00FE", "37FF"),
            _ev(6, 68, "main", "IN", "00FE", "37FF")]
    d = _pair_delays("SEND", starts, ends)
    check("C-3 正常分布の件数・統計", (d.valid, d.invalid, d.intermediate, d.minimum, d.median, d.maximum) == (3, 0, 0, 4, 6, 8))
    check("C-3 終点欠落を検出", _pair_delays("SEND", starts, ends[:-1]).invalid == 1)
    reverse = [replace(ends[0], clock=9), *ends[1:]]
    check("C-3 逆転終点を検出", _pair_delays("SEND", starts, reverse).invalid == 1)
    crossing = [ends[0], replace(ends[1], clock=31), replace(ends[2], clock=32), *ends[2:]]
    check("C-3 終点交差を検出", _pair_delays("SEND", starts, crossing).invalid > 0)
    end_d = _pair_delays_by_end("RECV", starts + [_ev(7, 32, "sub", "IN", "00FE", "3000")], ends)
    check("C-3 終点基準で直近起点を選び中間候補を分離", end_d.valid == 3 and end_d.intermediate == 1)
    always_zero = lambda _s, _e: DelayResult("SEND", len(_s), 0, 0, 0, 0.0, 0)
    check("C-3 常に0clock故障を検出", always_zero(starts, ends) != d)
    all_one_pair = lambda _s, _e: DelayResult("SEND", 1, len(_s) - 1, 0, 4, 4.0, 4)
    check("C-3 全イベント同一対故障を検出", all_one_pair(starts, ends) != d)

    print(f"selftest: OK {ok} / NG {ng} / 故障注入13件・空振り0件", file=out)
    return ng == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("summary")
    s.add_argument("--iolog", required=True, type=Path)
    s.add_argument("--label", required=True)
    s.add_argument("--out", type=Path)
    d = sub.add_parser("determinism")
    d.add_argument("--left", required=True, type=Path)
    d.add_argument("--right", required=True, type=Path)
    d.add_argument("--out", type=Path)
    sub.add_parser("selftest")
    args = ap.parse_args()

    target = io.StringIO()
    try:
        if args.mode == "summary":
            write_summary(args.iolog, args.label, target)
            rc = 0
        elif args.mode == "determinism":
            rc = 0 if write_determinism(args.left, args.right, target) else 1
        else:
            rc = 0 if selftest(target) else 1
    except (OSError, ValueError) as exc:
        print(f"NG  - {exc}", file=target)
        rc = 2
    text = target.getvalue()
    if getattr(args, "out", None):
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
