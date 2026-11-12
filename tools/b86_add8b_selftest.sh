#!/usr/bin/env bash
set -euo pipefail
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
unset B86_ADD8B_IRQ_CONTROL PC88_CORE PC88_FRONTEND B86_FRAMES B86_TIMEOUT B86_ADD8B_OWN_ROM_DIR B86_ADD8B_FILTER
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add8b.XXXXXX")"; trap 'rm -rf "$work"' EXIT
B86_ADD8B_FILTER='^none-c800-(none|r00b0)$' bash "$repo/tools/b86_add8b_run.sh" "$work/run"
B86_ADD8B_IRQ_CONTROL=1 B86_ADD8B_FILTER='^none-c800-none$' bash "$repo/tools/b86_add8b_run.sh" "$work/irq"
PYTHONDONTWRITEBYTECODE=1 python3 - "$repo/tools" "$work/run" "$work/irq" <<'PY'
import json,pathlib,sys,tempfile
sys.path.insert(0,sys.argv[1]); import b86_add8b as m
arms=dict(m.arms()); assert len(arms)==70
for a in arms.values():
 data,marks=m.generate(a); assert len(data)==256 and len(marks)==len(set(marks.values()))
r=json.loads((pathlib.Path(sys.argv[2])/'summary.json').read_text()); a=r['腕']['none-c800-none']; b=r['腕']['none-c800-r00b0']
assert a['戻り']=='確認' and b['戻り']=='確認', (a,b)
assert all(a['入力との一致'].values()) and not a['EI状態'],a
assert any(x['番地']=='D000' and x['件数']==1 for x in a['RAM書込']),a
assert r['キー対応']['none-c800-r00b0']['変化番地']==['D000'],r['キー対応']['none-c800-r00b0']
assert not list((pathlib.Path(sys.argv[2])/'raw').rglob('mem'))
irq=json.loads((pathlib.Path(sys.argv[3])/'summary.json').read_text())['腕']['none-c800-none']
assert irq['戻り']=='確認' and irq['割り込み受け口']['回数']>=1 and '戻り印前' in irq['割り込み受け口']['位置'],irq
assert all(0xcf80 <= int(x['番地'],16) <= 0xcfff for x in a['スタック付近書込'])
assert not (0xcf80 <= 0xd000 <= 0xcfff) and not any(0xcf80 <= x <= 0xcfff for x in (0xefff,0xeff9,0xf001,0xe6c3,*range(0xe6d0,0xe6e8)))
with tempfile.TemporaryDirectory() as t:
 p=pathlib.Path(t); marks=m.generate(arms['none-c800-none'])[1]
 def row(i,pc,addr,value): return f'{i} 0 {pc:04X} {addr:04X} {value:02X}\n'
 data=row(0,marks['startmem'],0xcff0,0xaa)+row(1,0x1234,0xd000,0x5a)+row(2,marks['bootmem'],0xcff2,0xbb)+row(3,0x2345,0xd001,0x7b)
 (p/'mem').write_text(data+'# 取りこぼし: 0件 / 総イベント数: 4件\n')
 assert [x[1] for x in m.parsemem(p/'mem',marks)]==[0xd000]
 (p/'mem').write_text(data+'# 取りこぼし: 1件 / 総イベント数: 4件\n'); assert m.parsemem(p/'mem',marks) is None
print('PASS: 70腕・自作ROM・打鍵差分・戻り・区間・取りこぼし・値なし')
PY
