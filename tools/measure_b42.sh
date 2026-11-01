#!/usr/bin/env bash
# 生記録は作業場に留め、結果には事前登録の行だけを書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B42_WORK:?}"
[[ ! -e "$PC88_B42_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B42_WORK"
work="$(cd "$PC88_B42_WORK" && pwd)"
core="${PC88_B42_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
# 比較対象のサブROMだけを履歴から再生成する。
git -C "$REPO" show ff113bf:src/l3_service/make_subrom.py > "$work/reference.py"
python3 "$work/reference.py" "$work/reference" > "$work/reference-build.log" 2>&1
for n in none 1 8 16 24 32 48 64 128 255; do
  args=()
  [[ "$n" == none ]] || args=(--dry-run-sub-entry-delay "$n")
  TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self-$n" "${args[@]}" >"$work/build-$n.log" 2>&1
done
if cmp -s "$work/reference/DISK.ROM" "$work/self-none/DISK.ROM"; then
  echo 'baseline-rom-equal true'
else
  echo 'baseline-rom-equal false'
  exit 1
fi
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B42_CORE_SRC:-$REPO/../vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" prefix="$work/$1" run_dir="$work/run-$1"
  trap 'rm -rf "$run_dir"' RETURN
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 4800 --type-at 3600 --type ' ' --io-log "$prefix.io" --sub-reg-log "$prefix.reg" --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr"
  rm -rf "$run_dir"
  trap - RETURN
}
run_one OO-1 "$PC88_REF_ROM_DIR"
run_one OO-2 "$PC88_REF_ROM_DIR"
run_one SS-none-1 "$work/self-none"
run_one SS-none-2 "$work/self-none"
for n in 1 8 16 24 32 48 64 128 255; do run_one "SS-$n-1" "$work/self-$n"; done
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY' || { echo '関門の判定に失敗' >&2; exit 1; }
import pathlib, sys
from b8_io_values import parse_log
from b40_cross_table import read as read_reg
from b41_cross_origin import read as read_origin, render
from check_l3_screen_output import read_screen, signature
w = pathlib.Path(sys.argv[1])
def read(name):
    lines = (w / (name + '.io')).read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
    main = lines[lines.index('# main\n') + 1:lines.index('# sub\n')]
    if not any('# 取りこぼし: 0件' in x for x in main): raise ValueError('記録が不完全')
    return parse_log(lines)[('IN', '00FC', 'raw')]
def screen(name): return signature(read_screen(w / (name + '.out')))
def metrics(a,b):
    diffs = [i for i,(x,y) in enumerate(zip(a,b)) if x[0] != y[0]]
    first = diffs[0] if diffs else None
    run = 0
    if first is not None:
        while first + run < min(len(a),len(b)) and a[first+run][0] != b[first+run][0]: run += 1
    return len(diffs), first, run
ok = True
def check(name, value):
    global ok
    print(f'{name} {str(value).lower()}')
    ok &= value
for arm in ('OO', 'SS-none'):
    x,y = arm+'-1', arm+'-2'
    check(arm+'-runs-io-equal', read(x) == read(y))
    label = 'OO' if arm == 'OO' else 'SS'
    check(arm+'-runs-reg-equal', render(label, read_origin(w / (x+'.reg'))) == render(label, read_origin(w / (y+'.reg'))))
a = read('OO-1')
b = read('SS-none-1')
diff,first,run = metrics(a,b)
check('fc-diff-257', diff == 257)
check('fc-first-76570', first == 76570)
check('fc-consecutive-132', run == 132)
if not ok: raise SystemExit(1)
rows = []
for n in ('none','1','8','16','24','32','48','64','128','255'):
    name = 'SS-'+n+'-1'
    b = read(name)
    diff,first,run = metrics(a,b)
    cross = len(read_reg(w / (name+'.reg')))
    same = 'same' if screen('OO-1') == screen(name) else 'differ'
    rows.append(f'row {n} fc-diff={diff} first={first if first is not None else "none"} run={run} left={len(a)} right={len(b)} cross={cross} screen={same}')
(w / 'result').write_text('\n'.join(rows)+'\n', encoding='utf-8')
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b42-g1-sub-entry-delay.txt"
