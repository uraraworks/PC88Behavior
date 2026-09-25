#!/usr/bin/env bash
# tools/make_m6fc_blank_disk.py の自己検査。合成D88だけで完結し、公式ROM・
# 公式ディスク・private/ には一切触れない。
#
# 検査項目:
#   1. 生成物のサイズと、全80トラック×16セクタの中身が規則どおり
#      （割り当て表3セクタ=V、それ以外全部=F）。読み取りは独立した
#      tools/d88_read_sector.py の D88Reader を使う（生成器自身の内部状態は見ない）。
#   2. 同じ引数で2回生成した像のSHA-256が一致する（決定性）。
#   3. V≠Fの組で、割り当て表3セクタだけがVであること（本文検査の一部）。
#   4. 既存ファイルを上書きしない（rc=2）。
#   5. --fat-value / --filler の範囲外指定はrc=2。
#   6. 陰性対照: 割り当て表の外の1セクタ内の1バイトを壊すと検査がNGになる。
#   7. 陰性対照: 割り当て表3セクタのうち1つを別の値で塗り潰すと検査がNGになる。
#   8. 追補1: --boot-fill 省略時の生成物は、追補1より前の規則（旧生成器と同じ規則）で
#      独立に組み立てた像とSHA-256が一致する（既定の出力は変更前とバイト一致）。
#   9. 追補1: --boot-fill 指定時、(0,0,1) の256バイトすべてがその値になる。
#  10. 追補1 陰性対照: --boot-fill 指定時、(0,0,1) 以外の全セクタが
#      --boot-fill 無指定の生成物と一致する（起動用セクタ以外は変わっていない）。
#  11. --boot-fill 範囲外指定はrc=2。
#
# 使い方: tools/make_m6fc_blank_disk_selftest.sh

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEN="$REPO/tools/make_m6fc_blank_disk.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

# --- 1. 正常生成 ---------------------------------------------------------
if python3 "$GEN" "$WORK/d1.d88" --fat-value 0xAA --filler 0x55 >/dev/null 2>"$WORK/d1.err"; then
  ok "正常な引数で生成できる"
else
  ng "正常な引数で生成に失敗した: $(cat "$WORK/d1.err")"
fi

# --- 2. 決定性（G5相当） -------------------------------------------------
if python3 "$GEN" "$WORK/d2.d88" --fat-value 0xAA --filler 0x55 >/dev/null 2>"$WORK/d2.err"; then
  sha1="$(shasum -a 256 "$WORK/d1.d88" | awk '{print $1}')"
  sha2="$(shasum -a 256 "$WORK/d2.d88" | awk '{print $1}')"
  if [ "$sha1" = "$sha2" ]; then
    ok "同じ引数2回でSHA-256が一致する(決定性)"
  else
    ng "同じ引数なのにSHA-256が一致しない"
  fi
else
  ng "2回目の生成に失敗した: $(cat "$WORK/d2.err")"
fi

# --- 4. 既存ファイルを上書きしない ---------------------------------------
if python3 "$GEN" "$WORK/d1.d88" --fat-value 0x00 --filler 0x00 >/dev/null 2>"$WORK/overwrite.err"; then
  ng "既存ファイルへ上書きできてしまった"
else
  rc_ow=$?
  if [ "$rc_ow" -eq 2 ]; then
    ok "既存ファイルへの上書きをrc=2で拒否した"
  else
    ng "既存ファイルの拒否がrc=2でない(rc=$rc_ow)"
  fi
fi

# --- 5. 範囲外指定 --------------------------------------------------------
python3 "$GEN" "$WORK/bad1.d88" --fat-value 256 --filler 0x00 >/dev/null 2>"$WORK/bad1.err"
rc_bad1=$?
if [ "$rc_bad1" -eq 2 ] && [ ! -e "$WORK/bad1.d88" ]; then
  ok "--fat-value 範囲外をrc=2で拒否した"
