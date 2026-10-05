#!/usr/bin/env bash
# m6i-b全腕ROM門の陽性対照とサイズ・命令境界の陰性対照。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 "$REPO/tools/check_m6ib_rom_gate.py" --work-dir "$WORK/ok" \
  >"$WORK/ok.json" || exit 1
if python3 "$REPO/tools/check_m6ib_rom_gate.py" --work-dir "$WORK/size" --fault size \
  >"$WORK/size.json"; then
  echo "NG: サイズ故障を通した" >&2
  exit 1
fi
if python3 "$REPO/tools/check_m6ib_rom_gate.py" --work-dir "$WORK/boundary" \
  --fault instruction-boundary >"$WORK/boundary.json"; then
  echo "NG: 命令境界故障を通した" >&2
  exit 1
fi
python3 - "$REPO" "$WORK" "$WORK/ok.json" "$WORK/size.json" "$WORK/boundary.json" <<'PY'
import json, sys
from pathlib import Path
repo, work = map(Path, sys.argv[1:3])
ok, size, boundary = [json.load(open(path, encoding="utf-8")) for path in sys.argv[3:]]
assert ok["passed"] and ok["b0_matches_m6ia_a0"]
assert ok["all_rom_sets_mutually_distinct"] and len(ok["sha256"]) == 12
assert not size["passed"] and not size["size_gate"]
assert size["instruction_boundary_gate"] and size["ram_allocation_gate"]
assert not boundary["passed"] and not boundary["instruction_boundary_gate"]
assert boundary["size_gate"] and boundary["ram_allocation_gate"]
for negative in (size, boundary):
    assert negative["b0_matches_m6ia_a0"] and negative["all_rom_sets_mutually_distinct"]

# 正典名を無差別に除外してRAM衝突を見逃さないことも確認する。
sys.path.insert(0, str(repo / "tools"))
import check_m6ib_rom_gate as gate
original_assemble = gate.mainrom.assemble
def collision_assemble(text, work):
    rom, asm = original_assemble(text, work)
    asm.symtab["MM_UNREGISTERED_COLLISION"] = gate.memmap.addresses()["MM_M6IB_FRAME_COUNT"]
    return rom, asm
assert gate.main_instruction_boundaries_valid(work / "ok/b1", work / "ram-positive", "B1") == (True, True)
gate.mainrom.assemble = collision_assemble
assert gate.main_instruction_boundaries_valid(work / "ok/b1", work / "ram-negative", "B1") == (True, False)
PY
echo "check_m6ib_rom_gate_selftest: 全12 ROM・陰性対照 OK"
