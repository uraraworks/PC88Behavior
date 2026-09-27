#!/usr/bin/env bash
# m6f-e追補2ドライバを、公式物を使わず偽フロントエンドで通し検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fe-add2-driver-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

python3 "$REPO/tools/make_m6fe_disk.py" "$WORK/main" >/dev/null
python3 "$REPO/tools/make_m6fe_disk.py" --addendum2 "$WORK/add2" >/dev/null

REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import copy, hashlib, json, os, pathlib, sys
repo = pathlib.Path(os.environ["REPO"]); work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
import derive_m6fe as derive, predict_m6fe as predict
main = predict._manifest(work / "main/manifest.json")
add2 = predict._manifest(work / "add2/manifest.json", True)
base_id = "files_layout_rule_G5_SPLIT63_80DOT_00BLANK_UNITS"
add2_id = base_id + "_T2"

def triples(lines): return tuple((v.physical_row, v.char_count, v.sha256) for v in lines)
def summary(tag): return {"line_count":1,"char_count":1,"sha256":hashlib.sha256(tag.encode()).hexdigest()}
def run(tag, lines=()):
    s=summary(tag)
    return {"screen":s,"late_screen":dict(s),"entry_lines":[
        {"physical_row":r,"char_count":c,"sha256":h} for r,c,h in lines],
        "input_wait":True,"reference_unchanged":True,"output_audit_clean":True,
        "fkey_unchanged":True,"extra_lines_absent":True,
        "g13":{"line_sha":True,"char_count":True,"physical_row":True}}
arms={}
for arm in derive.ALL_ARMS:
    if arm in predict.LAYOUT_ARMS[:-1]:
        lines=triples(predict.predict_candidate(main, arm, base_id))
    elif arm == "L96":
        lines=triples(predict.predict_add2_candidate(add2, "L96'", add2_id))
    else:
        lines=()
    item=run("base-"+arm, lines); arms[arm]=[copy.deepcopy(item),copy.deepcopy(item)]
arms["N-wait"][0]["input_wait"]=False; arms["N-wait"][1]["input_wait"]=False
doc={"format":"m6fe-observations-v1","arms":arms,"aux":{
    "order":"directory_order_skips_deleted","empty":"empty_has_no_entry_rows",
    "overflow":"overflow_other","drive":"default_is_1_explicit_1_2",
    "expression":"drive_expression_accepted","no_media":"files_no_media_waits_for_media"}}
(work / "base-observations.json").write_text(json.dumps(doc,sort_keys=True,separators=(",",":")),encoding="ascii")
PY

FAKE="$WORK/fake_frontend.py"
cat >"$FAKE" <<'PY'
#!/usr/bin/env python3
import hashlib, json, os, pathlib, sys
repo=pathlib.Path(os.environ["M6FE_ADD2_SELFTEST_REPO"]); sys.path.insert(0,str(repo/"tools"))
import predict_m6fe as predict
def one(argv,name):
    try: return argv[argv.index(name)+1]
    except ValueError: return None
def many(argv,name): return [argv[i+1] for i,v in enumerate(argv[:-1]) if v==name]
def hashed(row,body):
    raw=f"{row}\t{body}\n".encode(); return row,len(body),hashlib.sha256(raw).hexdigest()
def report(path,snapshots):
    with path.open("w",encoding="ascii") as out:
        for name,rows in snapshots:
            rows=sorted(rows); out.write(f"snapshot_id\t{name}\nphysical_row\tchar_count\tsha256\n")
            for row,count,digest in rows: out.write(f"{row}\t{count}\t{digest}\n")
            whole=hashlib.sha256("".join(f"{r}\t{c}\t{h}\n" for r,c,h in rows).encode()).hexdigest()
            out.write(f"line_count\t{len(rows)}\nchar_count\t{sum(v[1] for v in rows)}\nsha256\t{whole}\n")
def main():
    argv=sys.argv[1:]; out=pathlib.Path(one(argv,"--out")); io=pathlib.Path(one(argv,"--io-log"))
    arm=out.parent.name.rsplit("-r",1)[0]
    manifest=predict._manifest(pathlib.Path(os.environ["M6FE_ADD2_SELFTEST_MANIFEST"]),True)
    cid="files_layout_rule_G5_SPLIT63_80DOT_00BLANK_UNITS_T2"
    with open(os.environ["M6FE_ADD2_SELFTEST_COUNTER"],"a",encoding="ascii") as f: f.write("1\n")
    with open(os.environ["M6FE_ADD2_SELFTEST_ARGV"],"a",encoding="ascii") as f:
        f.write(json.dumps({"arm":arm,"argv":argv},separators=(",",":"))+"\n")
    entries=[(v.physical_row,v.char_count,v.sha256)
             for v in predict.predict_add2_candidate(manifest,arm,cid)]
    baseline=[hashed(0,"PROMPT"),hashed(19,"FKEY")]
    if os.environ.get("M6FE_ADD2_SELFTEST_BAD_BASELINE"): baseline.append(hashed(5,"X"))
    prompt=max((v[0] for v in entries),default=-1)+1
    final=entries+[hashed(prompt,"PROMPT"),hashed(19,"FKEY")]
    requested={v.split(":",1)[0] for v in many(argv,"--screen-signature-at")}
    snapshots=[("baseline",baseline),("final",final),("late",list(final))]
    report(out,[v for v in snapshots if v[0] in requested])
    io.write_text("# synthetic iolog\n",encoding="ascii")
    return 0