else
  ng "--fat-value 範囲外の拒否がrc=2でない、または出力が作られた(rc=$rc_bad1)"
fi

python3 "$GEN" "$WORK/bad2.d88" --fat-value 0x00 --filler -1 >/dev/null 2>"$WORK/bad2.err"
rc_bad2=$?
if [ "$rc_bad2" -eq 2 ] && [ ! -e "$WORK/bad2.d88" ]; then
  ok "--filler 範囲外をrc=2で拒否した"
else
  ng "--filler 範囲外の拒否がrc=2でない、または出力が作られた(rc=$rc_bad2)"
fi

python3 "$GEN" "$WORK/bad3.d88" --fat-value 0x00 --filler 0x00 --boot-fill 256 \
  >/dev/null 2>"$WORK/bad3.err"
rc_bad3=$?
if [ "$rc_bad3" -eq 2 ] && [ ! -e "$WORK/bad3.d88" ]; then
  ok "--boot-fill 範囲外をrc=2で拒否した"
else
  ng "--boot-fill 範囲外の拒否がrc=2でない、または出力が作られた(rc=$rc_bad3)"
fi

# --- 8〜10. 追補1: boot-fill 省略時のバイト一致・指定時の本文・陰性対照 ---
if python3 "$GEN" "$WORK/d3.d88" --fat-value 0xAA --filler 0x55 --boot-fill 0x77 \
  >/dev/null 2>"$WORK/d3.err"; then
  ok "--boot-fill 指定で生成できる"
else
  ng "--boot-fill 指定の生成に失敗した: $(cat "$WORK/d3.err")"
fi

# --- 本文検査・陰性対照（Python、独立読み手 d88_read_sector.py を使う） ---
verify_out="$(REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import os
import pathlib
import sys

repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
from d88_read_sector import D88Error, D88Reader  # noqa: E402

CYLINDERS = 40
HEADS = 2
SECTORS_PER_TRACK = 16
ALLOC = {(18, 1, 14), (18, 1, 15), (18, 1, 16)}
HEADER = 32
TRACK_TABLE = 164 * 4
SECTOR_UNIT = 16 + 256
TRACK_BYTES = SECTORS_PER_TRACK * SECTOR_UNIT


def sector_data_offset(c: int, h: int, r: int) -> int:
    phys = c * 2 + h
    return HEADER + TRACK_TABLE + phys * TRACK_BYTES + (r - 1) * SECTOR_UNIT + 16


def verify(img: bytes, fat_value: int, filler: int):
    expected_size = HEADER + TRACK_TABLE + CYLINDERS * HEADS * TRACK_BYTES
    if len(img) != expected_size:
        return False, "size_mismatch"
    try:
        reader = D88Reader(img)
    except D88Error:
        return False, "d88_structure_error"
    v_count = 0
    for c in range(CYLINDERS):
        for h in range(HEADS):
            for r in range(1, SECTORS_PER_TRACK + 1):
                try:
                    payload = reader.read_sector(c, h, r)
                except D88Error:
                    return False, "sector_missing"
                expect_v = (c, h, r) in ALLOC
                want = bytes([fat_value if expect_v else filler]) * 256
                if payload != want:
                    return False, "content_mismatch"
                if expect_v:
                    v_count += 1
    if v_count != 3:
        return False, "v_count_mismatch"
    return True, "ok"


base = (work / "d1.d88").read_bytes()
results = {}

# 3. 正の検査。
results["positive"] = verify(base, 0xAA, 0x55)[0]

# 6. 割り当て表の外の1セクタ内の1バイトを壊す(陰性対照A)。
outside = bytearray(base)
off = sector_data_offset(0, 0, 1)  # (18,1,*)以外の適当なセクタ
outside[off] ^= 0xFF
results["corrupt_outside_detected"] = not verify(bytes(outside), 0xAA, 0x55)[0]

