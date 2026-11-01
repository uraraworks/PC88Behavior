#!/usr/bin/env bash
# 生記録と画像は作業場に留め、結果には事前登録の行だけを書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B56_WORK:?}"
[[ ! -e "$PC88_B56_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B56_WORK"
work="$(cd "$PC88_B56_WORK" && pwd)"
core="${PC88_B56_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B56_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
# 異常終了時にも画像と走ごとの複製を消す。
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
run_one() {
  local name="$1" rom="$2" frames="$3" key="$4" prefix="$work/$1" run_dir="$work/run-$1"
  local -a keys=(--type-at 3600 --type "$key")
  if [[ "$name" == G-* ]]; then keys+=(--type-at 7200 --type "$key"); fi
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames "$frames" "${keys[@]}" --io-log "$prefix.io" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr"
  rm -rf "$run_dir"
}
for spec in F:7200 H:14400 I:28800 E:7200 G:14400; do
  arm="${spec%%:*}"; frames="${spec#*:}"
  case "$arm" in F|H|I) key=' ' ;; *) key=$'\n' ;; esac
  run_one "$arm-OO-1" "$PC88_REF_ROM_DIR" "$frames" "$key"
  run_one "$arm-OO-2" "$PC88_REF_ROM_DIR" "$frames" "$key"
  run_one "$arm-SS-1" "$work/self" "$frames" "$key"
  run_one "$arm-SS-2" "$work/self" "$frames" "$key"
done
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
import contextlib
import io
import pathlib
import sys
from b8_io_values import parse_log
from check_l3_screen_output import compare_rows, read_screen

w = pathlib.Path(sys.argv[1])
def fc(name):
    lines = (w / (name + '.io')).read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
    main = lines[lines.index('# main\n') + 1:lines.index('# sub\n')]
    if not any('# 取りこぼし: 0件' in x for x in main):
        raise ValueError('記録が不完全')
    return parse_log(lines)[('IN', '00FC', 'raw')]
def image(a, b):
    return (w / (a + '.png')).read_bytes() == (w / (b + '.png')).read_bytes()
def screen(a, b):
    with contextlib.redirect_stdout(io.StringIO()):
        return compare_rows(read_screen(w / (a + '.out')), read_screen(w / (b + '.out')))
def label(value):
    return 'same' if value else 'differ'
rows = []
for arm, frames in [('F', 7200), ('H', 14400), ('I', 28800), ('E', 7200), ('G', 14400)]:
    oo1, oo2, ss1, ss2 = (f'{arm}-{x}' for x in ('OO-1', 'OO-2', 'SS-1', 'SS-2'))
    oo = image(oo1, oo2)
    ss = image(ss1, ss2)
    if not oo:
        raise ValueError(f'{arm}: 公式画像が揺れるため比較できません')
    img = image(oo1, ss1)
    txt = screen(oo1, ss1)
    a, b = fc(oo1), fc(ss1)
    diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x[0] != y[0]]
    first = diffs[0] if diffs else 'none'
    rows.append(f'arm {arm} frames={frames} image={label(img)} text={label(txt)} fc-diff={len(diffs)} first={first} left={len(a)} right={len(b)} oo={label(oo)} ss={label(ss)}')
    for name in (oo1, oo2, ss1, ss2):
        (w / (name + '.png')).unlink()
(w / 'result').write_text('\n'.join(rows) + '\n', encoding='utf-8')
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b56-g1-later-frames.txt"
