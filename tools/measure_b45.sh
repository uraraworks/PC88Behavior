#!/usr/bin/env bash
# 生記録は作業場に留める。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B45_WORK:?}"
[[ ! -e "$PC88_B45_WORK" && -f "$PC88_G1_DISK" ]] || exit 1
mkdir -p "$PC88_B45_WORK"
work="$(cd "$PC88_B45_WORK" && pwd)"
core="${PC88_B45_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
mkdir "$work/source"
git -C "$REPO" archive HEAD | tar -x -C "$work/source"
TMPDIR="$work" python3 "$work/source/src/build_main_rom.py" "$work/self" --unscii-hex "${PC88_VENDOR_DIR:-$REPO/../vendor}/unscii/unscii-8.hex" --misaki-bdf "${PC88_VENDOR_DIR:-$REPO/../vendor}/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B45_CORE_SRC:-$REPO/../vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" prefix="$work/$1" run_dir="$work/run-$1"
  trap 'rm -rf "$run_dir"' RETURN
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 4800 --type-at 3600 --type ' ' --io-log "$prefix.io" --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr"
  rm -rf "$run_dir"
  trap - RETURN
}
run_one OO-1 "$PC88_REF_ROM_DIR"
run_one OO-2 "$PC88_REF_ROM_DIR"
run_one SS-1 "$work/self"
run_one SS-2 "$work/self"
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY' || exit 1
from pathlib import Path
import sys
from b45_sub_out_stream import read, compare
try:
    work = Path(sys.argv[1])
    data = {name: read(work / (name + '.io')) for name in ('OO-1', 'OO-2', 'SS-1', 'SS-2')}
    def output_equal(a, b):
        return (a[1] == b[1] and
                {p: [(v, pc) for v, pc, _ in seq] for p, seq in a[0].items()} ==
                {p: [(v, pc) for v, pc, _ in seq] for p, seq in b[0].items()})
    a, b = data['OO-1'][1], data['SS-1'][1]
    diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    first = diffs[0] if diffs else None
    run = 0
    if first is not None:
        while first + run < min(len(a), len(b)) and a[first + run] != b[first + run]:
            run += 1
    checks = [('OO-runs-output-equal', output_equal(data['OO-1'], data['OO-2'])),
              ('SS-runs-output-equal', output_equal(data['SS-1'], data['SS-2'])),
              ('fc-difference-count-257', len(diffs) == 257),
              ('fc-first-76570', first == 76570),
              ('fc-run-132', run == 132)]
    for name, ok in checks:
        print(f'{name} {str(ok).lower()}')
    if not all(ok for _, ok in checks):
        raise ValueError('gate')
    (work / 'result').write_text('\n'.join(compare(data['OO-1'], data['SS-1'])) + '\n', encoding='utf-8')
except Exception:
    print('関門の判定に失敗', file=sys.stderr)
    sys.exit(1)
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b45-g1-sub-out-stream.txt"
