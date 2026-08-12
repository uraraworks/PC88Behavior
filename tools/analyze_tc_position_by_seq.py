#!/usr/bin/env python3
"""PC88Behavior: 起動時FDC初期化区間の各batch境界とTC(OUT $F8)の出現位置を
seq番号レベルで正確に列挙する(M6t)。

背景: 混成ROM実走診断で、基準側は分岐点40がIN $FB(seq49、SENSE INT結果
2バイト目)、分岐点41がIN $FA(seq50、そのまま次コマンドへ)であるのに対し、
混成側は分岐点41がOUT $F8(seq50、TC)になっていた。docs/notes/m6q-boot-
fdc-sequence.md はbatch1・batch2の直後の両方にTCが来ると確定していたが、
この実走観測と整合するか、seq単位で検算する。

値は一切見ない(m6q・m6pと同じ規律)。使うのは件数・kind・pc・seqのみ。

再実行方法:
    python3 tools/analyze_tc_position_by_seq.py cross \
        --iolog d0-boot    measurements/m6c-sub-d0-boot.iolog.txt.gz \
        --iolog d1-files   measurements/m6c-sub-d1-files.iolog.txt.gz \
        --iolog d2-save    measurements/m6c-sub-d2-save.iolog.txt.gz \
        --iolog d5-seqfile measurements/m6c-sub-d5-seqfile.iolog.txt.gz \
        --out measurements/m6t-tc-position-by-seq-cross.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_fdc_ports import IoEvent, parse_iolog  # noqa: E402
from analyze_boot_fdc_sequence import find_boot_init_window, segment_runs  # noqa: E402


def report(label: str, sub_events: list[IoEvent]) -> str:
    lines = [f"### {label}", ""]
    win = find_boot_init_window(sub_events)
    if win is None:
        lines.append("起動時FDC初期化区間を特定できなかった")
        lines.append("")
        return "\n".join(lines)
    start, end = win
    window = sub_events[start:end]
    lines.append(f"区間: index[{start}:{end}) seq範囲=[{window[0].seq},{window[-1].seq}]")

    runs = segment_runs(window)
    # batch = (OUT run, IN run) のペア
    batches = []
    i = 0
    while i + 1 < len(runs):
        if runs[i]["kind"] == "OUT" and runs[i + 1]["kind"] == "IN":
            batches.append((runs[i], runs[i + 1]))
            i += 2
        else:
            i += 1

    # 区間内の $F7/$F8 イベントを全部、そのままseq順に列挙(三つ組み判定は
    # せず、単発OUT $F8だけの出現も見逃さない)
    f78 = [e for e in window if e.port in ("00F7", "00F8")]

    lines.append("")
    lines.append("batch境界とTC(単発含む)の位置:")
    for bi, (out_r, in_r) in enumerate(batches, start=1):
        lines.append(f"  batch{bi}: OUT run seq=[{out_r['start_seq']},{out_r['end_seq']}] "
                     f"(len={out_r['len']}) -> IN run seq=[{in_r['start_seq']},{in_r['end_seq']}] "
                     f"(len={in_r['len']})")
        # IN run終端の直後、次のbatchのOUT runが始まる前までに現れる$F7/$F8を列挙
        upper = batches[bi][0]["start_seq"] if bi < len(batches) else (window[-1].seq + 1)
        between = [e for e in f78 if in_r["end_seq"] < e.seq < upper]
        if between:
            for e in between:
                lines.append(f"      直後: {e.kind} ${e.port[-2:]} seq={e.seq} pc={e.pc}")
        else:
            lines.append("      直後: (F7/F8イベント無し)")
    lines.append("")

    # 参照用: seq 45-55 の生イベント列(実走観測 seq49/50 との突き合わせ用)
    lines.append("参照: seq 45-55 の生イベント列(このログでの対応番号。実走ログとは")
    lines.append("別採取のため絶対値の一致は保証されないが、構造(直前直後の並び)は")
    lines.append("比較できる):")
    for e in window:
        if 40 <= e.seq <= 60:
            lines.append(f"    seq={e.seq} {e.kind} ${e.port[-2:]} pc={e.pc}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("cross")
    c.add_argument("--iolog", nargs=2, action="append", metavar=("LABEL", "PATH"), required=True)
    c.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.mode == "cross":
        out_lines = ["# M6t: 起動時FDC初期化区間 batch境界・TC位置のseq単位確定 (cross)", ""]
        for label, path in args.iolog:
            events, masked = parse_iolog(Path(path))
            out_lines.append(report(label, events["sub"]))
        Path(args.out).write_text("\n".join(out_lines), encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
