#!/usr/bin/env bash
# l4-s9w。現在の src/ の自作ROMで PAINT の測定器具を全腕（2走ずつ）走らせ、公式観測の期待値
# （tests/conformance/expected_l4_paint.tsv）と腕ごとに照合する。公式ROMは不要。
# 使い方: tools/l4_paint_conform.sh [作業ディレクトリ(絶対パス)] [--only 腕ID,腕ID]
# 不一致があれば DIFF 行（画素数・ハッシュ・欠け/余りの画素数・結果行の差）を出して rc=1。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${1:-$REPO/../tmp/s9w-work}"
ONLY="${3:-}"
mkdir -p "$WORK"
python3 "$REPO/src/build_main_rom.py" "$WORK/conform-rom" --work-dir "$WORK/conform-asm" >/dev/null
python3 "$REPO/tools/l4_paint_measure.py" measure --rom-dir "$WORK/conform-rom" --no-calibration \
  --out "$WORK/conform_own.tsv" --work-dir "$WORK/conform-w" ${ONLY:+--only "$ONLY"}
python3 "$REPO/tools/l4_paint_measure.py" check --expected "$REPO/tests/conformance/expected_l4_paint.tsv" \
  --measured "$WORK/conform_own.tsv" ${ONLY:+--only "$ONLY"}
