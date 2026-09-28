#!/usr/bin/env bash
# m6f-h: 4腕×2走。G3を公式ROM起動前に検査し、画面は署名だけ残す。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${M6FH_FROZEN_CONFIG:-$REPO/tools/m6fh_frozen.tsv}"
FRONTEND="${M6FH_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
raw_dir=''; result=''; keep=0
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s","frontend_launch_count":%s}\n' "$1" "${launches:-0}"; exit 1; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --raw-dir) raw_dir="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    --keep-images) keep=1; shift ;;
    *) exit 2 ;;
  esac
done
[ -n "$raw_dir" ] && [ -n "$result" ] || exit 2
launches=0
python3 "$REPO/tools/check_m6fh_preregistration.py" --config "$CONFIG" >/dev/null 2>&1 || gate_failed G3
source "$REPO/tools/lib_m6f_measure.sh"
m6f_check_output_paths "$REPO" "$raw_dir" "$result" || gate_failed output_paths
[ ! -e "$result" ] || gate_failed result_exists
[ ! -e "$raw_dir" ] || gate_failed raw_dir_exists
[ -d "$(dirname "$result")" ] || gate_failed result_parent
if [ "${M6FH_TEST_SKIP_G1:-0}" = 1 ]; then
  ROM_DIR="${M6FH_TEST_ROM_DIR:-}"
  DISK_DIR="${M6FH_TEST_DISK_DIR:-}"
else
  ROM_DIR="${PC88_REF_ROM_DIR:-}"
  DISK_DIR="${PC88_REF_DISK_DIR:-}"
fi
[ -n "$ROM_DIR" ] && [ -d "$ROM_DIR" ] || gate_failed rom_dir
[ -n "$DISK_DIR" ] && [ -d "$DISK_DIR" ] || gate_failed disk_dir
REF_DISK="$DISK_DIR/$(m6f_cfg "$CONFIG" reference_disk)"
[ -f "$REF_DISK" ] || gate_failed reference_disk
REF_SHA="$(m6f_sha256 "$REF_DISK")" || gate_failed reference_sha
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
if [ "${M6FH_TEST_SKIP_G1:-0}" != 1 ]; then
  "$REPO/tools/make_m6fc_blank_disk_selftest.sh" >"$WORK/g1a" 2>&1 || gate_failed G1
  "$REPO/tools/measure_m6fh_driver_selftest.sh" >"$WORK/g1b" 2>&1 || gate_failed G1
fi
source "$REPO/tools/lib_l3_measure.sh"
CORE="${M6FH_TEST_CORE:-$(find_l3_core)}"; [ -n "$CORE" ] || gate_failed core
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || gate_failed frontend
else
  [ -x "$FRONTEND" ] || gate_failed frontend
fi
mkdir -p "$raw_dir" || gate_failed raw_dir
RUNS="$WORK/runs.ndjson"; : > "$RUNS"
for arm in H-1 H-2 H-3 H-0; do
  frames="$(m6f_keyed_cfg "$CONFIG" frames "$arm")" || gate_failed frames
  stimulus="$(python3 - "$REPO" "$arm" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]+'/tools')
import m6fh_script as s
print(s.escaped(s.keystrokes(sys.argv[2])))
PY
)" || gate_failed keystrokes
  for rep in 1 2; do
    disk1="$WORK/$arm-r$rep.drive1.d88"; disk2="$WORK/$arm-r$rep.drive2.d88"
    cp "$REF_DISK" "$disk1" || gate_failed reference_copy
    chmod u+w "$disk1" || gate_failed reference_mode
    python3 "$REPO/tools/make_m6fc_blank_disk.py" "$disk2" --fat-value 0xFF --filler 0xFF --sector-fill 18,1,13=0x00 >"$WORK/g2" 2>&1 || gate_failed G2
    [ "$(m6f_sha256 "$disk2")" = "$(m6f_cfg "$CONFIG" media_sha256)" ] || gate_failed G2
    report="$WORK/$arm-r$rep.report.json"; iolog="$WORK/$arm-r$rep.iolog.txt"
    qargs=(--core "$CORE" --rom-dir "$ROM_DIR" --disk "$disk1" --disk2 "$disk2"
      --save-to-disk-image --frames "$frames" --io-log "$iolog"
      --screen-signature-only --screen-signature-at "final:$frames" --out "$report"
      --type-at 300 --type '\n' --type-at 700 --type "$stimulus")
    launches=$((launches+1))
    M6FH_LONG_TYPING=1 /usr/bin/perl -e 'alarm shift; exec @ARGV' "$(m6f_cfg "$CONFIG" run_timeout_seconds)" "$FRONTEND" "${qargs[@]}" >"$WORK/stdout" 2>"$WORK/stderr" || gate_failed emulator_run
    [ -f "$report" ] || gate_failed signature_report
    [ "$(m6f_sha256 "$disk1")" = "$REF_SHA" ] && [ "$(m6f_sha256 "$REF_DISK")" = "$REF_SHA" ] || gate_failed G5
    safe="$WORK/$arm-r$rep.safe.json"
    python3 "$REPO/tools/m6fh_body.py" --image "$disk2" --arm "$arm" >"$safe" || gate_failed G6
    python3 - "$safe" "$arm" "$rep" <<'PY' >> "$RUNS" || gate_failed result_record
import json,sys
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text())
r.update(arm=sys.argv[2],repetition=int(sys.argv[3]),drive1_sha_ok=True)
print(json.dumps(r,sort_keys=True,separators=(',',':')))
PY
    if [ "$keep" = 1 ]; then cp "$disk2" "$raw_dir/$arm-r$rep.drive2.d88" || gate_failed keep_image; fi
  done
done
python3 - "$RUNS" "$result" <<'PY' || gate_failed result_write
import json,sys
from pathlib import Path
runs=[json.loads(x) for x in Path(sys.argv[1]).read_text().splitlines()]
with Path(sys.argv[2]).open('x',encoding='utf-8') as f:
    json.dump({'schema':1,'runs':runs},f,sort_keys=True,separators=(',',':'))
    f.write('\n')
PY
python3 "$REPO/tools/judge_m6fh.py" --result "$result"
