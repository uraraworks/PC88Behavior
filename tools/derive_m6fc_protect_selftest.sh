#!/usr/bin/env bash
# tools/derive_m6fc_protect.py の自己検査。合成JSONだけで完結し、公式ROM・
# 公式ディスク・private/には一切触れない。
#
# 検査項目（docs/notes/m6f-c-addendum3-write-protect-sectors.md 第3節）:
#   1. Wclearが非空の場合にQ1がderivedになる。
#   2. Wclearが空の場合(全Wがer&ERR=61)にQ1がnot_foundになる。
#   3. 2走で食い違ったWはrun_disagreementへ列挙され、Wclearから外れる。
#   4. Q2: P13優先(Wclear13が非空ならP13の最小値)。
#   5. Q2: P13が空でP1が非空ならP1へ繰り下がる。
#   6. Q2: 両方空ならprotect_sector_not_found。
#   7. protect_rule()が上記と整合する{"sector":[...],"w":...}またはNoneを返す。
#   8. overallが Q2 の状態と対応する。
#
# 使い方: tools/derive_m6fc_protect_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

out="$(REPO="$REPO" python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

repo = Path(os.environ["REPO"])
sys.path.insert(0, str(repo / "tools"))
import derive_m6fc_protect as d  # noqa: E402

results = {}


def marker_ok():
    return [{"row": 0, "tag": "ok", "numbers": []}]


def marker_er(err, erl=0):
    return [{"row": 0, "tag": "er", "numbers": [err, erl]}]


def run(sector, w, rep, markers, reads=None, writes=None):
    return {"sector": sector, "w": w, "repetition": rep, "markers": markers,
            "reads": reads or [], "writes": writes or [],
            "write_data_count": 0, "drive1_read_count": 0, "drive1_write_count": 0}


# --- 1. P13でWclearが非空(derived) -----------------------------------------
runs = []
for w in range(3):
    if w == 1:
        m1, m2 = marker_ok(), marker_ok()
    else:
        m1, m2 = marker_er(61), marker_er(61)
    runs.append(run("P13", w, 1, m1))
    runs.append(run("P13", w, 2, m2))
    runs.append(run("P1", w, 1, marker_er(61)))
    runs.append(run("P1", w, 2, marker_er(61)))
result1 = {"schema": 1, "runs": runs}
q1_1 = d.q1(result1)
results["wclear_derived_when_nonempty"] = (
    q1_1["P13"]["status"] == "derived" and q1_1["P13"]["value"] == [1]
)
results["wclear_not_found_when_all_blocked"] = (q1_1["P1"]["status"] == "not_found")

# --- 3. 2走食い違い(run_disagreement) --------------------------------------
runs2 = [
    run("P13", 0, 1, marker_ok()), run("P13", 0, 2, marker_er(61)),
    run("P13", 1, 1, marker_ok()), run("P13", 1, 2, marker_ok()),
    run("P1", 0, 1, marker_er(61)), run("P1", 0, 2, marker_er(61)),
]
result2 = {"schema": 1, "runs": runs2}
q1_2 = d.q1(result2)
results["run_disagreement_excluded_from_wclear"] = (
    q1_2["P13"]["status"] == "derived" and q1_2["P13"]["value"] == [1]
    and q1_2["P13"]["run_disagreement"] == [0]
)

# --- 4. Q2: P13優先 ----------------------------------------------------------
q2_priority = d.q2(q1_1)
results["q2_prefers_p13"] = (
    q2_priority["status"] == "derived" and q2_priority["sweep"] == "P13"
    and q2_priority["sector"] == {"c": 18, "h": 1, "r": 13} and q2_priority["w_star"] == 1
)

# --- 5. Q2: P13が空でP1が非空なら繰り下がる ----------------------------------
runs3 = []
for w in range(3):
    runs3.append(run("P13", w, 1, marker_er(61)))
    runs3.append(run("P13", w, 2, marker_er(61)))
    if w == 2:
        m1, m2 = marker_ok(), marker_ok()
    else:
        m1, m2 = marker_er(61), marker_er(61)
    runs3.append(run("P1", w, 1, m1))
    runs3.append(run("P1", w, 2, m2))
result3 = {"schema": 1, "runs": runs3}
q1_3 = d.q1(result3)
q2_fallback = d.q2(q1_3)
results["q2_falls_back_to_p1"] = (
    q2_fallback["status"] == "derived" and q2_fallback["sweep"] == "P1"
    and q2_fallback["sector"] == {"c": 18, "h": 1, "r": 1} and q2_fallback["w_star"] == 2
)

