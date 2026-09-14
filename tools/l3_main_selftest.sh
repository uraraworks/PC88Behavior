#!/usr/bin/env bash
# tools/l3_main_selftest.sh — M7段階2a: 自作main ROM(N88.ROM)がディスク無しで
# 自作バナー→Ok→カーソル表示まで出すことの自己検査。**公式ROMは要らない**
# （L1適合の比較先だけ、既にリポジトリにある測定記録
# measurements/l1-boot-io.iolog.txt.gz を使う。これは verify_l1.sh と同じ扱い）。
#
# 組み立て: src/build_main_rom.py（src/l1_ipl/make_ipl_rom.py の発行命令(L1)
# + src/l3_main/screen.asm(画面出力) を tools/asm/z80text.py で1本に組む）。
#
# 検査:
#   1. バナー行・Ok行が期待の行・桁に出ている（docs/spec/l3-main.md 第2節の
#      番地の式どおり）。自作ROMの画面内容なので本文を見てよい
#      （CLAUDE.md 禁止事項7の対象は公式ROM/測定の画面本文）。
#   2. 属性域が既定の並び（この実装が選んだ全ゼロ、src/l3_main/screen.asm
#      冒頭コメント参照）になっている。
#   3. スクロール: 表示行数を超える出力（--extra-lines）で、120×19=2280バイトの
#      書き写し＋末尾120バイトの再クリアが1つの連続書き込み(2400バイト)として
#      F3C8起点で複数回観測される（docs/spec/l3-main.md 第5節）。
#   4. L1適合（tools/verify_l1.sh と同じ判定、tools/cmp_io.py --init 350 --cycle 7）。
#   5. 故障注入: 番地の式を1バイトずらした変種（--inject-address-fault）では
#      検査1が確実に落ちることを確かめる（検出力の陰性対照）。
#
# 使い方: tools/l3_main_selftest.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
BASE_IOLOG="$REPO/measurements/l1-boot-io.iolog.txt.gz"
BUILD="$REPO/src/build_main_rom.py"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
fail() { echo "NG: $1" >&2; FAILED=1; }

FAILED=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi
make -s -C "$REPO/tools/harness/frontend" || exit 1
if [ ! -f "$BASE_IOLOG" ]; then
  echo "基準の測定記録が無い: $BASE_IOLOG" >&2; exit 1
fi

# -----------------------------------------------------------------------
say "1. 通常ビルド（extra-lines=0）"
NORMAL_ROM="$WORK/rom_normal"
python3 "$BUILD" "$NORMAL_ROM" >"$WORK/build_normal.txt" 2>&1 || { fail "build_main_rom.py(通常)が失敗"; cat "$WORK/build_normal.txt" >&2; }
cat "$WORK/build_normal.txt"

say "2. バナー・Ok・属性域の検査（VRAM写し）"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 90 \
    --vram-dump "$WORK/normal.vram.bin" --vram-dump-at 89 \
    >"$WORK/normal.stdout.txt" 2>"$WORK/normal.stderr.txt"
if [ $? -ne 0 ]; then
  fail "q88measure(通常)が失敗"; cat "$WORK/normal.stderr.txt" >&2
fi

python3 - "$WORK/normal.vram.bin" <<'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
STRIDE = 120
COLS = 80
BANNER_LEN = len("PC88Behavior v0.1")  # src/l3_main/screen.asm BANNER_TXT と同じ(自作文言)
OK_LEN = len("Ok")                      # 同 OK_TXT

def row_text(row):
    base = row * STRIDE
    return data[base:base + COLS]

def row_attr(row):
    base = row * STRIDE + COLS
    return data[base:base + 40]

ok = True

t0 = row_text(0)
if t0[0] == 0x20:
    print("NG: バナー行(row0)がcol0から始まっていない"); ok = False
if any(b == 0x20 for b in t0[:1]) is False and t0[BANNER_LEN] != 0x20:
    print("NG: バナー行の長さがBANNER_LENと合わない"); ok = False

t1 = row_text(1)
if t1[0] == 0x20:
    print("NG: Ok行(row1)がcol0から始まっていない"); ok = False
if t1[OK_LEN] != 0x20:
    print("NG: Ok行の長さがOK_LENと合わない"); ok = False

for row in (0, 1, 5, 19):
    a = row_attr(row)
    if any(a):
        print(f"NG: row{row}の属性域が既定の並び(全ゼロ)になっていない"); ok = False

