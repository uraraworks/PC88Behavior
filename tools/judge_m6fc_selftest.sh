#!/usr/bin/env bash
# tools/judge_m6fc.py の自己検査。合成JSONのみで完結する。
#
# 検査項目:
#   1. C0/C1/C2から再計算したoverallがstampされたoverallと一致すればrc=0。
#   2. 4通りの総合判定(m6f_c_boot_blocked等)がそれぞれ正しく出る。
#   3. 陰性対照: stampされたoverallをわざと食い違わせるとgate_failedになる。
#   4. 形式不正(derivationsが無い等)はrc=2でgate_failed。
#
# 使い方: tools/judge_m6fc_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JUDGE="$REPO/tools/judge_m6fc.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

write() { printf '%s' "$2" > "$WORK/$1"; }

d() { python3 - "$@" <<'PY'
import json,sys
c0,c1,c2,overall=sys.argv[1:5]
doc={"schema":1,"derivations":{
  "C0":{"status":c0}, "C1":{"status":c1},
  "C2":{"status":c2}}, "overall":overall}
for i in range(3,12):
    doc["derivations"][f"C{i}"]={"status":"not_found","candidate_count":0}
print(json.dumps(doc))
PY
}

d not_found derived accepted m6f_c_boot_blocked > "$WORK/blocked.json"
d derived not_found accepted m6f_c_no_free_mark > "$WORK/nofree.json"
d derived derived accepted m6f_c_blank_disk_accepted > "$WORK/accepted.json"
d derived derived not_accepted m6f_c_blank_disk_not_accepted > "$WORK/notaccepted.json"
d derived derived accepted m6f_c_blank_disk_not_accepted > "$WORK/mismatch.json"

for case in blocked nofree accepted notaccepted; do
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

echo '{"schema":1}' > "$WORK/malformed.json"
python3 "$JUDGE" --derived "$WORK/malformed.json" >/dev/null 2>&1
rc_malformed=$?
if [ "$rc_malformed" -eq 2 ]; then
  ok "形式不正(derivations無し)はrc=2"
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
