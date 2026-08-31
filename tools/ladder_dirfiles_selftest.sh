#!/usr/bin/env bash
# 合成画面・合成I/Oだけで、到達条件と故障注入の検出力を確認する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="$REPO/tools/ladder_dirfiles.py"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/pc88-ladder-selftest.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

python3 - "$TMP" <<'PY'
from pathlib import Path
import sys

root=Path(sys.argv[1])
program=[
'10 ON ERROR GOTO 100','20 OPEN "QZ9X" FOR INPUT AS #1',
'30 PRINT "D9N":END','100 IF ERL<>20 THEN PRINT "D9N":END',
'110 PRINT "D9E"','120 RESUME 130','130 PRINT "D9C":END','RUN']

def report(name, tail):
    rows=program+tail
    text='[測定終了時のテキスト画面]\n'
    text+='\n'.join(f'  {i:2d}| {row}' for i,row in enumerate(rows))+'\n\n'
    (root/f'{name}.report').write_text(text,encoding='utf-8')

def iolog(name, entry=True, write=False, dropped=0):
    # 公開FDC列: SEEK/SENSE INTERRUPT/SENSE DRIVE/READ。値は合成値だけ。
    main=[]; sub=[]; clock=1
    def ev(dst,cpu,frame,kind,port,value,pc='1111'):
        nonlocal clock
        dst.append(f'{len(dst)+1:6d} {clock:7d} {frame:6d}  {cpu:<4}  {kind:<4}  {port}   {value:02X}   {pc}')
        clock+=1
    frame=700 if entry else 600
    if entry:
        ev(main,'main',700,'IN','00FC',0x55)
    # SEEK 0F + 2 params (no result)
    for v in (0x0F,0,0): ev(sub,'sub',frame,'OUT','00FB',v)
    # SENSE INTERRUPT 08 + 2 result
    ev(sub,'sub',frame,'OUT','00FB',0x08)
    for v in (0,0): ev(sub,'sub',frame,'IN','00FB',v)
    # SENSE DRIVE 04 + param + result
    for v in (0x04,0): ev(sub,'sub',frame,'OUT','00FB',v)
    ev(sub,'sub',frame,'IN','00FB',0)
    # READ 06 + 8 params + synthetic data/result IN
    for v in (0x06,0,0,0,0,0,0,0,0): ev(sub,'sub',frame,'OUT','00FB',v)
    for v in (0,0,0,0,0,0,0): ev(sub,'sub',frame,'IN','00FB',v)
    if write:
        for v in (0x05,0,0,0,0,0,0,0,0): ev(sub,'sub',710,'OUT','00FB',v)
        ev(sub,'sub',710,'OUT','00FB',0x41)
        for v in (0,0,0,0,0,0,0): ev(sub,'sub',710,'IN','00FB',v)
    text='# PC88Behavior 順序付き I/O 記録\n# main\n# seq clock frame cpu kind port value pc\n'
    text+='\n'.join(main)+'\n'
    text+=f'# 取りこぼし: {dropped}件 / 総イベント数: {len(main)}件\n\n'
    text+='# sub\n# seq clock frame cpu kind port value pc\n'+'\n'.join(sub)+'\n'
    text+=f'# 取りこぼし: {dropped}件 / 総イベント数: {len(sub)}件\n'
    (root/f'{name}.io').write_text(text,encoding='utf-8')

report('ok',['D9E','D9C','Ok']); iolog('ok')
report('no_open',['D9E','D9C','Ok'])
p=(root/'no_open.report').read_text(); p=p.replace('20 OPEN "QZ9X" FOR INPUT AS #1\n',''); (root/'no_open.report').write_text(p)
iolog('no_open')
report('d9n',['D9N','Ok']); iolog('d9n')
report('wrong_line',['D9N','Ok']); iolog('wrong_line')
report('no_d9e',['D9C','Ok']); iolog('no_d9e')
report('no_d9c',['D9E','Ok']); iolog('no_d9c')
report('no_ok',['D9E','D9C']); iolog('no_ok')
report('io_zero',['D9E','D9C','Ok']); iolog('io_zero',entry=False)
report('write',['D9E','D9C','Ok']); iolog('write',write=True)
report('dropped',['D9E','D9C','Ok']); iolog('dropped',dropped=1)
PY

typed=(
  --typed '10 ON ERROR GOTO 100'
  --typed '20 OPEN "QZ9X" FOR INPUT AS #1'
  --typed '30 PRINT "D9N":END'
  --typed '100 IF ERL<>20 THEN PRINT "D9N":END'
  --typed '110 PRINT "D9E"'
  --typed '120 RESUME 130'
  --typed '130 PRINT "D9C":END'
  --typed RUN
)

pass=0; fail=0
if python3 "$HELPER" analyze --report "$TMP/ok.report" --iolog "$TMP/ok.io" \
  --kind missing "${typed[@]}" --out "$TMP/ok.json"; then
  printf 'OK: 陽性対照を合格にした\n'; pass=$((pass+1))
else printf 'NG: 陽性対照を不合格にした\n'; fail=$((fail+1)); fi

for case_name in no_open d9n wrong_line no_d9e no_d9c no_ok io_zero write dropped; do
  if python3 "$HELPER" analyze --report "$TMP/$case_name.report" \
    --iolog "$TMP/$case_name.io" --kind missing "${typed[@]}" \
    --out "$TMP/$case_name.json" >/dev/null 2>&1; then
    printf 'NG: 陰性対照 %s を誤って合格にした\n' "$case_name"; fail=$((fail+1))
  else
    printf 'OK: 陰性対照 %s を実際に不合格にした\n' "$case_name"; pass=$((pass+1))
  fi
done

# 同一Nの2runについて、件数・SHA-256・期待値0行の故障も不一致にする。
cp "$TMP/ok.json" "$TMP/ok2.json"
if python3 "$HELPER" pair --a "$TMP/ok.json" --b "$TMP/ok2.json" --out "$TMP/pair.json"; then
  printf 'OK: 同一の2run集計を完全一致にした\n'; pass=$((pass+1))
else printf 'NG: 同一の2run集計を不一致にした\n'; fail=$((fail+1)); fi

for field in entry_main_in_fc entry_main_in_fc_sha256 entry_write_count; do
  python3 - "$TMP/ok.json" "$TMP/broken.json" "$field" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); key=sys.argv[3]
x[key] = (x[key] + 1) if isinstance(x[key],int) else ('0'*64)
json.dump(x,open(sys.argv[2],'w',encoding='utf-8'),ensure_ascii=False)
PY
  if python3 "$HELPER" pair --a "$TMP/ok.json" --b "$TMP/broken.json" \
    --out "$TMP/broken-pair.json" >/dev/null 2>&1; then
    printf 'NG: 故障注入 %s を見逃した\n' "$field"; fail=$((fail+1))
  else
    printf 'OK: 故障注入 %s を不一致にした\n' "$field"; pass=$((pass+1))
  fi
done

printf '自己検査: OK=%d NG=%d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
