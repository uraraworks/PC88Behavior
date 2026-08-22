#!/usr/bin/env bash
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88-k00-metrics-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

make_logs() {
  local mode="$1"
  local off="$WORK/official-${mode}.txt"
  local mix="$WORK/mixed-${mode}.txt"
  {
    echo '1 10 0 main IN 00FE 10 1000'
    echo '2 20 0 main IN 00FE 20 1001'
    echo '3 30 0 main IN 00FE 30 1002'
  } >"$off"
  {
    echo '1 10 0 sub OUT 00FF 0B 2000'
    echo '2 20 0 sub IN 00FC -- 2001'
    echo '3 30 0 sub OUT 00FF 0B 2002'
    if [ "$mode" = "blank" ]; then
      echo '4 35 0 sub OUT 00FD -- 2003'
    fi
    echo '5 40 0 sub IN 00FC -- 2004'
    echo '6 50 0 main IN 00FE 10 1000'
    if [ "$mode" = "early" ]; then
      echo '7 60 0 main IN 00FE 99 1001'
    else
      echo '7 60 0 main IN 00FE 20 1001'
    fi
    echo '8 70 0 main IN 00FE 31 1002'
  } >"$mix"
}

make_logs normal
if ! python3 "$REPO/tools/check_k00_completion_metrics.py" \
    --official "$WORK/official-normal.txt" --mixed "$WORK/mixed-normal.txt" \
    --expected-corresponding 2 --min-nondata-difference 3 >/dev/null; then
  echo 'NG: 無傷の陽性対照が不合格'
  exit 1
fi

make_logs blank
if python3 "$REPO/tools/check_k00_completion_metrics.py" \
    --official "$WORK/official-blank.txt" --mixed "$WORK/mixed-blank.txt" \
    --expected-corresponding 2 --min-nondata-difference 3 >/dev/null 2>&1; then
  echo 'NG: 空振り故障注入を検出できない'
  exit 1
fi

make_logs early
if python3 "$REPO/tools/check_k00_completion_metrics.py" \
    --official "$WORK/official-early.txt" --mixed "$WORK/mixed-early.txt" \
    --expected-corresponding 2 --min-nondata-difference 3 >/dev/null 2>&1; then
  echo 'NG: 非データ差位置の後退を検出できない'
  exit 1
fi

echo 'check_k00_completion_metrics_selftest: OK（無傷合格、空振り・差位置後退を検出）'
