#!/usr/bin/env bash
# tools/m6fd_relocate.py の自己検査(G10)。合成D88だけで完結し、公式ROM・
# 公式ディスク・private/ には一切触れない。
#
# 検査項目:
#   1. 合成のsrc像(仮説H1〜H3に従うファイルを自前で書き込んだもの)から、
#      付け替え後の像を独立に読んで、鎖・エントリ・本体の写しが正しいこと。
#   2. break_link_at・override_start・dir_fillが効くこと。
#   3. 鎖の循環・範囲外・未定義(0xFF)・長さ不一致・エントリ未検出を
#      それぞれ拒否すること(rc!=0、理由の種類だけをstderrに出す)。
#   4. G9: 器具の標準出力・標準エラーに、本体の目印バイト列と割り当て表
#      位置160以降の目印バイト列のどちらも現れないこと。
#   5. 4.の陰性対照: 目印を出力してしまう壊れた版(一時コピーにprintを
#      足したもの)では、4.の検査がNGになること(検出力の確認)。
#
# 使い方: tools/m6fd_relocate_selftest.sh

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$REPO/tools/m6fd_relocate.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

# --- 合成src像を組み立てる(Python、独立実装。本体マーカーと位置160以降の
#     マーカーをそれぞれ埋め込む。目印はG9検査でgrepしやすいASCII文字列)。 ---
build_out="$(REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import os
import pathlib
import struct
import sys

repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
from make_m6fc_blank_disk import build_blank_disk  # noqa: E402

D88_HEADER_SIZE = 32
TRACK_COUNT = 164
TRACK_TABLE_SIZE = TRACK_COUNT * 4
SECTORS_PER_TRACK = 16
SECTOR_HEADER_SIZE = 16
SECTOR_SIZE = 256
TRACK_BYTES = SECTORS_PER_TRACK * (SECTOR_HEADER_SIZE + SECTOR_SIZE)
HEADS = 2
SECTOR_BASE = 1


def sector_data_offset(c, h, r):
    phys = c * 2 + h
    return (D88_HEADER_SIZE + TRACK_TABLE_SIZE + phys * TRACK_BYTES
            + (r - SECTOR_BASE) * (SECTOR_HEADER_SIZE + SECTOR_SIZE) + SECTOR_HEADER_SIZE)


def write_sector(img, c, h, r, data):
    assert len(data) == SECTOR_SIZE
    off = sector_data_offset(c, h, r)
    img[off:off + SECTOR_SIZE] = data


def linear_to_coord(linear):
    c = linear // (HEADS * SECTORS_PER_TRACK)
    rem = linear % (HEADS * SECTORS_PER_TRACK)
    h = rem // SECTORS_PER_TRACK
    r = (rem % SECTORS_PER_TRACK) + SECTOR_BASE
    return c, h, r


def unit_coords(unit):
    base = unit * 8
    return [linear_to_coord(base + j) for j in range(8)]


BODY_MARKER_5 = (b"ZQMARKERBODY05!!" * 16)[:256]
BODY_MARKER_10 = (b"ZQMARKERBODY10!!" * 16)[:256]
BODY_MARKER_15 = (b"ZQMARKERBODY15!!" * 16)[:256]
FAT_HIGH_MARKER = (b"ZQMARKERFATHIGH!" * 6)[:96]  # 位置160..255(96バイト)を埋める目印

img = bytearray(build_blank_disk(0xFF, 0xFF))

# 単位5→10→15(終端0xC1)の鎖。3セクタとも同じ値にする(仕様書2章)。
fat = bytearray([0xFF]) * SECTOR_SIZE
fat[5] = 10
fat[10] = 15
fat[15] = 0xC1  # 終端の値e
fat[160:256] = FAT_HIGH_MARKER  # 位置160以降の目印(仕様上は意味を持たない範囲)
for coord in ((18, 1, 14), (18, 1, 15), (18, 1, 16)):
    write_sector(img, *coord, bytes(fat))