# 7. 割り当て表3セクタのうち1つを別の値で塗り潰す(陰性対照B)。
mismatched = bytearray(base)
off2 = sector_data_offset(18, 1, 16)
mismatched[off2:off2 + 256] = bytes([0x11]) * 256  # V=0xAAでもF=0x55でもない値
results["one_table_sector_mismatch_detected"] = not verify(bytes(mismatched), 0xAA, 0x55)[0]

bad = [k for k, v in results.items() if not v]
for k, v in results.items():
    print(f"{k}={'ok' if v else 'ng'}")
sys.exit(1 if bad else 0)
PY
)"
py_rc=$?
printf '%s\n' "$verify_out"
if [ "$py_rc" -eq 0 ]; then
  ok "本文検査・陰性対照（独立読み手ベース）がすべて通った"
else
  ng "本文検査・陰性対照のいずれかが落ちた"
fi

# --- 追補1: boot-fill のバイト一致・本文・陰性対照(独立読み手ベース) -------
boot_out="$(REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import os
import pathlib
import sys

repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
from d88_read_sector import D88Reader  # noqa: E402

CYLINDERS = 40
HEADS = 2
SECTORS_PER_TRACK = 16
ALLOC = {(18, 1, 14), (18, 1, 15), (18, 1, 16)}
BOOT = (0, 0, 1)


def independent_build(fat_value: int, filler: int) -> bytes:
    """追補1より前の規則(旧生成器と同じ)を、本自己検査の中で独立に組み立てる。
    make_m6fc_blank_disk.build_blank_disk はimportせず、d88_read_sector経由でも
    生成器そのものでもない、ヘッダ・トラック表・セクタ本体を素手で並べる版。"""
    import struct
    N_CODE = 1
    SECTOR_SIZE = 256
    DISK_DENSITY_DOUBLE = 0x00
    DISK_DELETED_FALSE = 0x00
    STATUS_NORMAL = 0x00
    DISK_PROTECT_FALSE = 0x00
    DISK_TYPE_2D = 0x00
    TRACK_COUNT = 164

    header = bytearray(32)
    header[26] = DISK_PROTECT_FALSE
    header[27] = DISK_TYPE_2D
    track_table = bytearray(TRACK_COUNT * 4)
    body = bytearray()
    offset = 32 + TRACK_COUNT * 4
    for c in range(CYLINDERS):
        for h in range(HEADS):
            trk = bytearray()
            for r in range(1, SECTORS_PER_TRACK + 1):
                hdr = bytearray(16)
                hdr[0] = c & 0xFF
                hdr[1] = h & 0xFF
                hdr[2] = r & 0xFF
                hdr[3] = N_CODE
                hdr[4] = SECTORS_PER_TRACK & 0xFF
                hdr[5] = (SECTORS_PER_TRACK >> 8) & 0xFF
                hdr[6] = DISK_DENSITY_DOUBLE
                hdr[7] = DISK_DELETED_FALSE
                hdr[8] = STATUS_NORMAL
                hdr[14] = SECTOR_SIZE & 0xFF
                hdr[15] = (SECTOR_SIZE >> 8) & 0xFF
                trk += hdr
                value = fat_value if (c, h, r) in ALLOC else filler
                trk += bytes([value]) * SECTOR_SIZE
            phys = c * 2 + h
            struct.pack_into("<I", track_table, phys * 4, offset)
            body += trk
            offset += len(trk)
    struct.pack_into("<I", header, 28, offset)
    return bytes(header) + bytes(track_table) + bytes(body)


results = {}

# 8. 既定(boot-fill省略)の生成物は、旧規則で独立に組んだ像とSHA一致する。
default_img = (work / "d1.d88").read_bytes()  # --fat-value 0xAA --filler 0x55、--boot-fill無指定
independent = independent_build(0xAA, 0x55)
results["default_matches_independent_pre_addendum1_build"] = (default_img == independent)

