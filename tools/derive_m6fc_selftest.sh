#!/usr/bin/env bash
# tools/derive_m6fc.py の自己検査。合成の result.json と、
# tools/make_m6fc_blank_disk.build_blank_disk() で作った媒体に既知の
# パッチを当てた合成D88だけで完結する。公式ROM・公式ディスクには触れない。
#
# 検査項目:
#   1. 基本シナリオで C0/C1/C2/C3/C4/C5/C7/C8/C10 が derived、
#      C2=accepted、overall=m6f_c_blank_disk_accepted。
#   2. 陰性対照: 鎖を1か所壊すと C5=link_other になる。
#   3. 陰性対照: 本体セクタの配置をずらすと C4 の (S,o) が実際に変わる
#      （検出力の確認。固定の分類名切替えだけでなく値そのものが動くこと）。
#   4. 陰性対照: A3の2走を食い違わせると C3/C4 が ambiguous 側になる。
#   5. 陰性対照: SW-01の2走を食い違わせると C1.run_disagreement に載る。
#
# 使い方: tools/derive_m6fc_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 - "$REPO" "$WORK" <<'PY'
import json
import sys
from pathlib import Path

repo, work = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo / "tools"))
from make_m6fc_blank_disk import build_blank_disk  # noqa: E402
import derive_m6fc as dm  # noqa: E402

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
V_STAR = 0xFF
F_STAR = 0x00


def sector_offset(c, h, r):
    phys = c * 2 + h
    return HEADER + TRACK_TABLE + phys * TRACK_BYTES + (r - 1) * SECTOR_UNIT + 16


def patch(image, c, h, r, offset, data):
    base = bytearray(image)
    pos = sector_offset(c, h, r) + offset
    base[pos:pos + len(data)] = data
    return bytes(base)


C6_ARMS = ("A3", "A4-1", "A4-3", "A4-6", "A4-10", "A4-17")
ALL_ARMS_WITH_DISK = C6_ARMS + ("A1b", "A6", "A5", "A5b")

BODY_COORDS = [(0, 0, 1), (0, 0, 2), (0, 0, 3)]
TABLE_VALUES = {0: 1, 1: 2, 2: 0xC0}  # T[0]=1(次), T[1]=2(次), T[2]=終端0xC0


def build_arm_disk(arm, *, body_coords=BODY_COORDS, table_values=None, entry_offset=12):
    table_values = table_values if table_values is not None else TABLE_VALUES
    img = build_blank_disk(V_STAR, F_STAR)
    for k, v in table_values.items():
        for r in (14, 15, 16):
            img = patch(img, 18, 1, r, k, bytes([v]))
    for idx, (c, h, r) in enumerate(body_coords, start=1):
        img = patch(img, c, h, r, 0, f"{idx:05d}v".encode("ascii"))
    name = {"A1b": b"QZ7A", "A6": b"q7l"}.get(arm, b"QZ7B")
    if arm not in ("A5", "A5b"):
        img = patch(img, 18, 1, 3, 0, name)
        # 候補オフセット(9..14)のうち entry_offset だけ k1(=0) に一致させる。
        for j in dm.ENTRY_FIELD_OFFSETS:
            img = patch(img, 18, 1, 3, j, bytes([0 if j == entry_offset else 0xEE]))
    if arm in ("A5", "A5b"):
        for i in range(1, 4):
            img = patch(img, 18, 1, 1, (i - 1) * 16, f"Q{i:03d}     ".encode("ascii"))
    return img


def write_arm(raw_dir, arm, image1, image2=None):
    (raw_dir / f"{arm}-r1.d88").write_bytes(image1)
    (raw_dir / f"{arm}-r2.d88").write_bytes(image2 if image2 is not None else image1)


def base_result(sw_extra=None):
    sw_extra = sw_extra or {}
    runs = []

    def add(arm, rep, tags, numbers=None, name_counts=None, reads=None, writes=None):
        markers = [{"row": 1, "tag": t, "numbers": (numbers or {}).get(t, [])} for t in tags]
        runs.append({
            "arm": arm, "repetition": rep, "fat_value": V_STAR, "filler": F_STAR,
            "initial_sha": "x", "final_sha": "x", "markers": markers,
            "malformed_marker_rows": 0, "name_counts": name_counts or {},
            "reads": reads or [], "writes": writes or [], "write_data_count": len(writes or []),
        })

    for rep in (1, 2):
        add("GB-FF", rep, ["bt"])
    for rep in (1, 2):
        add("SW-FF", rep, ["ok"])
    for v, (t1, t2) in sw_extra.items():
        add(f"SW-{v:02X}", 1, [t1])
        add(f"SW-{v:02X}", 2, [t2])
    for rep in (1, 2):
        add("A1", rep, ["ok"], reads=[{"c": 18, "h": 1, "r": 3}, {"c": 18, "h": 1, "r": 3}])
    for rep in (1, 2):
        add("A1b", rep, ["ok"], name_counts={"QZ7A": 1})
    for rep in (1, 2):
        add("A2", rep, ["ld"])
    for rep in (1, 2):
        add("A3", rep, ["rb"], numbers={"rb": [0]})
        for arm in ("A4-1", "A4-3", "A4-6", "A4-10", "A4-17"):
            add(arm, rep, ["rb"], numbers={"rb": [0]})
    for rep in (1, 2):
        add("A5", rep, ["er"], numbers={"er": [7, 40]})
        add("A5b", rep, ["er"], numbers={"er": [7, 40]})
    for rep in (1, 2):
        add("A6", rep, ["ld"])
    return {"schema": 1, "runs": runs}