if ok:
    print("OK: バナー・Ok・属性域(既定の並び)")
else:
    sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "画面出力の検査"

# -----------------------------------------------------------------------
say "3. スクロールの検査（extra-lines=25 で20行を超えさせる）"
SCROLL_ROM="$WORK/rom_scroll"
python3 "$BUILD" "$SCROLL_ROM" --extra-lines 25 >"$WORK/build_scroll.txt" 2>&1 || { fail "build_main_rom.py(scroll)が失敗"; cat "$WORK/build_scroll.txt" >&2; }

"$FRONTEND" --core "$CORE" --rom-dir "$SCROLL_ROM" --frames 90 \
    --mem-write-log "$WORK/scroll.memlog.txt" --mem-write-range F3C8-FF80 \
    >"$WORK/scroll.stdout.txt" 2>"$WORK/scroll.stderr.txt"
if [ $? -ne 0 ]; then
  fail "q88measure(scroll)が失敗"; cat "$WORK/scroll.stderr.txt" >&2
fi

python3 - "$WORK/scroll.memlog.txt" <<'PYEOF'
import re, sys
pat = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s*$")
addrs = []
for line in open(sys.argv[1]):
    m = pat.match(line)
    if m:
        addrs.append(int(m.group(4), 16))

runs = []
start = prev = None
for a in addrs:
    if prev is None or a != prev + 1:
        if start is not None:
            runs.append(prev - start + 1)
        start = a
    prev = a
if start is not None:
    runs.append(prev - start + 1)

# 120*(ROWS-1) + 120(最終行の再クリア) = 2400 バイトの連続書き込みが
# 初期化(全画面クリア)1回 + スクロール回数ぶん、複数回現れるはず。
big = [r for r in runs if r >= 2400]
if len(big) < 2:
    print(f"NG: 2400バイト以上の連続書き込みが{len(big)}回しか無い(初期化+スクロールで2回以上のはず)")
    sys.exit(1)
print(f"OK: 2400バイト連続書き込み {len(big)} 回観測（初期化1回＋スクロール{len(big)-1}回）")
PYEOF
[ $? -ne 0 ] && fail "スクロールの検査"

# -----------------------------------------------------------------------
say "4. L1適合の検査"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 60 \
    --io-log "$WORK/normal.iolog.txt" \
    >"$WORK/normal_l1.stdout.txt" 2>"$WORK/normal_l1.stderr.txt"
if [ $? -ne 0 ]; then
  fail "q88measure(L1用)が失敗"; cat "$WORK/normal_l1.stderr.txt" >&2
fi
python3 "$REPO/tools/cmp_io.py" "$BASE_IOLOG" "$WORK/normal.iolog.txt" --init 350 --cycle 7
if [ $? -ne 0 ]; then
  fail "L1適合(cmp_io.py --init 350 --cycle 7)"
else
  echo "OK: L1適合を保っている"
fi

# -----------------------------------------------------------------------
say "5. 故障注入（番地の式を1バイトずらす。検査1が落ちることを確かめる）"
FAULT_ROM="$WORK/rom_fault"
python3 "$BUILD" "$FAULT_ROM" --inject-address-fault >"$WORK/build_fault.txt" 2>&1 || { fail "build_main_rom.py(fault)が失敗"; cat "$WORK/build_fault.txt" >&2; }

"$FRONTEND" --core "$CORE" --rom-dir "$FAULT_ROM" --frames 90 \
    --vram-dump "$WORK/fault.vram.bin" --vram-dump-at 89 \
    >"$WORK/fault.stdout.txt" 2>"$WORK/fault.stderr.txt"
if [ $? -ne 0 ]; then
  fail "q88measure(fault)が失敗"; cat "$WORK/fault.stderr.txt" >&2
fi

python3 - "$WORK/fault.vram.bin" <<'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
row0 = data[0:80]
# 故障注入(番地+1)がかかっていれば、col0は空白のまま(バナーがcol1から始まる)はず。
if row0[0] == 0x20:
    print("OK(検出力): 故障注入がかかると検査1どおりcol0が空白になり、正常判定と区別できた")
    sys.exit(0)
else:
    print("NG(検出力不足): 故障注入してもcol0が空白のままにならず、正常な場合と区別できない")
    sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "故障注入の検出力"

# -----------------------------------------------------------------------
echo
if [ "$FAILED" -eq 0 ]; then
  echo "l3_main_selftest: OK"
  exit 0
else
  echo "l3_main_selftest: NG"
  exit 1
fi
