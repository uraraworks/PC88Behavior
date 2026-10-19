#!/usr/bin/env python3
"""凍結TSVへの自作ROM照合。器具の出力は保存・転送せず、固定形式の要約のみ。

器具単位のキャッシュは自作ROM・tools閉包・期待値の内容ハッシュで照合する。
"""
import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
import csv
import importlib
import json
import os
import shutil
import traceback
from unittest.mock import patch
from pathlib import Path
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
# 名前、器具、measure追加引数、check追加引数、腕数（対照含む）、秒の見込み。
# integrated は check 内で測定。api は既存関数へ同じ引数を渡す（CLIの旧作業先制限を避ける）。
ROWS = [
 ('hexconst','l4_hexconst_measure.py',[],[],68,360),
 ('strcmp','l4_strcmp_measure.py',[],[],213,480),
 ('strfunc','l4_strfunc_measure.py',[],[],91,240),
 ('peekpoke','l4_peekpoke_measure.py',[],[],30,90),
 ('inkey','l4_inkey_measure.py',[],[],26,120),
 ('wrap','l4_wrap_measure.py',[],[],96,240),
 ('deffn','l4_deffn_measure.py',[],[],59,180),
 ('deftype','l4_deftype_measure.py',[],[],111,300),
 ('tabspc','l4_tabspc_measure.py',[],[],101,300),
 ('widthbeep','l4_widthbeep_measure.py',[],[],153,420),
 ('editinv','l4_editinv_measure.py',[],[],150,420),
 ('onwhile','l4_onwhile_measure.py',[],[],100,300),
 ('memlimit','l4_memlimit_measure.py',[],[],73,300),
 ('memlimit_add1','l4_memlimit_measure.py',['--addendum','1'],[],31,240),
 ('memlimit_add2','l4_memlimit_measure.py',['--addendum','2'],[],13,120),
 ('memlimit_add3','l4_memlimit_measure.py',['--addendum','3'],[],13,120),
 ('pusing','l4_pusing_measure.py',[],[],140,420),
 ('pusing_add2','l4_pusing_measure.py',['--addendum','2'],[],22,300),
 ('line','l4_line_measure.py',['--no-calibration'],[],68,240),
 ('circle','l4_circle_measure.py',['--no-calibration'],[],45,180),
 ('paint','l4_paint_measure.py',['--no-calibration'],[],67,360),
 ('getput','l4_getput_measure.py',['--no-calibration'],[],88,300),
 ('dim','l4_dim_results.py',[],[],143,420),
 ('input','l4_input_measure.py',['api'],[],75,240),
 ('directgoto','l4_directgoto_measure.py',['api'],[],16,90),
 ('key','l4_key_measure.py',['api'],[],38,120),
 ('portio','l4_portio_measure.py',['api'],[],50,180),
 ('out_output','l4_out_output_measure.py',['api'],[],18,90),
 ('mlcall','l4_mlcall_measure.py',['api','first','addendum1'],['--results'],70,420),
 ('mlcall_usrarg','l4_mlcall_measure.py',['api','addendum2','addendum3'],['--results'],20,180),
 ('listkw','l4_listkw_measure.py',['integrated'],[],723,180),
 ('listnum','l4_listnum_measure.py',['integrated'],[],193,420),
 ('s5j','l4_s5j_measure.py',['integrated'],[],113,300),
 ('rnd','l4_rnd_measure.py',['integrated'],['--all'],108,1800),
]
L3_EXPECTED = {
    'files','load','load_existing','seqfile','kill','name','run_file','merge','bsave',
    'bload','random_file','direct_sector','missing_load','write_protect','no_disk',
    'unreadable_disk','drive1','drive2','insert_after_wait','save_drive1','save_drive2',
    'screen','write',
}
SPECIAL_EXCLUDED = {
 'l4_bsave': 'l4_bsave_measure.py: 自作measureもPC88_REF_DISK_DIRの参照媒体必須。自作媒体だけの経路なし',
 'l4_editor': 'conform_l3_editor.sh の既存別経路（measure/checkサブコマンドなし）',
 **{f'l4_{n}': 'conform_l4.sh の既存別経路（対応するmeasure/checkサブコマンドなし）'
    for n in ('echo','print','float','programs','arith','trans')},
 **{f'l4_{n}_unpredicted': f'l4_{n}_measure.py: 予測なし専用表。checkはprediction=Noneを拒否し比較できない'
    for n in ('deftype','tabspc','widthbeep')},
}


