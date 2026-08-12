#!/usr/bin/env python3
"""PC88Behavior: sub側 $F7/$F8 アクセスを、直前の $FA/$FB (FDCコマンド/
結果フェーズ) との位置関係だけで分類する解析器 (M6p想定)。

背景: 混成ROM実走の診断(last.txt)で、公式subは「結果フェーズ($FA/$FB読み)
の直後」に `OUT $F8` を出すが、自作subはそこで$FEハンドシェイクへ戻って
しまい分岐していた。本稿はこの構造 ($F8がFDCの結果フェーズ終了後に
出る「TC」なのか、1.16節の起動手順の一部なのか) を、既存の伏せ字済み
ログの再解析だけで確認する。

値は $F7/$F8/$FF のみ見る。$FA/$FB/$FC/$FD の値は一切見ない
(このスクリプトはvalueを表示・比較する箇所で対象ポートを絞っている)。

追加測定は行っていない。既存の `measurements/m6c-sub-{d0-boot,d1-files,
d2-save,d5-seqfile}.iolog.txt.gz` を再解析する。パーサは
`tools/analyze_fdc_ports.py` の `parse_iolog`/`IoEvent` をそのまま
import して使う(二重実装しない)。

再実行方法:
    python3 tools/analyze_tc_and_f8.py cross \
        --iolog d0-boot measurements/m6c-sub-d0-boot.iolog.txt.gz \
        --iolog d1-files measurements/m6c-sub-d1-files.iolog.txt.gz \
        --iolog d2-save measurements/m6c-sub-d2-save.iolog.txt.gz \
        --iolog d5-seqfile measurements/m6c-sub-d5-seqfile.iolog.txt.gz \
        --out measurements/m6p-tc-and-f8-cross.txt
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_fdc_ports import IoEvent, parse_iolog  # noqa: E402


def classify(sub_events: list[IoEvent]) -> dict:
    """sub イベント列を前から走査し、$F7/$F8 の各アクセスを
    「直前の $FA/$FB アクセスの種類」で分類する。

    last_fb_kind: 直近の $FB アクセスの kind ('IN'=結果読み最中/直後,
        'OUT'=コマンド書き込み中, None=まだ$FBに触れていない)
    fb_run_len:   その連続の長さ(直前に $FA を挟んでも$FBのkindが
        変わらなければ連続とみなす。H2バースト定義とは別に、
        「同じkindが何回連続したか」だけを見る単純カウント)
    """
    f7f8_events = []
    last_fb_kind: str | None = None
    fb_run_len = 0
    last_fb_seq: int | None = None
    for e in sub_events:
        if e.port == "00FB":
            if e.kind == last_fb_kind:
                fb_run_len += 1
            else:
                last_fb_kind = e.kind
                fb_run_len = 1
            last_fb_seq = e.seq
        elif e.port in ("00F7", "00F8"):
            gap = None if last_fb_seq is None else e.seq - last_fb_seq
            f7f8_events.append({
                "seq": e.seq,
                "kind": e.kind,
                "port": e.port,
                "pc": e.pc,
                "value": e.value,
                "last_fb_kind": last_fb_kind,
                "fb_run_len_at_boundary": fb_run_len,
                "gap_from_last_fb": gap,
            })
    return {"f7f8": f7f8_events}


def order_check(sub_events: list[IoEvent]) -> str:
    """OUT $F8(pc=06D5) → OUT $F7(pc=036E) → IN $F8(pc=0332/03C2) の
    三つ組みが本当にこの順で隣接しているかを確認する。
    「隣接」の定義: $F7/$F8以外のポートを間に挟まず連続する場合のみ
    「直接連続」、それ以外(FA/FB等を挟む)は「非連続一致」に分ける。
    """
    only_f7f8 = [e for e in sub_events if e.port in ("00F7", "00F8")]
    seq_pairs = Counter()
    for a, b in zip(only_f7f8, only_f7f8[1:]):
        key = (f"{a.kind} {a.port}@{a.pc}", f"{b.kind} {b.port}@{b.pc}")
        seq_pairs[key] += 1
    lines = ["## 隣接ペア ($F7/$F8のみを抜き出した列での直後関係)", ""]
    for (a, b), c in seq_pairs.most_common(20):
        lines.append(f"  {a}  ->  {b} : {c}件")
    lines.append("")
    return "\n".join(lines)


def report_single(label: str, sub_events: list[IoEvent]) -> str:
    r = classify(sub_events)
    lines = [f"### {label}", ""]

    # (port,kind,pc,last_fb_kind) の組み合わせごとの件数
    key_counter = Counter(
        (x["port"], x["kind"], x["pc"], x["last_fb_kind"]) for x in r["f7f8"]
    )
    lines.append("port/kind/pc/直前FB種別 の組み合わせ件数:")
    for (port, kind, pc, lastfb), c in sorted(key_counter.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {kind} ${port[-2:]} pc={pc} 直前FB={lastfb}: {c}件")
    lines.append("")

    # $F8 OUT の値の分布 (F8は許可ポート)
    f8_out_vals = Counter(x["value"] for x in r["f7f8"] if x["port"] == "00F8" and x["kind"] == "OUT")
    lines.append(f"OUT $F8 の値分布: {dict(f8_out_vals)}")
    f8_in_vals = Counter(x["value"] for x in r["f7f8"] if x["port"] == "00F8" and x["kind"] == "IN")
    lines.append(f"IN  $F8 の値分布: {dict(f8_in_vals)}")
    f7_out_vals = Counter(x["value"] for x in r["f7f8"] if x["port"] == "00F7" and x["kind"] == "OUT")
    lines.append(f"OUT $F7 の値分布: {dict(f7_out_vals)}")
    lines.append("")

    # gap_from_last_fb の分布 (F8 OUT pc=06D5 のみ、"結果直後TC"仮説の検証)
    for port, kind, pc in [("00F8", "OUT", "06D5"), ("00F7", "OUT", "036E"), ("00F8", "IN", "0332")]:
        gaps = [x["gap_from_last_fb"] for x in r["f7f8"]
                if x["port"] == port and x["kind"] == kind and x["pc"] == pc]
        gap_counter = Counter(gaps)
        lines.append(f"{kind} ${port[-2:]} pc={pc}: 件数={len(gaps)}, "
                     f"直前FBからのgap分布(上位8)={gap_counter.most_common(8)}")
    lines.append("")

    lines.append(order_check(sub_events))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub_ap = ap.add_subparsers(dest="mode", required=True)
    cross = sub_ap.add_parser("cross")
    cross.add_argument("--iolog", action="append", nargs=2, metavar=("LABEL", "PATH"), required=True)
    cross.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    out_lines = ["# M6p: sub $F7/$F8 の分類 (直前 $FA/$FB との位置関係)", ""]
    for label, path in args.iolog:
        events, masked = parse_iolog(Path(path))
        masked_total = sum(masked.values())
        if masked_total:
            print(f"注記: {path}: 伏せ字イベント{masked_total}件 "
                  f"(FA/FBの値は使っていないので分類には影響しない)", file=sys.stderr)
        out_lines.append(report_single(label, events["sub"]))
        out_lines.append("")

    args.out.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()


