#!/usr/bin/env bash
# tools/derive_m6fd.py の自己検査。合成のresult.jsonと、
# tools/make_m6fc_blank_disk.build_blank_disk() で作った合成D88だけで完結する。
# 公式ROM・公式ディスクには一切触れない。
#
# 検査項目:
#   1. 基本シナリオでD1〜D9が期待どおりの値・分類になり、overall=m6f_d_rules_confirmed。
#   2. 陰性対照: 鎖を1か所壊すとD2=link_otherになる。
#   3. 陰性対照: 本体配置をずらすとD1の値が実際に変わる(検出力の確認)。
#   4. 陰性対照: I-250の2走を食い違わせるとD1=ambiguousになる。
#   5. D5: II-pが通らないとnot_readable、陰性対照(II-neg1がrb0)でcontrol_failed。
#   6. D6: stops_at_unused/scans_past_unusedの両分類、III-noneがerでない陰性対照でcontrol_failed。
#   7. D7: RusedにR=0xFFが混じるとcontrol_failed。r_star()がD3のeを除いた最小値を返す。
#   8. D8: reserve_needed/reserve_not_needed/ambiguous(2走食い違い)の3分類。
#   9. D9: disk_basic判定と対照(V-ff/V-c9)のcontrol_changed検出。
#  10. overallのゲート: D5/D6のどちらかが欠けるとm6f_d_incomplete。
#  11. G9: 出力に本体の中身・割り当て表の位置160以降の目印バイトが現れない。
#      陰性対照として、わざと漏らす壊れた版がその目印を検出できることも確かめる。
#
# 使い方: tools/derive_m6fd_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO" <<'PY'
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "tools"))
from make_m6fc_blank_disk import build_blank_disk  # noqa: E402
import derive_m6fd as dfd  # noqa: E402

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


I_ARMS = dfd.I_ARMS  # ("I-250","I-1","I-3","I-6","I-10","I-17")
BODY_COORDS = [(0, 0, 1), (0, 0, 2), (0, 0, 3)]
TABLE_VALUES = {0: 1, 1: 2, 2: 0xC9}  # T[0]=1,T[1]=2,T[2]=終端0xC9(201)
E_EXPECT = 0xC9
K1_OFFSET = 10  # entry先頭単位の欄の候補オフセット


def build_i_arm_disk(body_coords=None, table_values=None, entry_offset=K1_OFFSET,
                      write_bad_marker=False, table_position200=None):
    body_coords = body_coords if body_coords is not None else BODY_COORDS
    table_values = table_values if table_values is not None else TABLE_VALUES
    img = build_blank_disk(0xFF, 0xFF, sector_fills={(18, 1, 13): 0})
    for k, v in table_values.items():
        for r in (14, 15, 16):
            img = patch(img, 18, 1, r, k, bytes([v]))
    if table_position200 is not None:
        # G9用: 位置160以降(範囲外)に目印を置く。derive_m6fdはここを読んではいけない。
        for r in (14, 15, 16):
            img = patch(img, 18, 1, r, 200, bytes([table_position200]))
    for idx, (c, h, r) in enumerate(body_coords, start=1):
        payload = f"{idx:05d}v".encode("ascii")
        if write_bad_marker:
            payload += b"SECRETBODYPAYLOAD"
        img = patch(img, c, h, r, 0, payload)
    # エントリ: (18,0,5)にQZ7B、候補オフセット10..15のうちentry_offsetだけk1(=0)に一致。
    entry = bytearray(16)
    entry[0:4] = b"QZ7B"
    entry[4:9] = b"     "
    entry[9] = 0x20
    for j in (10, 11, 12, 13, 14, 15):
        entry[j] = 0 if j == entry_offset else 0xEE
    img = patch(img, 18, 0, 5, 0, bytes(entry))
    return img


