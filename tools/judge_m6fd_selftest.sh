#!/usr/bin/env bash
# tools/judge_m6fd.py の自己検査。合成JSONのみで完結する。
#
# 検査項目:
#   1. D1〜D6から再計算したoverallがstampされたoverallと一致すればrc=0。
#   2. m6f_d_rules_confirmed / m6f_d_incomplete のそれぞれが正しく出る。
#   3. 陰性対照: stampされたoverallをわざと食い違わせるとgate_failed(rc=2)。
#   4. 形式不正(derivationsが無い・D1〜D6のいずれかが無い)はrc=2でgate_failed。
#
# 使い方: tools/judge_m6fd_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JUDGE="$REPO/tools/judge_m6fd.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

d() {
  python3 - "$@" <<'PY'
import json, sys
d1, d2, d3, d4, d5, d6, overall = sys.argv[1:8]
doc = {"schema": 1, "derivations": {
    "D1": {"status": d1}, "D2": {"status": d2}, "D3": {"status": d3}, "D4": {"status": d4},
    "D5": {"status": d5}, "D6": {"status": d6, "directory_sectors": [7] if d6 != "control_failed" else []},
    "D7": {"status": "n/a"}, "D8": {"status": "reserve_other"}, "D9": {"classes": {}},
}, "overall": overall}
print(json.dumps(doc))
PY
}

d derived link_is_next_index end_constant derived relocated_readable stops_at_unused m6f_d_rules_confirmed \
  > "$WORK/confirmed.json"
d derived link_other end_constant derived relocated_readable stops_at_unused m6f_d_incomplete \
  > "$WORK/incomplete_chain.json"
d not_found link_is_next_index end_constant derived relocated_readable stops_at_unused m6f_d_incomplete \
  > "$WORK/incomplete_d1.json"
d derived link_is_next_index end_constant derived not_readable stops_at_unused m6f_d_incomplete \
  > "$WORK/incomplete_d5.json"
d derived link_is_next_index end_constant derived relocated_readable control_failed m6f_d_incomplete \
  > "$WORK/incomplete_d6.json"
d derived link_is_next_index end_constant derived relocated_readable stops_at_unused m6f_d_rules_confirmed \
  > "$WORK/mismatch.json"
python3 -c "
import json
doc = json.load(open('$WORK/mismatch.json'))
doc['overall'] = 'm6f_d_incomplete'
json.dump(doc, open('$WORK/mismatch.json', 'w'))
"

for case in confirmed incomplete_chain incomplete_d1 incomplete_d5 incomplete_d6; do
  out="$(python3 "$JUDGE" --derived "$WORK/$case.json")"
  rcx=$?
  expect=$(python3 -c "import json;print(json.load(open('$WORK/$case.json'))['overall'])")
  got="$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['overall'])" "$out")"
  if [ "$rcx" -eq 0 ] && [ "$got" = "$expect" ]; then
    ok "$case: overall=$expect でrc=0"
  else
    ng "$case: 期待($expect)と不一致または rc!=0 (rc=$rcx got=$got)"
  fi
done

python3 "$JUDGE" --derived "$WORK/mismatch.json" >"$WORK/mismatch.out" 2>/dev/null
rc_mismatch=$?
got_j="$(python3 -c "import json;print(json.load(open('$WORK/mismatch.out'))['overall'])" 2>/dev/null || echo none)"
if [ "$rc_mismatch" -eq 2 ] && [ "$got_j" = "None" ]; then
  ok "陰性対照: stampされたoverallを食い違わせるとgate_failed(rc=2)になる"
else
  ng "陰性対照: overall食い違いが検出されない(rc=$rc_mismatch got=$got_j)"
fi

echo '{"schema":1,"derivations":{"D1":{"status":"derived"}}}' > "$WORK/malformed.json"
python3 "$JUDGE" --derived "$WORK/malformed.json" >/dev/null 2>&1
rc_malformed=$?
if [ "$rc_malformed" -eq 2 ]; then
  ok "形式不正(D2〜D6無し)はrc=2"
else
  ng "形式不正の拒否がrc=2でない(rc=$rc_malformed)"
fi

python3 "$JUDGE" --derived "$WORK/nonexistent.json" >/dev/null 2>&1
rc_missing=$?
if [ "$rc_missing" -eq 2 ]; then
  ok "存在しない入力はrc=2"
else
  ng "存在しない入力の拒否がrc=2でない(rc=$rc_missing)"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"
