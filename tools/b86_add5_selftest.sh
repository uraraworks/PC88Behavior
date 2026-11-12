#!/usr/bin/env bash
set -euo pipefail
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
unset PC88_GAME_DIR B86_FRAMES B86_TIMEOUT PC88_CORE PC88_FRONTEND B86_ADD5_OWN_ROM_DIR
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add5.XXXXXX")"
trap 'rm -rf "$work"' EXIT
bash "$repo/tools/b86_add5_run.sh" "$work/run"
python3 - "$work/run" "$repo/tools" <<'PY'
import gzip,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); sys.path.insert(0,sys.argv[2]); import b86_add5 as m
for arm in m.arms():
 s=json.loads((p/'summary'/f'{arm[0]}.json').read_text())
 assert s['判定']=='取得',arm[0]
 assert len(s['区間'])==len(m.plan(arm)),(arm[0],len(s['区間']))
 assert all(x['戻り']=='確認' for x in s['区間']),arm[0]
 assert all(x['送信件数']==(1 if arm[1]=='positive' else 0) for x in s['区間']),arm[0]
 assert '5A' not in json.dumps(s,ensure_ascii=False)
a=next(m.arms()); d=p/'raw'/a[0]; _,marks=m.generate(a)
io=d/'io'; original=gzip.decompress((d/'io.gz').read_bytes()).decode(); io.write_text(original.replace('取りこぼし: 0件','取りこぼし: 1件',1))
assert m.summarize(d,a,marks)['判定'].startswith('欠測')
old=m.old.events
try:
 start=('OUT',0x7e,0,0xc015); req=('OUT',0x7f,0,marks['request_start'])
 m.old.events=lambda _: [start,req,start,req]
 s=m.summarize(d,a,marks); assert s['再起動'] and s['区間'][0]['戻り']=='戻らない（再起動）' and len(s['区間'])==1
 m.old.events=lambda _: [start,('OUT',0x7f,0,marks['request_end'])]
 assert '順序異常' in m.summarize(d,a,marks)['判定']
 seq=[start]
 for typ in m.plan(a):
  seq.extend([('OUT',0x7f,0,marks[typ+'_start']),('OUT',0x7f,m.PATTERN[0] if typ=='receive' else 0,marks[typ+'_end'])])
 m.old.events=lambda _: seq
 assert m.summarize(d,a,marks)['区間'][-1]['模様と一致'] is True
 seq[-1]=('OUT',0x7f,m.PATTERN[0]^1,marks['receive_end'])
 assert m.summarize(d,a,marks)['区間'][-1]['模様と一致'] is False
finally: m.old.events=old
print('PASS: 16腕、対照、再起動、欠測、値なし集計')
PY

# 配布用自作 ROM でも独立起動する。入口や 09 の未実装は結果の記録のみ。
python3 "$repo/src/build_main_rom.py" "$work/own-rom" > "$work/build.log"
B86_ADD5_OWN_ROM_DIR="$work/own-rom" bash "$repo/tools/b86_add5_run.sh" "$work/own-run"
python3 - "$work/own-run" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1])/'summary'
assert len(list(p.glob('*.json')))==16
assert all('判定' in json.loads(x.read_text()) for x in p.glob('*.json'))
print('PASS: 自作 main・sub の16腕を記録（未実装は判定対象外）')
PY
