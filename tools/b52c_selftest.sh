#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)}"
if [[ ! -f "$CORE" ]]; then echo 'B52c: コアがありません' >&2; exit 1; fi
export PC88_SUB_READ_CORE="$CORE"
export PC88_SUB_READ_CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$VENDOR/src}"
work="$(mktemp -d /tmp/b52c-selftest.XXXXXX)"; trap 'rm -rf "$work"' EXIT
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
import pathlib, sys
from b52c_diff import compare
from b38_sub_snapshot_compare import read
p = pathlib.Path(sys.argv[1]); base = bytearray(b'Q88SNAP1' + bytes(32768 + 36))
(p/'base.snap').write_bytes(base)
assert list(compare(read(p/'base.snap'), read(p/'base.snap'), 8)) == []
base[8+2] = 0x41; base[8+3] = 0x42
(p/'test.snap').write_bytes(base)
assert list(compare(read(p/'base.snap'), read(p/'test.snap'), 8)) == ['changed 4002 p0', 'changed 4003 ?']
assert list(compare(read(p/'base.snap'), read(p/'test.snap'), 256)) == ['changed 4002 p0', 'changed 4003 p171']
PY
python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" >/dev/null
"$REPO/tools/measure_b52c.sh" --work "$work/run" --dry-run-sub-rom "$work/sub/DISK.ROM" --output-dir "$work/result"
for row in 1 2 3 4 5; do
  "$work/run/front" --core "$CORE" --rom-dir "$work/run/rom-$row" --frames 2010 --disk "$work/run/a.d88" --io-log "$work/io-$row" >"$work/out-$row" 2>"$work/err-$row"
  python3 - "$work/io-$row" "$work/run/labels-$row.json" <<'PY'
import json, sys
first = json.load(open(sys.argv[2]))['labels']['_b52_first_fc']
lines = [x.split() for x in open(sys.argv[1])]
fc = [x for x in lines if len(x) >= 8 and x[3:6] == ['main', 'IN', '00FC']]
assert len(fc) == 2 and int(fc[0][7], 16) == first
PY
done
# 第231版: 公式と同じ先頭2バイトの変更を、作業域・スタックを除くRAMで検査。
PYTHONPATH="$REPO/tools" python3 - "$work/run" <<'PYTEST'
import pathlib, sys
from b38_sub_snapshot_compare import read
root = pathlib.Path(sys.argv[1])
for run in (1, 2):
    control = read(root / f'5-{run}.snap')[0]
    for row in range(1, 6):
        subject = read(root / f'{row}-{run}.snap')[0]
        address = 0x6000 if row == 3 else 0x7810
        expected = {} if row == 5 else {address: 0x41, address + 1: 0x44}
        changed = {i + 0x4000: b for i, (a, b) in enumerate(zip(control, subject))
                   if i + 0x4000 < 0x7B00 and a != b}
        assert changed == expected, (row, run)
PYTEST
cmp "$work/result/b52c-self-1.txt" "$work/result/b52c-self-2.txt"
printf 'B52c 自己検査 PASS\n'
