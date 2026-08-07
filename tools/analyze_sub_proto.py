#!/usr/bin/env python3
"""PC88Behavior: メイン/サブCPU間 通信窓口(ポートF3〜FF)の外部観測解析。

入力は measurements/ 配下の *.iolog.txt / *.intlog.txt。
リポジトリ内に絶対パスを焼き込まない — すべて引数で受け取る。

出力する4つの観測:
  Q1 データ経路の実証: (OUTポート -> INポート) ペアの値一致率・順序判定
  Q2 ステータスビットの所在: (cpu, INポート) ごとのビット別 定数/変化 分類
  Q3 割り込み源: 割り込み受理点の直前N件I/Oイベントの集計
  Q4 反復単位: サブの (kind,port) 記号列のn-gram頻出パターン

このスクリプトは採取済みログのみを読む。公式ROMのバイト列・逆アセンブル
結果には一切触れない。

再実行方法:
    python3 tools/analyze_sub_proto.py \
        --iolog measurements/m6-sub-d0-boot.iolog.txt \
        --intlog measurements/m6-sub-d0-boot.intlog.txt \
        --out measurements/m6-sub-proto-d0-boot.txt
"""
from __future__ import annotations

import argparse
import bisect
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IoEvent:
    seq: int
    frame: int
    cpu: str
    kind: str  # "IN" / "OUT"
    port: str  # 4桁hex文字列 (例 "00F8")
    value: int
    pc: str


@dataclass
class IntEvent:
    seq: int
    frame: int
    cpu: str
    im: int
    level: int
    ret_pc: str
    handler_pc: str


IO_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{4})\s*$"
)
INT_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(main|sub)\s+(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s*$"
)


def parse_iolog(path: Path) -> dict[str, list[IoEvent]]:
    """cpu -> events (seq昇順のまま)"""
    events: dict[str, list[IoEvent]] = {"main": [], "sub": []}
    cur_cpu = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("# main"):
                cur_cpu = "main"
                continue
            if line.startswith("# sub"):
                cur_cpu = "sub"
                continue
            if line.startswith("#") or not line.strip():
                continue
            m = IO_ROW_RE.match(line)
            if not m:
                continue
            seq, frame, cpu, kind, port, value, pc = m.groups()
            events[cpu].append(
                IoEvent(int(seq), int(frame), cpu, kind, port.upper(), int(value, 16), pc.upper())
            )
    return events


def parse_intlog(path: Path) -> dict[str, list[IntEvent]]:
    events: dict[str, list[IntEvent]] = {"main": [], "sub": []}
    cur_cpu = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("# main"):
                cur_cpu = "main"
                continue
            if line.startswith("# sub"):
                cur_cpu = "sub"
                continue
            if line.startswith("#") or not line.strip():
                continue
            m = INT_ROW_RE.match(line)
            if not m:
                continue
            seq, frame, cpu, im, level, ret_pc, handler_pc = m.groups()
            events[cpu].append(
                IntEvent(int(seq), int(frame), cpu, int(im), int(level), ret_pc.upper(), handler_pc.upper())
            )
    return events


# サブが触れるポート集合(タスクで明示された範囲)。F3-FFの範囲だが、
# 実際に出現するのは観測されたものだけを使う(決め打ちしない)。
COMM_WINDOW_LO = 0x00F0
COMM_WINDOW_HI = 0x00FF
MIN_SAMPLE = 10  # これ未満のペアはたまたま値が揃っただけの可能性が高く除外


def _in_comm_window(port: str) -> bool:
    v = int(port, 16)
    return COMM_WINDOW_LO <= v <= COMM_WINDOW_HI


