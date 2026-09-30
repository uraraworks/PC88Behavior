#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
# 器具が測る対象は「素の（旧）sub」＋腕ごとの main で、G4試走は素のsub SHAの一致、G6試走は
# 既定出力が baseline(9518294) と不変であることを見る。現在の作業ツリーは1.36aで sub と
# 既定出力が意図的に変わったため、器具を作った測定コミットの木で回す。
# 根拠: git log -1 --format=%H -- tools/m6ik_frozen.tsv
. "$(dirname "${BASH_SOURCE[0]}")/frozen_tree.sh"
use_frozen_checkout 2668f3f0b6de5e5b1333f0fd0b0514a90fa55f6f "$WORK"
for arm in K-00 K-01 K-F0 K-F1 K-M1 K-FR; do
  python3 "$REPO/src/build_main_rom.py" "$WORK/rom-$arm" --inject-m6ik-arm "$arm" \
    --work-dir "$WORK/build-$arm" >"$WORK/$arm.out"
done
python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/a.d88" --cylinders 40 \
  --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xA1 >/dev/null
python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/b.d88" --cylinders 40 \
  --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xB2 >/dev/null
python3 "$REPO/tools/check_m6ik_gates.py" --work "$WORK" \
  --sub-rom "$WORK/rom-K-F1/DISK.ROM" --dry-run >/dev/null
python3 - "$WORK" <<'PY'
import json,sys
from pathlib import Path
w=Path(sys.argv[1]); result=json.loads((w/'gates.json').read_text())
assert result['fr_difference_positions']==1
assert result['g6_mode']=='試走'
assert len(result['g6_output_sha256'])>=7
assert len(set(result['arm_main_sha256'].values()))==6
print('m6ik_build_selftest: G3/G4試走/G5/G6試走 OK')
PY
