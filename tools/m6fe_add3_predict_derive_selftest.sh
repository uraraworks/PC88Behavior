#!/usr/bin/env bash
# m6f-e追補3の予測・導出・判定・凍結・漏えい防止を合成署名で検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fe-add3-c.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
python3 "$REPO/tools/make_m6fe_disk.py" --addendum2 "$WORK/add2" >/dev/null
python3 "$REPO/tools/make_m6fe_disk.py" --addendum3 "$WORK/add3" >/dev/null
python3 "$REPO/tools/check_m6fe_candidates.py" --addendum3 "$WORK/add3/manifest.json" \
  >"$WORK/g4.out" 2>"$WORK/g4.err"

REPO="$REPO" WORK="$WORK" python3 - <<'PY'
from __future__ import annotations
import copy, hashlib, json, os, pathlib, subprocess, sys
repo = pathlib.Path(os.environ["REPO"]); work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
import derive_m6fe as derive, predict_m6fe as predict
add2_manifest = predict._manifest(work / "add2/manifest.json", True)
add3_manifest = predict._manifest(work / "add3/manifest.json", addendum3=True)
files_path = repo / "tools/m6fe_add3_candidates_frozen.tsv"
print_path = repo / "tools/m6fe_add3_print_frozen.tsv"
files = derive.load_add3_candidates(files_path)
prints = derive.load_add3_print_candidates(print_path)
base = derive.ADD3_BASE_RULE
canary = "ZQLEAK9"

def fail(label): print("NG " + label); raise SystemExit(1)
def triples(lines): return tuple((v.physical_row, v.char_count, v.sha256) for v in lines)
def summary(tag):
    return {"line_count":1,"char_count":1,"sha256":hashlib.sha256(tag.encode("ascii")).hexdigest()}
def run(tag, lines=(), pending=False):
    s = summary(tag)
    return {"screen":s,"late_screen":dict(s),"entry_lines":[
        {"physical_row":r,"char_count":c,"sha256":h} for r,c,h in lines],
        "input_wait":not pending,"input_pending":pending,"reference_unchanged":True,
        "output_audit_clean":True,"fkey_unchanged":True,"extra_lines_absent":True,
        "g13":{"line_sha":True,"char_count":True,"physical_row":True}}
def add3_doc(print_id, files_id):
    arms = {}
    for arm in predict.ADD3_PRINT_ARMS:
        item = run("p-"+arm, prints[(print_id, arm)])
        arms[arm] = [copy.deepcopy(item), copy.deepcopy(item)]
    for arm in predict.ADD3_FILES_ARMS:
        item = run("f-"+arm, files[(files_id, arm)])
        arms[arm] = [copy.deepcopy(item), copy.deepcopy(item)]
    return {"format":"m6fe-add3-observations-v1","arms":arms}
def add2_doc(add3_id):
    suffix = predict._add3_candidate_parts(add3_id)[1]
    trailing = 3 if suffix == "W" else int(suffix[1:])
    cid = base + f"_T{trailing}"
    arms = {}
    for arm in predict.ADD2_ARMS:
        lines = triples(predict.predict_add2_candidate(add2_manifest, arm, cid))
        item = run("a2-"+arm, lines); item.pop("input_pending")
        arms[arm] = [copy.deepcopy(item), copy.deepcopy(item)]
    return {"format":"m6fe-add2-observations-v1","arms":arms}
def derive_docs(doc3, doc2):
    p3=work/"obs3.json"; p2=work/"obs2.json"
    p3.write_text(json.dumps(doc3,sort_keys=True,separators=(",",":")),encoding="ascii")
    p2.write_text(json.dumps(doc2,sort_keys=True,separators=(",",":")),encoding="ascii")
    arms3,sha3=derive.load_add3_observations(p3); arms2,sha2=derive.load_add2_observations(p2)
    value=derive.derive_add3(arms3,files,prints,arms2)
    value["input_sha256"]=sha3; value["add2_observations_sha256"]=sha2
    return value

# _T2/_T3 は追補2と同じ予測規則。同じ90件媒体の全54候補でバイト一致する。
for cid in predict.candidate_ids():
    for suffix in ("T2","T3"):
        if triples(predict.predict_add3_candidate(add3_manifest,"L90'",cid+"_"+suffix)) != triples(
                predict.predict_add2_candidate(add2_manifest,"L90",cid+"_"+suffix)):
            fail("add2_rule_equivalence_"+suffix)

# Q-Aの2候補はP80で各一意、P79/P81は共通対照。
for q_a in predict.ADD3_PRINT_CANDIDATES:
    value=derive_docs(add3_doc(q_a,base+"_W"),add2_doc(base+"_W"))
    if value["q_a"] != q_a: fail("unique_"+q_a)