def analyze_q1_data_path(io: dict[str, list[IoEvent]], out) -> None:
    print("## Q1 データ経路の実証: (OUTポート -> INポート) 値一致率・順序判定", file=out)
    print(
        f"  (通信窓口として指定された ${COMM_WINDOW_LO:04X}-${COMM_WINDOW_HI:04X} の"
        f" ポートのみを対象にする。範囲外はCRTC/FDC等の無関係なハードウェアポートで"
        f" ノイズになるため除外。サンプル数 {MIN_SAMPLE} 未満のペアも偶然一致の"
        f" 可能性が高いため除外。)",
        file=out,
    )
    print(file=out)
    main_outs = [e for e in io["main"] if e.kind == "OUT" and _in_comm_window(e.port)]
    sub_outs = [e for e in io["sub"] if e.kind == "OUT" and _in_comm_window(e.port)]
    main_ins = [e for e in io["main"] if e.kind == "IN" and _in_comm_window(e.port)]
    sub_ins = [e for e in io["sub"] if e.kind == "IN" and _in_comm_window(e.port)]

    # 候補ペア: 片方のCPUのOUTポートともう片方のCPUのINポートの全組合せ。
    # 同一CPU内の対応(自分のOUTが自分のINに出る)は経路ではないので除外。
    directions = [
        ("main->sub", main_outs, sub_ins),
        ("sub->main", sub_outs, main_ins),
    ]

    for label, outs, ins in directions:
        print(f"### {label}", file=out)
        if not outs or not ins:
            print("  (OUTまたはINイベントが無く判定不能)", file=out)
            print(file=out)
            continue
        out_ports = sorted(set(e.port for e in outs))
        in_ports = sorted(set(e.port for e in ins))
        # INイベントをport別にframe/seq順のリストとして保持し、各OUTに対し
        # 直後(seq/frame的に後)で最も近い同値INを探す、という単純な追跡は
        # 別々のCPUクロックなので厳密比較ができない。そのため frame を
        # 共通の疎な時間軸として使い、「OUT.frame <= IN.frame」を順序条件、
        # 「値が一致」を一致条件とし、ポートペアごとに集計する。
        ins_by_port: dict[str, list[IoEvent]] = defaultdict(list)
        for e in ins:
            ins_by_port[e.port].append(e)
        # frame昇順のインデックス配列(bisect用)。元のイベント列は既に
        # seq昇順=frame昇順で入っているはずだが、念のためソートしておく。
        ins_frames_by_port: dict[str, list[int]] = {}
        for ip, evs in ins_by_port.items():
            evs.sort(key=lambda e: e.frame)
            ins_frames_by_port[ip] = [e.frame for e in evs]

        results = []
        for op in out_ports:
            op_events = [e for e in outs if e.port == op]
            for ip in in_ports:
                ip_events = ins_by_port[ip]
                ip_frames = ins_frames_by_port[ip]
                if not ip_events:
                    continue
                match = 0
                mismatch = 0
                order_ok = 0
                order_bad = 0
                # 各OUT値について、同フレーム以降で同ポートに現れた最初のINと
                # bisectでO(log n)比較(厳密な1:1対応ではなく傾向を見る)
                for oe in op_events:
                    idx = bisect.bisect_left(ip_frames, oe.frame)
                    if idx >= len(ip_events):
                        continue
                    found = ip_events[idx]
                    if found.value == oe.value:
                        match += 1
                    else:
                        mismatch += 1
                    if found.frame >= oe.frame:
                        order_ok += 1
                    else:
                        order_bad += 1
                total = match + mismatch
                if total < MIN_SAMPLE:
                    continue
                rate = match / total if total else 0.0
                results.append((op, ip, match, mismatch, rate, order_ok, order_bad))
        results.sort(key=lambda r: -r[4])
        if not results:
            print("  (比較可能なペアなし)", file=out)
        for op, ip, match, mismatch, rate, order_ok, order_bad in results:
            print(
                f"  OUT {op} -> IN {ip}: 一致 {match} / 不一致 {mismatch} "
                f"(一致率 {rate*100:.1f}%), 順序(OUT.frame<=IN.frame) {order_ok}/{order_ok+order_bad}",
                file=out,
            )
        print(file=out)


def analyze_q2_status_bits(io: dict[str, list[IoEvent]], out) -> None:
    print("## Q2 ステータスビットの所在: (CPU, INポート) ごとのビット分類", file=out)
    print(file=out)
    for cpu in ("main", "sub"):
        ins = [e for e in io[cpu] if e.kind == "IN"]
        by_port: dict[str, list[int]] = defaultdict(list)
        for e in ins:
            by_port[e.port].append(e.value)
        if not by_port:
            print(f"  ({cpu}: IN イベントなし)", file=out)
            continue
        print(f"### {cpu}", file=out)
        for port in sorted(by_port):
            vals = by_port[port]
            bit_states = []
            for b in range(8):
                bits = [(v >> b) & 1 for v in vals]
                if all(x == 0 for x in bits):
                    bit_states.append("0")
                elif all(x == 1 for x in bits):
                    bit_states.append("1")
                else:
                    bit_states.append("変")
            # bit7..bit0 の順で表示
            disp = " ".join(f"b{b}={bit_states[b]}" for b in reversed(range(8)))
            print(f"  IN {port} (n={len(vals)}): {disp}", file=out)
        print(file=out)


