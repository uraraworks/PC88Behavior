#!/usr/bin/env python3
"""q1入口の短時間自己検査。合成期待値の複製のみ変更し凍結表は触らない。"""
import copy
import csv
import io
from contextlib import redirect_stdout
import json
from pathlib import Path
import shutil
import tempfile
import subprocess
import sys
import os
from unittest.mock import patch

import l4_conform_self as runner


def cache_selftest(root):
    repo = root/'synthetic'; tools = repo/'tools'
    tools.mkdir(parents=True)
    (repo/'tests/conformance').mkdir(parents=True)
    rom = root/'rom'; rom.mkdir()
    romfile = rom/'self.rom'; romfile.write_bytes(b'synthetic-rom')
    for name in ('l4_conform_self.py','run_l4_conform_self.sh','runall_cache.py'):
        (tools/name).write_text('# synthetic adapter')
    dependency = tools/'helper.py'; dependency.write_text('VALUE = 1')
    rows = [(n,n+'.py',[],[],1,1) for n in ('alpha','beta')]
    # 両プロセスが起動しなければ完走できないバリアで実際の並列性を確認。
    script = """import helper
import os, sys, time
from pathlib import Path
work, result, exp = map(Path, sys.argv[1:])
assert not any(k.startswith('PC88_REF_') for k in os.environ)
(work/'started').touch()
deadline = time.monotonic()+10
while work.parent.name == 'batch-1' and len(list(work.parent.glob('*/started'))) < 2:
    if time.monotonic() > deadline:
        raise RuntimeError('parallel barrier')
    time.sleep(.01)
result.write_text(exp.read_text())
"""
    for row in rows:
        (tools/row[1]).write_text(script)
        (repo/'tests/conformance'/('expected_l4_'+row[0]+'.tsv')).write_text('OK')
    cache = root/'cache'
    calls = []
    def synthetic(argv, env):
        assert argv[:3] == ['nice','-n','10']
        name = argv[argv.index('--worker')+1]
        work = argv[argv.index('--work-dir')+1]
        result = argv[argv.index('--result')+1]
        calls.append(name)
        proc = subprocess.run(['nice','-n','10',sys.executable,str(tools/(name+'.py')),
                               work,result,str(repo/'tests/conformance'/
                                               ('expected_l4_'+name+'.tsv'))],
                              env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE)
        return proc.returncode
    serial = 0
    def run(no_cache=False):
        nonlocal serial
        serial += 1
        work = root/('batch-'+str(serial)); work.mkdir()
        output = io.StringIO()
        with redirect_stdout(output):
            rc = runner.run_rows(list(reversed(rows)), rom, work, 2, no_cache)
        lines = output.getvalue().splitlines()
        assert len(lines) == 3
        assert lines[0].split()[1] == 'alpha' and lines[1].split()[1] == 'beta'
        return rc, [line.split()[0] for line in lines[:2]]
    with patch.object(runner,'REPO',repo), \
         patch.object(runner,'cache_root',return_value=cache), \
         patch.object(runner,'run_silent',side_effect=synthetic), \
         patch.dict(os.environ, {'PC88_REF_SYNTHETIC':'must-be-removed'}):
        cache.mkdir()
        assert dependency in runner.tool_inputs(rows[0])
        first = run()
        assert first == (0,['OK','OK']), (first, calls)
        assert sorted(calls) == ['alpha','beta']; calls.clear()
        assert run() == (0,['CACHED','CACHED']) and not calls
        # ROM・import閉包・器具本体・期待値をそれぞれ単独で変更する。
        for path in (romfile, dependency, tools/'alpha.py', runner.expected(rows[0])):
            original = path.read_bytes()
            path.write_bytes(original + (b'\n# change' if path.suffix=='.py' else b'\n'))
            rc, values = run()
            assert rc == 0 and values[0] == 'OK'
            assert run() == (0,['CACHED','CACHED'])
            path.write_bytes(original)
            assert run()[1][0] == 'OK'
        # KNOWNも成功として記録する。NGと同走の他器具も完了する。
        runner.expected(rows[0]).write_text('NG')
        runner.expected(rows[1]).write_text('KNOWN')
        assert run() == (1,['NG','KNOWN'])
        assert run() == (1,['NG','CACHED'])
        saved = json.loads((cache/'alpha.json').read_text())
        assert saved['status'] == 'OK'  # NGで上書きしていない。
        runner.expected(rows[0]).write_text('KNOWN')
        assert run() == (0,['KNOWN','CACHED'])
        assert run() == (0,['CACHED','CACHED'])
        calls.clear()
        assert run(no_cache=True) == (0,['KNOWN','KNOWN'])
        assert sorted(calls) == ['alpha','beta']


