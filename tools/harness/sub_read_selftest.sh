#!/usr/bin/env bash
# 自作 ROM による読みの分類と値非出力の検査。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1)}"
CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$VENDOR/src}"
[ -n "$CORE" ] || { echo 'コア成果物がありません' >&2; exit 1; }
mkdir -p "$REPO/tmp/b34-work"
WORK="$(mktemp -d "$REPO/tmp/b34-work/subtest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$CORE_SRC/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$WORK/front"
python3 "$REPO/tools/harness/make_sub_read_rom.py" "$WORK/rom"
for mode in off on; do
  if [ "$mode" = on ]; then set -- --sub-read-log "$WORK/log"; else set --; fi
  "$WORK/front" --core "$CORE" --rom-dir "$WORK/rom" --frames 20 --sub-cpu-mode 2 --out "$WORK/$mode" --boundary-log "$WORK/main-$mode" "$@" >"$WORK/stdout-$mode" 2>"$WORK/stderr-$mode"
done
cmp "$WORK/off" "$WORK/on"
cmp "$WORK/main-off" "$WORK/main-on"
python3 - "$WORK/log" <<'PY'
import re, sys
lines = open(sys.argv[1]).read().splitlines()
assert all(re.fullmatch(r'R [0-9A-F]{4} (?:rom|unwritten|rom-written|ram-written) [0-9]+', line) for line in lines)
rows = {(x[1], x[2]): int(x[3]) for x in map(str.split, lines)}
for key in [('0100', 'rom'), ('5300', 'unwritten'), ('5100', 'rom-written'), ('5400', 'ram-written')]:
    assert rows.get(key, 0) > 0, key
assert not any(int(addr, 16) in range(0x4000, 0x4014) or addr == '5200' for addr, _ in rows)
assert not re.search(r'(?<![0-9A-Za-z])A5(?![0-9A-Za-z])', '\n'.join(lines))
PY
python3 "$REPO/tools/b34_whitelist_sub_reads.py" --selftest
python3 "$REPO/tools/b34_whitelist_sub_reads.py" "$WORK/log" --id G1 --rom self --out "$WORK/filtered"
echo 'サブ読み自己検査 PASS'
