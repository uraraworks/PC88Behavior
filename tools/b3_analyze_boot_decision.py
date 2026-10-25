#!/usr/bin/env python3
"""tools/b3_analyze_boot_decision.py — B3 事前登録ノート第5節 R0・R1・R4 の解析器。

読むのは iolog の seq・frame・cpu・kind・port・value だけ。発行元PC欄は
どこにも保持しない（分岐点はポートの並びで決める）。データポート FB〜FD の
value は読み捨てる（候補探索にも出力にも使わない）。出力は白リストの行のみ:
ポート・方向・ビット・0/1・件数・フレーム・分類。バイト値そのものは出さない。
エラーメッセージにもログ本文は載せない（行番号のみ）。

使い方:
  b3_analyze_boot_decision.py --run LABEL:ARM:IOLOG ... \
      [--baseline-a N] [--baseline-b D1] [--track PORT:BIT ...]
"""
import argparse
import gzip
import os
import sys

DATA_PORTS = (0xFB, 0xFC, 0xFD)
# 検査用の故障注入。立てると pc 欄とデータポート値を出力へ漏らす（陰性対照専用）。
FAULT_LEAK = os.environ.get('B3_ANALYZER_FAULT_LEAK') == '1'


def die(msg):
    sys.stderr.write('error: ' + msg + '\n')
    sys.exit(2)


class Run:
    def __init__(self, label, arm):
        self.label, self.arm = label, arm
        self.k1_port = None
        self.k1_frame = None
        self.k2 = 0
        self.k3 = 0
        # main の IN: (frame, port, value, before) ; データポートは含めない
        self.ins = []
        self.leak = []


def open_text(path):
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace')
    return open(path, 'rt', encoding='utf-8', errors='replace')


def parse(path, label, arm):
    run = Run(label, arm)
    try:
        fh = open_text(path)
    except OSError:
        die('cannot open run %s' % label)
    n_main = 0
    with fh:
        for n, line in enumerate(fh, 1):
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            f = line.split()
            # seq clock frame cpu kind port value pc（q88h_iolog の8欄）。
            # 使うのは seq・frame・cpu・kind・port・value だけで、pc は保持しない
            if len(f) != 8 or not f[0].isdigit() or not f[1].isdigit() \
                    or f[3] not in ('main', 'sub') or f[4] not in ('IN', 'OUT'):
                continue  # ヘッダ行（core: 等）
            try:
                frame = int(f[2])
                port = int(f[5], 16)
                if f[6] != '--':
                    value = int(f[6], 16)
                else:
                    value = None
            except ValueError:
                die('bad line %d in run %s' % (n, label))
            cpu, kind = f[3], f[4]
            if FAULT_LEAK and len(f) > 7 and len(run.leak) < 4:
                run.leak.append((f[7], f[6]))
            if cpu == 'sub':
                run.k3 += 1
                continue
            n_main += 1
            if 0xFC <= port <= 0xFF:
                run.k2 += 1
            if kind == 'OUT' and run.k1_port is None and port in (0xC1, 0xFF):
                run.k1_port, run.k1_frame = port, frame
                continue
            if kind == 'IN' and port not in DATA_PORTS and value is not None:
                run.ins.append((frame, port, value, run.k1_port is None))
    if n_main == 0:
        # 形式違い（欄の数のずれ等）で全行を読み飛ばすと、0件が「何も起きなかった」に化ける
        die('run %s: main のイベントを1件も読めなかった（形式を確認）' % label)
    return run


def classify(r):
    if r.k1_port == 0xC1 and r.k2 == 0 and r.k3 == 0:
        return 'ROM'
    if r.k1_port == 0xFF and r.k2 > 0 and r.k3 > 0:
        return 'DISK'
    return 'MIXED'


def bitsets(run, before_only):
    """(port,bit) -> (値の集合, 件数)"""
    d = {}
    for frame, port, value, before in run.ins:
        if before_only and not before:
            continue
        for b in range(8):
            s, c = d.get((port, b), (set(), 0))
            s.add((value >> b) & 1)
            d[(port, b)] = (s, c + 1)
    return d


