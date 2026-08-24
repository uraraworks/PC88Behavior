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
if default_used == candidate_used0 == candidate_used1 == 2042 \
        and candidate_used0 <= subrom.SUB_ROM_FETCH_WINDOW:
    ok("既定版・候補版とも2042バイトでフェッチ窓内")
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

raise SystemExit(1 if fail else 0)
PY
