#!/usr/bin/env bash
# 生記録は作業場に留める。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B54_WORK:?}"
[[ ! -e "$PC88_B54_WORK" && -f "$PC88_G1_DISK" ]] || exit 1
mkdir -p "$PC88_B54_WORK"
work="$(cd "$PC88_B54_WORK" && pwd)"
core="${PC88_B54_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "${PC88_VENDOR_DIR:-$REPO/../vendor}/unscii/unscii-8.hex" --misaki-bdf "${PC88_VENDOR_DIR:-$REPO/../vendor}/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B54_CORE_SRC:-$REPO/../vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" prefix="$work/$1" run_dir="$work/run-$1"
  trap 'rm -rf "$run_dir"' RETURN
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 4800 --type-at 3600 --type ' ' --io-log "$prefix.io" --sub-event-log "$prefix.event" --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr"
  rm -rf "$run_dir"
  trap - RETURN
}
run_one OO-1 "$PC88_REF_ROM_DIR"
run_one SS-1 "$work/self"
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY' || exit 1
from pathlib import Path
import sys
from b8_io_values import parse_log
work = Path(sys.argv[1])
checks = []
for arm, expected in (('OO', 112426), ('SS', 95522)):
    with (work / (arm + '-1.io')).open(encoding='utf-8', errors='replace') as f:
        count = len(parse_log(f)[('IN', '00FC', 'raw')])
    checks.append((f'{arm}-fc-count-{expected}', count == expected))
for name, ok in checks:
    print(f'{name} {str(ok).lower()}')
if not all(ok for _, ok in checks):
    sys.exit(1)
PY
if ! python3 "$REPO/tools/b46_sub_event_compare.py" "$work/OO-1.event" "$work/SS-1.event" >"$work/event-stream" 2>/dev/null; then
  echo b46_sub_event_compare.py
  exit 1
fi
if ! python3 "$REPO/tools/b48_fc_position.py" "$work/OO-1.io" "$work/SS-1.io" >"$work/fc-position" 2>/dev/null; then
  echo b48_fc_position.py
  exit 1
fi
if ! python3 "$REPO/tools/b49_handshake_order.py" "$work/OO-1.io" --arm OO >"$work/handshake-order" 2>/dev/null || ! python3 "$REPO/tools/b49_handshake_order.py" "$work/SS-1.io" --arm SS >>"$work/handshake-order" 2>/dev/null; then
  echo b49_handshake_order.py
  exit 1
fi
mkdir -p "$REPO/measurements"
cp "$work/event-stream" "$REPO/measurements/b54-g1-event-stream.txt"
cp "$work/fc-position" "$REPO/measurements/b54-g1-fc-position.txt"
cp "$work/handshake-order" "$REPO/measurements/b54-g1-handshake-order.txt"
