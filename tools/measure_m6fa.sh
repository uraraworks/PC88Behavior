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

raw_dir="${HOME:?HOMEが未設定}/_claude_work/m6fa-raw"; result=""
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
python3 - "$REPO" "$raw_dir" "$result" <<'PY' || gate_failed G6
import sys
from pathlib import Path
repo=Path(sys.argv[1]).resolve()
for raw in sys.argv[2:]:
    path=Path(raw).resolve(strict=False)
    try: path.relative_to(repo)
    except ValueError: continue
    raise SystemExit(1)
PY
mkdir -p "$raw_dir" || gate_failed raw_dir
[ -d "$(dirname "$result")" ] || gate_failed result_parent
[ ! -e "$result" ] || gate_failed result_exists
for arm in F0 F1 F2 F3 F4 F5 F6; do
  for run in 1 2; do
    [ ! -e "$raw_dir/$arm-r$run.diff.json" ] || gate_failed raw_output_exists
  done
done

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
cfg() { awk -F '\t' -v key="$1" '$1==key {if (++n==1) v=$2} END {if (n==1) print v; else exit 1}' "$CONFIG"; }
keyed_cfg() { awk -F '\t' -v key="$1" -v subkey="$2" '$1==key && index($2,subkey ":")==1 {if (++n==1) print substr($2,length(subkey)+2)} END {if (n!=1) exit 1}' "$CONFIG"; }
sha256() { python3 - "$1" <<'PY'
import hashlib,sys
h=hashlib.sha256()
with open(sys.argv[1],'rb') as f:
    for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
print(h.hexdigest())
PY
}

# G1〜G3。ここを通るまではfrontendをビルドも起動もしない。
"$REPO/tools/run_all_selftests.sh" >"$WORK/g1.out" 2>"$WORK/g1.err" || gate_failed G1
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

run_one() {
  local arm="$1" run="$2" disk="$WORK/$arm-r$run.d88"
  local iolog="$WORK/$arm-r$run.iolog.txt" report="$WORK/$arm-r$run.report.txt"
  local stdout="$WORK/$arm-r$run.stdout.txt" stderr="$WORK/$arm-r$run.stderr.txt"
  local raw="$raw_dir/$arm-r$run.diff.json" safe="$WORK/$arm-r$run.safe.json"
  local stimulus initial after_ref
  stimulus="$(keyed_cfg keystrokes "$arm")" || gate_failed stimulus
  cp "$REFERENCE" "$disk" || gate_failed copy
  chmod u+w "$disk" || gate_failed copy_mode
  initial="$(sha256 "$disk")" || gate_failed copy_sha
  [ "$initial" = "$reference_sha" ] || gate_failed G5
  local qargs=(--core "$CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$disk"
    --save-to-disk-image --frames "$frames" --io-log "$iolog" --out "$report"
    --type-at "$boot_frame" --type '\n')
  if [ -n "$stimulus" ]; then
    qargs+=(--type-at "$stimulus_frame" --type "$stimulus")
  fi
  /usr/bin/perl -e 'alarm shift; exec @ARGV' "$timeout" "$FRONTEND" "${qargs[@]}" \
    >"$stdout" 2>"$stderr" || gate_failed emulator_run
  # reportは存在だけを確認し、中身は一切開かない。
  [ -e "$report" ] && [ -s "$iolog" ] || gate_failed measurement_artifact
  after_ref="$(sha256 "$REFERENCE")" || gate_failed reference_sha_after
  [ "$after_ref" = "$reference_sha" ] || gate_failed reference_changed
  python3 "$REPO/tools/d88_diff.py" "$REFERENCE" "$disk" --output "$raw" \
    || gate_failed G6_diff
  python3 - "$REPO" "$arm" "$run" "$iolog" "$raw" "$safe" \
    "$reference_sha" "$initial" "$(sha256 "$disk")" <<'PY' || gate_failed safe_summary
import hashlib,json,sys
from pathlib import Path
repo=Path(sys.argv[1]); sys.path.insert(0,str(repo/'tools'))
from analyze_main_to_sub import parse_iolog
from analyze_write_path import parse_commands
arm,run,iolog,raw,out,refsha,initial,final=sys.argv[2:]
rows,masked=parse_iolog(Path(iolog))
if sum(masked.values()): raise SystemExit(1)
commands=parse_commands(rows); writes=sum(c.opcode==0x05 for c in commands)
diff=json.load(open(raw,encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
changed_sectors=int(diff['changed_sectors']); changed_bytes=int(diff['changed_bytes'])
reached=True if arm=='F0' else writes>0 and changed_bytes>0
body={'arm':arm,'repetition':int(run),'write_data_count':writes,
      'changed_sector_count':changed_sectors,'changed_byte_count':changed_bytes,
      'reached':reached,'reference_unchanged':refsha==initial,
      'reference_sha256':refsha,'copy_initial_sha256':initial,
      'copy_final_sha256':final,'diff_sha256':sha(raw),'iolog_sha256':sha(iolog)}
with open(out,'x',encoding='utf-8') as f: json.dump(body,f,sort_keys=True,separators=(',',':'))
PY
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
