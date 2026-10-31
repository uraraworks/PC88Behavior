#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$REPO/tools:$REPO/src" python3 - <<'PY'
from types import SimpleNamespace as E
from judge_b21 import judge
from analyze_b21 import analyze
from build_main_rom import b21_payload, b21_boot
base={(n,r):{'response':'C0' if n==1 else 'none'} for n in range(1,8) for r in (1,2)}
assert judge(base)['controls_passed']
base[2,2]['response']='12'; assert not judge(base)['controls_passed']
base[2,2]['response']='none';base[1,1]['response']='00';base[1,2]['response']='00';assert not judge(base)['controls_passed']
assert analyze(1,1,[E(addr=0xdf53,value=1),E(addr=0xdf58,value=0xc0),E(addr=0xdf59,value=1)],['A 00C1 1 0 1 0 0','W 7800 rom 1'])[2:] == ['C0','0','A 00C1 1 0 1 0 0;W 7800 rom 1']
assert analyze(1,1,[],[])[2:] == ['none','unknown','-']
for n in range(1,8): assert b21_boot(n)
for n in (6,7):
    payload=b21_payload(n); assert payload[-9:]==[0x46,0,0,0,1 if n==6 else 32,1,1 if n==6 else 32,27,255]
print('B21 自己検査 OK')
PY
