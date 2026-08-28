#!/usr/bin/env bash
# m7diでのanalyze_run_cutter_attribution.py自体の陰性対照(分類器の出し分け、
# アンカー例外が常に0を返す壊れ方をしていないことの確認)。
# 公式ROM・公式ディスク・公式ログは使用しない。
# 全項目一致ならrc=0、1つでも不一致ならrc=1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/analyze_run_cutter_attribution_selftest.py"