def analyze_q3_interrupt_source(
    io: dict[str, list[IoEvent]], intlog: dict[str, list[IntEvent]], out, n: int = 20
) -> None:
    print(f"## Q3 割り込み源: サブ割り込み受理直前{n}件のI/Oイベント集計", file=out)
    print(file=out)
    sub_io = io["sub"]
    sub_int = intlog["sub"]
    if not sub_int:
        print("  (サブの割り込み受理イベントなし)", file=out)
        print(file=out)
        return
    if not sub_io:
        print("  (サブのI/Oイベントなし)", file=out)
        print(file=out)
        return

    # frame昇順のsub_ioに対し、各割り込み受理点のframe以前・直近N件を集計
    sub_io_sorted = sorted(sub_io, key=lambda e: (e.frame, e.seq))
    sub_io_frames = [e.frame for e in sub_io_sorted]
    port_kind_counter: Counter[str] = Counter()
    last_event_counter: Counter[str] = Counter()  # 直前1件だけ
    n_considered = 0
    for ie in sub_int:
        # ie.frame 以下のI/Oイベントの末尾N件をbisectで求める
        idx = bisect.bisect_right(sub_io_frames, ie.frame)
        if idx == 0:
            continue
        window = sub_io_sorted[max(0, idx - n) : idx]
        n_considered += 1
        seen_in_this_window = set()
        for e in window:
            key = f"{e.kind} {e.port}"
            seen_in_this_window.add(key)
        for key in seen_in_this_window:
            port_kind_counter[key] += 1
        last = window[-1]
        last_event_counter[f"{last.kind} {last.port}"] += 1

    print(f"  対象割り込み受理点: {n_considered} 件 (全{len(sub_int)}件中)", file=out)
    print(f"  直前{n}件のウィンドウに出現した (kind port) の割り込み受理点カバー率 上位:", file=out)
    for key, cnt in port_kind_counter.most_common(15):
        rate = cnt / n_considered * 100 if n_considered else 0
        print(f"    {key}: {cnt}/{n_considered} 件のウィンドウに出現 ({rate:.1f}%)", file=out)
    print(f"  直前1件(直近イベント)の内訳 上位:", file=out)
    for key, cnt in last_event_counter.most_common(10):
        rate = cnt / n_considered * 100 if n_considered else 0
        print(f"    {key}: {cnt} 件 ({rate:.1f}%)", file=out)
    print(file=out)


def analyze_q4_repeat_units(io: dict[str, list[IoEvent]], out, min_n=2, max_n=30, top=10) -> None:
    print(f"## Q4 反復単位: サブの (kind,port) 記号列 n-gram (n={min_n}..{max_n})", file=out)
    print(file=out)
    sub_io = io["sub"]
    if not sub_io:
        print("  (サブのI/Oイベントなし)", file=out)
        return
    symbols = [f"{e.kind[0]}{e.port}" for e in sub_io]  # 例 "OF8", "IFA"

    for n in list(range(min_n, max_n + 1)):
        if len(symbols) < n:
            break
        counter: Counter[tuple] = Counter()
        for i in range(len(symbols) - n + 1):
            gram = tuple(symbols[i : i + n])
            counter[gram] += 1
        # 重複しない(overlapしても構わないが、意味のある反復だけ見たいので
        # 出現回数2回以上のものだけ)
        common = [(g, c) for g, c in counter.items() if c >= 2]
        common.sort(key=lambda x: -x[1])
        if not common:
            continue
        top_g, top_c = common[0]
        # nが大きい場合は代表的な上位のみ表示(全nを出すと膨大になるため
        # n=2,3,4,5,8,10,16,20,30 などの区切りで表示)
        if n in (2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 30) or n == max_n:
            print(f"  n={n}: 出現回数上位{min(top, len(common))}件", file=out)
            for g, c in common[:top]:
                print(f"    {' '.join(g)}  x{c}", file=out)
    print(file=out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iolog", required=True, type=Path, help="m6-sub-*.iolog.txt へのパス")
    ap.add_argument("--intlog", required=True, type=Path, help="m6-sub-*.intlog.txt へのパス")
    ap.add_argument("--out", required=True, type=Path, help="解析結果の出力先")
    ap.add_argument("--int-window", type=int, default=20, help="Q3のウィンドウ件数 (既定20)")
    args = ap.parse_args()

    io = parse_iolog(args.iolog)
    intlog = parse_intlog(args.intlog)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out:
        print(f"# サブCPU通信プロトコル解析: {args.iolog.name}", file=out)
        print(f"# iolog : {args.iolog}", file=out)
        print(f"# intlog: {args.intlog}", file=out)
        print(
            f"# main IOイベント数: {len(io['main'])}, sub IOイベント数: {len(io['sub'])}",
            file=out,
        )
        print(
            f"# main 割り込み受理数: {len(intlog['main'])}, sub 割り込み受理数: {len(intlog['sub'])}",
            file=out,
        )
        print(file=out)

        analyze_q1_data_path(io, out)
        analyze_q2_status_bits(io, out)
        analyze_q3_interrupt_source(io, intlog, out, n=args.int_window)
        analyze_q4_repeat_units(io, out)

    print(f"written: {args.out}")


if __name__ == "__main__":
    main()
