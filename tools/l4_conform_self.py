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


def check_selected(mod, row, rom, work, exp, out):
    # checkの内部準備: 値は解釈・表示せず、全期待腕にちょうど対応する操作を選ぶ。
    with exp.open(newline='') as stream:
        ids = {r['arm'] for r in csv.DictReader(stream, delimiter='\t')}
    name = row[0]
    if name.startswith('memlimit'):
        catalog = mod.selection(int(name[-1]) if '_add' in name else None)
    elif name == 'pusing_add2':
        catalog = mod.selected2()
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
    if name == 'wrap':
        passed = mod.emit(out, records, selected)
    else:
        passed = (mod.emit2 if name=='pusing_add2' else mod.emit)(out, records, **options)
    if not passed: return 'NG'
    with KnownSink() as sink:
        agrees = mod.check(exp, out)
    return status(not agrees, sink.known)


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
            if name == 'pusing_add2': ma += '（selected2/emit2）'
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
    """別プロセス。標準出力は親で/dev/nullへ。結果は固定語だけ。"""
    name, tool, margs, cargs, _, _ = row
    mod = importlib.import_module(Path(tool).stem)
    out = work/'measured.tsv'
    exp = expected(row)
    known = False
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
                    return 'NG'
            with KnownSink() as sink:
                _, bad = mod.results_check(exp, paths)
            return status(bool(bad), sink.known)
        if name == 'out_output':
            rc = mod.measure(rom, False, work, out)
            with KnownSink() as sink:
                differs = mod.check(exp, out) if not rc else True
            return status(rc or differs, sink.known)
        records = (mod.measure(rom, False, mod.arms(), work) if name == 'input'
                   else mod.measure(rom, False, work))
        if not mod.emit(out, records):
            return 'NG'
        with KnownSink() as sink:
            checked = mod.check(exp, out)
        bad = checked[1]
        return status(bool(bad), bool(checked[2]) if len(checked)>2 else sink.known)
    if margs[:1] == ['integrated']:
        # 元のcheckが測定と照合を一体で行う。TMPDIRで作業先を外部へ固定。
        sys.argv = [tool, 'check', '--rom-dir', str(rom), '--expected', str(exp), *cargs]
        # KNOWNの出力だけを検出し、本文は保持しない。
        with KnownSink() as sink:
            rc = mod.main()
        return status(rc, sink.known)
    env = dict(os.environ)
    rc = run_silent([sys.executable, str(REPO/'tools'/tool), 'measure', '--rom-dir', str(rom),
                     '--work-dir', str(work), '--out', str(out), *margs], env)
    if rc:
        return 'NG'
    if name == 'paint':
        _, bad, known, _ = mod.check(exp, out)
        return status(bool(bad), bool(known))
    rc = run_silent([sys.executable, str(REPO/'tools'/tool), 'check', '--expected', str(exp),
                     '--measured', str(out), *cargs], env)
    return status(rc)


class KnownSink:
    """行頭の固定語だけ検知。画面本文や差分は蓄積しない。"""
    def __init__(self):
        self.known = False
        self.prefix = ''
    def write(self, value):
        for part in value.splitlines(keepends=True):
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
    value = result.read_text().strip() if result.exists() else 'NG'
    return value if not rc and value in ('OK', 'KNOWN') else 'NG'


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
                        return 'CACHED', time.monotonic()-start
                except (OSError, ValueError, AttributeError):
                    pass
            value = measure_one(row, rom, root/row[0])
            if entry and value in ('OK','KNOWN'):
                # 成功だけを原子的に記録。並行する別の本走とも途中状態を共有しない。
                with tempfile.NamedTemporaryFile(mode='w', dir=cache, delete=False) as f:
                    temp = Path(f.name)
                    json.dump(dict(key=key, status=value), f)
                try:
                    temp.replace(entry)
                finally:
                    temp.unlink(missing_ok=True)
            return value, time.monotonic()-start
        except Exception:
            return 'NG', time.monotonic()-start

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {row[0]: pool.submit(run, row) for row in selected}
        results = {name: future.result() for name, future in futures.items()}
    counts = dict(OK=0, NG=0, KNOWN=0, CACHED=0)
    for name, (value, seconds) in sorted(results.items()):
        counts[value] += 1
        print(f'{value} {name} {seconds:.1f}秒' +
              ('（測定・照合または前提条件の不成立）' if value=='NG' else ''), flush=True)
    print('集計 ' + ' / '.join(f'{k} {v}' for k,v in counts.items()))
    return int(counts['NG'] != 0)


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
        try:
            value = worker(row, args.rom, work, args.result)
        except Exception:
            value = 'NG'
        args.result.write_text(value+'\n')
        return int(value == 'NG')
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
    with tempfile.TemporaryDirectory(prefix='run-', dir=work) as td:
        root = Path(td); env = clean_env(root)
        rom = root/'rom'
        rc = run_silent([sys.executable, str(REPO/'src/build_main_rom.py'), str(rom),
                         '--work-dir', str(root/'asm')], env)
        if rc:
            print(f'NG 自作ROMビルド失敗 rc={rc}（前提・書込み・ビルド環境を確認）'); return 1
        return run_rows(selected, rom, root, args.j, args.no_cache)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'NG 実行環境・作業先の不成立 ({type(exc).__name__})')
        raise SystemExit(1)