# 以下は採取対象の指定を持つ器具。照合アダプターが期待値の腕集合を検証し、
# 本体・追補のカタログから採取する。値の比較は元のcheckのみで行う。
SELECTED = {'hexconst','strcmp','strfunc','peekpoke','inkey','wrap','deffn',
            'deftype','tabspc','widthbeep','editinv','onwhile','memlimit',
            'memlimit_add1','memlimit_add2','memlimit_add3','pusing','pusing_add2'}


# 診断に値・例外本文を混ぜない。workerごとの独立プロセス内だけで使用。
DETAIL = {}


def exception_detail(exc):
    frames = [(Path(f.f_code.co_filename).name, n, f.f_code.co_name)
              for f, n in traceback.walk_tb(exc.__traceback__)]
    return dict(exception=type(exc).__name__,
                frames=[f'{file}:{line} {func}' for file, line, func in frames[-4:]])


def read_rows(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader((line for line in stream if not line.startswith('#')), delimiter='\t'))


def gates(paths):
    bad = set()
    for path in paths:
        if not path.exists():
            continue
        for r in read_rows(path):
            if (r.get('gate', 'pass') != 'pass' or
                    r.get('status') == 'gate_failed' or
                    r.get('typing_or_capture_failed', '0') != '0' or
                    r.get('skipped', '0') != '0'):
                bad.add(r['arm'])
    return sorted(bad)


def note_bad(bad, paths):
    DETAIL['mismatch'] = sorted(set(bad))
    DETAIL['gate'] = gates(paths)


def bool_bad(mod, exp, out):
    """bool型checkの診断用。期待値・観測を腕単位で比較しIDのみを返す。

    合否は必ず器具のcheckで決定する。射影はその器具と同じcomparableを使う。
    """
    wanted, actual = {}, {}
    for r in read_rows(exp):
        if r.get('candidate', 'K_BUF') != 'K_BUF' and mod.__name__ == 'l4_inkey_measure':
            continue
        wanted.setdefault(r['arm'], []).append(r)
    for r in read_rows(out):
        actual.setdefault(r['arm'], []).append(r)
    catalog = ({a['id']: a for a in mod.controls()+mod.arms()}
               if hasattr(mod, 'controls') else {})
    def value(r, aid, expected=False):
        field = next(k for k in (('prediction', 'observation', 'print_values') if expected
                                  else ('observation', 'print_values')) if r.get(k))
        v = json.loads(r[field])
        if hasattr(mod, 'comparable'):
            v = (mod.comparable(v) if mod.__name__ == 'l4_editinv_measure'
                 else mod.comparable(v, catalog[aid]))
        return v
    bad = set(wanted) ^ set(actual)
    for aid in set(wanted) & set(actual):
        runs = actual[aid]
        try:
            targets = [value(r, aid, True) for r in wanted[aid]]
            obs = [value(r, aid) for r in runs]
            if (len(runs) != 2 or {r['repeat'] for r in runs} != {'1','2'} or
                    obs[0] != obs[1] or any(v not in targets for v in obs) or
                    any(r.get('status', 'pass') not in ('pass', 'observed') for r in runs)):
                bad.add(aid)
        except (ValueError, KeyError, TypeError, StopIteration):
            bad.add(aid)
    return sorted(bad)


def checked_status(mod, exp, paths, checked, known=False):
    if isinstance(checked, bool):
        bad = bool_bad(mod, exp, paths[0]) if not checked else []
        failed = not checked
    else:
        bad = list(checked[1])
        failed = bool(bad)
        known = bool(checked[2]) if len(checked) > 2 else known
    if failed:
        note_bad(bad, paths)
    return status(failed, known)


def ng_measure(paths):
    note_bad([], paths)
    return 'NG'


def summary(detail):
    parts = []
    if detail.get('exception'):
        parts.append('例外=' + detail['exception'] + ' 場所=' + ', '.join(detail['frames']))
    for key, label in (('mismatch', '不一致'), ('gate', '関門落ち')):
        ids = detail.get(key, [])
        parts.append(f'{label}={len(ids)}' + (':' + ','.join(ids[:5]) if ids else ''))
    if detail.get('process_rc') is not None:
        parts.append(f"worker終了値={detail['process_rc']}")
    return ' / '.join(parts)


