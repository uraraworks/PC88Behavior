#!/usr/bin/env bash
# m6i-d G5: PC錨づけの3状態と誤検出陰性対照。G8: ROMディレクトリ自己汚染。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
from pathlib import Path
import sys

repo, scratch = map(Path, sys.argv[1:])
sys.path.insert(0, str(repo / "tools"))
import analyze_main_to_sub as m2s
import analyze_m6id as a
import build_m6ib_measure_rom as m6ib


def event(seq, clock, pc, kind="IN", port="00FE"):
    return m2s.Ev(seq, clock, 1, "sub", kind, port, 0, pc)


GATE = 0x1234

# (1) 別PCに長い IN $FE 連続があっても、ゲート入場ではない。
other_pc_spin = [event(i + 1, i + 1, "BEEF") for i in range(128)]
if a.gate_observation(other_pc_spin, GATE) != (False, False, 0, 0):
    raise SystemExit("G5別PCの長い連続をゲートと誤認した")
if a.gate_observation(other_pc_spin, None) != (False, False, 0, 0):
    raise SystemExit("G6ゲートなし腕で入場を誤認した")

# (2) ゲートPCのI/O後に別PCのsub I/Oがあれば解除。
released_rows = [event(1, 10, "1234"), event(2, 20, "5678", "OUT", "00F8")]
if a.gate_observation(released_rows, GATE) != (True, True, 1, 1):
    raise SystemExit("G5解除状態を識別できない")

# (3) ゲートPCのI/Oがあり、その後に別PCのsub I/Oがなければ未解除。
held_rows = [event(1, 10, "1234"), event(2, 20, "1234")]
if a.gate_observation(held_rows, GATE) != (True, False, 2, 0):
    raise SystemExit("G5未解除状態を識別できない")

# 途中で別PCへ進んでも、最後のゲートI/O後に進まなければ未解除。
last_gate_rows = [event(1, 10, "1234"), event(2, 20, "5678"),
                  event(3, 30, "1234")]
if a.gate_observation(last_gate_rows, GATE) != (True, False, 2, 0):
    raise SystemExit("G5最後のゲートI/O基準になっていない")

# G8: 走が生成しうる余分なファイルを置いても、到達判定は変わらない。
rom_dir = scratch / "rom"
rom_dir.mkdir()
for name, size in m6ib.EXPECTED_SIZES.items():
    (rom_dir / name).write_bytes(bytes(size))
digest = m6ib.rom_set_sha256(rom_dir)
rows = [event(1, 1, "9999")]
before = a.summarize("D-B0", rows, 0, rom_dir, digest, None)
(rom_dir / "generated.srm").write_bytes(b"synthetic")
if m6ib.sizes_valid(rom_dir):
    raise SystemExit("G8陰性対照が旧条件を壊していない")
after = a.summarize("D-B0", rows, 0, rom_dir, digest, None)
if not before["reached"] or not after["reached"] or before != after:
    raise SystemExit("G8余分なファイルで到達判定が変化した")

print("analyze_m6id_selftest: 項目数=5、G5=4・G8=1 OK（別PC長時間連続の陰性対照あり）")
PY
