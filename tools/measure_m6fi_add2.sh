#!/usr/bin/env bash
# m6f-i 追補2: 4腕各2走。画面はフロントエンド内で署名化し、本文を保存しない。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="${M6FI_ADD2_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
SUPPORT="$REPO/tools/m6fi_add2_measure_support.py"
TARGET="${PC88_M6FI_ADD2_WORK:-}"
FROZEN="$REPO/tools/m6fi_add2_frozen.tsv"
if [ "${M6FI_ADD2_TEST_MODE:-0}" = 1 ] && [ -n "${M6FI_ADD2_TEST_FROZEN:-}" ]; then
  FROZEN="$M6FI_ADD2_TEST_FROZEN"
fi
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/m6fi-add2-driver.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

failed() {
  python3 - "$1" "${LAUNCH_COUNT:-0}" <<'PY'
import json,sys
print(json.dumps({'judgment':'gate_failed','failed_gates':sys.argv[1].split(),
                  'frontend_launch_count':int(sys.argv[2])},separators=(',',':')))
PY
  exit 1
}

[ -n "$TARGET" ] || failed PC88_M6FI_ADD2_WORK_missing
G0=1; G1=1; G2=1; G3=1; G4=1; G5=1; G6=1; G7=1; G8=1
REVIEW_INPUTS='CLAUDE.md docs/notes/m6f-i-load-ascii-behavior-preregistration.md docs/notes/m6f-i-attempt2-and-addendum2.md docs/spec/l3-disk-format.md docs/spec/l4-program.md tools/make_m6fi_add2_disk.py tools/check_m6fi_add2_disk.py tools/check_m6fi_add2.py tools/predict_m6fi_add2.py tools/derive_m6fi_add2.py tools/judge_m6fi_add2.py tools/m6fi_add2_measure_support.py tools/measure_m6fi_add2.sh tools/m6fi_add2_selftest.py tools/compare_screen_signatures.py tools/run_all_selftests.sh'
if [ -n "${M6FI_ADD2_TEST_FORBIDDEN_INPUT:-}" ]; then REVIEW_INPUTS="$REVIEW_INPUTS $M6FI_ADD2_TEST_FORBIDDEN_INPUT"; fi
case " $REVIEW_INPUTS " in
  *" private/"*|*" vendor/"*|*"make_n88_blank_disk.py"*|*"make_n88_blank_disk_selftest.py"*|*"m7eb"*|*" image.c"*) G0=0 ;;
esac
if [ "${M6FI_ADD2_TEST_FAST_GATES:-0}" != 1 ]; then
  "$REPO/tools/make_m6fc_blank_disk_selftest.sh" >"$STAGE/g1a.out" 2>"$STAGE/g1a.err" || G1=0
  python3 "$REPO/tools/m6fi_add2_selftest.py" --disk-only >"$STAGE/g1b.out" 2>"$STAGE/g1b.err" || G1=0
fi
python3 "$REPO/tools/make_m6fi_add2_disk.py" "$STAGE/media" >"$STAGE/generate.out" 2>"$STAGE/generate.err" || G2=0
if [ "$G2" -eq 1 ]; then
  python3 "$REPO/tools/check_m6fi_add2_disk.py" "$STAGE/media/manifest.json" --frozen "$FROZEN" \
    >"$STAGE/g2.out" 2>"$STAGE/g2.err" || G2=0
fi
if [ "$G2" -eq 1 ]; then
  G3_MANIFEST="$STAGE/media/manifest.json"; G3_FROZEN="$FROZEN"
  if [ "${M6FI_ADD2_TEST_MODE:-0}" = 1 ]; then
    G3_MANIFEST="${M6FI_ADD2_TEST_G3_MANIFEST:-$G3_MANIFEST}"
    G3_FROZEN="${M6FI_ADD2_TEST_G3_FROZEN:-$G3_FROZEN}"
  fi
  python3 "$REPO/tools/check_m6fi_add2.py" "$G3_MANIFEST" --frozen "$G3_FROZEN" --scenario-only \
    >"$STAGE/g3.out" 2>"$STAGE/g3.err" || G3=0
  python3 "$REPO/tools/check_m6fi_add2.py" "$STAGE/media/manifest.json" \
    --frozen "$FROZEN" >"$STAGE/g4.out" 2>"$STAGE/g4.err" || G4=0
