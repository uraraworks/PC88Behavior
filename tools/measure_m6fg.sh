#!/usr/bin/env bash
# m6f-g: 5腕を各2走する測定ドライバ。画面本文は一切保存しない。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="${M6FG_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
SUPPORT="$REPO/tools/m6fg_measure_support.py"
WORK_TARGET="${PC88_M6FG_WORK:-}"
FROZEN="$REPO/tools/m6fg_frozen.tsv"
if [ "${M6FG_TEST_MODE:-0}" = 1 ] && [ -n "${M6FG_TEST_FROZEN:-}" ]; then
  FROZEN="$M6FG_TEST_FROZEN"
fi
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/m6fg-driver.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

emit_gate_failure() {
  python3 - "$1" <<'PY'
import json, sys
failed = [item for item in sys.argv[1].split() if item]
print(json.dumps({"judgment":"gate_failed","failed_gates":failed,
                  "frontend_launch_count":0}, sort_keys=True, separators=(",",":")))
PY
  exit 1
}

if [ -z "$WORK_TARGET" ]; then
  printf '%s\n' '{"frontend_launch_count":0,"judgment":"gate_failed","reason":"PC88_M6FG_WORK_missing"}'
  exit 1
fi

G0=1; G1=1; G2=1; G3=1; G4=1; G5=1; G6=1; G7=1; G8=1
REVIEW_INPUTS="CLAUDE.md docs/notes/m6f-g-files-marks-and-wide-size-preregistration.md tools/make_m6fg_disk.py tools/make_m6fg_disk_selftest.sh tools/check_m6fg_disk.py tools/predict_m6fg.py tools/derive_m6fg.py tools/judge_m6fg.py tools/check_m6fg_candidates.py tools/m6fg_measure_support.py tools/m6fg_predict_derive_selftest.sh tools/measure_m6fg.sh tools/measure_m6fg_driver_selftest.sh tools/compare_screen_signatures.py tools/screen_signature_selftest.sh tools/harness/frontend/main.c tools/harness/frontend/screen_signature.h tools/run_all_selftests.sh"
if [ -n "${M6FG_TEST_FORBIDDEN_INPUT:-}" ]; then
  REVIEW_INPUTS="$REVIEW_INPUTS $M6FG_TEST_FORBIDDEN_INPUT"
fi
case " $REVIEW_INPUTS " in
  *" private/"*|*" vendor/"*|*"make_n88_blank_disk.py"*|*"make_n88_blank_disk_selftest.py"*|*"m7eb"*|*" image.c"*) G0=0 ;;
esac

if [ "${M6FG_TEST_FAST_GATES:-0}" != 1 ]; then
  "$REPO/tools/check_cleanroom.sh" >"$STAGE/g0.out" 2>"$STAGE/g0.err" || G0=0
  "$REPO/tools/make_m6fc_blank_disk_selftest.sh" >"$STAGE/g1a.out" 2>"$STAGE/g1a.err" || G1=0
  "$REPO/tools/make_m6fg_disk_selftest.sh" >"$STAGE/g1b.out" 2>"$STAGE/g1b.err" || G1=0
fi

python3 "$REPO/tools/make_m6fg_disk.py" "$STAGE/media" \
  >"$STAGE/generate.out" 2>"$STAGE/generate.err" || G2=0
if [ "$G2" -eq 1 ]; then
  python3 "$REPO/tools/check_m6fg_disk.py" "$STAGE/media/manifest.json" \
    --image-dir "$STAGE/media" --sha256-file "$FROZEN" --json \
    >"$STAGE/g2.out" 2>"$STAGE/g2.err" || G2=0
fi
if [ "$G2" -eq 1 ]; then
  python3 - "$STAGE/media/manifest.json" "$FROZEN" <<'PY' \
    >"$STAGE/g3.out" 2>"$STAGE/g3.err" || G3=0
import hashlib, pathlib, sys
manifest, frozen = map(pathlib.Path, sys.argv[1:])
values = dict(line.split("\t") for line in frozen.read_text(encoding="ascii").splitlines())
raise SystemExit(0 if hashlib.sha256(manifest.read_bytes()).hexdigest() == values["manifest_sha256"] else 1)
PY
  python3 "$REPO/tools/check_m6fg_candidates.py" "$STAGE/media/manifest.json" \
    --frozen "$FROZEN" >"$STAGE/g4.out" 2>"$STAGE/g4.err" || G4=0
else
  G3=0; G4=0
fi