def out_output_bad(mod, exp, out):
    wanted = {r['arm']: json.loads(r['observation']) for r in read_rows(exp)}
    actual = {r['arm']['id']: r for r in mod.read_passed(out)}
    return [aid for aid, value in wanted.items()
            if aid not in actual or actual[aid]['obs'][0] != value]


def emit_pusing_add2(mod, out, records):
    """凍結追補は本体のscientific-07も含み、空書式の未凍結腕は含まない。

    emit2の全selected2集合必須条件とは別に、同じ4関門で期待腕を測る。
    値の照合は元のcheckに任せる。予測外を合格扱いする経路はない。
    """
    by_id = {r['arm']['id']: r for r in records}
    def stable(r):
        return (r['gate'] and not any(r['failed']) and
                r['obs'][0] == r['obs'][1] and mod.valid(r['obs'][0]))
    calibrated = all(a['id'] in by_id and stable(by_id[a['id']]) and
                     by_id[a['id']]['obs'][0] == mod.prediction(a) for a in mod.gates2())
    rows = []
    passed = calibrated
    for aid, r in by_id.items():
        gate = calibrated and stable(r)
        passed = passed and gate
        for i in range(2):
            rows.append((aid, i+1, json.dumps(r['obs'][i]),
                         'pass' if gate else 'gate_failed', int(r['failed'][i])))
    mod.write(out, ['arm','repeat','observation','gate','typing_or_capture_failed'], rows)
    return passed


def check_selected(mod, row, rom, work, exp, out):
    # checkの内部準備: 値は解釈・表示せず、全期待腕にちょうど対応する操作を選ぶ。
    with exp.open(newline='') as stream:
        ids = {r['arm'] for r in csv.DictReader(stream, delimiter='\t')}
    name = row[0]
    if name.startswith('memlimit'):
        catalog = mod.selection(int(name[-1]) if '_add' in name else None)
    elif name == 'pusing_add2':
        catalog = mod.controls()+mod.arms()+mod.selected2()
    else:
        catalog = mod.controls()+mod.arms()
        if name == 'inkey': catalog += mod.addendum_arms()
    by_id = {a['id']:a for a in catalog}
    if not ids or not ids <= set(by_id):
        raise ValueError('期待値の腕が器具カタログにない')
    selected = [a for a in by_id.values() if a['id'] in ids]
    trap = not (name=='hexconst' and not any(a.get('error') for a in selected if a['id'].startswith('control-')))
    options = {'trap': trap} if name=='hexconst' else {}
    records = mod.measure(rom, False, selected, work, **options)
    if name == 'pusing_add2':
        passed = emit_pusing_add2(mod, out, records)
    elif name == 'wrap':
        passed = mod.emit(out, records, selected)
    else:
        passed = (mod.emit2 if name=='pusing_add2' else mod.emit)(out, records, **options)
    if not passed:
        DETAIL['gate'] = gates([out])
        with KnownSink() as sink:
            checked = mod.check(exp, out)
        checked_status(mod, exp, [out], checked, sink.known)
        DETAIL['gate'] = gates([out])
        return 'NG'
    with KnownSink() as sink:
        agrees = mod.check(exp, out)
    return checked_status(mod, exp, [out], agrees, sink.known)


def expected(row):
    return REPO / 'tests/conformance' / ('expected_l4_' + row[0] + '.tsv')


def inventory():
    """期待値は名前の列挙だけ。値は器具のcheckへ渡す。"""
    used = {expected(r).name for r in ROWS}
    excluded = []
    for path in sorted((REPO/'tests/conformance').glob('expected_*.tsv')):
        if path.name not in used:
            key = path.stem.removeprefix('expected_')
            reason = SPECIAL_EXCLUDED.get(key)
            if reason is None:
                reason = 'conform_l3.sh の既存別経路' if key in L3_EXPECTED else '未棚卸し'
            excluded.append((path.name, reason))
    return excluded


