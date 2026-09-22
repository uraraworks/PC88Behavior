#!/usr/bin/env bash
# m6i-d D-B0〜D-B6-A0の同期ドライバ。G3/G7、次にm6i-b G4を通す。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FROZEN_CONFIG="${M6ID_FROZEN_CONFIG:-$REPO/tools/m6id_frozen.tsv}"
if ! python3 "$REPO/tools/check_m6id_preregistration.py" --config "$FROZEN_CONFIG"; then
  printf '%s\n' '{"judgment":"gate_failed","reason":"preregistration_mismatch"}'
  exit 1
fi

source "$REPO/tools/lib_l3_measure.sh"
FRONTEND="${M6ID_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"

cfg() {
  awk -F '\t' -v key="$1" '$1==key { if (++n==1) value=$2 } END { if (n==1) print value; else exit 1 }' "$FROZEN_CONFIG"
}

arm=""
result=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arm) arm="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
case "$arm" in D-B0|D-B1|D-B2|D-B3|D-B4|D-B5|D-B6-A0) ;; *) exit 2 ;; esac
[ -n "$result" ] && [ -d "$(dirname "$result")" ] || exit 2

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 既存G4がbuild_m6ib_measure_rom.pyで全12腕を一度だけ生成する。その検査済み
# 成果物から本測定の対象腕を選び、同じROM集合をfrontendへ渡す。
if ! python3 "$REPO/tools/check_m6ib_rom_gate.py" --work-dir "$WORK/rom-gate" \
    >"$WORK/rom-gate.out" 2>"$WORK/rom-gate.err"; then
  printf '%s\n' '{"judgment":"gate_failed","reason":"rom_gate_failed"}' | tee "$result"
  exit 1
fi
case "$arm" in
  D-B6-A0) base_arm="B6-A0"; rom_dir="$WORK/rom-gate/b6-a0" ;;
  *) base_arm="${arm#D-}"; rom_dir="$WORK/rom-gate/$(printf '%s' "$base_arm" | tr '[:upper:]' '[:lower:]')" ;;
esac
expected_rom_sha="$(python3 - "$WORK/rom-gate.out" "$base_arm" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value = payload["sha256"][sys.argv[2]]
if not isinstance(value, str) or len(value) != 64:
    raise SystemExit(1)
print(value)
PY
)" || exit 1

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
alarm_seconds=180
key_frame=$((frames - 50))
qargs=(--core "$CORE" --rom-dir "$rom_dir" --frames "$frames"
       --io-log "$WORK/run.io.txt" --out "$WORK/run.report.txt"
       --key-matrix "0x04:1:${key_frame}:10" --disk "$WORK/generated.d88")
/usr/bin/perl -e 'alarm shift; exec @ARGV' "$alarm_seconds" "$FRONTEND" \
  "${qargs[@]}" >"$WORK/run.stdout.txt" 2>"$WORK/run.stderr.txt" || exit 1

python3 "$REPO/tools/analyze_m6id.py" --arm "$arm" \
  --iolog "$WORK/run.io.txt" --rom-dir "$rom_dir" \
  --expected-rom-set-sha256 "$expected_rom_sha" --config "$FROZEN_CONFIG" \
  | tee "$result"
exit "${PIPESTATUS[0]}"
