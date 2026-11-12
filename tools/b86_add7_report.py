#!/usr/bin/env python3
"""対照の成立と各腕の値なし集計をまとめる。"""
import json
import pathlib
import sys
p=pathlib.Path(sys.argv[1])
rows={f.stem:json.loads(f.read_text()) for f in sorted(p.glob('*.json'))}
controls={}
for mode in ('di','ei','irq'):
    c=rows.get(f'control-{mode}-0',{})
    q=rows.get(f'positive-{mode}-6',{})
    controls[mode]={'対照': c.get('戻り')=='確認', '陽性対照':q.get('戻り')=='確認',
                    '受け口': (q.get('受け口回数',0)>0 if mode!='di' else '対象外')}
    controls[mode]['成立']=controls[mode]['対照'] and controls[mode]['陽性対照'] and (mode=='di' or controls[mode]['受け口'])
for name,row in rows.items():
    parts=name.split('-')
    if parts[0] in ('3080','39ce','3ded','11df'):
        row['対照成立']=controls[parts[1]]['成立']
pathlib.Path(sys.argv[2]).write_text(json.dumps({'対照':controls,'腕':rows},ensure_ascii=False,indent=2)+'\n')
