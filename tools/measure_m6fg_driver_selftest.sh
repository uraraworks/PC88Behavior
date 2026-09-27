#!/usr/bin/env bash
# m6f-gドライバを公式物なしの偽フロントエンドで検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fg-driver-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok(){ printf 'OK: %s\n' "$1"; }
ng(){ printf 'NG: %s\n' "$1"; rc=1; }
python3 "$REPO/tools/make_m6fg_disk.py" "$WORK/media" >/dev/null

FAKE="$WORK/fake_frontend.py"
printf '%s\n' '#!/usr/bin/env python3' >"$FAKE"
printf '%s\n' 'import hashlib,json,os,pathlib,sys' >>"$FAKE"
printf '%s\n' 'repo=pathlib.Path(os.environ["M6FG_SELFTEST_REPO"]); sys.path.insert(0,str(repo/"tools")); import predict_m6fg as p' >>"$FAKE"
printf '%s\n' 'def one(a,n):' ' try:return a[a.index(n)+1]' ' except ValueError:return None' >>"$FAKE"
printf '%s\n' 'def many(a,n):return [a[i+1] for i,v in enumerate(a[:-1]) if v==n]' >>"$FAKE"
printf '%s\n' 'def hashed(r,b):' ' raw=f"{r}\t{b}\n".encode(); return r,len(b),hashlib.sha256(raw).hexdigest()' >>"$FAKE"
printf '%s\n' 'def report(path,snaps):' ' with path.open("w",encoding="ascii") as out:' '  for name,rows in snaps:' '   rows=sorted(rows); out.write(f"snapshot_id\t{name}\nphysical_row\tchar_count\tsha256\n")' '   for r,c,h in rows:out.write(f"{r}\t{c}\t{h}\n")' '   whole=hashlib.sha256("".join(f"{r}\t{c}\t{h}\n" for r,c,h in rows).encode()).hexdigest()' '   out.write(f"line_count\t{len(rows)}\nchar_count\t{sum(x[1] for x in rows)}\nsha256\t{whole}\n")' >>"$FAKE"
printf '%s\n' 'def main():' ' a=sys.argv[1:]; out=pathlib.Path(one(a,"--out")); io=pathlib.Path(one(a,"--io-log")); arm=out.parent.name.rsplit("-r",1)[0]' ' manifest=p._manifest(pathlib.Path(os.environ["M6FG_SELFTEST_MANIFEST"]))' ' with open(os.environ["M6FG_SELFTEST_COUNTER"],"a") as f:f.write("1\n")' ' if arm=="G-P": lines=p.predict_mark(manifest,arm,"mark_2A")' ' elif arm=="G-B": lines=p.predict_mark(manifest,arm,"mark_50")' ' elif arm=="G-M": lines=p.predict_mixed(manifest,"mark_2A","mark_50")' ' else: lines=p.predict_size(manifest,arm)' ' signed=[(x.physical_row,x.char_count,x.sha256) for x in lines]' ' prompt=max((x[0] for x in signed),default=-1)+1' ' baseline=[hashed(0,"PROMPT"),hashed(19,"FKEY")]' ' if os.environ.get("M6FG_SELFTEST_BAD_BASELINE"):baseline.append(hashed(5,"X"))' ' final=signed+[hashed(prompt,"PROMPT"),hashed(19,"FKEY")]' ' wanted={x.split(":",1)[0] for x in many(a,"--screen-signature-at")}' ' report(out,[x for x in (("baseline",baseline),("final",final),("late",list(final))) if x[0] in wanted])' ' io.write_text("# synthetic iolog\n",encoding="ascii"); return 0' 'raise SystemExit(main())' >>"$FAKE"
chmod +x "$FAKE"
mkdir -p "$WORK/rom" "$WORK/refdisk"
printf '%s' 'SYNTHETIC-REFERENCE-DISK' >"$WORK/refdisk/N88_FE.D88"
COUNTER="$WORK/count.txt"

run_driver(){
  local target="$1"; shift
  env M6FG_FRONTEND="$FAKE" M6FG_TEST_CORE=selftest-core \
    M6FG_SELFTEST_REPO="$REPO" M6FG_SELFTEST_MANIFEST="$WORK/media/manifest.json" \
    M6FG_SELFTEST_COUNTER="$COUNTER" M6FG_TEST_ROM_DIR="$WORK/rom" \
    M6FG_TEST_DISK_DIR="$WORK/refdisk" PC88_M6FG_WORK="$target" "$@" \
    bash "$REPO/tools/measure_m6fg.sh"
}

