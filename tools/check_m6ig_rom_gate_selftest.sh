#!/usr/bin/env bash
# m6i-g G4の陽性7項目と各項目の陰性対照、介入sub差替え対照。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
POS="$WORK/positive"
mkdir -p "$POS"
for arm in G-N G-L0 G-L1 G-L2; do
  python3 "$REPO/tools/build_m6ig_measure_rom.py" "$POS/$arm" --arm "$arm" \
    --work-dir "$WORK/build-$arm" >"$WORK/build-$arm.out" || exit 1
done
for arm in B0 B1 B4 B5; do
  python3 "$REPO/tools/build_m6ib_measure_rom.py" "$POS/$arm" --arm "$arm" \
    --work-dir "$WORK/build-$arm" >"$WORK/build-$arm.out" || exit 1
done
CHECK=(python3 "$REPO/tools/check_m6ig_rom_gate.py")
run_check() {
  local root="$1" config="$REPO/tools/m6ig_frozen.tsv"
  [ ! -f "$root/config.tsv" ] || config="$root/config.tsv"
  "${CHECK[@]}" "$root/G-N" "$root/G-L0" "$root/G-L1" "$root/G-L2" \
    --m6ib-b0-dir "$root/B0" --m6ib-b1-dir "$root/B1" \
    --m6ib-b4-dir "$root/B4" --m6ib-b5-dir "$root/B5" --config "$config"
}
run_check "$POS" >"$WORK/positive.out" || exit 1
make_case() { cp -R "$POS" "$WORK/$1"; }
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
awk -F '\t' 'BEGIN{OFS="\t"} $1=="plain_subrom_sha256"{$2="0" substr($2,2) "d"}{print}' \
  "$REPO/tools/m6ig_frozen.tsv" >"$WORK/plain_subrom_frozen_match/config.tsv"
run_negative plain_subrom_frozen_match plain_subrom_frozen_match
make_case all_disks_identical; mutate_byte "$WORK/all_disks_identical/G-L0/DISK.ROM"
run_negative all_disks_identical all_disks_identical,disks_match_plain_subrom
make_case disks_match_plain_subrom
for arm in G-N G-L0 G-L1 G-L2; do mutate_byte "$WORK/disks_match_plain_subrom/$arm/DISK.ROM"; done
run_negative disks_match_plain_subrom disks_match_plain_subrom
make_case common_roms_identical; mutate_byte "$WORK/common_roms_identical/G-L1/FONT.ROM"
run_negative common_roms_identical common_roms_identical
make_case all_mains_distinct
cp "$WORK/all_mains_distinct/G-N/N88.ROM" "$WORK/all_mains_distinct/G-L0/N88.ROM"
run_negative all_mains_distinct all_mains_distinct,mains_match_m6ib_sources
make_case mains_match_m6ib_sources; mutate_byte "$WORK/mains_match_m6ib_sources/G-N/N88.ROM"
run_negative mains_match_m6ib_sources mains_match_m6ib_sources
make_case all_sizes_valid; : >"$WORK/all_sizes_valid/G-L2/EXTRA.ROM"
run_negative all_sizes_valid all_sizes_valid

# 必須対照: 1腕だけをB5の介入ありsubへ差し替える。
make_case intervention_sub_replacement
cp "$WORK/intervention_sub_replacement/B5/DISK.ROM" \
  "$WORK/intervention_sub_replacement/G-L1/DISK.ROM"
run_negative intervention_sub_replacement all_disks_identical,disks_match_plain_subrom

python3 - "$WORK/positive.out" <<'PY'
from pathlib import Path
import sys
rows=dict(line.split('=',1) for line in Path(sys.argv[1]).read_text().splitlines())
assert rows['passed']=='true' and sum(v=='OK' for v in rows.values())==7
PY
echo "check_m6ig_rom_gate_selftest: 陽性7項目OK、陰性対照8件false・NG集合一致（介入ありsub差替え検出）"
