#!/usr/bin/env bash
# m6f-e追補2の162候補・導出・判定・漏えい防止を合成署名だけで検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fe-add2-c.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
python3 "$REPO/tools/make_m6fe_disk.py" "$WORK/main" >/dev/null
python3 "$REPO/tools/make_m6fe_disk.py" --addendum2 "$WORK/add2" >/dev/null
python3 "$REPO/tools/check_m6fe_candidates.py" --addendum2 "$WORK/add2/manifest.json" \
  >"$WORK/g4.out" 2>"$WORK/g4.err"

REPO="$REPO" WORK="$WORK" python3 - <<'PY'
from __future__ import annotations
import copy, hashlib, json, os, pathlib, subprocess, sys
repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
import derive_m6fe as derive
import predict_m6fe as predict

main_manifest = predict._manifest(work / "main/manifest.json")
add2_manifest = predict._manifest(work / "add2/manifest.json", True)
main_candidates = derive.load_candidates(repo / "tools/m6fe_candidates_frozen.tsv")
add2_path = repo / "tools/m6fe_add2_candidates_frozen.tsv"
add2_candidates = derive.load_add2_candidates(add2_path)
base_id = "files_layout_rule_G5_SPLIT63_80DOT_00BLANK_UNITS"
canary = "ZQLEAK9"

def fail(label):
    print("NG " + label)
    raise SystemExit(1)

def triples(lines):
    return tuple((v.physical_row, v.char_count, v.sha256) for v in lines)

def summary(tag):
    return {"line_count": 1, "char_count": 1,
            "sha256": hashlib.sha256(tag.encode("ascii")).hexdigest()}

def make_run(tag, lines=()):
    screen = summary(tag)
    return {"screen": screen, "late_screen": dict(screen),
            "entry_lines": [{"physical_row": row, "char_count": count, "sha256": digest}
                            for row, count, digest in lines],
            "input_wait": True, "reference_unchanged": True,
            "output_audit_clean": True, "fkey_unchanged": True,
            "extra_lines_absent": True,
            "g13": {"line_sha": True, "char_count": True, "physical_row": True}}

def main_observations(l96_lines):
    arms = {}
    for arm in derive.ALL_ARMS:
        if arm in predict.LAYOUT_ARMS[:-1]:
            lines = main_candidates[(base_id, arm)]
        elif arm == "L96":
            lines = l96_lines
        else:
            lines = ()
        run = make_run("base-" + arm, lines)
        arms[arm] = [copy.deepcopy(run), copy.deepcopy(run)]
    arms["N-wait"][0]["input_wait"] = False
    arms["N-wait"][1]["input_wait"] = False
    return {"format": "m6fe-observations-v1", "arms": arms,
            "aux": {"order": "directory_order_skips_deleted",
                    "empty": "empty_has_no_entry_rows", "overflow": "overflow_other",
                    "drive": "default_is_1_explicit_1_2",
                    "expression": "drive_expression_accepted",
                    "no_media": "files_no_media_waits_for_media"}}

def add2_observations(candidate):
    arms = {}
    for arm in predict.ADD2_ARMS:
        lines = add2_candidates[(candidate, arm)]
        run = make_run("add2-" + arm, lines)
        arms[arm] = [copy.deepcopy(run), copy.deepcopy(run)]
    return {"format": "m6fe-add2-observations-v1", "arms": arms}

def load_docs(add2_doc, base_doc):
    apath = work / "add2-observations.json"
    bpath = work / "base-observations.json"
    apath.write_text(json.dumps(add2_doc, sort_keys=True, separators=(",", ":")), encoding="ascii")
    bpath.write_text(json.dumps(base_doc, sort_keys=True, separators=(",", ":")), encoding="ascii")
    add2_arms, add2_sha = derive.load_add2_observations(apath)
    base_arms, _aux, base_sha = derive.load_observations(bpath)
    return add2_arms, add2_sha, base_arms, base_sha, apath, bpath

