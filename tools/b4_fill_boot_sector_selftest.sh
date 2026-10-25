#!/bin/bash
# b4_fill_boot_sector.py の自己検査（陽性・陰性対照・故障注入・OUT既存）
set -u
cd "$(dirname "$0")/.."
PY=${PY:-$(command -v python3.12 || command -v python3)}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
FAIL=0
res() { if [ "$2" = 0 ]; then echo "OK: $1"; else echo "NG: $1"; FAIL=1; fi; }

"$PY" tools/make_m6fe_disk.py "$T/fe" >/dev/null 2>&1
"$PY" tools/make_m6fi_disk.py "$T/fi" >/dev/null 2>&1
D1=$(find "$T/fe" -name D1.d88 | head -1)
AS=$(find "$T/fi" -name ascii.d88 | head -1)
[ -n "$D1" ] && [ -n "$AS" ]; res "入力媒体の生成" $?

# 独立検証（本体の関数を使わず別実装）
cat > "$T/verify.py" <<'PYEOF'
import struct, sys
a = open(sys.argv[1], 'rb').read(); b = open(sys.argv[2], 'rb').read()
v = int(sys.argv[3], 0); tool = sys.argv[4] if len(sys.argv) > 4 else None
if len(a) != len(b): sys.exit(1)
pos = 32 + 164 * 4; target = None
while pos < len(a):
    size = a[pos+14] | (a[pos+15] << 8)
    if tuple(a[pos:pos+3]) == (0, 0, 1):
        target = (pos + 16, size)
    pos += 16 + size
if target is None or target[1] != 256: sys.exit(1)
s = target[0]
for i in range(len(a)):
    if s <= i < s + 256:
        if b[i] != v: sys.exit(1)
    elif a[i] != b[i]: sys.exit(1)
PYEOF

TOOL=${TOOL:-tools/b4_fill_boot_sector.py}
for pair in "D1:$D1" "ascii:$AS"; do
  n=${pair%%:*}; f=${pair#*:}
  "$PY" "$TOOL" "$f" "$T/$n.out" --fill 0xC9 >"$T/$n.log" 2>&1; rc=$?
  res "$n 実行成功" $rc
  "$PY" "$T/verify.py" "$f" "$T/$n.out" 0xC9; res "$n 陽性: (0,0,1)全C9・他不変" $?
done

# 陰性対照: (0,0,1) を (0,0,2) に書き換えた媒体
"$PY" - "$D1" "$T/nob.d88" <<'PYEOF'
import sys
a = bytearray(open(sys.argv[1], 'rb').read()); pos = 32 + 164*4
while pos < len(a):
    if tuple(a[pos:pos+3]) == (0, 0, 1): a[pos+2] = 99
    pos += 16 + (a[pos+14] | (a[pos+15] << 8))
open(sys.argv[2], 'wb').write(a)
PYEOF
"$PY" "$TOOL" "$T/nob.d88" "$T/nob.out" --fill 0xC9 >/dev/null 2>&1
[ $? -ne 0 ] && [ ! -e "$T/nob.out" ]; res "陰性対照: (0,0,1)無しは非0・OUT無し" $?

# OUT既存
: > "$T/exist.out"
"$PY" "$TOOL" "$D1" "$T/exist.out" --fill 0xC9 >/dev/null 2>&1
[ $? -ne 0 ] && [ ! -s "$T/exist.out" ]; res "OUT既存は非0・内容不変" $?

# 故障注入: 埋める位置を1セクタ(256バイト)ずらした変異体 → 検証がNGになること
sed 's/out\[start:start + 256\] = /out[start + 256:start + 512] = /; s/start <= i < start + 256/start + 256 <= i < start + 512/g' "$TOOL" > "$T/mut.py"
cmp -s "$TOOL" "$T/mut.py" && res "変異体が元と同一(注入失敗)" 1
"$PY" "$T/mut.py" "$D1" "$T/mut.out" --fill 0xC9 >/dev/null 2>&1
if [ -e "$T/mut.out" ]; then
  "$PY" "$T/verify.py" "$D1" "$T/mut.out" 0xC9; [ $? -ne 0 ]; res "故障注入: ずらし変異体は検証NG" $?
else
  res "故障注入: 変異体が出力しなかった(検証対象なし)" 1
fi

[ $FAIL = 0 ] && echo "全体: OK" || echo "全体: NG"
exit $FAIL
