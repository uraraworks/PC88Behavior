#!/usr/bin/env bash
# m6f-a測定ドライバ。親セッションが全7腕×2走をまとめて実行する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${M6FA_FROZEN_CONFIG:-$REPO/tools/m6fa_frozen.tsv}"
FRONTEND="${M6FA_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s"}\n' "$1"; exit 1; }

# G7は引数解釈や環境参照より先に固定値を照合する。
python3 "$REPO/tools/check_m6fa_preregistration.py" --config "$CONFIG" >/dev/null 2>&1 \
  || gate_failed preregistration_mismatch
source "$REPO/tools/lib_m6f_measure.sh"

raw_dir="$REPO/../tmp/m6-work/m6fa-raw"; result=""
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
disk_name="$(awk -F '\t' '$1=="reference_disk" {if (++n==1) v=$2} END {if (n==1) print v; else exit 1}' "$CONFIG")" \
  || gate_failed reference_disk_config
REFERENCE="$PC88_REF_DISK_DIR/$disk_name"
[ -f "$REFERENCE" ] || gate_failed reference_disk_missing

# 生差分と安全な結果のどちらもrepo内へ書かない。実体パスで判定する。
m6f_check_output_paths "$REPO" "$raw_dir" "$result" || gate_failed G6
mkdir -p "$raw_dir" || gate_failed raw_dir
[ -d "$(dirname "$result")" ] || gate_failed result_parent
[ ! -e "$result" ] || gate_failed result_exists
for arm in F0 F1 F2 F3 F4 F5 F6; do
  for run in 1 2; do
    [ ! -e "$raw_dir/$arm-r$run.diff.json" ] || gate_failed raw_output_exists
  done
done

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
cfg() { m6f_cfg "$CONFIG" "$1"; }
sha256() { m6f_sha256 "$1"; }

# G1〜G3。ここを通るまではfrontendをビルドも起動もしない。
# G1（run_all_selftests.sh 全体）はここでは回さない。m6i-c/g/h/i と同じく、腕を回す前に
# 親セッションで1回通す運用とする。とくにこのドライバは公式環境の変数を受け取るので、
# 中で回すと普段 SKIP される公式適合検査（conform_l3.sh 等）まで走り、腕に入る前に
# 1時間近くかかる。事前登録が要求するのは「腕の前に G1 が真であること」である。
"$REPO/tools/check_cleanroom.sh" >"$WORK/g2.out" 2>"$WORK/g2.err" || gate_failed G2
"$REPO/tools/d88_diff_selftest.sh" >"$WORK/g3.out" 2>"$WORK/g3.err" || gate_failed G3

source "$REPO/tools/lib_l3_measure.sh"
CORE="$(find_l3_core)"; [ -n "$CORE" ] || gate_failed core_missing
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || gate_failed frontend_missing
else
  [ -x "$FRONTEND" ] || gate_failed frontend_missing
fi
frames="$(cfg measurement_frames)"; timeout="$(cfg run_timeout_seconds)"
boot_frame="$(cfg boot_return_frame)"; stimulus_frame="$(cfg stimulus_frame)"
reference_sha="$(sha256 "$REFERENCE")" || gate_failed reference_sha

M6F_REPO="$REPO"; M6F_CONFIG="$CONFIG"; M6F_FRONTEND="$FRONTEND"
M6F_WORK="$WORK"; M6F_RAW_DIR="$raw_dir"; M6F_REFERENCE="$REFERENCE"
M6F_REFERENCE_SHA="$reference_sha"; M6F_CORE="$CORE"; M6F_FRAMES="$frames"
M6F_TIMEOUT="$timeout"; M6F_BOOT_FRAME="$boot_frame"
M6F_STIMULUS_FRAME="$stimulus_frame"; M6F_CONTROL_ARM="F0"

run_one() {
  m6f_run_one "$1" "$2"
}

# F0を先に2走し、G4を通らなければ刺激腕へ進まない。
run_one F0 1; run_one F0 2
python3 - "$WORK/F0-r1.safe.json" "$WORK/F0-r2.safe.json" <<'PY' || gate_failed G4
import json,sys
rows=[json.load(open(x)) for x in sys.argv[1:]]
raise SystemExit(0 if all(x['reached'] and x['write_data_count']==0 and
                          x['changed_sector_count']==0 and x['changed_byte_count']==0
                          for x in rows) else 1)
PY
for arm in F1 F2 F3 F4 F5 F6; do
  run_one "$arm" 1; run_one "$arm" 2
done

python3 - "$WORK" "$result" "$reference_sha" <<'PY' || gate_failed result_write
import hashlib,json,sys
from pathlib import Path
work,out,refsha=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
runs=[]
for arm in [f'F{i}' for i in range(7)]:
    for run in (1,2): runs.append(json.load(open(work/f'{arm}-r{run}.safe.json')))
body={'schema':1,'runs':runs,'reference_sha256':refsha,
      'all_reached':all(x['reached'] for x in runs),
      'run_count':len(runs)}
with out.open('x',encoding='utf-8') as f:
    json.dump(body,f,sort_keys=True,separators=(',',':')); f.write('\n')
PY
printf 'm6f-a measurement complete: raw=%s result=%s\n' "$raw_dir" "$result"
