#!/usr/bin/env bash
# m7cy第2段の判定器を、合成入力と2種の故障注入で検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$REPO" || exit 1
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
overall=0; detected=0; faults=2
ok() { echo "  OK   $1"; }; ng() { echo "  NG   $1"; overall=1; }
python3 - "$WORK" <<'PY'
import pathlib, sys
w=pathlib.Path(sys.argv[1]); pre=779; bulk=5635; post=9
first=[(i*29+7)&255 for i in range(bulk)]
second=[(i+3)&255 for i in range(bulk)]
def write(path, second_values):
    rows=[]; seq=0; clock=0
    def event(port, value):
        nonlocal seq, clock
        seq+=1; clock+=10
        rows.append(f"{seq} {clock} 0 main IN {port} {value:02X} 0100")
    for i in range(pre): event("00FC", (i*11)&255)
    for value in second_values: event("00FC", value)
    for i in range(post): event("00FC", (i*13)&255)
    for value in first: event("00FD", value)
    path.write_text("# main\n# seq clock frame cpu kind port value pc\n"+"\n".join(rows)+"\n")
write(w/"official.txt", second)
broken=list(second); broken[0]^=1
write(w/"mixed.txt", broken)
PY
out="$(python3 tools/search_second_channel_rules.py "$WORK/official.txt" "$WORK/mixed.txt" 2>&1)"
if grep -q '候補=位置(i+3)&FF.*prefix=6423' <<<"$out" \
   && grep -q '最大prefix: 6423' <<<"$out"; then
  ok "わざと伸びる位置規則を779から6423まで検出した"
else
  ng "合成陽性対照でprefixが伸びなかった"
fi
for fault in --fault-prefix-779 --fault-always-match; do
  if python3 tools/search_second_channel_rules.py "$fault" \
       "$WORK/official.txt" "$WORK/mixed.txt" >/dev/null 2>&1; then
    ng "故障 $fault を受理した"
  else
    detected=$((detected+1)); ok "故障 $fault を検出した"
  fi
done
if [ "$detected" -ne "$faults" ]; then ng "故障注入の空振り $((faults-detected))件"; fi
echo "search_second_channel_rules_selftest: 検出 ${detected}/${faults}、空振り $((faults-detected))"
exit "$overall"
