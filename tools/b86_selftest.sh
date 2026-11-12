#!/usr/bin/env bash
set -euo pipefail
unset PC88_REF_ROM_DIR PC88_REF_DISK_DIR PC88_REF_DISKB PC88_GAME_DIR B86_FRAMES B86_TIMEOUT PC88_CORE PC88_FRONTEND
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/b86.XXXXXX")"
trap 'rm -rf "$work"' EXIT
bash "$repo/tools/b86_run.sh" "$work/run"
python3 - "$work/run" "$repo/tools" <<'PY'
import importlib.util, json, pathlib, re, shutil, sys
p=pathlib.Path(sys.argv[1]); tools=pathlib.Path(sys.argv[2]); summaries=p/'summary'
assert len(list(summaries.glob('*.json')))==60
for f in summaries.glob('*.json'):
    s=json.loads(f.read_text())
    assert s['J_start']=='確認' and s['J_return']=='確認' and s['J_regs']=='取得' and s['J_ram']['判定']=='取得' and s['J_io']['判定']=='取得'
neg=json.loads((summaries/'negative-zero.json').read_text()); pos=json.loads((summaries/'positive-zero.json').read_text())
nraw=json.loads((p/'raw/negative-zero/result.json').read_text()); raw=json.loads((p/'raw/positive-zero/result.json').read_text())
assert not neg['J_io']['ポート別回数']
assert pos['J_io']['ポート別回数']==[{'方向':'OUT','ポート':'7E','回数':1}]
assert not any(x[0]=='D000' for x in nraw['ram_changes'])
assert any(x==['D000',0,90] for x in raw['ram_changes'])
assert raw['register_bytes']['C0C0'] & 1
assert raw['register_bytes']['C0C8']==0 and raw['register_bytes']['C0C9']==0xf0
# 集計器に未知の値を注入し、値だけを変えても集計が変化しないことを確認。
spec=importlib.util.spec_from_file_location('summarizer',tools/'b86_summarize.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
d=p/'mutation'; shutil.copytree(p/'raw/positive-zero',d)
io=(d/'io').read_text(); lines=io.splitlines()
indices=[i for i,line in enumerate(lines) if re.match(r'^\s*\d+\s+\d+\s+\d+\s+main\s+OUT\s+007D\s+[0-9A-F]{2}\s+C081$',line)]
assert len(indices)==2*0x2f00
for i in (indices[17],indices[17+0x2f00]):
    lines[i]=re.sub(r'(\s007D\s+)[0-9A-F]{2}(\s+C081)$',r'\g<1>AB\2',lines[i])
# 対照の区間内 I/O 値も別の値へ変更する。
for i, line in enumerate(lines):
    if re.match(r'^\s*\d+\s+\d+\s+\d+\s+main\s+OUT\s+007E\s+', line):
        lines[i]=re.sub(r'(\s007E\s+)[0-9A-F]{2}',r'\g<1>AB',line)
(d/'io').write_text('\n'.join(lines)+'\n')
mem=(d/'mem').read_text(); mem=re.sub(r'(\sC0C1\s+)[0-9A-F]{2}$',r'\g<1>AB',mem,flags=re.M); (d/'mem').write_text(mem)
assert mod.summarize(d)==pos
assert json.loads((d/'result.json').read_text())['register_bytes']['C0C1']==0xab
# 写しに一方だけ差を入れると変化番地として検出する。
lines[indices[17]]=re.sub(r'(\s007D\s+)[0-9A-F]{2}(\s+C081)$',r'\g<1>AC\2',lines[indices[17]])
(d/'io').write_text('\n'.join(lines)+'\n'); fault=mod.summarize(d)
assert fault['J_ram']['変化番地数']==pos['J_ram']['変化番地数']+1
# 取りこぼしは欠測にする。
(d/'io').write_text((d/'io').read_text().replace('取りこぼし: 0件','取りこぼし: 1件',1))
assert mod.summarize(d)['J_start']=='欠測'
print('PASS: 全60腕、対照、故障注入、値の非混入、取りこぼし')
PY
