#!/usr/bin/env bash
# l4-s1h 事前登録「器具の自己検査」節: 単一HOLD中の多数写しの自己検査
# （公式ROM不要）。
#
# l4-s1hのQ1は、1つの --key-matrix HOLD（長押し）の最中に複数回
# --vram-dump で覗く、という新しい使い方をする。既存の
# tools/harness/vram_dump_dynamic_selftest.sh（毎フレーム変わるカウンタROM
# で複数写しの整合性を確認）と tools/harness/key_matrix_selftest.sh
# （--key-matrixの押下区間を確認）は、それぞれ単独では検査済みだが、
# 「押しっぱなし中に複数回写しを取る」の組み合わせはどちらも検査して
# いない。本スクリプトはその組み合わせだけを追加で検査する。
#
# 自作カウンタROM（vram_dump_dynamic_selftest.shと同じ設計、バイト列は
# すべて自分で選んだ定数）を使い、20フレームの --key-matrix HOLD の
# 最中に2回、直前・直後に1回ずつ計4回 --vram-dump を取る。カウンタの値
# （F3C8）がフレーム差どおりに単調増加していれば、キー押しっぱなしの
# 最中に複数回写しを取ってもコアの実行・書き込みが乱れないと言える。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-s1h-multidump.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"

make -s -C "$FRONTEND_DIR"

# --- カウンタROM(vram_dump_dynamic_selftest.shと同じ設計) -----------------
mkdir -p "$WORK/rom"
python3 - "$WORK/rom" <<'PYEOF'
import sys
from pathlib import Path

SETUP, ENTRY = 0x1200, 0x1234
COUNTER = 0xC010
VRAM_CELL = 0xF3C8
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

# --- 20フレームHOLD中に2回、前後に1回ずつ、計4回の写しを取る ---------------
# キー自体(04:1='Q')はカウンタROMには何の意味も無い(ただの押しっぱなし)。
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 200 \
  --key-matrix 0x04:1:100:20 \
  --vram-dump "$WORK/d0.bin" --vram-dump-at 90 \
  --vram-dump "$WORK/d1.bin" --vram-dump-at 105 \
  --vram-dump "$WORK/d2.bin" --vram-dump-at 115 \
  --vram-dump "$WORK/d3.bin" --vram-dump-at 140 \
  >"$WORK/stdout.txt" 2>"$WORK/stderr.txt" \
  || ng "HOLD中複数写しの実行が失敗した"

# 写しが2枚以上のときファイル名へフレーム番号が差し込まれる規則
# (vram_dump_path_for、main.c 799行)があるため、実際のパスは標準エラーの
# 「VRAM写しを書き出した: <path> (frame=N)」から拾う。
mapfile_paths=()
while IFS= read -r p; do mapfile_paths+=("$p"); done < <(grep -o 'VRAM写しを書き出した: [^ ]*' "$WORK/stderr.txt" | sed 's/^VRAM写しを書き出した: //')
[ "${#mapfile_paths[@]}" -eq 4 ] || ng "写しが4枚そろっていない(${#mapfile_paths[@]}枚)"
for f in "${mapfile_paths[@]}"; do
  [ -f "$f" ] || ng "写し $f が作られていない"
done

python3 - "${mapfile_paths[@]}" <<'PYEOF' \
  || ng "HOLD中の複数写しでカウンタが単調増加していない(器具の疑いあり)"
import sys
paths = sys.argv[1:]
frames = [90, 105, 115, 140]
vals = [open(p, "rb").read()[0] for p in paths]
for i in range(len(frames) - 1):
    expected = (frames[i + 1] - frames[i]) % 256
    actual = (vals[i + 1] - vals[i]) % 256
    assert expected == actual, f"mismatch at {i}: expected {expected} actual {actual}"
PYEOF
ok "HOLD中(20フレーム、押下は frame100-119)に2回・前後に1回ずつ計4回の写しを取り、カウンタが単調増加していることを確認"
ok "全項目合格"
