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
(work.parent/(work.name+'.started')).touch()
deadline = time.monotonic()+10
while work.parent.name == 'batch-1' and len(list(work.parent.glob('*.started'))) < 2:
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


def diagnostic_selftest(root):
    from types import SimpleNamespace
    import l4_inkey_measure as mod
    work = root/'diagnostic'; work.mkdir()
    exp, out = work/'expected.tsv', work/'measured.tsv'
    # 合成値を使い、腕ID以外の比較内容が診断へ出ないことを確認。
    def write(path, headers, rows):
        with path.open('w', newline='') as f:
            w = csv.writer(f, delimiter='\t'); w.writerow(headers); w.writerows(rows)
    write(exp, ['arm','prediction'], [('hold-a', json.dumps(['SECRET-WANTED']))])
    write(out, ['arm','repeat','print_values','gate'],
          [('hold-a', i, json.dumps(['SECRET-ACTUAL']), 'pass') for i in (1,2)])
    row = ('synthetic','unused.py',[],[],1,1)
    result = work/'status.txt'
    def mismatch(*args):
        return runner.checked_status(mod, exp, [out], False)
    with patch.object(runner,'worker',side_effect=mismatch):
        assert runner.execute_worker(row, root/'rom', work, result) == 1
    payload = json.loads(result.read_text())
    assert payload['mismatch'] == ['hold-a'] and payload['status']=='NG'
    text = result.read_text() + runner.summary(payload)
    assert 'hold-a' in text and 'SECRET' not in text
    write(out, ['arm','repeat','print_values','gate'],
          [('hold-a', i, json.dumps(['SECRET-ACTUAL']), 'gate_failed') for i in (1,2)])
    with patch.object(runner,'worker',side_effect=mismatch):
        assert runner.execute_worker(row, root/'rom', work, result)==1
    assert json.loads(result.read_text())['gate']==['hold-a']
    def explosion(*args):
        with tempfile.TemporaryDirectory(prefix='retained-', dir=work) as td:
            (Path(td)/'marker').touch()
            raise ValueError('SECRET-EXCEPTION-BODY')
    with patch.object(runner,'worker',side_effect=explosion):
        assert runner.execute_worker(row, root/'rom', work, result)==1
    payload = json.loads(result.read_text())
    text = result.read_text()+runner.summary(payload)
    assert payload['exception']=='ValueError' and payload['frames']
    assert list(work.glob('retained-*/marker'))
    assert any('l4_conform_selftest.py:' in f and 'explosion' in f for f in payload['frames'])
    assert 'SECRET' not in text and len(payload['frames'])<=4
    # 集計行にも同じ診断が載り、NG作業先を保持する。
    batch = root/'diagnostic-batch'; batch.mkdir()
    def failed(*args):
        dest = args[2]; dest.mkdir(); (dest/'status.txt').write_text(json.dumps(payload))
        return payload
    with patch.object(runner,'measure_one',side_effect=failed), redirect_stdout(io.StringIO()) as sink:
        assert runner.run_rows([row], root/'rom', batch, 1, True)==1
    assert 'ValueError' in sink.getvalue() and 'explosion' in sink.getvalue()
    assert 'SECRET' not in sink.getvalue() and (batch/'synthetic/status.txt').exists()
    # 実際のworker結果ファイルを親が読み、ID要約を出す。
    def synthetic(argv, env):
        Path(argv[argv.index('--result')+1]).write_text(json.dumps(
            dict(status='NG', mismatch=['hold-a'], gate=[])))
        return 1
    batch = root/'diagnostic-ids'; batch.mkdir()
    with patch.object(runner,'run_silent',side_effect=synthetic), redirect_stdout(io.StringIO()) as sink:
        assert runner.run_rows([row], root/'rom', batch, 1, True)==1
    assert '不一致=1:hold-a' in sink.getvalue() and 'SECRET' not in sink.getvalue()
    # 外部許可根は明示した子孫だけ。symlinkによる脱出も拒否。
    from l4_work_paths import allowed_path, ENV
    external = root/'allowed'; external.mkdir()
    sibling = root/'sibling'; sibling.mkdir()
    (external/'escape').symlink_to(sibling, target_is_directory=True)
    with patch.dict(os.environ, {ENV:str(external)}):
        assert allowed_path(external/'child', ())
        assert not allowed_path(sibling, ())
        assert not allowed_path(external/'escape/child', ())
        assert not allowed_path(Path('relative'), ())
    for invalid in (str(runner.REPO), str(runner.REPO.parent), '/', 'relative'):
        with patch.dict(os.environ, {ENV:invalid}):
            assert not allowed_path(runner.REPO/'tools/new-file', ())
    # 追補2凍結表の腕を本体+追補カタログから取得し、4関門を省かない。
    import l4_pusing_measure as pu
    row = next(r for r in runner.ROWS if r[0]=='pusing_add2')
    def measure(rom, official, selected, dest, **kwargs):
        assert not official and 'scientific-07' in {a['id'] for a in selected}
        return [dict(arm=a, obs=[pu.prediction(a)]*2, others=[0,0],
                     failed=[False,False], gate=True) for a in selected]
    with patch.object(pu,'measure',side_effect=measure):
        # 合成値の照合は凍結値と一致する必要がない。カタログ・関門・checkの接続を確認。
        runner.DETAIL.clear()
        assert runner.check_selected(pu, row, root/'rom', work, runner.expected(row), out) in ('OK','NG')
    assert {a['id'] for a in pu.gates2()} <= {r['arm'] for r in runner.read_rows(out)}
    # 本体は凍結表にない対照も採取し、出力は期待腕だけに保つ。
    row = next(r for r in runner.ROWS if r[0]=='pusing')
    subset = pu.controls()[:2] + pu.arms()[:1]
    expected = work/'pusing-synthetic.tsv'
    pu.write(expected, ['arm','prediction'],
             [(a['id'], json.dumps(pu.control_value(a))) for a in subset])
    def replay(rom, official, selected, dest, **kwargs):
        assert not official
        assert {a['id'] for a in pu.controls()} <= {a['id'] for a in selected}
        return [dict(arm=a, obs=[pu.control_value(a)]*2, others=[0,0],
                     failed=[False,False], gate=True) for a in selected]
    with patch.object(pu,'measure',side_effect=replay):
        assert runner.check_selected(pu, row, root/'rom', work, expected, out) == 'OK'
    assert {r['arm'] for r in runner.read_rows(out)} == {a['id'] for a in subset}
    good = replay(root/'rom', False, pu.controls()+pu.arms()[:1], work)
    for aid in pu.WRAP_CONTROLS:
        # 未出力対照でも、欠落・不一致・採取失敗は全照合腕の関門に伝播。
        for fault in ('missing', 'different', 'failed'):
            bad = copy.deepcopy(good)
            rec = next(r for r in bad if r['arm']['id'] == aid)
            if fault == 'missing': bad.remove(rec)
            elif fault == 'different': rec['obs'] = [pu.prediction(rec['arm'])]*2
            else: rec['failed'][0] = True
            assert not pu.emit(out, bad, selected=subset)
            assert not pu.check(expected, out)
    assert not pu.emit(out, good, selected=[dict(id='absent')])
    # 一体checkのID抽出と関門分類も値を転送しない。
    for name, record in (('listkw', dict(id='test-arm', obs_sig='gate_failed')),
                         ('s5j', dict(arm=SimpleNamespace(id='test-arm'), stable=False)),
                         ('listnum', dict(id='test-arm', gates=[True,False]))):
        def original(*args): return [record]
        def main():
            if name == 'listnum': fake.check_records([record], {})
            else: fake.measure()
            print('test-arm' if name == 's5j' else 'NG test-arm: SECRET-BODY')
            return 1
        fake = SimpleNamespace(measure=original, check_records=original, main=main)
        runner.DETAIL.clear()
        assert runner.integrated_check(fake, name, {'test-arm'}) == 'NG'
        assert runner.DETAIL['mismatch'] == runner.DETAIL['gate'] == ['test-arm']
        assert 'SECRET' not in json.dumps(runner.DETAIL)
    import l4_rnd_measure as rnd
    synthetic = [dict(round='round1', arm='test-arm', count='1', sha256_16='wanted')]
    runner.DETAIL.clear()
    with patch.object(rnd,'load_expected',return_value=synthetic), \
         patch.object(rnd,'arm_catalog',return_value={('round1','test-arm'):dict(id='test-arm',counts=[1])}), \
         patch.object(rnd,'run_arm',return_value=([['SECRET-VALUE']],0)), \
         patch.object(rnd,'valid',return_value=False):
        assert runner.check_rnd(rnd, root/'rom', exp, work/'rnd')=='NG'
    assert runner.DETAIL['mismatch']==runner.DETAIL['gate']==['round1:test-arm']
    assert 'SECRET' not in json.dumps(runner.DETAIL)
    print('OK NG診断: 不一致ID・関門ID / 例外型と末尾4フレーム / 本文・値なし / 集計要約・NG保持 / 外部許可根・脱出拒否 / 追補2カタログ')