def write_i_arms(raw_dir, *, body_coords=None, table_values=None, entry_offset=K1_OFFSET,
                  mismatch_arm=None, write_bad_marker=False, table_position200=None):
    """全I-*腕を同一構成で書く。mismatch_armを指定するとその腕だけ2走を食い違わせる。"""
    for arm in I_ARMS:
        img1 = build_i_arm_disk(body_coords=body_coords, table_values=table_values,
                                 entry_offset=entry_offset, write_bad_marker=write_bad_marker,
                                 table_position200=table_position200)
        img2 = img1
        if arm == mismatch_arm:
            img2 = build_i_arm_disk(body_coords=[(0, 0, 1), (0, 0, 2)], table_values=table_values,
                                     entry_offset=entry_offset)
        (raw_dir / f"{arm}-r1.d88").write_bytes(img1)
        (raw_dir / f"{arm}-r2.d88").write_bytes(img2)


def make_result(*, d5=None, d6=None, d7=None, d8=None, d9=None):
    """D5〜D9系の腕をmarkers/entry_fieldsで作る。各パラメータは上書き用の辞書。"""
    d5 = d5 or {}
    d6 = d6 or {}
    d7 = d7 or {}
    d8 = d8 or {}
    d9 = d9 or {}
    runs = []

    def add(arm, rep, tags, numbers=None, entry_fields=None, writes=None):
        markers = [{"row": 1, "tag": t, "numbers": (numbers or {}).get(t, [])} for t in tags]
        runs.append({
            "arm": arm, "repetition": rep, "markers": markers,
            "malformed_marker_rows": 0, "reads": [], "writes": writes or [],
            "write_data_count": len(writes or []), "entry_fields": entry_fields or {},
        })

    # I-* 腕: D3で使うwrites(最後の単位=線形2、座標(0,0,3))を両走とも1件入れる。
    for arm in I_ARMS:
        for rep in (1, 2):
            add(arm, rep, [], writes=[{"c": 0, "h": 0, "r": 3}])

    # D5
    ii_d = d5.get("ii_d", ("rb", "rb"))
    ii_p = d5.get("ii_p", ("ld", "ld"))
    ii_neg1 = d5.get("ii_neg1", (None, None))
    ii_neg2 = d5.get("ii_neg2", (None, None))
    for rep, tag in zip((1, 2), ii_d):
        add("II-d", rep, [tag] if tag else [], numbers={"rb": [0]} if tag == "rb" else {})
    for rep, tag in zip((1, 2), ii_p):
        add("II-p", rep, [tag] if tag else [])
    for rep, tag in zip((1, 2), ii_neg1):
        add("II-neg1", rep, [tag] if tag else [], numbers={"rb": [0]} if tag == "rb" else {})
    for rep, tag in zip((1, 2), ii_neg2):
        add("II-neg2", rep, [tag] if tag else [], numbers={"rb": [0]} if tag == "rb" else {})

    # D6: 既定はr=7だけ00でok、FFでは見つからない(stops_at_unused)、noneはer。
    zero_ok = set(d6.get("zero_ok", {7}))
    ff_ok = set(d6.get("ff_ok", set()))
    none_tag = d6.get("none_tag", "er")
    for r in range(1, 13):
        tag00 = "ok" if r in zero_ok else "ng"
        tagff = "ok" if r in ff_ok else "ng"
        for rep in (1, 2):
            add(f"III-00-{r:02d}", rep, [tag00])
            add(f"III-FF-{r:02d}", rep, [tagff])
    for rep in (1, 2):
        add("III-none", rep, [none_tag] if none_tag else [])

    # D7: 既定でR=0x14,0xB0,0xC9(=e)がRused、R=0xFFは含めない。
    rused_defaults = d7.get("rused", (0x14, 0xB0, 0xC9))
    include_ff = d7.get("include_ff", False)
    r_values = set(rused_defaults) | ({0xFF} if include_ff else set())
    for r_value in range(256):
        want_ok = r_value in r_values
        arm = f"IV-R-{r_value:02X}"
        if not want_ok:
            continue
        ef = {"QZ7A": {"pos": {"c": 18, "h": 0, "r": 5, "offset": 0},
                        "bytes9_15": [0x20, 20, 0xEE, 0xEE, 0xEE, 0xEE, 0xEE]}}
        for rep in (1, 2):
            add(arm, rep, ["ok"], entry_fields=ef)

    # D8
    free_ck = d8.get("free", ("cx", "cx"))
    res_ck = d8.get("res", ("ck", "ck"))
    for rep, tag in zip((1, 2), free_ck):
        if tag == "ck":
            add("IV-fill-free", rep, ["ck"], numbers={"ck": [1]})
        elif tag == "ck0":
            add("IV-fill-free", rep, ["ck"], numbers={"ck": [0]})
        elif tag == "cx":
            add("IV-fill-free", rep, ["cx"], numbers={"cx": [53]})
        else:
            add("IV-fill-free", rep, [])
    for rep, tag in zip((1, 2), res_ck):
        if tag == "ck":
            add("IV-fill-res", rep, ["ck"], numbers={"ck": [1]})
        else:
            add("IV-fill-res", rep, [])

    # D9
    v_classes = d9.get("classes", {
        "V-missing": "disk_basic", "V-crc": "disk_basic",
        "V-deleted": "no_basic", "V-single": "no_basic",
        "V-ff": "no_basic", "V-c9": "nondisk_basic",
    })
    for arm, cls in v_classes.items():
        if cls == "disk_basic":
            tags = ["bt", "ok"]
        elif cls == "nondisk_basic":
            tags = ["bt"]
        elif cls == "error_after_boot":
            tags = ["bt", "er"]
        else:
            tags = []
        for rep in (1, 2):
            add(arm, rep, tags)

    return {"schema": 1, "runs": runs}


