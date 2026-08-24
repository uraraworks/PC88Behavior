#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO" <<'PY'
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

repo = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "analyze_no_disk_timing", repo / "tools/analyze_no_disk_timing.py")
timing = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = timing
spec.loader.exec_module(timing)


def write_iolog(path, *, base, gap2=0, gap3=0, gap4=0,
                wait_delay=0, ready_delay=0):
    rows = []
    seq = 0
    def add(clock, cpu, kind, port, value, pc):
        nonlocal seq
        seq += 1
        rows.append((clock, seq, cpu, kind, port, value, pc))

    # 校正窓: m2, s256, m1, s1, m6。値は解析結果へ保持しない。
    add(base + 0, "main", "OUT", "00FD", "--", "37F4")
    add(base + 1, "main", "OUT", "00FD", "--", "3811")
    for index in range(256):
        add(base + 10 + index, "main", "IN", "00FC", "--", "3880")
    run2 = base + 300 + gap2
    add(run2, "main", "OUT", "00FD", "--", "3811")
    wait_start = run2 + 20
    ready = wait_start + 30 + wait_delay
    read = ready + 10 + ready_delay
    add(wait_start, "main", "IN", "00FE", "20", "3853")
    add(wait_start + 2, "main", "IN", "00FE", "21", "3853")
    add(ready, "sub", "OUT", "00FD", "--", "0001")
    add(read + gap3, "main", "IN", "00FC", "--", "3863")
    axis = base + 400 + gap4
    # sub側も確定済みbit0..3の変化だけを解析できるサンプルを置く。
    add(base + 5, "sub", "IN", "00FE", "00", "0002")
    add(base + 7, "sub", "IN", "00FE", "02", "0002")
    for index in range(6):
        add(axis + index, "main", "OUT", "00FD", "--", "37F4")
    rows.sort()
    path.write_text("\n".join(
        f"{seq} {clock} 700 {cpu} {kind} {port} {value} {pc}"
        for clock, seq, cpu, kind, port, value, pc in rows
    ) + "\n# 取りこぼし: 0件\n", encoding="utf-8")


