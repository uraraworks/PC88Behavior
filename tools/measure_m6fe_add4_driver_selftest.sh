#!/usr/bin/env bash
# m6f-e追補4ドライバを、公式物を使わず偽フロントエンドで通し検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fe-add4-driver-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

python3 "$REPO/tools/make_m6fe_disk.py" --addendum3 "$WORK/add3" >/dev/null
python3 - "$WORK/add3-derived.json" <<'PY'
import json, pathlib, sys
q_b="files_layout_rule_G5_SPLIT63_80DOT_00BLANK_UNITS_W"
value={"format":"m6fe-add3-derived-v1","overall":"inconclusive_print_control",
       "q_a":"inconclusive_print_control","q_b":q_b,
       "gates":{f"G{i}":True for i in range(9,14)},"candidates":[q_b],
       "first_empty_arm":None,"l90_comparison":"l90_reproduced",
       "fkey_unchanged":True,"extra_lines_absent":True,"input_sha256":"1"*64,
       "add2_observations_sha256":"2"*64}
pathlib.Path(sys.argv[1]).write_text(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n",encoding="ascii")
PY

FAKE="$WORK/fake_frontend.py"
cat >"$FAKE" <<'PY'
#!/usr/bin/env python3
import hashlib,json,os,pathlib,sys
repo=pathlib.Path(os.environ["M6FE_ADD4_SELFTEST_REPO"]); sys.path.insert(0,str(repo/"tools")); import predict_m6fe as p
def one(a,n):
 try:return a[a.index(n)+1]
 except ValueError:return None
def many(a,n):return [a[i+1] for i,v in enumerate(a[:-1]) if v==n]
def hashed(r,b):
 raw=f"{r}\t{b}\n".encode(); return r,len(b),hashlib.sha256(raw).hexdigest()
def report(path,snaps):
 with path.open("w",encoding="ascii") as out:
  for name,rows in snaps:
   rows=sorted(rows); out.write(f"snapshot_id\t{name}\nphysical_row\tchar_count\tsha256\n")
   for r,c,h in rows:out.write(f"{r}\t{c}\t{h}\n")
   whole=hashlib.sha256("".join(f"{r}\t{c}\t{h}\n" for r,c,h in rows).encode()).hexdigest()
   out.write(f"line_count\t{len(rows)}\nchar_count\t{sum(x[1] for x in rows)}\nsha256\t{whole}\n")
def main():
 a=sys.argv[1:]; out=pathlib.Path(one(a,"--out")); io=pathlib.Path(one(a,"--io-log")); arm=out.parent.name.rsplit("-r",1)[0]
 with open(os.environ["M6FE_ADD4_SELFTEST_COUNTER"],"a") as f:f.write("1\n")
 with open(os.environ["M6FE_ADD4_SELFTEST_ARGV"],"a") as f:f.write(json.dumps({"arm":arm,"argv":a},separators=(",",":"))+"\n")
 marker=os.environ["M6FE_ADD4_SELFTEST_CANARY"]
 baseline=[hashed(0,marker),hashed(19,"FKEY")]
 if os.environ.get("M6FE_ADD4_SELFTEST_BAD_BASELINE"):baseline.append(hashed(5,"X"))
 lines=[(x.physical_row,x.char_count,x.sha256) for x in p.predict_add4_print_candidate(arm,"wrap_then_newline_blank")]
 if os.environ.get("M6FE_ADD4_SELFTEST_PENDING") and arm=="P80":
  typed=many(a,"--type")[-1][:-2].lower(); chunks=[typed[i:i+80].rstrip() for i in range(0,len(typed),80)]
  lines=[hashed(i,b) for i,b in enumerate(chunks)]
 prompt=max((x[0] for x in lines),default=-1)+1; final=lines+[hashed(prompt,marker),hashed(19,"FKEY")]
 wanted={x.split(":",1)[0] for x in many(a,"--screen-signature-at")}
 report(out,[x for x in (("baseline",baseline),("final",final),("late",list(final))) if x[0] in wanted])
 io.write_text("# synthetic iolog\n",encoding="ascii"); return 0
raise SystemExit(main())
PY
chmod +x "$FAKE"
mkdir -p "$WORK/rom" "$WORK/refdisk"
printf '%s' 'SYNTHETIC-REFERENCE-DISK' >"$WORK/refdisk/N88_FE.D88"
COUNTER="$WORK/count.txt"; ARGV_LOG="$WORK/argv.jsonl"; CANARY="ZQADD4LEAK"

run_driver() {
  local target="$1"; shift
  env M6FE_FRONTEND="$FAKE" M6FE_ADD4_TEST_CORE=selftest-core \
    M6FE_ADD4_SELFTEST_REPO="$REPO" M6FE_ADD4_SELFTEST_COUNTER="$COUNTER" \
    M6FE_ADD4_SELFTEST_ARGV="$ARGV_LOG" M6FE_ADD4_SELFTEST_CANARY="$CANARY" \
    M6FE_ADD4_TEST_ROM_DIR="$WORK/rom" M6FE_ADD4_TEST_DISK_DIR="$WORK/refdisk" \
    PC88_M6FE_WORK="$target" "$@" bash "$REPO/tools/measure_m6fe_add4.sh" \
    --add3-derived "$WORK/add3-derived.json"
}

: >"$COUNTER"; : >"$ARGV_LOG"
run_driver "$WORK/result-positive" M6FE_ADD4_TEST_MODE=1 >"$WORK/positive.out" 2>"$WORK/positive.err"
positive_rc=$?
if [ "$positive_rc" -eq 0 ] && [ "$(wc -l <"$COUNTER" | tr -d ' ')" = 6 ] \
  && grep -q 'q_a=wrap_then_newline_blank' "$WORK/positive.out" \
  && grep -q 'adopted=true' "$WORK/positive.out"; then
  ok "偽フロントエンドで3腕×2走を完走し採用した"
else ng "通し正例が失敗した(rc=$positive_rc)"; tail -20 "$WORK/positive.out" "$WORK/positive.err"; fi

if python3 - "$WORK/result-positive" "$ARGV_LOG" <<'PY'
import json,pathlib,sys
result,log=map(pathlib.Path,sys.argv[1:]); judge=json.loads((result/"judgment.json").read_text())
summary=json.loads((result/"summary.json").read_text()); obs=json.loads((result/"observations.json").read_text())
q_b="files_layout_rule_G5_SPLIT63_80DOT_00BLANK_UNITS_W"
assert judge["judgments"]==["wrap_then_newline_blank",q_b]
assert judge["adopted"] is True and judge["not_adopted"] is False
assert summary["run_count"]==summary["frontend_launch_count"]==6 and len(obs["arms"])==3
calls=[json.loads(x) for x in log.read_text().splitlines()]; assert len(calls)==6
for call in calls:
 a=call["argv"]; assert "--screen-signature-only" in a and "--expect-disk2-empty" in a
 assert "--disk2" not in a and a[a.index("--frames")+1]=="8000"
 typed=[a[i+1] for i,v in enumerate(a[:-1]) if v=="--type"][-1]
 assert 'PRINT "A' in typed and ':PRINT "B"' in typed
PY
then ok "出力契約・Q-B引数・打鍵不変・フレーム数を確認した"; else ng "通し正例の契約が不正"; fi

if ! grep -R -F -q "$CANARY" "$WORK/result-positive" "$WORK/positive.out" "$WORK/positive.err"; then
  ok "画面本文の漏えい目印は成果物と出力に無い"
else ng "画面本文の漏えい目印を検出した"; fi
printf '%s' "$CANARY" >"$WORK/leak-negative.txt"
if grep -F -q "$CANARY" "$WORK/leak-negative.txt"; then ok "漏えい検査の陰性対照を確認した"; else ng "漏えい陰性対照が効かない"; fi

# 未実行の長い入力エコーを専用判定へ分ける。
: >"$COUNTER"; : >"$ARGV_LOG"
run_driver "$WORK/result-pending" M6FE_ADD4_TEST_MODE=1 M6FE_ADD4_TEST_FAST_GATES=1 \
  M6FE_ADD4_SELFTEST_PENDING=1 >"$WORK/pending.out" 2>"$WORK/pending.err"
if [ "$?" -eq 0 ] && grep -q 'q_a=inconclusive_input_limit' "$WORK/pending.out" \
  && grep -q 'adopted=false' "$WORK/pending.out"; then
  ok "未実行入力をinconclusive_input_limitへ分離した"
else ng "入力制限の分離に失敗した"; fi

for gate in G0 G1 G2 G3 G4 G5 G6 G7 G8; do
  : >"$COUNTER"; : >"$ARGV_LOG"
  run_driver "$WORK/result-$gate" M6FE_ADD4_TEST_MODE=1 M6FE_ADD4_TEST_FAST_GATES=1 \
    M6FE_ADD4_TEST_FAIL_GATE="$gate" >"$WORK/$gate.out" 2>"$WORK/$gate.err"
  gate_rc=$?
  if [ "$gate_rc" -ne 0 ] && [ ! -s "$COUNTER" ] && python3 - "$WORK/$gate.out" "$gate" <<'PY'
import json,pathlib,sys
v=json.loads(pathlib.Path(sys.argv[1]).read_text()); raise SystemExit(0 if v.get("failed_gates")==[sys.argv[2]] and v.get("frontend_launch_count")==0 else 1)
PY
  then ok "$gate 陰性対照はNG集合={$gate}、起動回数0"; else ng "$gate 陰性対照の停止条件が不正"; fi
done

: >"$COUNTER"; : >"$ARGV_LOG"
run_driver "$WORK/result-g14" M6FE_ADD4_TEST_MODE=1 M6FE_ADD4_TEST_FAST_GATES=1 \
  M6FE_ADD4_SELFTEST_BAD_BASELINE=1 >"$WORK/g14.out" 2>"$WORK/g14.err"
if [ "$?" -eq 0 ] && [ "$(wc -l <"$COUNTER" | tr -d ' ')" = 1 ] \
  && grep -q 'judgment=inconclusive_cls_baseline' "$WORK/g14.out"; then
  ok "G14陰性対照は最初の走で停止した"
else ng "G14停止が不正"; fi

if [ "$rc" -eq 0 ]; then printf '%s\n' '全項目 OK'; else printf '%s\n' 'NG あり'; fi
exit "$rc"