def run_case(name, work, *, i_kwargs=None, result_kwargs=None):
    raw_dir = work / name
    raw_dir.mkdir()
    write_i_arms(raw_dir, **(i_kwargs or {}))
    result = make_result(**(result_kwargs or {}))
    return dfd.build(result, raw_dir), result, raw_dir


import tempfile
with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)

    # --- 1. 基本シナリオ -----------------------------------------------------
    base, base_result, base_raw = run_case("base", work)
    d = base["derivations"]
    checks = {
        "D1_derived_s1_o0": d["D1"]["status"] == "derived" and d["D1"]["value"] == {"s": 1, "o": 0},
        "D1_replicas_match": d["D1"]["replica_15_matches_t"] and d["D1"]["replica_16_matches_t"],
        "D2_link_is_next_index": d["D2"]["status"] == "link_is_next_index",
        "D2_terminal": d["D2"]["terminal_value"] == E_EXPECT,
        "D3_end_constant": d["D3"]["status"] == "end_constant" and d["D3"]["value"] == E_EXPECT,
        "D4_derived_offset10": d["D4"]["status"] == "derived" and d["D4"]["value"] == {"offset": 10},
        "D5_relocated_readable": d["D5"]["status"] == "relocated_readable",
        "D6_stops_at_unused": d["D6"]["status"] == "stops_at_unused" and d["D6"]["directory_sectors"] == [7],
        "D7_rused": d["D7"]["rused"] == [0x14, 0xB0, 0xC9] and not d["D7"]["control_failed"],
        "D8_reserve_needed": d["D8"]["status"] == "reserve_needed",
        "D9_disk_basic_arms": d["D9"]["disk_basic_arms"] == ["V-crc", "V-missing"]
                               and not d["D9"]["control_changed"],
        "overall_confirmed": base["overall"] == "m6f_d_rules_confirmed",
    }
    for k, v in checks.items():
        (ok if v else ng)(f"基本シナリオ: {k}")

    # r_starの確認(環境変数経由)。
    import os
    os.environ["M6FD_RAW_DIR"] = str(base_raw)
    rstar = dfd.r_star(base_result)
    if rstar == 0xB0:
        ok(f"r_star: 期待どおり0xB0(={rstar})")
    else:
        ng(f"r_star: 期待(0xB0)と不一致: {rstar}")
    del os.environ["M6FD_RAW_DIR"]
    try:
        dfd.r_star(base_result)
        ng("r_star: raw_dir未指定・環境変数未設定でも例外にならない")
    except dfd.InputError:
        ok("r_star: raw_dir未指定・環境変数未設定はInputError")

    # --- 2. 陰性対照: 鎖を1か所壊す -------------------------------------------
    broken_table = dict(TABLE_VALUES)
    broken_table[1] = 55  # 本来2であるべき値を壊す
    broken, _, _ = run_case("chain_broken", work, i_kwargs={"table_values": broken_table})
    d2 = broken["derivations"]
    if d2["D2"]["status"] == "link_other" and d2["D2"]["mismatches"]:
        ok("陰性対照: 鎖を壊すとD2=link_otherになり検出力がある")
    else:
        ng(f"陰性対照: 鎖を壊してもlink_otherにならない: {d2['D2']}")

    # --- 3. 陰性対照: 本体配置をずらすとD1が実際に変わる ------------------------
    shifted_coords = [(0, 0, 2), (0, 0, 3), (0, 0, 4)]
    shifted, _, _ = run_case("mapping_shifted", work, i_kwargs={"body_coords": shifted_coords})
    d3 = shifted["derivations"]
    if d3["D1"]["status"] == "derived" and d3["D1"]["value"] != d["D1"]["value"]:
        ok(f"陰性対照: 配置をずらすとD1の値が変わる(base={d['D1']['value']} shifted={d3['D1']['value']})")
    else:
        ng(f"陰性対照: 配置をずらしてもD1が変わらない: {d3['D1']}")

    # --- 4. 陰性対照: I-250の2走食い違い --------------------------------------
    mismatched, _, _ = run_case("run_mismatch", work, i_kwargs={"mismatch_arm": "I-250"})
    d4c = mismatched["derivations"]
    if d4c["D1"]["status"] == "ambiguous":
        ok("陰性対照: I-250の2走食い違いでD1=ambiguous")
    else:
        ng(f"陰性対照: I-250の2走食い違いが検出されない: {d4c['D1']}")

    # --- 5. D5の分類 ----------------------------------------------------------
    not_readable, _, _ = run_case("d5_not_readable", work,
                                   result_kwargs={"d5": {"ii_p": (None, None)}})
    if not_readable["derivations"]["D5"]["status"] == "not_readable":
        ok("D5: II-pが通らないとnot_readable")
    else:
        ng(f"D5: not_readableにならない: {not_readable['derivations']['D5']}")

    control_failed5, _, _ = run_case("d5_control_failed", work,
                                      result_kwargs={"d5": {"ii_neg1": ("rb", "rb")}})
    if control_failed5["derivations"]["D5"]["status"] == "control_failed":
        ok("陰性対照: D5のII-neg1がrb0になるとcontrol_failed")
    else:
        ng(f"陰性対照: D5のcontrol_failedが検出されない: {control_failed5['derivations']['D5']}")

    # --- 6. D6の分類 ------------------------------------------------------------
    scans_past, _, _ = run_case("d6_scans_past", work,
                                 result_kwargs={"d6": {"zero_ok": {7}, "ff_ok": {7}}})
    if scans_past["derivations"]["D6"]["status"] == "scans_past_unused":
        ok("D6: FFでも見つかるとscans_past_unused")
    else:
        ng(f"D6: scans_past_unusedにならない: {scans_past['derivations']['D6']}")

    d6_control_failed, _, _ = run_case("d6_control_failed", work,
                                        result_kwargs={"d6": {"none_tag": "ok"}})
    if d6_control_failed["derivations"]["D6"]["status"] == "control_failed":
        ok("陰性対照: III-noneがerでないとD6=control_failed")
    else:
        ng(f"陰性対照: D6のcontrol_failedが検出されない: {d6_control_failed['derivations']['D6']}")

    # --- 7. D7の陰性対照(R=0xFFが混じる) ----------------------------------------
    d7_control_failed, _, _ = run_case("d7_control_failed", work,
                                        result_kwargs={"d7": {"include_ff": True}})
    if d7_control_failed["derivations"]["D7"]["control_failed"] and \
            0xFF in d7_control_failed["derivations"]["D7"]["rused"]:
        ok("陰性対照: R=0xFFがRusedに混じるとD7=control_failed")
    else:
        ng(f"陰性対照: D7のcontrol_failedが検出されない: {d7_control_failed['derivations']['D7']}")

    # --- 8. D8の分類 --------------------------------------------------------------
    reserve_not_needed, _, _ = run_case("d8_not_needed", work,
                                         result_kwargs={"d8": {"free": ("ck", "ck"), "res": ("ck", "ck")}})
    if reserve_not_needed["derivations"]["D8"]["status"] == "reserve_not_needed":
        ok("D8: 両方ck1ならreserve_not_needed")
    else:
        ng(f"D8: reserve_not_neededにならない: {reserve_not_needed['derivations']['D8']}")

    d8_ambiguous, _, _ = run_case("d8_ambiguous", work,
                                   result_kwargs={"d8": {"free": ("cx", "ck")}})
    if d8_ambiguous["derivations"]["D8"]["status"] == "ambiguous":
        ok("陰性対照: IV-fill-freeの2走食い違いでD8=ambiguous")
    else:
        ng(f"陰性対照: D8のambiguousが検出されない: {d8_ambiguous['derivations']['D8']}")

    # --- 9. D9のcontrol_changed ----------------------------------------------------
    d9_bad, _, _ = run_case("d9_control_changed", work,
                             result_kwargs={"d9": {"classes": {
                                 "V-missing": "disk_basic", "V-crc": "no_basic",
                                 "V-deleted": "no_basic", "V-single": "no_basic",
                                 "V-ff": "disk_basic", "V-c9": "nondisk_basic"}}})
    if d9_bad["derivations"]["D9"]["control_changed"]:
        ok("陰性対照: V-ffがno_basicでないとD9.control_changed=True")
    else:
        ng(f"陰性対照: D9のcontrol_changedが検出されない: {d9_bad['derivations']['D9']}")

    # --- 10. overallのゲート: D5が欠けるとm6f_d_incomplete --------------------------
    incomplete, _, _ = run_case("overall_incomplete", work,
                                 result_kwargs={"d5": {"ii_p": (None, None)}})
    if incomplete["overall"] == "m6f_d_incomplete":
        ok("overallゲート: D5がnot_readableだとm6f_d_incomplete")
    else:
        ng(f"overallゲート: incompleteにならない: {incomplete['overall']}")

    # --- 11. G9: 出力に本体の中身・位置160以降の目印が現れない -----------------------
    leaky_marker = 0xDE  # 222。他の導出値と衝突しない値を選ぶ。
    g9_case, g9_result, g9_raw = run_case(
        "g9", work,
        i_kwargs={"write_bad_marker": True, "table_position200": leaky_marker})
    text = json.dumps(g9_case, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if "SECRETBODYPAYLOAD" not in text and str(leaky_marker) not in text:
        ok("G9: 出力に本体の中身・位置160以降の目印が現れない")
    else:
        ng("G9: 出力に目印が漏れている")

    # G9の陰性対照: わざと位置160以降を読んで出力する壊れた版が目印を検出できること。
    def leaky_build(result, raw_dir):
        import sys as _sys
        sys.path.insert(0, str(repo / "tools"))
        from d88_read_sector import D88Reader
        arm_path = raw_dir / "I-250-r1.d88"
        reader = D88Reader(arm_path.read_bytes())
        leaked_value = reader.read_sector(18, 1, 14)[200]
        return {"leaked_position_200": leaked_value}

    leaky_out = json.dumps(leaky_build(g9_result, g9_raw))
    if str(leaky_marker) in leaky_out:
        ok("G9陰性対照: わざと位置160以降を出す壊れた版は目印を検出できる")
    else:
        ng("G9陰性対照: 壊れた版でも目印が検出できない(検査方法自体が機能していない)")

print()
if rc == 0:
    print("全項目 OK")
else:
    print("NG あり")
sys.exit(rc)
PY
exit $?