# 9. boot-fill指定時、(0,0,1)の256バイトすべてがその値になる。
boot_img = (work / "d3.d88").read_bytes()  # --fat-value 0xAA --filler 0x55 --boot-fill 0x77
reader = D88Reader(boot_img)
boot_payload = reader.read_sector(*BOOT)
results["boot_fill_applied"] = (boot_payload == bytes([0x77]) * 256)

# 10. 陰性対照: (0,0,1)以外の全セクタは、boot-fill無指定の生成物(=fat=0xAA/filler=0x55)と
#     一致する(起動用セクタ以外は変わっていない)。
reader_default = D88Reader(default_img)
all_other_match = True
for c in range(CYLINDERS):
    for h in range(HEADS):
        for r in range(1, SECTORS_PER_TRACK + 1):
            if (c, h, r) == BOOT:
                continue
            if reader.read_sector(c, h, r) != reader_default.read_sector(c, h, r):
                all_other_match = False
results["boot_fill_does_not_touch_other_sectors"] = all_other_match

bad = [k for k, v in results.items() if not v]
for k, v in results.items():
    print(f"{k}={'ok' if v else 'ng'}")
sys.exit(1 if bad else 0)
PY
)"
boot_rc=$?
printf '%s\n' "$boot_out"
if [ "$boot_rc" -eq 0 ]; then
  ok "追補1: boot-fillのバイト一致・本文・陰性対照がすべて通った"
else
  ng "追補1: boot-fill検査のいずれかが落ちた"
fi

# --- 追補3: --sector-fill の本文・優先順位・陰性対照・rc=2各種 -------------
if python3 "$GEN" "$WORK/d4.d88" --fat-value 0xAA --filler 0x55 \
  --sector-fill 0,0,1=0xC0 --sector-fill 5,1,7=0x33 >/dev/null 2>"$WORK/d4.err"; then
  ok "--sector-fill 複数指定で生成できる"
else
  ng "--sector-fill 複数指定の生成に失敗した: $(cat "$WORK/d4.err")"
fi

# --boot-fill と --sector-fill を同じ起動用セクタに与えた場合、sector-fillが勝つ。
if python3 "$GEN" "$WORK/d5.d88" --fat-value 0xAA --filler 0x55 --boot-fill 0x77 \
  --sector-fill 0,0,1=0xC0 >/dev/null 2>"$WORK/d5.err"; then
  ok "--boot-fill と --sector-fill(同一座標)の併用で生成できる"
else
  ng "--boot-fill と --sector-fill(同一座標)の併用に失敗した: $(cat "$WORK/d5.err")"
fi

sector_fill_out="$(REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import os
import pathlib
import sys

repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
from d88_read_sector import D88Reader  # noqa: E402

CYLINDERS = 40
HEADS = 2
SECTORS_PER_TRACK = 16
BOOT = (0, 0, 1)

results = {}

# 9. 指定セクタだけが値になっている。
d4 = D88Reader((work / "d4.d88").read_bytes())
results["sector_fill_0_0_1_applied"] = d4.read_sector(0, 0, 1) == bytes([0xC0]) * 256
results["sector_fill_5_1_7_applied"] = d4.read_sector(5, 1, 7) == bytes([0x33]) * 256

# 指定セクタ以外はboot-fill無指定・sector-fill無指定の既定生成物(d1.d88、
# --fat-value 0xAA --filler 0x55)と一致する(指定セクタだけが変わること)。
base = D88Reader((work / "d1.d88").read_bytes())
touched = {BOOT, (5, 1, 7)}
all_other_match = True
for c in range(CYLINDERS):
    for h in range(HEADS):
        for r in range(1, SECTORS_PER_TRACK + 1):
            if (c, h, r) in touched:
                continue
            if d4.read_sector(c, h, r) != base.read_sector(c, h, r):
                all_other_match = False
results["sector_fill_does_not_touch_other_sectors"] = all_other_match