if [ "${M6FG_TEST_FAST_GATES:-0}" != 1 ]; then
  "$REPO/tools/screen_signature_selftest.sh" >"$STAGE/g5a.out" 2>"$STAGE/g5a.err" || G5=0
  "$REPO/tools/m6fg_predict_derive_selftest.sh" >"$STAGE/g5b.out" 2>"$STAGE/g5b.err" || G5=0
  [ "$G5" -eq 1 ] || G6=0
fi

if [ "$G2" -eq 1 ]; then
  python3 - "$STAGE/media/manifest.json" <<'PY' >"$STAGE/g7.out" 2>"$STAGE/g7.err" || G7=0
import json, pathlib, sys
doc = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="ascii"))
ok = all(arm.get("drive2") == arm.get("id")
         and arm.get("command") == "CLS:FILES 2"
         and arm.get("command_time") == "after_boot_complete"
         and not arm.get("events") for arm in doc.get("arms", []))
raise SystemExit(0 if ok else 1)
PY
else
  G7=0
fi
[ ! -e "$WORK_TARGET" ] || G8=0
if [ "$G2" -eq 1 ]; then
  python3 "$SUPPORT" plan-check --manifest "$STAGE/media/manifest.json" \
    >"$STAGE/g8.out" 2>"$STAGE/g8.err" || G8=0
fi

if [ "${M6FG_TEST_MODE:-0}" = 1 ] && [ -n "${M6FG_TEST_FAIL_GATE:-}" ]; then
  case "$M6FG_TEST_FAIL_GATE" in
    G0) G0=0;; G1) G1=0;; G2) G2=0;; G3) G3=0;; G4) G4=0;;
    G5) G5=0;; G6) G6=0;; G7) G7=0;; G8) G8=0;;
  esac
fi
FAILED=""
for index in 0 1 2 3 4 5 6 7 8; do
  eval "value=\$G$index"
  [ "$value" -eq 1 ] || FAILED="$FAILED G$index"
done
[ -z "$FAILED" ] || emit_gate_failure "${FAILED# }"

if [ "${M6FG_TEST_MODE:-0}" = 1 ]; then
  ROM_DIR="${M6FG_TEST_ROM_DIR:-}"
  DISK_DIR="${M6FG_TEST_DISK_DIR:-}"
else
  ROM_DIR="${PC88_REF_ROM_DIR:-}"
  DISK_DIR="${PC88_REF_DISK_DIR:-}"
fi
[ -n "$ROM_DIR" ] && [ -d "$ROM_DIR" ] || emit_gate_failure reference_rom
[ -n "$DISK_DIR" ] && [ -d "$DISK_DIR" ] || emit_gate_failure reference_disk_dir
REF_DISK="$DISK_DIR/N88_FE.D88"
[ -f "$REF_DISK" ] || emit_gate_failure reference_disk
source "$REPO/tools/lib_m6f_measure.sh"
REF_SHA="$(m6f_sha256 "$REF_DISK")" || emit_gate_failure reference_sha
source "$REPO/tools/lib_l3_measure.sh"
CORE="${M6FG_TEST_CORE:-$(find_l3_core)}"
[ -n "$CORE" ] || emit_gate_failure core
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || emit_gate_failure frontend
else
  [ -x "$FRONTEND" ] || emit_gate_failure frontend
fi

mkdir "$WORK_TARGET" || emit_gate_failure work_create
mkdir "$STAGE/safe" "$STAGE/runs" || emit_gate_failure stage_create
LAUNCH_COUNT=0

