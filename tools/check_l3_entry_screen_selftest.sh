#!/usr/bin/env bash
# check_l3_entry_screen.py のRUN"file" / MERGE到達判定自己検査。
# 入力はすべて自作の合成画面で、実画面本文は扱わない。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO/tools/check_l3_entry_screen.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

cat > "$WORK/run-positive.txt" <<'EOF'
  0| run"q7u"
  1| R7X
  2| Ok
EOF
cat > "$WORK/run-negative.txt" <<'EOF'
  0| run"q7u"
  1| Ok
EOF
cat > "$WORK/merge-positive.txt" <<'EOF'
  0| 10 print "m7a"
  1| merge"q7m"
  2| Ok
  3| run
  4| M7A
  5| M7B
  6| Ok
EOF
cat > "$WORK/merge-negative.txt" <<'EOF'
  0| 10 print "m7a"
  1| merge"q7m"
  2| Ok
  3| run
  4| M7A
  5| Ok
EOF

if python3 "$CHECK" --report "$WORK/run-positive.txt" --scenario run_file \
     >/dev/null 2>&1 \
   && ! python3 "$CHECK" --report "$WORK/run-negative.txt" --scenario run_file \
        >/dev/null 2>&1; then
  ok 'RUN"file": 実行マーカーを持つ陽性と、欠く陰性を区別'
else
  ng 'RUN"file": 陽性・陰性対照を区別できない'
fi

if python3 "$CHECK" --report "$WORK/merge-positive.txt" --scenario merge \
     >/dev/null 2>&1 \
   && ! python3 "$CHECK" --report "$WORK/merge-negative.txt" --scenario merge \
        >/dev/null 2>&1; then
  ok 'MERGE: 元行・併合行を持つ陽性と、併合行を欠く陰性を区別'
else
  ng 'MERGE: 陽性・陰性対照を区別できない'
fi

exit "$rc"