# 10. 優先順位: --sector-fill が --boot-fill より勝つ(同一座標指定時)。
d5 = D88Reader((work / "d5.d88").read_bytes())
results["sector_fill_wins_over_boot_fill"] = d5.read_sector(0, 0, 1) == bytes([0xC0]) * 256

bad = [k for k, v in results.items() if not v]
for k, v in results.items():
    print(f"{k}={'ok' if v else 'ng'}")
sys.exit(1 if bad else 0)
PY
)"
sf_rc=$?
printf '%s\n' "$sector_fill_out"
if [ "$sf_rc" -eq 0 ]; then
  ok "追補3: --sector-fill の本文・優先順位がすべて通った"
else
  ng "追補3: --sector-fill 検査のいずれかが落ちた"
fi

# 既定(--sector-fill無指定)の生成物は、追補3より前の生成物(d1.d88)とバイト一致する。
sha_d1="$(shasum -a 256 "$WORK/d1.d88" | awk '{print $1}')"
python3 "$GEN" "$WORK/d6.d88" --fat-value 0xAA --filler 0x55 >/dev/null 2>"$WORK/d6.err"
sha_d6="$(shasum -a 256 "$WORK/d6.d88" | awk '{print $1}')"
if [ "$sha_d1" = "$sha_d6" ]; then
  ok "追補3: --sector-fill無指定の既定生成物は追補3より前とバイト一致する"
else
  ng "追補3: --sector-fill無指定の既定生成物がバイト一致しない"
fi

# 陰性対照: 範囲外座標・範囲外値・形式不正・重複指定・割り当て表セクタ指定は
# すべてrc=2で出力を作らない。
python3 "$GEN" "$WORK/bad4.d88" --fat-value 0x00 --filler 0x00 \
  --sector-fill 40,0,1=0xC0 >/dev/null 2>"$WORK/bad4.err"
rc_bad4=$?
if [ "$rc_bad4" -eq 2 ] && [ ! -e "$WORK/bad4.d88" ]; then
  ok "--sector-fill のC範囲外をrc=2で拒否した"
else
  ng "--sector-fill のC範囲外の拒否がrc=2でない、または出力が作られた(rc=$rc_bad4)"
fi

python3 "$GEN" "$WORK/bad5.d88" --fat-value 0x00 --filler 0x00 \
  --sector-fill 0,0,0=0xC0 >/dev/null 2>"$WORK/bad5.err"
rc_bad5=$?
if [ "$rc_bad5" -eq 2 ] && [ ! -e "$WORK/bad5.d88" ]; then
  ok "--sector-fill のR範囲外(0)をrc=2で拒否した"
else
  ng "--sector-fill のR範囲外(0)の拒否がrc=2でない、または出力が作られた(rc=$rc_bad5)"
fi

python3 "$GEN" "$WORK/bad6.d88" --fat-value 0x00 --filler 0x00 \
  --sector-fill 0,0,1=0x100 >/dev/null 2>"$WORK/bad6.err"
rc_bad6=$?
if [ "$rc_bad6" -eq 2 ] && [ ! -e "$WORK/bad6.d88" ]; then
  ok "--sector-fill の値範囲外をrc=2で拒否した"
else
  ng "--sector-fill の値範囲外の拒否がrc=2でない、または出力が作られた(rc=$rc_bad6)"
fi

python3 "$GEN" "$WORK/bad7.d88" --fat-value 0x00 --filler 0x00 \
  --sector-fill "bogus" >/dev/null 2>"$WORK/bad7.err"
rc_bad7=$?
if [ "$rc_bad7" -eq 2 ] && [ ! -e "$WORK/bad7.d88" ]; then
  ok "--sector-fill の形式不正をrc=2で拒否した"
else
  ng "--sector-fill の形式不正の拒否がrc=2でない、または出力が作られた(rc=$rc_bad7)"
fi

python3 "$GEN" "$WORK/bad8.d88" --fat-value 0x00 --filler 0x00 \
  --sector-fill 0,0,1=0xAA --sector-fill 0,0,1=0xBB >/dev/null 2>"$WORK/bad8.err"