run_one() {
  local arm="$1" rep="$2"
  local run_dir="$STAGE/runs/$arm-r$rep"
  local disk1="$run_dir/drive1.d88" disk2="$run_dir/drive2.d88"
  local report="$run_dir/signatures.tsv" iolog="$run_dir/iolog.txt"
  local stdout="$run_dir/stdout.txt" stderr="$run_dir/stderr.txt"
  mkdir "$run_dir" || return 1
  cp "$REF_DISK" "$disk1" || return 1
  [ "$(m6f_sha256 "$disk1")" = "$REF_SHA" ] || return 1
  cp "$STAGE/media/$arm.d88" "$disk2" || return 1
  local qargs=(--core "$CORE" --rom-dir "$ROM_DIR" --disk "$disk1" --disk2 "$disk2"
    --frames 8000 --io-log "$iolog" --io-log-from-frame 650
    --screen-signature-only --screen-signature-at baseline:600
    --screen-signature-at final:7700 --screen-signature-at late:8000 --out "$report"
    --type-at 300 --type '\n' --type-at 500 --type 'CLS\n'
    --type-at 700 --type 'CLS:FILES 2\n')
  local attempt=0 run_rc=0
  while :; do
    attempt=$((attempt + 1)); LAUNCH_COUNT=$((LAUNCH_COUNT + 1)); run_rc=0
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$FRONTEND" "${qargs[@]}" \
      >"$stdout" 2>"$stderr" || run_rc=$?
    [ "$run_rc" -eq 0 ] && break
    [ "$run_rc" -eq 134 ] && [ "$attempt" -lt 3 ] || return 1
    rm -f "$report" "$iolog"
  done
  [ -s "$report" ] && [ -e "$iolog" ] || return 1
  local unchanged=false
  if [ "$(m6f_sha256 "$disk1")" = "$REF_SHA" ] \
    && [ "$(m6f_sha256 "$REF_DISK")" = "$REF_SHA" ]; then unchanged=true; fi
  python3 "$SUPPORT" normalize-run --report "$report" --iolog "$iolog" \
    --arm "$arm" --repetition "$rep" --reference-unchanged "$unchanged" \
    --output "$STAGE/safe/$arm-r$rep.safe.json" || return 1
  rm -f "$disk1" "$disk2" "$report" "$iolog" "$stdout" "$stderr"
  rmdir "$run_dir" || return 1
}

for arm in G-P G-B G-M G-Z1 G-Z2; do
  for rep in 1 2; do
    run_one "$arm" "$rep" || {
      printf '{"frontend_launch_count":%d,"judgment":"gate_failed","reason":"run_failed"}\n' "$LAUNCH_COUNT"
      exit 1
    }
    baseline_ok="$(python3 - "$STAGE/safe/$arm-r$rep.safe.json" <<'PY'
import json, sys
print("1" if json.load(open(sys.argv[1], encoding="ascii"))["baseline_ok"] else "0")
PY
)"
    if [ "$baseline_ok" != 1 ]; then
      printf '%s\n' '{"overall":"inconclusive_cls_baseline","judgments":["inconclusive_cls_baseline"]}' >"$WORK_TARGET/judgment.json"
      printf '{"format":"m6fg-summary-v1","frontend_launch_count":%d,"judgments":["inconclusive_cls_baseline"],"run_count":%d}\n' "$LAUNCH_COUNT" "$LAUNCH_COUNT" >"$WORK_TARGET/summary.json"
      printf 'm6f-g measurement complete: judgment=inconclusive_cls_baseline launches=%d\n' "$LAUNCH_COUNT"
      exit 0
    fi
  done
  python3 "$SUPPORT" arm-check --arm "$arm" \
    --run "$STAGE/safe/$arm-r1.safe.json" --run "$STAGE/safe/$arm-r2.safe.json" \
    >"$STAGE/$arm-gates.json" 2>"$STAGE/$arm-gates.err" || {
      printf '{"frontend_launch_count":%d,"judgment":"gate_failed","reason":"run_gate"}\n' "$LAUNCH_COUNT"
      exit 1
    }
done

python3 "$SUPPORT" assemble --run-dir "$STAGE/safe" \
  --output "$WORK_TARGET/observations.json" || exit 1
python3 "$REPO/tools/derive_m6fg.py" --manifest "$STAGE/media/manifest.json" \
  --observations "$WORK_TARGET/observations.json" --output "$WORK_TARGET/derived.json" || exit 1
python3 "$REPO/tools/judge_m6fg.py" --derived "$WORK_TARGET/derived.json" \
  >"$WORK_TARGET/judgment.json" || exit 1
python3 "$SUPPORT" summary --judgment "$WORK_TARGET/judgment.json" \
  --frontend-launch-count "$LAUNCH_COUNT" --output "$WORK_TARGET/summary.json" || exit 1

AUDIT_NAMES="$(find "$WORK_TARGET" -type f -maxdepth 1 -print | sed "s#^$WORK_TARGET/##" | LC_ALL=C sort | tr '\n' ' ')"
[ "$AUDIT_NAMES" = "derived.json judgment.json observations.json summary.json " ] || {
  printf '{"frontend_launch_count":%d,"judgment":"gate_failed","reason":"G12"}\n' "$LAUNCH_COUNT"
  exit 1
}
judgments="$(python3 - "$WORK_TARGET/judgment.json" <<'PY'
import json, sys
print(",".join(json.load(open(sys.argv[1], encoding="ascii"))["judgments"]))
PY
)"
printf 'm6f-g measurement complete: judgments=%s launches=%d\n' "$judgments" "$LAUNCH_COUNT"