def run_case(name, *, sw_extra=None, patch_arms=None, mismatch_a3=False):
    raw_dir = work / name
    raw_dir.mkdir()
    patch_arms = patch_arms or {}
    for arm in ALL_ARMS_WITH_DISK:
        kwargs = patch_arms.get(arm, {})
        img1 = build_arm_disk(arm, **kwargs)
        img2 = None
        if arm == "A3" and mismatch_a3:
            img2 = build_arm_disk(arm, body_coords=BODY_COORDS[:2])
        write_arm(raw_dir, arm, img1, img2)
    result = base_result(sw_extra=sw_extra)
    result_path = work / f"{name}.result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    return dm.build(result, raw_dir)


# --- 1. 基本シナリオ --------------------------------------------------------
base = run_case("base")
d = base["derivations"]
checks = {
    "C0_derived": d["C0"]["status"] == "derived" and d["C0"]["value"] == 0xFF,
    "C1_derived": d["C1"]["status"] == "derived" and d["C1"]["value"] == 0xFF,
    "C2_accepted": d["C2"]["status"] == "accepted",
    "C3_identical": d["C3"]["status"] == "replicas_identical",
    "C4_derived_s1_o0": d["C4"]["status"] == "derived" and d["C4"]["value"] == {"s": 1, "o": 0},
    "C5_link_is_next_index": d["C5"] is not None and d["C5"]["status"] == "link_is_next_index",
    "C5_terminal": d["C5"] is not None and d["C5"]["terminal_value"] == 0xC0,
    "C7_derived_offset12": d["C7"]["status"] == "derived" and d["C7"]["value"] == {"offset": 12},
    "C8_derived": d["C8"]["status"] == "derived",
    "C10_derived": d["C10"]["status"] == "derived"
                   and d["C10"]["value"] == [{"c": 18, "h": 1, "r": 3}],
    "overall_accepted": base["overall"] == "m6f_c_blank_disk_accepted",
}
for k, v in checks.items():
    (ok if v else ng)(f"基本シナリオ: {k}")

# --- 2. 陰性対照: 鎖を1か所壊す ---------------------------------------------
broken_table = dict(TABLE_VALUES)
broken_table[1] = 5  # 本来2であるべき値を壊す
broken = run_case("chain_broken", patch_arms={a: {"table_values": broken_table} for a in C6_ARMS})
d2 = broken["derivations"]
if d2["C5"] is not None and d2["C5"]["status"] == "link_other" and d2["C5"]["mismatches"]:
    ok("陰性対照: 鎖を壊すとC5=link_otherになり検出力がある")
else:
    ng(f"陰性対照: 鎖を壊してもlink_otherにならない: {d2['C5']}")

# --- 3. 陰性対照: 本体配置をずらすとC4の値が実際に変わる --------------------
shifted_coords = [(0, 0, 2), (0, 0, 3), (0, 0, 4)]
shifted = run_case("mapping_shifted",
                    patch_arms={a: {"body_coords": shifted_coords} for a in C6_ARMS})
d3 = shifted["derivations"]
if d3["C4"]["status"] == "derived" and d3["C4"]["value"] != base["derivations"]["C4"]["value"]:
    ok(f"陰性対照: 配置をずらすとC4の値が変わる(base={base['derivations']['C4']['value']} "
       f"shifted={d3['C4']['value']})")
else:
    ng(f"陰性対照: 配置をずらしてもC4が変わらない: {d3['C4']}")

# --- 4. 陰性対照: A3の2走食い違い -------------------------------------------
mismatched = run_case("run_mismatch", mismatch_a3=True)
d4 = mismatched["derivations"]
if d4["C3"]["status"] == "ambiguous" and d4["C4"]["status"] == "not_found":
    ok("陰性対照: A3の2走食い違いでC3=ambiguous,C4=not_found")
else:
    ng(f"陰性対照: A3の2走食い違いが検出されない: C3={d4['C3']} C4={d4['C4']}")

# --- 5. 陰性対照: SW-01の2走食い違い ----------------------------------------
disagree = run_case("sw_disagreement", sw_extra={0x01: ("ok", "ng")})
d5 = disagree["derivations"]
if d5["C1"].get("run_disagreement") == [1] and d5["C1"]["status"] == "derived" \
        and d5["C1"]["value"] == 0xFF:
    ok("陰性対照: SW-01の2走食い違いがC1.run_disagreementに載り、V*は動じない")
else:
    ng(f"陰性対照: SW-01の食い違いが正しく扱われない: {d5['C1']}")

print()
if rc == 0:
    print("全項目 OK")
else:
    print("NG あり")
sys.exit(rc)
PY
exit $?
