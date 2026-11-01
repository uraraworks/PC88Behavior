#!/usr/bin/env bash
# 生記録は作業場に留める。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B50_WORK:?}"
[[ ! -e "$PC88_B50_WORK" && -f "$PC88_G1_DISK" ]] || exit 1
mkdir -p "$PC88_B50_WORK"
work="$(cd "$PC88_B50_WORK" && pwd)"
core="${PC88_B50_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
mkdir "$work/source"
git -C "$REPO" archive HEAD | tar -x -C "$work/source"
TMPDIR="$work" python3 "$work/source/src/build_main_rom.py" "$work/self" --unscii-hex "${PC88_VENDOR_DIR:-$REPO/../vendor}/unscii/unscii-8.hex" --misaki-bdf "${PC88_VENDOR_DIR:-$REPO/../vendor}/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B50_CORE_SRC:-$REPO/../vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
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
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PYCODE' || exit 1
from pathlib import Path
import sys
from b50_paired_request import read, bursts, summarize
try:
    work = Path(sys.argv[1])
    names = ('OO-1', 'OO-2', 'SS-1', 'SS-2')
    data = {n: read(work / (n + '.io')) for n in names}
    pairs = [(bursts(data[n])) for n in names]
    shapes = [[(x[0], x[1]) for x in group] for group in pairs]
    outputs = [summarize(data['OO-1'], data['SS-1']),
               summarize(data['OO-2'], data['SS-2'])]
    # 各腕の出力の再現性は相手を固定して検査する。
    oo_repeat = summarize(data['OO-1'], data['SS-1']) == summarize(data['OO-2'], data['SS-1'])
    ss_repeat = (summarize(data['OO-1'], data['SS-1']) == summarize(data['OO-1'], data['SS-2'])
                 and [(x[0], x[1], x[2]) for x in pairs[2]] == [(x[0], x[1], x[2]) for x in pairs[3]])
    a, b = data['OO-1'][1], data['SS-1'][1]
    diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x[3] != y[3]]
    first = diffs[0] if diffs else None
    run = 0
    if first is not None:
        while first + run < min(len(a), len(b)) and a[first + run][3] != b[first + run][3]:
            run += 1
    burst_rows = [[(x[0], x[1], x[2]) for x in group] for group in pairs]
    checks = [('burst-shape', all(s == [(3, 'single'), (5, 'single'), (8, 'paired'), (11, 'single')] for s in shapes)),
              ('OO-runs-output-equal', oo_repeat), ('SS-runs-output-equal', ss_repeat),
              ('OO-SS-burst-equal', burst_rows[0] == burst_rows[2]),
              ('fc-difference-count-257', len(diffs) == 257),
              ('fc-first-76570', first == 76570), ('fc-run-132', run == 132)]
    for name, ok in checks:
        print(f'{name} {str(ok).lower()}')
    if not all(ok for _, ok in checks):
        sys.exit(1)
    (work / 'result').write_text('\n'.join(outputs[0]) + '\n', encoding='utf-8')
except Exception:
    print('analysis false', file=sys.stderr)
    sys.exit(1)
PYCODE
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b50-g1-paired-request.txt"
