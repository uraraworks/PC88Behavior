#!/usr/bin/env bash
# 境界記録は作業場に残し、結果には集計行だけを書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B61_WORK:?}"
[[ ! -e "$PC88_B61_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B61_WORK"
work="$(cd "$PC88_B61_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B61_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B61_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local arm="$1" key="$2" frames="$3" repeat="$4" rc=0
  local name="${arm}-${frames}-${repeat}" run_dir prefix
  run_dir="$work/run-$name"
  prefix="$work/$name"
  local -a keys=(--type-at 3600 --type ' ')
  if [[ "$key" != none ]]; then keys+=(--key-at 7200 --key "RETROK_$key"); fi
  mkdir -p "$run_dir/rom"
  cp -RL "$PC88_REF_ROM_DIR/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames "$frames" "${keys[@]}" --boundary-log "$prefix.boundary" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  printf '%s rc=%s\n' "$name" "$rc" >>"$work/progress"
  return "$rc"
}
for arm in none 2 i F1 ESC; do
  key="$arm"
  [[ "$arm" != ESC ]] || key=ESCAPE
  for frames in 3600 7200 7800 14400; do
    for repeat in 1 2; do
      run_one "$arm" "$key" "$frames" "$repeat"
    done
  done
done
status=0
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY' || status=$?
import pathlib
import sys
from b1_whitelist_boundary import filter_lines

work = pathlib.Path(sys.argv[1])
addresses = ('3391', '3827', '39CE', '3DED', '650F', '6B62', '7341', '7552')
ends = (3600, 7200, 7800, 14400)
intervals = ('0-3599', '3600-7199', '7200-7799', '7800-14399')
result = []
status = 0
for arm in ('none', '2', 'i', 'F1', 'ESC'):
    previous = {address: 0 for address in (*addresses, 'other')}
    for end, interval in zip(ends, intervals):
        runs = []
        for repeat in (1, 2):
            path = work / f'{arm}-{end}-{repeat}.boundary'
            lines, _, _ = filter_lines(path.read_text(encoding='utf-8', errors='replace').splitlines(), 'G1', 'official')
            counts = {address: 0 for address in (*addresses, 'other')}
            for line in lines:
                fields = line.split()
                if fields and fields[0] == 'A':
                    address = fields[1] if fields[1] in addresses else 'other'
                    counts[address] += int(fields[2])
            runs.append(counts)
        if runs[0] != runs[1]:
            status = 1
        current = runs[0]
        for address in (*addresses, 'other'):
            result.append(f'calls {arm} {address} {interval} {current[address] - previous[address]}')
        result.append(f'total {arm} {interval} {sum(current.values()) - sum(previous.values())}')
        previous = current
(work / 'result').write_text('\n'.join(result) + '\n', encoding='utf-8')
sys.exit(status)
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b61-g1-key-rom-calls.txt"
exit "$status"
