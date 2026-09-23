#!/usr/bin/env bash
# m6i-h G4の陽性9項目と各項目の陰性対照を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
POS="$WORK/positive"; mkdir -p "$POS"
for arm in H-N H-W H-A H-B; do
  python3 "$REPO/tools/build_m6ih_measure_rom.py" "$POS/$arm" --arm "$arm" \
    --work-dir "$WORK/build-$arm" >"$WORK/build-$arm.out" || exit 1
done
for arm in B0 B4; do
  python3 "$REPO/tools/build_m6ib_measure_rom.py" "$POS/$arm" --arm "$arm" \
    --work-dir "$WORK/build-$arm" >"$WORK/build-$arm.out" || exit 1
done

# この直接対照は、末尾のnot frame_ref and not wait_labelを削るとH-Wで失敗する。
python3 - "$REPO" "$POS" "$WORK/direct-no-frame-wait" <<'PY'
import pathlib
import sys

repo, positive, work = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(repo / "tools"))
import check_m6ih_rom_gate as gate

b4_main = (positive / "B4" / "N88.ROM").read_bytes()
cases = (("H-W", False), ("H-A", True), ("H-B", True))
for arm, expected in cases:
    actual = gate.no_frame_wait_and_matches(
        positive / arm, work / arm, arm, b4_main
    )
    assert actual is expected, (arm, expected, actual)
PY

CHECK=(python3 "$REPO/tools/check_m6ih_rom_gate.py")
run_check() {
  local root="$1" config="$REPO/tools/m6ih_frozen.tsv"
  [ ! -f "$root/config.tsv" ] || config="$root/config.tsv"
  "${CHECK[@]}" "$root/H-N" "$root/H-W" "$root/H-A" "$root/H-B" \
    --m6ib-b0-dir "$root/B0" --m6ib-b4-dir "$root/B4" \
    --work-dir "$root/verify" --config "$config"
}
run_check "$POS" >"$WORK/positive.out" || exit 1
make_case() { cp -R "$POS" "$WORK/$1"; rm -rf "$WORK/$1/verify"; }
mutate_byte() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); data=bytearray(p.read_bytes()); data[0]^=1; p.write_bytes(data)
PY
}
run_negative() {
  local name="$1" expected="$2" output="$WORK/$1.out"
  if run_check "$WORK/$name" >"$output"; then echo "NG: $name を通した" >&2; exit 1; fi
  python3 - "$output" "$expected" <<'PY'
from pathlib import Path
import sys
rows=dict(line.split('=',1) for line in Path(sys.argv[1]).read_text().splitlines())
actual={k for k,v in rows.items() if v=='NG'}; expected=set(sys.argv[2].split(','))
assert rows['passed']=='false' and actual==expected,(sorted(actual),sorted(expected))
PY
}

make_case plain_subrom_frozen_match
sed 's/^plain_subrom_sha256.*/plain_subrom_sha256\t0/' "$REPO/tools/m6ih_frozen.tsv" >"$WORK/plain_subrom_frozen_match/config.tsv"
run_negative plain_subrom_frozen_match plain_subrom_frozen_match
make_case all_disks_identical; mutate_byte "$WORK/all_disks_identical/H-W/DISK.ROM"
run_negative all_disks_identical all_disks_identical,disks_match_plain_subrom
make_case disks_match_plain_subrom
for arm in H-N H-W H-A H-B; do mutate_byte "$WORK/disks_match_plain_subrom/$arm/DISK.ROM"; done
run_negative disks_match_plain_subrom disks_match_plain_subrom
make_case common_roms_identical; mutate_byte "$WORK/common_roms_identical/H-A/FONT.ROM"
run_negative common_roms_identical common_roms_identical
make_case all_mains_distinct; cp "$WORK/all_mains_distinct/H-N/N88.ROM" "$WORK/all_mains_distinct/H-B/N88.ROM"
run_negative all_mains_distinct all_mains_distinct,new_mains_have_no_frame_wait
make_case mains_match_m6ib_sources; mutate_byte "$WORK/mains_match_m6ib_sources/H-N/N88.ROM"
run_negative mains_match_m6ib_sources mains_match_m6ib_sources
make_case new_mains_have_no_frame_wait; cp "$WORK/new_mains_have_no_frame_wait/B4/N88.ROM" "$WORK/new_mains_have_no_frame_wait/H-A/N88.ROM"
run_negative new_mains_have_no_frame_wait all_mains_distinct,new_mains_have_no_frame_wait
make_case retry_marker_allocation
sed 's/retry_marker_address\t0xE00D/retry_marker_address\t0xE00E/' "$REPO/tools/m6ih_frozen.tsv" >"$WORK/retry_marker_allocation/config.tsv"
run_negative retry_marker_allocation retry_marker_allocation
make_case all_sizes_valid; : >"$WORK/all_sizes_valid/H-B/EXTRA.ROM"
run_negative all_sizes_valid all_sizes_valid

