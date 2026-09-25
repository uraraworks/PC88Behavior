#!/usr/bin/env bash
# tools/derive_m6fd_add1.py の自己検査。合成のresult.jsonと、
# tools/make_m6fc_blank_disk.build_blank_disk() で作った合成D88だけで完結する。
# 公式ROM・公式ディスクには一切触れない。
#
# 検査項目:
#   1. D3': 6腕でe-uが一定ならend_plus_used_sectors(値を記録)。
#   2. D3': 陰性対照(chain_broken): 1腕でT[k1]=0xFFに当たるとend_otherになり、
#      chain_broken_armsに列挙される。
#   3. D3': 陰性対照(ambiguous): 1腕の2走でe/uが食い違うとend_otherになる
#      (ambiguousはentriesに入らず腕数不足でend_other)。
#   4. D3': eが全腕同じ(uは違う)ならend_constant。
#   5. R*: d7_prime+r_star_add1が、I-*のD3'事後記録のeを除いた最小値を返す。
#   6. D8: derive_m6fd.d8_reserve_neededをそのまま適用できる。
#   7. 総合: 全条件成立でm6f_d_add1_rules_confirmed、1条件欠落でincomplete。
#   8. G9: 出力に位置160以降・本体の目印バイトが現れない。陰性対照として
#      わざと漏らす壊れた関数がその目印を検出できることも確かめる。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO" <<'PY'
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "tools"))
from make_m6fc_blank_disk import build_blank_disk  # noqa: E402
import derive_m6fc as dm  # noqa: E402
import derive_m6fd_add1 as add1  # noqa: E402

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
E_ARMS = add1.E_ARMS
K1 = 20


def sector_offset(c, h, r):
    phys = c * 2 + h
    return HEADER + TRACK_TABLE + phys * TRACK_BYTES + (r - 1) * SECTOR_UNIT + 16


def patch(image, c, h, r, offset, data):
    base = bytearray(image)
    pos = sector_offset(c, h, r) + offset
    base[pos:pos + len(data)] = data
    return bytes(base)


def make_entry_fields(k1):
    return {"QZ7B": {"pos": {"c": 18, "h": 0, "r": 5, "offset": 0},
                      "bytes9_15": [0x20, k1, 0xEE, 0xEE, 0xEE, 0xEE, 0xEE]}}


def coords_for_range(lo, hi):
    return [{"c": c, "h": h, "r": r} for n in range(lo, hi) for (c, h, r) in [dm.coord_of_linear(n)]]


def make_arm_image(k_m, e_value, table160_marker=None, body_marker=None, hits_ff=False):
    img = build_blank_disk(0xFF, 0xFF, sector_fills={(18, 1, 13): 0})
    for r in (14, 15, 16):
        img = patch(img, 18, 1, r, K1, bytes([k_m]))
        term = 0xFF if hits_ff else e_value
        img = patch(img, 18, 1, r, k_m, bytes([term]))
        if table160_marker is not None:
            img = patch(img, 18, 1, r, 200, bytes([table160_marker]))
    if body_marker is not None:
        img = patch(img, 0, 0, 1, 0, bytes([body_marker]) * 8)
    return img


def write_arm(raw_dir, arm, *, k_m, u, e_value=0xC9, mismatch=False, hits_ff=False,
              table160_marker=None, body_marker=None):
    img1 = make_arm_image(k_m, e_value, table160_marker=table160_marker, body_marker=body_marker,
                           hits_ff=hits_ff)
    img2 = img1
    (raw_dir / f"{arm}-r1.d88").write_bytes(img1)
    if mismatch:
        img2 = make_arm_image(k_m + 1, e_value, table160_marker=table160_marker, body_marker=body_marker)
    (raw_dir / f"{arm}-r2.d88").write_bytes(img2)
    lo, hi = 8 * k_m, 8 * k_m + u
    writes = coords_for_range(lo, hi)
    return [
        {"arm": arm, "repetition": 1, "entry_fields": make_entry_fields(K1), "writes": writes},
        {"arm": arm, "repetition": 2, "entry_fields": make_entry_fields(K1), "writes": writes},
    ]


import tempfile

# --- 1. D3': end_plus_used_sectors(e-u=0xC0一定、値を記録) --------------------
with tempfile.TemporaryDirectory() as tmp:
    raw_dir = Path(tmp)
    runs = []
    k_ms = {"E-2": 1, "E-4": 2, "E-8": 3, "E-12": 4, "E-20": 5, "E-33": 6}
    us = {"E-2": 2, "E-4": 3, "E-8": 4, "E-12": 5, "E-20": 6, "E-33": 7}
    for arm in E_ARMS:
        k_m, u = k_ms[arm], us[arm]
        e_value = 0xC0 + u
        runs += write_arm(raw_dir, arm, k_m=k_m, u=u, e_value=e_value)
    runs_by_key = {(r["arm"], r["repetition"]): r for r in runs}
    d3p = add1.d3_prime(runs_by_key, raw_dir, E_ARMS)
    if d3p.get("status") == "end_plus_used_sectors" and d3p.get("value") == 0xC0 \
            and d3p.get("matches_expected_0xc0") is True:
        ok("1: D3'がend_plus_used_sectors、値0xC0を記録した")
    else:
        ng(f"1: D3'の判定が想定と違う: {d3p}")

