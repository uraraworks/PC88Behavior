#!/usr/bin/env bash
# テキストVRAMの写し（M7器具1、--vram-dump/--vram-dump-at）の自己検査、その2。
#
# vram_dump_selftest.sh は起動直後に一度だけ書かれ、以後変わらない内容
# （L1のfont_sample）でしか写しを試していない。それだけでは「毎回同じ内容を
# 返す壊れた器具」でも見た目上は合格してしまう穴がある（M7段階1の予備走
# l4-s1a の診断で、この穴を塞ぐ必要が明らかになった）。
#
# ここでは毎フレーム変わる内容（VSYNC割り込みのたびに8bitカウンタを1増やし、
# その場でF3C8（row0=0,col0=0）へ書く自作ROM）を使い、複数フレームで写しを
# 取って「そのフレームに対応する値」であること（単調に増え、フレーム差と
# 値の差が一致すること）を確かめる。IM1→RST 0038h・レベル毎回再アームの
# 手順は tools/harness/make_test_rom.py の --enable-int（intlog_selftest.sh用）
# で既に実測・確認済みの通り（このコアの割り込みコントローラは受理のたびに
# レベルを0へ戻すので、毎回OUT[E4]で再アームしないと2回目以降が受理され
# ない——PC-8801のハード仕様であってROMの内容とは無関係）。
#
# 故障注入: 「常に同じ時点の写しを返す壊れた器具」を模して、後のフレーム
# 用の写しとして実際には前のフレームの写しを渡し、本検査の一致判定が
# NGになることを確認する（陰性対照）。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-vramdumpdyn.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"

make -s -C "$FRONTEND_DIR"

# --- 自作カウンタROMを組む（バイト列は全て自分で選んだ定数） -------------
mkdir -p "$WORK/rom"
python3 - "$WORK/rom" <<'PYEOF'
import sys
from pathlib import Path

SETUP, ENTRY = 0x1200, 0x1234
COUNTER = 0xC010
VRAM_CELL = 0xF3C8          # row0=0,col0=0
INT_LEVEL_PORT, INT_LEVEL_VAL = 0xE4, 0x02
INT_MASK_PORT, INT_MASK_VAL = 0xE6, 0x02
N88_SIZE, DISK_SIZE, FILL = 0x8000, 0x0800, 0x00


def lo(v): return v & 0xFF
def hi(v): return (v >> 8) & 0xFF


rom = bytearray([FILL] * N88_SIZE)
rom[0x0000:0x0003] = bytes([0xC3, lo(SETUP), hi(SETUP)])
setup = bytes([0xAF, 0x32, lo(COUNTER), hi(COUNTER), 0xC3, lo(ENTRY), hi(ENTRY)])
rom[SETUP:SETUP + len(setup)] = setup
prog = bytes([
    0x31, 0xFF, 0xFF,
    0x3E, INT_LEVEL_VAL, 0xD3, INT_LEVEL_PORT,
    0x3E, INT_MASK_VAL, 0xD3, INT_MASK_PORT,
    0xED, 0x56, 0xFB,
    0x76, 0x18, 0xFD,
])
rom[ENTRY:ENTRY + len(prog)] = prog
vector = bytes([
    0x3A, lo(COUNTER), hi(COUNTER), 0x3C,
    0x32, lo(COUNTER), hi(COUNTER),
    0x32, lo(VRAM_CELL), hi(VRAM_CELL),
    0x3E, INT_LEVEL_VAL, 0xD3, INT_LEVEL_PORT,
    0xFB, 0xC9,
])
rom[0x0038:0x0038 + len(vector)] = vector

d = Path(sys.argv[1])
(d / "N88.ROM").write_bytes(rom)
(d / "DISK.ROM").write_bytes(bytes([0x76] + [FILL] * (DISK_SIZE - 1)))
PYEOF
ok "毎フレーム変わるカウンタROMを自作の規則から生成(N88.ROM/DISK.ROM)"

# --- 陽性: 3フレーム(20/60/120)で写しを取り、F3C8の値の差がフレーム差と一致 ---
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 121 \
  --vram-dump "$WORK/pos.bin" --vram-dump-at 20 \
  --vram-dump "$WORK/pos.bin" --vram-dump-at 60 \
  --vram-dump "$WORK/pos.bin" --vram-dump-at 120 \
  --out "$WORK/pos.report.txt" \
  >"$WORK/pos.stdout" 2>"$WORK/pos.stderr" \
  || ng "陽性対照の実行が失敗した"

for f in 000020 000060 000120; do
  [ -f "$WORK/pos.f$f.bin" ] || ng "写し pos.f$f.bin が作られていない"
done

python3 - "$WORK/pos.f000020.bin" "$WORK/pos.f000060.bin" "$WORK/pos.f000120.bin" <<'PYEOF' \
  || ng "写しの値がフレーム差どおりに単調増加していない(器具の疑いあり)"
import sys
paths = sys.argv[1:]
frames = [20, 60, 120]
vals = [open(p, "rb").read()[0] for p in paths]  # F3C8 = 写しの先頭バイト
for i in range(len(frames) - 1):
    expected = (frames[i + 1] - frames[i]) % 256
    actual = (vals[i + 1] - vals[i]) % 256
    assert expected == actual, "mismatch"
PYEOF
ok "写し3枚(frame=20/60/120)のF3C8値が、フレーム差ぶんだけ単調に増えていることを確認"

# --- 故障注入: 「常に同じ時点の写しを返す壊れた器具」を模す(陰性対照) ------
# frame=120用の写しとして、実際にはframe=60の写し(pos.f000060.bin)を渡す。
set +e
python3 - "$WORK/pos.f000020.bin" "$WORK/pos.f000060.bin" "$WORK/pos.f000060.bin" <<'PYEOF'
import sys
paths = sys.argv[1:]
frames = [20, 60, 120]
vals = [open(p, "rb").read()[0] for p in paths]
for i in range(len(frames) - 1):
    expected = (frames[i + 1] - frames[i]) % 256
    actual = (vals[i + 1] - vals[i]) % 256
    if expected != actual:
        sys.exit(1)
sys.exit(0)
PYEOF
fault_rc=$?
set -e
[ "$fault_rc" -ne 0 ] || ng "故障注入(常に同じ時点の写し)後も一致してしまい、検査が検出できていない"
ok "故障注入(常に同じ時点の写しを返す壊れた器具)により不一致を検出できることを確認(陰性対照)"

ok "全項目合格"
