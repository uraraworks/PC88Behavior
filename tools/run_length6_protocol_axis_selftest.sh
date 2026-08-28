#!/usr/bin/env bash
# m7dmでの`run_length6_protocol_axis.py`の陽性対照・故障注入。
# 公式ROM・公式ディスク・公式ログは使用しない。
# 全項目一致ならrc=0、1つでも不一致ならrc=1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/run_length6_protocol_axis_selftest.py"
