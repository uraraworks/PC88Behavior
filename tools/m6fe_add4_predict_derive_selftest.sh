#!/usr/bin/env bash
# m6f-e追補4の予測・導出・判定・凍結・漏えい防止を合成署名で検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fe-add4-c.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
python3 "$REPO/tools/make_m6fe_disk.py" --addendum3 "$WORK/add3" >/dev/null
python3 "$REPO/tools/check_m6fe_candidates.py" --addendum4 "$WORK/add3/manifest.json" \
  >"$WORK/g4.out" 2>"$WORK/g4.err"

REPO="$REPO" WORK="$WORK" python3 - <<'PY'
from __future__ import annotations
import copy, hashlib, json, os, pathlib, subprocess, sys
repo = pathlib.Path(os.environ["REPO"]); work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
import derive_m6fe as derive, predict_m6fe as predict

lower_path = repo / "tools/m6fe_add4_print_frozen.tsv"
upper_path = repo / "tools/m6fe_add3_print_frozen.tsv"
lower = derive.load_add4_print_candidates(lower_path)
upper = derive.load_add3_print_candidates(upper_path)
base = derive.ADD3_BASE_RULE
q_b_target = base + "_W"
canary = "ZQLEAK4"

def fail(label): print("NG " + label); raise SystemExit(1)
def summary(tag):
    return {"line_count":1,"char_count":1,
            "sha256":hashlib.sha256(tag.encode("ascii")).hexdigest()}
def run(tag, lines=(), pending=False):
    value = summary(tag)
    return {"screen":value,"late_screen":dict(value),"entry_lines":[
        {"physical_row":r,"char_count":c,"sha256":h} for r,c,h in lines],
        "input_wait":not pending,"input_pending":pending,"reference_unchanged":True,
        "output_audit_clean":True,"fkey_unchanged":True,"extra_lines_absent":True,
        "g13":{"line_sha":True,"char_count":True,"physical_row":True}}
def observations(candidate):
    arms = {}
    for arm in predict.ADD3_PRINT_ARMS:
        item = run("p-" + arm, lower[(candidate, arm)])
        arms[arm] = [copy.deepcopy(item), copy.deepcopy(item)]
    return {"format":"m6fe-add4-observations-v1","arms":arms}
def source_doc(q_b=q_b_target):
    return {"format":"m6fe-add3-derived-v1","overall":"inconclusive_print_control",
            "q_a":"inconclusive_print_control","q_b":q_b,
            "gates":{f"G{i}":True for i in range(9,14)},"candidates":[q_b],
            "first_empty_arm":None,"l90_comparison":"l90_reproduced",
            "fkey_unchanged":True,"extra_lines_absent":True,
            "input_sha256":"1"*64,"add2_observations_sha256":"2"*64}
def derive_doc(doc, q_b=q_b_target):
    path = work / "obs.json"
    path.write_text(json.dumps(doc,sort_keys=True,separators=(",",":")),encoding="ascii")
    arms, digest = derive.load_add4_observations(path)
    value = derive.derive_add4(arms, lower, q_b)
    value["input_sha256"] = digest; value["add3_derived_sha256"] = "3"*64
    return value

# 2候補はP80でそれぞれ一意になり、P79/P81は両候補共通の対照になる。
for candidate in predict.ADD3_PRINT_CANDIDATES:
    value = derive_doc(observations(candidate))
    if value["q_a"] != candidate: fail("unique_" + candidate)

# 追補3の大文字表へ戻すと、P79/P81の両方が小文字合成署名と不一致になる。
for arm in ("P79", "P81"):
    for candidate in predict.ADD3_PRINT_CANDIDATES:
        if upper[(candidate, arm)] == lower[(candidate, arm)]:
            fail("uppercase_negative_" + arm)

control = observations("wrap_then_newline_blank")
for item in control["arms"]["P79"]: item["entry_lines"][0]["sha256"] = "0"*64
if derive_doc(control)["q_a"] != "inconclusive_print_control": fail("p79_control")
control = observations("wrap_then_newline_blank")
for item in control["arms"]["P81"]: item["entry_lines"][0]["sha256"] = "0"*64
if derive_doc(control)["q_a"] != "inconclusive_print_control": fail("p81_control")

