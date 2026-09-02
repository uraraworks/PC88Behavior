#!/usr/bin/env bash
# 公開FDC段・$FB run・run内位置の追加集計を、合成fixtureと故障注入で検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 - "$REPO" "$TMP" <<'PY'
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

repo, tmp = Path(sys.argv[1]), Path(sys.argv[2])
analyzer_path = repo / "tools/analyze_sub_interrupt_shape.py"
spec = importlib.util.spec_from_file_location("interrupt_shape", analyzer_path)
assert spec is not None and spec.loader is not None
analyzer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = analyzer
spec.loader.exec_module(analyzer)


def write_io(path: Path, events: list[tuple[int, str, str, int]],
             main_fault: bool = False) -> None:
    """公開μPD765形式だけから合成したI/O fixtureを書く。"""
    rows: list[tuple[int, str, str, int, str]] = [
        (clock, kind, port, value, "sub")
        for clock, kind, port, value in events
    ]
    if main_fault:
        # clock 12のsub $FBより後に同clockのmainイベントを置き、受理直前を壊す。
        rows.append((12, "OUT", "0040", 0, "main"))
    rows.sort(key=lambda row: (row[0], row[4] == "main"))
    with path.open("w", encoding="utf-8") as fp:
        fp.write("# 公開仕様だけから作った合成FDCログ（公式データ不使用）\n")
        fp.write("# seq clock frame cpu kind port value pc\n")
        for seq, (clock, kind, port, value, cpu) in enumerate(rows, 1):
            fp.write(
                f"{seq} {clock} 1 {cpu} {kind} {port} {value:02X} 0100\n"
            )