for unit, marker in ((5, BODY_MARKER_5), (10, BODY_MARKER_10), (15, BODY_MARKER_15)):
    for coord in unit_coords(unit):
        write_sector(img, *coord, marker)

# エントリ: (18,1,1)の先頭に置く。名前"SRCF"+空白詰め、9バイト目=0x00(データ)、
# 10バイト目=開始単位5、11〜15バイト目は識別用の非0xFF値。
entry = bytearray(16)
entry[0:9] = b"SRCF" + b" " * 5
entry[9] = 0x00
entry[10] = 5
entry[11:16] = bytes([0x01, 0x02, 0x03, 0x04, 0x05])
sector1 = bytearray(write_sector.__globals__["SECTOR_SIZE"])
sector1[0:16] = entry
sector1[16:] = bytes([0xFF]) * (SECTOR_SIZE - 16)
write_sector(img, 18, 1, 1, bytes(sector1))

(work / "src.d88").write_bytes(bytes(img))
print("src_built_ok")
PY
)"
if [ "$build_out" = "src_built_ok" ]; then
  ok "合成src像を組み立てた"
else
  ng "合成src像の組み立てに失敗した: $build_out"
fi

SRC="$WORK/src.d88"

# --- 1. 正常な付け替え ----------------------------------------------------
python3 "$TOOL" "$SRC" "$WORK/dst_ok.d88" --src-name SRCF --dst-name DSTF \
  --dst-units 20,21,22 >"$WORK/ok.out" 2>"$WORK/ok.err"
rc_ok=$?
if [ "$rc_ok" -eq 0 ]; then
  ok "正常な付け替えがrc=0で成功した"
else
  ng "正常な付け替えが失敗した(rc=$rc_ok): $(cat "$WORK/ok.err")"
fi
if grep -q "^鎖の長さ: 3$" "$WORK/ok.out"; then
  ok "鎖の長さ3が報告された"
else
  ng "鎖の長さの報告が期待と違う: $(cat "$WORK/ok.out")"
fi

# --- 2. override-start・dir-fill 付き ---------------------------------------
python3 "$TOOL" "$SRC" "$WORK/dst_ov.d88" --src-name SRCF --dst-name DSTF \
  --dst-units 20,21,22 --override-start 99 --dir-fill 00 \
  >"$WORK/ov.out" 2>"$WORK/ov.err"
rc_ov=$?
if [ "$rc_ov" -eq 0 ]; then
  ok "override-start/dir-fill付きの付け替えがrc=0で成功した"
else
  ng "override-start/dir-fill付きの付け替えが失敗した(rc=$rc_ov): $(cat "$WORK/ov.err")"
fi

# --- 3. break-link-at ------------------------------------------------------
python3 "$TOOL" "$SRC" "$WORK/dst_bl.d88" --src-name SRCF --dst-name DSTF \
  --dst-units 20,21,22 --break-link-at 21 >"$WORK/bl.out" 2>"$WORK/bl.err"
rc_bl=$?
if [ "$rc_bl" -eq 0 ]; then
  ok "break-link-at付きの付け替えがrc=0で成功した"
else
  ng "break-link-at付きの付け替えが失敗した(rc=$rc_bl): $(cat "$WORK/bl.err")"
fi

# --- 本文検査(独立読み手 d88_read_sector.D88Reader を使う) ------------------
verify_out="$(REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import os
import pathlib
import sys

repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
from d88_read_sector import D88Reader  # noqa: E402

BODY_MARKER_5 = (b"ZQMARKERBODY05!!" * 16)[:256]
BODY_MARKER_10 = (b"ZQMARKERBODY10!!" * 16)[:256]
BODY_MARKER_15 = (b"ZQMARKERBODY15!!" * 16)[:256]

results = {}


def unit_coords(unit):
    base = unit * 8
    coords = []
    for j in range(8):
        linear = base + j
        c = linear // 32
        rem = linear % 32
        h = rem // 16
        r = (rem % 16) + 1
        coords.append((c, h, r))
    return coords


