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

第3版（M6c 共通クロック対応）:
    従来は main/sub 別々の frame（フレーム番号、粗い）でしか対応付けが
    できなかった。M6c で main/sub・iolog/intlog を横断する単調増加の
    共通クロック（`clock` 列）をハーネスに追加したため、本スクリプトは
    frame ではなく clock で全イベントを1本の時系列にマージして扱う。
    これにより「同じ frame 内で実際にはどちらが先だったか」を初めて
    区別できる。

再実行方法:
    python3 tools/analyze_sub_proto.py \
        --iolog measurements/m6c-sub-d0-boot.iolog.txt \
        --intlog measurements/m6c-sub-d0-boot.intlog.txt \
        --out measurements/m6c-sub-proto-d0-boot.txt
"""
from __future__ import annotations

import argparse
import sys
import bisect
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# cmp_io.py の gzip 透過オープンを共有する（.gz と非圧縮を同じ経路で読む。
# 2026-08-10 measurements/*.iolog.txt,*.intlog.txt を gzip 化したため必要
# になった。docs/notes/disclosure-2026-08-10.md 参照。二重実装しない）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402


@dataclass
class IoEvent:
    seq: int
    clock: int
    frame: int
    cpu: str
    kind: str  # "IN" / "OUT"
    port: str  # 4桁hex文字列 (例 "00F8")
    value: int
    pc: str


@dataclass
class IntEvent:
    seq: int
    clock: int
    frame: int
    cpu: str
    im: int
    level: int
    ret_pc: str
    handler_pc: str


# M6c: clock 列付きフォーマット (seq clock frame cpu kind port value pc)
IO_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{4})\s*$"
)
INT_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s*$"
)


def parse_iolog(path: Path) -> dict[str, list[IoEvent]]:
    """cpu -> events (seq昇順のまま。clock列を持つM6c形式が前提)"""
    events: dict[str, list[IoEvent]] = {"main": [], "sub": []}
    cur_cpu = None
    with cmp_io._open_iolog(str(path)) as f:
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
            seq, clock, frame, cpu, kind, port, value, pc = m.groups()
            events[cpu].append(
                IoEvent(
                    int(seq), int(clock), int(frame), cpu, kind,
                    port.upper(), int(value, 16), pc.upper(),
                )
            )
    return events


def parse_intlog(path: Path) -> dict[str, list[IntEvent]]:
    events: dict[str, list[IntEvent]] = {"main": [], "sub": []}
    cur_cpu = None
    with cmp_io._open_iolog(str(path)) as f:
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
            seq, clock, frame, cpu, im, level, ret_pc, handler_pc = m.groups()
            events[cpu].append(
                IntEvent(
                    int(seq), int(clock), int(frame), cpu, int(im), int(level),
                    ret_pc.upper(), handler_pc.upper(),
                )
            )
    return events


# サブが触れるポート集合(タスクで明示された範囲)。F3-FFの範囲だが、
# 実際に出現するのは観測されたものだけを使う(決め打ちしない)。
COMM_WINDOW_LO = 0x00F0
COMM_WINDOW_HI = 0x00FF
MIN_SAMPLE = 10  # これ未満のペアはたまたま値が揃っただけの可能性が高く除外
SMALL_OUT_WARN = 20  # 発行元OUTの絶対数がこれ未満なら「少数OUT罠」の疑いを明示
CHANCE_RATE = 1.0 / 256.0  # 1バイト一様分布での偶然一致率(約0.39%)


def _in_comm_window(port: str) -> bool:
    v = int(port, 16)
    return COMM_WINDOW_LO <= v <= COMM_WINDOW_HI


def _collapse_consecutive(events: list[IoEvent]) -> list[IoEvent]:
    """同一ポートの列から、直前と同値の連続(ポーリング読み)を1件に畳む。

    残るのは各「値が変化した瞬間」のイベントのみ(先頭は必ず残す)。
    引数は既にclock昇順(真の発生順)であることを前提とする。
    """
    collapsed: list[IoEvent] = []
    prev_value = None
    for e in events:
        if prev_value is None or e.value != prev_value:
            collapsed.append(e)
        prev_value = e.value
    return collapsed


def _significance_note(rate: float, total: int) -> str:
    if total <= 0:
        return ""
    ratio = rate / CHANCE_RATE if CHANCE_RATE else 0.0
    return f"(偶然一致率{CHANCE_RATE*100:.2f}%の{ratio:.1f}倍)"


def _match_backward_clock(
    out_events_by_port: dict[str, list[IoEvent]],
    out_clocks_by_port: dict[str, list[int]],
    ip_events: list[IoEvent],
) -> dict[str, tuple[int, int, int]]:
    """各INイベントについて、そのport(の相手候補OUTポート op)ごとに
    「clockがそのIN未満で最大のOUTイベント」(=真の意味で直前のOUT)を探し、
    一致/不一致/対応なしを集計する。

    clock は main/sub・iolog/intlog を横断する単調増加の共通時間軸なので、
    frame と違い「同一frame内でどちらが先か」を正しく区別できる。

    戻り値: op -> (match, mismatch, no_preceding)
    """
    result: dict[str, tuple[int, int, int]] = {}
    for op, op_clocks in out_clocks_by_port.items():
        op_events = out_events_by_port[op]
        match = 0
        mismatch = 0
        no_preceding = 0
        for ie in ip_events:
            # ie.clock 未満で最大のOUT clockのインデックス(真に直前のOUT)
            idx = bisect.bisect_left(op_clocks, ie.clock) - 1
            if idx < 0:
                no_preceding += 1
                continue
            oe = op_events[idx]
            if oe.value == ie.value:
                match += 1
            else:
                mismatch += 1
        result[op] = (match, mismatch, no_preceding)
    return result


def analyze_q1_data_path(io: dict[str, list[IoEvent]], out) -> None:
    print("## Q1 データ経路の実証: (OUTポート -> INポート) 値一致率・対応付け", file=out)
    print(
        f"  (通信窓口として指定された ${COMM_WINDOW_LO:04X}-${COMM_WINDOW_HI:04X} の"
        f" ポートのみを対象にする。範囲外はCRTC/FDC等の無関係なハードウェアポートで"
        f" ノイズになるため除外。サンプル数 {MIN_SAMPLE} 未満のペアも偶然一致の"
        f" 可能性が高いため除外。)",
        file=out,
    )
    print(
        "  第3版での変更点: 対応付けの時間軸を frame(粗い・CPU間の真の前後関係を"
        "保証しない) から clock(M6cで追加した main/sub横断の単調増加共通クロック)"
        "に差し替えた。各INに対して「clock順で真に直前にある、当該ポートへの"
        "相手CPUのOUT」を探す(第2版までと対応付けの発想=IN基点・後ろ向きは同じ、"
        "軸だけがframe→clockに変わった)。同一ポート・同一値の連続読み(ポーリング)"
        "を1件に畳んだ「変化時のみ」の一致率を、畳む前(raw)と併記する。"
        "各一致率には偶然一致率(1バイト一様分布で約0.39%)との比を併記し、"
        "有意性の目安にする。発行元OUTの絶対数が少ない(<20件)ペアは"
        "「少数OUT罠の疑い」を明示する(第2版で見つかった落とし穴の再発防止)。",
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

        # OUT側: port別にclock昇順で保持(bisect用)。
        outs_by_port: dict[str, list[IoEvent]] = defaultdict(list)
        for e in outs:
            outs_by_port[e.port].append(e)
        out_counts_by_port: dict[str, int] = {}
        out_clocks_by_port: dict[str, list[int]] = {}
        for op, evs in outs_by_port.items():
            evs.sort(key=lambda e: e.clock)
            out_clocks_by_port[op] = [e.clock for e in evs]
            out_counts_by_port[op] = len(evs)

        # IN側: port別のraw列(clock昇順)とcollapsed(値変化時のみ)列
        ins_by_port: dict[str, list[IoEvent]] = defaultdict(list)
        for e in ins:
            ins_by_port[e.port].append(e)
        for ip, evs in ins_by_port.items():
            evs.sort(key=lambda e: e.clock)

        in_ports = sorted(ins_by_port)
        results = []
        for ip in in_ports:
            raw_ins = ins_by_port[ip]
            collapsed_ins = _collapse_consecutive(raw_ins)
            raw_stats = _match_backward_clock(outs_by_port, out_clocks_by_port, raw_ins)
            collapsed_stats = _match_backward_clock(outs_by_port, out_clocks_by_port, collapsed_ins)
            for op in sorted(out_clocks_by_port):
                r_match, r_mismatch, r_nopre = raw_stats[op]
                c_match, c_mismatch, c_nopre = collapsed_stats[op]
                r_total = r_match + r_mismatch
                c_total = c_match + c_mismatch
                if r_total < MIN_SAMPLE and c_total < MIN_SAMPLE:
                    continue
                r_rate = r_match / r_total if r_total else 0.0
                c_rate = c_match / c_total if c_total else 0.0
                results.append(
                    (
                        op, ip, r_match, r_mismatch, r_nopre, r_rate,
                        c_match, c_mismatch, c_nopre, c_rate,
                        out_counts_by_port[op],
                    )
                )
        # 畳んだ後(値が変化した瞬間)の一致率で降順ソート — ポーリングの水増しを
        # 除いた「本当に効いていそうな」ペアを上に出す。
        results.sort(key=lambda r: -r[9])
        if not results:
            print("  (比較可能なペアなし)", file=out)
        for op, ip, r_m, r_mm, r_np, r_rate, c_m, c_mm, c_np, c_rate, op_n in results:
            warn = f"  ※少数OUT罠の疑い(OUT {op} の発行数={op_n}件)" if op_n < SMALL_OUT_WARN else ""
            print(f"  OUT {op} (発行数{op_n}件) -> IN {ip}:{warn}", file=out)
            print(
                f"    畳む前(raw)    : 一致 {r_m} / 不一致 {r_mm} (一致率 {r_rate*100:.1f}%)"
                f" {_significance_note(r_rate, r_m + r_mm)}"
                f" [対応OUTなし {r_np} 件は分母外]",
                file=out,
            )
            print(
                f"    値変化時のみ(collapsed): 一致 {c_m} / 不一致 {c_mm} (一致率 {c_rate*100:.1f}%)"
                f" {_significance_note(c_rate, c_m + c_mm)}"
                f" [対応OUTなし {c_np} 件は分母外]",
                file=out,
            )
        print(file=out)


def analyze_control_vs_data_ports(io: dict[str, list[IoEvent]], out) -> None:
    print("## Q1補助 制御ポート/データポートの判定: OUT値の異なり数と分布", file=out)
    print(
        "  データポートなら書き込まれる値は広く散る(ユニーク値数が多い)はず。"
        "制御ポート/ストローブなら少数の値(典型的にはコマンド語)に集中するはず。"
        "この節はその区別を数字で出すためのもので、経路の当否そのものは判定しない。",
        file=out,
    )
    print(file=out)
    for cpu in ("main", "sub"):
        outs = [e for e in io[cpu] if e.kind == "OUT" and _in_comm_window(e.port)]
        by_port: dict[str, Counter[int]] = defaultdict(Counter)
        for e in outs:
            by_port[e.port][e.value] += 1
        if not by_port:
            print(f"  ({cpu}: 通信窓口へのOUTイベントなし)", file=out)
            continue
        print(f"### {cpu} が OUT したポート", file=out)
        for port in sorted(by_port):
            counter = by_port[port]
            total = sum(counter.values())
            unique = len(counter)
            top = counter.most_common(5)
            top_str = ", ".join(f"{v:02X}={c}({c/total*100:.0f}%)" for v, c in top)
            # 単純な目安: 上位1値が90%以上を占め、かつユニーク値が8以下なら
            # 「制御ポート的」、そうでなければ「データポート的」と仮ラベルする。
            # あくまで目安であり断定ではない。
            top1_share = top[0][1] / total if top else 0.0
            if unique <= 8 and top1_share >= 0.9:
                label = "制御ポート的(少数値に集中)"
            elif unique >= 32:
                label = "データポート的(広く散る)"
            else:
                label = "中間的(断定不可)"
            print(
                f"  OUT {port} (n={total}, ユニーク値数={unique}, 上位1値占有率={top1_share*100:.0f}%): "
                f"{label}",
                file=out,
            )
            print(f"    上位値: {top_str}", file=out)
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
    print(f"## Q3 割り込み源: サブ割り込み受理直前{n}件のI/Oイベント集計(clockベース)", file=out)
    print(
        "  第3版での変更点: 従来は「サブ自身のI/Oイベントのみ」をframe単位で見ていたため、"
        "割り込みを受理した時点で相手CPU(main)が直前に何をしていたかは原理的に見えなかった"
        "(frameでは同一frame内の主従関係が復元できない)。共通クロックにより main+sub を"
        "1本のclock順イベント列にマージし、割り込み受理の直前に「どちらのCPUが・どのポートに・"
        "IN/OUTしたか」を区別して集計する。",
        file=out,
    )
    print(file=out)
    sub_int = intlog["sub"]
    if not sub_int:
        print("  (サブの割り込み受理イベントなし)", file=out)
        print(file=out)
        return
    merged = sorted(io["main"] + io["sub"], key=lambda e: e.clock)
    if not merged:
        print("  (I/Oイベントなし)", file=out)
        print(file=out)
        return
    merged_clocks = [e.clock for e in merged]

    port_kind_counter: Counter[str] = Counter()
    last_event_counter: Counter[str] = Counter()  # 直前1件だけ
    last_main_event_counter: Counter[str] = Counter()  # 直前1件のうちmain発のもの
    n_considered = 0
    n_with_main_in_window = 0
    for ie in sub_int:
        # ie.clock 未満のI/Oイベントの末尾N件をbisectで求める(真に受理前)
        idx = bisect.bisect_left(merged_clocks, ie.clock)
        if idx == 0:
            continue
        window = merged[max(0, idx - n) : idx]
        n_considered += 1
        seen_in_this_window = set()
        has_main = False
        for e in window:
            key = f"{e.cpu} {e.kind} {e.port}"
            seen_in_this_window.add(key)
            if e.cpu == "main":
                has_main = True
        if has_main:
            n_with_main_in_window += 1
        for key in seen_in_this_window:
            port_kind_counter[key] += 1
        last = window[-1]
        last_event_counter[f"{last.cpu} {last.kind} {last.port}"] += 1
        if last.cpu == "main":
            last_main_event_counter[f"{last.kind} {last.port}"] += 1

    print(f"  対象割り込み受理点: {n_considered} 件 (全{len(sub_int)}件中)", file=out)
    print(
        f"  直前{n}件のウィンドウにmain側のイベントが1件以上含まれた受理点: "
        f"{n_with_main_in_window}/{n_considered} 件 "
        f"({n_with_main_in_window/n_considered*100 if n_considered else 0:.1f}%)",
        file=out,
    )
    print(f"  直前{n}件のウィンドウに出現した (cpu kind port) の割り込み受理点カバー率 上位:", file=out)
    for key, cnt in port_kind_counter.most_common(15):
        rate = cnt / n_considered * 100 if n_considered else 0
        print(f"    {key}: {cnt}/{n_considered} 件のウィンドウに出現 ({rate:.1f}%)", file=out)
    print(f"  直前1件(clock順で真に直近のイベント)の内訳 上位:", file=out)
    for key, cnt in last_event_counter.most_common(10):
        rate = cnt / n_considered * 100 if n_considered else 0
        print(f"    {key}: {cnt} 件 ({rate:.1f}%)", file=out)
    print(f"  うち、直前1件がmain側だったものの内訳 上位:", file=out)
    if not last_main_event_counter:
        print("    (該当なし — 直前1件は常にsub自身のイベントだった)", file=out)
    for key, cnt in last_main_event_counter.most_common(10):
        rate = cnt / n_considered * 100 if n_considered else 0
        print(f"    main {key}: {cnt} 件 (受理点全体の{rate:.1f}%)", file=out)
    print(file=out)


def analyze_q4_repeat_units(io: dict[str, list[IoEvent]], out, min_n=2, max_n=30, top=10) -> None:
    print(f"## Q4 反復単位: サブの (kind,port) 記号列 n-gram (n={min_n}..{max_n}, clock順)", file=out)
    print(file=out)
    sub_io = sorted(io["sub"], key=lambda e: e.clock)
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
    ap.add_argument("--iolog", required=True, type=Path, help="m6c-sub-*.iolog.txt へのパス(clock列必須)")
    ap.add_argument("--intlog", required=True, type=Path, help="m6c-sub-*.intlog.txt へのパス(clock列必須)")
    ap.add_argument("--out", required=True, type=Path, help="解析結果の出力先")
    ap.add_argument("--int-window", type=int, default=20, help="Q3のウィンドウ件数 (既定20)")
    args = ap.parse_args()

    io = parse_iolog(args.iolog)
    intlog = parse_intlog(args.intlog)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out:
        print(f"# サブCPU通信プロトコル解析(第3版・共通クロック対応): {args.iolog.name}", file=out)
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
        analyze_control_vs_data_ports(io, out)
        analyze_q2_status_bits(io, out)
        analyze_q3_interrupt_source(io, intlog, out, n=args.int_window)
        analyze_q4_repeat_units(io, out)

    print(f"written: {args.out}")


if __name__ == "__main__":
    main()