rc_bad8=$?
if [ "$rc_bad8" -eq 2 ] && [ ! -e "$WORK/bad8.d88" ]; then
  ok "--sector-fill の座標重複をrc=2で拒否した"
else
  ng "--sector-fill の座標重複の拒否がrc=2でない、または出力が作られた(rc=$rc_bad8)"
fi

python3 "$GEN" "$WORK/bad9.d88" --fat-value 0x00 --filler 0x00 \
  --sector-fill 18,1,14=0xAA >/dev/null 2>"$WORK/bad9.err"
rc_bad9=$?
if [ "$rc_bad9" -eq 2 ] && [ ! -e "$WORK/bad9.d88" ]; then
  ok "--sector-fill の割り当て表セクタ指定をrc=2で拒否した"
else
  ng "--sector-fill の割り当て表セクタ指定の拒否がrc=2でない、または出力が作られた(rc=$rc_bad9)"
fi

# --- m6f-d: 既定(--fat-position/--boot-sector-mode無指定)はバイト一致 -----
python3 "$GEN" "$WORK/d7.d88" --fat-value 0xAA --filler 0x55 >/dev/null 2>"$WORK/d7.err"
sha_d7="$(shasum -a 256 "$WORK/d7.d88" | awk '{print $1}')"
if [ "$sha_d1" = "$sha_d7" ]; then
  ok "m6f-d: --fat-position/--boot-sector-mode無指定の既定生成物はm6f-d以前とバイト一致する"
else
  ng "m6f-d: --fat-position/--boot-sector-mode無指定の既定生成物がバイト一致しない"
fi

# --- m6f-d: --fat-position の本文・優先順位・陰性対照・rc=2各種 -----------
if python3 "$GEN" "$WORK/d8.d88" --fat-value 0xFF --filler 0xFF \
  --fat-position 5=0xAA --fat-position 200=0xBB >/dev/null 2>"$WORK/d8.err"; then
  ok "--fat-position 複数指定で生成できる"
else
  ng "--fat-position 複数指定の生成に失敗した: $(cat "$WORK/d8.err")"
fi

fat_position_out="$(REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import os
import pathlib
import sys

repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
from d88_read_sector import D88Reader  # noqa: E402

ALLOC = [(18, 1, 14), (18, 1, 15), (18, 1, 16)]

results = {}
d8 = D88Reader((work / "d8.d88").read_bytes())
ok_all = True
for coord in ALLOC:
    payload = d8.read_sector(*coord)
    if payload[5] != 0xAA or payload[200] != 0xBB:
        ok_all = False
    # 指定していない位置はfat-valueのまま。
    if payload[0] != 0xFF or payload[6] != 0xFF or payload[199] != 0xFF:
        ok_all = False
results["fat_position_applied_to_all_three_sectors"] = ok_all

# 陰性対照: 指定していない位置(例えば4)を書き換えて壊すと不一致になる検査。
tampered_ok = True
for coord in ALLOC:
    payload = bytearray(d8.read_sector(*coord))
    payload[4] = 0x11  # fat-value(0xFF)のはずの位置を壊す
    if payload[4] == 0xFF:
        tampered_ok = False
results["tamper_changes_value"] = tampered_ok

bad = [k for k, v in results.items() if not v]
for k, v in results.items():
    print(f"{k}={'ok' if v else 'ng'}")
sys.exit(1 if bad else 0)
PY
)"
fp_rc=$?
printf '%s\n' "$fat_position_out"
if [ "$fp_rc" -eq 0 ]; then
  ok "m6f-d: --fat-position の本文・陰性対照がすべて通った"
else
  ng "m6f-d: --fat-position 検査のいずれかが落ちた"
fi

python3 "$GEN" "$WORK/badfp1.d88" --fat-value 0x00 --filler 0x00 \
  --fat-position 256=0xAA >/dev/null 2>"$WORK/badfp1.err"
