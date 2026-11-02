#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d /tmp/b70-selftest.XXXXXX)"; trap 'rm -rf "$work"' EXIT
export PC88_SUB_READ_CORE="${PC88_SUB_READ_CORE:-$REPO/tmp/b62-core/core/quasi88_libretro.dylib}"
export PC88_SUB_READ_CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$REPO/tmp/b62-core/core/src}"
python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" >/dev/null
PC88_B70_WORK="$work/measure" bash "$REPO/tools/measure_b70.sh" --dry-run-sub-rom "$work/sub/DISK.ROM" --output-dir "$work/results"
python3 - "$work" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
requests = ([14,1,1,2,3,0x60,0], [14,2,1,5,3,0x60,0], [14,1,1,2,3,0x60,0], [14,1,1,2,3,0x60,0], [14,1,0,2,3,0x60,0])
for row, request in enumerate(requests, 1):
    lines = (p / f'measure/S-{row}-row-1.first.io').read_text().splitlines()
    values = [int(f[6], 16) for line in lines if len(f := line.split()) == 8 and f[3:6] == ['main', 'OUT', '00FD']]
    assert values[:10] == [0, 0x17, 1 if row == 3 else 15, *request]
    assert f'row {row} S ' in (p / 'results/b70-sub-request-0e-drive2.txt').read_text()
print(next(line for line in (p / 'results/b70-sub-request-0e-drive2.txt').read_text().splitlines() if line.startswith('row 1 S reply=')))
PY
printf 'B70 自己検査 PASS\n'
