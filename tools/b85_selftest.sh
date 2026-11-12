#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
for name in ${!PC88_REF_@}; do unset "$name"; done
work="$(mktemp -d "${TMPDIR:-/tmp}/b85-selftest.XXXXXX")"
trap 'rm -rf "$work"' EXIT
core="$(find_l3_core)"
[[ -f "$core" ]] || { echo 'B85: 自作 ROM 用コアがありません' >&2; exit 1; }
ensure_l3_frontend >"$work/frontend.log" 2>&1
for arm in negative positive fault; do
  case "$arm" in negative) row=1; opts=();; positive) row=9; opts=();; fault) row=9; opts=(--fault);; esac
  TMPDIR="$work" python3 "$REPO/tools/b85_build_rom.py" "$work/$arm" --row "$row" ${opts[@]+"${opts[@]}"} >"$work/$arm.build" 2>&1
  /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$REPO/tools/harness/frontend/q88measure" --core "$core" --rom-dir "$work/$arm" --frames 2010 --io-log "$work/$arm.io" --mem-write-log "$work/$arm.mem" --mem-write-range DF50-DF53 >"$work/$arm.out" 2>"$work/$arm.err"
done
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
from pathlib import Path
import sys
from analyze_main_to_sub import parse_iolog
from analyze_m6ia_main_sub import read_memlog
from analyze_b16 import io_drops
root=Path(sys.argv[1])
for arm,expected in [('negative',[]),('positive',[12,120,0,0,1,85]),('fault',[12,120,0,0,1,85])]:
    path=root/(arm+'.io')
    assert io_drops(path)==0
    events,masked=parse_iolog(path); assert not masked
    sent=[e.value for e in events if e.cpu=='main' and e.kind=='OUT' and e.port=='00FD']
    memory={e.addr:e.value for e in read_memlog(root/(arm+'.mem'))}
    assert memory.get(0xdf53)==1 and memory.get(0xdf52)==0
    n=memory[0xdf50]
    actual=sent[-n:] if n else []
    if arm=='fault': assert actual != expected and n==len(expected)
    else: assert actual==expected and n==len(expected)
print('B85 自作どうし自己検査: 陰性・陽性・故障注入 PASS')
PY
# 実行器の全腕・二走と、公開可能な項目の限定を確認する。
bash "$REPO/tools/b85_run.sh" "$work/run"
PYTHONPATH="$REPO/tools" python3 - "$work/run" <<'PY'
import json, sys
from pathlib import Path
from b85_summarize import validate, summarize
root=Path(sys.argv[1]); path=root/'summary/b85.json'
data=json.loads(path.read_text()); validate(data)
assert data['controls_passed'] and len(data['arms']) == 8
assert all(len(arm['runs']) == 2 and all(run is not None for run in arm['runs']) for arm in data['arms'])
# 値列を表す任意の欄を注入するとホワイトリスト検証が拒否する。
probe=json.loads(path.read_text()); probe['arms'][0]['raw_value']='SECRET_DATA_VALUE'
try: validate(probe)
except AssertionError: pass
else: raise AssertionError('unexpected field accepted')
assert 'SECRET_DATA_VALUE' not in path.read_text()
# 欠落スナップショットは必ず instrument_invalid に倒す。
snap=root/'raw/2-1.snap'; saved=snap.read_bytes(); snap.unlink()
summarize(root)
assert all(a['judgment']=='instrument_invalid' for a in json.loads(path.read_text())['arms'])
snap.write_bytes(saved)
summarize(root)
print('B85 全腕・値なし集計・欠落検出: PASS')
PY
