#!/usr/bin/env python3
"""run切り出し誤差の規則生成陽性対照（m7df）。

公式ログを入力にせず、合成iolog/intlogだけを現行cutへ通す。FEスピン系と
SEND run系は別々に集計し、事前登録した分子・分母との完全一致を検査する。
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import analyze_run_boundary as run_cut  # noqa: E402
import analyze_sub_fe as fe_cut  # noqa: E402
import analyze_sub_proto as sub_proto  # noqa: E402


@dataclass(frozen=True)
class Row:
    clock: int
    cpu: str
    kind: str
    port: str
    value: str
    pc: str


class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.detected = 0
        self.faults = 0

    def check(self, label: str, actual, expected) -> None:
        if actual == expected:
            print(f"OK  - {label}: {actual}")
        else:
            self.failures.append(f"{label}: 実測={actual}, 予測={expected}")
            print(f"NG  - {self.failures[-1]}")

    def fault(self, label: str, detected: bool) -> None:
        self.faults += 1
        if detected:
            self.detected += 1
            print(f"OK  - 故障注入 {label} を検出")
        else:
            self.failures.append(f"故障注入 {label} が空振り")
            print(f"NG  - {self.failures[-1]}")


def write_iolog(path: Path, rows: list[Row]) -> None:
    lines = ["# 規則生成した合成ログ（公式データ不使用）",
             "# seq clock frame cpu kind port value pc"]
    for seq, row in enumerate(sorted(rows, key=lambda x: x.clock), 1):
        lines.append(
            f"{seq} {row.clock} 0 {row.cpu} {row.kind} "
            f"{row.port} {row.value} {row.pc}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_intlog(path: Path, clocks: list[int]) -> None:
    lines = ["# 規則生成した合成割り込みログ（公式データ不使用）"]
    for seq, clock in enumerate(sorted(clocks), 1):
        lines.append(f"{seq} {clock} 0 main 1 0 1000 2000")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fe_fixture(n: int, *, pc: str, entry: int, exit_: int,
               omitted: set[int] | None = None,
               split: set[int] | None = None,
               endpoint: bool = False,
               shifted: bool = False,
               missing: bool = False) -> tuple[list[Row], list[int], set[int]]:
    """n個の真の2読取りスピンを生成する。境界番号iはcall iの直後。"""
    omitted = omitted or set()
    split = split or set()
    rows: list[Row] = []
    interrupt_clocks: list[int] = []
    true_starts: set[int] = set()
    clock = 10
    for i in range(n):
        values = [entry, exit_]
        if endpoint and i == 0:
            values = values[1:]
        if endpoint and i == n - 1:
            values = values[:-1]
        if missing and i == n // 2:
            values = values[:1]
        for pos, value in enumerate(values):
            if pos == 0:
                true_starts.add(clock)
            rows.append(Row(clock, "main", "IN", "00FE", f"{value:02X}", pc))
            clock += 10
            if i in split and pos == 0:
                rows.append(Row(clock, "main", "IN", "00E4", "00", "3000"))
                clock += 10
            if shifted and i == 11 and pos == 0:
                rows.append(Row(clock, "main", "IN", "00E4", "00", "3000"))
                clock += 10
        if i < n - 1:
            if i in omitted or (shifted and i == 10):
                # 直前のexitと次回entryの中間clock。次イベントと同値に
                # すると厳密な前後関係を持たず、境界アンカーにならない。
                interrupt_clocks.append(clock - 5)
            else:
                rows.append(Row(clock, "main", "OUT", "00FF", "0A", "3001"))
                clock += 10
    return rows, interrupt_clocks, true_starts


def fe_current(tmp: Path, name: str, rows: list[Row], pc: str,
               invalid: tuple[int, int]) -> tuple[int, int, list[fe_cut.Ev]]:
    path = tmp / f"fe-{name}.iolog.txt"
    write_iolog(path, rows)
    parsed, _ = fe_cut.parse_iolog(path)
    stats = fe_cut.analyze_sub_fe(parsed, cpu="main")
    if pc not in stats:
        return 0, 0, parsed
    st = stats[pc]
    return st.n_spins, st.transitions[invalid], parsed


def fe_anchored(parsed: list[fe_cut.Ev], pc: str,
                interrupt_clocks: list[int]) -> tuple[int, int]:
    """iologの通常境界に加え、intlogの共通clockを境界として分割する。"""
    cpu_rows = [e for e in parsed if e.cpu == "main"]
    spins: list[list[int]] = []
    cur: list[int] = []
    prev_clock: int | None = None
    for event in cpu_rows:
        target = event.kind == "IN" and event.port == "00FE" and event.pc == pc
        if not target:
            if cur:
                spins.append(cur)
                cur = []
            prev_clock = None
            continue
        has_interrupt = (
            prev_clock is not None
            and any(prev_clock < clock < event.clock for clock in interrupt_clocks)
        )
        if has_interrupt and cur:
            spins.append(cur)
            cur = []
        if event.value is not None:
            cur.append(event.value)
        prev_clock = event.clock
    if cur:
        spins.append(cur)
    incomplete = sum(len(spin) != 2 for spin in spins)
    return len(spins), incomplete


def fe_explicit(parsed: list[fe_cut.Ev], pc: str,
                true_starts: set[int]) -> tuple[int, int]:
    """規則生成時に独立に置いた呼出し開始clockでスピンを切る。"""
    spins: list[list[int]] = []
    cur: list[int] = []
    for event in parsed:
        if not (event.cpu == "main" and event.kind == "IN"
                and event.port == "00FE" and event.pc == pc):
            continue
        if event.clock in true_starts and cur:
            spins.append(cur)
            cur = []
        if event.value is not None:
            cur.append(event.value)
    if cur:
        spins.append(cur)
    return len(spins), sum(len(spin) != 2 for spin in spins)


def send_fixture(n: int = 1000, *, split: set[int] | None = None,
                 merge: set[int] | None = None, endpoint: bool = False,
                 shifted: bool = False, missing: bool = False
                 ) -> tuple[list[Row], list[int], set[int]]:
    split = split or set()
    merge = merge or set()
    rows: list[Row] = []
    int_clocks: list[int] = []
    true_starts: set[int] = set()
    clock = 10
    pcs = ("37F4", "3811", "37F4")
    for i in range(n):
        rows.append(Row(clock, "main", "OUT", "00FF", "0F", "3700"))
        clock += 10
        kept = [0, 1, 2]
        if endpoint and i == 0:
            kept = [1, 2]
        if endpoint and i == n - 1:
            kept = [0, 1]
        if missing and i == n // 2:
            kept = [0, 2]
        first_kept = True
        for pos in kept:
            if first_kept:
                true_starts.add(clock)
                first_kept = False
            rows.append(Row(clock, "main", "OUT", "00FD", "--", pcs[pos]))
            clock += 10
            if i in split and pos == 0:
                rows.append(Row(clock, "main", "IN", "00E4", "00", "3900"))
                clock += 10
            if shifted and i == 11 and pos == 0:
                rows.append(Row(clock, "main", "IN", "00E4", "00", "3900"))
                clock += 10
        if i < n - 1:
            if i in merge or (shifted and i == 10):
                rows.append(Row(clock, "main", "IN", "00FE", "20", "3901"))
                int_clocks.append(clock + 1)
            else:
                rows.append(Row(clock, "main", "IN", "00E4", "00", "3900"))
            clock += 10
    return rows, int_clocks, true_starts


def send_metrics_from_runs(runs: list[list[int]], main_rows) -> tuple[int, int, int, int, int]:
    all_fd = [idx for run in runs for idx in run]
    positions = {idx: pos for pos, idx in enumerate(all_fd)}
    first_yes = first_total = cont_no = cont_total = parity_bad = 0
    for run in runs:
        for pos, idx in enumerate(run):
            flat = positions[idx]
            start = all_fd[flat - 1] + 1 if flat else 0
            has_0f = any(
                e.kind == "OUT" and e.port == "00FF" and e.value == 0x0F
                for e in main_rows[start:idx]
            )
            if pos == 0:
                first_total += 1
                first_yes += int(has_0f)
            else:
                cont_total += 1
                cont_no += int(not has_0f)
        if len(run) >= 2:
            parity = len(run) % 2
            expected_pc = "37F4" if parity else "3811"
            parity_bad += int(main_rows[run[-1]].pc != expected_pc)
    return first_yes, first_total, cont_no, cont_total, parity_bad


def send_current(tmp: Path, name: str, rows: list[Row]):
    path = tmp / f"send-{name}.iolog.txt"
    write_iolog(path, rows)
    parsed, _ = run_cut.m2s.parse_iolog(path)
    runs, main_rows = run_cut.main_send_runs(parsed)
    return send_metrics_from_runs(runs, main_rows), parsed


def send_explicit(parsed, true_starts: set[int], interrupt_clocks: list[int] | None = None,
                  *, respect_current_boundaries: bool = False):
    """明示run開始clock、またはintlog境界で選択イベント列を分ける。"""
    main_rows = [e for e in parsed if e.cpu == "main"]
    fd_idx = [
        i for i, e in enumerate(main_rows)
        if e.kind == "OUT" and e.port == "00FD" and e.pc in run_cut.SEND_PCS
    ]
    runs: list[list[int]] = []
    cur: list[int] = []
    for idx in fd_idx:
        event = main_rows[idx]
        split = event.clock in true_starts and bool(cur)
        if respect_current_boundaries and cur:
            between = main_rows[cur[-1] + 1:idx]
            split = split or any(e.port not in ("00FE", "00FF") for e in between)
        if interrupt_clocks and cur:
            prev_clock = main_rows[cur[-1]].clock
            split = split or any(prev_clock < c < event.clock for c in interrupt_clocks)
        if split:
            runs.append(cur)
            cur = []
        cur.append(idx)
    if cur:
        runs.append(cur)
    return send_metrics_from_runs(runs, main_rows)


def disjoint_boundaries(count: int) -> set[int]:
    return {2 * i for i in range(count)}


def rate(numerator: int, denominator: int) -> str:
    return f"{100.0 * numerator / denominator:.4f}%"


def run_fe_suite(tmp: Path, result: Result) -> None:
    print("== FEスピン系 ==")
    for name, n, pc, entry, exit_, invalid, missing_count, expected_rate in (
        ("pre", 5517, "2000", 0x20, 0x21, (0x21, 0x20), 6, "0.1089%"),
        ("post", 5523, "2001", 0x41, 0x40, (0x40, 0x41), 10, "0.1814%"),
    ):
        base_rows, _, _ = fe_fixture(n, pc=pc, entry=entry, exit_=exit_)
        spins, bad, _ = fe_current(tmp, f"{name}-base", base_rows, pc, invalid)
        result.check(f"{name}正常形のスピン数", spins, n)
        result.check(f"{name}正常形の例外数", bad, 0)

        omitted = set(range(0, missing_count * 2, 2))
        rows, int_clocks, _ = fe_fixture(
            n, pc=pc, entry=entry, exit_=exit_, omitted=omitted)
        spins, bad, parsed = fe_current(tmp, f"{name}-missing", rows, pc, invalid)
        result.check(f"{name}境界欠落の現cutスピン数", spins, n - missing_count)
        result.check(f"{name}境界欠落の現cut例外数", bad, missing_count)
        result.check(f"{name}境界欠落の例外率", rate(bad, spins), expected_rate)
        result.fault(f"FE-{name}-境界欠落", bad == missing_count)

        int_path = tmp / f"fe-{name}.intlog.txt"
        write_intlog(int_path, int_clocks)
        parsed_ints = sub_proto.parse_intlog(int_path)["main"]
        int_clocks_parsed = [event.clock for event in parsed_ints]
        aware_spins, incomplete = fe_anchored(parsed, pc, int_clocks_parsed)
        result.check(f"{name} intlog-aware cutスピン数", aware_spins, n)
        result.check(f"{name} intlog-aware cut不完全数", incomplete, 0)
        result.fault(f"FE-{name}-不可視割り込み", aware_spins == n and bad == missing_count)

        split_set = set(range(missing_count))
        rows, _, starts = fe_fixture(
            n, pc=pc, entry=entry, exit_=exit_, split=split_set)
        split_spins, _, parsed = fe_current(tmp, f"{name}-split", rows, pc, invalid)
        result.check(f"{name}偽分割の現cutスピン数", split_spins, n + missing_count)
        result.check(f"{name}偽分割の明示境界cut",
                     fe_explicit(parsed, pc, starts), (n, 0))
        result.fault(
            f"FE-{name}-偽分割",
            split_spins == n + missing_count
            and fe_explicit(parsed, pc, starts) == (n, 0))

    rows, _, _ = fe_fixture(50, pc="2000", entry=0x20, exit_=0x21, endpoint=True)
    spins, bad, parsed = fe_current(tmp, "endpoint", rows, "2000", (0x21, 0x20))
    _, incomplete = fe_anchored(parsed, "2000", [])
    result.fault("FE-先頭末尾打切り", spins == 50 and bad == 0 and incomplete == 2)

    rows, _, starts = fe_fixture(50, pc="2000", entry=0x20, exit_=0x21, shifted=True)
    spins, bad, parsed = fe_current(tmp, "shifted", rows, "2000", (0x21, 0x20))
    _, incomplete = fe_anchored(parsed, "2000", [])
    result.fault("FE-境界1位置ずれ", bad == 1 and incomplete == 2
                 and fe_explicit(parsed, "2000", starts) == (50, 0))

    rows, _, _ = fe_fixture(50, pc="2000", entry=0x20, exit_=0x21, missing=True)
    spins, bad, parsed = fe_current(tmp, "one-missing", rows, "2000", (0x21, 0x20))
    _, incomplete = fe_anchored(parsed, "2000", [])
    result.fault("FE-1件欠落", spins == 50 and bad == 0 and incomplete == 1)


def run_send_suite(tmp: Path, result: Result) -> None:
    print("== SEND run系 ==")
    rows, _, starts = send_fixture()
    baseline, parsed = send_current(tmp, "base", rows)
    result.check("SEND正常形", baseline, (1000, 1000, 2000, 2000, 0))
    result.check("SEND正常形の明示境界cut", send_explicit(parsed, starts), baseline)

    for count, predicted in ((10, "99.01%"), (53, "94.97%"),
                             (100, "90.91%"), (190, "84.03%")):
        rows, _, starts = send_fixture(split=set(range(count)))
        metrics, parsed = send_current(tmp, f"split-{count}", rows)
        result.check(f"偽分割s={count}の先頭率",
                     f"{100.0 * metrics[0] / metrics[1]:.2f}%", predicted)
        if count == 100:
            result.check("偽分割s=100の分子分母と偶奇反例",
                         (metrics[0], metrics[1], metrics[4]), (1000, 1100, 100))
        corrected = send_explicit(parsed, starts)
        result.check(f"偽分割s={count}の明示境界cut", corrected, baseline)
        result.fault(f"SEND-偽分割-s={count}", metrics != baseline and corrected == baseline)

    for count, predicted in ((20, "99.01%"), (100, "95.24%"),
                             (353, "85.00%")):
        rows, _, starts = send_fixture(merge=disjoint_boundaries(count))
        metrics, parsed = send_current(tmp, f"merge-{count}", rows)
        result.check(f"偽結合m={count}の継続0Fなし率",
                     f"{100.0 * metrics[2] / metrics[3]:.2f}%", predicted)
        if count == 100:
            result.check("偽結合m=100の分子分母と偶奇反例", metrics,
                         (900, 900, 2000, 2100, 100))
        corrected = send_explicit(parsed, starts)
        result.check(f"偽結合m={count}の明示境界cut", corrected, baseline)
        result.fault(f"SEND-偽結合-m={count}", metrics != baseline and corrected == baseline)

    rows, int_clocks, starts = send_fixture(merge=disjoint_boundaries(20))
    metrics, parsed = send_current(tmp, "interrupt", rows)
    int_path = tmp / "send-interrupt.intlog.txt"
    write_intlog(int_path, int_clocks)
    parsed_clocks = [e.clock for e in sub_proto.parse_intlog(int_path)["main"]]
    aware = send_explicit(
        parsed, set(), parsed_clocks, respect_current_boundaries=True)
    result.check("割り込み注入の現cut", metrics, (980, 980, 2000, 2020, 20))
    result.check("割り込み注入のintlog-aware cut", aware, baseline)
    result.fault("SEND-不可視割り込み", metrics != baseline and aware == baseline)

    rows, _, starts = send_fixture(split=set(range(10)))
    metrics, parsed = send_current(tmp, "handler-io", rows)
    corrected = send_explicit(parsed, starts)
    result.check("割り込みhandler I/O注入の現cut", metrics[:2], (1000, 1010))
    result.check("割り込みhandler I/O注入の明示境界cut", corrected, baseline)
    result.fault("SEND-handler-I/O", metrics != baseline and corrected == baseline)

    rows, _, starts = send_fixture(endpoint=True)
    metrics, _ = send_current(tmp, "endpoint", rows)
    result.fault("SEND-先頭末尾打切り", metrics != baseline and metrics[4] >= 1)

    rows, _, starts = send_fixture(shifted=True)
    metrics, parsed = send_current(tmp, "shifted", rows)
    result.fault("SEND-境界1位置ずれ",
                 metrics != baseline and send_explicit(parsed, starts) == baseline)

    rows, _, starts = send_fixture(missing=True)
    metrics, _ = send_current(tmp, "one-missing", rows)
    result.fault("SEND-1件欠落", metrics != baseline and metrics[4] == 1)

    empty_metrics, _ = send_current(tmp, "empty", [])
    result.fault("SEND-0件入力拒否", empty_metrics == (0, 0, 0, 0, 0))
    broken = tmp / "send-broken.iolog.txt"
    broken.write_text("これは解析可能な行ではない\n", encoding="utf-8")
    parsed_broken, _ = run_cut.m2s.parse_iolog(broken)
    result.fault("SEND-解析不能入力拒否", not parsed_broken)


def main() -> int:
    result = Result()
    with tempfile.TemporaryDirectory() as work:
        tmp = Path(work)
        run_fe_suite(tmp, result)
        run_send_suite(tmp, result)
    misses = result.faults - result.detected
    print(f"検出 {result.detected}/{result.faults}、空振り {misses}件")
    if result.failures or misses:
        print("==> 一部 NG")
        return 1
    print("==> 全項目 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
