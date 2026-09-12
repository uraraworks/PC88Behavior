#!/usr/bin/env bash
# 合成抽象列だけで候補指標・定数化故障・該当なし判定を検証する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO" <<'PY'
import importlib.util
import sys
from pathlib import Path

repo = Path(sys.argv[1])

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

search = load("search_error_response_candidate",
              repo / "tools/search_error_response_candidate.py")
subrom = load("make_subrom_candidate_selftest",
              repo / "src/l3_service/make_subrom.py")

fail = False
def ok(message):
    print(f"OK: {message}")
def ng(message):
    global fail
    fail = True
    print(f"NG: {message}")

reference = search.AbstractResult(
    exchange=(("main→sub", 6), ("sub→main", 1), ("main→sub", 6)),
    fdc=("SEEK", "READ DATA", "READ DATA"),
    screen_line_count=3, screen_char_count=12, screen_sha256="a" * 64)
candidate0 = search.AbstractResult(
    exchange=(("main→sub", 6), ("sub→main", 1), ("main→sub", 2)),
    fdc=("SEEK", "READ DATA", "SEEK"),
    screen_line_count=2, screen_char_count=9, screen_sha256="b" * 64)
candidate1 = search.AbstractResult(
    exchange=reference.exchange, fdc=reference.fdc,
    screen_line_count=reference.screen_line_count,
    screen_char_count=reference.screen_char_count,
    screen_sha256=reference.screen_sha256)

m0 = search.compare_result(reference, candidate0, 0)
m1 = search.compare_result(reference, candidate1, 1)
if (m0.exchange_prefix, m0.fdc_prefix) == (2, 2) and search.exact_match(m1) \
        and search.metric_vector(m0) != search.metric_vector(m1):
    ok("候補差が交換prefix・FDC prefix・画面3指標へ反映される")
else:
    ng("候補差が指標へ反映されない")

status, selected = search.classify_results([m0, m1])
if status == "found" and selected == [1]:
    ok("完全一致候補だけを発見として報告する")
else:
    ng("完全一致候補の発見判定が不正")

# 故障注入: 候補1の入力にも候補0の固定結果を返す計算器を模す。
constant0 = search.compare_result(reference, candidate0, 0)
constant1 = search.compare_result(reference, candidate0, 1)
status, selected = search.classify_results([constant0, constant1])
if status == "insensitive" and not selected:
    ok("常に同じ値を返す指標計算故障を検査不能として検出")
else:
    ng("定数化した指標計算故障を検出できない")

# 完全一致は無いが指標は異なる入力。insensitiveやfoundにしてはいけない。
candidate2 = search.AbstractResult(
    exchange=(("main→sub", 6),), fdc=("SEEK",),
    screen_line_count=1, screen_char_count=1, screen_sha256="c" * 64)
m2 = search.compare_result(reference, candidate2, 2)
status, selected = search.classify_results([m0, m2])
if status == "not_found" and selected:
    ok("完全一致0件を『見つからなかった』と判定し、最良候補は別表示する")
else:
    ng("完全一致0件を正しくnot_foundにできない")

default_rom, default_used = subrom.build()
candidate_rom0, candidate_used0 = subrom.build(error_response_candidate=0)
candidate_rom1, candidate_used1 = subrom.build(error_response_candidate=1)
diffs = [pos for pos, (left, right) in enumerate(zip(candidate_rom0, candidate_rom1))
         if left != right]
# 2026-09-10: 絶対値2042の直書きをやめた。見たいのは「既定版と候補版が
# 同サイズ」＝候補の切り替えが即値1セルしか動かさないことと、窓内であること。
if default_used == candidate_used0 == candidate_used1 \
        and candidate_used0 <= subrom.SUB_ROM_FETCH_WINDOW:
    ok(f"既定版・候補版とも同サイズ（{default_used}バイト）でフェッチ窓内")
else:
    ng("生成コードサイズまたはフェッチ窓制約が不正")
if default_rom == candidate_rom0:
    ok("既定値0x00は候補0で再現できる")
else:
    ng("既定値を候補0で再現できない")
if len(diffs) == 1 and candidate_rom0[diffs[0]] == 0 \
        and candidate_rom1[diffs[0]] == 1:
    ok("候補0/1の生成ROM差分は候補即値セル1バイトだけ")
else:
    ng("候補差が即値セル1バイト以外へ波及した")

# m7ls: 打鍵フレームを引数化しても、既定値700のargvは変更前と完全一致する。
OLD_FIXED_SUFFIX = ["--type-at", "300", "--type", r"\n",
                    "--type-at", "700", "--type", r"FILES 2\n"]
