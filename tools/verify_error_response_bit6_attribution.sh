#!/usr/bin/env bash
# unreadable_diskのエラー応答bit6帰属回帰。
# 既定版は交換構造全長・画面が一致し、bit6=1故障注入版は構造prefix=38・
# 画面3指標が不一致になる、という両条件を必須にする。

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 - "$REPO" "$WORK" "${1:-900}" <<'PY'
import importlib.util
import os
import sys
from pathlib import Path

repo, state_dir, frames = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

sys.path.insert(0, str(repo / "tools"))
search = load("error_response_attribution_search",
              repo / "tools/search_error_response_candidate.py")
attribution = load("error_response_bit6_attribution",
                   repo / "tools/error_response_bit6_attribution.py")
subrom = load("error_response_attribution_subrom",
              repo / "src/l3_service/make_subrom.py")

exchange = tuple(("main→sub", 6) if pos % 2 == 0 else ("sub→main", 1)
                 for pos in range(60))
reference = search.AbstractResult(exchange, tuple("R" for _ in range(60)),
                                  *attribution.EXPECTED_SCREEN)
default = search.AbstractResult(exchange, tuple("D" for _ in range(55)),
                                *attribution.EXPECTED_SCREEN)
broken_exchange = exchange[:38] + (("main→sub", 2),)
broken = search.AbstractResult(broken_exchange, tuple("B" for _ in range(55)),
                               0, 0, "0" * 64)
synthetic_measurements = ((reference, {}), (default, {}), (broken, {}))
passed, _, _ = attribution.judge_measurements(*synthetic_measurements)
if not passed:
    print("NG: selftestの正常な合成入力を合格にできない")
    raise SystemExit(1)
print("OK: selftestは既定の全長・画面一致と故障注入のprefix 38・画面不一致を要求")

if (attribution.judge_measurements(
        (reference, {}), (broken, {}), (broken, {}))[0]
        or attribution.judge_measurements(
            (reference, {}), (default, {}), (default, {}))[0]):
    print("NG: selftestの帰属故障注入を見逃した")
    raise SystemExit(1)
print("OK: selftestは既定側破壊と故障注入側無効化をともに検出")

default_rom, default_used = subrom.build()
broken_rom, broken_used = subrom.build(break_error_response_bit6=True)
candidate0_rom, candidate0_used = subrom.build(error_response_candidate=0)
candidate64_rom, candidate64_used = subrom.build(error_response_candidate=0x40)
diffs = [pos for pos, pair in enumerate(zip(default_rom, broken_rom))
         if pair[0] != pair[1]]
if not (default_used == broken_used == candidate0_used == candidate64_used == 2042
        and default_rom == candidate0_rom and broken_rom == candidate64_rom
        and len(diffs) == 1
        and default_rom[diffs[0]] ^ broken_rom[diffs[0]] == 0x40):
    print("NG: 既定値・bit6故障注入・候補再現または生成サイズが不正")
    raise SystemExit(1)
print("OK: 既定0x00と故障注入0x40はbit6即値1セルだけが異なり、コード2042バイト")

if os.environ.get("PC88_ERROR_RESPONSE_OPT_IN") != "1":
    print("SKIP: PC88_ERROR_RESPONSE_OPT_IN未設定（本体未実行、selftestのみrc=0）")
    raise SystemExit(0)

rom_env, disk_env = os.environ.get("PC88_REF_ROM_DIR"), os.environ.get("PC88_REF_DISK_DIR")
if not rom_env or not disk_env:
    print("エラー: PC88_REF_ROM_DIR / PC88_REF_DISK_DIRが未設定", file=sys.stderr)
    raise SystemExit(2)
disk_source = Path(disk_env) / "N88_FE.D88"
frontend = repo / "tools/harness/frontend/q88measure"
if not disk_source.is_file() or not frontend.is_file():
    print("エラー: 参照媒体またはq88measureが無い", file=sys.stderr)
    raise SystemExit(2)
core = search.discover_core()
common = dict(frames=frames, timeout=120, state_dir=state_dir,
              rom_source=Path(rom_env), disk_source=disk_source,
              core=core, frontend=frontend, candidate=None)
official = search.measure_once(official=True, tag="official", **common)
actual_default = search.measure_once(official=False, tag="default", **common)
actual_broken = search.measure_once(official=False, tag="broken",
                                    break_error_response_bit6=True, **common)
passed, default_metric, broken_metric = attribution.judge_measurements(
    official, actual_default, actual_broken)
print(f"既定: exchange_prefix={default_metric.exchange_prefix} "
      f"exchange_exact={int(default_metric.exchange_exact)} "
      f"screen={int(default_metric.screen_lines_match)}/"
      f"{int(default_metric.screen_chars_match)}/"
      f"{int(default_metric.screen_sha256_match)} "
      f"fdc_prefix={default_metric.fdc_prefix} fdc_exact={int(default_metric.fdc_exact)}")
print(f"故障注入: exchange_prefix={broken_metric.exchange_prefix} "
      f"exchange_exact={int(broken_metric.exchange_exact)} "
      f"screen={int(broken_metric.screen_lines_match)}/"
      f"{int(broken_metric.screen_chars_match)}/"
      f"{int(broken_metric.screen_sha256_match)}")
if not passed:
    print("NG: 既定一致・bit6=1陰性対照の両条件を満たさない")
    raise SystemExit(1)
print("OK: 既定の交換構造全長・画面一致とbit6=1版のprefix 38・画面不一致を確認")
PY
