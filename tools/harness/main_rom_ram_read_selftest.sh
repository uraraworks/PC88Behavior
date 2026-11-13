#!/usr/bin/env bash
# 自作 ROM だけを使う。値や画面は表示しない。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CORE="${Q88_MAIN_READ_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88-main-read.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
nice -n 10 make -s -C "$REPO/tools/harness/frontend"
python3 "$REPO/tools/harness/make_boundary_rom.py" "$WORK/rom" >/dev/null
python3 - "$WORK/rom" "$WORK/cross" <<'PYROM'
import pathlib, sys
src, dst = map(pathlib.Path, sys.argv[1:]); dst.mkdir()
rom = bytearray((src/'N88.ROM').read_bytes())
# RAM が 8000 番地を初期化し、ROM 最終番地の即値命令へ飛ぶ。
# 8000 はオペランドであり、データ読みではない。
code = bytes([0x3e,0xa5,0x32,0x00,0x80,0x3e,0x18,0x32,0x01,0x80,
              0x3e,0xfe,0x32,0x02,0x80,0xc3,0xff,0x7f])
rom[0x300:0x300+len(code)] = code
rom[0x7fff] = 0x3e
(dst/'N88.ROM').write_bytes(rom)
(dst/'DISK.ROM').write_bytes((src/'DISK.ROM').read_bytes())
PYROM
run() {
  "$REPO/tools/harness/frontend/q88measure" --core "$CORE" --rom-dir "$WORK/rom" --frames 30 --out "$WORK/trace" --main-rom-ram-read-log "$WORK/$1" "${@:2}" >"$WORK/stdout" 2>"$WORK/stderr" || { cat "$WORK/stderr" >&2; exit 1; }
}
run normal
"$REPO/tools/harness/frontend/q88measure" --core "$CORE" --rom-dir "$WORK/cross" --frames 30 --out "$WORK/trace" --main-rom-ram-read-log "$WORK/cross.txt" >"$WORK/stdout" 2>"$WORK/stderr"
run empty --main-rom-ram-read-window 31-40
run limited --main-rom-ram-read-limit 0
python3 - "$WORK" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
def read(name):
    s = (p/name).read_text()
    lines = s.splitlines()
    assert lines[0] == '# entry ram_address reads'
    assert re.fullmatch(r'# limit=\d+ rows=\d+ dropped_reads=\d+ unattributed_reads=\d+ saturated_reads=\d+', lines[1])
    rows = {}
    for line in lines[2:]:
        m = re.fullmatch(r'([0-9A-F]{4}) ([0-9A-F]{4}) (\d+)', line)
        assert m, line
        rows[m[1], m[2]] = int(m[3])
    return s, rows
s, rows = read('normal')
assert rows['1000', 'A800'] == 2, rows
assert all(addr != 'A900' for entry, addr in rows), rows
assert all(not 0x9000 <= int(addr,16) <= 0x9040 for entry, addr in rows), rows
assert not re.search(r'(?<![0-9A-F])(A5C3|5AE1)(?![0-9A-F])', s)
assert all(addr != '8000' for entry, addr in read('cross.txt')[1])
assert read('empty')[1] == {}
limited, rows = read('limited')
assert rows == {} and re.search(r'limit=0 rows=0 dropped_reads=[1-9]\d*', limited)
print('main ROM RAM read 自己検査 PASS')
PY