rc_badfp1=$?
if [ "$rc_badfp1" -eq 2 ] && [ ! -e "$WORK/badfp1.d88" ]; then
  ok "--fat-position の位置範囲外をrc=2で拒否した"
else
  ng "--fat-position の位置範囲外の拒否がrc=2でない、または出力が作られた(rc=$rc_badfp1)"
fi

python3 "$GEN" "$WORK/badfp2.d88" --fat-value 0x00 --filler 0x00 \
  --fat-position 5=0x100 >/dev/null 2>"$WORK/badfp2.err"
rc_badfp2=$?
if [ "$rc_badfp2" -eq 2 ] && [ ! -e "$WORK/badfp2.d88" ]; then
  ok "--fat-position の値範囲外をrc=2で拒否した"
else
  ng "--fat-position の値範囲外の拒否がrc=2でない、または出力が作られた(rc=$rc_badfp2)"
fi

python3 "$GEN" "$WORK/badfp3.d88" --fat-value 0x00 --filler 0x00 \
  --fat-position "bogus" >/dev/null 2>"$WORK/badfp3.err"
rc_badfp3=$?
if [ "$rc_badfp3" -eq 2 ] && [ ! -e "$WORK/badfp3.d88" ]; then
  ok "--fat-position の形式不正をrc=2で拒否した"
else
  ng "--fat-position の形式不正の拒否がrc=2でない、または出力が作られた(rc=$rc_badfp3)"
fi

python3 "$GEN" "$WORK/badfp4.d88" --fat-value 0x00 --filler 0x00 \
  --fat-position 5=0xAA --fat-position 5=0xBB >/dev/null 2>"$WORK/badfp4.err"
rc_badfp4=$?
if [ "$rc_badfp4" -eq 2 ] && [ ! -e "$WORK/badfp4.d88" ]; then
  ok "--fat-position の位置重複をrc=2で拒否した"
else
  ng "--fat-position の位置重複の拒否がrc=2でない、または出力が作られた(rc=$rc_badfp4)"
fi

# --- m6f-d: --boot-sector-mode の本文・陰性対照・rc=2各種 -----------------
for mode in missing crc deleted single; do
  if python3 "$GEN" "$WORK/bsm_$mode.d88" --fat-value 0xAA --filler 0x55 \
    --boot-sector-mode "$mode" >/dev/null 2>"$WORK/bsm_$mode.err"; then
    ok "--boot-sector-mode $mode で生成できる"
  else
    ng "--boot-sector-mode $mode の生成に失敗した: $(cat "$WORK/bsm_$mode.err")"
  fi
done

bsm_out="$(REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import os
import pathlib
import struct
import sys

repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
from d88_read_sector import D88Error, D88Reader  # noqa: E402

HEADER = 32
TRACK_TABLE_OFFSET = HEADER
TRACK_COUNT = 164


def track_offset(img: bytes, c: int, h: int) -> int:
    phys = c * 2 + h
    return struct.unpack_from("<I", img, TRACK_TABLE_OFFSET + phys * 4)[0]


def track_headers(img: bytes, c: int, h: int):
    """(0,0)トラックの各セクタヘッダ16バイトを、独立にID順で素手で読む。"""
    start = track_offset(img, c, h)
    # 次トラック(0,1)の開始位置を終端に使う。
    end = track_offset(img, c, h + 1) if h == 0 else len(img)
    pos = start
    headers = []
    while pos < end:
        hdr = img[pos:pos + 16]
        size = struct.unpack_from("<H", hdr, 14)[0]
        headers.append(hdr)
        pos += 16 + size
    return headers


results = {}

base = (work / "d1.d88").read_bytes()  # --fat-value 0xAA --filler 0x55 (既定、None相当)
base_headers = track_headers(base, 0, 0)
results["default_boot_track_has_16_sectors"] = len(base_headers) == 16