# 各G4判定だけをTrueへ置換し、対応するNG集合照合が必ず不一致になることを実走する。
python3 - "$REPO" "$WORK" <<'PY'
import ast
import contextlib
import io
import pathlib
import sys

repo, work = map(pathlib.Path, sys.argv[1:])
source_path = repo / "tools/check_m6ih_rom_gate.py"
source = source_path.read_text(encoding="utf-8")
cases = {
    "plain_subrom_frozen_match": ("plain_subrom_frozen_match", {"plain_subrom_frozen_match"}),
    "all_disks_identical": ("all_disks_identical", {"all_disks_identical", "disks_match_plain_subrom"}),
    "disks_match_plain_subrom": ("disks_match_plain_subrom", {"disks_match_plain_subrom"}),
    "common_roms_identical": ("common_roms_identical", {"common_roms_identical"}),
    "all_mains_distinct": ("all_mains_distinct", {"all_mains_distinct", "new_mains_have_no_frame_wait"}),
    "mains_match_m6ib_sources": ("mains_match_m6ib_sources", {"mains_match_m6ib_sources"}),
    "new_mains_have_no_frame_wait": ("new_mains_have_no_frame_wait", {"all_mains_distinct", "new_mains_have_no_frame_wait"}),
    "retry_marker_allocation": ("retry_marker_allocation", {"retry_marker_allocation"}),
    "all_sizes_valid": ("all_sizes_valid", {"all_sizes_valid"}),
}

class ForceCheckTrue(ast.NodeTransformer):
    def __init__(self, target):
        self.target = target
        self.replaced = 0

    def visit_Assign(self, node):
        self.generic_visit(node)
        if (any(isinstance(target, ast.Name) and target.id == "checks"
                for target in node.targets) and isinstance(node.value, ast.Dict)):
            for index, key in enumerate(node.value.keys):
                if isinstance(key, ast.Constant) and key.value == self.target:
                    node.value.values[index] = ast.copy_location(ast.Constant(True), node.value.values[index])
                    self.replaced += 1
        return node

for target, (case_name, expected) in cases.items():
    tree = ast.parse(source, filename=str(source_path))
    transformer = ForceCheckTrue(target)
    tree = ast.fix_missing_locations(transformer.visit(tree))
    assert transformer.replaced == 1, (target, transformer.replaced)
    namespace = {"__name__": f"m6ih_mutant_{target}", "__file__": str(source_path)}
    exec(compile(tree, str(source_path), "exec"), namespace)
    case = work / case_name
    config = case / "config.tsv"
    if not config.is_file():
        config = repo / "tools/m6ih_frozen.tsv"
    old_argv = sys.argv
    sys.argv = [str(source_path), *(str(case / arm) for arm in ("H-N", "H-W", "H-A", "H-B")),
                "--m6ib-b0-dir", str(case / "B0"), "--m6ib-b4-dir", str(case / "B4"),
                "--work-dir", str(work / "true-mutants" / target), "--config", str(config)]
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            rc = namespace["main"]()
    finally:
        sys.argv = old_argv
    rows = dict(line.split("=", 1) for line in output.getvalue().splitlines())
    actual = {name for name, value in rows.items() if value == "NG"}
    assert actual == expected - {target}, (target, sorted(actual), sorted(expected))
    assert actual != expected, (target, "NG集合照合をすり抜けた")
    assert rc == (1 if actual else 0), (target, rc, sorted(actual))
PY

# 必須対照: 1腕だけをm6i-b B4の介入ありsubへ差し替える。
make_case intervention_sub_replacement
cp "$WORK/intervention_sub_replacement/B4/DISK.ROM" "$WORK/intervention_sub_replacement/H-A/DISK.ROM"
run_negative intervention_sub_replacement all_disks_identical,disks_match_plain_subrom

python3 - "$WORK/positive.out" <<'PY'
from pathlib import Path
import sys
rows=dict(line.split('=',1) for line in Path(sys.argv[1]).read_text().splitlines())
assert rows['passed']=='true' and sum(v=='OK' for v in rows.values())==9
PY
echo "check_m6ih_rom_gate_selftest: 陽性9項目OK、陰性対照10件false・NG集合一致、待ち判定の直接対照3件OK、全9項目True変異を拒否"
