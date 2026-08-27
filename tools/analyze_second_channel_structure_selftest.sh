#!/usr/bin/env bash
# 合成入力だけでm7cy第1段の区間分解・位置検出を検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
overall=0; detected=0; faults=3
ok() { echo "  OK   $1"; }
ng() { echo "  NG   $1"; overall=1; }

python3 - "$WORK" <<'PY'
import pathlib, sys
w = pathlib.Path(sys.argv[1])
def write(name, ports, old=False):
    rows=[]
    for seq, port in enumerate(ports, 1):
        if old:
            rows.append(f"{seq} 0 sub OUT {port} 00 0100")
        else:
            rows.append(f"{seq} {seq*10} 0 sub OUT {port} 00 0100")
    (w/name).write_text("# sub\n# seq clock frame cpu kind port value pc\n"+"\n".join(rows)+"\n")
# 前FD 2件、バルクはFC 4件に対し、slot 1/2へ余分FDを置く。
# 最後のFCより後ろに、対になるFDと追加FDを各1件置く。
write("ok.txt", ["00FD","00FD","00FC","00FD","00FD","00FC","00FD",
                 "00FD","00FC","00FD","00FC","00FD","00FD"])
write("no-boundary.txt", ["00FD","00FD"])
write("no-clock.txt", ["00FC","00FD"], old=True)
PY

out="$(python3 tools/analyze_second_channel_structure.py --label 合成 "$WORK/ok.txt" 2>&1)"
if grep -q 'sub OUT \$FC: バルク前=0 中=4 後=0 合計=4' <<<"$out" \
   && grep -q 'sub OUT \$FD: バルク前=2 中=5 後=2 合計=9' <<<"$out" \
   && grep -q 'バルク中の隣接FC→FD対: 3' <<<"$out" \
   && grep -q '最終FC直後の次チャンネルイベントがFD: はい' <<<"$out" \
   && grep -q '余分FD挿入slot（直前FC件数、0-based）: 1..2（間隔1、2件）' <<<"$out"; then
  ok "3区間分解と既知位置の余分FDを検出した"
else
  ng "正常合成入力の集計が期待と違う"; printf '%s\n' "$out"
fi

for fixture in no-boundary no-clock; do
  if python3 tools/analyze_second_channel_structure.py "$WORK/$fixture.txt" >/dev/null 2>&1; then
    ng "故障 $fixture を受理した"
  else
    detected=$((detected+1)); ok "故障 $fixture を検出した"
  fi
done
# 周期検出器を壊す故障: 余分FDの1件を除去し、件数とslotの双方が変わること。
sed '7d' "$WORK/ok.txt" > "$WORK/period-broken.txt"
broken="$(python3 tools/analyze_second_channel_structure.py "$WORK/period-broken.txt" 2>&1 || true)"
if [ "$broken" != "$out" ] && ! grep -q '余分FD挿入slot（直前FC件数、0-based）: 1..2' <<<"$broken"; then
  detected=$((detected+1)); ok "余分FD周期の故障を検出した"
else
  ng "余分FD周期の故障を検出しなかった"
fi

if [ "$detected" -ne "$faults" ]; then ng "故障注入の空振り $((faults-detected)) 件"; fi
echo "analyze_second_channel_structure_selftest: 検出 ${detected}/${faults}、空振り $((faults-detected))"
exit "$overall"
