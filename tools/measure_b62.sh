#!/usr/bin/env bash
# 生記録は作業場に留める。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B62_WORK:?}"
[[ ! -e "$PC88_B62_WORK" && -f "$PC88_G1_DISK" ]] || exit 1
mkdir -p "$PC88_B62_WORK"
work="$(cd "$PC88_B62_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B62_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*' EXIT
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B62_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" key="$3" prefix="$work/$1" run_dir="$work/run-$1"
  local -a keys=(--type-at 3600 --type ' ')
  if [[ "$key" != none ]]; then keys+=(--key-at 7200 --key "RETROK_$key"); fi
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 9000 "${keys[@]}" --main-event-log "$prefix.event" --main-event-from-frame 7000 --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  rm -rf "$run_dir"
}
for key in none 2 i; do
  run_one "$key-OO-1" "$PC88_REF_ROM_DIR" "$key"
  run_one "$key-OO-2" "$PC88_REF_ROM_DIR" "$key"
  run_one "$key-SS-1" "$work/self" "$key"
done
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
from pathlib import Path
import sys
from b62_main_event_compare import compare
w = Path(sys.argv[1])
def rows(key, a, b):
    return compare(w / f'{key}-{a}.event', w / f'{key}-{b}.event')
checks = [(f'official-{key}-equal', rows(key, 'OO-1', 'OO-2')[1] == 'first-diff none') for key in ('none', '2', 'i')]
checks.append(('control-official-self-equal', rows('none', 'OO-1', 'SS-1')[1] == 'first-diff none'))
for name, ok in checks:
    print(f'{name} {str(ok).lower()}')
if not all(ok for _, ok in checks):
    sys.exit(1)
with (w / 'result').open('w', encoding='utf-8') as out:
    for key in ('none', '2', 'i'):
        for row in rows(key, 'OO-1', 'SS-1'):
            out.write(f'{key} {row}\n')
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b62-g1-main-event-stream.txt"
