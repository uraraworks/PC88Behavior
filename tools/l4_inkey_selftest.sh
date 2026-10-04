#!/usr/bin/env bash
# l4-s9c: 自作ROMの定数と合成対照のみ。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# 制限付き環境でも指定コマンドだけで検証できるよう、一時領域を使う。
if [[ $# -eq 0 ]]; then
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/l4s9c-selftest.XXXXXX")"
  trap 'rm -rf "$WORK"' EXIT
  python3 "$REPO/tools/l4_inkey_measure.py" selftest --work-dir "$WORK"
else
  python3 "$REPO/tools/l4_inkey_measure.py" selftest "$@"
fi
