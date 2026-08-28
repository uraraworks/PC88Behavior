#!/usr/bin/env python3
"""m7dk: `boundary_match`残差(m7dh)の生成規則探索。

`docs/notes/m7dj-boundary-match-residual-rule-search-preregistration.md`で
事前登録した候補X1〜X6を、実測ログ(または合成selftestログ)へ適用する。

評価母集団は、`analyze_run_cutter_attribution.py`の現cut例外(0F側は`ff_bad`、
偶奇側は`parity_bad`)のうち、独立境界アンカーによる分類(`classify_send`)を
一度だけ行った結果である。ラベルは「その例外が`boundary_match`カテゴリか
どうか」の2値。候補規則は、境界分類そのもの(`false_split`等)を一切参照せず、
run長・位置・pc列パターン(公開済み`SEND_PCS`の並び)・共通clock間隔・
条件名・起動バルク相対位置という構造的特徴だけから予測する。

データポート($FB/$FC/$FD)の値は一切使わない。
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import analyze_boot_exchange as boot  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_run_cutter_attribution as attrib  # noqa: E402
import analyze_sub_proto as sub_proto  # noqa: E402

CONDITIONS = ["d0-boot", "d1-files", "d2-save", "d5-seqfile"]

# X1(バースト継続)のgap閾値候補。事前登録どおり有限個をあらかじめ固定する
# (実測値を見てから決めていない)。
X1_GAP_THRESHOLDS = (2, 5, 10, 20, 50)


@dataclass
class Instance:
    indicator: str  # "0f" | "parity"
    condition: str
    run_len: int
    position: int  # 0Fは違反位置のrun内index。偶奇はrun末尾index(len-1)
    pc_pattern: tuple[str, ...]
    gap_prev: int | None
    phase: str  # "boot_bulk" | "normal"
    category: str  # classify_sendの生の帰属
    label: bool = field(init=False)

    def __post_init__(self) -> None:
        self.label = self.category == "boundary_match"


def bulk_clock_range(rows: list) -> tuple[int, int] | None:
    tx = m2s.classify_transactions(rows)
    runs = boot.group_runs(tx)
    _boot_runs, bulk_run = boot.split_boot_and_bulk(runs)
    if bulk_run is None:
        return None
    return bulk_run.lo, bulk_run.hi


def phase_of(clock: int, bulk: tuple[int, int] | None) -> str:
    if bulk is not None and bulk[0] <= clock <= bulk[1]:
        return "boot_bulk"
    return "normal"


def build_instances(rows: list, interrupts: dict, condition: str) -> list[Instance]:
    current_runs, main_rows = attrib.current_send.main_send_runs(rows)
    anchors = attrib.anchor_send_runs(rows)
    _metrics, ff_bad, parity_bad = attrib.send_outcomes(current_runs, main_rows)
    all_fd = [idx for run in current_runs for idx in run]
    int_clocks = [e.clock for e in interrupts["main"]]
    bulk = bulk_clock_range(rows)

    # run identity -> 直前run(同じcurrent_runs列内の1つ前)を求めるための索引
    run_start_clock = {id(run): main_rows[run[0]].clock for run in current_runs}
    run_end_clock = {id(run): main_rows[run[-1]].clock for run in current_runs}
    ordered = sorted(current_runs, key=lambda r: run_start_clock[id(r)])
    prev_end: dict[int, int | None] = {}
    prev = None
    for run in ordered:
        prev_end[id(run)] = run_end_clock[id(prev)] if prev is not None else None
        prev = run

    def gap_prev(run: list[int]) -> int | None:
        pe = prev_end[id(run)]
        return None if pe is None else run_start_clock[id(run)] - pe

    def pc_pattern(run: list[int]) -> tuple[str, ...]:
        return tuple(main_rows[i].pc for i in run)

    instances: list[Instance] = []
    for run, idx in ff_bad:
        cat = attrib.classify_send(run, idx, anchors, main_rows, int_clocks, all_fd)
        instances.append(Instance(
            indicator="0f", condition=condition, run_len=len(run),
            position=run.index(idx), pc_pattern=pc_pattern(run),
            gap_prev=gap_prev(run), phase=phase_of(run_start_clock[id(run)], bulk),
            category=cat,
        ))
    for run in parity_bad:
        cat = attrib.classify_send(run, None, anchors, main_rows, int_clocks, all_fd)
        instances.append(Instance(
            indicator="parity", condition=condition, run_len=len(run),
            position=len(run) - 1, pc_pattern=pc_pattern(run),
            gap_prev=gap_prev(run), phase=phase_of(run_start_clock[id(run)], bulk),
            category=cat,
        ))
    return instances


def run_identity_for_boundary_match(rows: list, interrupts: dict) -> tuple[set, set]:
    """0F側・偶奇側それぞれの`boundary_match`例外が属するrunの識別集合
    (run内イベントclockのtupleをキーにする)を返す。論点0用。"""
    current_runs, main_rows = attrib.current_send.main_send_runs(rows)
    anchors = attrib.anchor_send_runs(rows)
    _metrics, ff_bad, parity_bad = attrib.send_outcomes(current_runs, main_rows)
    all_fd = [idx for run in current_runs for idx in run]
    int_clocks = [e.clock for e in interrupts["main"]]

    def key(run: list[int]) -> tuple[int, ...]:
        return tuple(main_rows[i].clock for i in run)

    ff_runs = set()
    for run, idx in ff_bad:
        cat = attrib.classify_send(run, idx, anchors, main_rows, int_clocks, all_fd)
        if cat == "boundary_match":
            ff_runs.add(key(run))
    parity_runs = set()
    for run in parity_bad:
        cat = attrib.classify_send(run, None, anchors, main_rows, int_clocks, all_fd)
        if cat == "boundary_match":
            parity_runs.add(key(run))
    return ff_runs, parity_runs


# --- 候補規則 --------------------------------------------------------------

def build_candidates(instances: list[Instance]) -> dict[str, callable]:
    cands: dict[str, callable] = {}
    for g in X1_GAP_THRESHOLDS:
        cands[f"X1_gap<={g}"] = (lambda g: (lambda i: i.gap_prev is not None and i.gap_prev <= g))(g)
    cands["X2_boot_bulk"] = lambda i: i.phase == "boot_bulk"
    cands["X2_normal"] = lambda i: i.phase == "normal"
    for c in CONDITIONS:
        cands[f"X3_cond={c}"] = (lambda c: (lambda i: i.condition == c))(c)
    cands["X3_cond!=d0-boot"] = lambda i: i.condition != "d0-boot"
    for p in sorted({i.pc_pattern for i in instances}):
        cands[f"X4_pc={p}"] = (lambda p: (lambda i: i.pc_pattern == p))(p)
    for L in sorted({i.run_len for i in instances}):
        cands[f"X5_len={L}"] = (lambda L: (lambda i: i.run_len == L))(L)
        cands[f"X5_len>={L}"] = (lambda L: (lambda i: i.run_len >= L))(L)
    return cands


def build_combo_candidates(instances: list[Instance]) -> dict[str, callable]:
    """X6: 軸3×軸8(gap×条件)、軸3×軸6(gap×pcパターン)、軸2×軸8(フェーズ×条件)
    の3通りに限定する。単一軸(X1〜X5)が全滅した場合だけ呼び出す。"""
    combos: dict[str, callable] = {}
    for g in X1_GAP_THRESHOLDS:
        for c in CONDITIONS:
            combos[f"X6_gap<={g}&cond={c}"] = (
                lambda g, c: (lambda i: i.gap_prev is not None and i.gap_prev <= g and i.condition == c)
            )(g, c)
    for g in X1_GAP_THRESHOLDS:
        for p in sorted({i.pc_pattern for i in instances}):
            combos[f"X6_gap<={g}&pc={p}"] = (
                lambda g, p: (lambda i: i.gap_prev is not None and i.gap_prev <= g and i.pc_pattern == p)
            )(g, p)
    for c in CONDITIONS:
        combos[f"X6_boot_bulk&cond={c}"] = (
            lambda c: (lambda i: i.phase == "boot_bulk" and i.condition == c)
        )(c)
    return combos


def evaluate(candidates: dict[str, callable], instances: list[Instance]) -> dict[str, dict]:
    result = {}
    for name, pred in candidates.items():
        fp = fn = tp = tn = 0
        for inst in instances:
            p = bool(pred(inst))
            if p and inst.label:
                tp += 1
            elif p and not inst.label:
                fp += 1
            elif not p and inst.label:
                fn += 1
            else:
                tn += 1
        result[name] = {"fp": fp, "fn": fn, "tp": tp, "tn": tn, "errors": fp + fn}
    return result


def observationally_equivalent(names: list[str], candidates: dict[str, callable],
                                instances: list[Instance]) -> bool:
    """誤り0件の候補群が、全instanceへの予測を完全に共有するか。"""
    if len(names) <= 1:
        return True
    rows = [tuple(bool(candidates[n](i)) for n in names) for i in instances]
    return all(len(set(row)) == 1 for row in rows)


# --- 実測ドライバ -----------------------------------------------------------

def load_condition(iolog: Path, intlog: Path, condition: str):
    rows, _ = m2s.parse_iolog(iolog)
    interrupts = sub_proto.parse_intlog(intlog)
    return rows, interrupts


def main() -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scratch-dir", required=True, type=Path,
                     help="m7dhと同じ命名(<cond>-run{1,2}.iolog.txt / .intlog.txt)が"
                          "置かれたリポジトリ外の一時ディレクトリ")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    report: dict = {"conditions": {}, "run_consistency": {}}
    all_instances: list[Instance] = []
    ff_bm_by_cond: dict[str, set] = {}
    parity_bm_by_cond: dict[str, set] = {}

    for cond in CONDITIONS:
        io1 = args.scratch_dir / f"{cond}-run1.iolog.txt"
        int1p = args.scratch_dir / f"{cond}-run1.intlog.txt"
        io2 = args.scratch_dir / f"{cond}-run2.iolog.txt"
        int2p = args.scratch_dir / f"{cond}-run2.intlog.txt"
        for p in (io1, int1p, io2, int2p):
            if not p.exists():
                print(f"SKIP: {cond} の入力が無い ({p})", file=sys.stderr)
                return 2

        rows1, interrupts1 = load_condition(io1, int1p, cond)
        rows2, interrupts2 = load_condition(io2, int2p, cond)
        v1 = attrib.validate(rows1, interrupts1)
        v2 = attrib.validate(rows2, interrupts2)
        same = v1["structure_sha256"] == v2["structure_sha256"]
        report["run_consistency"][cond] = {
            "run1_sha256_16": v1["structure_sha256"][:16],
            "run2_sha256_16": v2["structure_sha256"][:16],
            "identical": same,
        }
        if not same:
            print(f"NG: {cond} run1/run2が一致しない。単一走扱いにする。", file=sys.stderr)

        instances = build_instances(rows1, interrupts1, cond)
        all_instances.extend(instances)

        ff_runs, parity_runs = run_identity_for_boundary_match(rows1, interrupts1)
        ff_bm_by_cond[cond] = ff_runs
        parity_bm_by_cond[cond] = parity_runs

        cnt = Counter((i.indicator, i.category) for i in instances)
        report["conditions"][cond] = {
            "instances": len(instances),
            "by_indicator_category": {f"{k[0]}/{k[1]}": v for k, v in sorted(cnt.items())},
        }

    # 論点0: 0F側/偶奇側boundary_matchのrun集合の重なり
    agreement = {}
    total_ff = total_parity = total_inter = total_union = 0
    for cond in CONDITIONS:
        ff = ff_bm_by_cond[cond]
        pa = parity_bm_by_cond[cond]
        inter = ff & pa
        union = ff | pa
        agreement[cond] = {
            "0f_boundary_match_runs": len(ff),
            "parity_boundary_match_runs": len(pa),
            "intersection": len(inter),
            "union": len(union),
            "jaccard": (len(inter) / len(union)) if union else None,
        }
        total_ff += len(ff)
        total_parity += len(pa)
        total_inter += len(inter)
        total_union += len(union)
    agreement["__total__"] = {
        "0f_boundary_match_runs": total_ff,
        "parity_boundary_match_runs": total_parity,
        "intersection": total_inter,
        "union": total_union,
        "jaccard": (total_inter / total_union) if total_union else None,
    }
    report["point0_overlap"] = agreement

    # 候補評価: 0F側・偶奇側を別々に
    for indicator in ("0f", "parity"):
        subset = [i for i in all_instances if i.indicator == indicator]
        cands = build_candidates(subset)
        results = evaluate(cands, subset)
        zero_error = sorted(n for n, r in results.items() if r["errors"] == 0)
        combo_results = {}
        combo_zero = []
        if not zero_error:
            combos = build_combo_candidates(subset)
            combo_results = evaluate(combos, subset)
            combo_zero = sorted(n for n, r in combo_results.items() if r["errors"] == 0)
        equiv = observationally_equivalent(zero_error, cands, subset) if zero_error else None
        report[f"candidates_{indicator}"] = {
            "universe": len(subset),
            "positives": sum(1 for i in subset if i.label),
            "negatives": sum(1 for i in subset if not i.label),
            "results": results,
            "zero_error_candidates": zero_error,
            "observationally_equivalent": equiv,
            "combo_results": combo_results,
            "combo_zero_error_candidates": combo_zero,
        }

    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
                        encoding="utf-8")
    print(f"論点0(合算): intersection={total_inter} union={total_union} "
          f"jaccard={(total_inter/total_union) if total_union else 'NA'}")
    for indicator in ("0f", "parity"):
        c = report[f"candidates_{indicator}"]
        print(f"{indicator}: universe={c['universe']} pos={c['positives']} "
              f"neg={c['negatives']} zero_error={c['zero_error_candidates']} "
              f"combo_zero_error={c['combo_zero_error_candidates']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