# missing: トラックが15セクタ、各ヘッダの「セクタ数」欄も15、R=1が無い、
# D88Readerでは(0,0,1)が読めない。
missing = (work / "bsm_missing.d88").read_bytes()
missing_headers = track_headers(missing, 0, 0)
results["missing_track_has_15_sectors"] = len(missing_headers) == 15
count_field_ok = all(struct.unpack_from("<H", h, 4)[0] == 15 for h in missing_headers)
results["missing_sector_count_field_is_15"] = count_field_ok
results["missing_no_r1_header"] = all(h[2] != 1 for h in missing_headers)
try:
    D88Reader(missing).read_sector(0, 0, 1)
    results["missing_read_sector_fails"] = False
except D88Error:
    results["missing_read_sector_fails"] = True

# crc/deleted/single: (0,0,1)のヘッダの該当バイトだけが変わり、他は既定と同じ。
def boot_header(img: bytes) -> bytes:
    for h in track_headers(img, 0, 0):
        if h[2] == 1:
            return h
    raise AssertionError("(0,0,1)のヘッダが見つからない")

base_boot = boot_header(base)

crc_boot = boot_header((work / "bsm_crc.d88").read_bytes())
results["crc_status_is_data_crc_error"] = crc_boot[8] == 0xB0
results["crc_other_id_fields_unchanged"] = (crc_boot[0:8] == base_boot[0:8]
                                             and crc_boot[9:16] == base_boot[9:16])

deleted_boot = boot_header((work / "bsm_deleted.d88").read_bytes())
results["deleted_flag_is_set"] = deleted_boot[7] == 0x10
results["deleted_other_id_fields_unchanged"] = (
    deleted_boot[0:7] == base_boot[0:7] and deleted_boot[8:16] == base_boot[8:16])

single_boot = boot_header((work / "bsm_single.d88").read_bytes())
results["single_density_is_set"] = single_boot[6] == 0x40
results["single_other_id_fields_unchanged"] = (
    single_boot[0:6] == base_boot[0:6] and single_boot[7:16] == base_boot[7:16])

# 陰性対照: crc/deleted/singleの本体セクタ数はどれも16のまま(missingだけが15)。
for mode in ("crc", "deleted", "single"):
    img = (work / f"bsm_{mode}.d88").read_bytes()
    results[f"{mode}_track_still_has_16_sectors"] = len(track_headers(img, 0, 0)) == 16

# 陰性対照: crc/deleted/single のいずれも他のトラックには影響しない
# (18,1,14) の割り当て表セクタが既定(base)と一致する。
for mode in ("crc", "deleted", "single", "missing"):
    img = (work / f"bsm_{mode}.d88").read_bytes()
    reader = D88Reader(img)
    reader_base = D88Reader(base)
    results[f"{mode}_fat_sector_unchanged"] = (
        reader.read_sector(18, 1, 14) == reader_base.read_sector(18, 1, 14))

bad = [k for k, v in results.items() if not v]
for k, v in results.items():
    print(f"{k}={'ok' if v else 'ng'}")
sys.exit(1 if bad else 0)
PY
)"
bsm_rc=$?
printf '%s\n' "$bsm_out"
if [ "$bsm_rc" -eq 0 ]; then
  ok "m6f-d: --boot-sector-mode の本文・陰性対照がすべて通った"
else
  ng "m6f-d: --boot-sector-mode 検査のいずれかが落ちた"
fi

python3 "$GEN" "$WORK/badbsm1.d88" --fat-value 0x00 --filler 0x00 \
  --boot-sector-mode bogus >/dev/null 2>"$WORK/badbsm1.err"
rc_badbsm1=$?
if [ "$rc_badbsm1" -ge 2 ] && [ ! -e "$WORK/badbsm1.d88" ]; then
  ok "--boot-sector-mode の不正な値を拒否した(argparseのchoices、rc>=2)"
else
  ng "--boot-sector-mode の不正な値の拒否がrc>=2でない、または出力が作られた(rc=$rc_badbsm1)"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"
