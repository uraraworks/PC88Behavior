#!/usr/bin/env python3
"""tools/analyze_bulk_trigger.py — 起動時バルクバースト(5635件)の
開始条件・終端条件・ハンドシェイクの有無を測定する。

`docs/spec/l3-subrom.md` 3節「サブが要求を受けてから最初に応答するまでの
遅延・手順。測定は未着手」および1.10節「バルクは$FEハンドシェイクを
一切伴わない単純反復ループ」の裏取り(または訂正)を目的とする解析器。

対象イベント: main の `IN $FD`。`docs/notes/m6-sub-invariant.md` 1節・
`docs/spec/l3-subrom.md` 1.6節で確定した5635件のバースト本体であり、
`sub OUT $FC` と対になる(同 1.2節)。

使っているのは cpu/seq/clock/frame/port/kind/pc の各列のみ。value 列は
一切参照しない(伏せ字済みログでも解析結果が変わらないことの裏付けにもなる)。
`tools/cmp_io.py` の `parse_iolog`/`_open_iolog` を import して共有し、
パーサを二重実装しない。

やること(5つの問い。docs/notes/m6j-bulk-trigger.md に対応):
  Q1 main IN $FD の pc 分布(バースト本体のループはどこか)
  Q2 バースト開始点(最初の main IN $FD)から遡った main の I/O・pc 列
     (どうやってバーストに入るか)
  Q3 sub OUT $FC の pc 分布(Q1と同じことをsub側で)
  Q4 バースト終端(5635件目)の直後、main/subがそれぞれ何をするか
     (どちらが先に抜けるか、共通クロックで判定できる)
  Q5 バースト区間内(最初の IN $FD の clock 〜 5635件目の clock)に、
     main/sub の $FE/$FF アクセスが何件あるか
     (0件でなければ1.10節「ハンドシェイクを伴わない」の訂正が必要)

再実行方法:
    python3 tools/analyze_bulk_trigger.py \
        --iolog measurements/m6g-d0-boot-run1.iolog.txt.gz \
        --out measurements/m6j-bulk-trigger.txt

検出力の自己検算: pc 列をシャッフルした場合に Q1/Q3 の集中度
(最頻 pc の占有率)が崩れることを --selftest で確認できる
(`tools/verify_analyzer_corruption.py` の思想を踏襲。簡易版)。
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

# cmp_io.py の Event/parse_iolog/gzip透過オープンを共有する(二重実装しない)。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402

Event = cmp_io.Event

BURST_PORT = "00FD"  # main が読む側(sub OUT $FC と対になる。l3-subrom.md 1.2節)
BURST_KIND = "IN"
PAIR_PORT_MAIN_READ2 = "00FC"  # 発見: バースト区間内で main が同時に読んでいる別チャンネル(下記Q1参照)


def pc_histogram(events: list[Event], kind: str, port: str) -> list[tuple[str, int]]:
    """指定 kind/port のイベントを pc でグループ化し、件数の多い順に返す。"""
    c = Counter(e.pc for e in events if e.kind == kind and e.port == port)
    return sorted(c.items(), key=lambda kv: -kv[1])


def find_target(events: list[Event], kind: str, port: str) -> list[Event]:
    return [e for e in events if e.kind == kind and e.port == port]


def context_before(all_events: list[Event], boundary_clock: int, n: int) -> list[Event]:
    """boundary_clock より前の直近 n 件(発生順=clock昇順)を返す。"""
    before = [e for e in all_events if e.clock is not None and e.clock < boundary_clock]
    return before[-n:]


def context_after(all_events: list[Event], boundary_clock: int, n: int) -> list[Event]:
    """boundary_clock より後の直後 n 件を返す。"""
    after = [e for e in all_events if e.clock is not None and e.clock > boundary_clock]
    return after[:n]


def fmt_ev(e: Event) -> str:
    # value は出さない(伏せ字方針。伏せ字でなくても本解析器は値を使わない)。
    return f"clock={e.clock:>8} frame={e.frame:>5} {e.cpu:<4} {e.kind:<3} port={e.port} pc={e.pc}"


def count_ports_in_clock_range(
    events: list[Event], lo: int, hi: int, ports: set[str]
) -> Counter:
    """[lo, hi] の clock 範囲内で、指定ポート集合への (cpu, kind, port) 別件数を数える。"""
    c: Counter = Counter()
    for e in events:
        if e.clock is None:
            continue
        if lo <= e.clock <= hi and e.port in ports:
            c[(e.cpu, e.kind, e.port)] += 1
    return c


def random_sample_selftest(
    all_events: list[Event], target: list[Event], seed: int = 1234
) -> tuple[float, float]:
    """Q1/Q3 の pc 集中度が「IN $FD / OUT $FC を選んだこと」に特有かを見る。

    最初に書いた版は「選び終わった後の pc 列そのものをシャッフルする」
    テストだったが、これは多重集合(件数の集合)を変えないため
    占有率が変わりようがなく、検出力ゼロの無意味なテストだった
    (シャッフルしても Counter の結果は不変。値そのものは元々使っていない
    ので触りようがないのと同じ理由で、これも「触っても変わらない」だけの
    偽の安全確認だった——気づいた時点で直す。CLAUDE.mdの規律どおり
    ごまかさずここに記録する)。

    正しい検出力テストは「kind=IN・port=$FD という選び方をしなかったら
    この集中は消えるか」である。全イベントから同数をランダムに抽出し、
    その pc 分布の最頻占有率と比較する。ランダム抽出のほうが低ければ、
    Q1/Q3 の集中は「IN $FD / OUT $FC を選んだ」ことに特有の現象であり、
    たまたま出た数字ではないと言える。

    戻り値: (対象の最頻pc占有率, ランダム抽出n件の最頻pc占有率)
    """
    n = len(target)
    if n == 0 or not all_events:
        return 0.0, 0.0
    orig_top = Counter(e.pc for e in target).most_common(1)[0][1] / n

    rng = random.Random(seed)
    sample = rng.sample(all_events, min(n, len(all_events)))
    sample_top = Counter(e.pc for e in sample).most_common(1)[0][1] / len(sample)
    return orig_top, sample_top


def write_report(iolog_path: Path, out) -> None:
    main_events = cmp_io.parse_iolog(str(iolog_path), "main")
    sub_events = cmp_io.parse_iolog(str(iolog_path), "sub")

    print(f"# M6j バルクトリガー解析: {iolog_path.name}", file=out)
    print(file=out)
    print(
        "値(value列)は一切使わない。使用列: cpu/seq/clock/frame/port/kind/pc のみ。",
        file=out,
    )
    print(file=out)

    # --- Q1: main IN $FD の pc 分布 -------------------------------------
    main_fd_in = find_target(main_events, BURST_KIND, BURST_PORT)
    print(f"## Q1: main IN ${BURST_PORT[-2:]} の pc 分布(バースト本体のループはどこか)", file=out)
    print(f"  総件数: {len(main_fd_in)}", file=out)
    hist = pc_histogram(main_fd_in, BURST_KIND, BURST_PORT)
    print(f"  pc の種類数: {len(hist)}", file=out)
    for pc, n in hist:
        print(f"    pc={pc}: {n}件", file=out)
    print(file=out)

    if not main_fd_in:
        print("(main IN $FD が0件のため、以降のQ2/Q4/Q5は評価できない)", file=out)
        return

    burst_lo_clock = main_fd_in[0].clock
    burst_hi_clock = main_fd_in[-1].clock
    print(
        f"  バースト区間の clock 範囲: {burst_lo_clock} 〜 {burst_hi_clock}"
        f"(frame {main_fd_in[0].frame}〜{main_fd_in[-1].frame})",
        file=out,
    )
    print(file=out)

    # 発見: バースト区間内で main は $FC も同時に読んでいる(sub OUT $FD と対)。
    # これは Q1 が問う「本体のループ」の一部なので、参考として同じ区間で見る。
    main_fc_in_in_range = [
        e for e in main_events
        if e.kind == "IN" and e.port == PAIR_PORT_MAIN_READ2
        and e.clock is not None and burst_lo_clock <= e.clock <= burst_hi_clock
    ]
    print(
        f"## 補足: バースト区間内の main IN ${PAIR_PORT_MAIN_READ2[-2:]}"
        "(併走している別チャンネルの有無を確認)",
        file=out,
    )
    print(f"  件数: {len(main_fc_in_in_range)}", file=out)
    for pc, n in pc_histogram(main_fc_in_in_range, "IN", PAIR_PORT_MAIN_READ2):
        print(f"    pc={pc}: {n}件", file=out)
    print(
        "  (0件でなければ、バースト1回のループ本体が $FD 読み出しだけでなく"
        "$FC 読み出しも同時に行っている=ループが2チャンネル分の受信を"
        "1周期でまとめて処理していることを示す。詳細はノート本文参照)",
        file=out,
    )
    print(file=out)

    # --- Q2: バースト開始点から遡った main の I/O・pc列 -------------------
    print("## Q2: バースト開始点から遡った main の I/O 列(どうやって入るか)", file=out)
    before_n = 60
    ctx = context_before(main_events, burst_lo_clock, before_n)
    print(f"  最初の main IN $FD (clock={burst_lo_clock}) の直前 {len(ctx)} 件:", file=out)
    for e in ctx:
        print(f"    {fmt_ev(e)}", file=out)
    print(file=out)

    # --- Q3: sub OUT $FC の pc 分布 --------------------------------------
    sub_fc_out = find_target(sub_events, "OUT", "00FC")
    print(f"## Q3: sub OUT $FC の pc 分布(Q1と同じ問いをsub側で)", file=out)
    print(f"  総件数: {len(sub_fc_out)}", file=out)
    hist_sub = pc_histogram(sub_fc_out, "OUT", "00FC")
    print(f"  pc の種類数: {len(hist_sub)}", file=out)
    for pc, n in hist_sub:
        print(f"    pc={pc}: {n}件", file=out)
    print(file=out)

    if sub_fc_out:
        sub_lo_clock = sub_fc_out[0].clock
        sub_hi_clock = sub_fc_out[-1].clock
        print(
            f"  sub側バースト区間の clock 範囲: {sub_lo_clock} 〜 {sub_hi_clock}",
            file=out,
        )
        print(file=out)
    else:
        sub_lo_clock = sub_hi_clock = None

    # --- Q4: バースト終端の直後、main/sub は何をするか ---------------------
    print("## Q4: バースト終端(5635件目)の直後、main/subは何をするか", file=out)
    print(f"  main側終端 clock={burst_hi_clock}", file=out)
    if sub_hi_clock is not None:
        print(f"  sub側終端  clock={sub_hi_clock}", file=out)
        if burst_hi_clock < sub_hi_clock:
            print(
                "  → main側の5635件目のほうが先に起きている"
                "(main が先に抜けた/sub がまだ動いている、と読める)",
                file=out,
            )
        elif sub_hi_clock < burst_hi_clock:
            print(
                "  → sub側の5635件目のほうが先に起きている"
                "(sub が先に止まった、と読める)",
                file=out,
            )
        else:
            print("  → 両側の終端clockが一致(同時)", file=out)
    print(file=out)

    after_n = 30
    ctx_after_main = context_after(main_events, burst_hi_clock, after_n)
    print(f"  main側、終端直後 {len(ctx_after_main)} 件:", file=out)
    for e in ctx_after_main:
        print(f"    {fmt_ev(e)}", file=out)
    print(file=out)

    if sub_hi_clock is not None:
        ctx_after_sub = context_after(sub_events, sub_hi_clock, after_n)
        print(f"  sub側、終端直後 {len(ctx_after_sub)} 件:", file=out)
        for e in ctx_after_sub:
            print(f"    {fmt_ev(e)}", file=out)
        print(file=out)

    # --- Q5: バースト区間内の $FE/$FF アクセス件数 -------------------------
    print(
        "## Q5: バースト区間内($FD最初の件〜5635件目まで)の $FE/$FF アクセス件数",
        file=out,
    )
    all_events_sorted = sorted(
        [e for e in main_events + sub_events if e.clock is not None],
        key=lambda e: e.clock,
    )
    handshake_ports = {"00FE", "00FF"}
    counts = count_ports_in_clock_range(all_events_sorted, burst_lo_clock, burst_hi_clock, handshake_ports)
    total = sum(counts.values())
    print(f"  区間内の $FE/$FF アクセス総数: {total}", file=out)
    for (cpu, kind, port), n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {cpu} {kind} ${port[-2:]}: {n}件", file=out)
    print(file=out)
    if total == 0:
        print(
            "  → 0件。1.10節「ハンドシェイクを一切伴わない単純反復ループ」は"
            "この測定でも支持される。",
            file=out,
        )
    else:
        print(
            "  → 0件ではない。1.10節「バルクは$FEハンドシェイクを一切伴わない"
            "単純反復ループ」という記述は、この測定結果と食い違う。"
            "訂正が必要(詳細はノート本文)。",
            file=out,
        )
    print(file=out)

    # --- 検出力の自己検算 -------------------------------------------------
    print(
        "## 検出力の自己検算(IN $FD/OUT $FCという選び方をやめても集中するか)",
        file=out,
    )
    orig_top_main, rand_top_main = random_sample_selftest(main_events, main_fd_in)
    print(
        f"  main IN $FD: 対象の最頻pc占有率={orig_top_main:.3f} / "
        f"同数ランダム抽出(全イベントから)={rand_top_main:.3f}",
        file=out,
    )
    orig_top_sub, rand_top_sub = random_sample_selftest(sub_events, sub_fc_out)
    print(
        f"  sub OUT $FC: 対象の最頻pc占有率={orig_top_sub:.3f} / "
        f"同数ランダム抽出(全イベントから)={rand_top_sub:.3f}",
        file=out,
    )
    print(
        "  (ランダム抽出のほうが明確に低ければ、Q1/Q3の集中は「IN $FD/OUT $FCを"
        "選んだ」ことに特有の現象であり、たまたま出た数字ではないと言える)",
        file=out,
    )
    print(file=out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as out:
            write_report(args.iolog, out)
    except cmp_io.FormatError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"エラー: ファイルを読めない: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
