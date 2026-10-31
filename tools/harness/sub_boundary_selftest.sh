#!/usr/bin/env bash
# 自作 ROM だけを使うサブ境界の陽性・陰性対照。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_BOUNDARY_CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1)}"
CORE_SRC="${PC88_SUB_BOUNDARY_CORE_SRC:-$VENDOR/src}"
[ -n "$CORE" ] || { echo "コア成果物がありません" >&2; exit 1; }
mkdir -p "$REPO/tmp/b15-work"
WORK="$(mktemp -d "$REPO/tmp/b15-work/subtest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
FRONT="$WORK/q88measure"
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$CORE_SRC/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$FRONT"
python3 "$REPO/tools/harness/make_sub_boundary_rom.py" "$WORK/rom"
for mode in off on; do
  if [ "$mode" = on ]; then
    set -- --sub-boundary-log "$WORK/log"
  else
    set --
  fi
  "$FRONT" --core "$CORE" --rom-dir "$WORK/rom" --frames 20 --sub-cpu-mode 2 --out "$WORK/$mode" --boundary-log "$WORK/main-$mode" "$@" >"$WORK/stdout-$mode" 2>"$WORK/stderr-$mode"
done
cmp "$WORK/off" "$WORK/on"
cmp "$WORK/main-off" "$WORK/main-on"
python3 - "$WORK/log" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
lines = text.splitlines()
a = {x[1]: tuple(map(int, x[2:])) for x in (line.split() for line in lines) if x[0] == 'A'}
w = {(x[1], x[2]): int(x[3]) for x in (line.split() for line in lines) if x[0] == 'W'}
assert a == {'0100': (2, 2, 0, 0, 2), '0150': (1, 0, 1, 0, 0)}, a
assert w.get(('5000', 'ram')) == 1 and w.get(('5001', 'rom')) == 2, w
assert all(re.fullmatch(r'(?:A [0-9A-F]{4}(?: [0-9]+){5}|W [0-9A-F]{4} (?:rom|ram) [0-9]+)', line) for line in lines)
assert not re.search(r'(?<![0-9A-Za-z])(?:A5C3|A5)(?![0-9A-Za-z])', text)
PY
python3 "$REPO/tools/b15_whitelist_sub_boundary.py" --selftest
python3 "$REPO/tools/b15_whitelist_sub_boundary.py" "$WORK/log" --id G1 --rom self --out "$WORK/filtered"
echo 'サブ境界自己検査 PASS（陽性・陰性・値非出力・無効時比較）'