def first_frames(run):
    ff = {}
    for frame, port, value, before in run.ins:
        if before and port not in ff:
            ff[port] = frame
    return ff


def fmt(s):
    return ','.join(str(x) for x in sorted(s)) if s else '-'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', action='append', default=[], required=True)
    ap.add_argument('--baseline-a', default='N')
    ap.add_argument('--baseline-b', default='D1')
    ap.add_argument('--track', action='append', default=[])
    a = ap.parse_args()

    runs = []
    for spec in a.run:
        p = spec.split(':', 2)
        if len(p) != 3:
            die('bad --run spec')
        runs.append(parse(p[2], p[0], p[1]))

    tracks = []
    for t in a.track:
        try:
            ps, bs = t.split(':')
            port, bit = int(ps, 16), int(bs)
        except ValueError:
            die('bad --track spec')
        if port in DATA_PORTS or not 0 <= bit <= 7:
            die('track not allowed')
        tracks.append((port, bit))

    print('== R0 ==')
    for r in runs:
        k1 = 'none' if r.k1_port is None else '%02X' % r.k1_port
        kf = 'none' if r.k1_frame is None else str(r.k1_frame)
        print('R0\trun=%s\tarm=%s\tK1_port=%s\tbranch_frame=%s\tK2=%d\tK3=%d\tclass=%s'
              % (r.label, r.arm, k1, kf, r.k2, r.k3, classify(r)))

    print('== R1 ==')
    A = [r for r in runs if r.arm == a.baseline_a]
    B = [r for r in runs if r.arm == a.baseline_b]
    if not A or not B:
        print('R1\tskipped: baseline arm has no runs')
    else:
        sa = [bitsets(r, True) for r in A]
        sb = [bitsets(r, True) for r in B]
        allr = A + B
        sall = sa + sb
        keys = set()
        for d in sall:
            keys |= set(d)
        cand = []
        same = shaky = other = 0
        for key in sorted(keys):
            present = all(key in d for d in sall)
            vals_a = [d[key][0] for d in sa if key in d]
            vals_b = [d[key][0] for d in sb if key in d]
            if present and all(len(s) == 1 for s in vals_a + vals_b):
                va, vb = vals_a[0], vals_b[0]
                if all(s == va for s in vals_a) and all(s == vb for s in vals_b):
                    if va != vb:
                        cand.append((key, next(iter(va)), next(iter(vb))))
                    else:
                        same += 1
                    continue
            if any(len(s) > 1 for s in vals_a + vals_b):
                shaky += 1
            else:
                other += 1
        print('R1\tcandidates=%d' % len(cand))
        ffs = [first_frames(r) for r in allr]
        for (port, bit), va, vb in cand:
            reads = ' '.join('%s:%d' % (r.label, d[(port, bit)][1])
                             for r, d in zip(allr, sall))
            frs = ' '.join('%s:%d' % (r.label, f[port]) for r, f in zip(allr, ffs))
            print('R1\tcandidate\tport=%02X\tbit=%d\ta=%d\tb=%d\treads_before=[%s]\tfirst_frame=[%s]'
                  % (port, bit, va, vb, reads, frs))
        print('R1\tnon_candidates\tsame=%d\tvaries_within_arm=%d\tother=%d' % (same, shaky, other))

    if tracks:
        print('== R4 ==')
        for r in runs:
            bs, bw = bitsets(r, True), bitsets(r, False)
            for port, bit in tracks:
                sb_, cb = bs.get((port, bit), (set(), 0))
                sw_, cw = bw.get((port, bit), (set(), 0))
                print('R4\trun=%s\tarm=%s\tport=%02X\tbit=%d\tbefore=%s\tbefore_reads=%d\twhole=%s\twhole_reads=%d'
                      % (r.label, r.arm, port, bit, fmt(sb_), cb, fmt(sw_), cw))

    if FAULT_LEAK:
        for r in runs:
            for pc, v in r.leak:
                print('LEAK\tpc=%s\tvalue=%s' % (pc, v))


if __name__ == '__main__':
    main()