def table():
    print('名前\t期待値\t器具\tmeasure引数\tcheck引数\t腕数上限（対照含む）\t見込み秒')
    for r in ROWS:
        name, tool, m, c, count, seconds = r
        if name in SELECTED:
            ma = 'API measure(R,False,期待腕の操作集合,W); emit(M,records)'
            if name == 'pusing_add2': ma += '（本体＋selected2カタログ、追補2の4関門）'
            if name.startswith('memlimit'): ma += ' ' + ' '.join(m)
            ca = 'API check(E,M)（期待値全腕、predicted-onlyなし）'
        elif m[:1] == ['integrated']:
            ma = 'check内の自作measure（作業先TMPDIR）'
            ca = 'check --rom-dir R --expected E ' + ' '.join(c)
        elif m[:1] == ['api']:
            ma = 'API measure(R,False,W)' + (' rounds='+','.join(m[1:]) if len(m)>1 else '')
            if name == 'input': ma = 'API measure(R,False,arms(),W); emit(M,records)'
            elif name == 'out_output': ma = 'API measure(R,False,W,M)'
            elif name.startswith('mlcall'): ma += '; emit(M,records)'
            else: ma += '; emit(M,records)'
            ca = ('API results_check(E,測定TSV群)' if c else 'API check(E,M)')
        else:
            ma = 'measure --rom-dir R --work-dir W --out M ' + ' '.join(m)
            ca = 'check --expected E --measured M ' + ' '.join(c)
        print('\t'.join(map(str,[name,expected(r).name,tool,ma.strip(),ca.strip(),count or '不明',f'{seconds}〜{seconds*3}'])))
    for name, reason in inventory():
        print(f'対象外\t{name}\t{reason}\t—\t—\t—\t—')


