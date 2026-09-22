#!/usr/bin/env bash
# m6i-c G4の陽性対照と、全10項目それぞれの陰性対照。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="/private/tmp/claude-501/-Users-haruurara-MyProject--emulator-PC88/f621696a-188f-4769-8f74-f19993332403/scratchpad"
mkdir -p "$SCRATCH"
WORK="$(mktemp -d "$SCRATCH/m6ic-rom-gate.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

POSITIVE="$WORK/positive"
mkdir -p "$POSITIVE"

# 重い基底ビルドはC0/C1の各1回だけにする。
for arm in C0 C1; do
  python3 "$REPO/tools/build_m6ic_measure_rom.py" "$POSITIVE/$arm" --arm "$arm" \
    --work-dir "$WORK/build-$arm" >"$WORK/build-$arm.txt" || exit 1
done

# C2/C3も本番ビルダー自身の合成関数で作り、陽性対照の生成経路を複製しない。
python3 - "$REPO" "$POSITIVE" <<'PY'
import pathlib
import sys

repo, positive = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(repo / "tools"))
import build_m6ic_measure_rom as builder

for arm in ("C2", "C3"):
    builder.copy_rom_set(
        positive / arm, positive / "C0", positive / "C1", arm
    )
PY

python3 "$REPO/tools/check_m6ic_rom_gate.py" \
  "$POSITIVE/C0" "$POSITIVE/C1" "$POSITIVE/C2" "$POSITIVE/C3" \
  >"$WORK/positive.txt" || exit 1

make_case() {
  local name="$1"
  cp -R "$POSITIVE" "$WORK/$name"
}

mutate_byte_same_size() {
  python3 - "$1" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = bytearray(path.read_bytes())
data[0] ^= 1
path.write_bytes(data)
PY
}

make_wrong_config() {
  local key="$1"
  local output="$2"
  python3 - "$REPO/tools/m6ic_frozen.tsv" "$key" "$output" <<'PY'
import pathlib
import sys

source, key, output = sys.argv[1:]
lines = pathlib.Path(source).read_text(encoding="utf-8").splitlines()
prefix = key + "\t"
matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
assert len(matches) == 1
lines[matches[0]] = prefix + "0" * 64
pathlib.Path(output).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

run_negative() {
  local name="$1"
  local target="$2"
  local expected_ng="$3"
  local config="${4:-$REPO/tools/m6ic_frozen.tsv}"
  local case_dir="$WORK/$name"
  local result="$WORK/$name.txt"

  if python3 "$REPO/tools/check_m6ic_rom_gate.py" \
    "$case_dir/C0" "$case_dir/C1" "$case_dir/C2" "$case_dir/C3" \
    --config "$config" >"$result"; then
    echo "NG: $name の故障注入を通した" >&2
    exit 1
  fi

  python3 - "$result" "$target" "$expected_ng" <<'PY'
import pathlib
import sys

path, target, expected_text = sys.argv[1:]
rows = dict(
    line.split("=", 1)
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines()
)
expected = set(expected_text.split(","))
actual = {name for name, value in rows.items() if value == "NG"}
assert rows["passed"] == "false", (path, rows["passed"])
assert rows[target] == "NG", (path, target, rows[target])
assert actual == expected, (path, sorted(expected), sorted(actual))
PY
}

# 凍結値だけを壊すため、ROM間の直交関係には影響しない。
make_case c0_frozen_match
make_wrong_config c0_rom_set_sha256 "$WORK/c0-wrong.tsv"
run_negative c0_frozen_match c0_frozen_match c0_frozen_match "$WORK/c0-wrong.tsv"

make_case c1_frozen_match
make_wrong_config c1_rom_set_sha256 "$WORK/c1-wrong.tsv"
run_negative c1_frozen_match c1_frozen_match c1_frozen_match "$WORK/c1-wrong.tsv"

make_case c2_main_matches_c0
cp "$WORK/c2_main_matches_c0/C1/N88.ROM" \
  "$WORK/c2_main_matches_c0/C2/N88.ROM"
run_negative c2_main_matches_c0 c2_main_matches_c0 c2_main_matches_c0

make_case c2_disk_matches_c1
cp "$WORK/c2_disk_matches_c1/C0/DISK.ROM" \
  "$WORK/c2_disk_matches_c1/C2/DISK.ROM"
run_negative c2_disk_matches_c1 c2_disk_matches_c1 c2_disk_matches_c1

make_case c3_main_matches_c1
cp "$WORK/c3_main_matches_c1/C0/N88.ROM" \
  "$WORK/c3_main_matches_c1/C3/N88.ROM"
run_negative c3_main_matches_c1 c3_main_matches_c1 c3_main_matches_c1

make_case c3_disk_matches_c0
cp "$WORK/c3_disk_matches_c0/C1/DISK.ROM" \
  "$WORK/c3_disk_matches_c0/C3/DISK.ROM"
run_negative c3_disk_matches_c0 c3_disk_matches_c0 c3_disk_matches_c0

make_case main_variant_count_is_2
mutate_byte_same_size "$WORK/main_variant_count_is_2/C2/N88.ROM"
# 第3変種をC2に作るので、C0との一致も巻き添えでNGになる。
run_negative main_variant_count_is_2 main_variant_count_is_2 \
  c2_main_matches_c0,main_variant_count_is_2

make_case disk_variant_count_is_2
mutate_byte_same_size "$WORK/disk_variant_count_is_2/C2/DISK.ROM"
# 第3変種をC2に作るので、C1との一致も巻き添えでNGになる。
run_negative disk_variant_count_is_2 disk_variant_count_is_2 \
  c2_disk_matches_c1,disk_variant_count_is_2

make_case common_roms_identical
mutate_byte_same_size "$WORK/common_roms_identical/C2/FONT.ROM"
run_negative common_roms_identical common_roms_identical common_roms_identical

make_case all_sizes_valid
: >"$WORK/all_sizes_valid/C2/EXTRA.ROM"
run_negative all_sizes_valid all_sizes_valid all_sizes_valid

python3 - "$WORK/positive.txt" <<'PY'
import pathlib
import sys

rows = dict(
    line.split("=", 1)
    for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
)
assert rows["passed"] == "true"
assert sum(value == "OK" for value in rows.values()) == 10
assert sum(value == "NG" for value in rows.values()) == 0
PY

echo "check_m6ic_rom_gate_selftest: 陽性対照10項目 OK・NG 0件、陰性対照10件 false・対象項目 NG"
