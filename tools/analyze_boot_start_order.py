#!/usr/bin/env python3
"""起動直後のmain送信・sub受信・FDC初期化・応答の順序だけを検査する。

入力は伏せ済みの共通clock付きiolog。clockはイベントを一列に並べるためだけに
使い、絶対値は出力しない。データポートのvalue列も読み捨て、出力するのは
イベント種別の順序、件数、合否だけである。

既存の ``analyze_main_to_sub.py`` のパーサ／main SEND・RECV分類と、
``analyze_boot_fdc_sequence.py`` の起動時FDC初期化窓／batch分割を再利用する。

再実行例:
  python3 tools/analyze_boot_start_order.py \
    --iolog measurements/m6g-d0-boot-run1.iolog.txt.gz \
    --iolog measurements/m6g-d0-boot-run2.iolog.txt.gz
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_boot_fdc_sequence as boot_fdc  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402


@dataclass(frozen=True)
class Result:
    startup_rx_count: int
    init_batch_count: int
    sub_response_before_second_send: int
    main_response_before_second_send: int
    first_response_sub_tx_count: int
    first_response_main_rx_count: int
    order_ok: bool
    shape_ok: bool

    @property
    def ok(self) -> bool:
        return self.order_ok and self.shape_ok


def _strictly_increasing(values: list[int]) -> bool:
    return all(a < b for a, b in zip(values, values[1:]))


def analyze(rows: list[m2s.Ev]) -> Result:
    """順序命題を検査する。valueおよびclockの絶対値は結果へ保持しない。"""
    sub = [e for e in rows if e.cpu == "sub"]
    window = boot_fdc.find_boot_init_window(sub)
    sends = [e for e in m2s.classify_transactions(rows) if m2s.tx_kind(e) == "SEND"]
    main_recvs = [e for e in m2s.classify_transactions(rows)
                  if m2s.tx_kind(e) in ("RECV", "BULK_RECV")]

    if window is None or len(sends) < 2 or not main_recvs:
        return Result(0, 0, 0, 0, 0, 0, False, False)

    start, end = window
    init = sub[start:end]
    if not init:
        return Result(0, 0, 0, 0, 0, 0, False, False)

    init_runs = boot_fdc.segment_runs(init)
    alternating = all(
        run["kind"] == ("OUT" if i % 2 == 0 else "IN")
        for i, run in enumerate(init_runs)
    )
    batch_count = len(init_runs) // 2 if len(init_runs) % 2 == 0 and alternating else 0

    first_send, second_send = sends[0], sends[1]
    init_start, init_end = init[0], init[-1]
    startup_rxs = [
        e for e in sub
        if e.kind == "IN" and e.port == "00FC"
        and first_send.clock < e.clock < init_start.clock
    ]
    sub_txs_before_second = [
        e for e in sub
        if e.kind == "OUT" and e.port == "00FD"
        and first_send.clock < e.clock < second_send.clock
    ]
    main_recvs_before_second = [
        e for e in main_recvs if first_send.clock < e.clock < second_send.clock
    ]
    sub_txs_after_second = [
        e for e in sub
        if e.kind == "OUT" and e.port == "00FD" and e.clock > second_send.clock
    ]
    main_recvs_after_second = [e for e in main_recvs if e.clock > second_send.clock]

    if not startup_rxs or not sub_txs_after_second or not main_recvs_after_second:
        return Result(
            len(startup_rxs), batch_count, len(sub_txs_before_second),
            len(main_recvs_before_second), 0, 0, False, False,
        )

    first_sub_tx = sub_txs_after_second[0]
    first_main_recv = main_recvs_after_second[0]
    first_response_sub_tx_count = sum(
        second_send.clock < e.clock <= first_main_recv.clock for e in sub_txs_after_second
    )
    first_response_main_rx_count = sum(
        second_send.clock < e.clock <= first_main_recv.clock for e in main_recvs_after_second
    )
    order_ok = _strictly_increasing([
        first_send.clock,
        startup_rxs[0].clock,
        init_start.clock,
        init_end.clock,
        second_send.clock,
        first_sub_tx.clock,
        first_main_recv.clock,
    ])
    shape_ok = (
        len(startup_rxs) == 1
        and batch_count == 7
        and len(sub_txs_before_second) == 0
        and len(main_recvs_before_second) == 0
        and first_response_sub_tx_count == 1
        and first_response_main_rx_count == 1
    )
    return Result(
        len(startup_rxs), batch_count, len(sub_txs_before_second),
        len(main_recvs_before_second), first_response_sub_tx_count,
        first_response_main_rx_count, order_ok, shape_ok,
    )


def print_result(index: int, result: Result) -> None:
    print(f"入力{index}: 判定={'OK' if result.ok else 'NG'}")
    print("  順序: main送信#1 -> sub起動専用受信 -> FDC初期化開始 "
          "-> FDC初期化完了 -> main送信#2 -> sub応答#1 -> main受信#1")
    print(f"  sub起動専用受信件数={result.startup_rx_count}")
    print(f"  FDC初期化batch件数={result.init_batch_count}")
    print(f"  main送信#2前sub応答件数={result.sub_response_before_second_send}")
    print(f"  main送信#2前main受信件数={result.main_response_before_second_send}")
    print(f"  初回応答sub送信件数={result.first_response_sub_tx_count}")
    print(f"  初回応答main受信件数={result.first_response_main_rx_count}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iolog", action="append", required=True, type=Path)
    args = parser.parse_args()

    all_ok = True
    for index, path in enumerate(args.iolog, 1):
        rows, _masked = m2s.parse_iolog(path)
        result = analyze(rows)
        print_result(index, result)
        all_ok &= result.ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
