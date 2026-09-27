#!/usr/bin/env bash
# m6f-gの191候補、動的G-M、3桁、判定、漏えい防止を合成署名で検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fg-predict.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
python3 "$REPO/tools/make_m6fg_disk.py" "$WORK/media" >/dev/null
python3 "$REPO/tools/check_m6fg_candidates.py" "$WORK/media/manifest.json" \
  >"$WORK/g4.out" 2>"$WORK/g4.err"

REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import copy, hashlib, json, os, pathlib, subprocess, sys
repo=pathlib.Path(os.environ["REPO"]); work=pathlib.Path(os.environ["WORK"])
sys.path.insert(0,str(repo/"tools"))
import derive_m6fg as derive, predict_m6fg as predict
manifest=predict._manifest(work/"media/manifest.json")
candidates=derive.load_candidates(repo/"tools/m6fg_candidates_frozen.tsv")
canary="QZLEAK9"
def fail(label): print("NG "+label); raise SystemExit(1)
def triples(lines): return tuple((x.physical_row,x.char_count,x.sha256) for x in lines)
def summary(tag):
 return {"line_count":1,"char_count":1,"sha256":hashlib.sha256(tag.encode("ascii")).hexdigest()}
def run(tag,lines):
 s=summary(tag)
 return {"screen":s,"late_screen":dict(s),"entry_lines":[
  {"physical_row":r,"char_count":c,"sha256":h} for r,c,h in lines],
  "input_wait":True,"reference_unchanged":True,"output_audit_clean":True,
  "fkey_unchanged":True,"extra_lines_absent":True,
  "g13":{"line_sha":True,"char_count":True,"physical_row":True}}
def document(p_id,b_id,mixed=True,size_min=True):
 arms={}
 for arm,cid in (("G-P",p_id),("G-B",b_id)):
  item=run(arm,candidates[(cid,arm)]); arms[arm]=[copy.deepcopy(item),copy.deepcopy(item)]
 mlines=triples(predict.predict_mixed(manifest,p_id,b_id))
 if not mixed:
  mlines=((mlines[0][0],mlines[0][1],"0"*64),)+mlines[1:]
 item=run("G-M",mlines); arms["G-M"]=[copy.deepcopy(item),copy.deepcopy(item)]
 for arm in predict.SIZE_ARMS:
  lines=candidates[("size_min_digits",arm)]
  if not size_min and arm=="G-Z2": lines=((lines[0][0],lines[0][1],"0"*64),)
  item=run(arm,lines); arms[arm]=[copy.deepcopy(item),copy.deepcopy(item)]
 return {"format":"m6fg-observations-v1","arms":arms}
def derive_doc(doc):
 path=work/"current.json"; path.write_text(json.dumps(doc,sort_keys=True,separators=(",",":")),encoding="ascii")
 arms,digest=derive.load_observations(path); value=derive.derive(arms,candidates,manifest); value["input_sha256"]=digest
 return value

tests=(("mark_2A","mark_50"),("mark_2A_nosize","mark_50_nosize"),("hidden","hidden"))
for p_id,b_id in tests:
 value=derive_doc(document(p_id,b_id))
 if value["mark_candidates"]!={"G-P":[p_id],"G-B":[b_id]}: fail("unique_"+p_id)
 if value["mixed_judgment"]!="mixed_row_consistent": fail("mixed_consistent_"+p_id)
 if value["size_judgment"]!="size_min_digits": fail("size_min_"+p_id)
positive=derive_doc(document("mark_2A","mark_50"))
if derive_doc(document("mark_2A","mark_50",mixed=False))["mixed_judgment"]!="mixed_row_inconsistent": fail("mixed_inconsistent")
if derive_doc(document("mark_2A","mark_50",size_min=False))["size_judgment"]!="size_other": fail("size_other")