else G3=0; G4=0; fi
if [ "${M6FI_ADD2_TEST_FAST_GATES:-0}" != 1 ]; then
  "$REPO/tools/screen_signature_selftest.sh" >"$STAGE/g5a.out" 2>"$STAGE/g5a.err" || G5=0
  python3 "$REPO/tools/m6fi_add2_selftest.py" --prediction-only >"$STAGE/g5b.out" 2>"$STAGE/g5b.err" || G5=0
  [ "$G5" -eq 1 ] || G6=0
fi
if [ "$G2" -eq 1 ]; then
  python3 "$SUPPORT" plan-check --manifest "$STAGE/media/manifest.json" >"$STAGE/g7.out" 2>"$STAGE/g7.err" || G7=0
else G7=0; fi
[ ! -e "$TARGET" ] || G8=0
if [ "${M6FI_ADD2_TEST_MODE:-0}" = 1 ]; then
  case "${M6FI_ADD2_TEST_FAIL_GATE:-}" in
    G0) G0=0;; G1) G1=0;; G2) G2=0;; G3) G3=0;; G4) G4=0;;
    G5) G5=0;; G6) G6=0;; G7) G7=0;; G8) G8=0;;
  esac
fi
FAILED=''
for index in 0 1 2 3 4 5 6 7 8; do
  eval "value=\$G$index"
  [ "$value" -eq 1 ] || FAILED="$FAILED G$index"
done
[ -z "$FAILED" ] || failed "${FAILED# }"

if [ "${M6FI_ADD2_TEST_MODE:-0}" = 1 ]; then
  ROM_DIR="${M6FI_ADD2_TEST_ROM_DIR:-}"; DISK_DIR="${M6FI_ADD2_TEST_DISK_DIR:-}"
else
  ROM_DIR="${PC88_REF_ROM_DIR:-}"; DISK_DIR="${PC88_REF_DISK_DIR:-}"
fi
[ -n "$ROM_DIR" ] && [ -d "$ROM_DIR" ] || failed reference_rom
[ -n "$DISK_DIR" ] && [ -d "$DISK_DIR" ] || failed reference_disk_dir
REF_DISK="$DISK_DIR/N88_FE.D88"
[ -f "$REF_DISK" ] || failed reference_disk
source "$REPO/tools/lib_m6f_measure.sh"
REF_SHA="$(m6f_sha256 "$REF_DISK")" || failed reference_sha
source "$REPO/tools/lib_l3_measure.sh"
CORE="${M6FI_ADD2_TEST_CORE:-$(find_l3_core)}"
[ -n "$CORE" ] || failed core
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || failed frontend
else [ -x "$FRONTEND" ] || failed frontend; fi
mkdir "$TARGET" || failed work_create
mkdir "$STAGE/safe" "$STAGE/runs" || failed stage_create
LAUNCH_COUNT=0