def run_silent(argv, env):
    # 画面本文を含む例外・check差分もログに残さない。
    return subprocess.run(argv, cwd=REPO, env=env, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode


def status(rc, known=False):
    return 'NG' if rc else 'KNOWN' if known else 'OK'


def worker(row, rom, work, result):
    """別プロセス。標準出力は破棄し、結果は合否と値を含まない診断だけ。"""
    name, tool, margs, cargs, _, _ = row
    mod = importlib.import_module(Path(tool).stem)
    out = work/'measured.tsv'
    exp = expected(row)
    if name in SELECTED:
        return check_selected(mod, row, rom, work, exp, out)
    if margs[:1] == ['api']:
        if name.startswith('mlcall'):
            paths = []
            for rnd in margs[1:]:
                dest = work/rnd; dest.mkdir()
                mod.ROUND = rnd
                p = dest/'measured.tsv'; paths.append(p)
                if not mod.emit(p, mod.measure(rom, False, dest)):
                    return ng_measure(paths)
            with KnownSink() as sink:
                _, bad = mod.results_check(exp, paths)
            note_bad(bad, paths) if bad else None
            return status(bool(bad), sink.known)
        if name == 'out_output':
            rc = mod.measure(rom, False, work, out)
            with KnownSink() as sink:
                differs = mod.check(exp, out) if not rc else True
            if rc:
                DETAIL['gate'] = gates([out])
                if out.exists(): note_bad(out_output_bad(mod, exp, out), [out])
                return 'NG'
            if differs: note_bad(out_output_bad(mod, exp, out), [out])
            return status(differs, sink.known)
        records = (mod.measure(rom, False, mod.arms(), work) if name == 'input'
                   else mod.measure(rom, False, work))
        if not mod.emit(out, records):
            with KnownSink() as sink:
                checked = mod.check(exp, out)
            checked_status(mod, exp, [out], checked, sink.known)
            DETAIL['gate'] = gates([out])
            return 'NG'
        with KnownSink() as sink:
            checked = mod.check(exp, out)
        return checked_status(mod, exp, [out], checked, sink.known)
    if margs[:1] == ['integrated']:
        # 元のcheckが測定と照合を一体で行う。TMPDIRで作業先を外部へ固定。
        sys.argv = [tool, 'check', '--rom-dir', str(rom), '--expected', str(exp), *cargs]
        # 合否語と許可した腕IDだけを検出する。
        if name == 'rnd': return check_rnd(mod, rom, exp, work)
        return integrated_check(mod, name, integrated_ids(exp))
    env = dict(os.environ)
    rc = run_silent([sys.executable, str(REPO/'tools'/tool), 'measure', '--rom-dir', str(rom),
                     '--work-dir', str(work), '--out', str(out), *margs], env)
    if rc:
        # measureが候補差をNGとした場合も、存在するTSVから腕を診断する。
        if not out.exists(): return ng_measure([out])
        with KnownSink() as sink:
            checked = mod.check(exp, out)
        checked_status(mod, exp, [out], checked, sink.known)
        DETAIL['gate'] = gates([out])
        return 'NG'
    with KnownSink() as sink:
        checked = mod.check(exp, out)
    return checked_status(mod, exp, [out], checked, sink.known)


def check_rnd(mod, rom, exp, work):
    """一体checkと同じ全腕・1走の署名照合。構造化されたIDだけを記録する。"""
    selected = mod.select_expected(mod.load_expected(exp), None, True)
    catalog = mod.arm_catalog()
    bad, gate = [], []
    if not selected:
        raise ValueError('照合対象なし')
    for row in selected:
        aid = row['round'] + ':' + row['arm']
        arm = catalog[(row['round'], row['arm'])]
        dest = work / row['round'] / row['arm']; dest.mkdir(parents=True)
        try:
            if 'pages' in arm:
                parts, _ = mod.run_paged_arm(rom, False, arm, dest)
                valid_output = mod.paged_valid(parts, arm)
                values = [value for part in parts for value in part]
            else:
                values, _ = mod.run_arm(rom, False, arm, dest)
                valid_output = mod.valid(values, arm['counts']) and all(
                    len(value) == (3 if arm['id'] == 'range' and i == 2 else 5)
                    for i, value in enumerate(values))
            if not valid_output: gate.append(aid)
            agrees = (valid_output and len(values) == int(row['count']) and
                      mod.rows_digest(values)[:16] == row['sha256_16'])
        except Exception as exc:
            agrees = False; gate.append(aid)
            if 'exception' not in DETAIL: DETAIL.update(exception_detail(exc))
        if not agrees: bad.append(aid)
    if bad:
        DETAIL.update(mismatch=sorted(bad), gate=sorted(gate))
    return status(bool(bad))


def record_gates(records):
    for r in records:
        aid = r.get('id')
        if aid is None:
            arm = r['arm']; aid = arm['id'] if isinstance(arm, dict) else arm.id
        if (r.get('obs_sig') == 'gate_failed' or not r.get('stable', True) or
                not all(r.get('gates', [True])) or not r.get('gate', True)):
            DETAIL.setdefault('gate', []).append(aid)
    DETAIL['gate'] = sorted(set(DETAIL.get('gate', [])))


def integrated_check(mod, name, ids):
    # 一体checkの戻り値はrcだけなので、測定レコードから関門IDを受け取る。
    function = 'check_records' if name == 'listnum' else 'measure'
    original = getattr(mod, function, None)
    def observed(*args, **kwargs):
        if name == 'listnum':
            record_gates(args[0])
            return original(*args, **kwargs)
        records = original(*args, **kwargs)
        record_gates(records)
        return records
    with KnownSink(ids=ids) as sink:
        if original and name != 'rnd':
            with patch.object(mod, function, observed):
                rc = mod.main()
        else:
            rc = mod.main()
    if rc:
        DETAIL['mismatch'] = sorted(sink.bad)
    return status(rc, sink.known)


def integrated_ids(exp):
    ids = set()
    for line in exp.read_text().splitlines():
        if line.startswith('# excluded\t'):
            ids.update(line.split('\t')[1].split(','))
        elif line and not line.startswith('#'):
            ids.add(line.split('\t')[0])
    # RNDはroundとarmを組み合わせて表示する。
    for r in read_rows(exp):
        if 'round' in r and 'arm' in r:
            ids.add(r['round'] + ':' + r['arm'])
    return ids



class KnownSink:
    """行頭の固定語だけ検知。画面本文や差分は蓄積しない。"""
    def __init__(self, ids=()):
        self.ids = ids
        self.bad = set()
        self.line = ''
        self.known = False
        self.prefix = ''
    def write(self, value):
        for part in value.splitlines(keepends=True):
            if self.ids:
                self.line = (self.line + part)[:256]
                if part.endswith('\n'):
                    line = self.line.strip()
                    for aid in self.ids:
                        if (line == aid or line.startswith('NG ' + aid + ':') or
                                line.startswith(aid + ' 不一致')):
                            self.bad.add(aid)
                    self.line = ''
            self.prefix = (self.prefix + part)[:6]
            if self.prefix.startswith('KNOWN '): self.known = True
            if part.endswith('\n'): self.prefix = ''
        return len(value)
    def flush(self): pass
    def __enter__(self):
        self.old = sys.stdout; sys.stdout = self
        return self
    def __exit__(self, *args): sys.stdout = self.old


def clean_env(work):
    env = {k:v for k,v in os.environ.items() if not k.startswith('PC88_REF_')}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['TMPDIR'] = str(work)
    env['PC88_L4_CONFORM_ALLOWED_ROOT'] = str(work.resolve())
    return env


def external_work(value):
    p = Path(value).expanduser().resolve()
    if p == REPO or REPO in p.parents:
        raise ValueError('作業先はリポジトリ外の絶対パスを指定してください')
    p.mkdir(parents=True, exist_ok=True)
    return p


def tool_inputs(row):
    """runallの参照名解析を流用し、tools内だけで閉包を求める。

    毎回読み直すため、同一プロセスの自己検査でも変更を見落とさない。
    private/・ノート・runallのglobal_fpには触れない。
    """
    import runall_cache as cache
    index = {}
    for p in (REPO/'tools').rglob('*'):
        if p.suffix in ('.py', '.sh') and '__pycache__' not in p.parts:
            index.setdefault(p.name, []).append(p)
    pending = [REPO/'tools'/row[1]]
    seen = set()
    while pending:
        p = pending.pop()
        if p in seen:
            continue
        seen.add(p)
        for name in cache.referenced_names(str(p), p.read_text()):
            pending.extend(index.get(name, []))
    # 照合アダプター・閉包解析の変更も成功キャッシュを失効させる。
    seen.update(REPO/'tools'/n for n in
                ('l4_conform_self.py', 'run_l4_conform_self.sh', 'runall_cache.py'))
    return sorted(seen)


def file_digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def rom_digest(rom):
    files = sorted(p for p in rom.rglob('*') if p.is_file())
    if not files:
        raise ValueError('自作ROMがありません')
    return hashlib.sha256(json.dumps([(str(p.relative_to(rom)), file_digest(p))
                                      for p in files]).encode()).hexdigest()


def cache_key(row, rom_hash):
    data = [1, row, rom_hash,
            [(str(p.relative_to(REPO)), file_digest(p)) for p in tool_inputs(row)],
            file_digest(expected(row))]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def cache_root():
    base = os.environ.get('PC88_RUNALL_CACHE_DIR', str(REPO.parent/'tmp/runall-cache'))
    return external_work(str(Path(base)/'l4-conform-self'))


def measure_one(row, rom, dest):
    dest.mkdir()
    result = dest/'status.txt'
    rc = run_silent(['nice','-n','10',sys.executable,str(Path(__file__).resolve()),
                     '--worker',row[0],'--work-dir',str(dest),'--rom',str(rom),
                     '--result',str(result)], clean_env(dest))
    raw = result.read_text().strip() if result.exists() else 'NG'
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = dict(status=raw)  # 合成・旧workerとの互換
    if rc or payload.get('status') not in ('OK', 'KNOWN'):
        payload['status'] = 'NG'
        if not result.exists(): payload['process_rc'] = rc
    else:
        shutil.rmtree(dest)
    return payload


def run_rows(selected, rom, root, jobs, no_cache=False):
    cache = None if no_cache else cache_root()
    rh = rom_digest(rom) if cache else None

    def run(row):
        start = time.monotonic()
        try:
            key = cache_key(row, rh) if cache else None
            entry = cache/(row[0]+'.json') if cache else None
            if entry:
                try:
                    saved = json.loads(entry.read_text())
                    if saved.get('key') == key and saved.get('status') in ('OK','KNOWN'):
                        return 'CACHED', time.monotonic()-start, {}
                except (OSError, ValueError, AttributeError):
                    pass
            detail = measure_one(row, rom, root/row[0])
            value = detail['status']
            if entry and value in ('OK','KNOWN'):
                # 成功だけを原子的に記録。並行する別の本走とも途中状態を共有しない。
                with tempfile.NamedTemporaryFile(mode='w', dir=cache, delete=False) as f:
                    temp = Path(f.name)
                    json.dump(dict(key=key, status=value), f)
                try:
                    temp.replace(entry)
                finally:
                    temp.unlink(missing_ok=True)
            return value, time.monotonic()-start, detail
        except Exception as exc:
            detail = dict(status='NG', **exception_detail(exc))
            dest = root/row[0]; dest.mkdir(exist_ok=True)
            (dest/'status.txt').write_text(json.dumps(detail)+'\n')
            return 'NG', time.monotonic()-start, detail

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {row[0]: pool.submit(run, row) for row in selected}
        results = {name: future.result() for name, future in futures.items()}
    counts = dict(OK=0, NG=0, KNOWN=0, CACHED=0)
    for name, (value, seconds, detail) in sorted(results.items()):
        counts[value] += 1
        print(f'{value} {name} {seconds:.1f}秒' +
              (' ' + summary(detail) if value=='NG' else ''), flush=True)
    print('集計 ' + ' / '.join(f'{k} {v}' for k,v in counts.items()))
    return int(counts['NG'] != 0)


class WorkerDirectory:
    """worker内の測定中間物は親が合否に応じてまとめて処理する。"""
    def __init__(self, *args, **kwargs):
        self.name = tempfile.mkdtemp(*args, **kwargs)
    def __enter__(self): return self.name
    def __exit__(self, *args): pass
    def cleanup(self): pass


def execute_worker(row, rom, work, result):
    DETAIL.clear()
    try:
        with patch.object(tempfile, 'TemporaryDirectory', WorkerDirectory):
            value = worker(row, rom, work, result)
    except Exception as exc:
        value = 'NG'
        DETAIL.update(exception_detail(exc))
    result.write_text(json.dumps(dict(status=value, **DETAIL), ensure_ascii=False)+'\n')
    return int(value == 'NG')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--list', action='store_true')
    ap.add_argument('-j', type=int, default=3, help='同時実行する器具数（既定3）')
    ap.add_argument('--no-cache', action='store_true', help='キャッシュの参照・記録をしない')
    ap.add_argument('--only', help='器具名（一覧の名前列）、カンマ区切り')
    ap.add_argument('--work-dir', default=os.environ.get('PC88_L4_CONFORM_WORK',
                   str(Path(os.environ.get('TMPDIR','/tmp'))/'q1-check-work')))
    ap.add_argument('--worker', help=argparse.SUPPRESS)
    ap.add_argument('--rom', type=Path, help=argparse.SUPPRESS)
    ap.add_argument('--result', type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    for k in list(os.environ):
        if k.startswith('PC88_REF_'): del os.environ[k]
    if args.list:
        table(); return 0
    if args.j < 1:
        ap.error('-j は1以上を指定してください')
    work = external_work(args.work_dir)
    if args.worker:
        row = next(r for r in ROWS if r[0] == args.worker)
        return execute_worker(row, args.rom, work, args.result)
    names = args.only.split(',') if args.only is not None else [r[0] for r in ROWS]
    if not names or any(n not in {r[0] for r in ROWS} for n in names):
        ap.error('--only の名前が一覧にありません')
    if any(reason=='未棚卸し' for _,reason in inventory()):
        print('NG 新しい期待値の棚卸しが必要です。--listを確認してください'); return 2
    selected = [r for r in ROWS if r[0] in names]
    if any(not expected(r).is_file() for r in selected):
        print('NG 前提不足: 対象の凍結期待値TSVがありません'); return 2
    front = REPO/'tools/harness/frontend/q88measure'
    if not front.is_file() or not os.access(front, os.X_OK):
        print('NG 前提不足: q88measureが実行不可。tools/setup_harness.shで準備してください'); return 2
    import l4_listkw_measure as kw
    try:
        kw.find_core()
    except (SystemExit, OSError):
        print('NG 前提不足: quasi88のコアがありません。tools/setup_harness.shで準備してください'); return 2
    root = Path(tempfile.mkdtemp(prefix='run-', dir=work))
    try:
        env = clean_env(root)
        rom = root/'rom'
        rc = run_silent([sys.executable, str(REPO/'src/build_main_rom.py'), str(rom),
                         '--work-dir', str(root/'asm')], env)
        if rc:
            print(f'NG 自作ROMビルド失敗 rc={rc}（前提・書込み・ビルド環境を確認）'); return 1
        return run_rows(selected, rom, root, args.j, args.no_cache)
    finally:
        # NGの器具ディレクトリだけ残す（ROM・ビルド中間物は除去）。
        for path in root.iterdir():
            if path.is_dir() and not (path/'status.txt').exists(): shutil.rmtree(path)
        if not any(root.iterdir()): root.rmdir()
        else: print(f'NG 作業先保持: {root}')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'NG 実行環境・作業先の不成立 ({type(exc).__name__})')
        raise SystemExit(1)