# --- 1. 正常な付け替え(dst_ok.d88) ---
reader = D88Reader((work / "dst_ok.d88").read_bytes())

fat14 = reader.read_sector(18, 1, 14)
fat15 = reader.read_sector(18, 1, 15)
fat16 = reader.read_sector(18, 1, 16)
results["fat_20_is_21"] = fat14[20] == 21 == fat15[20] == fat16[20]
results["fat_21_is_22"] = fat14[21] == 22 == fat15[21] == fat16[21]
results["fat_22_is_terminal_0xC1"] = fat14[22] == 0xC1 == fat15[22] == fat16[22]
# 使っていない位置は空き(0xFF)のまま。
results["fat_unused_position_still_ff"] = fat14[0] == 0xFF and fat14[19] == 0xFF and fat14[23] == 0xFF

body20 = b"".join(reader.read_sector(*c) for c in unit_coords(20))
body21 = b"".join(reader.read_sector(*c) for c in unit_coords(21))
body22 = b"".join(reader.read_sector(*c) for c in unit_coords(22))
results["body_20_matches_src_unit5"] = body20 == BODY_MARKER_5 * 8
results["body_21_matches_src_unit10"] = body21 == BODY_MARKER_10 * 8
results["body_22_matches_src_unit15"] = body22 == BODY_MARKER_15 * 8

entry = reader.read_sector(18, 1, 1)[0:16]
results["entry_name_is_dst_name"] = entry[0:9] == b"DSTF" + b" " * 5
results["entry_byte9_copied_from_src"] = entry[9] == 0x00
results["entry_byte10_is_first_dst_unit"] = entry[10] == 20
results["entry_bytes_11_15_copied_from_src"] = entry[11:16] == bytes([0x01, 0x02, 0x03, 0x04, 0x05])

# --- 2. override-start / dir-fill(dst_ov.d88) ---
reader_ov = D88Reader((work / "dst_ov.d88").read_bytes())
entry_ov = reader_ov.read_sector(18, 1, 1)[0:16]
results["override_start_applied"] = entry_ov[10] == 99

all_dir_zero_except_entry = True
for r in range(1, 13):
    sector = reader_ov.read_sector(18, 1, r)
    if r == 1:
        rest = sector[16:]
        if rest != bytes(len(rest)):
            all_dir_zero_except_entry = False
        # エントリを置いたセクタの先頭16バイトはエントリそのもの(非ゼロ)。
        if sector[0:16] == bytes(16):
            all_dir_zero_except_entry = False
    else:
        if sector != bytes(256):
            all_dir_zero_except_entry = False
results["dir_fill_00_zeroes_directory_except_entry"] = all_dir_zero_except_entry

# --- 3. break-link-at(dst_bl.d88) ---
reader_bl = D88Reader((work / "dst_bl.d88").read_bytes())
fat_bl = reader_bl.read_sector(18, 1, 14)
fat_bl15 = reader_bl.read_sector(18, 1, 15)
fat_bl16 = reader_bl.read_sector(18, 1, 16)
results["break_link_sets_ff_all_three"] = fat_bl[21] == 0xFF == fat_bl15[21] == fat_bl16[21]
# 他の位置(20→21)は break-link の影響を受けていない。
results["break_link_does_not_touch_other_positions"] = fat_bl[20] == 21

bad = [k for k, v in results.items() if not v]
for k, v in results.items():
    print(f"{k}={'ok' if v else 'ng'}")
sys.exit(1 if bad else 0)
PY
)"
verify_rc=$?
printf '%s\n' "$verify_out"
if [ "$verify_rc" -eq 0 ]; then
  ok "本文検査(鎖・エントリ・本体の写し・override-start・dir-fill・break-link-at)がすべて通った"
else
  ng "本文検査のいずれかが落ちた"
fi

# --- 3(続). 拒否系(陰性対照つき) -------------------------------------------

# 長さ不一致
python3 "$TOOL" "$SRC" "$WORK/bad_len.d88" --src-name SRCF --dst-name DSTF \
  --dst-units 20,21 >/dev/null 2>"$WORK/bad_len.err"
