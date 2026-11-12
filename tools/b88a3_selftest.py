#!/usr/bin/env python3
"""全腕実走と、既知の対照・破損・欠測・値漏れ・再集計を検査する。"""
import copy
import json
import os
from pathlib import Path
import re
import sys
from b88a3_arms import arms, inputs, REQUESTS
from b88a3_boot import assemble, generate_boot
from b88a3_fixture import build, SOURCE
from b88a3_run import run_one, clean_run
from b88a3_summarize import summarize_run, report, candidate_values, result_relations, COMMAND_LENGTH
from b88_selftest import value_free as base_value_free


def boolean(v):
    assert type(v) is bool


def natural(v, maximum=100000000):
    assert type(v) is int and 0 <= v <= maximum


def bools(v, keys):
    assert isinstance(v, dict) and set(v) == set(keys)
    for b in v.values(): boolean(b)


def value_free(row):
    r=copy.deepcopy(row)
    if set(r)=={'判定','戻り','理由'}:
        base_value_free(r); return
    p,irq,comm,fdc,result,seek=[r.pop(k) for k in ('準備','割り込み','通信','FDC取引','結果相','シーク')]
    if r['理由'] in ('媒体条件不成立','先行処理未帰還','入口未到達','読出し準備未完了','追跡容量超過','結果相未確認'):
        assert r['判定']==r['戻り']=='欠測'
        if len(r)==3: r['理由']='入口未到達'
        else: r.update(戻り='戻らない',理由='時間上限')
    base_value_free(r)
    assert set(p)=={'媒体交換確認','前処理開始','前処理完了','入口到達','読出し要求の準備完了','段階'}
    for k in set(p)-{'段階','読出し要求の準備完了'}: boolean(p[k])
    if p['読出し要求の準備完了'] is not None: boolean(p['読出し要求の準備完了'])
    assert len(p['段階']) in (0,9)
    for v in p['段階']:
        assert set(v)=={'開始','完了'}
        for n in v.values(): natural(n)
    assert set(irq)=={'呼出し直前','入口','戻り直後','EI遅延確認回数','受理回数','入口から戻りの変化'}
    for k in ('呼出し直前','入口','戻り直後'):
        if irq[k] is not None:
            assert set(irq[k])=={'IFF1','IFF2','IM'}
            for key,n in irq[k].items(): natural(n,2 if key=='IM' else 1)
    if irq['入口から戻りの変化'] is not None: bools(irq['入口から戻りの変化'],('IFF1','IFF2','IM'))
    natural(irq['EI遅延確認回数']); assert len(irq['受理回数'])==3
    for n in irq['受理回数']: natural(n)
    assert set(comm)=={'main送信完了数','サブ受信数','受信順に入力と一致','main応答受信数','応答ハンドシェイク完了数',
                       '引数と応答の通信完了','応答長の仕様と一致','自作移動先到達回数'}
    for k in ('受信順に入力と一致','引数と応答の通信完了'): boolean(comm[k])
    if comm['応答長の仕様と一致'] is not None: boolean(comm['応答長の仕様と一致'])
    for k in set(comm)-{'受信順に入力と一致','引数と応答の通信完了','応答長の仕様と一致'}: natural(comm[k])
    for t in fdc:
        assert set(t)=={'区間','種類','コマンドと引数','引数完了','結果','データ受信数','データ送信数'}
        assert t['区間'] in ('入口から戻り','前処理')
        from b88_summarize import FDC
        assert t['種類'] in set(FDC.values()) | {'INVALID'}
        assert 1<=len(t['コマンドと引数'])<=9 and len(t['結果'])<=7
        for n in t['コマンドと引数']+t['結果']: natural(n,255)
        boolean(t['引数完了']);natural(t['データ受信数']);natural(t['データ送信数'])
        assert p['媒体交換確認']
    assert set(result)=={'前処理末尾で確認','入口で確認','READ入力と一致','データ受信数','結果7バイト',
                         '7F0Dから7F13との位置別一致','戻りとの関係'}
    for k in ('前処理末尾で確認','入口で確認','READ入力と一致'):
        if result[k] is not None: boolean(result[k])
    natural(result['データ受信数'])
    if result['結果7バイト'] is not None:
        assert len(result['結果7バイト'])==7 and result['READ入力と一致']
        for n in result['結果7バイト']: natural(n,255)
    if result['7F0Dから7F13との位置別一致'] is not None:
        assert len(result['7F0Dから7F13との位置別一致'])==7
        for b in result['7F0Dから7F13との位置別一致']: boolean(b)
    rr=result['戻りとの関係']
    if rr is not None:
        assert set(rr)=={'A','F各ビット','FはAND(ST0,C0)と一致','BC','DE','HL'}
        keys={'ST0','ST1','ST2','ST0&C0','ST0&3F','ST0|ST1|ST2','定数0','定数1'}
        for k in ('A','BC','DE','HL'): bools(rr[k],keys)
        boolean(rr['FはAND(ST0,C0)と一致'])
        assert set(rr['F各ビット'])=={'C','N','PV','X','H','Y','Z','S'}
        for v in rr['F各ビット'].values(): bools(v,{'0','1','ST0の同位bit','ST1の同位bit','ST2の同位bit','AND(ST0,C0)の同位bit'})
    assert set(seek)=={'OUT F8','入力との関係'}
    for n in seek['OUT F8']: natural(n,255)
    for t in seek['入力との関係']:
        assert set(t)=={'対象','候補の真偽'}
        assert t['対象'] in ('SEEK装置','SEEKシリンダ','SENSE DRIVE STATUS装置','RECALIBRATE装置','OUT F8')
        bools(t['候補の真偽'],candidate_values(inputs({'kind':'negative'})))


