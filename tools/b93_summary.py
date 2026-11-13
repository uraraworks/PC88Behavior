#!/usr/bin/env python3
"""B93 の外部記録を検証し、値や見出し本文を出さずに比較する。"""
import argparse
import json
import re
from b92_summary import outside

CPUS = ('main', 'sub')
VALUES = ('00', '01', '02', '03', '10', '40', '7F', '80', 'FF')
TL = re.compile(r'^(\d+)\s+\d+\s+([0-9A-F]{4})\s+(call|jump|int|ret|accept)\s+\d+$')
IO = re.compile(r'io (\d+) ([01]) ([01]) ([0-9A-F]{2}) ([0-9A-F]{4}) ([1-9][0-9]*)')


def timeline(path, frames):
    prev = 0
    with outside(path).open() as fp:
        for line in fp:
            line = line.rstrip('\n')
            m = TL.fullmatch(line)
            if not m or not prev <= int(m[1]) < frames:
                raise ValueError('境界記録の欠落または形式不正')
            prev = int(m[1])
            yield (m[2], m[3]), 1


def io_headers(path, cpu):
    with outside(path).open() as fp:
        for line in fp:
            m = IO.fullmatch(line.rstrip('\n'))
            if m and int(m[2]) == cpu:
                yield (m[3], m[4], m[5]), int(m[6])


def difference(a, b):
    """反復を展開せず、長さだけの違いも1始まりの件目で返す。"""
    a, b = iter(a), iter(b)
    x, y = next(a, None), next(b, None)
    offset = 1
    while x is not None and y is not None:
        if x[0] != y[0]:
            return offset
        take = min(x[1], y[1])
        offset += take
        x = next(a, None) if x[1] == take else (x[0], x[1] - take)
        y = next(b, None) if y[1] == take else (y[0], y[1] - take)
    return offset if x is not None or y is not None else None


def read_run(path, frames):
    p = outside(path)
    result = dict(path=p, frames=frames, entry=False, returned=False, interventions=0,
                  targets={a: None for a in ('3E0D', '3080')}, last=[None, None],
                  counts=[0, 0], max_gap=[0, 0], stop_snapshot=[None, None])
    state, next_frame, entry_frame = 'waiting', 0, None
    snapshot = None
    done = False
    with (p/'events').open() as fp:
        if fp.readline() != 'B93 2\n':
            raise ValueError('記録版不正')
        for raw in fp:
            line = raw.rstrip('\n')
            if done:
                raise ValueError('末尾以降の記録')
            f = line.split()
            if not f:
                raise ValueError('空の記録')
            tag = f[0]
            m = IO.fullmatch(line)
            if m:
                fr, cpu, _, _, _, count = m.groups()
                fr, cpu, count = int(fr), int(cpu), int(count)
                if fr != next_frame:
                    raise ValueError('I/Oフレーム不正')
                result['last'][cpu] = fr
                result['counts'][cpu] += count
                result['stop_snapshot'][cpu] = None
            elif tag == 'frame' and len(f) == 6:
                fr, *fields = map(int, f[1:])
                if (fr != next_frame or fr >= frames or any(x not in (0, 1, 2) for x in fields[:2]) or
                        any(not -1 <= x <= 255 for x in fields[2:])):
                    raise ValueError('フレーム記録不正')
                snapshot = {'フレーム': fr,
                            'CPU位置': dict(zip(CPUS, [('RAM', 'ROM', '未取得')[x] for x in fields[:2]])),
                            '待機ポート候補': dict(zip(CPUS, [f'{x:02X}' if x >= 0 else None for x in fields[2:]]))}
                for cpu in range(2):
                    last = result['last'][cpu]
                    gap = fr - last if last is not None else fr + 1
                    result['max_gap'][cpu] = max(result['max_gap'][cpu], gap)
                    if gap and result['stop_snapshot'][cpu] is None:
                        result['stop_snapshot'][cpu] = snapshot
                next_frame += 1
            elif tag == 'entry' and len(f) == 2 and state == 'waiting':
                entry_frame = int(f[1])
                if entry_frame != next_frame:
                    raise ValueError('入口フレーム不正')
                result['entry'] = True
                state = 'active'
            elif tag == 'exit' and len(f) == 3 and state == 'active':
                fr, returned = map(int, f[1:])
                if fr != next_frame or returned not in (0, 1) or fr < entry_frame or (returned and fr-entry_frame >= 30):
                    raise ValueError('帰還記録不正')
                result['returned'] = bool(returned)
                state = 'returned' if returned else 'timeout'
            elif line == 'intervention 1' and state == 'returned' and not result['interventions']:
                result['interventions'] = 1
                state = 'intervened'
            elif tag == 'hit' and len(f) == 3 and f[2] in result['targets']:
                fr = int(f[1])
                if fr != next_frame or result['targets'][f[2]] is not None:
                    raise ValueError('到達記録不正')
                result['targets'][f[2]] = fr
            elif tag == 'end' and len(f) == 8 and state != 'active':
                if list(map(int, f[1:7])) != [frames, int(result['entry']), int(result['returned']), result['interventions'], *result['counts']] or next_frame != frames:
                    raise ValueError('末尾記録不整合')
                result['timeline_expected'] = int(f[7])
                done = True
            else:
                raise ValueError('記録形式不正')
    if not done:
        raise ValueError('記録切断')
    result['final'] = snapshot
    result['timeline_count'] = sum(n for _, n in timeline(p/'timeline', frames))
    if result['timeline_count'] != result['timeline_expected']:
        raise ValueError('境界件数不一致')
    return result


