#!/usr/bin/env bash
# ラベルにパス区切りを含む需要入口でも、期待値故障注入が空振りしないことを単独確認する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HASH="$REPO/tools/hash_io_stream.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK   %s\n' "$1"; }
ng() { printf 'NG   %s\n' "$1"; }
source "$REPO/tools/lib_l3_conformance.sh"

log="$REPO/tests/fixtures/conform_l3_selftest.iolog.txt"
expected="$REPO/tests/fixtures/conform_l3_selftest.expected.tsv"
label='ランダムアクセスファイルPUT/GET判定器'

if ! run_conformance "$log" "$expected" "${label}-無傷" >/dev/null; then
  ng '無傷の期待値が一致しない'
  exit 1
fi
if run_conformance "$log" /dev/null "${label}-空期待値故障" >/dev/null 2>&1; then
  ng '空の期待値が一致してしまった'
  exit 1
fi
ok 'ランダムアクセスファイルPUT/GET判定器: 空の期待値を不一致検出'
if entry_expected_fault_selftest "$log" "$expected" "$label"; then
  ok 'ランダムアクセスファイルPUT/GET判定器: 故障注入3件を検出'
  exit 0
fi
ng 'ランダムアクセスファイルPUT/GET判定器: 故障注入が空振りした'
exit 1
