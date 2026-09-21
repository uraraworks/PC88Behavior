#!/usr/bin/env python3
"""m6i-a main↔sub READの生ログを本文・値列なしで判定する。

入力ファイルはこの解析器だけが読む。標準出力は件数、SHA-256、真偽、
事前登録済み判定名だけで、受信バイト列、データポート値列、画面本文は
一切出さない。未到達は例外にせず ``unreached`` を返す。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_write_path as awp  # noqa: E402
import analyze_sub_proto as subproto  # noqa: E402
import check_l3_screen_output as screencheck  # noqa: E402


EXPECT_SHA = {
    1: "4ed6e24a1fb78f8c79423740e05a311c438bae0f09b9974e50619050fdb8540a",
    2: "f0cb8924325dbf2dece67fbebf41a9ee1ffbcd88fe8493ca18cbb49129d3ab0f",
}
MARKERS = {
    "request": 0xE000,
    "recv256": 0xE001,
    "success": 0xE002,
    "timeout": 0xE003,
    "fault_wait": 0xE004,
    "fault_cont": 0xE005,
    "fault_pair": 0xE006,
}
MEM_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+"
    r"([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s*$"
)


class AnalysisError(Exception):
    """入力不備。メッセージ本文は外へ出さない。"""


@dataclass(frozen=True)
class MemEvent:
    seq: int
    frame: int
    pc: int
    addr: int
    value: int


@dataclass(frozen=True)
class Inputs:
    memlog: Path
    iolog: Path
    report: Path
    intlog: Path | None = None


def require_no_drops(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="strict")
    drops = re.findall(r"取りこぼし:\s*([0-9]+)件", text)
    if not drops or any(int(n) != 0 for n in drops):
        raise AnalysisError("log_drops")


def read_memlog(path: Path) -> list[MemEvent]:
    require_no_drops(path)
    rows: list[MemEvent] = []
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        match = MEM_RE.match(line)
        if match:
            seq, frame, pc, addr, value = match.groups()
            rows.append(MemEvent(int(seq), int(frame), int(pc, 16),
                                 int(addr, 16), int(value, 16)))
    if any(row.seq != index for index, row in enumerate(rows, 1)):
        raise AnalysisError("memlog_sequence")
    return rows


def one_writes(rows: list[MemEvent], addr: int) -> int:
    return sum(row.addr == addr and row.value == 1 for row in rows)


def sector_blocks(rows: list[MemEvent]) -> list[bytes]:
    """DF00-DFFFへの連続256位置書込みを順序・番地込みで切り出す。"""
    blocks: list[bytes] = []
    current: list[int] = []
    expected = 0xDF00
    for row in rows:
        if not 0xDF00 <= row.addr <= 0xDFFF:
            continue
        if row.addr == 0xDF00:
            if current:
                current = []
            expected = 0xDF00
        if row.addr != expected:
            current = []
            expected = 0xDF00
            if row.addr != expected:
                continue
        current.append(row.value)
        expected += 1
        if expected == 0xE000:
            blocks.append(bytes(current))
            current = []
            expected = 0xDF00
    return blocks


def a5_pairs(rows: list[MemEvent]) -> tuple[int, int, int]:
    """(レジスタ一致回数, ポート一致回数, バンク署名一致回数)。"""
    reg_ok = port_ok = bank_ok = 0
    latest: dict[int, int] = {}
    for row in rows:
        latest[row.addr] = row.value
        if row.addr != 0xE034 or row.value != 1:
            continue
        pre = [latest.get(0xE010 + i) for i in range(12)]
        post = [latest.get(0xE01C + i) for i in range(12)]
        ports_pre = [latest.get(0xE028 + i) for i in range(2)]
        ports_post = [latest.get(0xE02A + i) for i in range(2)]
        banks_pre = [latest.get(0xE02C + i) for i in range(4)]
        banks_post = [latest.get(0xE030 + i) for i in range(4)]
        reg_ok += int(None not in pre + post and pre == post)
        port_ok += int(None not in ports_pre + ports_post and ports_pre == ports_post)
        bank_ok += int(None not in banks_pre + banks_post
                       and banks_pre == [0xB0, 0xB1, 0xB2, 0xB3]
                       and banks_post == banks_pre)
    return reg_ok, port_ok, bank_ok


def screen_facts(path: Path) -> dict[str, object]:
    rows = screencheck.read_screen(path)
    sig = screencheck.signature(rows)
    # l3_main_selftest.sh の既存シナリオ base_Q: row2,col0へ小文字q。
    accepted = any(row == 2 and body.startswith("q") for row, body in rows)
    return {
        "key_input_accepted": accepted,
        "screen_line_count": sig.line_count,
        "screen_char_count": sig.char_count,
        "screen_sha256": sig.sha256,
    }


def protocol_runs(io_rows: list[m2s.Ev], sector: int) -> int:
    """5要求→06/C0/12→256受信の完全列を数える。値列は返さない。"""
    data = [row for row in io_rows if row.cpu == "main" and
            ((row.kind == "OUT" and row.port == "00FD") or
             (row.kind == "IN" and row.port == "00FC"))]
    expected_head = [
        ("OUT", 0x02), ("OUT", 0x00), ("OUT", 0x00),
        ("OUT", 0x00), ("OUT", sector), ("OUT", 0x06),
        ("IN", 0xC0), ("OUT", 0x12),
    ]
    count = 0
    for index in range(0, len(data) - len(expected_head) - 256 + 1):
        head = data[index:index + len(expected_head)]
        if any(row.value is None for row in head):
            continue
        if [(row.kind, row.value) for row in head] != expected_head:
            continue
        tail = data[index + len(expected_head):index + len(expected_head) + 256]
        if len(tail) == 256 and all(row.kind == "IN" and row.value is not None
                                    for row in tail):
            count += 1
    return count


def request_runs(io_rows: list[m2s.Ev], sector: int) -> int:
    outs = [row.value for row in io_rows
            if row.cpu == "main" and row.kind == "OUT" and row.port == "00FD"]
    needle = [0x02, 0x00, 0x00, 0x00, sector]
    return sum(outs[i:i + 5] == needle for i in range(len(outs) - 4))


def fdc_facts(io_rows: list[m2s.Ev], sector: int) -> dict[str, object]:
    commands = awp.parse_commands(io_rows)
    reads = [cmd for cmd in commands if cmd.opcode == 0x06]
    senses = [cmd for cmd in commands if cmd.opcode == 0x04]
    coordinate_count = sum(cmd.param_values is not None and len(cmd.param_values) == 8 and
                           cmd.param_values[1:4] == [0, 0, sector] for cmd in reads)
    return {
        "fdc_read_data_count": len(reads),
        "fdc_sense_drive_status_count": len(senses),
        "fdc_read_coordinate_match": coordinate_count > 0,
        "fdc_read_coordinate_match_count": coordinate_count,
    }


def main_interrupt_count(path: Path | None) -> int:
    if path is None:
        return 0
    require_no_drops(path)
    return len(subproto.parse_intlog(path)["main"])


def analyze_single(inputs: Inputs, sector: int, srm_before: int,
                   srm_after: int) -> tuple[dict[str, object], list[bytes]]:
    mem = read_memlog(inputs.memlog)
    require_no_drops(inputs.iolog)
    io_rows, masked = m2s.parse_iolog(inputs.iolog)
    if sum(masked.values()):
        raise AnalysisError("masked_input")
    blocks = sector_blocks(mem)
    hashes = [hashlib.sha256(block).hexdigest() for block in blocks]
    facts: dict[str, object] = {
        "srm_before_count": srm_before,
        "srm_after_count": srm_after,
        "request_marker_count": one_writes(mem, MARKERS["request"]),
        "recv256_marker_count": one_writes(mem, MARKERS["recv256"]),
        "success_marker_count": one_writes(mem, MARKERS["success"]),
        "timeout_marker_count": one_writes(mem, MARKERS["timeout"]),
        "fault_wait_marker_count": one_writes(mem, MARKERS["fault_wait"]),
        "fault_cont_marker_count": one_writes(mem, MARKERS["fault_cont"]),
        "fault_pair_marker_count": one_writes(mem, MARKERS["fault_pair"]),
        "receive_complete_block_count": len(blocks),
        "receive_position_count": len(blocks[-1]) if blocks else 0,
        "receive_sha256": hashes[-1] if hashes else None,
        "request_run_count": request_runs(io_rows, sector),
        "complete_protocol_run_count": protocol_runs(io_rows, sector),
    }
    facts.update(fdc_facts(io_rows, sector))
    facts.update(screen_facts(inputs.report))
    facts["main_interrupt_count"] = main_interrupt_count(inputs.intlog)
    reg_ok, port_ok, bank_ok = a5_pairs(mem)
    facts.update({
        "register_preserved_count": reg_ok,
        "bank_port_restored_count": port_ok,
        "bank_signature_preserved_count": bank_ok,
        "bank_probe_count": one_writes(mem, 0xE034),
        "repeat_done_marker_count": one_writes(mem, 0xE035),
        "all_receive_sha_match": bool(hashes) and all(h == EXPECT_SHA[1] for h in hashes),
    })
    return facts, blocks


def reached_normal(f: dict[str, object], expected_runs: int, sector: int) -> bool:
    return (
        f["request_marker_count"] == expected_runs
        and f["recv256_marker_count"] == expected_runs
        and f["success_marker_count"] == expected_runs
        and f["timeout_marker_count"] == 0
        and f["receive_complete_block_count"] == expected_runs
        and f["request_run_count"] == expected_runs
        and f["complete_protocol_run_count"] == expected_runs
        and f["fdc_read_data_count"] >= expected_runs
        and f["fdc_read_coordinate_match_count"] >= expected_runs
        and (f["receive_sha256"] == EXPECT_SHA[sector])
        and f["key_input_accepted"]
    )


def normal_reach_indicators(f: dict[str, object], expected_runs: int) -> bool:
    """SHAと復帰可否を除く、事前登録の到達指標。"""
    return (
        f["request_marker_count"] == expected_runs
        and f["recv256_marker_count"] == expected_runs
        and f["success_marker_count"] == expected_runs
        and f["receive_complete_block_count"] == expected_runs
        and f["request_run_count"] == expected_runs
        and f["complete_protocol_run_count"] == expected_runs
        and f["fdc_read_data_count"] >= expected_runs
        and f["fdc_read_coordinate_match_count"] >= expected_runs
    )


def last_reached(f: dict[str, object]) -> str:
    if f["success_marker_count"]:
        return "成功完了印"
    if f["timeout_marker_count"]:
        return "timeout完了印"
    if f["recv256_marker_count"]:
        return "256位置受信完了印"
    if f["request_marker_count"]:
        return "要求run完了印"
    if any(f[name] for name in ("fault_wait_marker_count", "fault_cont_marker_count",
                                 "fault_pair_marker_count")):
        return "故障注入通過印"
    return "なし"


def judge_one(arm: str, f: dict[str, object], screen_expected: tuple[int, int, str] | None
              ) -> tuple[str, bool, str]:
    if f["srm_before_count"] != 0:
        return "gate_failed", False, "srm_present_before_run"
    if arm == "A0":
        reached = normal_reach_indicators(f, 1)
        if not reached:
            return "unreached", False, "normal_reach_marker_missing"
        passed = reached_normal(f, 1, 1) and f["key_input_accepted"]
        return ("read_matches_generated_sector" if passed else "read_data_mismatch",
                passed, "matched" if passed else "normal_condition_mismatch")
    if arm == "A1":
        reached = normal_reach_indicators(f, 1)
        if not reached:
            return "unreached", False, "normal_reach_marker_missing"
        passed = reached_normal(f, 1, 2) and f["receive_sha256"] != EXPECT_SHA[1]
        return ("sector_select_changes_signature" if passed else "fixed_value_suspected",
                passed, "matched" if passed else "sector_signature_condition_mismatch")
    if arm == "A2":
        reached = (f["request_marker_count"] == 1 and
                   f["fdc_sense_drive_status_count"] >= 2 and
                   f["fdc_read_data_count"] == 0 and f["timeout_marker_count"] == 1)
        if not reached:
            return "unreached", False, "no_media_reach_condition_missing"
        passed = (f["success_marker_count"] == 0 and
                  f["recv256_marker_count"] == 0 and f["key_input_accepted"])
        return ("no_media_returns" if passed else "no_media_hangs_or_completes",
                passed, "matched" if passed else "no_media_return_condition_mismatch")
    if arm == "A3":
        if f["fault_wait_marker_count"] < 1:
            return "unreached", False, "fault_marker_missing"
        escaped = reached_normal(f, 1, 1)
        return ("wait_negative_escaped" if escaped else "wait_negative_detected",
                not escaped, "negative_escaped" if escaped else "negative_detected")
    if arm == "A5":
        reached = (normal_reach_indicators(f, 200) and
                   f["bank_probe_count"] == 200 and
                   f["repeat_done_marker_count"] == 1 and
                   f["main_interrupt_count"] >= 1 and f["key_input_accepted"])
        if not reached:
            return "unreached", False, "repeat_reach_condition_missing"
        screen_ok = screen_expected is not None and (
            f["screen_line_count"], f["screen_char_count"], f["screen_sha256"]
        ) == screen_expected
        passed = (reached_normal(f, 200, 1) and f["all_receive_sha_match"] and
                  f["register_preserved_count"] == 200 and
                  f["bank_port_restored_count"] == 200 and
                  f["bank_signature_preserved_count"] == 200 and screen_ok)
        return ("integration_regression_free" if passed else "integration_regressed",
                passed, "matched" if passed else "integration_condition_mismatch")
    raise AnalysisError("unknown_arm")


def parse_screen_expected(text: str | None) -> tuple[int, int, str] | None:
    if text is None:
        return None
    fields = text.split(":")
    if len(fields) != 3 or not re.fullmatch(r"[0-9a-f]{64}", fields[2]):
        raise AnalysisError("screen_expected_format")
    return int(fields[0]), int(fields[1]), fields[2]


def emit(payload: dict[str, object]) -> None:
    # ensure_asciiにより、入力由来の本文が偶発的に混ざっても可視文字列として
    # 出ないが、そもそもpayloadへ本文・値列を入れないことが第一防壁。
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=("A0", "A1", "A2", "A3", "A4", "A5"))
    ap.add_argument("--memlog", type=Path)
    ap.add_argument("--iolog", type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--intlog", type=Path)
    ap.add_argument("--cont-memlog", type=Path)
    ap.add_argument("--cont-iolog", type=Path)
    ap.add_argument("--cont-report", type=Path)
    ap.add_argument("--pair-memlog", type=Path)
    ap.add_argument("--pair-iolog", type=Path)
    ap.add_argument("--pair-report", type=Path)
    ap.add_argument("--srm-before", type=int, default=0)
    ap.add_argument("--srm-after", type=int, default=0)
    ap.add_argument("--screen-expected", help="line_count:char_count:sha256")
    args = ap.parse_args()
    try:
        if args.arm == "A4":
            paths = (args.cont_memlog, args.cont_iolog, args.cont_report,
                     args.pair_memlog, args.pair_iolog, args.pair_report)
            if any(path is None for path in paths):
                raise AnalysisError("a4_inputs_missing")
            cont, _ = analyze_single(Inputs(args.cont_memlog, args.cont_iolog,
                                             args.cont_report), 1,
                                     args.srm_before, args.srm_after)
            pair, _ = analyze_single(Inputs(args.pair_memlog, args.pair_iolog,
                                             args.pair_report), 1,
                                     args.srm_before, args.srm_after)
            if args.srm_before != 0:
                judgment, passed, reason = "gate_failed", False, "srm_present_before_run"
            elif cont["fault_cont_marker_count"] < 1 or pair["fault_pair_marker_count"] < 1:
                judgment, passed, reason = "unreached", False, "fault_marker_missing"
            else:
                escaped = reached_normal(cont, 1, 1) or reached_normal(pair, 1, 1)
                judgment = "sequence_negative_escaped" if escaped else "sequence_negative_detected"
                passed, reason = not escaped, ("negative_escaped" if escaped else "negative_detected")
            payload = {
                "arm": "A4", "judgment": judgment, "passed": passed, "reason": reason,
                "cont_last_reached": last_reached(cont),
                "pair_last_reached": last_reached(pair),
                "cont_fault_marker_count": cont["fault_cont_marker_count"],
                "pair_fault_marker_count": pair["fault_pair_marker_count"],
                "cont_receive_position_count": cont["receive_position_count"],
                "pair_receive_position_count": pair["receive_position_count"],
                "cont_receive_sha256": cont["receive_sha256"],
                "pair_receive_sha256": pair["receive_sha256"],
                "srm_before_count": args.srm_before, "srm_after_count": args.srm_after,
            }
        else:
            if args.memlog is None or args.iolog is None or args.report is None:
                raise AnalysisError("inputs_missing")
            facts, _ = analyze_single(Inputs(args.memlog, args.iolog, args.report,
                                              args.intlog),
                                      2 if args.arm == "A1" else 1,
                                      args.srm_before, args.srm_after)
            judgment, passed, reason = judge_one(
                args.arm, facts, parse_screen_expected(args.screen_expected))
            payload = {"arm": args.arm, "judgment": judgment, "passed": passed,
                       "reason": reason, "last_reached": last_reached(facts), **facts}
        emit(payload)
        return 0 if payload["passed"] else 1
    except (OSError, UnicodeError, ValueError, AnalysisError, awp.SafeError,
            screencheck.ScreenError):
        emit({"arm": args.arm, "judgment": "unreached", "passed": False,
              "reason": "analysis_input_error", "last_reached": "不明"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
