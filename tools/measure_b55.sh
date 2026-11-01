#!/usr/bin/env bash
# 生記録は作業場に留め、結果には事前登録の行だけを書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B55_WORK:?}"
[[ ! -e "$PC88_B55_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B55_WORK"
work="$(cd "$PC88_B55_WORK" && pwd)"
core="${PC88_B55_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
# 作業ツリーから配布構成を生成する。測定はクラウド環境で行う。
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "${PC88_VENDOR_DIR:-$REPO/../vendor}/unscii/unscii-8.hex" --misaki-bdf "${PC88_VENDOR_DIR:-$REPO/../vendor}/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B55_CORE_SRC:-$REPO/../vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" prefix="$work/$1" run_dir="$work/run-$1"
  trap 'rm -rf "$run_dir"' RETURN
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 4800 --type-at 3600 --type ' ' --io-log "$prefix.io" --sub-reg-log "$prefix.reg" --sub-event-log "$prefix.event" --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr"
  rm -rf "$run_dir"
  trap - RETURN
}
run_one OO-1 "$PC88_REF_ROM_DIR"
run_one OO-2 "$PC88_REF_ROM_DIR"
run_one SS-1 "$work/self"
run_one SS-2 "$work/self"
gate_rc=0
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY' || gate_rc=$?
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
checks = []
def check(name, value):
    global ok
    checks.append(f'{name} {str(value).lower()}')
    print(checks[-1])
    ok &= value
for arm in ('OO', 'SS'):
    x,y = arm+'-1', arm+'-2'
    check(arm+'-runs-io-equal', read(x) == read(y))
    check(arm+'-runs-reg-equal', render(arm, read_origin(w / (x+'.reg'))) == render(arm, read_origin(w / (y+'.reg'))))
    check(arm+'-runs-screen-equal', screen(x) == screen(y))
a = read('OO-1')
b = read('SS-1')
check('OO-fc-count-112426', len(a) == 112426)
if not ok: raise SystemExit(1)
diff,first,run = metrics(a,b)
cross = len(read_reg(w / 'SS-1.reg'))
same = 'same' if screen('OO-1') == screen('SS-1') else 'differ'
rows = [f'row self fc-diff={diff} first={first if first is not None else "none"} run={run} left={len(a)} right={len(b)} cross={cross} screen={same}']
(w / 'result').write_text('\n'.join(rows)+'\n', encoding='utf-8')
PY
mkdir -p "$REPO/measurements"
if [[ -f "$work/result" ]]; then
  cp "$work/result" "$REPO/measurements/b55-g1-row.txt"
fi
if (( ! gate_rc )); then
  python3 "$REPO/tools/b46_sub_event_compare.py" "$work/OO-1.event" "$work/SS-1.event" >"$REPO/measurements/b55-g1-event-stream.txt" || gate_rc=$?
  python3 "$REPO/tools/b48_fc_position.py" "$work/OO-1.io" "$work/SS-1.io" >"$REPO/measurements/b55-g1-fc-position.txt" || gate_rc=$?
fi
if ((gate_rc)); then echo '関門の判定に失敗' >&2; fi
exit "$gate_rc"