rc_len=$?
if [ "$rc_len" -ne 0 ] && [ ! -e "$WORK/bad_len.d88" ] && grep -q ChainLengthMismatchError "$WORK/bad_len.err"; then
  ok "鎖の長さ不一致を拒否した(ChainLengthMismatchError)"
else
  ng "鎖の長さ不一致の拒否が期待と違う(rc=$rc_len): $(cat "$WORK/bad_len.err")"
fi

# エントリが見つからない
python3 "$TOOL" "$SRC" "$WORK/bad_nf.d88" --src-name NOPE --dst-name DSTF \
  --dst-units 20,21,22 >/dev/null 2>"$WORK/bad_nf.err"
rc_nf=$?
if [ "$rc_nf" -ne 0 ] && [ ! -e "$WORK/bad_nf.d88" ] && grep -q EntryNotFoundError "$WORK/bad_nf.err"; then
  ok "エントリ未検出を拒否した(EntryNotFoundError)"
else
  ng "エントリ未検出の拒否が期待と違う(rc=$rc_nf): $(cat "$WORK/bad_nf.err")"
fi

# 循環・範囲外・未定義は、それぞれ別の壊れたsrc像で確かめる。
cycle_out="$(REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import os
import pathlib
import sys

repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))

D88_HEADER_SIZE = 32
TRACK_TABLE_SIZE = 164 * 4
SECTOR_HEADER_SIZE = 16
SECTOR_SIZE = 256
TRACK_BYTES = 16 * (SECTOR_HEADER_SIZE + SECTOR_SIZE)


def sector_data_offset(c, h, r):
    phys = c * 2 + h
    return (D88_HEADER_SIZE + TRACK_TABLE_SIZE + phys * TRACK_BYTES
            + (r - 1) * (SECTOR_HEADER_SIZE + SECTOR_SIZE) + SECTOR_HEADER_SIZE)


def write_sector(img, c, h, r, data):
    off = sector_data_offset(c, h, r)
    img[off:off + SECTOR_SIZE] = data


base = bytearray((work / "src.d88").read_bytes())

# 循環: T[5]=10, T[10]=5
cycle = bytearray(base)
fat = bytearray([0xFF]) * SECTOR_SIZE
fat[5] = 10
fat[10] = 5
for coord in ((18, 1, 14), (18, 1, 15), (18, 1, 16)):
    write_sector(cycle, *coord, bytes(fat))
(work / "src_cycle.d88").write_bytes(bytes(cycle))

# 範囲外: エントリの開始単位を170(160以上、割り当て単位に対応しない)にする
rangeimg = bytearray(base)
entry = bytearray(16)
entry[0:9] = b"SRCF" + b" " * 5
entry[9] = 0x00
entry[10] = 170
entry[11:16] = bytes([1, 2, 3, 4, 5])
sector1 = bytearray(SECTOR_SIZE)
sector1[0:16] = entry
sector1[16:] = bytes([0xFF]) * (SECTOR_SIZE - 16)
write_sector(rangeimg, 18, 1, 1, bytes(sector1))
(work / "src_range.d88").write_bytes(bytes(rangeimg))

# 未定義: T[5]=10, T[10]=0xFF(160未満の途中で未定義)
undef = bytearray(base)
fat = bytearray([0xFF]) * SECTOR_SIZE
fat[5] = 10
# fat[10] は明示的に0xFFのまま(既定)。
for coord in ((18, 1, 14), (18, 1, 15), (18, 1, 16)):
    write_sector(undef, *coord, bytes(fat))
(work / "src_undef.d88").write_bytes(bytes(undef))

print("ok")
PY
)"
if [ "$cycle_out" = "ok" ]; then
  ok "循環・範囲外・未定義それぞれの壊れたsrc像を組み立てた"
else
  ng "壊れたsrc像の組み立てに失敗した: $cycle_out"
fi

python3 "$TOOL" "$WORK/src_cycle.d88" "$WORK/bad_cycle.d88" --src-name SRCF --dst-name DSTF \
  --dst-units 20,21,22 >/dev/null 2>"$WORK/bad_cycle.err"
