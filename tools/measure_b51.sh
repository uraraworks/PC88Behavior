#!/usr/bin/env bash
# 生記録は作業場に留める。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B51_WORK:?}"
[[ ! -e "$PC88_B51_WORK" && -f "$PC88_G1_DISK" ]] || exit 1
mkdir -p "$PC88_B51_WORK"
work="$(cd "$PC88_B51_WORK" && pwd)"
core="${PC88_B51_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
mkdir "$work/source"
git -C "$REPO" archive HEAD | tar -x -C "$work/source"
TMPDIR="$work" python3 "$work/source/src/build_main_rom.py" "$work/self" --unscii-hex "${PC88_VENDOR_DIR:-$REPO/../vendor}/unscii/unscii-8.hex" --misaki-bdf "${PC88_VENDOR_DIR:-$REPO/../vendor}/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B51_CORE_SRC:-$REPO/../vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$work/source/tools/harness/core" "$work/source/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" prefix="$work/$1" run_dir="$work/run-$1"
  trap 'rm -rf "$run_dir"' RETURN
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 4800 --type-at 3600 --type ' ' --sub-rom-access-log "$prefix.access" --sub-rom-access-window 76569,76828 --io-log "$prefix.io" --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr"
  rm -rf "$run_dir"
  trap - RETURN
}
run_one OO-1 "$PC88_REF_ROM_DIR"
run_one OO-2 "$PC88_REF_ROM_DIR"
run_one SS-1 "$work/self"
run_one SS-2 "$work/self"
PYTHONPATH="$work/source/tools" python3 - "$work" <<'PYCODE' || exit 1
from pathlib import Path
import sys
from b50_paired_request import read
from b51_whitelist import filter_line
try:
    w = Path(sys.argv[1]); names = ('OO-1', 'OO-2', 'SS-1', 'SS-2')
    io = [read(w / (n + '.io'))[1] for n in names]
    def difference(a, b):
        diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x[3] != y[3]]
        first = diffs[0] if diffs else None
        run = 0
        if first is not None:
            while first + run < min(len(a), len(b)) and a[first + run][3] != b[first + run][3]: run += 1
        return len(diffs), first, run
    rows = [(w / (n + '.access')).read_text(encoding='utf-8').splitlines() for n in names]
    checks = [('fc-difference-b44', all(difference(io[i], io[i+2]) == (257, 76570, 132) for i in (0, 1))),
              ('OO-runs-equal', rows[0] == rows[1]), ('SS-runs-equal', rows[2] == rows[3]),
              ('complete', all(r and r[-1] == 'dropped=0 complete=1' for r in rows))]
    for name, ok in checks: print(f'{name} {str(ok).lower()}')
    if not all(ok for _, ok in checks): sys.exit(1)
    for arm, row in [('OO', rows[0]), ('SS', rows[2])]:
        filtered = [filter_line(x) for x in row]
        if any(x is None for x in filtered): raise ValueError('invalid row')
        (w / ('result-' + arm)).write_text('# 識別子: G1\n' + '\n'.join(filtered) + '\n', encoding='utf-8')
except Exception:
    print('analysis false', file=sys.stderr); sys.exit(1)
PYCODE
mkdir -p "$REPO/measurements"
cp "$work/result-OO" "$REPO/measurements/b51-g1-sub-rom-access-OO.txt"
cp "$work/result-SS" "$REPO/measurements/b51-g1-sub-rom-access-SS.txt"
