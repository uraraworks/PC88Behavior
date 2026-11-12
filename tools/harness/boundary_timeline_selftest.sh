#!/usr/bin/env bash
# 自作 ROM のみを使う時系列記録の検査。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CORE="${Q88_TIMELINE_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88-timeline.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
make -s -C "$REPO/tools/harness/frontend"
for variant in main int; do
  python3 "$REPO/tools/harness/make_boundary_rom.py" "$WORK/$variant" --variant "$variant" >/dev/null
done
mkdir -p "$WORK/negative"
python3 - "$REPO" "$WORK/negative" <<'PY'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location('fixture', pathlib.Path(sys.argv[1]) / 'tools/harness/make_boundary_rom.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
rom = m.build_n88('main')
rom[0x300:0x302] = b'\x18\xfe'  # RAM 内で永久ループ
p = pathlib.Path(sys.argv[2]); (p / 'N88.ROM').write_bytes(rom); (p / 'DISK.ROM').write_bytes(m.build_disk())
PY
run() {
  "$REPO/tools/harness/frontend/q88measure" --core "$CORE" --rom-dir "$WORK/$1" --frames 30 --out "$WORK/trace" --boundary-timeline "$WORK/$2" "${@:3}" >"$WORK/stdout" 2>"$WORK/stderr" || { cat "$WORK/stderr" >&2; exit 1; }
}
run main main.txt
run int int.txt
run negative negative.txt
run main limited.txt --boundary-timeline-limit 2
python3 - "$WORK" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
def rows(name):
    text = (p / name).read_text()
    result = []
    for line in text.splitlines():
        if line.startswith('#'): continue
        m = re.fullmatch(r'(\d+) (\d+) ([0-9A-F]{4}) (call|jump|int|ret|accept) (\d+)', line)
        assert m, (name, line)
        result.append((int(m[1]), int(m[2]), m[3], m[4], int(m[5])))
    assert all(a[1] < b[1] and a[0] <= b[0] for a,b in zip(result,result[1:]))
    return text, result
text, main = rows('main.txt')
calls = [r for r in main if r[2:4] == ('1000', 'call')]
assert len(calls) == 2
assert all(any(r[2:5] == ('1000', 'ret', c[4]) and r[1] > c[1] for r in main) for c in calls)
assert any(r[2:4] == ('2000', 'jump') for r in main)
itext, ints = rows('int.txt')
assert sum(r[3] == 'accept' for r in ints) >= 5
cross = [r for r in ints if r[2:4] == ('0038', 'int')]
assert len(cross) >= 5 and sum(r[3] == 'accept' for r in ints) >= len(cross)
assert any(any(r[3] == 'ret' and r[4] == c[4] for r in ints) for c in cross)
assert rows('negative.txt')[1] == []
limited, lr = rows('limited.txt')
assert len(lr) == 2 and re.search(r'^# limit reached: dropped=[1-9][0-9]*$', limited, re.M)
# フィールドの形式を限定し、データ・レジスタの欄が無いことも確認する。
assert not re.search(r'(?<![0-9A-Za-z])(A5C3|5AE1)(?![0-9A-Za-z])', text + itext)
print('boundary timeline 自己検査 PASS')
PY