run_one() {
  local arm="$1" rep="$2" run_dir="$STAGE/runs/$1-r$2"
  local disk1="$run_dir/drive1.d88" disk2="$run_dir/drive2.d88"
  local report="$run_dir/signatures.tsv" iolog="$run_dir/iolog.txt"
  local stdout="$run_dir/stdout.txt" stderr="$run_dir/stderr.txt"
  mkdir "$run_dir" || return 1
  cp "$REF_DISK" "$disk1" || return 1
  [ "$(m6f_sha256 "$disk1")" = "$REF_SHA" ] || return 1
  cp "$STAGE/media/ascii.d88" "$disk2" || return 1
  local command
  command="$(python3 - "$STAGE/media/manifest.json" "$arm" <<'PY'
import json,sys
doc=json.load(open(sys.argv[1],encoding='ascii'))
sys.stdout.write(next(a['command'] for a in doc['arms'] if a['id']==sys.argv[2]))
PY
)" || return 1
  command="$command"$'\n'
  local qargs=(--core "$CORE" --rom-dir "$ROM_DIR" --disk "$disk1" --disk2 "$disk2"
    --frames 8000 --io-log "$iolog" --io-log-from-frame 650
    --screen-signature-only --screen-signature-at baseline:600
    --screen-signature-at final:7700 --screen-signature-at late:8000 --out "$report"
    --type-at 300 --type $'\n' --type-at 500 --type $'CLS\n'
    --type-at 700 --type "$command")
  case "$arm" in
    E-3)
      # m6f-e G10 と同じく300フレーム隔てた画面の一致と入力待ちで
      # LOAD完了を判定する。4000フレームのCLS:LIST打鍵より前に2点を置く。
      qargs+=(--screen-signature-at load:3300 --screen-signature-at load_late:3600
        --type-at 4000 --type $'CLS:LIST\n') ;;
  esac
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
  if [ "$(m6f_sha256 "$disk1")" = "$REF_SHA" ] && [ "$(m6f_sha256 "$REF_DISK")" = "$REF_SHA" ]; then unchanged=true; fi
  python3 "$SUPPORT" normalize-run --report "$report" --iolog "$iolog" \
    --arm "$arm" --repetition "$rep" --reference-unchanged "$unchanged" \
    --output "$STAGE/safe/$arm-r$rep.safe.json" || return 1
  rm -f "$disk1" "$disk2" "$report" "$iolog" "$stdout" "$stderr"
  rmdir "$run_dir" || return 1
}

for arm in "I-4'" "E-2'" E-3 E-3m; do
  for rep in 1 2; do
    run_one "$arm" "$rep" || failed run_failed
    baseline_ok="$(python3 - "$STAGE/safe/$arm-r$rep.safe.json" <<'PY'
import json,sys
print('1' if json.load(open(sys.argv[1],encoding='ascii'))['baseline_ok'] else '0')
PY
)"
    if [ "$baseline_ok" != 1 ]; then
      printf '%s\n' '{"overall":"inconclusive_cls_baseline","judgments":["inconclusive_cls_baseline"]}' >"$TARGET/judgment.json"
      printf '{"format":"m6fi-add2-summary-v1","frontend_launch_count":%d,"judgments":["inconclusive_cls_baseline"],"run_count":%d}\n' "$LAUNCH_COUNT" "$LAUNCH_COUNT" >"$TARGET/summary.json"
      printf 'm6f-i add2 measurement complete: judgment=inconclusive_cls_baseline launches=%d\n' "$LAUNCH_COUNT"
      exit 0
    fi
  done
  python3 "$SUPPORT" arm-check --arm "$arm" \
    --run "$STAGE/safe/$arm-r1.safe.json" --run "$STAGE/safe/$arm-r2.safe.json" \
    >"$STAGE/$arm-gates.json" 2>"$STAGE/$arm-gates.err" || failed run_gate
done
python3 "$SUPPORT" assemble --run-dir "$STAGE/safe" --output "$TARGET/observations.json" || failed assemble
python3 "$REPO/tools/derive_m6fi_add2.py" --observations "$TARGET/observations.json" \
  --output "$TARGET/derived.json" || failed derive
python3 "$REPO/tools/judge_m6fi_add2.py" --derived "$TARGET/derived.json" \
  >"$TARGET/judgment.json" || failed judge
python3 "$SUPPORT" summary --judgment "$TARGET/judgment.json" \
  --frontend-launch-count "$LAUNCH_COUNT" --output "$TARGET/summary.json" || failed summary
AUDIT_NAMES="$(find "$TARGET" -maxdepth 1 -type f -print | sed "s#^$TARGET/##" | LC_ALL=C sort | tr '\n' ' ')"
[ "$AUDIT_NAMES" = 'derived.json judgment.json observations.json summary.json ' ] || failed G12
python3 - "$TARGET/judgment.json" "$LAUNCH_COUNT" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding='ascii'))
print('m6f-i add2 measurement complete: judgments='+','.join(v['judgments'])+' launches='+sys.argv[2])
PY