: >"$COUNTER"
run_driver "$WORK/result-positive" M6FG_TEST_MODE=1 >"$WORK/positive.out" 2>"$WORK/positive.err"
positive_rc=$?
if [ "$positive_rc" -eq 0 ] && [ "$(wc -l <"$COUNTER" | tr -d ' ')" = 10 ] \
  && grep -q 'mark_2A,mark_50,mixed_row_consistent,size_min_digits' "$WORK/positive.out"; then
  ok '5腕×2走を完走'
else ng "通し正例(rc=$positive_rc)"; fi
if python3 - "$WORK/result-positive" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); s=json.loads((p/"summary.json").read_text()); j=json.loads((p/"judgment.json").read_text())
assert s["run_count"]==s["frontend_launch_count"]==10 and s["output_audit_file_count"]==0
assert j["judgments"]==["mark_2A","mark_50","mixed_row_consistent","size_min_digits"]
assert sorted(x.name for x in p.iterdir())==["derived.json","judgment.json","observations.json","summary.json"]
PY
then ok '出力許可リスト'; else ng '出力契約'; fi

for gate in G0 G1 G2 G3 G4 G5 G6 G7 G8; do
  : >"$COUNTER"
  run_driver "$WORK/result-$gate" M6FG_TEST_MODE=1 M6FG_TEST_FAST_GATES=1 \
    M6FG_TEST_FAIL_GATE="$gate" >"$WORK/$gate.out" 2>"$WORK/$gate.err"
  gate_rc=$?
  if [ "$gate_rc" -ne 0 ] && [ ! -s "$COUNTER" ] && python3 - "$WORK/$gate.out" "$gate" <<'PY'
import json,pathlib,sys
v=json.loads(pathlib.Path(sys.argv[1]).read_text()); assert v["failed_gates"]==[sys.argv[2]] and v["frontend_launch_count"]==0
PY
  then ok "$gate 陰性対照 NG集合={$gate} 起動0"; else ng "$gate 陰性対照"; fi
done

# 候補表SHAだけを壊し、実際の凍結照合G4が起動前に止める。
python3 - "$REPO/tools/m6fg_frozen.tsv" "$WORK/bad-frozen.tsv" <<'PY'
import pathlib,sys
src,dst=map(pathlib.Path,sys.argv[1:]); rows=[]
for line in src.read_text(encoding="ascii").splitlines():
 key,value=line.split("\t"); rows.append(key+"\t"+("0"*64 if key=="candidates_sha256" else value))
dst.write_text("\n".join(rows)+"\n",encoding="ascii")
PY
: >"$COUNTER"
run_driver "$WORK/result-frozen" M6FG_TEST_MODE=1 M6FG_TEST_FAST_GATES=1 \
  M6FG_TEST_FROZEN="$WORK/bad-frozen.tsv" >"$WORK/frozen.out" 2>"$WORK/frozen.err"
if [ "$?" -ne 0 ] && [ ! -s "$COUNTER" ] && python3 - "$WORK/frozen.out" <<'PY'
import json,pathlib,sys
v=json.loads(pathlib.Path(sys.argv[1]).read_text()); assert v["failed_gates"]==["G4"] and v["frontend_launch_count"]==0
PY
then ok '凍結破壊はG4、起動0'; else ng '凍結破壊'; fi

: >"$COUNTER"
run_driver "$WORK/result-g14" M6FG_TEST_MODE=1 M6FG_TEST_FAST_GATES=1 \
  M6FG_SELFTEST_BAD_BASELINE=1 >"$WORK/g14.out" 2>"$WORK/g14.err"
if [ "$?" -eq 0 ] && [ "$(wc -l <"$COUNTER" | tr -d ' ')" = 1 ] \
  && grep -q 'judgment=inconclusive_cls_baseline' "$WORK/g14.out"; then
  ok 'G14陰性対照は1走で停止'
else ng 'G14陰性対照'; fi

if [ "$rc" -eq 0 ]; then printf '%s\n' 'OK m6f-gドライバ 全項目'; else printf '%s\n' 'NG あり'; fi
exit "$rc"