# 1文字署名の破壊は候補集合を空にし、欠落・重複summaryも厳格に拒否する。
broken=document("mark_2A","mark_50"); broken["arms"]["G-P"][0]["entry_lines"][0]["sha256"]="0"*64; broken["arms"]["G-P"][1]["entry_lines"][0]["sha256"]="0"*64
if derive_doc(broken)["mark_judgments"]["G-P"]!="inconclusive_G-P_no_candidate": fail("no_candidate")
raw=(repo/"tools/m6fg_candidates_frozen.tsv").read_text(encoding="ascii").splitlines()
index=next(i for i,x in enumerate(raw) if x.startswith("summary\t"))
for label,lines in (("missing",raw[:index]+raw[index+1:]),("duplicate",raw+[raw[index]])):
 path=work/(label+".tsv"); path.write_text("\n".join(lines)+"\n",encoding="ascii")
 try: derive.load_candidates(path)
 except derive.InputError: pass
 else: fail("table_"+label)

# G9〜G13は壊した1項目だけをNG集合へ出す。
mutations={}
d=document("mark_2A","mark_50"); d["arms"]["G-P"][1]["screen"]=summary("different"); d["arms"]["G-P"][1]["late_screen"]=summary("different"); mutations["G9"]=d
d=document("mark_2A","mark_50"); d["arms"]["G-P"][0]["late_screen"]=summary("different"); mutations["G10"]=d
d=document("mark_2A","mark_50"); d["arms"]["G-P"][0]["reference_unchanged"]=False; mutations["G11"]=d
d=document("mark_2A","mark_50"); d["arms"]["G-P"][0]["output_audit_clean"]=False; mutations["G12"]=d
d=document("mark_2A","mark_50"); d["arms"]["G-P"][0]["g13"]["line_sha"]=False; mutations["G13"]=d
for wanted,doc in mutations.items():
 value=derive_doc(doc); failed={key for key,passed in value["gates"].items() if not passed}
 if failed!={wanted} or value["overall"]!="gate_failed": fail("gate_"+wanted)

# 独立判定器と全判定名。
path=work/"derived.json"; path.write_text(json.dumps(positive,sort_keys=True,separators=(",",":"))+"\n",encoding="ascii")
p=subprocess.run([sys.executable,str(repo/"tools/judge_m6fg.py"),"--derived",str(path)],text=True,capture_output=True)
value=json.loads(p.stdout)
if p.returncode or value["judgments"]!=["mark_2A","mark_50","mixed_row_consistent","size_min_digits"]: fail("judge")
bad=copy.deepcopy(positive); bad["mixed_judgment"]="mixed_row_inconsistent"
badpath=work/"bad-derived.json"; badpath.write_text(json.dumps(bad),encoding="ascii")
p=subprocess.run([sys.executable,str(repo/"tools/judge_m6fg.py"),"--derived",str(badpath)],text=True,capture_output=True)
if p.returncode!=2 or json.loads(p.stdout)["judgments"]!=["gate_failed"]: fail("judge_negative")

# 合成本文の目印が候補表・JSON・標準出力・例外へ出ないことと、その陰性対照。
leak=copy.deepcopy(manifest)
for definition in leak["media"].values(): definition["entries"][0]["name"]=canary
payload=predict.render_candidates(leak)
if canary.encode("ascii") in payload: fail("leak_candidates")
badobs=work/"badobs.json"; badobs.write_text(json.dumps({"format":"m6fg-observations-v1","arms":{},"marker":canary}),encoding="ascii")
p=subprocess.run([sys.executable,str(repo/"tools/derive_m6fg.py"),"--observations",str(badobs),
                  "--manifest",str(work/"media/manifest.json")],text=True,capture_output=True)
if p.returncode!=2 or canary in p.stdout+p.stderr: fail("leak_exception")
broken_output=work/"broken-output"; broken_output.write_text(canary,encoding="ascii")
if canary.encode("ascii") not in broken_output.read_bytes(): fail("leak_negative_control")
print("OK m6f-g予測導出: 印・nosize・hidden・G-M・3桁・NG集合・漏えい陰性対照")
PY