def selftest(work):
    import l4_paint_measure as p
    lm = p.lm
    with tempfile.TemporaryDirectory(prefix='selftest-', dir=work) as td:
        root = Path(td)
        arms = {a['id']: a for a in p.arms()}
        plain = dict(arm='base-cls3', n=0, hash=lm.pix_hash({}), tail=0,
                     stat=[], spans=[], res={}, sent=1, last={})
        a = arms[next(iter(p.KNOWN_DIFFERENCES))]
        seed = dict(p.comparable(plain), res={})
        alternative = p.known_difference_target(a, seed)
        official = dict(alternative, hash='synthetic-frozen-observation')
        expected, measured = root/'expected.tsv', root/'measured.tsv'
        lm.write_tsv(expected, ['arm','observation'],
                     [(a['id'],json.dumps(official)),
                      ('base-cls3',json.dumps(p.comparable(plain)))])

        def save(value, base=plain, gate='pass'):
            obs = dict(value, arm=a['id'], sent=1)
            lm.write_tsv(measured, ['arm','repeat','plan','observation','gate',
                                    'prediction_judgement','failed'],
                         [(aid,i+1,json.dumps(p.plan(arms[aid])),json.dumps(o),gate,'{}',0)
                          for aid,o in ((a['id'],obs),('base-cls3',base)) for i in range(2)])

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
        with patch.object(runner, 'run_silent', return_value=0) as run, \
             patch('l4_line_measure.check', return_value=([], {'synthetic-arm': []})):
            assert runner.worker(row, root/'rom', root, root/'result') == 'NG'
            assert run.call_count == 1
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
        diagnostic_selftest(root)
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