def compare(a, b):
    return {'境界の初差異件目': difference(timeline(a['path']/'timeline', a['frames']), timeline(b['path']/'timeline', b['frames'])),
            'I_Oの初差異件目': {c: difference(io_headers(a['path']/'events', i), io_headers(b['path']/'events', i)) for i, c in enumerate(CPUS)}}


def describe(run, expected):
    if run is None:
        return {'状態': '欠測'}
    valid = run['entry'] and run['returned'] and run['interventions'] == expected
    return {'状態': '有効' if valid else '対象未到達・未帰還または介入不成立',
            '入口到達': run['entry'], '帰還': run['returned'], '介入回数': run['interventions'],
            '指定フレーム数': run['frames'], '任意fetch到達': {a: f is not None for a, f in run['targets'].items()},
            '初到達フレーム': run['targets'], '境界件数': run['timeline_count'],
            'I_O': {c: {'件数': run['counts'][i], '最終フレーム': run['last'][i],
                       '最終フレームにも発生': run['last'][i] == run['frames']-1,
                       '状態': ('全区間I/Oなし' if run['last'][i] is None else '最終フレームまでI/O継続' if run['last'][i] == run['frames']-1 else '末尾でI/O無通信'),
                       '末尾無通信フレーム数': run['frames']-1-run['last'][i] if run['last'][i] is not None else run['frames'],
                       '最大無通信フレーム数': run['max_gap'][i],
                       '末尾無通信開始時': run['stop_snapshot'][i]} for i, c in enumerate(CPUS)},
            '終了時': run['final']}


def summarize(base, runs):
    if len(base) != 2 or any(k not in VALUES for k in runs):
        raise ValueError('腕の形式不正')
    comparison = compare(*base) if all(base) else None
    stable = (comparison['境界の初差異件目'] is None and
              all(x is None for x in comparison['I_Oの初差異件目'].values())) if comparison else None
    bases = [describe(b, 0) for b in base]
    result = {'基準2回一致': stable, '基準2回比較': comparison, '基準': bases,
              '判定規則': 'フレームは0始まり。I/O無通信は処理停止を断定しない。待機ポート候補は当該フレームに同一PC/portのINのみが2回以上。ポーリングでもI/O継続となる。', '腕': {}}
    for name in VALUES:
        run = runs.get(name)
        row = describe(run, 1)
        row['介入効果の比較可能'] = bool(stable and all(b['状態'] == '有効' for b in bases) and row['状態'] == '有効')
        if run is not None and base[0] is not None:
            row.update(compare(base[0], run))
        result['腕'][name] = row
    return result


def collect(raw, frames):
    runs = {}
    for name in ('base1', 'base2', *VALUES):
        p = outside(raw)/name
        try:
            if (p/'status').read_text() != '0\n':
                raise ValueError('実行失敗')
            runs[name] = read_run(p, frames)
        except (OSError, ValueError):
            runs[name] = None
    return summarize([runs.pop('base1'), runs.pop('base2')], runs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', help='b93_run.sh の出力ディレクトリ')
    args = parser.parse_args()
    try:
        out = outside(args.run)
        config = json.loads((out/'config.json').read_text())
        frames = config['frames']
        if type(frames) is not int or not 1 <= frames <= 10000000:
            raise ValueError('設定不正')
        report = collect(out/'raw', frames)
        (out/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        print('B93: 値なし集計完了（欠測は集計内に明示）')
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, 'B93: 集計失敗\n')


if __name__ == '__main__':
    main()
