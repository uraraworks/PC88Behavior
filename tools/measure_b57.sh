#!/usr/bin/env bash
# 生記録と画像は作業場に留め、結果には事前登録の行だけを書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B57_WORK:?}"
[[ ! -e "$PC88_B57_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B57_WORK"
work="$(cd "$PC88_B57_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B57_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B57_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
run_one() {
  local name="$1" rom="$2" arm="$3" prefix="$work/$1" run_dir="$work/run-$1"
  local frame key n=0 rc=0
  local -a keys=()
  # 3600〜27600 の21打鍵。frontend の通常上限512打鍵未満。
  for ((frame=3600; frame<28800; frame+=1200)); do
    case "$arm" in
      R) key='\n' ;; S) key=' ' ;; 1|2) key="$arm" ;; Y) key=y ;;
      M) if (( n % 2 == 0 )); then key=' '; else key='\n'; fi ;;
    esac
    keys+=(--type-at "$frame" --type "$key")
    ((n+=1))
  done
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 28800 "${keys[@]}" --sub-reg-log "$prefix.reg" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then
    printf '打鍵の無視: %s\n' "$name" >&2
    return 1
  fi
  if (( rc != 0 )); then
    printf '走行失敗: %s\n' "$name" >&2
    return "$rc"
  fi
}
for arm in R S 1 2 Y M; do
  run_one "$arm-OO-1" "$PC88_REF_ROM_DIR" "$arm"
  run_one "$arm-OO-2" "$PC88_REF_ROM_DIR" "$arm"
  run_one "$arm-SS-1" "$work/self" "$arm"
done
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
import contextlib
import io
import pathlib
import sys
from b39_sub_reg_compare import read
from check_l3_screen_output import compare_rows, read_screen

w = pathlib.Path(sys.argv[1])
def image(a, b):
    return (w / (a + '.png')).read_bytes() == (w / (b + '.png')).read_bytes()
def screen(a, b):
    with contextlib.redirect_stdout(io.StringIO()):
        return compare_rows(read_screen(w / (a + '.out')), read_screen(w / (b + '.out')))
def label(value):
    return 'same' if value else 'differ'
rows = []
for arm in ('R', 'S', '1', '2', 'Y', 'M'):
    oo1, oo2, ss1 = (f'{arm}-{x}' for x in ('OO-1', 'OO-2', 'SS-1'))
    a, b = read(w / (oo1 + '.reg')), read(w / (ss1 + '.reg'))
    first = next((i for i, (x, y) in enumerate(zip(a['C'], b['C'])) if x[6] != y[6]), 'none')
    rows.append(f"arm {arm} oo={label(image(oo1, oo2))} image={label(image(oo1, ss1))} text={label(screen(oo1, ss1))} cross={len(a['C'])} {len(b['C'])} fc={len(a['F'])} {len(b['F'])} first-cross-pc={first}")
    for name in (oo1, oo2, ss1):
        (w / (name + '.png')).unlink()
(w / 'result').write_text('\n'.join(rows) + '\n', encoding='utf-8')
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b57-g1-key-sequences.txt"
