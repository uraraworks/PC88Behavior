#!/usr/bin/env python3
"""tools/analyze_fc_send_path.py — 混成ROM実走診断で見つかった

    sub OUT $FC : 5635件 (基準ログ) / 0件 (混成ログ)
    main IN $FD : 5635件 (基準ログ) / 0件 (混成ログ)

という対を、`docs/spec/l3-subrom.md` 1.15節の sub視点SENDプリミティブ
(`OUT $FD`)とは別の「もう1本のSEND経路」なのか、それとも既存の1.14節
「バルク転送」・1.6節「起動時5635件バースト」・`tools/analyze_bulk_trigger.py`
Q1補足が既に見つけていた「並行チャンネル」の**同一物**なのかを、
値を一切使わずに確認する。

`tools/analyze_bulk_trigger.py` の `find_target`/`pc_histogram` を
import して再利用し、パーサ・分類ロジックを二重実装しない。

やること:
  1. sub OUT $FC / OUT $FD、main IN $FC / IN $FD の pc 分布(件数)を
     1条件について出す(`analyze_bulk_trigger.py` Q1/Q3の再掲+補完)。
  2. sub OUT $FC の直前直後で最も近い sub OUT $FF の値を集計する
     (1.15節SEND手順3「OUT $FF 09」・手順5「OUT $FF 08」と同じ語彙か、
     未知の語彙かを確認する)。同じことを sub OUT $FD についても行う。
  3. sub OUT $FC の直後(同一loop iteration内)に sub OUT $FD が
     隣接して現れる割合(1周期で両ポートを書いているかどうか)を数える。
  4. --cross: 4条件全部で1・2・3が一致するかを確認する。
  5. --clockpair: 共通クロック付きログ(m6g)で、sub OUT $FC と
     main IN $FD を発生順にペアリングし、clock差の分布を出す
     (同一ラッチを介した対応であることの直接証拠)。

再実行方法:
    python3 tools/analyze_fc_send_path.py \
        --iolog measurements/m6c-sub-d0-boot.iolog.txt.gz \
        --label d0-boot \
        --out measurements/m6o-fc-send-path-d0-boot.txt

    python3 tools/analyze_fc_send_path.py cross \
        --iolog measurements/m6c-sub-d0-boot.iolog.txt.gz \
                measurements/m6c-sub-d1-files.iolog.txt.gz \
                measurements/m6c-sub-d2-save.iolog.txt.gz \
                measurements/m6c-sub-d5-seqfile.iolog.txt.gz \
        --label d0-boot d1-files d2-save d5-seqfile \
        --out measurements/m6o-fc-send-path-cross.txt

    python3 tools/analyze_fc_send_path.py clockpair \
        --iolog measurements/m6g-d0-boot-run1.iolog.txt.gz \
        --out measurements/m6o-fc-send-path-clockpair-run1.txt
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402
from analyze_bulk_trigger import find_target, pc_histogram  # noqa: E402

Event = cmp_io.Event


def nearest_ff_context(events: list[Event], target: Event, idx: int) -> tuple[str | None, str | None]:
    """target(sub OUT $FC/$FD 1件、events[idx])の直前・直後で最も近い
    sub OUT $FF の値。呼び出し側が idx を渡すことで O(n) の
    events.index() 探索を避ける(4条件横断で件数が数万件になるため)。"""
    before = None
    for i in range(idx - 1, -1, -1):
        e = events[i]
        if e.kind == "OUT" and e.port == "00FF":
            before = e.value
            break
        if e.kind == "OUT" and e.port in ("00FC", "00FD"):
            break  # 別のFC/FDイベントに当たったら打ち切る(隣接判定のため)
    after = None
    for i in range(idx + 1, len(events)):
        e = events[i]
        if e.kind == "OUT" and e.port == "00FF":
            after = e.value
            break
        if e.kind == "OUT" and e.port in ("00FC", "00FD"):
            break
    return before, after


def ff_context_summary(events: list[Event], targets: list[Event]) -> dict[str, Counter]:
    before_c: Counter = Counter()
    after_c: Counter = Counter()
    idx_of = {id(e): i for i, e in enumerate(events)}
    for t in targets:
        b, a = nearest_ff_context(events, t, idx_of[id(t)])
        before_c[b] += 1
        after_c[a] += 1
    return {"before": before_c, "after": after_c}


def adjacency_rate(sub_events: list[Event], fc_targets: list[Event]) -> tuple[int, int]:
    """sub OUT $FC の直後、次のFC/FDイベントまでの間に sub OUT $FD が
    挟まらず隣接して現れる件数と、そうでない件数。"""
    adjacent = 0
    other = 0
    idx_of = {id(e): i for i, e in enumerate(sub_events)}
    for t in fc_targets:
        i = idx_of[id(t)]
        found = False
        for j in range(i + 1, min(i + 4, len(sub_events))):
            e = sub_events[j]
            if e.kind == "OUT" and e.port == "00FD":
                found = True
                break
            if e.kind == "OUT" and e.port == "00FC":
                break
        if found:
            adjacent += 1
        else:
            other += 1
    return adjacent, other


def single_condition_report(iolog_path: Path, label: str, out) -> dict:
    main_events = cmp_io.parse_iolog(str(iolog_path), "main")
    sub_events = cmp_io.parse_iolog(str(iolog_path), "sub")

    print(f"# M6o fc-send-path 解析: {label} ({iolog_path.name})", file=out)
    print(file=out)

    result: dict = {"label": label}

    print("## 1. pc 分布", file=out)
    for cpu, events, kind, port in [
        ("sub", sub_events, "OUT", "00FC"),
        ("sub", sub_events, "OUT", "00FD"),
        ("main", main_events, "IN", "00FC"),
        ("main", main_events, "IN", "00FD"),
    ]:
        tgt = find_target(events, kind, port)
        hist = pc_histogram(tgt, kind, port)
        print(f"  {cpu} {kind} ${port[-2:]}: 総件数={len(tgt)}", file=out)
        for pc, n in hist:
            print(f"    pc={pc}: {n}件", file=out)
        result[f"{cpu}_{kind}_{port}"] = {pc: n for pc, n in hist}
    print(file=out)

    sub_fc = find_target(sub_events, "OUT", "00FC")
    sub_fd = find_target(sub_events, "OUT", "00FD")

    print("## 2. sub OUT $FC の前後最寄り OUT $FF 値", file=out)
    ctx_fc = ff_context_summary(sub_events, sub_fc)
    print(f"  直前: {dict(ctx_fc['before'])}", file=out)
    print(f"  直後: {dict(ctx_fc['after'])}", file=out)
    result["fc_ff_before"] = dict(ctx_fc["before"])
    result["fc_ff_after"] = dict(ctx_fc["after"])
    print(file=out)

    print("## 2b. sub OUT $FD の前後最寄り OUT $FF 値(比較用。ハンドシェイク分・バルク分が混在)", file=out)
    ctx_fd = ff_context_summary(sub_events, sub_fd)
    print(f"  直前: {dict(ctx_fd['before'])}", file=out)
    print(f"  直後: {dict(ctx_fd['after'])}", file=out)
    result["fd_ff_before"] = dict(ctx_fd["before"])
    result["fd_ff_after"] = dict(ctx_fd["after"])
    print(file=out)

    print("## 3. sub OUT $FC の直後に sub OUT $FD が隣接するか", file=out)
    adj, other = adjacency_rate(sub_events, sub_fc)
    print(f"  隣接あり: {adj}件 / 隣接なし: {other}件", file=out)
    result["fc_fd_adjacent"] = adj
    result["fc_fd_other"] = other
    print(file=out)

    return result


def cross_report(iolog_paths: list[Path], labels: list[str], out) -> None:
    print("# M6o fc-send-path cross解析(4条件横断)", file=out)
    print(file=out)
    results = []
    for path, label in zip(iolog_paths, labels):
        buf_lines: list[str] = []

        class _W:
            def write(self, s):
                buf_lines.append(s)

        import io
        buf = io.StringIO()
        r = single_condition_report(path, label, buf)
        results.append(r)
        print(buf.getvalue(), file=out)

    print("## 横断比較: 全条件で一致するか", file=out)
    keys = ["sub_OUT_00FC", "sub_OUT_00FD", "main_IN_00FC", "main_IN_00FD"]
    for k in keys:
        vals = [tuple(sorted(r[k].items(), key=lambda kv: str(kv[0]))) for r in results]
        same = len(set(vals)) == 1
        print(f"  {k}: 4条件でpc分布パターン一致={same}", file=out)
        if not same:
            for r in results:
                print(f"    {r['label']}: {r[k]}", file=out)

    ff_keys = ["fc_ff_before", "fc_ff_after", "fd_ff_before", "fd_ff_after"]
    for k in ff_keys:
        vals = [tuple(sorted(r[k].items(), key=lambda kv: str(kv[0]))) for r in results]
        same = len(set(vals)) == 1
        print(f"  {k}: 4条件で一致={same}", file=out)
        if not same:
            for r in results:
                print(f"    {r['label']}: {r[k]}", file=out)

    adj_rates = [(r["label"], r["fc_fd_adjacent"], r["fc_fd_other"]) for r in results]
    all_perfect = all(o == 0 for _, _, o in adj_rates)
    print(f"  fc_fd_adjacent: 全条件で隣接なし0件={all_perfect}", file=out)
    for label, a, o in adj_rates:
        print(f"    {label}: 隣接あり={a} 隣接なし={o}", file=out)


def clockpair_report(iolog_path: Path, out) -> None:
    main_events = cmp_io.parse_iolog(str(iolog_path), "main")
    sub_events = cmp_io.parse_iolog(str(iolog_path), "sub")

    sub_fc = [e for e in find_target(sub_events, "OUT", "00FC") if e.clock is not None]
    main_fd = [e for e in find_target(main_events, "IN", "00FD") if e.clock is not None]

    print(f"# M6o fc-send-path clockpair解析: {iolog_path.name}", file=out)
    print(file=out)
    print(f"sub OUT $FC (clock付き): {len(sub_fc)}件", file=out)
    print(f"main IN $FD (clock付き): {len(main_fd)}件", file=out)
    print(file=out)

    if not sub_fc or not main_fd or len(sub_fc) != len(main_fd):
        print("件数が一致しないため発生順ペアリングは行わない。", file=out)
        return

    deltas = [m.clock - s.clock for s, m in zip(sub_fc, main_fd)]
    c = Counter(deltas)
    print("clock差(main - sub)の分布(発生順に1:1対応させた場合):", file=out)
    for d, n in c.most_common():
        print(f"  delta={d}: {n}件", file=out)
    print(file=out)
    modal_delta, modal_n = c.most_common(1)[0]
    print(
        f"最頻delta={modal_delta} が {modal_n}/{len(deltas)}件"
        f" ({100*modal_n/len(deltas):.2f}%) を占める。"
        " subの書き込みが常に先行し、mainの読み出しがほぼ一定の遅延で"
        "追随するなら、両者は同一ラッチの書き手/読み手であることの"
        "直接証拠になる。",
        file=out,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", default="single", choices=["single", "cross", "clockpair"])
    ap.add_argument("--iolog", required=True, type=Path, nargs="+")
    ap.add_argument("--label", type=str, nargs="+", default=None)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    with open(args.out, "w", encoding="utf-8") as out:
        if args.mode == "single":
            label = args.label[0] if args.label else args.iolog[0].stem
            single_condition_report(args.iolog[0], label, out)
        elif args.mode == "cross":
            labels = args.label or [p.stem for p in args.iolog]
            cross_report(args.iolog, labels, out)
        elif args.mode == "clockpair":
            clockpair_report(args.iolog[0], out)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
