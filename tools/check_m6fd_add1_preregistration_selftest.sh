#!/usr/bin/env bash
# tools/check_m6fd_add1_preregistration.py の自己検査。
#   1. 陽性側: リポジトリ本体の tools/m6fd_add1_frozen.tsv は rc=0 で通る。
#   2. 陰性対照: 凍結表を改ざん(腕の1行を削る／segment本文を書き換える／
#      判定名を削る)すると rc!=0 になる。
#   3. 陰性対照: 追補1ノートの主要語を欠いたコピーだとrc!=0になる。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

if python3 "$REPO/tools/check_m6fd_add1_preregistration.py" >"$WORK/pos.out" 2>&1; then
  ok "陽性側: 本体の凍結表はrc=0で通る"
else
  ng "陽性側が失敗した: $(cat "$WORK/pos.out")"
fi

grep -v '^arm	E-33$' "$REPO/tools/m6fd_add1_frozen.tsv" > "$WORK/missing_arm.tsv"
if python3 "$REPO/tools/check_m6fd_add1_preregistration.py" --config "$WORK/missing_arm.tsv" \
    >"$WORK/neg1.out" 2>&1; then
  ng "陰性対照(腕欠落)を検出できなかった"
else
  ok "陰性対照(腕欠落): rc!=0で検出した"
fi

python3 - "$REPO/tools/m6fd_add1_frozen.tsv" "$WORK/bad_segment.tsv" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8").read().splitlines()
changed = False
for i, line in enumerate(lines):
    if line.startswith("segment\tE-2\t"):
        lines[i] = line.replace("chr$(66)", "chr$(67)", 1)
        changed = True
        break
assert changed
open(dst, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
if python3 "$REPO/tools/check_m6fd_add1_preregistration.py" --config "$WORK/bad_segment.tsv" \
    >"$WORK/neg2.out" 2>&1; then
  ng "陰性対照(segment改ざん)を検出できなかった"
else
  ok "陰性対照(segment改ざん): rc!=0で検出した"
fi

grep -v '^judgment	m6f_d_add1_incomplete$' "$REPO/tools/m6fd_add1_frozen.tsv" > "$WORK/missing_judgment.tsv"
if python3 "$REPO/tools/check_m6fd_add1_preregistration.py" --config "$WORK/missing_judgment.tsv" \
    >"$WORK/neg3.out" 2>&1; then
  ng "陰性対照(判定名欠落)を検出できなかった"
else
  ok "陰性対照(判定名欠落): rc!=0で検出した"
fi

sed 's/end_plus_used_sectors/xxx/' "$REPO/docs/notes/m6f-d-addendum1-terminal-and-reserve.md" \
  > "$WORK/addendum_missing.md"
if python3 "$REPO/tools/check_m6fd_add1_preregistration.py" --addendum "$WORK/addendum_missing.md" \
    >"$WORK/neg4.out" 2>&1; then
  ng "陰性対照(追補1本文欠落)を検出できなかった"
else
  ok "陰性対照(追補1本文欠落): rc!=0で検出した"
fi

echo
if [ "$rc" -eq 0 ]; then echo "全項目 OK"; else echo "NG あり"; fi
exit "$rc"
