#!/usr/bin/env bash
# m7dfで事前登録したFE/SENDのrun切り出し誤差を合成ログで検算する。
# 公式ROM・公式ディスク・公式ログは使用しない。
# 全予測一致かつ故障注入の空振り0件ならrc=0、それ以外はrc=1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/run_cutter_positive_selftest.py"
