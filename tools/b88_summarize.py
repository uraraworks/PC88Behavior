#!/usr/bin/env python3
"""B88 の公開可能な集計。生レジスタ・RAM値・I/O値・内部PCを出力しない。"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from b88_arms import arms

REGS = ('SP', 'HL', 'DE', 'BC', 'F', 'A')
FDC = {2: 'READ TRACK', 3: 'SPECIFY', 4: 'SENSE DRIVE STATUS', 5: 'WRITE DATA',
       6: 'READ DATA', 7: 'RECALIBRATE', 8: 'SENSE INTERRUPT STATUS',
       9: 'WRITE DELETED DATA', 10: 'READ ID', 12: 'READ DELETED DATA',
       13: 'FORMAT TRACK', 15: 'SEEK', 17: 'SCAN EQUAL',
       25: 'SCAN LOW OR EQUAL', 29: 'SCAN HIGH OR EQUAL'}


def inputs(arm):
    v = arm['variant']
    return dict(zip(REGS, (0x7e00, 0x6300 if v == 'hl' else 0x6100,
                          0x6200 if v == 'de' else 0x6000, 2 if v == 'bc' else 1,
                          int(v == 'f'), int(v == 'a'))))


def read_capture(path):
    lines = path.read_text().splitlines()
    if not lines or lines[0] != 'B88 1' or lines[-1] != 'END':
        raise ValueError('計測記録不完全')
    counters, io, fdc, changes, values = {}, [], [], [], None
    for line in lines[1:-1]:
        fields = line.split()
        kind = fields[0]
        if kind in ('B', 'S', 'E', 'R') and len(fields) == 2 and kind not in counters:
            counters[kind] = int(fields[1])
        elif kind == 'V' and len(fields) == 6 and values is None:
            words = [int(x) for x in fields[1:]]
            if not all(0 <= x <= 65535 for x in words): raise ValueError('不正なレジスタ記録')
            values = dict(zip(REGS, words[:4] + [words[4] & 255, words[4] >> 8]))
        elif kind == 'I' and len(fields) == 4:
            direction, port, count = int(fields[1]), int(fields[2], 16), int(fields[3])
            if direction not in (0, 1) or not 0 <= port <= 255 or count <= 0: raise ValueError('不正なI/O記録')
            io.append({'方向': 'OUT' if direction else 'IN', 'ポート': f'{port:02X}', '件数': count})
        elif kind == 'C' and len(fields) == 3:
            command, count = map(int, fields[1:])
            if not 0 <= command < 32 or count <= 0: raise ValueError('不正なFDC記録')
            fdc.append({'種類': FDC.get(command, 'INVALID'), '件数': count})
        elif kind == 'W' and len(fields) == 4:
            addr, count, changed = int(fields[1], 16), int(fields[2]), int(fields[3])
            if not 0x4000 <= addr < 0x8000 or count <= 0 or changed not in (0, 1): raise ValueError('不正なRAM記録')
            changes.append((f'{addr:04X}', count, bool(changed)))
        else:
            raise ValueError('計測記録の形式不正')
    if set(counters) != {'B', 'S', 'E', 'R'} or any(v < 0 for v in counters.values()):
        raise ValueError('計測印の欠落')
    if bool(counters['E']) != (values is not None): raise ValueError('戻り記録不完全')
    return counters, io, fdc, changes, values


def read_main(path, labels):
    text = path.read_text()
    tail = re.findall(r'# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件', text)
    if len(tail) != 1 or int(tail[0][0]): raise ValueError('取りこぼし')
    rows = []
    for line in text.splitlines():
        m = re.fullmatch(r'\s*(\d+)\s+\d+\s+([0-9A-F]{4})\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s*', line)
        if m: rows.append(tuple(int(x, 10 if i == 0 else 16) for i, x in enumerate(m.groups())))
    if len(rows) != int(tail[0][1]) or [r[0] for r in rows] != list(range(1, len(rows)+1)):
        raise ValueError('イベント欠落')
    boots = sum(pc == labels['BOOT'] and addr == 0xcff0 for _, pc, addr, _ in rows)
    done = sum(pc == labels['DONE'] and addr == 0xcff1 for _, pc, addr, _ in rows)
    failed = any(addr == 0xcff2 for _, _, addr, _ in rows)
    results = [(addr, value) for _, pc, addr, value in rows if pc == labels['RECEIVE_RESULT'] + 3 and 0xcf00 <= addr < 0xcf0c]
    packet = bytes(v for _, v in results) if [a for a, _ in results] == list(range(0xcf00, 0xcf0c)) else None
    return boots, done, failed, packet


def summarize_run(directory, arm, input_values=None):
    missing = {'判定': '欠測', '戻り': '欠測', '理由': '記録不足・実行失敗'}
    try:
        status = json.loads((directory / 'status.json').read_text())
        if status != {'成功': True}: return missing, None
        labels = json.loads((directory / 'labels.json').read_text())['main']
        c, io, fdc, changes, values = read_capture(directory / 'capture')
        boots, done, failed, packet = read_main(directory / 'mem', labels)
        if boots != c['B']: raise ValueError('起動印の不一致')
    except (OSError, ValueError, KeyError, TypeError):
        return missing, None
    if not boots or not c['S']:
        return {'判定': '欠測', '戻り': '欠測', '理由': '入口未到達'}, None
    restarted = bool(c['R'] or boots > 1 or c['S'] > 1)
    returned = c['E'] == 1 and not restarted
    row = {'判定': '取得', '戻り': '確認' if returned else '戻らない',
           '理由': '戻り印' if returned else '再起動' if restarted else '時間上限',
           '再起動': restarted, '起動回数': boots, '開始回数': c['S'],
           'I/O': io, 'FDC': fdc,
           'RAM': {'比較終端': '戻り' if returned else '再起動' if restarted else '時間上限',
                   '変化番地': [a for a, _, changed in changes if changed],
                   '値変化回数': [{'番地': a, '件数': n} for a, n, _ in changes]},
           '呼出し直前SP': '入力から戻り先1語分減少' if arm['mode'] == 'jp' else '入力と一致',
           '結果搬送一致': None, '入力との一致': None}
    if returned:
        expected = inputs(arm) if input_values is None else input_values
        received = None
        if packet is not None and packet[:2] == bytes((expected['A'], 0xa5)):
            received = dict(zip(REGS, [int.from_bytes(packet[i:i+2], 'little') for i in (2, 4, 6, 8)] + [packet[10], packet[11]]))
        row['結果搬送一致'] = done == 1 and not failed and received == values
        if row['結果搬送一致']:
            row['入力との一致'] = {k: received[k] == expected[k] for k in REGS}
            return row, received
        row['判定'] = '欠測'
        row['理由'] = '結果搬送不一致'
    return row, None


def report(root):
    rows, values = {}, {}
    for arm in arms():
        name = arm['name']; runs, vals = [], []
        for repeat in (1, 2):
            path = root / 'raw' / name / str(repeat)
            try:
                row = json.loads((path / 'row.json').read_text())
                value = json.loads((path / 'values.tmp').read_text()) if (path / 'values.tmp').exists() else None
            except (OSError, ValueError):
                row, value = {'判定': '欠測', '戻り': '欠測', '理由': '未実行'}, None
            runs.append(row); vals.append(value)
        rows[name] = {'走': runs, '2走一致': runs[0] == runs[1] if all(x['判定'] == '取得' for x in runs) else None}
        values[name] = vals
    for arm in arms():
        name = arm['name']
        baseline = name.rsplit('-', 1)[0] + '-base' if arm['address'] is not None else 'negative'
        # mem_hl/mem_de はハイフンを含まないため同じ入口・入り方の base となる。
        rows[name]['基準腕との一致'] = [None if x is None or y is None else {k: x[k] == y[k] for k in REGS}
                                      for x, y in zip(values[name], values[baseline])]
        cached = root / 'raw' / name / 'comparison.json'
        if cached.exists() and not any((root / 'raw' / name / str(i) / 'values.tmp').exists() for i in (1, 2)):
            rows[name]['基準腕との一致'] = json.loads(cached.read_text())
    totals = Counter(x['戻り'] for row in rows.values() for x in row['走'])
    result = {'腕数': len(rows), '走数': 2 * len(rows),
              '集計': {k: totals[k] for k in ('確認', '戻らない', '欠測')}, '腕': rows}
    (root / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    report(args.out.resolve())


if __name__ == '__main__':
    main()
