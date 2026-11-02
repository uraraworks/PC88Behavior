#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d /tmp/b68-selftest.XXXXXX)"; trap 'rm -rf "$work"' EXIT
export PC88_SUB_READ_CORE="${PC88_SUB_READ_CORE:-$REPO/tmp/b62-core/core/quasi88_libretro.dylib}"
export PC88_SUB_READ_CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$REPO/tmp/b62-core/core/src}"
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
import json, pathlib, sys
from analyze_b68 import fc_info, fdc, ram_lines, reply_count
p=pathlib.Path(sys.argv[1]); base=bytearray(b'Q88SNAP1'+bytes(32768+36))
(p/'base').write_bytes(base)
test=bytearray(base); test[8+4:8+8]=bytes([0xa1,2,1,3]); test[8+12]=0xee
(p/'test').write_bytes(test)
assert list(ram_lines(p/'base',p/'test',1)) == ['row 1 ram 4004-4007 2/1/3+0','row 1 ram 400C-400C ?']
assert list(ram_lines(p/'base',p/'base',8)) == []
assert fdc([('OUT',0xfb,x,0) for x in [15,0,2,8]]) == 'seek(0,2);sense_interrupt()'
try:
    fdc([('OUT',0xfb,15,0)])
    raise AssertionError('incomplete')
except ValueError:
    pass
(p/'labels').write_text(json.dumps({'labels':{'_b68_first_fc':0x1234}}))
(p/'io').write_text('# main\n1 0 0 main IN 00FC AB 1000\n2 0 0 main IN 00FC CD 1001\n3 0 0 main IN 00FC EF 1234\n4 0 0 main IN 00FC 00 1235\n# 取りこぼし: 0件 / 総イベント数: 4件\n# sub\n# 取りこぼし: 0件 / 総イベント数: 0件\n')
assert reply_count(p/'io',p/'labels') == 2
assert fc_info(p/'io',p/'labels') == (2, 2, 4)
(p/'timeout').write_text('# main\n# 取りこぼし: 0件 / 総イベント数: 0件\n')
assert fc_info(p/'timeout',p/'labels') == (0, -1, 0)
(p/'io').write_text((p/'io').read_text().replace('0件 / 総イベント数: 4件','1件 / 総イベント数: 4件'))
try:
    reply_count(p/'io',p/'labels')
    raise AssertionError('drop')
except ValueError:
    pass
PY
python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" >/dev/null
python3 "$REPO/tools/make_l3_testdisk.py" "$work/a.d88" --cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xA1 >/dev/null
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$PC88_SUB_READ_CORE_SRC/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front"
for row in {1..8}; do
  python3 "$REPO/src/build_main_rom.py" "$work/rom-$row" --inject-b68-row "$row" --labels-out "$work/labels-$row" >"$work/build-$row" 2>&1
  cp "$work/sub/DISK.ROM" "$work/rom-$row/DISK.ROM"
  /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$work/front" --core "$PC88_SUB_READ_CORE" --rom-dir "$work/rom-$row" --frames 2010 --disk "$work/a.d88" --io-log "$work/io-$row" >"$work/out-$row" 2>"$work/err-$row"
  python3 - "$work/io-$row" "$row" <<'PYCODE'
import sys
rows = ([14,1,0,2,3,0x60,0],[14,2,0,2,3,0x60,0],[14,1,1,2,3,0x60,0],[14,1,0,5,3,0x60,0],[14,1,0,2,7,0x60,0],[14,1,0,2,3,0x70,0],[14,1,0,2,3,0x60,0x80],[])
values=[]
for line in open(sys.argv[1]):
    f=line.split()
    if len(f)==8 and f[3:6]==['main','OUT','00FD']:
        values.append(int(f[6],16))
row=int(sys.argv[2]); assert values[:3]==[0,0x17,15]
assert values[3:3+len(rows[row-1])]==rows[row-1]
PYCODE
done
export PC88_B68_WORK="$work/measure"
export PC88_REF_ROM_DIR="$work/sub"
export PC88_B68_OUTPUT_DIR="$work/results"
bash "$REPO/tools/measure_b68.sh"
for run in 1 2; do
  for row in {1..8}; do
    test -s "$work/measure/$row-$run.first.io"
    test -s "$work/measure/$row-$run.io"
    read -r target count < <(python3 "$REPO/tools/analyze_b68.py" "$row" "$work/measure/$row-$run.first.io" /dev/null /dev/null "$work/measure/labels-$row.json" --fc-info)
    if [[ "$target" == -1 ]]; then
      test ! -e "$work/measure/$row-$run.snap"
      ! grep -q "^row $row ram " "$work/results/b68-official-$run.txt"
    else
      test -s "$work/measure/$row-$run.snap"
    fi
  done
done
test -s "$work/measure/8-1.snap"
test -s "$work/measure/8-2.snap"
printf 'B68 自己検査 PASS\n' 