# T1は本体予測器と同じ。全54候補について同一媒体L96/L96'を比較する。
for candidate in predict.candidate_ids():
    if triples(predict.predict_candidate(main_manifest, "L96", candidate)) != triples(
            predict.predict_add2_candidate(add2_manifest, "L96'", candidate + "_T1")):
        fail("t1_main_equivalence")

# L80は本体で残ったG5規則についてTに依存しない対照。
values = {triples(predict.predict_add2_candidate(
    add2_manifest, "L80", base_id + f"_T{t}")) for t in (1, 2, 3)}
if len(values) != 1:
    fail("l80_invariant")

# 本体L0〜L11で54候補を絞った上で、T1/T2/T3が各1候補だけ残る。
for trailing in (1, 2, 3):
    intended = base_id + f"_T{trailing}"
    add2_doc = add2_observations(intended)
    l96_lines = tuple((v["physical_row"], v["char_count"], v["sha256"])
                      for v in add2_doc["arms"]["L96'"][0]["entry_lines"])
    loaded = load_docs(add2_doc, main_observations(l96_lines))
    add2_arms, add2_sha, base_arms, base_sha, apath, bpath = loaded
    result = derive.derive_add2(add2_arms, add2_candidates, base_arms, main_candidates)
    result["input_sha256"] = add2_sha
    result["base_observations_sha256"] = base_sha
    if result["overall"] != intended or result["candidates"] != [intended]:
        fail(f"unique_t{trailing}")
    if result["l96_comparison"] != "l96_reproduced":
        fail(f"l96_reproduced_t{trailing}")
    derived_path = work / f"derived-t{trailing}.json"
    derived_path.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n",
                            encoding="ascii")
    proc = subprocess.run([sys.executable, str(repo / "tools/judge_m6fe.py"),
                           "--addendum2", "--derived", str(derived_path)],
                          text=True, capture_output=True)
    value = json.loads(proc.stdout)
    if proc.returncode != 0 or value["judgments"] != [intended, "l96_reproduced"]:
        fail(f"judge_t{trailing}")

# L96比較の陰性対照。
doc = add2_observations(base_id + "_T2")
base = main_observations(())
add2_arms, _, base_arms, _, _, _ = load_docs(doc, base)
changed = derive.derive_add2(add2_arms, add2_candidates, base_arms, main_candidates)
if changed["l96_comparison"] != "l96_changed":
    fail("l96_changed")

# G9〜G13を1項目ずつ壊し、NG集合を完全一致で照合する。
positive = add2_observations(base_id + "_T2")
l96_lines = tuple((v["physical_row"], v["char_count"], v["sha256"])
                  for v in positive["arms"]["L96'"][0]["entry_lines"])
base = main_observations(l96_lines)
mutations = {}
doc = copy.deepcopy(positive); doc["arms"]["L80"][1]["screen"] = summary("different"); doc["arms"]["L80"][1]["late_screen"] = summary("different"); mutations["G9"] = doc
doc = copy.deepcopy(positive); doc["arms"]["L80"][0]["late_screen"] = summary("different"); mutations["G10"] = doc
doc = copy.deepcopy(positive); doc["arms"]["L80"][0]["reference_unchanged"] = False; mutations["G11"] = doc
doc = copy.deepcopy(positive); doc["arms"]["L80"][0]["output_audit_clean"] = False; mutations["G12"] = doc
doc = copy.deepcopy(positive); doc["arms"]["L80"][0]["g13"]["line_sha"] = False; mutations["G13"] = doc
for wanted, doc in mutations.items():
    add2_arms, _, base_arms, _, _, _ = load_docs(doc, base)
    value = derive.derive_add2(add2_arms, add2_candidates, base_arms, main_candidates)
    failed = {gate for gate, passed in value["gates"].items() if not passed}
    if failed != {wanted} or value["overall"] != "gate_failed":
        fail("gate_set_" + wanted)