# --- 6. Q2: 両方空(protect_sector_not_found) --------------------------------
runs4 = []
for w in range(2):
    runs4.append(run("P13", w, 1, marker_er(61)))
    runs4.append(run("P13", w, 2, marker_er(61)))
    runs4.append(run("P1", w, 1, marker_er(61)))
    runs4.append(run("P1", w, 2, marker_er(61)))
result4 = {"schema": 1, "runs": runs4}
q1_4 = d.q1(result4)
q2_none = d.q2(q1_4)
results["q2_not_found_when_both_empty"] = (q2_none["status"] == "protect_sector_not_found")

# --- 7. protect_rule()の整合性 ----------------------------------------------
results["protect_rule_matches_q2_priority"] = (
    d.protect_rule(result1) == {"sector": [18, 1, 13], "w": 1}
)
results["protect_rule_matches_q2_fallback"] = (
    d.protect_rule(result3) == {"sector": [18, 1, 1], "w": 2}
)
results["protect_rule_none_when_not_found"] = (d.protect_rule(result4) is None)

# --- 8. overallの整合性 ------------------------------------------------------
build1 = d.build(result1)
build4 = d.build(result4)
results["overall_derived"] = (build1["overall"] == "m6f_c_protect_sector_derived")
results["overall_not_found"] = (build4["overall"] == "protect_sector_not_found")

# --- Q3: 分類と座標列が記録される --------------------------------------------
q3_1 = d.q3(result1)
results["q3_records_classification_and_coords"] = (
    q3_1["P13"]["01"]["repetition1"]["classification"]["tag"] == "ok"
    and q3_1["P13"]["00"]["repetition1"]["classification"]["err"] == 61
)

bad = [k for k, v in results.items() if not v]
for k, v in results.items():
    print(f"{k}={'ok' if v else 'ng'}")
sys.exit(1 if bad else 0)
PY
)"
py_rc=$?
printf '%s\n' "$out"
if [ "$py_rc" -eq 0 ]; then
  ok "derive_m6fc_protect の合成検査がすべて通った"
else
  ng "derive_m6fc_protect の合成検査のいずれかが落ちた"
fi

# --- CLIの動作確認(--result/--output) ---------------------------------------
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cat > "$WORK/result.json" <<'JSON'
{"schema":1,"runs":[
  {"sector":"P13","w":0,"repetition":1,"markers":[{"row":0,"tag":"ok","numbers":[]}],"reads":[],"writes":[],"write_data_count":0,"drive1_read_count":0,"drive1_write_count":0},
  {"sector":"P13","w":0,"repetition":2,"markers":[{"row":0,"tag":"ok","numbers":[]}],"reads":[],"writes":[],"write_data_count":0,"drive1_read_count":0,"drive1_write_count":0},
  {"sector":"P1","w":0,"repetition":1,"markers":[{"row":0,"tag":"er","numbers":[61,20]}],"reads":[],"writes":[],"write_data_count":0,"drive1_read_count":0,"drive1_write_count":0},
  {"sector":"P1","w":0,"repetition":2,"markers":[{"row":0,"tag":"er","numbers":[61,20]}],"reads":[],"writes":[],"write_data_count":0,"drive1_read_count":0,"drive1_write_count":0}
]}
JSON
if python3 "$REPO/tools/derive_m6fc_protect.py" --result "$WORK/result.json" --output "$WORK/out.json" \
  && python3 -c "import json,sys; d=json.load(open('$WORK/out.json')); sys.exit(0 if d['overall']=='m6f_c_protect_sector_derived' else 1)"; then
  ok "CLI: --result/--outputが動作しoverallが正しい"
else
  ng "CLIの動作確認に失敗した"
fi

# 不正な結果JSON(runsが無い)はrc=1でエラーを返す(本文は漏らさない)。
echo '{"schema":1}' > "$WORK/bad_result.json"
python3 "$REPO/tools/derive_m6fc_protect.py" --result "$WORK/bad_result.json" >/dev/null 2>"$WORK/bad.err"
bad_rc=$?
if [ "$bad_rc" -eq 1 ]; then
  ok "不正な結果JSONをrc=1で拒否した"
else
  ng "不正な結果JSONの拒否がrc=1でない(rc=$bad_rc)"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"
