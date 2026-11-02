#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B67_WORK:?}"
[[ ! -e "$PC88_B67_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B67_WORK"
work="$(cd "$PC88_B67_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B67_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B67_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" start="$3" end="$4" prefix="$work/$1" run_dir="$work/run-$1" rc=0
  local frame n=0 key
  local -a keys=(--key-hold 60 --type-at 3600 --type ' ' --key-at 7200 --key RETROK_F1) sequence=(RETROK_RETURN RETROK_SPACE)
  for ((frame=12000; frame<43200; frame+=2400)); do
    key="${sequence[n % 2]}"
    keys+=(--key-at "$frame" --key "$key")
    ((n+=1))
  done
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --insert-disk2 "$run_dir/G1-1.d88" --insert-disk2-at 1 --insert-disk2-image 1 --frames "$end" "${keys[@]}" --io-log "$prefix.io" --io-log-from-frame "$start" --sub-reg-log "$prefix.reg" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  return "$rc"
}
for start in 12000 19800 27600 35400; do
  end=$((start + 7800))
  run_one "O-$start" "$PC88_REF_ROM_DIR" "$start" "$end"
  run_one "S-$start" "$work/self" "$start" "$end"
done
PYTHONPATH="$REPO/tools" python3 - "$work" >"$work/result" <<'PY'
from pathlib import Path
import sys
from b39_sub_reg_compare import read as reg
from b67_requests import read, requests
w = Path(sys.argv[1])
for start in (12000, 19800, 27600, 35400):
    data = []
    for arm in ('O', 'S'):
        prefix = w / f'{arm}-{start}'
        sections, complete = read(prefix.with_suffix('.io'))
        record = reg(prefix.with_suffix('.reg'))
        rows = []
        if complete:
            offset = len(record['F']) - sum(e[1:3] == ('IN', 0xFC) for e in sections['main'])
            if offset < 0: raise ValueError()
            rows = requests(sections['main'], offset, arm, start)
        data.append((len(record['C']), int(complete), rows))
    print(f'window {start}-{start+7800} cross={data[0][0]} {data[1][0]} complete={data[0][1]} {data[1][1]}')
    for _, _, rows in data:
        for row in rows: print(row)
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b67-g1-f1-requests.txt"
