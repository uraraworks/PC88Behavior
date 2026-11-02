#!/usr/bin/env bash
# 生記録は作業場に留める。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B73_WORK:?}"
[[ ! -e "$PC88_B73_WORK" && -f "$PC88_G1_DISK" ]] || exit 1
mkdir -p "$PC88_B73_WORK"
work="$(cd "$PC88_B73_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B73_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*' EXIT
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B73_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" prefix="$work/$1" run_dir="$work/run-$1"
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
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --insert-disk2 "$run_dir/G1-1.d88" --insert-disk2-at 1 --insert-disk2-image 1 --frames 19800 "${keys[@]}" --sub-rom-access-log "$prefix.access" --sub-rom-access-window 112680,112830 --io-log "$prefix.io" --io-log-from-frame 12000 --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr"
  rm -rf "$run_dir"
  python3 "$REPO/tools/b51_whitelist.py" "$prefix.access" --out "$prefix.filtered" 2>"$prefix.filter-log"
  PYTHONPATH="$REPO/tools" python3 - "$prefix" <<'PY'
from pathlib import Path
import sys
from b13_sub_fdc import read_events
from analyze_b12 import CMDS
p = Path(sys.argv[1])
try:
    events = read_events(Path(str(p) + '.io'))
    writes = [value for kind, port, value, pc in events if kind == 'OUT' and port == 0xFB]
    names = []
    i = 0
    while i < len(writes):
        name, length = CMDS.get(writes[i] & 31, ('unknown', 1))
        if i + length > len(writes):
            raise ValueError('incomplete')
        names.append(name)
        i += length
    result = ' '.join(names)
except (OSError, UnicodeError, ValueError, IndexError):
    result = 'incomplete'
Path(str(p) + '.fdc').write_text(result + '\n', encoding='utf-8')
PY
}
run_one O-1 "$PC88_REF_ROM_DIR"
run_one O-2 "$PC88_REF_ROM_DIR"
run_one S-1 "$work/self"
run_one S-2 "$work/self"
for arm in O S; do
  cmp -s "$work/$arm-1.filtered" "$work/$arm-2.filtered" || exit 1
  cmp -s "$work/$arm-1.fdc" "$work/$arm-2.fdc" || exit 1
done
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY' >"$work/result"
from pathlib import Path
import sys
w = Path(sys.argv[1])
for arm in ('O', 'S'):
    for line in (w / f'{arm}-1.filtered').read_text(encoding='utf-8').splitlines():
        if line.startswith('A '):
            print(f'A {arm} {line[2:]}')
    print(f"fdc {arm} {(w / f'{arm}-1.fdc').read_text(encoding='utf-8').strip()}")
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b73-g1-f1-sub-after-0e.txt"
