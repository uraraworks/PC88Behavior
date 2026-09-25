#!/usr/bin/env bash
# tools/m6fd_entry.py の自己検査。合成D88だけで完結する（公式ROM・公式ディスクは使わない）。
#
# 検査項目:
#   1. トラック18の非割り当て表セクタに置いた名前を見つけ、pos/bytes9_15が正しい。
#   2. 名前が無ければ None。
#   3. 割り当て表3セクタ(18,1,14)〜(18,1,16)に名前を置いても見つからない
#      （検索対象から除かれていることの陰性対照）。
#   4. トラック18より前に同じ名前があっても、探すのはトラック18だけ
#      （範囲外の混入を拾わないことの陰性対照）。
#   5. H=0とH=1の両方で見つかる（両ヘッドを検索することの確認）。
#
# 使い方: tools/m6fd_entry_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO" <<'PY'
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "tools"))
from make_m6fc_blank_disk import build_blank_disk  # noqa: E402
import m6fd_entry as me  # noqa: E402

rc = 0


def ok(msg):
    print(f"OK: {msg}")


def ng(msg):
    global rc
    print(f"NG: {msg}")
    rc = 1


HEADER = 32
TRACK_TABLE = 164 * 4
SECTOR_UNIT = 16 + 256
TRACK_BYTES = 16 * SECTOR_UNIT


def sector_offset(c, h, r):
    phys = c * 2 + h
    return HEADER + TRACK_TABLE + phys * TRACK_BYTES + (r - 1) * SECTOR_UNIT + 16


def patch(image, c, h, r, offset, data):
    base = bytearray(image)
    pos = sector_offset(c, h, r) + offset
    base[pos:pos + len(data)] = data
    return bytes(base)


base_img = build_blank_disk(0xFF, 0xFF)

# --- 1. 基本: (18,0,5)にQZ7Bを置き、9〜15バイト目に既知値を入れる ----------
img = base_img
name = b"QZ7B"
entry = bytearray(16)
entry[0:4] = name
entry[4:9] = b"     "
for i, off in enumerate(range(9, 16)):
    entry[off] = 30 + i
img = patch(img, 18, 0, 5, 32, bytes(entry))
result = me.entry_fields(img, name)
if (result is not None and result["pos"] == {"c": 18, "h": 0, "r": 5, "offset": 32}
        and result["bytes9_15"] == [30, 31, 32, 33, 34, 35, 36]):
    ok("基本: 位置とbytes9_15が正しい")
else:
    ng(f"基本: 期待と不一致: {result}")

# --- 2. 名前が無い ------------------------------------------------------
result_none = me.entry_fields(base_img, b"NOPE")
if result_none is None:
    ok("陰性対照: 名前が無ければNone")
else:
    ng(f"陰性対照: 名前が無いのに見つかった: {result_none}")

# --- 3. 割り当て表3セクタに置いても見つからない ------------------------------
img_fat = base_img
for r in (14, 15, 16):
    img_fat = patch(img_fat, 18, 1, r, 5, name)
result_fat = me.entry_fields(img_fat, name)
if result_fat is None:
    ok("陰性対照: 割り当て表3セクタの名前は検索対象外")
else:
    ng(f"陰性対照: 割り当て表3セクタの名前を拾ってしまった: {result_fat}")

# --- 4. トラック18以外に置いても見つからない --------------------------------
img_outside = patch(base_img, 5, 0, 3, 10, name)
result_outside = me.entry_fields(img_outside, name)
if result_outside is None:
    ok("陰性対照: トラック18以外の名前は検索対象外")
else:
    ng(f"陰性対照: トラック18以外の名前を拾ってしまった: {result_outside}")

# --- 5. H=1でも見つかる --------------------------------------------------
entry2 = bytearray(16)
entry2[0:4] = name
entry2[4:9] = b"     "
for i, off in enumerate(range(9, 16)):
    entry2[off] = 40 + i
img_h1 = patch(base_img, 18, 1, 2, 48, bytes(entry2))
result_h1 = me.entry_fields(img_h1, name)
if (result_h1 is not None and result_h1["pos"] == {"c": 18, "h": 1, "r": 2, "offset": 48}
        and result_h1["bytes9_15"] == [40, 41, 42, 43, 44, 45, 46]):
    ok("H=1のセクタでも見つかる")
else:
    ng(f"H=1: 期待と不一致: {result_h1}")

print()
if rc == 0:
    print("全項目 OK")
else:
    print("NG あり")
sys.exit(rc)
PY
exit $?
