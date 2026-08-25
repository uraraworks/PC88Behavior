#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO" <<'PY'
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

repo = Path(sys.argv[1])


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


subrom = load("early_response_subrom", repo / "src/l3_service/make_subrom.py")
search = load("early_response_search", repo / "tools/search_error_response_candidate.py")


def assembled(length=None):
    a = subrom.build_subrom(early_response_after=length)
    a.resolve()
    return a


def check_candidate(a, length):
    table = a.labels["_window_run_lengths"]
    if a.code[table + 2] != length:
        raise ValueError("0x02長さ表が指定値でない")
    start = a.labels["_recv_dispatch_window_done"]
    marker = a.labels["EARLY_RESPONSE_INTERVENTION_REACHED"]
    pattern = bytes((0xCD, marker & 0xFF, marker >> 8, 0xC3))
    pos = bytes(a.code).find(pattern, start, start + 96)
    if pos < 0:
        raise ValueError("実行到達マーカーのCALLが無い")
    target = a.code[pos + 4] | a.code[pos + 5] << 8
    if target != a.labels["_exchange3_normal_response"]:
        raise ValueError("既存1バイト応答入口を再利用していない")
    if a.code[a.labels["EARLY_RESPONSE_INTERVENTION_REACHED"]] != 0xC9:
        raise ValueError("実行到達マーカーがRETでない")


default = assembled()
for length in (3, 5, 6, 12):
    check_candidate(assembled(length), length)
print("OK: 3/5/6/12の可変長表と0x02限定・既存1バイト応答経路を確認")

default_rom, default_used = subrom.build()
candidate_rom, candidate_used = subrom.build(early_response_after=5)
if (default_used, candidate_used) != (2042, 2044):
    raise SystemExit(f"NG: code size is not 2042/2044: {default_used}/{candidate_used}")
search.validate_rom_intervention_bytes(
    bytes(default_rom), bytes(candidate_rom), name="early_response_after_5")
marker = assembled(5).labels["EARLY_RESPONSE_INTERVENTION_REACHED"]
if marker >= subrom.SUB_ROM_FETCH_WINDOW:
    raise SystemExit(f"NG: 到達マーカーがフェッチ窓外: 0x{marker:04X}")
print(f"OK: 既定/介入ROMは2042/2044 bytes、到達マーカー0x{marker:04X}は窓内")

# 故障注入1: 0x02長さ表を別値へ壊す。
fault_table = assembled(5)
fault_table.code[fault_table.labels["_window_run_lengths"] + 2] = 6
try:
    check_candidate(fault_table, 5)
except ValueError:
    pass
else:
    raise SystemExit("NG: 長さ表故障を検出できない")

# 故障注入2: 応答先を従来のREAD DATA経路へ戻す。
fault_target = assembled(5)
marker = fault_target.labels["EARLY_RESPONSE_INTERVENTION_REACHED"]
pattern = bytes((0xCD, marker & 0xFF, marker >> 8, 0xC3))
start = fault_target.labels["_recv_dispatch_window_done"]
pos = bytes(fault_target.code).find(pattern, start, start + 96)
target = fault_target.labels["_general_read_request"]
fault_target.code[pos + 4:pos + 6] = bytes((target & 0xFF, target >> 8))
try:
    check_candidate(fault_target, 5)
except ValueError:
    pass
else:
    raise SystemExit("NG: 応答先故障を検出できない")
print("OK: 長さ表故障と応答先READ DATA戻しを検出")


def trap_report(address, count):
    return ("[トラップ サブCPU] 要求された入口（実行）\n"
            f"  {address:04X}  回数={count}  caller=0000 prev_fetch=0000 "
            "AF=0000 BC=0000 DE=0000 HL=0000\n"
            "[トラップ サブCPU] 要求された番地（データ）\n")


with tempfile.TemporaryDirectory() as reach_text:
    reach = Path(reach_text)
    address = assembled(3).labels["EARLY_RESPONSE_INTERVENTION_REACHED"]
    trap_map = reach / "trap.map"
    report = reach / "report.txt"
    trap_map.write_text(f"sub {address:04X}-{address:04X}\n", encoding="utf-8")
    report.write_text(trap_report(address, 1), encoding="utf-8")
    if search.validate_early_response_execution(report, trap_map) != 1:
        raise SystemExit("NG: 実行1回を受理できない")

    # 故障注入: mapを到達したマーカーの隣（未到達）へずらす。
    unreachable = address - 1
    trap_map.write_text(f"sub {unreachable:04X}-{unreachable:04X}\n",
                        encoding="utf-8")
    try:
        search.validate_early_response_execution(report, trap_map)
    except search.SearchError as exc:
        if "actual=0" not in str(exc):
            raise
    else:
        raise SystemExit("NG: 未到達番地故障を検出できない")

    trap_map.write_text(f"sub {address:04X}-{address:04X}\n", encoding="utf-8")
    report.write_text(trap_report(address, 50000), encoding="utf-8")
    try:
        search.validate_early_response_execution(report, trap_map)
    except search.SearchError as exc:
        if "actual=50000" not in str(exc):
            raise
    else:
        raise SystemExit("NG: 過剰実行回数故障を検出できない")
print("OK: 実行1回を受理し、未到達番地と0/50000回故障を検出")

with tempfile.TemporaryDirectory() as work_text:
    work = Path(work_text)
    head_script = work / "head.py"
    head_script.write_bytes(subprocess.run(
        ["git", "show", "HEAD:src/l3_service/make_subrom.py"], cwd=repo,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout)
    subprocess.run([sys.executable, str(head_script), str(work / "head")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    subprocess.run([sys.executable, str(repo / "src/l3_service/make_subrom.py"),
                    str(work / "default")], stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE, check=True)
    baseline = (work / "head" / "DISK.ROM").read_bytes()
    current = (work / "default" / "DISK.ROM").read_bytes()
    search.validate_default_rom_bytes(baseline, current)

    for invalid in (2, 13):
        completed = subprocess.run([
            sys.executable, str(repo / "src/l3_service/make_subrom.py"),
            str(work / f"invalid-{invalid}"), "--early-response-after", str(invalid),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if completed.returncode == 0:
            raise SystemExit(f"NG: 範囲外長{invalid}を受理した")
print("OK: 既定ROMはHEAD一致、範囲外2/13を拒否")
PY

echo "early_response_rom_selftest: OK"