# 追補3 derived.json からQ-Bを引数で受け、§2.3どおり採否を出す。
source = work / "add3-derived.json"
source.write_text(json.dumps(source_doc(),sort_keys=True,separators=(",",":"))+"\n",encoding="ascii")
q_b, source_sha = derive.load_add3_q_b(source)
if q_b != q_b_target or len(source_sha) != 64: fail("q_b_argument")
positive = observations("wrap_then_newline_blank")
value = derive_doc(positive, q_b)
if not value["adopted"] or value["not_adopted"]: fail("adopted")
if derive_doc(observations("wrap_absorbs_newline"), q_b)["adopted"]: fail("not_adopted_q_a")
if derive_doc(positive, base + "_T2")["adopted"]: fail("not_adopted_q_b")

# G9〜G13を1項目ずつ壊し、NG集合を完全一致で照合する。
mutations = {}
d=copy.deepcopy(positive); d["arms"]["P79"][1]["screen"]=summary("different"); d["arms"]["P79"][1]["late_screen"]=summary("different"); mutations["G9"]=d
d=copy.deepcopy(positive); d["arms"]["P79"][0]["late_screen"]=summary("different"); mutations["G10"]=d
d=copy.deepcopy(positive); d["arms"]["P79"][0]["reference_unchanged"]=False; mutations["G11"]=d
d=copy.deepcopy(positive); d["arms"]["P79"][0]["output_audit_clean"]=False; mutations["G12"]=d
d=copy.deepcopy(positive); d["arms"]["P79"][0]["g13"]["line_sha"]=False; mutations["G13"]=d
for wanted, doc in mutations.items():
    result = derive_doc(doc); failed = {key for key, ok in result["gates"].items() if not ok}
    if failed != {wanted} or result["adopted"] or not result["not_adopted"]:
        fail("gate_set_" + wanted)

# 独立判定器はQ-A名とQ-B候補IDを並べ、採否を真偽で出す。
value = derive_doc(positive, q_b)
value["add3_derived_sha256"] = source_sha
derived_path = work / "derived.json"
derived_path.write_text(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n",encoding="ascii")
proc = subprocess.run([sys.executable,str(repo/"tools/judge_m6fe.py"),"--addendum4",
                       "--derived",str(derived_path)],text=True,capture_output=True)
judged = json.loads(proc.stdout)
if (proc.returncode or judged["judgments"] != ["wrap_then_newline_blank",q_b_target]
        or not judged["adopted"] or judged["not_adopted"]): fail("judge")

# 凍結照合と欠落検出。
raw = lower_path.read_text(encoding="ascii").splitlines()
index = next(i for i,item in enumerate(raw) if item.startswith("summary\t"))
bad = work / "bad.tsv"; bad.write_text("\n".join(raw[:index]+raw[index+1:])+"\n",encoding="ascii")
try: derive.load_add4_print_candidates(bad)
except derive.InputError: pass
else: fail("candidate_missing")

# 合成目印が候補表・導出・判定・例外出力へ漏れない。陰性対照も確認する。
manifest = json.loads((work/"add3/manifest.json").read_text(encoding="ascii"))
manifest["media"]["L81"]["entries"][0]["name"] = canary
leak_manifest = work/"leak-manifest.json"
leak_manifest.write_text(json.dumps(manifest,sort_keys=True),encoding="ascii")
out = work/"leak.tsv"
p = subprocess.run([sys.executable,str(repo/"tools/predict_m6fe.py"),"--addendum4",
                    "--print-predictions",str(leak_manifest),"--output",str(out)],
                   text=True,capture_output=True)
badobs = work/"bad-observations.json"
badobs.write_text(json.dumps({"format":"m6fe-add4-observations-v1","arms":{},
                              "forbidden":canary}),encoding="ascii")
badp = subprocess.run([sys.executable,str(repo/"tools/derive_m6fe.py"),"--addendum4",
                       "--observations",str(badobs),"--add3-derived",str(source)],
                      text=True,capture_output=True)
audit = (out.read_bytes()+p.stdout.encode()+p.stderr.encode()+derived_path.read_bytes()
         +badp.stdout.encode()+badp.stderr.encode())
if p.returncode or badp.returncode == 0 or canary.encode() in audit: fail("leak")
negative = work/"leak-negative.txt"; negative.write_text(canary,encoding="ascii")
if canary.encode() not in negative.read_bytes(): fail("leak_negative_control")
print("OK add4_lowercase_unique_uppercase_negative_freeze_gates_leak")
PY
