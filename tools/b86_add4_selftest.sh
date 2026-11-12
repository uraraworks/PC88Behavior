#!/usr/bin/env bash
set -euo pipefail
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
unset PC88_GAME_DIR B86_FRAMES B86_TIMEOUT PC88_CORE PC88_FRONTEND
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86add4.XXXXXX")"
trap 'rm -rf "$work"' EXIT
bash "$repo/tools/b86_add4_run.sh" "$work/run"
python3 - "$work/run" "$repo/tools" <<'PY'
import gzip,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); sys.path.insert(0,sys.argv[2]); import b86_add4 as m
for arm in m.arms():
 s=json.loads((p/'summary'/f'{arm[0]}.json').read_text())
 assert s['判定']=='取得' and s['前置き完了']=='確認',arm[0]
 assert len(s['区間'])==arm[2] and all(x['戻り']=='確認' for x in s['区間']),arm[0]
 assert all(x['送信件数']==(1 if arm[4]=='positive' else 0) for x in s['区間']),arm[0]
 assert '5A' not in json.dumps(s,ensure_ascii=False)
arm=next(m.arms()); d=p/'raw'/arm[0]; _,pcs=m.generate(arm)
io=d/'io'; original=gzip.decompress((d/'io.gz').read_bytes()).decode(); io.write_text(original.replace('取りこぼし: 0件','取りこぼし: 1件',1))
assert m.summarize(d,arm,pcs)['判定'].startswith('欠測')
io.write_text(original)
# 先頭印だけ、順序異常、および受信済み自作セクタとの照合。
original_events=m.old.events
try:
 data=(d/'probe.bin').read_bytes(); value=data[0]
 m.old.events=lambda _: [('OUT',0x7f,0,pcs[0])]
 assert m.summarize(d,arm,pcs)['区間'][0]['開始']=='欠測'
 m.old.events=lambda _: [('OUT',0x7f,0,pcs[1])]
 assert '順序異常' in m.summarize(d,arm,pcs)['判定']
 m.old.events=lambda _: ([('OUT',0x7f,0,pcs[x]) for x in (0,1,2,3,4)] +
                          [('IN',0xfc,b,0) for b in data] + [('OUT',0x7f,value,pcs[5])])
 row=m.summarize(d,arm,pcs)['区間'][0]
 assert row['受信件数']==256 and any(x['座標']==[0,0,1] and 0 in x['位置'] for x in row['戻りAと一致する受信済み自作媒体の位置'])
finally: m.old.events=original_events
print('PASS: 66腕、対照、反復、欠測、値なし集計')
PY