def write_int(path: Path, clocks: list[int]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        fp.write("# seq clock frame cpu im level ret_pc handler_pc\n")
        for seq, clock in enumerate(clocks, 1):
            fp.write(f"{seq} {clock} 1 sub 0 0 0101 0101\n")
        fp.write(f"# 取りこぼし: 0件 / 総イベント数: {len(clocks)}件\n")


# SPECIFY、SENSE DRIVE STATUS、READ DATA。値は合成fixture内部だけで使い、
# 解析出力へは公開コマンド種別名しか出さない。
base_events = [
    (5, "IN", "00FA", 0),
    (7, "IN", "00FA", 0),
    (10, "OUT", "00FB", 0x03),
    (11, "OUT", "00FB", 0xA5),
    (12, "OUT", "00FB", 0x5A),
    (14, "IN", "00FA", 0),
    (20, "OUT", "00FB", 0x04),
    (21, "OUT", "00FB", 0),
    (23, "IN", "00FA", 0),
    (24, "IN", "00FB", 0),
    (26, "IN", "00FA", 0),
    (30, "OUT", "00FB", 0x06),
    (32, "OUT", "00FB", 0),
    (34, "OUT", "00FB", 1),
    (36, "IN", "00FA", 0),
    (38, "OUT", "00FB", 2),
    (40, "OUT", "00FB", 3),
    (42, "OUT", "00FB", 4),
    (44, "OUT", "00FB", 5),
    (46, "OUT", "00FB", 6),
    (48, "OUT", "00FB", 7),
    (60, "IN", "00FB", 0),
    (62, "IN", "00FB", 0),
    (64, "IN", "00FA", 0),
    (66, "IN", "00FB", 0),
    (68, "IN", "00FA", 0),
]
base_interrupts = [6, 13, 22, 25, 35, 63, 67]

write_io(tmp / "base.io", base_events)
write_int(tmp / "base.int", base_interrupts)
base = analyzer.analyze(tmp / "base.io", tmp / "base.int")

expected = {
    "fdc_command_kinds": [
        "SPECIFY", "SENSE DRIVE STATUS", "READ DATA",
    ],
    "fdc_command_count": 3,
    "fdc_command_kinds_sha256":
        "35975a95c515ce3d93711c2088de1eb65ffa6aabe8ae4eaf7f5d571659760cc9",
    "interrupts_by_fdc_command_index_nonzero": {-1: 1, 0: 1, 1: 2, 2: 3},
    "fb_run_count": 4,
    "fb_run_length_histogram": {1: 1, 3: 1, 5: 1, 9: 1},
    "interrupts_by_fb_run_index_nonzero": {0: 2, 1: 1, 2: 1, 3: 2},
    "fb_runs_with_interrupt": 4,
    "fb_runs_without_interrupt": 0,
    "interrupt_position_in_run_histogram_nonzero": {0: 1, 1: 1, 2: 3, 4: 1},
    "interrupts_without_fb_run_position": 1,
}
for key, wanted in expected.items():
    if base.get(key) != wanted:
        print(
            f"NG: 陽性対照の{key}が期待値と不一致: "
            f"期待={wanted!r} 実際={base.get(key)!r}"
        )
        raise SystemExit(1)
print("OK: 陽性対照で追加集計が全て期待値どおり")

# 故障1: READ DATA直後の受理1件を発行直前へずらす。
write_int(tmp / "shifted.int", [6, 13, 22, 25, 29, 63, 67])
shifted = analyzer.analyze(tmp / "base.io", tmp / "shifted.int")

# 故障2: SPECIFYと次コマンドの間へ逆方向$FBを挿入し、runを1本分割する。
split_events = [*base_events, (16, "IN", "00FB", 0)]
write_io(tmp / "split.io", split_events)
split = analyzer.analyze(tmp / "split.io", tmp / "base.int")

# 故障3: SPECIFYを1件（コマンド語と2パラメータ）抜く。
missing_command_events = [
    event for event in base_events if event[0] not in {10, 11, 12}
]
write_io(tmp / "missing-command.io", missing_command_events)
missing_command = analyzer.analyze(
    tmp / "missing-command.io", tmp / "base.int"
)

faults = {
    "受理1件ずらし": shifted,
    "run 1本分割": split,
    "FDCコマンド1件抜き": missing_command,
}
for label, result in faults.items():
    changed = [key for key in expected if result[key] != base[key]]
    if not changed:
        print(f"NG: {label}で追加集計が1項目も変化しない")
        raise SystemExit(1)
    print(f"OK: {label}を追加集計の変化で検出（{len(changed)}項目）")

# 追加した各集計が、3故障の少なくとも1つで実際に変わることを先に検査する。
undetected = [
    key for key in expected
    if all(result[key] == base[key] for result in faults.values())
]
if undetected:
    print("NG: 故障注入で変化しなかった追加集計: " + ", ".join(undetected))
    raise SystemExit(1)
print("OK: 故障注入で変化しなかった追加集計なし")

# 既存の外形検査も維持する。正常fixtureはrc=0、main直前注入はrc=1。
write_io(tmp / "main-fault.io", base_events, main_fault=True)
good = subprocess.run(
    [sys.executable, str(analyzer_path), "--iolog", str(tmp / "base.io"),
     "--intlog", str(tmp / "base.int"), "--check"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
)
bad = subprocess.run(
    [sys.executable, str(analyzer_path), "--iolog", str(tmp / "main-fault.io"),
     "--intlog", str(tmp / "base.int"), "--check"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
)
if good.returncode != 0 or bad.returncode != 1:
    print(
        "NG: 既存外形検査のrcが不一致: "
        f"正常={good.returncode} main直前注入={bad.returncode}"
    )
    raise SystemExit(1)
print("OK: 既存外形検査は正常rc=0、main直前注入rc=1")

# 未知コマンドの生値を診断へ漏らさないことも固定する。
unknown_events = [event for event in base_events if event[0] not in {10, 11, 12}]
unknown_events.append((10, "OUT", "00FB", 0x1E))
write_io(tmp / "unknown.io", unknown_events)
unknown = subprocess.run(
    [sys.executable, str(analyzer_path), "--iolog", str(tmp / "unknown.io"),
     "--intlog", str(tmp / "base.int")],
    capture_output=True, text=True, check=False,
)
if unknown.returncode != 2 or "1e" in unknown.stderr.lower() or "0x" in unknown.stderr.lower():
    print("NG: 未知コマンドを安全な固定診断rc=2で扱えない")
    raise SystemExit(1)
try:
    parsed = json.loads(subprocess.run(
        [sys.executable, str(analyzer_path), "--iolog", str(tmp / "base.io"),
         "--intlog", str(tmp / "base.int")],
        capture_output=True, text=True, check=True,
    ).stdout)
except (json.JSONDecodeError, subprocess.CalledProcessError):
    print("NG: 正常fixtureのJSON出力を読めない")
    raise SystemExit(1)
if parsed["fdc_command_kinds"] != expected["fdc_command_kinds"]:
    print("NG: JSON出力のFDC列が公開種別名だけになっていない")
    raise SystemExit(1)
print("OK: 未知コマンドの生値を出さず解析不能rc=2")
PY
