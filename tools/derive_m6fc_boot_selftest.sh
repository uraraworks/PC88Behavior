#!/usr/bin/env bash
# tools/derive_m6fc_boot.py の自己検査。合成のresult JSONだけで完結し、
# 公式ROM・公式ディスクには触れない。
#
# 検査項目:
#   1. 基本シナリオ: 2走ともZQbtが出たXの集合がB1.value、X*はその最小値、
#      overall=m6f_c_boot_addendum1_ok。
#   2. 陰性対照: 2走で食い違ったXはB1.run_disagreementに載り、Xbootから外れる。
#   3. Xboot が空ならB1=not_found、overall=not_found、boot_fill_star()はNone。
#   4. B2: 先頭4個の初出順座標と(0,0,1)の読み回数が正しく数えられる。
#   5. B2 陰性対照: 2走のreadsが食い違うとそのXはambiguousになる。
#   6. boot_fill_star() が derive_m6fc_boot.build() のx_starと一致する。
#
# 使い方: tools/derive_m6fc_boot_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

out="$(python3 - "$REPO" <<'PY'
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "tools"))
import derive_m6fc_boot as d  # noqa: E402

rc = 0


def ok(msg):
    print(f"OK: {msg}")


def ng(msg):
    global rc
    print(f"NG: {msg}")
    rc = 1


def marker(tag, numbers=None):
    return {"row": 1, "tag": tag, "numbers": numbers or []}


def run(x, rep, bt, reads=None):
    return {
        "arm": f"BX-{x:02X}", "x": x, "repetition": rep,
        "markers": [marker("bt")] if bt else [],
        "reads": reads or [], "read_001_count": sum(1 for c in (reads or [])
                                                      if (c["c"], c["h"], c["r"]) == (0, 0, 1)),
        "write_data_count": 0,
    }


# --- 1. 基本シナリオ ---------------------------------------------------------
runs = []
for x in range(256):
    boots = x in (0x00, 0x0F, 0xFF)
    runs.append(run(x, 1, boots))
    runs.append(run(x, 2, boots))
result = {"schema": 1, "runs": runs}
b1 = d.boot_capable_values(result)
if b1["status"] == "derived" and b1["value"] == [0, 15, 255]:
    ok("B1: 2走とも起動できたXの集合がXboot")
else:
    ng(f"B1の基本シナリオが期待と違う: {b1}")

x_star = d.boot_fill_star(result)
if x_star == 0:
    ok("X*はXbootの最小値")
else:
    ng(f"X*が期待と違う: {x_star}")

built = d.build(result)
if built["overall"] == "m6f_c_boot_addendum1_ok" and built["x_star"] == 0:
    ok("build()のoverall/x_starが正しい")
else:
    ng(f"build()のoverallが期待と違う: {built}")

# --- 2. 陰性対照: 2走食い違い -------------------------------------------------
runs2 = list(runs)
# X=0x10は本来falseだが、rep1だけtrueにして食い違わせる。
for i, r in enumerate(runs2):
    if r["x"] == 0x10 and r["repetition"] == 1:
        runs2[i] = run(0x10, 1, True)
result2 = {"schema": 1, "runs": runs2}
b1b = d.boot_capable_values(result2)
if 0x10 in b1b["run_disagreement"] and 0x10 not in b1b["value"]:
    ok("陰性対照: 2走食い違いのXはrun_disagreementに載りXbootから外れる")
else:
    ng(f"食い違い検出に失敗: {b1b}")

# --- 3. Xbootが空 -------------------------------------------------------------
runs3 = [run(x, rep, False) for x in range(256) for rep in (1, 2)]
result3 = {"schema": 1, "runs": runs3}
b1c = d.boot_capable_values(result3)
if b1c["status"] == "not_found":
    ok("Xbootが空ならB1=not_found")
else:
    ng(f"空集合の判定が期待と違う: {b1c}")
if d.boot_fill_star(result3) is None:
    ok("Xbootが空ならboot_fill_star()はNone")
else:
    ng("boot_fill_star()がNoneを返さなかった")
built3 = d.build(result3)
if built3["overall"] == "not_found" and built3["x_star"] is None:
    ok("build()もXboot空でoverall=not_found")
else:
    ng(f"build()の空集合overallが期待と違う: {built3}")

# --- 4. B2: 先頭4個と(0,0,1)の読み回数 ---------------------------------------
reads = (
    [{"c": 0, "h": 0, "r": 1}] * 3
    + [{"c": 0, "h": 0, "r": 2}]
    + [{"c": 0, "h": 0, "r": 1}]
    + [{"c": 1, "h": 0, "r": 3}, {"c": 2, "h": 1, "r": 5}, {"c": 9, "h": 0, "r": 1}]
)
runs4 = [run(0x20, 1, True, reads), run(0x20, 2, True, reads)]
result4 = {"schema": 1, "runs": runs4}
b2 = d.next_read(result4)
entry = b2["20"]
expect_first4 = [{"c": 0, "h": 0, "r": 1}, {"c": 0, "h": 0, "r": 2},
                  {"c": 1, "h": 0, "r": 3}, {"c": 2, "h": 1, "r": 5}]
if entry["status"] == "derived" and entry["first4"] == expect_first4 and entry["boot_sector_read_count"] == 4:
    ok("B2: 初出順の先頭4個と(0,0,1)の読み回数が正しい")
else:
    ng(f"B2の集計が期待と違う: {entry}")

# --- 5. B2 陰性対照: 2走のreadsが食い違う -------------------------------------
runs5 = [run(0x21, 1, True, reads), run(0x21, 2, True, reads[:2])]
result5 = {"schema": 1, "runs": runs5}
b2b = d.next_read(result5)
entry5 = b2b["21"]
if entry5["status"] == "ambiguous":
    ok("陰性対照: B2の2走readsが食い違うとambiguousになる")
else:
    ng(f"B2の食い違い検出に失敗: {entry5}")

sys.exit(rc)
PY
)"
rc=$?
printf '%s\n' "$out"
exit "$rc"