raise SystemExit(main())
PY
chmod +x "$FAKE"
mkdir -p "$WORK/rom" "$WORK/refdisk"
printf '%s' 'SYNTHETIC-REFERENCE-DISK' >"$WORK/refdisk/N88_FE.D88"
COUNTER="$WORK/count.txt"; ARGV_LOG="$WORK/argv.jsonl"

run_driver() {
  local target="$1"; shift
  env M6FE_FRONTEND="$FAKE" M6FE_ADD2_TEST_CORE=selftest-core \
    M6FE_ADD2_SELFTEST_REPO="$REPO" M6FE_ADD2_SELFTEST_MANIFEST="$WORK/add2/manifest.json" \
    M6FE_ADD2_SELFTEST_COUNTER="$COUNTER" M6FE_ADD2_SELFTEST_ARGV="$ARGV_LOG" \
    M6FE_ADD2_TEST_ROM_DIR="$WORK/rom" M6FE_ADD2_TEST_DISK_DIR="$WORK/refdisk" \
    PC88_M6FE_WORK="$target" "$@" "$REPO/tools/measure_m6fe_add2.sh" \
    --base-observations "$WORK/base-observations.json"
}

: >"$COUNTER"; : >"$ARGV_LOG"
run_driver "$WORK/result-positive" M6FE_ADD2_TEST_MODE=1 \
  >"$WORK/positive.out" 2>"$WORK/positive.err"
positive_rc=$?
if [ "$positive_rc" -eq 0 ] && [ "$(wc -l <"$COUNTER" | tr -d ' ')" = 10 ] \
  && grep -q 'judgment=files_layout_rule_G5_SPLIT63_80DOT_00BLANK_UNITS_T2' "$WORK/positive.out"; then
  ok "偽フロントエンドで5腕×2走を完走した"
else
  ng "通し正例が失敗した(rc=$positive_rc)"
  tail -20 "$WORK/positive.out" "$WORK/positive.err"
fi
if python3 - "$WORK/result-positive" "$ARGV_LOG" <<'PY'
import json,pathlib,sys
result,log=map(pathlib.Path,sys.argv[1:])
judge=json.loads((result/"judgment.json").read_text(encoding="ascii"))
summary=json.loads((result/"summary.json").read_text(encoding="ascii"))
obs=json.loads((result/"observations.json").read_text(encoding="ascii"))
assert judge["overall"].endswith("_T2") and judge["judgments"][-1]=="l96_reproduced"
assert summary["run_count"]==summary["frontend_launch_count"]==10
assert set(obs["arms"])=={"L80","L85","L90","L95","L96'"}
calls=[json.loads(line) for line in log.read_text(encoding="ascii").splitlines()]
assert len(calls)==10
for call in calls:
    argv=call["argv"]
    assert "--screen-signature-only" in argv
    assert argv[argv.index("--frames")+1]=="12000"
    assert argv[argv.index("--type-at",argv.index("--type-at")+1)+1]=="500"
PY
then ok "出力契約・L96再現判定・12000フレームを確認した"
else ng "通し正例の出力契約が不正"; fi

for gate in G0 G1 G2 G3 G4 G5 G6 G7 G8; do
  : >"$COUNTER"; : >"$ARGV_LOG"
  run_driver "$WORK/result-$gate" M6FE_ADD2_TEST_MODE=1 M6FE_ADD2_TEST_FAST_GATES=1 \
    M6FE_ADD2_TEST_FAIL_GATE="$gate" >"$WORK/$gate.out" 2>"$WORK/$gate.err"
  gate_rc=$?
  if [ "$gate_rc" -ne 0 ] && [ ! -s "$COUNTER" ] && python3 - "$WORK/$gate.out" "$gate" <<'PY'
import json,pathlib,sys
v=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="ascii"))
raise SystemExit(0 if v.get("failed_gates")==[sys.argv[2]] and v.get("frontend_launch_count")==0 else 1)
PY
  then ok "$gate 陰性対照はNG集合={$gate}、起動回数0"
  else ng "$gate 陰性対照の停止条件が不正"; fi
done

: >"$COUNTER"; : >"$ARGV_LOG"
run_driver "$WORK/result-g14" M6FE_ADD2_TEST_MODE=1 M6FE_ADD2_TEST_FAST_GATES=1 \
  M6FE_ADD2_SELFTEST_BAD_BASELINE=1 >"$WORK/g14.out" 2>"$WORK/g14.err"
g14_rc=$?
if [ "$g14_rc" -eq 0 ] && [ "$(wc -l <"$COUNTER" | tr -d ' ')" = 1 ] \
  && grep -q 'judgment=inconclusive_cls_baseline' "$WORK/g14.out"; then
  ok "G14陰性対照は最初の走で停止した"
else ng "G14陰性対照が専用判定で停止しない"; fi

if [ "$rc" -eq 0 ]; then printf '%s\n' '全項目 OK'; else printf '%s\n' 'NG あり'; fi
exit "$rc"
