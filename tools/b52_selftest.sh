#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
PYTHONPATH="$REPO/tools:$REPO/src" python3 - "$work" <<'PY'
import csv, pathlib, sys
from build_main_rom import b52_boot
from judge_b52 import FIELDS,load,judge
from analyze_b52 import analyze,LENGTHS
root=pathlib.Path(sys.argv[1]); paths=[]
# B52測定時点の事前登録対照（自作未実装）の判定器は履歴として維持する。
# 現行の自作ROMの期待は、下の実走で公開済み公式の行と照合する。
for kind in ('official','self'):
 for run in (1,2):
  path=root/f'{kind}-{run}.tsv';paths.append(path)
  with path.open('w') as f:
   w=csv.writer(f,delimiter='\t',lineterminator='\n');w.writerow(FIELDS)
   for row in range(1,9):
    assert b52_boot(row)
    length=LENGTHS[row-1];start=0x20 if row==4 else 0x10
    payload=bytes([0x3e,0x5a,0x32,0x3f,0x78,0xc3,0xc1,0]) if row==7 else bytes(0xa0+i for i in range(length))
    data=bytearray((i*7+13)&255 for i in range(64))
    if kind=='official':
     start += row==8
     data[start:start+length]=payload
     if row==7:data[63]=0x5a
    lines=['1 0 1000 DE04 5A\n','2 0 1000 DE00 00\n','3 0 1000 DE03 A5\n']+[f'{i+4} 0 1000 {0xe000+i:04X} {v:02X}\n' for i,v in enumerate(data)]+['68 0 1000 DE01 01\n','取りこぼし: 0件\n']
    w.writerow(analyze(row,run,lines))
a=load(paths[:2]);b=load(paths[2:]);assert judge(a,b)['controls_passed']
a[1,2]['match']='0';assert not judge(a,b)['controls_passed']
PY
python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" > /dev/null
"$REPO/tools/measure_b52.sh" --work "$work/run" --dry-run-sub-rom "$work/sub/DISK.ROM" --output-dir "$work/results"
python3 - "$work/results" "$REPO/measurements/b52-official-1.tsv" <<'PY'
import csv,pathlib,sys
files=list(pathlib.Path(sys.argv[1]).glob('b52-self-*.tsv'))
assert len(files)==2
for p in files:
 with p.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
 assert len(rows)==8
 # 第231版: 行7は先頭2バイトだけのコードを実行し、読み返しまで戻らない。
 with open(sys.argv[2]) as f: expected=list(csv.DictReader(f,delimiter='\t'))
 assert all(all(r[k]==e[k] for k in r if k!='run') for r,e in zip(rows,expected)),rows
print('B52 自己検査 OK')
PY
