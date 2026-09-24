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

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"