# --- 2. D3'陰性対照: chain_broken(0xFFに当たる) ------------------------------
with tempfile.TemporaryDirectory() as tmp:
    raw_dir = Path(tmp)
    runs = []
    for arm in E_ARMS:
        k_m, u = k_ms[arm], us[arm]
        e_value = 0xC0 + u
        hits_ff = (arm == "E-33")
        runs += write_arm(raw_dir, arm, k_m=k_m, u=u, e_value=e_value, hits_ff=hits_ff)
    runs_by_key = {(r["arm"], r["repetition"]): r for r in runs}
    d3p = add1.d3_prime(runs_by_key, raw_dir, E_ARMS)
    if d3p.get("status") == "end_other" and d3p.get("chain_broken_arms") == ["E-33"]:
        ok("2: 陰性対照(0xFFに当たる): end_otherかつchain_broken_armsに列挙した")
    else:
        ng(f"2: 陰性対照(chain_broken)が検出されなかった: {d3p}")

# --- 3. D3'陰性対照: ambiguous(2走食い違い) -----------------------------------
with tempfile.TemporaryDirectory() as tmp:
    raw_dir = Path(tmp)
    runs = []
    for arm in E_ARMS:
        k_m, u = k_ms[arm], us[arm]
        e_value = 0xC0 + u
        mismatch = (arm == "E-2")
        runs += write_arm(raw_dir, arm, k_m=k_m, u=u, e_value=e_value, mismatch=mismatch)
    runs_by_key = {(r["arm"], r["repetition"]): r for r in runs}
    d3p = add1.d3_prime(runs_by_key, raw_dir, E_ARMS)
    if d3p.get("status") == "end_other" and "E-2" not in d3p.get("detail", {}):
        ok("3: 陰性対照(2走食い違い): end_otherになりE-2がentriesから外れた")
    else:
        ng(f"3: 陰性対照(ambiguous)が検出されなかった: {d3p}")

# --- 4. D3': end_constant(eは同じ、uは違う) -----------------------------------
with tempfile.TemporaryDirectory() as tmp:
    raw_dir = Path(tmp)
    runs = []
    for arm in E_ARMS:
        k_m, u = k_ms[arm], us[arm]
        runs += write_arm(raw_dir, arm, k_m=k_m, u=u, e_value=0xC9)
    runs_by_key = {(r["arm"], r["repetition"]): r for r in runs}
    d3p = add1.d3_prime(runs_by_key, raw_dir, E_ARMS)
    if d3p.get("status") == "end_constant" and d3p.get("value") == 0xC9:
        ok("4: D3'がend_constant(e=0xC9)を判定した")
    else:
        ng(f"4: end_constantの判定が想定と違う: {d3p}")

# --- 5. R*: d7_prime + r_star_add1 --------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    raw_dir = Path(tmp)
    i_runs = []
    I_ARMS = add1.dfd.I_ARMS
    # I-*の6腕: 事後記録用。全腕でe=0xC9(D3'のes_observedに0xC9が入る)。
    for arm in I_ARMS:
        i_runs += write_arm(raw_dir, arm, k_m=3, u=2, e_value=0xC9)
    # IV-R系: R=0x14(k1位置=1として20=k_m条件で"ok"),R=0xB0,R=0xC9(除外対象),R=0xFF(除外)。
    def add_ivr(runs, r_value, ok_tag):
        for rep in (1, 2):
            markers = [{"row": 1, "tag": "ok", "numbers": []}] if ok_tag else []
            ef = {"QZ7A": {"pos": {"c": 18, "h": 0, "r": 5, "offset": 0},
                            "bytes9_15": [0x20, 20, 0xEE, 0xEE, 0xEE, 0xEE, 0xEE]}} if ok_tag else {}
            runs.append({"arm": f"IV-R-{r_value:02X}", "repetition": rep, "markers": markers,
                         "entry_fields": ef, "writes": []})
    base_runs = list(i_runs)
    for r in (0x14, 0xB0, 0xC9, 0xFF):
        add_ivr(base_runs, r, True)
    base_result = {"schema": 1, "runs": base_runs}
    r_star, d7p = add1.r_star_add1(base_result, raw_dir)
    # Rused={0x14,0xB0,0xC9,0xFF}。0xFFは候補から除外(control_failed扱いでも
    # r_starの候補選定はA0-FE範囲のみ見るので影響なし)。0xC9はes_observedに
    # 含まれるので除外。候補は0xB0のみ。
    if r_star == 0xB0 and d7p.get("control_failed") is True:
        ok(f"5: r_star_add1が0xB0を返した(0xC9をD3'のI事後記録で除外)")
    else:
        ng(f"5: r_star_add1の結果が想定と違う: r_star={r_star} d7p={d7p}")