control=add3_doc("wrap_then_newline_blank",base+"_W")
control["arms"]["P79"][0]["entry_lines"][0]["sha256"]="0"*64
control["arms"]["P79"][1]["entry_lines"][0]["sha256"]="0"*64
if derive_docs(control,add2_doc(base+"_W"))["q_a"] != "inconclusive_print_control": fail("p79_control")
control=add3_doc("wrap_then_newline_blank",base+"_W")
control["arms"]["P81"][0]["entry_lines"][0]["sha256"]="0"*64
control["arms"]["P81"][1]["entry_lines"][0]["sha256"]="0"*64
if derive_docs(control,add2_doc(base+"_W"))["q_a"] != "inconclusive_print_control": fail("p81_control")
pending=add3_doc("wrap_then_newline_blank",base+"_W")
for item in pending["arms"]["P80"]: item["input_pending"]=True; item["input_wait"]=False
if derive_docs(pending,add2_doc(base+"_W"))["overall"] != "inconclusive_input_limit": fail("input_limit")

# Q-BのT2/T3/Wは、本体確定規則を土台に各1候補だけ残る。
for suffix in ("T2","T3","W"):
    cid=base+"_"+suffix
    value=derive_docs(add3_doc("wrap_then_newline_blank",cid),add2_doc(cid))
    if value["q_b"] != cid or value["candidates"] != [cid]: fail("unique_"+suffix)
    if suffix == "W" and value["l90_comparison"] != "l90_reproduced": fail("l90_reproduced")

# Q-AとQ-Bの不一致、およびL90変化を独立に検出する。
value=derive_docs(add3_doc("wrap_absorbs_newline",base+"_W"),add2_doc(base+"_W"))
if value["overall"] != "inconclusive_add3_disagree": fail("disagree")
changed=add2_doc(base+"_W"); changed["arms"]["L90"][0]["entry_lines"]=[]; changed["arms"]["L90"][1]["entry_lines"]=[]
if derive_docs(add3_doc("wrap_then_newline_blank",base+"_W"),changed)["l90_comparison"] != "l90_changed": fail("l90_changed")

# G9〜G13を1項目ずつ壊し、NG集合を完全一致で照合する。
positive=add3_doc("wrap_then_newline_blank",base+"_W"); mutations={}
d=copy.deepcopy(positive); d["arms"]["P79"][1]["screen"]=summary("different"); d["arms"]["P79"][1]["late_screen"]=summary("different"); mutations["G9"]=d
d=copy.deepcopy(positive); d["arms"]["P79"][0]["late_screen"]=summary("different"); mutations["G10"]=d
d=copy.deepcopy(positive); d["arms"]["P79"][0]["reference_unchanged"]=False; mutations["G11"]=d
d=copy.deepcopy(positive); d["arms"]["P79"][0]["output_audit_clean"]=False; mutations["G12"]=d
d=copy.deepcopy(positive); d["arms"]["P79"][0]["g13"]["line_sha"]=False; mutations["G13"]=d
for wanted,doc in mutations.items():
    value=derive_docs(doc,add2_doc(base+"_W")); failed={k for k,v in value["gates"].items() if not v}
    if failed != {wanted} or value["overall"] != "gate_failed": fail("gate_set_"+wanted)

# 独立判定器の正例。
value=derive_docs(positive,add2_doc(base+"_W")); path=work/"derived.json"
path.write_text(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n",encoding="ascii")
proc=subprocess.run([sys.executable,str(repo/"tools/judge_m6fe.py"),"--addendum3","--derived",str(path)],text=True,capture_output=True)
judged=json.loads(proc.stdout)
if proc.returncode or judged["overall"] != base+"_W" or judged["judgments"][1:] != ["wrap_then_newline_blank",base+"_W","l90_reproduced"]: fail("judge")

# 凍結表の欠落を厳格parserが検出する。
raw=files_path.read_text(encoding="ascii").splitlines(); i=next(i for i,v in enumerate(raw) if v.startswith("summary\t"))
bad=work/"bad-candidates.tsv"; bad.write_text("\n".join(raw[:i]+raw[i+1:])+"\n",encoding="ascii")
try: derive.load_add3_candidates(bad)
except derive.InputError: pass
else: fail("candidate_missing")

# 自作名の漏えい目印は候補表・導出・判定・例外出力に現れない。
leak=copy.deepcopy(add3_manifest); leak["media"]["L81"]["entries"][0]["name"]=canary
leak_path=work/"leak-manifest.json"; leak_path.write_text(json.dumps(leak,sort_keys=True),encoding="ascii")
out=work/"leak.tsv"
proc=subprocess.run([sys.executable,str(repo/"tools/predict_m6fe.py"),"--addendum3",str(leak_path),"--output",str(out)],text=True,capture_output=True)
badobs=work/"bad-observations.json"; badobs.write_text(json.dumps({"format":"m6fe-add3-observations-v1","arms":{},"forbidden":canary}),encoding="ascii")
badproc=subprocess.run([sys.executable,str(repo/"tools/derive_m6fe.py"),"--addendum3","--observations",str(badobs),"--add2-observations",str(work/"obs2.json")],text=True,capture_output=True)
audit=out.read_bytes()+proc.stdout.encode()+proc.stderr.encode()+path.read_bytes()+badproc.stdout.encode()+badproc.stderr.encode()
if proc.returncode or badproc.returncode == 0 or canary.encode() in audit: fail("leak")
negative=work/"leak-negative.txt"; negative.write_text(canary,encoding="ascii")
if canary.encode() not in negative.read_bytes(): fail("leak_negative_control")
print("OK add3_print_files_disagree_freeze_gates_leak")
PY