def write_intlog(path, clocks):
    rows = []
    for seq, (clock, cpu) in enumerate(clocks, 1):
        rows.append(f"{seq} {clock} 700 {cpu} 1 0 1000 2000")
    path.write_text("\n".join(rows) + "\n# 取りこぼし: 0件\n",
                    encoding="utf-8")


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    off_io, mix_io = tmp / "off.io", tmp / "mix.io"
    off_int, mix_int = tmp / "off.int", tmp / "mix.int"
    write_iolog(off_io, base=100)
    write_iolog(mix_io, base=1100, gap2=3, gap3=2, gap4=7,
                wait_delay=5, ready_delay=2)
    write_intlog(off_int, [(105, "main"), (430, "main"), (440, "sub")])
    write_intlog(mix_int, [(1105, "main"), (1430, "main"),
                           (1440, "main"), (1475, "sub"), (1480, "sub")])

    result = timing.compare(off_io, off_int, mix_io, mix_int, 4, 4)
    diff = result["differences"]
    if diff["interrupt_counts_mixed_minus_official"]["main"]["calibration_window"] != 1:
        raise SystemExit("NG: 窓内main割り込み受理件数差を検出できない")
    if diff["logical_arrival_mixed_minus_official"]["+0"] != 7:
        raise SystemExit("NG: 共通基準から+0へ到達するclock位相差を検出できない")
    print("OK: 同じ論理位置への到達位相をずらす故障を検出")

    # 実験driverと同じログ故障注入: 基準clockより後だけを既知量ずらす。
    shifted_io, shifted_int = tmp / "shifted.io", tmp / "shifted.int"
    shifted_io.write_bytes(mix_io.read_bytes())
    shifted_int.write_bytes(mix_int.read_bytes())
    search_spec = importlib.util.spec_from_file_location(
        "search_error_response_candidate",
        repo / "tools/search_error_response_candidate.py")
    search = importlib.util.module_from_spec(search_spec)
    sys.modules[search_spec.name] = search
    search_spec.loader.exec_module(search)
    reference_clock = timing.shape.exchange_runs(shifted_io)[0].start_clock
    search.inject_clock_shift((shifted_io, shifted_int),
                              after_clock=reference_clock, delta=257)
    shifted = timing.compare(off_io, off_int, shifted_io, shifted_int, 4, 4)
    expected = {key: value + 257 for key, value in
                diff["logical_arrival_mixed_minus_official"].items()}
    if shifted["differences"]["logical_arrival_mixed_minus_official"] != expected:
        raise SystemExit("NG: armログへの既知clockずらしをarrival_deltaが検出しない")
    if search.metric_source_sha256(mix_io, mix_int) == search.metric_source_sha256(
            shifted_io, shifted_int):
        raise SystemExit("NG: arm固有入力の指紋がclock故障注入を識別しない")
    print("OK: 独立armログのclock +257故障をarrival_deltaと入力指紋が検出")
    if diff["interrupt_counts_mixed_minus_official"]["sub"]["axis_near"] != 2:
        raise SystemExit("NG: 軸近傍sub割り込み受理件数差を検出できない")
    if result["official"]["fe_handshake"]["main"]["transition_count"] != 1:
        raise SystemExit("NG: main側$FE状態遷移列を抽出できない")
    intervals = result["differences"]["one_byte_response_mixed_minus_official"]
    if intervals != {"main_wait_until_sub_ready": 5,
                     "sub_ready_until_main_read": 4}:
        raise SystemExit(f"NG: 軸直前1バイト応答の2間隔差が不正: {intervals}")
    print("OK: sub準備位相とmain読取位相をずらす故障を2間隔で検出")
    report = "\n".join(timing.report_lines(result))
    if "校正窓" not in report or "軸直前1バイト応答" not in report:
        raise SystemExit("NG: 値なしレポートへ全指標を出力できない")
    print("OK: 割り込み件数・到達位相・$FE遷移・1バイト応答間隔を値なしで抽出")

    # 故障注入1: 件数計算を定数化すると、既知のmain/sub割り込み件数差が消える。
    constant = timing.compare(
        off_io, off_int, mix_io, mix_int, 4, 4, fault_constant_counts=True)
    if constant["differences"]["interrupt_counts_mixed_minus_official"]["main"][
            "calibration_window"] != 0:
        raise SystemExit("NG: 件数定数化故障を合成できない")
    if diff["interrupt_counts_mixed_minus_official"]["main"]["calibration_window"] == 0:
        raise SystemExit("NG: 件数定数化故障を検出できない")
    if constant["differences"]["interrupt_counts_mixed_minus_official"]["sub"][
            "axis_near"] != 0 or diff[
            "interrupt_counts_mixed_minus_official"]["sub"]["axis_near"] == 0:
        raise SystemExit("NG: sub割り込み受理件数の定数化故障を検出できない")
    print("OK: main/sub件数を定数化する故障を既知の割り込み件数差で検出")

    # 故障注入2: 同じ$FE列の相対位相だけをずらし、位相列比較が拾うことを確認。
    off_runs = timing.shape.exchange_runs(off_io)
    off_bounds = timing.bounds(off_runs, 4)
    off_rows, _ = timing.m2s.parse_iolog(off_io)
    normal_phase = timing.fe_transition_summary(off_rows, off_bounds, "main")
    shifted_phase = timing.fe_transition_summary(
        off_rows, off_bounds, "main", fault_shift=1)
    if normal_phase == shifted_phase:
        raise SystemExit("NG: $FE遷移の位相ずらし故障を検出できない")
    print("OK: $FE状態遷移列の位相をずらす故障を検出")

    # 故障注入3: 混成遷移列の1要素だけを壊し、既定の要約が位置を報告する。
    injected = json.loads(json.dumps(result))
    injected["mixed"]["fe_handshake"]["main"] = json.loads(json.dumps(
        injected["official"]["fe_handshake"]["main"]))
    injected["mixed"]["fe_handshake"]["main"]["transitions"][0][
        "interval_from_previous_fe"] += 1
    summary_report = "\n".join(timing.report_lines(injected))
    if "$FE main差" not in summary_report or "差異位置=0" not in summary_report:
        raise SystemExit("NG: 1点だけの$FE差を要約が報告しない")
    compact = timing.compact_result(injected)
    if compact["differences"]["fe_transition_difference_positions"]["main"] != [0]:
        raise SystemExit("NG: 既定JSON要約が1点差を保持しない")
    if "遷移列（全量）" in summary_report:
        raise SystemExit("NG: 既定レポートへ全量遷移列を出している")
    print("OK: 1点差の故障注入を差分要約が位置0として報告（全量は既定非表示）")

    encoded = json.dumps(result, ensure_ascii=False)
    for forbidden in ('"value"', 'ret_pc', 'handler_pc', 'absolute_clock'):
        if forbidden in encoded:
            raise SystemExit(f"NG: 情報境界外の項目を結果へ保存した: {forbidden}")
    print("OK: 交換値・生$FE値・PC・絶対clockを集約結果へ保存しない")
PY
