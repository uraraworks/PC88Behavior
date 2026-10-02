#!/usr/bin/env python3
"""m6f-k: 合成後像による全候補、G8/G10/G11、起動前凍結の陰性対照。"""
from __future__ import annotations
import itertools
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_m6fk_disk as check
import m6fk_judge as judge
import m6fk_read as reader
import m6fk_script as script
from make_m6fk_disk import MEDIA, build, offsets
from m6fk_measure import default_core, preflight
from m6fh_body import Image


def require(ok: bool, name: str) -> None:
    if not ok:
        raise AssertionError(name)


def lines(name):
    if name == 'other':
        return [dict(physical_row=0, char_count=1, sha256='0'*64)]
    return [dict(physical_row=r, char_count=c, sha256=s) for r, c, s in judge.predictions()[name]]


def fat(data, unit, value):
    off = offsets(data)
    for r in (14, 15, 16):
        data[off[(18, 1, r)]+unit] = value


def record(data, slot):
    return offsets(data)[(18, 1, slot//16+1)]+slot%16*16


def rename(data, slot=0):
    p = record(data, slot)
    data[p:p+9] = b'qsd'.ljust(9, b' ')


def delete(data, slot=1, mode='first_byte_00_rest_kept'):
    p = record(data, slot)
    if mode == 'first_byte_00_rest_kept':
        data[p] = 0
    elif mode == 'all_ff':
        data[p:p+16] = b'\xff'*16
    else:
        data[p+11] = 0x42


def classify(arm, data, screen, base=None):
    before, after, changes = reader.compare(build(script.MEDIA[arm]) if base is None else base, data, arm)
    return judge.classify(arm, before, after, lines(screen), changes)


def expect(arm, data, screen, candidate, base=None):
    result = classify(arm, data, screen, base)
    require(result['candidates'] == [candidate], '候補取り違え_'+arm+'_'+candidate)
    require(judge.combine({arm: [result, result]})['judgments'][arm] == candidate, '2走正例')
    return candidate


def judgments():
    covered = {arm: set() for arm in script.ARMS}
    for entry, units, screen in itertools.product(
            ('first_byte_00_rest_kept', 'all_ff', 'other'),
            ('units_freed', 'units_kept', 'other'), ('ok_line', 'no_line', 'other')):
        data = bytearray(build('KM'))
        delete(data, mode=entry)
        if units == 'units_freed':
            for unit in reader.units(reader.inspect(build('KM'), 'K-1'), 1):
                fat(data, unit, 255)
        elif units == 'other':
            fat(data, 20, 0xc1)
        candidate = '/'.join((entry, units, screen))
        covered['K-1'].add(expect('K-1', data, screen, candidate))
    # 固定単位20/21を判定器が前提にせず、元の鎖からたどること。
    moved = bytearray(build('KM'))
    moved[record(moved, 1)+10] = 40
    fat(moved, 20, 255); fat(moved, 21, 255)
    fat(moved, 40, 41); fat(moved, 41, 0xc1)
    data = bytearray(moved); delete(data); fat(data, 40, 255); fat(data, 41, 255)
    expect('K-1', data, 'ok_line', 'first_byte_00_rest_kept/units_freed/ok_line', moved)
    for entry, screen in itertools.product(
            ('same_slot_name_only', 'same_slot_other_fields_changed', 'new_slot', 'other'),
            ('ok_line', 'no_line', 'other')):
        data = bytearray(build('KM'))
        if entry.startswith('same_slot'):
            rename(data)
            if entry == 'same_slot_other_fields_changed':
                data[record(data, 0)+11] = 0x42
        elif entry == 'new_slot':
            data[record(data, 3):record(data, 3)+16] = data[record(data, 0):record(data, 0)+16]
            rename(data, 3); delete(data, 0)
        candidate = '/'.join((entry, screen))
        covered['N-1'].add(expect('N-1', data, screen, candidate))
    error_ids = [x for x in judge.predictions() if x.startswith('error_')]
    for arm in ('K-2', 'K-3', 'N-2', 'N-3', 'N-4'):
        for screen in error_ids + ['ok_line', 'no_line', 'other']:
            candidate = screen if screen.startswith('error_') else (
                'no_error_media_unchanged' if screen != 'other' else 'other')
            covered[arm].add(expect(arm, build(script.MEDIA[arm]), screen, candidate))
        changed = bytearray(build(script.MEDIA[arm])); rename(changed)
        expect(arm, changed, 'error_53', 'other')
    # 追補1: 印のある媒体での改名。画面が no_line で形が N-1 と同じときだけ受理する（陰性対照2種）。
    renamed_kp = bytearray(build('KP')); rename(renamed_kp)
    covered['N-4'].add(expect('N-4', renamed_kp, 'no_line', 'renamed_ignoring_protect'))
    expect('N-4', renamed_kp, 'ok_line', 'other')
    widened = bytearray(renamed_kp); widened[record(widened, 0)+11] = 0x42
    expect('N-4', widened, 'no_line', 'other')
    for arm in ('K-4', 'N-6'):
        data = bytearray(build('KM'))
        if arm == 'K-4':
            delete(data, 2); fat(data, 30, 255)
        else:
            rename(data, 2)
        for screen in ('ok_line', 'no_line'):
            covered[arm].add(expect(arm, data, screen, 'case_insensitive'))
        covered[arm].add(expect(arm, build('KM'), 'error_53', 'error_53_unchanged'))
        covered[arm].add(expect(arm, build('KM'), 'ok_line', 'other'))
    data = bytearray(build('KM')); rename(data)
    covered['N-5'].add(expect('N-5', data, 'ok_line', 'renamed_on_drive2'))
    for screen in error_ids:
        covered['N-5'].add(expect('N-5', build('KM'), screen, screen))
    covered['N-5'].add(expect('N-5', build('KM'), 'no_line', 'other'))
    require(covered == {k: set(v) for k, v in judge.candidate_ids().items()}, '全候補網羅')
    for runs in ([dict(candidates=[])]*2, [dict(candidates=['a', 'b'])]*2,
                 [dict(candidates=['a']), dict(candidates=['b'])],
                 [dict(candidates=['a'], detail=1), dict(candidates=['a'], detail=2)], []):
        require(judge.combine({'K-1': runs})['judgments']['K-1'] == 'inconclusive_K-1', '0件複数不一致')
    require(len(judge.predictions()) == len(set(judge.predictions().values())), '署名一意')
    # エラー本文の派生形を誤って既知エラーと分類しない。
    number = 53
    question = [dict(zip(('physical_row', 'char_count', 'sha256'), judge.signed(0, '?'+judge.errors()[number])))]
    require(judge.match_screen(question) == [], '疑問符陰性対照')


def disk_tests(tmp):
    preflight(HERE/'m6fk_frozen.tsv', tmp/'unused')
    original = build('KM')
    for media in MEDIA:
        require(check.inspect(build(media), media) == [], 'G9正例')
    off = offsets(original)
    def broken(name, edit, expected):
        data = bytearray(original); edit(data)
        require(check.inspect(data, 'KM') == expected, 'G9陰性_'+name)
    broken('name', lambda b: b.__setitem__(record(b, 0), ord('X')), ['entry_name'])
    broken('type', lambda b: b.__setitem__(record(b, 0)+9, 128), ['file_type'])
    broken('unit', lambda b: b.__setitem__(record(b, 0)+10, 11), ['entry_first_unit'])
    broken('entry_reserved', lambda b: b.__setitem__(record(b, 0)+11, 0), ['entry_reserved'])
    broken('unused', lambda b: b.__setitem__(record(b, 3), 0), ['first_unused'])
    broken('marker', lambda b: b.__setitem__(off[(18, 1, 13)], 16), ['write_marker'])
    broken('copies', lambda b: b.__setitem__(off[(18, 1, 15)]+10, 255), ['fat_copies'])
    broken('shape', lambda b: b.__setitem__(28, b[28]^1), ['d88_shape'])
    for unit, value, failure in ((74, 255, 'reserved_units'), (20, 0xc1, 'chain'),
                                  (21, 0xc2, 'terminal'), (11, 0xc1, 'fat_free')):
        broken(failure, lambda b: fat(b, unit, value), [failure])
    # 合成した媒体だけでASCII形式と9セクタ以上の本体を独立に確認。
    image = Image(original)
    bodies = []
    for chain in ([10], [20, 21], [30]):
        parts = []
        for unit in chain:
            value = image.sector_prefix((18, 1, 14), 160)[unit]
            count = 8 if value < 160 else value-0xc0
            for sub in range(count):
                linear = unit*8+sub
                parts.append(bytes(image.sector(linear//32, (linear//16)%2, linear%16+1)))
        payload = b''.join(parts).split(b'\x1a', 1)[0]
        require(b'\x1a' in b''.join(parts) and payload.endswith(b'\r\n'), '合成本体2.6')
        bodies.append(payload)
    require(bodies[0] == b'10 PRINT 1\r\n' and bodies[2] == b'10 PRINT 3\r\n' and
            len(bodies[1]) > 8*256 and len(bodies[1]) < 9*256 and
            all(line.split(b' ', 1)[0].isdigit() for line in bodies[1].split(b'\r\n')[:-1]), '合成媒体本体')
    # G8: 読み取りAPIを計測し、最大159を実際に確かめる。
    touched = []
    orig_prefix = Image.sector_prefix
    def audited(image, coord, limit):
        if coord in ((18, 1, 14), (18, 1, 15), (18, 1, 16)):
            touched.append(limit-1)
            require(limit <= 160, 'G8読取上限')
        return orig_prefix(image, coord, limit)
    marked = bytearray(original)
    sentinel = b'LEAK_SENTINEL_K1'
    for r in (14, 15, 16):
        marked[off[(18, 1, r)]+160:off[(18, 1, r)]+160+len(sentinel)] = sentinel
    with patch.object(Image, 'sector_prefix', audited):
        before, after, changes = reader.compare(original, marked, 'K-1')
        require(check.inspect(marked, 'KM') == [], 'G8独立検査')
    require(max(touched) == 159 and before == after and changes['media_unchanged'], 'G8値未参照')
    # G10: 未配置枠・本体への目印は内部結果、CLI、判定のどれにも出ない。
    marked[record(marked, 191):record(marked, 191)+16] = sentinel
    body_coord = (2, 1, 1)
    marked[off[body_coord]:off[body_coord]+len(sentinel)] = sentinel
    before, after, changes = reader.compare(original, marked, 'K-1')
    safe = reader.safe_result(before, after, changes)
    require(not changes['media_unchanged'], 'G10変化真偽')
    require(next(x for x in safe['unplaced_slots'] if x['position'] == 191)['changed'], 'G10枠位置')
    require(next(x for x in safe['body_sectors'] if x['position'] == list(body_coord))['changed'], 'G10本体位置')
    for key in ('unplaced_slots', 'body_sectors', 'marker_sectors'):
        require(all(set(x) == {'position', 'changed'} and isinstance(x['changed'], bool) for x in safe[key]), 'G10値出力経路なし')
    require(changes['_renamed_slots'] == [], 'G10任意枠を新名と誤認しない')
    require(sentinel.decode() not in json.dumps(safe), 'G10直接出力陰性')
    deleted_marked = bytearray(marked); delete(deleted_marked, 0)
    expect('N-1', deleted_marked, 'ok_line', 'other/ok_line')
    # 判定器へも値のない観測だけを渡す。
    observation = judge.classify('K-1', before, after, lines('ok_line'), changes)
    require(observation['candidates'] == ['other/units_kept/ok_line'], 'G10判定陰性')
    old_path, new_path = tmp/'old.d88', tmp/'new.d88'
    old_path.write_bytes(original); new_path.write_bytes(marked)
    proc = subprocess.run([sys.executable, str(HERE/'m6fk_read.py'), '--image', str(new_path),
                           '--before', str(old_path), '--arm', 'K-1'], capture_output=True)
    require(proc.returncode == 0 and json.loads(proc.stdout) == safe and
            sentinel not in proc.stdout+proc.stderr, 'G10 CLI陰性対照')


FAKE = r'''#!/usr/bin/env python3
import hashlib,os,pathlib,sys
sys.path.insert(0,str(pathlib.Path(os.environ['M6FK_TEST_REPO'])/'tools'))
import m6fk_judge as j
from make_m6fk_disk import offsets
a=sys.argv[1:]
def value(flag): return a[a.index(flag)+1]
def many(flag): return [a[i+1] for i,x in enumerate(a[:-1]) if x==flag]
with open(os.environ['M6FK_TEST_COUNT'],'a') as f: f.write('1\n')
arm=pathlib.Path(value('--out')).parent.name.split('-r')[0]
assert '--screen-signature-only' in a
assert value('--frames')=='8600'
assert many('--type')[-1]=='rem q6kready\\n'
p=pathlib.Path(value('--disk2')); data=bytearray(p.read_bytes()); off=offsets(data)
def fat(unit,n):
 for r in (14,15,16): data[off[(18,1,r)]+unit]=n
def rename(slot):
 start=off[(18,1,1)]+slot*16
 data[start:start+9]=b'qsd'.ljust(9,b' ')
choice='ok_line'
if arm=='K-1': data[off[(18,1,1)]+16]=0; fat(20,255); fat(21,255)
elif arm=='K-2': choice='error_53'
elif arm=='K-3': choice='error_61'
elif arm=='K-4': choice='error_53'
elif arm in ('N-1','N-5'): rename(0)
elif arm=='N-2': choice='error_58'
elif arm=='N-3': choice='error_53'
elif arm=='N-4': choice='error_61'
elif arm=='N-6': rename(2)
if os.environ.get('M6FK_TEST_G11'): data[28]^=1
if os.environ.get('M6FK_TEST_REF_CHANGED'):
 ref=pathlib.Path(value('--disk')); ref.write_bytes(b'CHANGED')
p.write_bytes(data)
def signed(row,s): return row,len(s),hashlib.sha256(f'{row}\t{s}\n'.encode()).hexdigest()
fkey=signed(19,'FKEY')
def write(name,rows):
 rows=sorted(rows)
 out.write(f'snapshot_id\t{name}\nphysical_row\tchar_count\tsha256\n')
 for row,count,digest in rows: out.write(f'{row}\t{count}\t{digest}\n')
 whole=hashlib.sha256(''.join(f'{r}\t{c}\t{s}\n' for r,c,s in rows).encode()).hexdigest()
 out.write(f'line_count\t{len(rows)}\nchar_count\t{sum(x[1] for x in rows)}\nsha256\t{whole}\n')
with pathlib.Path(value('--out')).open('w') as out:
 for name in [x.split(':')[0] for x in many('--screen-signature-at')]:
  if name=='baseline': rows=[signed(0,'BASELINE'),fkey]
  elif name=='ready':
   rows=[signed(2,'rem q6kready'),fkey]
   if not os.environ.get('M6FK_TEST_G11'): rows.append(signed(3,'Ok'))
  else:
   current='no_line' if os.environ.get('M6FK_TEST_DIFFER') and '-r2' in str(p) else choice
   rows=list(j.predictions()[current])+[signed(1,'LEAK_SENTINEL'),fkey]
  write(name,rows)
pathlib.Path(value('--io-log')).write_text('synthetic\n')
'''


def driver_tests(tmp):
    fake = tmp/'fake.py'; fake.write_text(FAKE); fake.chmod(0o755)
    (tmp/'rom').mkdir(); (tmp/'ref').mkdir()
    (tmp/'ref'/'N88_FE.D88').write_bytes(b'SYNTHETIC')
    count = tmp/'count'
    base = {**os.environ, 'M6FK_TEST_MODE': '1', 'M6FK_FRONTEND': str(fake),
            'M6FK_TEST_ROM_DIR': str(tmp/'rom'), 'M6FK_TEST_DISK_DIR': str(tmp/'ref'),
            'M6FK_TEST_CORE': 'synthetic', 'M6FK_TEST_REPO': str(HERE.parent),
            'M6FK_TEST_COUNT': str(count)}
    def run(label, extra=None, options=()):
        count.write_text('')
        proc = subprocess.run(['bash', str(HERE/'measure_m6fk.sh'), '--work', str(tmp/label), *options],
                              env={**base, **(extra or {})}, capture_output=True)
        return proc, len(count.read_text().splitlines())
    good, n = run('good')
    require(good.returncode == 0 and n == 20, '偽フロントエンド20走')
    result = json.loads((tmp/'good'/'result.json').read_bytes())
    expected = {'K-1': 'first_byte_00_rest_kept/units_freed/ok_line', 'K-2': 'error_53',
                'K-3': 'error_61', 'K-4': 'error_53_unchanged', 'N-1': 'same_slot_name_only/ok_line',
                'N-2': 'error_58', 'N-3': 'error_53', 'N-4': 'error_61',
                'N-5': 'renamed_on_drive2', 'N-6': 'case_insensitive'}
    require(result['judgment']['judgments'] == expected, '全腕2走判定')
    require(b'LEAK_SENTINEL' not in (tmp/'good'/'result.json').read_bytes()+good.stdout+good.stderr, '画面漏えい陰性')
    require(not list((tmp/'good').glob('*.d88')), '測定後像削除')
    subset, n = run('subset', options=('--arms', 'K-1,N-1'))
    require(subset.returncode == 0 and n == 4, '部分腕2走')
    differs, n = run('differs', {'M6FK_TEST_DIFFER': '1'}, ('--arms', 'K-1'))
    require(differs.returncode == 0 and n == 2 and json.loads((tmp/'differs'/'result.json').read_bytes())[
        'judgment']['judgments']['K-1'] == 'inconclusive_K-1', '2走不一致 inconclusive')
    stopped, n = run('g11', {'M6FK_TEST_G11': '1'}, ('--arms', 'K-1'))
    require(stopped.returncode != 0 and n == 1 and json.loads(stopped.stdout)['reason'] == 'G11', 'G11媒体読取前停止')
    stopped, n = run('refchanged', {'M6FK_TEST_REF_CHANGED': '1'}, ('--arms', 'K-1'))
    require(stopped.returncode != 0 and n == 1 and json.loads(stopped.stdout)['reason'] == 'G5', '参照媒体不変')
    for key, extra, options in (
            ('duplicate', {}, ('--arms', 'K-1,K-1')),
            ('uppercase', {'M6FK_TEST_UPPERCASE': '1'}, ())):
        proc, n = run(key, extra, options)
        require(proc.returncode != 0 and n == 0, '起動0_'+key)
    frozen = (HERE/'m6fk_frozen.tsv').read_text()
    for index, row in enumerate(frozen.splitlines()):
        key = row.split('\t')[0]
        bad = tmp/'bad.tsv'; bad.write_text(frozen.replace(key+'\t', key+'\t0', 1))
        proc, n = run('frozen'+str(index), {'M6FK_TEST_FROZEN': str(bad)})
        require(proc.returncode != 0 and n == 0 and json.loads(proc.stdout)['reason'] == 'G3', '凍結破壊起動0_'+key)
    proc, n = run('internal', options=('--result', str(HERE.parent/'tmp'/'m6fk-forbidden.json')))
    require(proc.returncode != 0 and n == 0 and json.loads(proc.stdout)['reason'] == 'output_inside_repository', '出力先関門')
    fixture = tmp/'fixture'; (fixture/'tools').mkdir(parents=True)
    (fixture/'tools'/'lib_l3_measure.sh').write_bytes((HERE/'lib_l3_measure.sh').read_bytes())
    vendor = fixture.parent/'vendor'/'quasi88-libretro'; vendor.mkdir(parents=True)
    core = vendor/'quasi88_libretro.synthetic'; core.touch()
    require(default_core(fixture) == str(core), 'コア探索共通規則')


def main():
    try:
        with tempfile.TemporaryDirectory(prefix='m6fk-selftest-') as value:
            tmp = pathlib.Path(value)
            disk_tests(tmp); judgments()
            if '--preflight' not in sys.argv:
                driver_tests(tmp)
        print('OK m6f-k: 全候補・2走一致・G8/G9/G10/G11・凍結破壊起動0・偽フロントエンド')
        return 0
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
        # 合成器具の固定ラベルだけ。入力媒体の値は含めない。
        print('NG m6f-k: '+type(exc).__name__+':'+str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
