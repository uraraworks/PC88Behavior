#!/usr/bin/env bash
# check_l3_entry_screen.py のRUN"file" / MERGE / BSAVE・BLOAD到達判定自己検査。
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
cat > "$WORK/bsave-positive.txt" <<'EOF'
  0| clear ,&hbfff
  1| Ok
  2| poke &hc000,71:poke &hc001,149:poke &hc002,203:poke &hc003,37
  3| Ok
  4| if peek(&hc000)=71 and peek(&hc001)=149 then print"b7s" else print"b7f"
  5| B7S
  6| Ok
  7| bsave"q7b",&hc000,4
  8| Ok
EOF
cat > "$WORK/bsave-negative.txt" <<'EOF'
  0| clear ,&hbfff
  1| Ok
  2| poke &hc000,71:poke &hc001,149:poke &hc002,203:poke &hc003,37
  3| Ok
  4| if peek(&hc000)=71 then print"b7s" else print"b7f"
  5| B7F
  6| Ok
  7| bsave"q7b",&hc000,4
  8| Ok
EOF
cat > "$WORK/bsave-no-ok.txt" <<'EOF'
  0| clear ,&hbfff
  1| Ok
  2| poke &hc000,71:poke &hc001,149:poke &hc002,203:poke &hc003,37
  3| Ok
  4| if peek(&hc000)=71 then print"b7s" else print"b7f"
  5| B7S
  6| Ok
  7| bsave"q7b",&hc000,4
  8| Synthetic failure
EOF
cat > "$WORK/bload-positive.txt" <<'EOF'
  0| clear ,&hbfff
  1| Ok
  2| poke &hc000,0:poke &hc001,0:poke &hc002,0:poke &hc003,0
  3| Ok
  4| bload"q7b"
  5| Ok
  6| if peek(&hc000)=71 and peek(&hc001)=149 then print"b7x" else print"b7n"
  7| B7X
  8| Ok
EOF
cat > "$WORK/bload-negative.txt" <<'EOF'
  0| clear ,&hbfff
  1| Ok
  2| poke &hc000,0:poke &hc001,0:poke &hc002,0:poke &hc003,0
  3| Ok
  4| bload"q7b"
  5| Ok
  6| if peek(&hc000)=71 then print"b7x" else print"b7n"
  7| B7N
  8| Ok
EOF
cat > "$WORK/random-positive.txt" <<'EOF'
  0| run
  1| R7C
  2| R7A
  3| R7D
  4| R7B
  5| R7E
  6| Ok
EOF
sed 's/  2| R7A/  2| R7N/' "$WORK/random-positive.txt" > "$WORK/random-bad-record1.txt"
sed 's/  4| R7B/  4| R7N/' "$WORK/random-positive.txt" > "$WORK/random-bad-record2.txt"

if python3 "$CHECK" --report "$WORK/run-positive.txt" --scenario run_file >/dev/null 2>&1 \
   && ! python3 "$CHECK" --report "$WORK/run-negative.txt" --scenario run_file >/dev/null 2>&1; then
  ok 'RUN"file": 実行マーカーを持つ陽性と、欠く陰性を区別'
else
  ng 'RUN"file": 陽性・陰性対照を区別できない'
fi

if python3 "$CHECK" --report "$WORK/merge-positive.txt" --scenario merge >/dev/null 2>&1 \
   && ! python3 "$CHECK" --report "$WORK/merge-negative.txt" --scenario merge >/dev/null 2>&1; then
  ok 'MERGE: 元行・併合行を持つ陽性と、併合行を欠く陰性を区別'
else
  ng 'MERGE: 陽性・陰性対照を区別できない'
fi

if python3 "$CHECK" --report "$WORK/bsave-positive.txt" --scenario bsave >/dev/null 2>&1 \
   && ! python3 "$CHECK" --report "$WORK/bsave-negative.txt" --scenario bsave >/dev/null 2>&1 \
   && ! python3 "$CHECK" --report "$WORK/bsave-no-ok.txt" --scenario bsave >/dev/null 2>&1; then
  ok 'BSAVE: 陽性と、保存前不一致・直後Ok欠落の陰性を区別'
else
  ng 'BSAVE: 陽性・陰性対照を区別できない'
fi

if python3 "$CHECK" --report "$WORK/bload-positive.txt" --scenario bload >/dev/null 2>&1 \
   && ! python3 "$CHECK" --report "$WORK/bload-negative.txt" --scenario bload >/dev/null 2>&1; then
  ok 'BLOAD: 読込み効果を持つ陽性と、直後Okだけの陰性を区別'
else
  ng 'BLOAD: 陽性・陰性対照を区別できない'
fi

if python3 "$CHECK" --report "$WORK/random-positive.txt" --scenario random_file >/dev/null 2>&1 \
   && ! python3 "$CHECK" --report "$WORK/random-bad-record1.txt" --scenario random_file >/dev/null 2>&1 \
   && ! python3 "$CHECK" --report "$WORK/random-bad-record2.txt" --scenario random_file >/dev/null 2>&1; then
  ok 'ランダムファイル: 2レコード読戻し陽性と、各片方だけ失敗する陰性を区別'
else
  ng 'ランダムファイル: 陽性・陰性対照を区別できない'
fi

exit "$rc"
