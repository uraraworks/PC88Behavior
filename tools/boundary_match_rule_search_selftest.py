#!/usr/bin/env python3
"""m7dk: `tools/boundary_match_rule_search.py`の陽性対照・故障注入。

m7djで事前登録した5候補(X1〜X5)それぞれについて、既知の生成規則を仕込んだ
合成ログを1本ずつ作り、対応する候補が誤り0件で検出できること、対象でない
軸の候補は誤り0件にならないことを確認する。X2(起動バルク相対位置)だけは
構造上SEND runがバルク区間の内側に位置し得ない(挿入した瞬間にbulk run自体が
分断される)ため、`phase_of`/`bulk_clock_range`をユニットレベルで直接検算する。

さらに、評価関数`evaluate()`自体が「常に誤り0件」を返す壊れ方をしていないかを、
既知に誤りが生じるはずの入力で確認する(コーディネータ指摘の重点項目)。
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import analyze_boot_exchange as boot  # noqa: E402
import analyze_run_cutter_attribution as attrib  # noqa: E402
import boundary_match_rule_search as search  # noqa: E402
from analyze_run_cutter_attribution_selftest import (  # noqa: E402
    Row, write_iolog, write_empty_intlog,
)
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_sub_proto as sub_proto  # noqa: E402


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


def emit_run(rows: list[Row], clock: int, pc_pattern: tuple[str, ...],
              violation: str | None) -> int:
    """1本のSEND runを合成する。戻り値は更新後clock。
    violation: None(正常) / "ff"(継続位置へ本物の0Fを追加、境界は保つ) /
               "split"(run途中へ無関係I/Oを挿入し、現cutだけを分割する偽物)。
    """
    def emit(kind: str, port: str, value: str, pc: str) -> None:
        nonlocal clock
        rows.append(Row(clock, "main", kind, port, value, pc))
        clock += 10

    emit("OUT", "00FF", "0F", "3700")
    for i, pc in enumerate(pc_pattern):
        if i == 1 and violation == "ff":
            emit("OUT", "00FF", "0F", "3700")
        if i == 1 and violation == "split":
            emit("IN", "00E4", "00", "3900")
        emit("OUT", "00FD", "--", pc)
    emit("IN", "00FC", "--", "3880")
    return clock


def load_instances(rows: list[Row], condition: str) -> list[search.Instance]:
    tmp_dir = Path(tempfile.mkdtemp())
    iolog = tmp_dir / "iolog.txt"
    intlog = tmp_dir / "intlog.txt"
    write_iolog(iolog, rows)
    write_empty_intlog(intlog)
    parsed, _ = m2s.parse_iolog(iolog)
    interrupts = sub_proto.parse_intlog(intlog)
    return search.build_instances(parsed, interrupts, condition)


def summarize(instances: list[search.Instance]) -> tuple[int, int]:
    pos = sum(1 for i in instances if i.label)
    neg = sum(1 for i in instances if not i.label)
    return pos, neg


# --- X1: gap_prev閾値 -------------------------------------------------------

def check_x1() -> None:
    # 注意: "split"で作るfalse_split例外は、現cutが割ったsub-runの直前が
    # 「自分自身の分割元(sibling)」になるため、事前にどれだけ大きく
    # clockを空けてもgap_prevは常にイベント間隔程度の小さい値になる
    # (この事実自体が構造的な発見であり、m7dkノートに残す)。そのため
    # X1(gap閾値)の陰性側には、境界を壊さず"interrupt_boundary"で
    # label Falseを作る(割り込みだけを注入し、gap_prevは正しく制御できる)。
    rows: list[Row] = []
    clock = 10
    clock = emit_run(rows, clock, ("37F4", "3811"), None)  # 前置filler(gap定義用)
    # 短い間隔 + 本物の違反(境界は保つ) -> label True
    for _ in range(3):
        clock = emit_run(rows, clock, ("37F4", "37F4", "37F4"), "ff")
    # 長い間隔 + 割り込みで例外化(境界は保つ) -> label False
    neg_starts: list[int] = []
    for _ in range(3):
        clock += 2000
        neg_starts.append(clock)
        clock = emit_run(rows, clock, ("37F4", "37F4", "37F4"), "ff")

    tmp_dir = Path(tempfile.mkdtemp())
    iolog = tmp_dir / "iolog.txt"
    intlog = tmp_dir / "intlog.txt"
    write_iolog(iolog, rows)
    lines = ["# 規則生成した合成割り込みログ(公式データ不使用)"]
    for seq, start in enumerate(neg_starts, 1):
        lines.append(f"{seq} {start + 15} 0 main 1 0 1000 2000")
    intlog.write_text("\n".join(lines) + "\n", encoding="utf-8")
    parsed, _ = m2s.parse_iolog(iolog)
    interrupts = sub_proto.parse_intlog(intlog)
    instances = search.build_instances(parsed, interrupts, "SYN_X1")

    pos, neg = summarize(instances)
    R.check("X1陽性対照/真陽性件数(本物の違反・短間隔)", pos, 3)
    R.check("X1陽性対照/真陰性件数(割り込みで例外化・長間隔)", neg, 3)

    cand = search.build_candidates(instances)
    result = search.evaluate({"X1_gap<=50": cand["X1_gap<=50"]}, instances)
    R.check("X1陽性対照/対象軸の誤り件数", result["X1_gap<=50"]["errors"], 0)

    other = search.evaluate({"X2_normal": cand["X2_normal"]}, instances)
    R.check_true("X1陰性対照/対象でない軸(X2_normal)は誤り0件にならない",
                 other["X2_normal"]["errors"] > 0)


# --- X3: 条件名 --------------------------------------------------------------

def check_x3() -> None:
    rows_pos: list[Row] = []
    clock = 10
    for _ in range(3):
        clock = emit_run(rows_pos, clock, ("37F4", "3811", "37F4"), "ff")
    rows_neg: list[Row] = []
    clock = 10
    for _ in range(3):
        clock = emit_run(rows_neg, clock, ("37F4", "3811", "3811"), "split")

    instances = (load_instances(rows_pos, "SYN_POS")
                 + load_instances(rows_neg, "SYN_NEG"))
    pos, neg = summarize(instances)
    R.check("X3陽性対照/真陽性件数", pos, 3)
    R.check("X3陽性対照/真陰性件数", neg, 3)

    pred_pos = lambda i: i.condition == "SYN_POS"  # noqa: E731
    result = search.evaluate({"X3_cond=SYN_POS": pred_pos}, instances)
    R.check("X3陽性対照/対象軸の誤り件数", result["X3_cond=SYN_POS"]["errors"], 0)

    pred_len = lambda i: i.run_len >= 100  # noqa: E731 (どのinstanceにも該当しない軸)
    other = search.evaluate({"X5_len>=100": pred_len}, instances)
    R.check_true("X3陰性対照/対象でない軸(X5_len>=100)は誤り0件にならない",
                 other["X5_len>=100"]["errors"] > 0)


# --- X4: pc列パターン --------------------------------------------------------

def check_x4() -> None:
    rows: list[Row] = []
    clock = 10
    for _ in range(3):
        clock = emit_run(rows, clock, ("37F4", "3811"), "ff")
    for _ in range(3):
        clock = emit_run(rows, clock, ("3811", "3811"), "split")

    instances = load_instances(rows, "SYN_X4")
    pos, neg = summarize(instances)
    R.check("X4陽性対照/真陽性件数", pos, 3)
    R.check("X4陽性対照/真陰性件数", neg, 3)

    cand = search.build_candidates(instances)
    key = "X4_pc=('37F4', '3811')"
    R.check_true("X4陽性対照/候補が生成されている", key in cand)
    result = search.evaluate({key: cand[key]}, instances)
    R.check("X4陽性対照/対象軸の誤り件数", result[key]["errors"], 0)

    other = search.evaluate({"X2_normal": cand["X2_normal"]}, instances)
    R.check_true("X4陰性対照/対象でない軸(X2_normal)は誤り0件にならない",
                 other["X2_normal"]["errors"] > 0)


# --- X5: run長 ---------------------------------------------------------------

def check_x5() -> None:
    rows: list[Row] = []
    clock = 10
    for _ in range(3):
        clock = emit_run(rows, clock, ("37F4", "37F4", "37F4", "3811"), "ff")
    for _ in range(3):
        clock = emit_run(rows, clock, ("37F4", "37F4"), "split")

    instances = load_instances(rows, "SYN_X5")
    pos, neg = summarize(instances)
    R.check("X5陽性対照/真陽性件数", pos, 3)
    R.check("X5陽性対照/真陰性件数", neg, 3)

    cand = search.build_candidates(instances)
    result = search.evaluate({"X5_len=4": cand["X5_len=4"]}, instances)
    R.check("X5陽性対照/対象軸の誤り件数", result["X5_len=4"]["errors"], 0)

    other = search.evaluate({"X2_normal": cand["X2_normal"]}, instances)
    R.check_true("X5陰性対照/対象でない軸(X2_normal)は誤り0件にならない",
                 other["X2_normal"]["errors"] > 0)


# --- X2: フェーズ(ユニットレベル) --------------------------------------------
#
# 実run単位の陽性対照が構造的に作れない理由(m7dkノート参照): SEND runの
# `OUT $FD`はclassify_transactions()の対象なので、bulk RECV区間の内側へ
# 挿入した瞬間にbulk runそのものを分断してしまい、「bulk区間の内側にある
# SEND run」を作ることが原理的にできない。そのためphase_of/bulk_clock_range
# 自体をユニットレベルで直接検算する。

def check_x2_unit() -> None:
    Ev = attrib.Ev

    def bulk_ev(clock: int, kind: str = "IN") -> object:
        return Ev(clock, clock, 0, "main", "IN", "00FC", None, "C269")

    # bulk run: clock 100..(100+1099*10) の1100件連続
    bulk_events = [bulk_ev(100 + i * 10) for i in range(1100)]
    runs = boot.group_runs(bulk_events)
    boot_runs, bulk_run = boot.split_boot_and_bulk(runs)
    R.check_true("X2ユニット/bulk runを検出した", bulk_run is not None)
    lo, hi = bulk_run.lo, bulk_run.hi

    R.check("X2ユニット/範囲内clockはboot_bulk", search.phase_of((lo + hi) // 2, (lo, hi)),
            "boot_bulk")
    R.check("X2ユニット/下端clockはboot_bulk(inclusive)", search.phase_of(lo, (lo, hi)),
            "boot_bulk")
    R.check("X2ユニット/上端clockはboot_bulk(inclusive)", search.phase_of(hi, (lo, hi)),
            "boot_bulk")
    R.check("X2ユニット/範囲外(直前)はnormal", search.phase_of(lo - 1, (lo, hi)), "normal")
    R.check("X2ユニット/範囲外(直後)はnormal", search.phase_of(hi + 1, (lo, hi)), "normal")
    R.check("X2ユニット/bulk無しは常にnormal", search.phase_of(999999, None), "normal")

    # 構造的制約の確認: SEND run(OUT $FD, pc in SEND_PCS)をbulk区間の
    # 内側へ挿入すると、bulk run自体が2分割されて閾値未満になり、
    # split_boot_and_bulkが検出できなくなることを確認する
    # (=「bulk内側のSEND run」を作れないという主張の裏付け)。
    mixed = (bulk_ev(100 + i * 10) for i in range(550))
    mixed = list(mixed)
    mixed.append(Ev(6000, 6000, 0, "main", "OUT", "00FD", None, "37F4"))
    mixed += [bulk_ev(6100 + i * 10) for i in range(550)]
    runs2 = boot.group_runs(mixed)
    _boot_runs2, bulk_run2 = boot.split_boot_and_bulk(runs2)
    R.check_true(
        "X2ユニット/SEND runを挟むとbulk runが閾値未満に分断される(構造的制約の再現)",
        bulk_run2 is None,
    )


# --- 評価関数自体の故障注入(コーディネータ指摘の重点項目) ------------------

def check_evaluate_not_degenerate() -> None:
    """evaluate()が常に誤り0件を返す壊れ方をしていないことを、既知に
    誤りが生じるはずの入力で確認する。"""
    Instance = search.Instance
    # label True 2件、label False 2件を手作りする(category経由でlabelが
    # 決まるので、boundary_match/other を直接指定する)。
    mk = lambda cat: Instance(  # noqa: E731
        indicator="0f", condition="X", run_len=1, position=0,
        pc_pattern=("37F4",), gap_prev=None, phase="normal", category=cat,
    )
    instances = [mk("boundary_match"), mk("boundary_match"),
                 mk("false_split"), mk("interrupt_boundary")]

    always_true = lambda i: True  # noqa: E731
    always_false = lambda i: False  # noqa: E731

    result = search.evaluate({"always_true": always_true, "always_false": always_false},
                              instances)
    # always_true: 全件Trueと予測 -> label False の2件がFP -> errors=2
    R.check("故障注入/常時Trueは誤り2件を正しく報告する(0固定ではない)",
            result["always_true"]["errors"], 2)
    # always_false: 全件Falseと予測 -> label True の2件がFN -> errors=2
    R.check("故障注入/常時Falseは誤り2件を正しく報告する(0固定ではない)",
            result["always_false"]["errors"], 2)

    def evaluate_broken_alwayszero(candidates, instances):
        """わざと壊した評価器: 何を渡しても誤り0件を返す。この壊れ方を
        自分たちのテストが検出できることを示すための陰性対照。"""
        return {name: {"fp": 0, "fn": 0, "tp": 0, "tn": 0, "errors": 0}
                for name in candidates}

    broken = evaluate_broken_alwayszero(
        {"always_true": always_true, "always_false": always_false}, instances)
    # 壊れた評価器は両方とも誤り0件を返す -> 正しい evaluate() の結果と
    # 食い違うことを確認する(=このテストスイートが「常に誤り0件を返す
    # 壊れ方」を見分けられることの確認)。
    mismatch = any(
        broken[name]["errors"] != result[name]["errors"]
        for name in ("always_true", "always_false")
    )
    R.check_true(
        "故障注入/常時誤り0固定の壊れた評価器は、正しい評価器と結果が食い違う"
        "(=このテストで検出できる)",
        mismatch,
    )


# --- 論点0: 集合の同定ロジック自体の健全性 -----------------------------------

def check_run_identity_logic() -> None:
    """run_identity_for_boundary_matchが、意図どおり `0F`側と偶奇側それぞれ
    独立にboundary_matchのrunだけを拾うことを、既知構成の合成ログで確認する。
    """
    rows: list[Row] = []
    clock = 10
    # run A: 0F側だけ本物の違反(継続位置)。偶奇は正しい(len=3、期待pc一致)。
    clock = emit_run(rows, clock, ("37F4", "37F4", "37F4"), "ff")
    # run B: 偶奇側だけ本物の違反(len=2なのに期待"3811"でなく"37F4"のまま)。
    clock = emit_run(rows, clock, ("37F4", "37F4"), None)
    # run C: 両方とも境界だけ壊れた偽物(false_split想定、どちらの集合にも
    # 入らないはず)。
    clock = emit_run(rows, clock, ("37F4", "37F4", "37F4"), "split")

    tmp_dir = Path(tempfile.mkdtemp())
    iolog = tmp_dir / "iolog.txt"
    intlog = tmp_dir / "intlog.txt"
    write_iolog(iolog, rows)
    write_empty_intlog(intlog)
    parsed, _ = m2s.parse_iolog(iolog)
    interrupts = sub_proto.parse_intlog(intlog)
    ff_runs, parity_runs = search.run_identity_for_boundary_match(parsed, interrupts)

    R.check("論点0ロジック/0F側boundary_match run数", len(ff_runs), 1)
    R.check("論点0ロジック/偶奇側boundary_match run数", len(parity_runs), 1)
    R.check_true("論点0ロジック/0F側と偶奇側は別run(重ならない、この構成では)",
                 ff_runs.isdisjoint(parity_runs))


def main() -> int:
    check_x1()
    check_x3()
    check_x4()
    check_x5()
    check_x2_unit()
    check_evaluate_not_degenerate()
    check_run_identity_logic()

    print()
    if R.failures:
        print(f"NG: {len(R.failures)}件の不一致")
        for f in R.failures:
            print(f"  - {f}")
        return 1
    print("OK: 全項目一致(X1/X3/X4/X5陽性対照、X2ユニット検算、評価器の故障注入、論点0ロジック)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
