#!/usr/bin/env python3
"""m7dm: `run_length6_protocol_axis.py`の陽性対照・故障注入。

Y2(sub側FDCアクセス件数)・Y3(往復の位置)・Y4(直後FDCコマンド種別)それぞれに
既知の生成規則を仕込んだ合成ログで検出力を確認する。あわせて、評価関数が
「常に誤り0件」を返す壊れ方をしていないこと、「run長==6」への言い換えに
過ぎない候補を正しく不合格にできることも確認する。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_sub_proto as sub_proto  # noqa: E402
import boundary_match_rule_search as bmrs  # noqa: E402
import run_length6_protocol_axis as y  # noqa: E402
from analyze_run_cutter_attribution_selftest import (  # noqa: E402
    Row, write_iolog, write_empty_intlog,
)
from boundary_match_rule_search_selftest import emit_run  # noqa: E402


class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, label: str, actual, expected) -> None:
        if actual == expected:
            print(f"OK  - {label}: {actual}")
        else:
            self.failures.append(f"{label}: 実測={actual!r}, 予測={expected!r}")
            print(f"NG  - {self.failures[-1]}")

    def check_true(self, label: str, cond: bool) -> None:
        self.check(label, bool(cond), True)


R = Result()


def load_protocol_instances(rows: list[Row], condition: str) -> list:
    tmp = Path(tempfile.mkdtemp())
    iolog, intlog = tmp / "io.txt", tmp / "int.txt"
    write_iolog(iolog, rows)
    write_empty_intlog(intlog)
    parsed, _ = m2s.parse_iolog(iolog)
    interrupts = sub_proto.parse_intlog(intlog)
    return y.build_protocol_instances(parsed, interrupts, condition)


def emit_fdc_access(rows: list[Row], clock: int, n: int) -> int:
    """sub $FA/$FBへn件の孤立アクセスを積む(コマンド構造は問わない、Y2用)。"""
    for k in range(n):
        rows.append(Row(clock, "sub", "IN", "00FA", "01", "9000"))
        clock += 10
    return clock


def emit_read_command(rows: list[Row], clock: int) -> int:
    """READ DATA(opcode 0x06)の最小構成をsub $FBへ積む(Y4用)。
    opcode(OUT) + param8(OUT) + result7(IN)。値は0固定(構造だけが対象)。
    """
    rows.append(Row(clock, "sub", "OUT", "00FB", "06", "A000")); clock += 10
    for _ in range(8):
        rows.append(Row(clock, "sub", "OUT", "00FB", "00", "A000")); clock += 10
    for _ in range(7):
        rows.append(Row(clock, "sub", "IN", "00FB", "00", "A000")); clock += 10
    return clock


# --- Y2: sub側FDCアクセス件数 -----------------------------------------------

def check_y2() -> None:
    rows: list[Row] = []
    clock = 10
    clock = emit_run(rows, clock, ("37F4", "3811"), None)  # filler
    for _ in range(3):
        run_start = clock
        clock = emit_run(rows, clock, ("37F4", "37F4", "37F4"), "ff")
        # 対応するRECV(IN $FC)をwindow終端として追加
        rows.append(Row(clock, "main", "IN", "00FC", "--", "3880")); clock += 10
        # windowの内側にFDCアクセス5件
        clock = emit_fdc_access(rows, run_start + 5, 5)
        clock = max(clock, run_start) + 10
    for _ in range(3):
        run_start = clock
        clock += 2000
        clock = emit_run(rows, clock, ("37F4", "37F4", "3811"), "split")
        rows.append(Row(clock, "main", "IN", "00FC", "--", "3880")); clock += 10

    instances = load_protocol_instances(rows, "SYN_Y2")
    pos = sum(1 for i in instances if i.label)
    neg = sum(1 for i in instances if not i.label)
    R.check("Y2陽性対照/真陽性件数(FDCアクセスあり)", pos, 3)
    R.check("Y2陽性対照/真陰性件数(境界だけ壊れた偽物)", neg, 3)

    cand = y.build_candidates(instances)
    result = y.evaluate({"Y2_fdc>=1": cand["Y2_fdc>=1"]}, instances)
    R.check("Y2陽性対照/対象軸の誤り件数", result["Y2_fdc>=1"]["errors"], 0)

    other = y.evaluate({"Y4_next=なし": cand["Y4_next=なし"]}, instances)
    R.check_true("Y2陰性対照/対象でない軸(Y4_next=なし)は誤り0件にならない",
                 other["Y4_next=なし"]["errors"] > 0)


# --- Y4: 直後FDCコマンド種別 --------------------------------------------------

def check_y4() -> None:
    rows: list[Row] = []
    clock = 10
    clock = emit_run(rows, clock, ("37F4", "3811"), None)
    for _ in range(3):
        clock = emit_run(rows, clock, ("37F4", "37F4", "37F4"), "ff")
        rows.append(Row(clock, "main", "IN", "00FC", "--", "3880")); clock += 10
        clock = emit_read_command(rows, clock)
        clock += 20
    for _ in range(3):
        clock += 500
        clock = emit_run(rows, clock, ("37F4", "37F4", "3811"), "split")
        rows.append(Row(clock, "main", "IN", "00FC", "--", "3880")); clock += 10

    instances = load_protocol_instances(rows, "SYN_Y4")
    pos = sum(1 for i in instances if i.label)
    neg = sum(1 for i in instances if not i.label)
    R.check("Y4陽性対照/真陽性件数(直後READ)", pos, 3)
    R.check("Y4陽性対照/真陰性件数(直後コマンドなし)", neg, 3)

    cand = y.build_candidates(instances)
    result = y.evaluate({"Y4_next=READ": cand["Y4_next=READ"]}, instances)
    R.check("Y4陽性対照/対象軸の誤り件数", result["Y4_next=READ"]["errors"], 0)

    other = y.evaluate({"Y2_fdc==0": cand["Y2_fdc==0"]}, instances)
    R.check_true("Y4陰性対照/対象でない軸(Y2_fdc==0)は誤り0件にならない",
                 other["Y2_fdc==0"]["errors"] > 0)


# --- Y3: ordinal(通し番号) ---------------------------------------------------

def check_y3_ordinal() -> None:
    rows: list[Row] = []
    clock = 10
    for _ in range(3):
        clock = emit_run(rows, clock, ("37F4", "37F4", "37F4"), "ff")
        rows.append(Row(clock, "main", "IN", "00FC", "--", "3880")); clock += 10
    # 間に大量のfillerを挟んで通し番号を後ろへずらす
    for _ in range(30):
        clock = emit_run(rows, clock, ("37F4", "3811"), None)
        rows.append(Row(clock, "main", "IN", "00FC", "--", "3880")); clock += 10
    for _ in range(3):
        clock = emit_run(rows, clock, ("37F4", "37F4", "3811"), "split")
        rows.append(Row(clock, "main", "IN", "00FC", "--", "3880")); clock += 10

    instances = load_protocol_instances(rows, "SYN_Y3")
    pos = sum(1 for i in instances if i.label)
    neg = sum(1 for i in instances if not i.label)
    R.check("Y3陽性対照/真陽性件数(通し番号が早い)", pos, 3)
    R.check("Y3陽性対照/真陰性件数(通し番号が遅い)", neg, 3)

    cand = y.build_candidates(instances)
    result = y.evaluate({"Y3_ordinal<5": cand["Y3_ordinal<5"]}, instances)
    R.check("Y3陽性対照/対象軸の誤り件数", result["Y3_ordinal<5"]["errors"], 0)

    other = y.evaluate({"Y4_next=READ": cand["Y4_next=READ"]}, instances)
    R.check_true("Y3陰性対照/対象でない軸(Y4_next=READ)は誤り0件にならない",
                 other["Y4_next=READ"]["errors"] > 0)


# --- 評価関数の故障注入(m7dkと同じ評価器を再利用しているだけの再確認) --------

def check_evaluate_not_degenerate() -> None:
    Instance = bmrs.Instance
    mk = lambda cat: Instance(  # noqa: E731
        indicator="0f", condition="X", run_len=6, position=0,
        pc_pattern=("37F4",), gap_prev=None, phase="normal", category=cat,
    )
    instances = [mk("boundary_match"), mk("boundary_match"),
                 mk("false_split"), mk("interrupt_boundary")]
    always_true = lambda i: True  # noqa: E731
    result = y.evaluate({"always_true": always_true}, instances)
    R.check("故障注入/常時Trueは誤り2件を正しく報告する(0固定ではない、評価器はm7dkと共通)",
            result["always_true"]["errors"], 2)


# --- run長6への言い換え判定 ---------------------------------------------------

def check_tautology_rejected() -> None:
    """m7dkの実測(0F側)と同じ構成——run長6かつboundary_match44件、
    run長6以外のboundary_match4件、run長6だがboundary_matchでない4件、
    残り40件——を模した合成母集団で、「run_len==6」候補が誤り8件のまま
    (0件にならない)ことを確認する。"""
    Instance = bmrs.Instance
    instances = []
    def mk(run_len, cat):
        return Instance(indicator="0f", condition="X", run_len=run_len,
                        position=0, pc_pattern=("37F4",), gap_prev=None,
                        phase="normal", category=cat)
    instances += [mk(6, "boundary_match") for _ in range(44)]
    instances += [mk(3, "boundary_match") for _ in range(4)]
    instances += [mk(6, "false_split") for _ in range(4)]
    instances += [mk(3, "false_split") for _ in range(40)]

    tautology = lambda i: i.run_len == 6  # noqa: E731
    result = y.evaluate({"len==6": tautology}, instances)
    R.check("言い換え判定/run_len==6候補は誤り8件のまま(不合格)",
            result["len==6"]["errors"], 8)
    R.check_true("言い換え判定/誤り0件ではないので不合格と判定できる",
                 result["len==6"]["errors"] != 0)


def main() -> int:
    check_y2()
    check_y4()
    check_y3_ordinal()
    check_evaluate_not_degenerate()
    check_tautology_rejected()

    print()
    if R.failures:
        print(f"NG: {len(R.failures)}件の不一致")
        for f in R.failures:
            print(f"  - {f}")
        return 1
    print("OK: 全項目一致(Y2/Y3/Y4陽性対照、評価器再確認、言い換え判定)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