# 凍結候補表のsummary欠落・重複を厳格parserが検出する。
raw = add2_path.read_text(encoding="ascii").splitlines()
index = next(i for i, line in enumerate(raw) if line.startswith("summary\t"))
for label, lines in (("missing", raw[:index] + raw[index + 1:]),
                     ("duplicate", raw + [raw[index]])):
    path = work / f"candidates-{label}.tsv"
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    try:
        derive.load_add2_candidates(path)
    except derive.InputError:
        pass
    else:
        fail("candidate_" + label)

# 漏えい目印は予測表・stdout/stderr・例外経路に現れない。
leak = copy.deepcopy(add2_manifest)
leak["media"]["L80"]["entries"][0]["name"] = canary
leak_path = work / "leak-manifest.json"
leak_path.write_text(json.dumps(leak, sort_keys=True), encoding="ascii")
out_path = work / "leak-candidates.tsv"
proc = subprocess.run([sys.executable, str(repo / "tools/predict_m6fe.py"),
                       "--addendum2", str(leak_path), "--output", str(out_path)],
                      text=True, capture_output=True)
if proc.returncode != 0:
    fail("leak_predict")
leak_table = derive.load_add2_candidates(out_path)
leak_doc = {"format": "m6fe-add2-observations-v1", "arms": {}}
for arm in predict.ADD2_ARMS:
    item = make_run("leak-" + arm, leak_table[(base_id + "_T2", arm)])
    leak_doc["arms"][arm] = [copy.deepcopy(item), copy.deepcopy(item)]
l96_lines = tuple((v["physical_row"], v["char_count"], v["sha256"])
                  for v in leak_doc["arms"]["L96'"][0]["entry_lines"])
leak_arms, leak_sha, base_arms, base_sha, _, leak_base_path = load_docs(
    leak_doc, main_observations(l96_lines))
leak_derived = derive.derive_add2(leak_arms, leak_table, base_arms, main_candidates)
leak_derived["input_sha256"] = leak_sha
leak_derived["base_observations_sha256"] = base_sha
leak_derived_path = work / "leak-derived.json"
leak_derived_path.write_text(json.dumps(leak_derived, sort_keys=True, separators=(",", ":")) + "\n",
                             encoding="ascii")
judge = subprocess.run([sys.executable, str(repo / "tools/judge_m6fe.py"), "--addendum2",
                        "--derived", str(leak_derived_path)], text=True, capture_output=True)
signature_report = work / "signature-report.tsv"
signature_report.write_text(
    "physical_row\tchar_count\tsha256\n0\t7\t" +
    hashlib.sha256(("0\t" + canary + "\n").encode()).hexdigest() + "\n", encoding="ascii")
bad = work / "bad-observations.json"
bad.write_text(json.dumps({"format": "m6fe-add2-observations-v1", "arms": {},
                           "forbidden": canary}), encoding="ascii")
bad_proc = subprocess.run([sys.executable, str(repo / "tools/derive_m6fe.py"), "--addendum2",
                           "--observations", str(bad), "--base-observations", str(leak_base_path)],
                          text=True, capture_output=True)
audit = (out_path.read_bytes() + proc.stdout.encode() + proc.stderr.encode()
         + leak_derived_path.read_bytes() + judge.stdout.encode() + judge.stderr.encode()
         + signature_report.read_bytes() + bad_proc.stdout.encode() + bad_proc.stderr.encode())
if canary.encode("ascii") in audit or judge.returncode != 0 or bad_proc.returncode == 0:
    fail("leak_output")
broken = work / "broken-output.txt"
broken.write_text(canary, encoding="ascii")
if canary.encode("ascii") not in broken.read_bytes():
    fail("leak_negative_control")

print("OK add2_t1_t2_t3_l80_freeze_gates_leak")
PY
