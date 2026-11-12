#!/usr/bin/env bash
# 自作サブの 0x16 定常受信の1バイトあたりTステートが 97430aa 以下であることの自己検査（G1 の1フレームずれの再発防止）。
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tools/sub_recv_timing_selftest.py
