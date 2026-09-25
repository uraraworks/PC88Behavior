#!/usr/bin/env bash
# derive_m6fd の D1〜D4 を、現実に近い形（1単位8セクタ、3単位にまたがる I-250、
# 1セクタだけの小さい腕）で確かめる。既存の自己検査は1単位1セクタの合成だけで、
# (a) 単位の並びをセクタごとに作ると同じ単位どうしを鎖として比べてしまう不具合、
# (b) 小さい腕で (S,o) を腕ごとに導出し直すと決まらない不具合、を表に出せなかった。
# 陰性対照: 直す前の形（セクタごとの並び）で D2 が link_other になること。
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
import sys
from pathlib import Path
repo, work = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo / "tools"))
import derive_m6fd as dfd
import derive_m6fc as dm
from make_m6fc_blank_disk import build_blank_disk
HEADER, TRACK_TABLE, SECTOR_UNIT, SPT = 32, 164 * 4, 16 + 256, 16
def off(c, h, r):
    return HEADER + TRACK_TABLE + (c * 2 + h) * SPT * SECTOR_UNIT + (r - 1) * SECTOR_UNIT + 16
def patch(img, c, h, r, o, data):
    b = bytearray(img); p = off(c, h, r) + o; b[p:p + len(data)] = data; return bytes(b)
def coords_of_unit(k, n=8):
    out = []
    for L in range(8 * k, 8 * k + n):
        t, r = divmod(L, 16); out.append((t // 2, t % 2, r + 1))
    return out
def disk(units, sectors_last, table, k1):
    img = build_blank_disk(0xFF, 0xFF, sector_fills={(18, 1, 13): 0})
    for k, v in table.items():
        for r in (14, 15, 16):
            img = patch(img, 18, 1, r, k, bytes([v]))
    idx = 1
    for i, k in enumerate(units):
        n = sectors_last if i == len(units) - 1 else 8
        for (c, h, r) in coords_of_unit(k, n):
            img = patch(img, c, h, r, 0, f"{idx:05d}v".encode()); idx += 1
    entry = bytearray(b"QZ7B     " + bytes([0x00, k1, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]))
    return patch(img, 18, 1, 1, 0, bytes(entry))
raw = work / "raw"; raw.mkdir()
big = disk([72, 71, 68], 4, {72: 71, 71: 68, 68: 0xC4}, 72)
small = disk([72], 1, {72: 0xC1}, 72)
for rep in (1, 2):
    (raw / f"I-250-r{rep}.d88").write_bytes(big)
    for arm in ("I-1", "I-3", "I-6", "I-10", "I-17"):
        (raw / f"{arm}-r{rep}.d88").write_bytes(small)
reps = dfd.load_i_reps(raw)
d1 = dfd.d1_unit_and_position(reps)
d2 = dfd.d2_chain(d1, reps)
d4 = dfd.d4_entry_head_field(reps)
fails = []
if not (d1.get("status") == "derived" and d1["value"] == {"s": 8, "o": 0}):
    fails.append(f"D1 {d1.get('status')} {d1.get('value')}")
if not (d2 and d2.get("status") == "link_is_next_index" and d2.get("k_sequence") == [72, 71, 68]):
    fails.append(f"D2 {d2 and d2.get('status')} {d2 and d2.get('k_sequence')}")
if not (d4.get("status") == "derived" and d4.get("value") == {"offset": 10}):
    fails.append(f"D4 {d4.get('status')} {d4.get('value')}")
# 陰性対照: セクタごとの並び（直す前の形）で鎖を見ると link_other になる。
body = dm.find_body_sectors(dm.load_disk(raw / "I-250-r1.d88"))
per_sector = [dm.linear_number(*c) // 8 for c, _ in body]
t = dm.sector(dm.load_disk(raw / "I-250-r1.d88"), (18, 1, 14))
if dm.chain(t, per_sector)["status"] != "link_other":
    fails.append("陰性対照: セクタごとの並びでも link_is_next_index になった（検出力なし）")
for f in fails: print("NG:", f)
print("全項目 OK" if not fails else "NG あり")
raise SystemExit(1 if fails else 0)
PY
