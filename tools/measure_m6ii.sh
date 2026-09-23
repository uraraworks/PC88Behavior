#!/usr/bin/env bash
# m6i-i測定ドライバ。G1〜G10が全て真のときだけ選択腕を1走する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${M6II_FROZEN_CONFIG:-$REPO/tools/m6ii_frozen.tsv}"
FRONTEND="${M6II_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s"}\n' "$1"; exit 1; }
python3 "$REPO/tools/check_m6ii_preregistration.py" --config "$CONFIG" >/dev/null 2>&1 \
  || gate_failed preregistration_mismatch
arm=""; result=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arm) arm="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
case "$arm" in I-S|I-F-H|I-F-D|I-F-R|I-F-RETRY) ;; *) exit 2 ;; esac
[ -n "$result" ] && [ -d "$(dirname "$result")" ] || exit 2
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
cfg() { awk -F '\t' -v key="$1" '$1==key {if (++n==1) v=$2} END {if (n==1) print v; else exit 1}' "$CONFIG"; }

# G1/G2。ここを通る前にfrontendへ触れない。
"$REPO/tools/run_all_selftests.sh" >"$WORK/g1.out" 2>"$WORK/g1.err" || gate_failed G1
"$REPO/tools/check_cleanroom.sh" >"$WORK/g2.out" 2>"$WORK/g2.err" || gate_failed G2

GEOM=(--cylinders 40 --double-sided --sectors-per-track 16)
python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/legacy.d88" "${GEOM[@]}" >/dev/null || gate_failed G3
python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/a.d88" "${GEOM[@]}" \
  --content-rule coord-header --disk-id 0xA1 >/dev/null || gate_failed G4
python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/b.d88" "${GEOM[@]}" \
  --content-rule coord-header --disk-id 0xB2 >/dev/null || gate_failed G4

BUILD=(python3 "$REPO/src/build_main_rom.py")
build_rom() { local name="$1"; shift; "${BUILD[@]}" "$WORK/rom-$name" "$@" --work-dir "$WORK/build-$name" >/dev/null; }
build_rom main --enable-main-sub-read || gate_failed G8
build_rom retry --enable-disk-read-retry || gate_failed G8
build_rom chr --enable-disk-read-chr || gate_failed G8
build_rom plain || gate_failed G6
build_rom I-S --inject-m6ii-sweep || gate_failed G6
build_rom I-F-H --inject-m6ii-sweep --inject-m6ii-fault-h || gate_failed G6
build_rom I-F-D --inject-m6ii-sweep --inject-m6ii-fault-d || gate_failed G6
build_rom I-F-R --inject-m6ii-sweep --inject-m6ii-fault-r || gate_failed G6
build_rom I-F-RETRY --inject-m6ii-sweep --inject-m6ii-fault-retry || gate_failed G6

python3 - "$REPO" "$WORK" "$CONFIG" <<'PY' || gate_failed G3_G4_G5_G6_G8_G10
import ast,hashlib,sys
from pathlib import Path
repo,work,config=map(Path,sys.argv[1:])
sys.path.insert(0,str(repo/'tools'))
from d88_read_sector import D88Reader
from check_m6ii_preregistration import load_tsv,keyed,one,ARM_HASHES
cfg=load_tsv(config)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if sha(work/'legacy.d88')!=one(cfg,'normal_media_sha256'): raise SystemExit(1)
if sha(work/'a.d88')!=one(cfg,'disk_a_sha256') or sha(work/'b.d88')!=one(cfg,'disk_b_sha256'): raise SystemExit(1)
def payloads(path):
    r=D88Reader(path.read_bytes())
    return [r.read_sector(c,h,s) for c in range(40) for h in range(2) for s in range(1,17)]
a,b=payloads(work/'a.d88'),payloads(work/'b.d88'); legacy=payloads(work/'legacy.d88')
if len(set(a+b))!=2560 or len(set(legacy+legacy))==2560: raise SystemExit(1)
source=(repo/'tools/analyze_m6ii.py').read_text(); tree=ast.parse(source)
for node in ast.walk(tree):
    names=([x.name for x in node.names] if isinstance(node,ast.Import) else
           [node.module or ''] if isinstance(node,ast.ImportFrom) else [])
    if any(x.split('.')[-1]=='make_l3_testdisk' for x in names): raise SystemExit(1)
if any(x in source for x in ('iterdir(','.glob(','.rglob(','rom-dir','rom_dir','N88.ROM')): raise SystemExit(1)
expected={'main':'main_sub_sha256','retry':'disk_retry_sha256','chr':'disk_chr_sha256'}
for directory,key in expected.items():
    if sha(work/('rom-'+directory)/'N88.ROM')!=one(cfg,key): raise SystemExit(1)
plain=one(cfg,'plain_subrom_sha256')
for name in ('plain','I-S','I-F-H','I-F-D','I-F-R','I-F-RETRY'):
    if sha(work/('rom-'+name)/'DISK.ROM')!=plain: raise SystemExit(1)
for name,want in keyed(cfg['arm_sha256']).items():
    if sha(work/('rom-'+name)/'N88.ROM')!=want or want!=ARM_HASHES[name]: raise SystemExit(1)
PY

# G7は呼び先スタブを実Z80で走らせる既存の独立検査。
"$REPO/tools/disk_read_chr_z80_selftest.sh" >"$WORK/g7.out" 2>"$WORK/g7.err" || gate_failed G7

source "$REPO/tools/lib_l3_measure.sh"
CORE="$(find_l3_core)"; [ -n "$CORE" ] || gate_failed core_missing
ensure_l3_frontend || gate_failed frontend_missing
frames="$(cfg measurement_frames)"
qargs=(--core "$CORE" --rom-dir "$WORK/rom-$arm" --frames "$frames"
       --mem-write-log "$WORK/run.mem.txt" --mem-write-range DF00-E038
       --disk "$WORK/a.d88" --disk2 "$WORK/b.d88")
/usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$FRONTEND" "${qargs[@]}" \
  >"$WORK/run.stdout.txt" 2>"$WORK/run.stderr.txt" || gate_failed emulator_run
python3 "$REPO/tools/analyze_m6ii.py" --arm "$arm" --memlog "$WORK/run.mem.txt" \
  --disk-a "$WORK/a.d88" --disk-b "$WORK/b.d88" | tee "$result"
exit "${PIPESTATUS[0]}"