def selftest(work):
    import l4_paint_measure as p
    lm = p.lm
    with tempfile.TemporaryDirectory(prefix='selftest-', dir=work) as td:
        root = Path(td)
        arms = {a['id']: a for a in p.arms()}
        plain = dict(arm='base-cls3', n=0, hash=lm.pix_hash({}), tail=0,
                     stat=[], spans=[], res={}, sent=1, last={})
        a = arms['ws-8a']
        seed = dict(p.comparable(plain), res={'2': [0,0,0]})
        alternative = p.known_difference_target(a, seed)
        official = dict(alternative, hash='synthetic-frozen-observation')
        expected, measured = root/'expected.tsv', root/'measured.tsv'
        lm.write_tsv(expected, ['arm','observation'],
                     [('ws-8a',json.dumps(official)),
                      ('base-cls3',json.dumps(p.comparable(plain)))])

        def save(value, base=plain, gate='pass'):
            obs = dict(value, arm=a['id'], sent=1)
            lm.write_tsv(measured, ['arm','repeat','plan','observation','gate',
                                    'prediction_judgement','failed'],
                         [(aid,i+1,json.dumps(p.plan(arms[aid])),json.dumps(o),gate,'{}',0)
                          for aid,o in (('ws-8a',obs),('base-cls3',base)) for i in range(2)])

        def verdict(exp=expected):
            _, bad, known, _ = p.check(exp, measured)
            return runner.status(bool(bad), bool(known))

        save(official)
        assert verdict() == 'OK'
        save(alternative)
        assert verdict() == 'KNOWN'
        # 複製のデータ行を1行だけ変更。元の期待値は変えない。
        broken = root/'expected-broken.tsv'
        shutil.copyfile(expected, broken)
        before = expected.read_bytes()
        with broken.open(newline='') as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        changed = json.loads(rows[1]['observation']); changed['hash'] = 'negative-control'
        rows[1]['observation'] = json.dumps(changed)
        lm.write_tsv(broken, ['arm','observation'],
                     [(r['arm'],r['observation']) for r in rows])
        assert verdict(broken) == 'NG'
        assert expected.read_bytes() == before
        # 既知腕でも許容外の誤り番号・関門落ちはNG。
        wrong = copy.deepcopy(alternative)
        key = next(str(i) for it,stmt,probe,i,pred in p.steps(a)[0] if it['op']=='P')
        wrong['res'][key][0] = 5
        save(wrong); assert verdict() == 'NG'
        save(alternative, gate='gate_failed'); assert verdict() == 'NG'
        assert runner.status(1, True) == 'NG'
        # 本物の凍結表も複製だけを破損させる。空画面腕の独立な合成観測を照合。
        frozen = runner.expected(next(r for r in runner.ROWS if r[0]=='paint'))
        copied = root/'frozen-copy.tsv'
        shutil.copyfile(frozen, copied)
        save(alternative)
        assert not p.check(frozen, measured, ['base-cls3'])[1]
        with copied.open(newline='') as stream:
            reader = csv.DictReader(stream, delimiter='\t')
            headers = reader.fieldnames
            rows = list(reader)
        changed_rows = 0
        for row in rows:
            if row['arm']=='base-cls3':
                value = json.loads(row['observation'])
                value['hash'] = 'negative-control'
                row['observation'] = json.dumps(value)
                changed_rows += 1
        assert changed_rows == 1
        lm.write_tsv(copied, headers, [[row[h] for h in headers] for row in rows])
        assert p.check(copied, measured, ['base-cls3'])[1]
        assert not p.check(frozen, measured, ['base-cls3'])[1]
        # 許可された自作入口が測定・checkを呼び、NGを握り潰さないこと。
        row = next(r for r in runner.ROWS if r[0]=='line')
        with patch.object(runner, 'run_silent', side_effect=[0, 1]) as run:
            assert runner.worker(row, root/'rom', root, root/'result') == 'NG'
            assert run.call_count == 2
            assert all('--official' not in call.args[0] for call in run.call_args_list)
        # KEYの4要素戻り値（KNOWNあり）も既存判定のまま要約する。
        import l4_key_measure as key
        row = next(r for r in runner.ROWS if r[0]=='key')
        with patch.object(key,'measure',return_value=[]), \
             patch.object(key,'emit',return_value=True), \
             patch.object(key,'check',return_value=(1,[],['boot'],[])):
            assert runner.worker(row, root/'rom', root, root/'result')=='KNOWN'
        with patch.object(key,'measure',return_value=[]), \
             patch.object(key,'emit',return_value=True), \
             patch.object(key,'check',return_value=(0,['unexpected'],['boot'],[])):
            assert runner.worker(row, root/'rom', root, root/'result')=='NG'
        # --listは期待値の本文を開かず、名前・器具定義だけを列挙する。
        with patch.object(Path, 'open', side_effect=AssertionError('一覧で本文を開いた')), \
             redirect_stdout(io.StringIO()):
            runner.table()
        cache_selftest(root)
        env = runner.clean_env(root)
        assert not any(k.startswith('PC88_REF_') for k in env)
        assert not any(reason == '未棚卸し' for _,reason in runner.inventory())
    print('OK 陽性照合 / 凍結表・合成期待値の複製1行破損→NG / 登録差→KNOWN / 許容外・関門落ち→NG')
    print('OK 自作measure→checkのNG伝播 / 公式引数なし / PC88_REF_*除去 / 棚卸し網羅 / -j 2並列・NG後も完走 / 器具別CACHED・各入力変更失効・NG非記録・no-cache')
    return 0


if __name__ == '__main__':
    import argparse
    import os
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work-dir', default=os.environ.get('PC88_L4_CONFORM_WORK',
                    str(Path(os.environ.get('TMPDIR','/tmp'))/'q1-check-work')))
    args = ap.parse_args()
    raise SystemExit(selftest(runner.external_work(args.work_dir)))