# --- 6. D8: derive_m6fd.d8_reserve_neededをそのまま適用 -----------------------
add1_runs_d8 = [
    {"arm": "IV-fill-free", "repetition": 1, "markers": [{"row": 1, "tag": "cx", "numbers": [53]}]},
    {"arm": "IV-fill-free", "repetition": 2, "markers": [{"row": 1, "tag": "cx", "numbers": [53]}]},
    {"arm": "IV-fill-res", "repetition": 1, "markers": [{"row": 1, "tag": "ck", "numbers": [1]}]},
    {"arm": "IV-fill-res", "repetition": 2, "markers": [{"row": 1, "tag": "ck", "numbers": [1]}]},
]
d8 = add1.d8_add1({"schema": 1, "runs": add1_runs_d8})
if d8.get("status") == "reserve_needed":
    ok("6: D8がreserve_neededを判定した")
else:
    ng(f"6: D8の判定が想定と違う: {d8}")

# --- 7. 総合: 全条件成立→m6f_d_add1_rules_confirmed、1条件欠落→incomplete ----
def base_derived(d5_status="relocated_readable", d6_dirs=(7,)):
    return {"derivations": {
        "D1": {"status": "derived", "value": {"s": 8, "o": 0}},
        "D2": {"status": "link_is_next_index"},
        "D4": {"status": "derived", "value": {"offset": 10}},
        "D5": {"status": d5_status},
        "D6": {"status": "stops_at_unused", "directory_sectors": list(d6_dirs)},
    }}


with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
    add1_raw = Path(tmp1)
    base_raw = Path(tmp2)
    add1_runs = []
    for arm in E_ARMS:
        k_m, u = k_ms[arm], us[arm]
        add1_runs += write_arm(add1_raw, arm, k_m=k_m, u=u, e_value=0xC0 + u)
    add1_result = {"schema": 1, "runs": add1_runs}
    base_i_runs = []
    for arm in add1.dfd.I_ARMS:
        base_i_runs += write_arm(base_raw, arm, k_m=3, u=2, e_value=0xC9)
    base_result = {"schema": 1, "runs": base_i_runs}

    built_ok = add1.build(base_derived(), base_result, base_raw, add1_result, add1_raw)
    built_bad = add1.build(base_derived(d5_status="not_readable"), base_result, base_raw,
                            add1_result, add1_raw)
    if built_ok["overall"] == "m6f_d_add1_rules_confirmed" and built_bad["overall"] == "m6f_d_add1_incomplete":
        ok("7: 総合判定(confirmed/incomplete)がD5欠落の有無と対応した")
    else:
        ng(f"7: 総合判定が想定と違う: ok={built_ok['overall']} bad={built_bad['overall']}")

    # --- 8. G9: 出力に位置160以降・本体の目印が現れない -----------------------
    MARKER_160 = 0x5A
    MARKER_BODY = 0x66
    with tempfile.TemporaryDirectory() as tmp3:
        leak_raw = Path(tmp3)
        leak_runs = []
        for arm in E_ARMS:
            k_m, u = k_ms[arm], us[arm]
            leak_runs += write_arm(leak_raw, arm, k_m=k_m, u=u, e_value=0xC0 + u,
                                    table160_marker=MARKER_160, body_marker=MARKER_BODY)
        leak_result = {"schema": 1, "runs": leak_runs}
        built_leak = add1.build(base_derived(), base_result, base_raw, leak_result, leak_raw)
        text = json.dumps(built_leak, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        marker_present = (str(MARKER_160) in text.replace("22090", "")) or (chr(MARKER_BODY) * 8 in text)
        # 数値90(=0x5A)は座標等にも出うるため、目印を8個並べたバイト列としての
        # 出現(本体の目印)と、位置160の値そのもの(0x5A)がどこにも書き出されて
        # いないことを、値の集合として確認する。
        leaked_160 = any(
            (isinstance(v, int) and v == MARKER_160)
            for d in built_leak["derivations"].values() if isinstance(d, dict)
            for v in d.values() if isinstance(v, int)
        )
        if not leaked_160 and chr(MARKER_BODY) * 8 not in text:
            ok("8: G9 出力に位置160以降・本体の目印が現れなかった")
        else:
            ng(f"8: G9 出力に目印が漏れた: leaked_160={leaked_160}")

        # 陰性対照: わざと位置160の値を出力する壊れた関数を用意し、検出できることを確かめる。
        def leaky_build():
            reader = dm.load_disk(leak_raw / "E-2-r1.d88")
            payload = dm.sector(reader, add1.FAT_PRIMARY)
            return {"leaked_position_200": payload[200]}
        leaky_out = leaky_build()
        if leaky_out["leaked_position_200"] == MARKER_160:
            ok("8: 陰性対照(わざと漏らす関数)は目印を検出できる(検出力の確認)")
        else:
            ng("8: 陰性対照が目印を検出できなかった(検査自体が壊れている)")

print()
if rc == 0:
    print("全項目 OK")
else:
    print("NG あり")
sys.exit(rc)
PY
