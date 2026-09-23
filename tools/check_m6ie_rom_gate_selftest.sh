#!/usr/bin/env bash
# m6i-e G4の陽性対照と、全12項目それぞれの陰性対照。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
POS="$WORK/positive"
mkdir -p "$POS"
for arm in E0 E1 E2 E3; do
  python3 "$REPO/tools/build_m6ie_measure_rom.py" "$POS/$arm" --arm "$arm" \
    --work-dir "$WORK/build-$arm" >"$WORK/build-$arm.out" || exit 1
done
for arm in C0 C2; do
  python3 "$REPO/tools/build_m6ic_measure_rom.py" "$POS/$arm" --arm "$arm" \
    --work-dir "$WORK/build-$arm" >"$WORK/build-$arm.out" || exit 1
done

CHECK=(python3 "$REPO/tools/check_m6ie_rom_gate.py")
run_check() {
  local root="$1"
  local config="$REPO/tools/m6ic_frozen.tsv"
  if [ -f "$root/m6ic.tsv" ]; then config="$root/m6ic.tsv"; fi
  "${CHECK[@]}" "$root/E0" "$root/E1" "$root/E2" "$root/E3" \
    --m6ic-c0-dir "$root/C0" --m6ic-c2-dir "$root/C2" --m6ic-config "$config"
}
run_check "$POS" >"$WORK/positive.out" || exit 1

make_case() { cp -R "$POS" "$WORK/$1"; }
mutate_at() {
  python3 - "$1" "$2" <<'PY'
from pathlib import Path
import sys
p, offset = Path(sys.argv[1]), int(sys.argv[2])
d = bytearray(p.read_bytes()); d[offset] ^= 1; p.write_bytes(d)
PY
}
insert_pos() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys
d=Path(sys.argv[1]).read_bytes(); needle=bytes((0xDB,0xFE,0xE6,0x08,0x28,0xFA))
assert d.count(needle)==1
print(d.index(needle))
PY
}
run_negative() {
  local name="$1" expected="$2" output="$WORK/$1.out"
  if run_check "$WORK/$name" >"$output"; then
    echo "NG: $name の故障注入を通した" >&2; exit 1
  fi
  python3 - "$output" "$expected" <<'PY'
from pathlib import Path
import sys
rows=dict(line.split('=',1) for line in Path(sys.argv[1]).read_text().splitlines())
actual={k for k,v in rows.items() if v=='NG'}
expected=set(sys.argv[2].split(','))
assert rows['passed']=='false' and actual==expected,(sorted(actual),sorted(expected))
PY
  [ "$?" -eq 0 ] || exit 1
}

pos="$(insert_pos "$POS/E0/DISK.ROM")"
make_case m6ic_c0_frozen_match
awk -F '\t' 'BEGIN{OFS="\t"} $1=="c0_rom_set_sha256"{$2="0000000000000000000000000000000000000000000000000000000000000000"}{print}' \
  "$REPO/tools/m6ic_frozen.tsv" >"$WORK/m6ic_c0_frozen_match/m6ic.tsv"
run_negative m6ic_c0_frozen_match m6ic_c0_frozen_match
make_case all_mains_identical; mutate_at "$WORK/all_mains_identical/E2/N88.ROM" 0
run_negative all_mains_identical all_mains_identical
make_case main_matches_m6ic_c0; mutate_at "$WORK/main_matches_m6ic_c0/C0/N88.ROM" 0
run_negative main_matches_m6ic_c0 m6ic_c0_frozen_match,main_matches_m6ic_c0
make_case e1_disk_matches_m6ic_c2; mutate_at "$WORK/e1_disk_matches_m6ic_c2/C2/DISK.ROM" 0
run_negative e1_disk_matches_m6ic_c2 e1_disk_matches_m6ic_c2
make_case e0_disk_matches_m6ic_c0; mutate_at "$WORK/e0_disk_matches_m6ic_c0/C0/DISK.ROM" 0
run_negative e0_disk_matches_m6ic_c0 m6ic_c0_frozen_match,e0_disk_matches_m6ic_c0
make_case insertions_share_six_byte_region; mutate_at "$WORK/insertions_share_six_byte_region/E2/DISK.ROM" $((pos + 20))
run_negative insertions_share_six_byte_region insertions_share_six_byte_region,e0_insertion_matches_registered,e2_insertion_matches_registered,e3_insertion_matches_registered,e1_e3_shifted_match
make_case e0_insertion_matches_registered; mutate_at "$WORK/e0_insertion_matches_registered/E0/DISK.ROM" "$pos"
run_negative e0_insertion_matches_registered e0_disk_matches_m6ic_c0,e0_insertion_matches_registered
make_case e2_insertion_matches_registered; mutate_at "$WORK/e2_insertion_matches_registered/E2/DISK.ROM" $((pos + 2))
run_negative e2_insertion_matches_registered e2_insertion_matches_registered
make_case e3_insertion_matches_registered; mutate_at "$WORK/e3_insertion_matches_registered/E3/DISK.ROM" $((pos + 2))
run_negative e3_insertion_matches_registered e3_insertion_matches_registered
make_case e1_e3_shifted_match; mutate_at "$WORK/e1_e3_shifted_match/E1/DISK.ROM" $((pos + 30))
run_negative e1_e3_shifted_match e1_disk_matches_m6ic_c2,e1_e3_shifted_match
make_case common_roms_identical; mutate_at "$WORK/common_roms_identical/E2/FONT.ROM" 0
run_negative common_roms_identical common_roms_identical
make_case all_sizes_valid; : >"$WORK/all_sizes_valid/E2/EXTRA.ROM"
run_negative all_sizes_valid all_sizes_valid

python3 - "$WORK/positive.out" <<'PY'
from pathlib import Path
import sys
rows=dict(line.split('=',1) for line in Path(sys.argv[1]).read_text().splitlines())
assert rows['passed']=='true'
assert sum(v=='OK' for v in rows.values())==12
PY
echo "check_m6ie_rom_gate_selftest: 陽性12項目 OK、陰性対照12件（挿入バイト改変を含む）false・NG集合一致"
