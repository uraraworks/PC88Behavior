#!/usr/bin/env bash
# tools/build_blank_data_disk.py の自己検査（決定性・規則照合・陰性対照・上書き拒否）。
# 合成D88だけで完結し、公式ROM・公式ディスク・private/ には触れない。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEN="$REPO/tools/build_blank_data_disk.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 "$GEN" --check || exit 1
python3 "$GEN" "$WORK/a.d88" >/dev/null || exit 1
python3 "$GEN" "$WORK/b.d88" >/dev/null || exit 1
cmp -s "$WORK/a.d88" "$WORK/b.d88" && echo "OK: 別プロセスでも同一バイト列" || { echo "NG: 別プロセスで不一致"; exit 1; }
python3 "$GEN" "$WORK/a.d88" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && echo "OK: 既存ファイルを上書きしない(rc=2)" || { echo "NG: 上書き拒否rc=$rc"; exit 1; }
