#!/usr/bin/env bash
# クラウド用。公式素材は環境変数からのみ受け取り、生記録は作業場に留める。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B37_WORK:?}"
[[ ! -e "$PC88_B37_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B37_WORK"
work="$(cd "$PC88_B37_WORK" && pwd)"
core="${PC88_B37_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
mkdir -p "$work/source" "$work/self"
git -C "$REPO" archive ff113bf | tar -x -C "$work/source"
TMPDIR="$work" python3 "$work/source/src/build_main_rom.py" "$work/self" --unscii-hex "$REPO/../vendor/unscii/unscii-8.hex" --misaki-bdf "$REPO/../vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B37_CORE_SRC:-$REPO/../vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
mkdir -p "$REPO/measurements"
for arm in OO SS; do
  if [[ "$arm" == OO ]]; then rom="$PC88_REF_ROM_DIR"; else rom="$work/self"; fi
  for run in 1 2; do
    prefix="$work/$arm-$run"
    run_dir="$work/run-$arm-$run"
    trap 'rm -rf "$run_dir"' EXIT
    mkdir -p "$run_dir/rom"
    cp -RL "$rom/." "$run_dir/rom/"
    cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
    "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 4800 --type-at 3600 --type ' ' --io-log "$prefix.io" --sub-rom-read-log "$prefix.raw" --sub-rom-read-window 76500,76766 --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr"
    rm -rf "$run_dir"
    trap - EXIT
    python3 "$REPO/tools/b37_whitelist_sub_rom_reads.py" "$prefix.raw" --out "$work/$arm-$run.filtered" 2>"$prefix.filter.err"
  done
done
# B8 の値非公開経路を使い、関門を満たすかだけを判定する。
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
import pathlib, sys
from b8_io_values import parse_log
w = pathlib.Path(sys.argv[1])
def read(name):
    p = w / (name + '.io')
    with p.open(encoding='utf-8', errors='replace') as f:
        text = f.readlines()
    main = text[text.index('# main\n') + 1:text.index('# sub\n')]
    if not any('# 取りこぼし: 0件' in x for x in main): raise ValueError('I/O 記録が不完全')
    return parse_log(text)[('IN', '00FC', 'raw')]
ok = True
def check(name, result):
    global ok
    print(f'{name} {str(result).lower()}')
    ok &= result

for n in (1, 2):
    a, b = read(f'OO-{n}'), read(f'SS-{n}')
    diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x[0] != y[0]]
    first = diffs[0] if diffs else None
    run = 0
    if first is not None:
        while first + run < min(len(a), len(b)) and a[first+run][0] != b[first+run][0]: run += 1
    check(f'fc-diff-257-run{n}', len(diffs) == 257)
    check(f'fc-first-76570-run{n}', first == 76570)
    check(f'fc-consecutive-132-run{n}', run == 132)
for arm in ('OO', 'SS'):
    f1, f2 = ((w / f'{arm}-{n}.filtered').read_bytes() for n in (1, 2))
    check(f'{arm}-runs-equal', f1 == f2)
    check(f'{arm}-complete', f1.endswith(b'dropped=0 complete=1\n'))
    for n in (1, 2):
        check(f'{arm}-no-exclusions-run{n}', (w / f'{arm}-{n}.filter.err').read_text().strip() == '除外: 0 行')
if not ok: raise SystemExit(1)
PY
for arm in OO SS; do
  for run in 1 2; do
    cp "$work/$arm-$run.filtered" "$REPO/measurements/b37-g1-sub-rom-reads-$arm-$run.txt"
  done
done
python3 "$REPO/tools/b37_sub_rom_reads_compare.py" "$work/OO-1.filtered" "$work/SS-1.filtered"