if search.keystroke_command_suffix() == OLD_FIXED_SUFFIX:
    ok("keystroke_command_suffixの既定値argvは変更前の固定argvと完全一致")
else:
    ng("keystroke_command_suffixの既定値argvが変更前と食い違う")
if search.keystroke_command_suffix(780) == \
        ["--type-at", "300", "--type", r"\n",
         "--type-at", "780", "--type", r"FILES 2\n"]:
    ok("keystroke_command_suffixは打鍵フレームを差し替えられる")
else:
    ng("keystroke_command_suffixが打鍵フレームを反映しない")

# m7ls: classify_keystroke_shiftの4判定。
def shift_arm(valid, request_length):
    return {"valid": valid, "request_length": request_length}

nondet_sides = {
    "official": {"deterministic": False, "expected_control": 5,
                "shift_arms": [shift_arm(True, 5)] * 3},
    "mixed": {"deterministic": True, "expected_control": 6,
             "shift_arms": [shift_arm(True, 6)] * 3},
}
if search.classify_keystroke_shift(nondet_sides) == "nondeterministic":
    ok("対照の繰り返し不一致をnondeterministicと判定")
else:
    ng("対照の繰り返し不一致をnondeterministicと判定できない")

flipped_sides = {
    "official": {"deterministic": True, "expected_control": 5,
                "shift_arms": [shift_arm(True, 5), shift_arm(True, 6), shift_arm(True, 5)]},
    "mixed": {"deterministic": True, "expected_control": 6,
             "shift_arms": [shift_arm(True, 6)] * 3},
}
if search.classify_keystroke_shift(flipped_sides) == "keystroke_timing_affects_branch":
    ok("有効な腕で要求長が動くとkeystroke_timing_affects_branchと判定")
else:
    ng("要求長が動いたのにkeystroke_timing_affects_branchにならない")

excluded_sides = {
    "official": {"deterministic": True, "expected_control": 5,
                "shift_arms": [shift_arm(True, 5)] * 3},
    "mixed": {"deterministic": True, "expected_control": 6,
             "shift_arms": [shift_arm(True, 6)] * 3},
}
if search.classify_keystroke_shift(excluded_sides) == "wait_length_excluded":
    ok("6腕すべて有効で要求長不変ならwait_length_excludedと判定")
else:
    ng("6腕すべて有効・不変なのにwait_length_excludedにならない")

unreached_sides = {
    "official": {"deterministic": True, "expected_control": 5,
                "shift_arms": [shift_arm(False, None), shift_arm(True, 5), shift_arm(True, 5)]},
    "mixed": {"deterministic": True, "expected_control": 6,
             "shift_arms": [shift_arm(True, 6)] * 3},
}
if search.classify_keystroke_shift(unreached_sides) == "inconclusive_ineffective_arms":
    ok("unreachedな腕が1つでもあるとwait_length_excludedにならない")
else:
    ng("unreachedな腕があるのにwait_length_excludedへ落ちる、または誤判定")

# m7ls 陽性対照①: 打鍵フレームをargvへ渡し忘れる故障（腕が常に700で走る）を、
# 有効性条件(c)（+0開始フレームのずれが打鍵フレーム移動量と対応するか）が
# 捕まえることを確かめる。files_at=780（期待ずれ+80）なのに実際のずれが
# 0（=700のまま走った）合成データを与える。
forgot_shift = search.keystroke_shift_arm_valid(
    reached=True, exchange_prefix_matches_control=True,
    start_frame_delta=0, expected_delta=780 - 700,
    window_count_differs_from_control=True)
if forgot_shift is False:
    ok("陽性対照1: 打鍵フレーム渡し忘れ（ずれ0）を条件(c)が無効と判定")
else:
    ng("陽性対照1: 打鍵フレーム渡し忘れが無効と判定されない（直す前に赤くならない）")

# m7ls 陽性対照②: 条件(c)の許容幅を無限にする故障で、陽性対照①のケースが
# 検出されなくなる（=有効と誤判定される）ことを確認し、(c)が検出を担って
# いることを裏付ける。
forgot_shift_unbounded_tolerance = search.keystroke_shift_arm_valid(
    reached=True, exchange_prefix_matches_control=True,
    start_frame_delta=0, expected_delta=780 - 700,
    window_count_differs_from_control=True,
    tolerance=10 ** 9)
if forgot_shift_unbounded_tolerance is True:
    ok("陽性対照2: 許容幅を無限にすると陽性対照1の故障が検出されなくなる"
       "（条件(c)が検出を担っている確認）")
else:
    ng("陽性対照2: 許容幅を無限にしても検出されてしまい、(c)の寄与を確認できない")

raise SystemExit(1 if fail else 0)
PY