rc_cycle=$?
if [ "$rc_cycle" -ne 0 ] && [ ! -e "$WORK/bad_cycle.d88" ] && grep -q ChainCycleError "$WORK/bad_cycle.err"; then
  ok "鎖の循環を拒否した(ChainCycleError)"
else
  ng "鎖の循環の拒否が期待と違う(rc=$rc_cycle): $(cat "$WORK/bad_cycle.err")"
fi

python3 "$TOOL" "$WORK/src_range.d88" "$WORK/bad_range.d88" --src-name SRCF --dst-name DSTF \
  --dst-units 20,21,22 >/dev/null 2>"$WORK/bad_range.err"
rc_range=$?
if [ "$rc_range" -ne 0 ] && [ ! -e "$WORK/bad_range.d88" ] && grep -q ChainRangeError "$WORK/bad_range.err"; then
  ok "鎖の範囲外を拒否した(ChainRangeError)"
else
  ng "鎖の範囲外の拒否が期待と違う(rc=$rc_range): $(cat "$WORK/bad_range.err")"
fi

python3 "$TOOL" "$WORK/src_undef.d88" "$WORK/bad_undef.d88" --src-name SRCF --dst-name DSTF \
  --dst-units 20,21,22 >/dev/null 2>"$WORK/bad_undef.err"
rc_undef=$?
if [ "$rc_undef" -ne 0 ] && [ ! -e "$WORK/bad_undef.d88" ] && grep -q ChainUndefinedError "$WORK/bad_undef.err"; then
  ok "鎖の未定義(0xFF)を拒否した(ChainUndefinedError)"
else
  ng "鎖の未定義の拒否が期待と違う(rc=$rc_undef): $(cat "$WORK/bad_undef.err")"
fi

# --- 4. G9: 標準出力・標準エラーに目印が現れない ----------------------------
leak=0
for f in "$WORK"/*.out "$WORK"/*.err; do
  [ -e "$f" ] || continue
  if grep -q "ZQMARKERBODY" "$f" || grep -q "ZQMARKERFATHIGH" "$f"; then
    leak=1
    printf '       漏れを検出: %s\n' "$f"
  fi
done
if [ "$leak" -eq 0 ]; then
  ok "G9: 全出力に本体マーカー・位置160以降マーカーが現れない"
else
  ng "G9: 出力に目印バイト列が現れた"
fi

# --- 5. G9の陰性対照: 目印を出力してしまう壊れた版でNGになることを確認 ------
BROKEN="$WORK/m6fd_relocate_broken.py"
cp "$TOOL" "$BROKEN"
cp "$REPO/tools/make_m6fc_blank_disk.py" "$WORK/make_m6fc_blank_disk.py"
cp "$REPO/tools/make_l3_testdisk.py" "$WORK/make_l3_testdisk.py"
cp "$REPO/tools/d88_read_sector.py" "$WORK/d88_read_sector.py" 2>/dev/null || true
# 単位を写す行の直後に、写した中身をそのまま標準出力へ漏らす1行を挿入する。
python3 - "$BROKEN" <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
needle = "            _write_sector(new_image, *dc, payload)\n"
assert needle in text, "挿入対象の行が見つからない(器具の実装が変わった可能性)"
broken = text.replace(needle, needle + "            print(payload)\n", 1)
assert broken != text
open(path, "w", encoding="utf-8").write(broken)
PY
python3 "$BROKEN" "$SRC" "$WORK/dst_broken.d88" --src-name SRCF --dst-name DSTF \
  --dst-units 20,21,22 >"$WORK/broken.out" 2>"$WORK/broken.err"
if grep -q "ZQMARKERBODY" "$WORK/broken.out"; then
  ok "陰性対照: 壊れた版は本体マーカーを標準出力に漏らした(検出力の確認)"
else
  ng "陰性対照: 壊れた版でも漏れが検出できなかった(検査の検出力が無い)"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"
