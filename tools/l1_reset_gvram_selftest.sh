#!/usr/bin/env bash
# 自作ROMで描画・リセット後の3面を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
core="$(find_l3_core)"
[ -n "$core" ] || { echo 'FAIL: コアがありません' >&2; exit 1; }
ensure_l3_frontend
python3 "$REPO/src/build_main_rom.py" "$WORK/rom" >"$WORK/build.log" 2>&1 || { grep -i error "$WORK/build.log" >&2 || true; exit 1; }
cp -R "$WORK/rom" "$WORK/fault"
# 署名が一致しても消去を飛ばす。ROMの他の箇所は変更しない。
python3 - "$WORK/fault/N88.ROM" <<'PY'
import sys
p = sys.argv[1]
b = bytearray(open(p, 'rb').read())
pattern = bytes.fromhex('3a 2c f2 fe a5 20')
i = b.find(pattern)
assert i >= 0 and b.find(pattern, i + 1) < 0
b[i + 5] = 0x18
open(p, 'wb').write(b)
PY
run() {
  local rom="$1" dump="$2" reset="$3"
  local args=()
  [ "$reset" = yes ] && args=(--reset-at 1800)
  "$REPO/tools/harness/frontend/q88measure" --core "$core" --rom-dir "$rom" \
    --frames 2102 --type-at 300 --type '\n' --type-at 700 \
    --type 'screen 0,0:line(0,0)-(639,199),7,bf\n' \
    ${args[@]+"${args[@]}"} --gvram-dump "$dump" --gvram-dump-at 2100 \
    --out "$WORK/trace" >"$WORK/stdout" 2>"$WORK/stderr"
}
run "$WORK/rom" "$WORK/before" no
run "$WORK/rom" "$WORK/after" yes
run "$WORK/fault" "$WORK/fault-after" yes
python3 - "$WORK/before" "$WORK/after" "$WORK/fault-after" <<'PY'
import pathlib, sys
before, after, fault = (pathlib.Path(p).read_bytes() for p in sys.argv[1:])
assert all(len(b) == 0xc000 for b in (before, after, fault))
assert all(any(before[i:i+0x4000]) for i in range(0, 0xc000, 0x4000)), '描画失敗'
assert not any(after), 'リセット後のVRAMが非ゼロ'
assert any(fault), '陰性対照を検出できない'
print('PASS: 描画・リセット後の3面消去、陰性対照')
PY
