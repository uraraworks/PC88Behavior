#!/usr/bin/env bash
# m6f-b測定ドライバ。全9腕×2走を新しい使い捨て複製で実行する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${M6FB_FROZEN_CONFIG:-$REPO/tools/m6fb_frozen.tsv}"
FRONTEND="${M6FB_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s"}\n' "$1"; exit 1; }

# 凍結照合は引数解釈・環境参照・frontend起動より先に行う。
python3 "$REPO/tools/check_m6fb_preregistration.py" --config "$CONFIG" >/dev/null 2>&1 \
  || gate_failed preregistration_mismatch
source "$REPO/tools/lib_m6f_measure.sh"

raw_dir="$REPO/../tmp/m6-work/m6fb-raw"; result=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --raw-dir) raw_dir="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
[ -n "$raw_dir" ] && [ -n "$result" ] || exit 2
[ -n "${PC88_REF_ROM_DIR:-}" ] || gate_failed PC88_REF_ROM_DIR_missing
[ -n "${PC88_REF_DISK_DIR:-}" ] || gate_failed PC88_REF_DISK_DIR_missing
[ -d "$PC88_REF_ROM_DIR" ] || gate_failed reference_rom_dir_missing
disk_name="$(m6f_cfg "$CONFIG" reference_disk)" || gate_failed reference_disk_config
REFERENCE="$PC88_REF_DISK_DIR/$disk_name"
[ -f "$REFERENCE" ] || gate_failed reference_disk_missing

# 生差分と安全な結果はどちらもリポジトリ外だけを許す。
m6f_check_output_paths "$REPO" "$raw_dir" "$result" || gate_failed G6
mkdir -p "$raw_dir" || gate_failed raw_dir
[ -d "$(dirname "$result")" ] || gate_failed result_parent
[ ! -e "$result" ] || gate_failed result_exists
for arm in G0 G1 G2 G3 G4 G5 G6 G7 G8; do
  for run in 1 2; do
    [ ! -e "$raw_dir/$arm-r$run.diff.json" ] || gate_failed raw_output_exists
  done
done

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# 重い全体検査は親セッションが腕の前に一度だけ行う。ここでは軽い関門だけを通す。
"$REPO/tools/check_cleanroom.sh" >"$WORK/g2.out" 2>"$WORK/g2.err" || gate_failed G2
"$REPO/tools/d88_diff_selftest.sh" >"$WORK/g3.out" 2>"$WORK/g3.err" || gate_failed G3

source "$REPO/tools/lib_l3_measure.sh"
CORE="$(find_l3_core)"; [ -n "$CORE" ] || gate_failed core_missing
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || gate_failed frontend_missing
else
  [ -x "$FRONTEND" ] || gate_failed frontend_missing
fi
frames="$(m6f_cfg "$CONFIG" measurement_frames)"
timeout="$(m6f_cfg "$CONFIG" run_timeout_seconds)"
boot_frame="$(m6f_cfg "$CONFIG" boot_return_frame)"
stimulus_frame="$(m6f_cfg "$CONFIG" stimulus_frame)"
reference_sha="$(m6f_sha256 "$REFERENCE")" || gate_failed reference_sha

M6F_REPO="$REPO"; M6F_CONFIG="$CONFIG"; M6F_FRONTEND="$FRONTEND"
M6F_WORK="$WORK"; M6F_RAW_DIR="$raw_dir"; M6F_REFERENCE="$REFERENCE"
M6F_REFERENCE_SHA="$reference_sha"; M6F_CORE="$CORE"; M6F_FRAMES="$frames"
M6F_TIMEOUT="$timeout"; M6F_BOOT_FRAME="$boot_frame"
M6F_STIMULUS_FRAME="$stimulus_frame"; M6F_CONTROL_ARM="G0"

# 陰性対照を先に2走し、空でなければ刺激腕へ進まない。
m6f_run_one G0 1; m6f_run_one G0 2
python3 - "$WORK/G0-r1.safe.json" "$WORK/G0-r2.safe.json" <<'PY' || gate_failed G4
import json,sys
rows=[json.load(open(path,encoding='utf-8')) for path in sys.argv[1:]]
raise SystemExit(0 if all(row['reached'] and row['write_data_count']==0 and
                          row['changed_sector_count']==0 and row['changed_byte_count']==0
                          for row in rows) else 1)
PY

# Sの前提をG1の両走で再確認してから、残りの腕へ進む。
m6f_run_one G1 1; m6f_run_one G1 2
python3 - "$raw_dir/G1-r1.diff.json" "$raw_dir/G1-r2.diff.json" <<'PY' || gate_failed G8
import json,sys
target=(18,1,3)
for path in sys.argv[1:]:
    doc=json.load(open(path,encoding='utf-8'))
    changed={(int(row['c']),int(row['h']),int(row['r'])) for row in doc['changes']}
    if target not in changed:
        raise SystemExit(1)
PY
for arm in G2 G3 G4 G5 G6 G7 G8; do
  m6f_run_one "$arm" 1; m6f_run_one "$arm" 2
done

python3 - "$WORK" "$result" "$reference_sha" <<'PY' || gate_failed result_write
import json,sys
from pathlib import Path
work,out,refsha=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
runs=[]
for arm in [f'G{i}' for i in range(9)]:
    for run in (1,2):
        runs.append(json.load(open(work/f'{arm}-r{run}.safe.json',encoding='utf-8')))
body={'schema':1,'runs':runs,'reference_sha256':refsha,
      'all_reached':all(row['reached'] for row in runs),'run_count':len(runs),
      'directory_sector_changed':True}
with out.open('x',encoding='utf-8') as stream:
    json.dump(body,stream,sort_keys=True,separators=(',',':')); stream.write('\n')
PY
printf 'm6f-b measurement complete: raw=%s result=%s\n' "$raw_dir" "$result"
