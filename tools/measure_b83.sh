#!/usr/bin/env bash
# B83: B82の散らばった違いが、公式どうしでも打鍵を1フレームずらすだけで出る型かを対照として測る。
# 生記録は作業場に留め、比較結果だけをmeasurements/b83-g1-timing-sensitivity.txtへ書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B83_WORK:?}"
[[ ! -e "$PC88_B83_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B83_WORK"
work="$(cd "$PC88_B83_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B83_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
printf 'build\n' >"$work/progress"
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B83_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" arm="$3" d="$4" prefix="$work/$1" run_dir="$work/run-$1" rc=0
  local frame n=0 key
  local -a keys=(--key-hold 60 --type-at $((3600+d)) --type ' ') sequence=()
  case "$arm" in
    I1|I2|I3) keys+=(--key-at $((7200+d)) --key RETROK_i) ;;
    S1) keys+=(--key-at $((7200+d)) --key RETROK_s) ;;
    F1) keys+=(--key-at $((7200+d)) --key RETROK_F1) ;;
  esac
  case "$arm" in
    I1|S1|F1) sequence=(RETROK_RETURN RETROK_SPACE) ;;
    I2) sequence=(RETROK_{1..9} RETROK_0) ;;
    I3) sequence=(RETROK_ESCAPE RETROK_F{1..5}) ;;
  esac
  for ((frame=12000; frame<108000; frame+=2400)); do
    key="${sequence[n % ${#sequence[@]}]}"
    keys+=(--key-at "$((frame+d))" --key "$key")
    ((n+=1))
  done
  printf '%s\n' "$name" >"$work/progress"
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --insert-disk2 "$run_dir/G1-1.d88" --insert-disk2-at 1 --insert-disk2-image 1 --frames 108000 "${keys[@]}" --frame-hash-every 600 --frame-hash-log "$prefix.fh" --sub-reg-log "$prefix.reg" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  return "$rc"
}
for arm in I1 S1 F1; do
  run_one "$arm-OO-1" "$PC88_REF_ROM_DIR" "$arm" 0
  run_one "$arm-OO-K1" "$PC88_REF_ROM_DIR" "$arm" 1
  run_one "$arm-SS-1" "$work/self" "$arm" 0
done
printf 'compare\n' >"$work/progress"
python3 - "$work" <<'PY'
import pathlib, re, sys
w = pathlib.Path(sys.argv[1])
def parse(name):
    lines = (w / (name + '.fh')).read_text().splitlines()
    ms = [re.fullmatch(r'(\d+) ([0-9a-f]{64})', x) for x in lines]
    if len(ms) != 180 or any(m is None for m in ms) or [int(m[1]) for m in ms] != list(range(600, 108001, 600)):
        raise ValueError('invalid frame hash log')
    return [(int(m[1]), m[2]) for m in ms]
def diff(a, b):
    return [f for (f, x), (_, y) in zip(parse(a), parse(b)) if x != y]
def ranges(fs):
    out = []
    for f in fs:
        if out and f == out[-1][1] + 600: out[-1][1] = f
        else: out.append([f, f])
    return ' '.join(f'{a}-{b}' for a, b in out) or 'none'
def image(a, b):
    return 'same' if (w / (a + '.png')).read_bytes() == (w / (b + '.png')).read_bytes() else 'differ'
rows = []
for arm in ('I1', 'S1', 'F1'):
    for other in ('OO-K1', 'SS-1'):
        fs = diff(f'{arm}-OO-1', f'{arm}-{other}')
        longest = max((b - a) // 600 + 1 for a, b in ([[int(x) for x in r.split('-')] for r in ranges(fs).split()] if fs else [[0, -600]]))
        rows.append(f"arm {arm} vs={other} ndiff={len(fs)} longest={longest} end-image={image(f'{arm}-OO-1', f'{arm}-{other}')} ranges={ranges(fs)}")
(w / 'result').write_text('\n'.join(rows) + '\n', encoding='utf-8')
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b83-g1-timing-sensitivity.txt"
printf 'done\n' >"$work/progress"
