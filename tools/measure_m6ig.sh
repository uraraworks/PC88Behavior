#!/usr/bin/env bash
# m6i-g の同期ドライバ。G3/G9、G4の順に通した後だけエミュレータを起動する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FROZEN_CONFIG="${M6IG_FROZEN_CONFIG:-$REPO/tools/m6ig_frozen.tsv}"
if ! python3 "$REPO/tools/check_m6ig_preregistration.py" --config "$FROZEN_CONFIG"; then
  printf '%s\n' '{"judgment":"gate_failed","reason":"preregistration_mismatch"}'
  exit 1
fi

source "$REPO/tools/lib_l3_measure.sh"
FRONTEND="${M6IG_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
cfg() {
  awk -F '\t' -v key="$1" '$1==key {if (++n==1) value=$2} END {if (n==1) print value; else exit 1}' "$FROZEN_CONFIG"
}

arm=""; result=""; fault=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arm) arm="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    --g5-fault) fault="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
case "$arm" in G-N|G-L0|G-L1|G-L2) ;; *) exit 2 ;; esac
[ -n "$result" ] && [ -d "$(dirname "$result")" ] || exit 2
case "$fault" in
  ""|state_changed|read_issue_frame_changed|request_counter_fixed|shared_state_event) ;;
  *) exit 2 ;;
esac

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
for gate_arm in G-N G-L0 G-L1 G-L2; do
  python3 "$REPO/tools/build_m6ig_measure_rom.py" "$WORK/rom-$gate_arm" \
    --arm "$gate_arm" --work-dir "$WORK/build-$gate_arm" \
    >"$WORK/build-$gate_arm.out" 2>"$WORK/build-$gate_arm.err" || {
      printf '%s\n' '{"judgment":"gate_failed","reason":"rom_build_failed"}' | tee "$result"
      exit 1
    }
done
for ref_arm in B0 B1 B4 B5; do
  python3 "$REPO/tools/build_m6ib_measure_rom.py" "$WORK/ref-$ref_arm" \
    --arm "$ref_arm" --work-dir "$WORK/build-ref-$ref_arm" \
    >"$WORK/ref-$ref_arm.out" 2>"$WORK/ref-$ref_arm.err" || exit 1
done
if ! python3 "$REPO/tools/check_m6ig_rom_gate.py" \
    "$WORK/rom-G-N" "$WORK/rom-G-L0" "$WORK/rom-G-L1" "$WORK/rom-G-L2" \
    --m6ib-b0-dir "$WORK/ref-B0" --m6ib-b1-dir "$WORK/ref-B1" \
    --m6ib-b4-dir "$WORK/ref-B4" --m6ib-b5-dir "$WORK/ref-B5" \
    --config "$FROZEN_CONFIG" >"$WORK/rom-gate.out" 2>"$WORK/rom-gate.err"; then
  printf '%s\n' '{"judgment":"gate_failed","reason":"rom_gate_failed"}' | tee "$result"
  exit 1
fi

python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/generated.d88" \
  --cylinders 40 --double-sided --sectors-per-track 16 \
  >"$WORK/disk.out" 2>"$WORK/disk.err" || exit 1
disk_sha="$(shasum -a 256 "$WORK/generated.d88" | awk '{print $1}')"
if [ "$disk_sha" != "$(cfg normal_media_sha256)" ]; then
  printf '%s\n' '{"judgment":"gate_failed","reason":"media_sha_mismatch"}' | tee "$result"
  exit 1
fi

CORE="$(find_l3_core)"
[ -n "$CORE" ] && ensure_l3_frontend || exit 1
frames="$(cfg arm_frames)"
# 発行はG-N=6、他=60だが、終了確認の打鍵は全腕で共通の測定期限から決める。
key_frame=$((frames - 50))
qargs=(--core "$CORE" --rom-dir "$WORK/rom-$arm" --frames "$frames"
       --io-log "$WORK/run.io.txt" --int-log "$WORK/run.int.txt"
       --mem-write-log "$WORK/run.mem.txt" --mem-write-range DF00-E038
       --out "$WORK/run.report.txt" --key-matrix "0x04:1:${key_frame}:10"
       --disk "$WORK/generated.d88")
/usr/bin/perl -e 'alarm shift; exec @ARGV' 180 "$FRONTEND" \
  "${qargs[@]}" >"$WORK/run.stdout.txt" 2>"$WORK/run.stderr.txt" || exit 1

extra_fault=()
if [ -n "$fault" ]; then extra_fault+=(--fault "$fault"); fi
python3 "$REPO/tools/analyze_m6ig.py" --arm "$arm" \
  --iolog "$WORK/run.io.txt" --memlog "$WORK/run.mem.txt" \
  --report "$WORK/run.report.txt" --intlog "$WORK/run.int.txt" \
  --rom-dir "$WORK/rom-$arm" --config "$FROZEN_CONFIG" \
  ${extra_fault[@]+"${extra_fault[@]}"} | tee "$result"
exit "${PIPESTATUS[0]}"
