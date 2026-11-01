#!/usr/bin/env bash
# クラウド用。公式素材は環境変数からのみ受け取り、生記録は作業場に留める。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B38_WORK:?}"
[[ ! -e "$PC88_B38_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B38_WORK"
work="$(cd "$PC88_B38_WORK" && pwd)"
core="${PC88_B38_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
mkdir -p "$work/source" "$work/self"
git -C "$REPO" archive ff113bf | tar -x -C "$work/source"
TMPDIR="$work" python3 "$work/source/src/build_main_rom.py" "$work/self" --unscii-hex "$REPO/../vendor/unscii/unscii-8.hex" --misaki-bdf "$REPO/../vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B38_CORE_SRC:-$REPO/../vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
mkdir -p "$REPO/measurements"
for arm in OO SS; do
  if [[ "$arm" == OO ]]; then rom="$PC88_REF_ROM_DIR"; else rom="$work/self"; fi
  for run in 1 2 control; do
    prefix="$work/$arm-$run"
    run_dir="$work/run-$arm-$run"
    trap 'rm -rf "$run_dir"' EXIT
    mkdir -p "$run_dir/rom"
    cp -RL "$rom/." "$run_dir/rom/"
    cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
    if [[ "$run" == control ]]; then
      args=(--sub-rom-read-log "$prefix.raw" --sub-rom-read-window 0,2000)
    else
      args=(--io-log "$prefix.io" --sub-snapshot "$prefix.snap" --sub-snapshot-at-fc 76569)
    fi
    "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 4800 --type-at 3600 --type ' ' "${args[@]}" --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr"
    rm -rf "$run_dir"
    trap - EXIT
  done
done
# B8 の値非公開経路を使い、関門を満たすかだけを判定する。
PYTHONPATH="$REPO/tools" python3 - "$work" 2>"$work/gate.err" <<'PY' || { echo "関門の判定に失敗" >&2; exit 1; }
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
    from b38_sub_snapshot_compare import compare, read as read_snapshot
    lines = compare(read_snapshot(w / f'{arm}-1.snap'), read_snapshot(w / f'{arm}-2.snap'))
    check(f'{arm}-runs-ram-equal', lines[-1] == 'total differ=0')
    check(f'{arm}-runs-registers-equal', all(not x.endswith(' differ') for x in lines if x.startswith('REG ')))
if not ok: raise SystemExit(1)
PY
python3 "$REPO/tools/b38_sub_snapshot_compare.py" "$work/OO-1.snap" "$work/SS-1.snap" > "$work/result"
for arm in OO SS; do
  python3 "$REPO/tools/b37_whitelist_sub_rom_reads.py" "$work/$arm-control.raw" --out "$work/$arm-control.filtered" 2>"$work/$arm-control.filter.err"
  count=$(grep -c '^W ' "$work/$arm-control.filtered" || true)
  printf 'control %s W=%s\n' "$arm" "$count" >> "$work/result"
done
cp "$work/result" "$REPO/measurements/b38-g1-sub-ram-diff.txt"