def machine(code, origin=0x1800):
    return assemble(f' ORG {origin}\n'+code)[0]


def main(root):
    assert not any(k.startswith('PC88_REF_') for k in os.environ)
    catalog=list(arms());assert len(catalog)==len({a['name'] for a in catalog})==138
    summary=json.loads((root/'summary.json').read_text())
    assert summary['腕数']==138 and summary['走数']==276
    for a in catalog:
        data,disk,labels=generate_boot(a)
        assert len(data)==2304 and labels['sub']['invoke']==labels['sub']['start']+4
        record=summary['腕'][a['name']]
        for r in record['走']:
            value_free(r)
            assert r['準備']['媒体交換確認']
            if a.get('case')=='no-media':
                # このコアは空ドライブのREADを結果相へ進めない。呼出し前欠測。
                assert r['判定']==r['戻り']=='欠測' and not r['準備']['入口到達']
                assert r['結果相']['戻りとの関係'] is None
                continue
            assert r['判定']=='取得' and r['戻り']=='確認', (a['name'],r['理由'])
            assert r['結果搬送一致'] and record['2走一致']
            assert r['割り込み']['呼出し直前']['IFF1']==int(a['iff']=='ei')
            if a['kind']=='request':
                c=r['通信']; assert c['引数と応答の通信完了']
                assert c['main送信完了数']==c['サブ受信数']==len(a['sent'])
                assert c['応答長の仕様と一致']==(True if a['expected'] is not None else None)
                assert c['自作移動先到達回数']==int(a['request']==13)
                if a['request']==18: assert r['準備']['読出し要求の準備完了']
                if a['request'] in (1,2,14):
                    assert any(t['種類']==('WRITE DATA' if a['request']==1 else 'READ DATA') for t in r['FDC取引'])
            elif a['kind']=='result':
                q=r['結果相']; assert q['前処理末尾で確認'] and q['入口で確認'] and q['READ入力と一致']
                assert q['データ受信数']==(256 if a['case']=='normal' else 0)
                assert (q['結果7バイト'][0]&0xc0)==(0 if a['case']=='normal' else 0x40)
                assert q['7F0Dから7F13との位置別一致']==[True]*7
                assert q['戻りとの関係']['A']['ST0&C0'] and q['戻りとの関係']['FはAND(ST0,C0)と一致']
                assert all(r['入力との一致'][k] for k in ('BC','DE','HL'))
            elif a['kind']=='seek':
                ts=r['FDC取引']; assert [t['種類'] for t in ts]==['SEEK','SENSE INTERRUPT STATUS','SENSE DRIVE STATUS']
                assert ts[0]['コマンドと引数']==[15,inputs(a)['A']&1,inputs(a)['DE']>>9]
                assert len(ts[1]['結果'])==2 and len(ts[2]['結果'])==1
                assert r['シーク']['OUT F8']==[7]
    assert summary['シーク規則']['SEEKシリンダ']['成立候補']==['D>>1']
    assert summary['シーク規則']['SEEK装置']['成立候補']==['A&01']
    assert report(root)==summary
    print('B88追補3: 全138腕×2走・3入口・通信長・FDC相・シーク規則・再集計 PASS',flush=True)

    core=next(root.glob('quasi88_libretro.*'));front=root/'b88_frontend';sub,labels=build()
    sequence=0
    negative=next(a for a in catalog if a['name']=='negative')
    def run(arm=None,check=None,**kwargs):
        nonlocal sequence
        sequence+=1;p=root/'controls'/str(sequence);a=arm or negative
        options=dict(frames=120,timeout=120);options.update(kwargs)
        try:
            run_one(p,a,core,front,sub,**options)
            assert (p/'rom'/'DISK.ROM').is_file() and not (p/'rom').is_symlink()
            r,v=summarize_run(p,a);value_free(r)
            if check: check(p,a,r,v)
            return r,v
        finally: clean_run(p)
    # 00ED: 引数ゼロ消費・途中帰還・順序破壊・応答不足/過剰・未帰還。
    a=next(a for a in catalog if a['name']=='00ed-0c-di')
    for count in (0,1,4,20):
        code=''.join(f' CALL {labels["RECV"]}\n' for _ in range(count))+' RET\n'
        r,v=run(a,fixture={0xed:b'\xc3\x00\x18',0x1800:machine(code)})
        assert r['戻り']=='確認' and r['通信']['サブ受信数']==count
        assert r['通信']['引数と応答の通信完了']==(count==20)
    r,_=run(a,fixture={0xed:b'\x18\xfe'})
    assert r['戻り']=='戻らない' and r['通信']['応答長の仕様と一致'] is None
    a=next(a for a in catalog if a['name']=='00ed-06-di')
    for count in (0,2):
        code=''.join(f' LD A,53\n CALL {labels["SEND"]}\n' for _ in range(count))+' RET\n'
        r,_=run(a,fixture={0xed:b'\xc3\x00\x18',0x1800:machine(code)})
        assert r['通信']['main応答受信数']==count and r['通信']['応答長の仕様と一致'] is False
    # 通信の順序が壊れた記録は完了判定に流用しない。
    def broken_stream(p,a,r,v):
        q=p/'extra';x=json.loads(q.read_text());x['stream_ok']=0;q.write_text(json.dumps(x))
        bad,_=summarize_run(p,a);assert not bad['通信']['引数と応答の通信完了']
    run(a,check=broken_stream)
    print('B88追補3: 00EDの途中帰還・未帰還・応答不足/過剰・通信不一致 PASS',flush=True)

    a=next(a for a in catalog if a['name']=='0263-normal-di')
    # 結果の配置・保存レジスタ・A/F規則をそれぞれ壊す。
    for tweak in ('placement','register','flags','short'):
        if tweak=='short': code=' LD B,6\nLOOP:\n CALL %d\n DJNZ LOOP\n RET\n'%labels['FDC_IN']
        else:
            code=f' CALL {labels["RESULT"]}\n'+{
                'placement':' LD HL,07F0Dh\n INC (HL)\n',
                'register':' INC BC\n', 'flags':' SCF\n'}[tweak]+' RET\n'
        r,_=run(a,fixture={0x263:b'\xc3\x00\x18',0x1800:machine(code)})
        assert r['戻り']=='確認'
        if tweak=='placement': assert r['結果相']['7F0Dから7F13との位置別一致'][0] is False
        if tweak=='register': assert r['入力との一致']['BC'] is False
        if tweak=='flags': assert r['結果相']['戻りとの関係']['FはAND(ST0,C0)と一致'] is False
        if tweak=='short': assert r['結果相']['結果7バイト'] is None and r['結果相']['戻りとの関係'] is None
    for bit,name in enumerate(('C','N','PV','X','H','Y','Z','S')):
        code=f' PUSH HL\n CALL {labels["RESULT"]}\n PUSH AF\n POP HL\n LD A,L\n XOR {1<<bit}\n LD L,A\n PUSH HL\n POP AF\n POP HL\n RET\n'
        r,_=run(a,fixture={0x263:b'\xc3\x00\x18',0x1800:machine(code)})
        flags=r['結果相']['戻りとの関係']['F各ビット']
        assert {k:v['AND(ST0,C0)の同位bit'] for k,v in flags.items()}=={k:k!=name for k in flags}
    # 入口で結果相を偽装した記録・READ引数取り違えは規則を出さない。
    def phase_break(p,a,r,v):
        q=p/'extra';original=q.read_text()
        for key,val in (('ready_msr',0xf0),('entry_msr',0xf0)):
            x=json.loads(original);x[key]=val;q.write_text(json.dumps(x))
            bad,v=summarize_run(p,a);assert bad['判定']=='欠測' and v is None
            assert bad['結果相']['戻りとの関係'] is None
        x=json.loads(original);x['commands'][0]['bytes'][4]^=1;q.write_text(json.dumps(x))
        bad,_=summarize_run(p,a);assert not bad['結果相']['READ入力と一致'] and bad['結果相']['戻りとの関係'] is None
    run(a,check=phase_break)
    r,_=run(a,fault='phase-bypass')
    assert r['判定']=='欠測' and r['理由']=='結果相未確認'
    assert r['結果相']['戻りとの関係'] is None
    r,_=run(a,fixture={0x2a7:b'\xc9'})
    assert r['判定']=='欠測' and not r['準備']['入口到達']
    for step in range(9):
        r,_=run(a,fault=f'prehang-{step}')
        assert r['判定']=='欠測' and r['理由']=='先行処理未帰還'
        assert r['準備']['段階'][step]['開始']>=1 and r['準備']['段階'][step]['完了']==0
    print('B88追補3: 結果相・異常結果・7位置の配置・A/F/保存レジスタ・9段階欠測 PASS',flush=True)

    # シーク候補の取り違えを、各レジスタを独立に出力する自作FDC腕で検出。
    a=next(a for a in catalog if a['name']=='07d6-mixed-1-di')
    for reg in ('A','B','C','D','E'):
        code=f''' PUSH AF
 PUSH BC
 PUSH DE
 PUSH HL
 LD L,{reg}
 LD A,15
 CALL {labels['FDC_OUT']}
 LD A,0
 CALL {labels['FDC_OUT']}
 LD A,L
 CALL {labels['FDC_OUT']}
 POP HL
 POP DE
 POP BC
 POP AF
 RET
'''
        r,_=run(a,fixture={0x7d6:b'\xc3\x00\x18',0x1800:machine(code)})
        rel=next(v['候補の真偽'] for v in r['シーク']['入力との関係'] if v['対象']=='SEEKシリンダ')
        assert rel[reg] and not rel['D>>1'] if reg!='B' else rel[reg]
    for iff in ('di','ei'):
        for im in (0,1,2):
            for iff2 in (0,1):
                a=dict(negative,iff=iff,im=im)
                r,_=run(a,fault=machine(' DI\n IM 2\n RET\n'),test_iff2=iff2)
                assert r['割り込み']['入口']==dict(IFF1=int(iff=='ei'),IFF2=iff2,IM=im)
                assert r['割り込み']['戻り直後']==dict(IFF1=0,IFF2=iff2,IM=2)
    print('B88追補3: A/B/C/D/E独立依存・候補取り違え・IFF1/IFF2/IM PASS',flush=True)

    for fault in ('result','restart','hang','prehang'):
        r,v=run(fault=fault)
        if fault=='result': assert r['判定']=='欠測' and not r['結果搬送一致'] and v is None
        elif fault=='prehang': assert r['判定']=='欠測'
        else: assert r['戻り']=='戻らない' and r['再起動']==(fault=='restart')
    for options in ({'frames':1},{'timeout':0.000001}):
        r,v=run(**options);assert r['判定']=='欠測' and v is None
    def broken(p,a,r,v):
        for name,edit in (
            ('extra',lambda s:s.replace('{','{"内部PC":123,',1)),
            ('extra',lambda s:s.replace('"states":[','"states":[[256,0,0],',1)),
            ('capture',lambda s:s.removesuffix('END\n')),
            ('capture',lambda s:s.replace('END\n','SECRET-DO-NOT-LEAK\nEND\n')),
            ('mem',lambda s:s.replace('取りこぼし: 0件','取りこぼし: 1件'))):
            q=p/name;old=q.read_text();q.write_text(edit(old))
            bad,v=summarize_run(p,a);assert bad['判定']=='欠測' and v is None
            assert 'SECRET' not in json.dumps(bad);q.write_text(old)
        q=p/'extra';x=json.loads(q.read_text());x['media_ok']=0;q.write_text(json.dumps(x))
        bad,v=summarize_run(p,a);assert bad['判定']=='欠測' and v is None
    run(check=broken)
    neg=summary['腕']['negative']['走'][0]
    for section in (None,'準備','割り込み','通信','結果相','シーク'):
        bad=copy.deepcopy(neg);target=bad if section is None else bad[section];target['値列']='SECRET-DO-NOT-LEAK'
        try: value_free(bad)
        except AssertionError: pass
        else: raise AssertionError('漏洩対照の検出力不足')
    forbidden={'values.tmp','mem','capture','extra','stderr','rom','probe.bin','probe.d88','media.d88','media2.d88','fixture.bin'}
    assert all(p.name not in forbidden and p.suffix.upper()!='.ROM' for d in ('raw','controls') for p in (root/d).rglob('*'))
    assert not (root/'build').exists()
    print('B88追補3: 時間切れ・再起動・搬送破損・記録破損・値漏れ・後片付け PASS',flush=True)


if __name__=='__main__': main(Path(sys.argv[1]))
