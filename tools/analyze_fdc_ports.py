#!/usr/bin/env python3
"""PC88Behavior: サブCPU側 FDC制御ポート ($FA/$FB, 補助として $F7/$F8/$FE/$FF)
の意味論を測定するための解析器 (M6h)。

入力は measurements/ 配下の M6c 形式 (共通クロック付き8列) *.iolog.txt。
出力する観測 (すべて測定ログの機械的な再集計):

  H1  $FA の値と、直後に sub が $FB へアクセスするかどうかの相関。
      「data-ready を示すビット」の候補をビット単位の相関係数で洗い出す。
  H2  sub OUT $FB の値列に見えるバースト構造（先頭バイト候補・バースト長）。
      「$FA を挟まず連続する OUT $FB の塊」をバーストの定義とする。
  H3  操作の種類 (d0-boot/d1-files/d2-save/d5-seqfile) ごとの
      バースト先頭バイト分布の比較。
  H4  $F7 / $F8 の OUT が、H2 のバースト開始・終了のどちらに近いか
      （制御/ストローブ的ポートの役割を絞る）。

このスクリプトは採取済みログのみを読む。公式ROMのバイト列・逆アセンブル
結果には一切触れない。

再実行方法:
    python3 tools/analyze_fdc_ports.py \
        --iolog measurements/m6c-sub-d0-boot.iolog.txt \
        --label d0-boot \
        --out measurements/m6h-fdc-d0-boot.txt
"""
from __future__ import annotations

import argparse
import sys
import re
from collections import Counter
from dataclasses import dataclass
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
    kind: str
    port: str
    value: int
    pc: str


IO_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{4})\s*$"
)


def parse_iolog(path: Path) -> dict[str, list[IoEvent]]:
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


def bits(v: int) -> list[int]:
    return [(v >> b) & 1 for b in range(8)]


def h1_fa_predicts_fb(sub_events: list[IoEvent]) -> str:
    """$FA の値ビットと「直後に $FB アクセスがあるか」の相関を測る。

    「直後」の定義: sub のイベント列(seq昇順=発生順)で、当該 IN $FA の
    次のイベントが $FB へのアクセス(IN/OUTどちらでも)かどうか。
    比較のため、次のイベントが $FB でない場合の $FA 値も集める。
    """
    fa_idx = [i for i, e in enumerate(sub_events) if e.kind == "IN" and e.port == "00FA"]
    followed_by_fb_vals: list[int] = []
    not_followed_vals: list[int] = []
    next_port_counter: Counter[str] = Counter()
    for i in fa_idx:
        if i + 1 >= len(sub_events):
            continue
        nxt = sub_events[i + 1]
        next_port_counter[f"{nxt.kind} {nxt.port}"] += 1
        if nxt.port == "00FB":
            followed_by_fb_vals.append(sub_events[i].value)
        else:
            not_followed_vals.append(sub_events[i].value)

    lines = []
    lines.append("## H1: IN $FA の値と、直後イベントが $FB かどうかの相関")
    lines.append("")
    lines.append(f"IN $FA 総数: {len(fa_idx)}")
    lines.append(f"直後が $FB (IN/OUT問わず): {len(followed_by_fb_vals)} 件")
    lines.append(f"直後が $FB でない: {len(not_followed_vals)} 件")
    lines.append("")
    lines.append("直後イベントの内訳 (上位10):")
    for k, c in next_port_counter.most_common(10):
        lines.append(f"  {k}: {c}")
    lines.append("")

    lines.append("ビットごとの「1である割合」比較 (followed-by-FB群 vs not群):")
    lines.append(f"{'bit':>4} {'p(1|followedByFB)':>20} {'p(1|not)':>12} {'差':>8}")
    for b in range(8):
        if followed_by_fb_vals:
            p1 = sum((v >> b) & 1 for v in followed_by_fb_vals) / len(followed_by_fb_vals)
        else:
            p1 = float("nan")
        if not_followed_vals:
            p0 = sum((v >> b) & 1 for v in not_followed_vals) / len(not_followed_vals)
        else:
            p0 = float("nan")
        diff = p1 - p0 if followed_by_fb_vals and not_followed_vals else float("nan")
        lines.append(f"{b:>4} {p1:>20.4f} {p0:>12.4f} {diff:>+8.4f}")
    lines.append("")
    lines.append(
        "解釈の注意: 差が大きいビットは「$FB直後アクセスの有無」と相関するが、"
        "相関があるだけで「そのビットがRQM/DIOのようなハンドシェイクビットだ」"
        "と断定はできない。因果の向き・実機での再現性は別に要検証。"
    )
    lines.append("")
    return "\n".join(lines)


def h2_fb_burst_structure(sub_events: list[IoEvent]) -> tuple[str, list[list[IoEvent]]]:
    """sub の OUT $FB を「$FA アクセスを挟まない連続塊」でバースト分割する。

    バーストの区切り: 当該 OUT $FB の直前に IN $FA が挟まっていたら新バースト。
    (「ステータスを確認してからコマンド/データを書く」定型を区切りに使う仮説)
    """
    bursts: list[list[IoEvent]] = []
    cur: list[IoEvent] = []
    last_was_fa = True  # 先頭は常に新バースト扱い
    for e in sub_events:
        if e.kind == "OUT" and e.port == "00FB":
            if last_was_fa and cur:
                bursts.append(cur)
                cur = []
            cur.append(e)
            last_was_fa = False
        elif e.port == "00FA" and e.kind == "IN":
            last_was_fa = True
        # 他のポートは区切り判定に使わない(直前1件がFAかどうかだけ見る)
    if cur:
        bursts.append(cur)

    lengths = Counter(len(b) for b in bursts)
    first_bytes = Counter(b[0].value for b in bursts)

    lines = []
    lines.append("## H2: sub OUT $FB のバースト構造 (IN $FA 直後を区切りとする定義)")
    lines.append("")
    lines.append(f"バースト数: {len(bursts)}")
    lines.append(f"OUT $FB 総数: {sum(len(b) for b in bursts)}")
    lines.append("")
    lines.append("バースト長の分布 (上位15):")
    for length, c in lengths.most_common(15):
        lines.append(f"  長さ{length}: {c}件")
    lines.append("")
    lines.append("バースト先頭バイト値の分布 (上位15):")
    for v, c in first_bytes.most_common(15):
        lines.append(f"  0x{v:02X}: {c}件")
    lines.append("")
    lines.append(
        "解釈の注意: この区切り方(IN $FAの直後で切る)自体が1つの仮説であり、"
        "実際のコマンド境界と一致する保証はない。長さ1のバーストが大多数を占める"
        "場合は「$FAで都度ステータス確認しながら1バイトずつ$FBに書く」型を示唆し、"
        "長さが数バイトで揃うバーストが目立つ場合は「コマンド+引数」型を示唆する、"
        "という**定性的な読み方**に留める。"
    )
    lines.append("")
    return "\n".join(lines), bursts


def h3_burst_first_byte_by_condition(all_bursts: dict[str, list[list[IoEvent]]]) -> str:
    lines = []
    lines.append("## H3: 条件別のバースト先頭バイト分布比較")
    lines.append("")
    for label, bursts in all_bursts.items():
        fb = Counter(b[0].value for b in bursts)
        total = sum(fb.values())
        top = fb.most_common(5)
        lines.append(f"### {label} (バースト数 {len(bursts)})")
        for v, c in top:
            pct = 100.0 * c / total if total else 0.0
            lines.append(f"  0x{v:02X}: {c}件 ({pct:.1f}%)")
        lines.append("")
    return "\n".join(lines)


def h4_f7_f8_timing(sub_events: list[IoEvent], bursts: list[list[IoEvent]]) -> str:
    """$F7/$F8 の OUT が、直前直後にどのポートを挟むかを集計する。
    (バースト開始/終了との近さを見て「制御/ストローブ」候補の役割を絞る)
    """
    # seq -> index
    idx_by_seq = {e.seq: i for i, e in enumerate(sub_events)}
    burst_start_seqs = {b[0].seq for b in bursts}
    burst_end_seqs = {b[-1].seq for b in bursts}

    lines = []
    lines.append("## H4: sub OUT $F7 / $F8 と H2バーストの時間的位置関係")
    lines.append("")
    for port in ("00F7", "00F8"):
        occ = [e for e in sub_events if e.kind == "OUT" and e.port == port]
        near_start = 0
        near_end = 0
        for e in occ:
            i = idx_by_seq.get(e.seq)
            if i is None:
                continue
            # 前後2件以内にバースト開始/終了があるか
            window = sub_events[max(0, i - 2): i + 3]
            wseqs = {w.seq for w in window}
            if wseqs & burst_start_seqs:
                near_start += 1
            if wseqs & burst_end_seqs:
                near_end += 1
        lines.append(f"OUT ${port[-2:]}: 総数 {len(occ)}件")
        lines.append(f"  バースト開始の前後2件以内: {near_start}件")
        lines.append(f"  バースト終了の前後2件以内: {near_end}件")
        vals = Counter(e.value for e in occ)
        lines.append(f"  値の分布(上位5): {vals.most_common(5)}")
        lines.append("")
    lines.append(
        "解釈の注意: 「前後2件以内」は粗い近傍定義。近い/遠いという定性的傾向は"
        "読めるが、因果（$F7/$F8書き込みがバーストの引き金かどうか）はこの解析"
        "だけでは決められない。"
    )
    lines.append("")
    return "\n".join(lines)


def h5_fa_fe_stability(sub_events: list[IoEvent]) -> str:
    """$FA / $FE の全区間ビット定数性を再確認する(Q2の裏取り・単一スクリプトで完結させる)。"""
    lines = ["## H5: $FA / $FE / $FF ビットの定数性再確認 (Q2の裏取り)", ""]
    for port in ("00FA", "00FE", "00FF"):
        for kind in ("IN", "OUT"):
            vals = [e.value for e in sub_events if e.kind == kind and e.port == port]
            if not vals:
                continue
            const_bits = []
            for b in range(8):
                bitvals = {(v >> b) & 1 for v in vals}
                if len(bitvals) == 1:
                    const_bits.append((b, next(iter(bitvals))))
            lines.append(
                f"sub {kind} ${port[-2:]}: {len(vals)}件, "
                f"固定ビット: {const_bits if const_bits else 'なし(全ビット変化)'}"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub_ap = ap.add_subparsers(dest="mode", required=True)

    single = sub_ap.add_parser("single", help="H1/H2/H4/H5 を1条件について実行")
    single.add_argument("--iolog", type=Path, required=True)
    single.add_argument("--label", type=str, required=True)
    single.add_argument("--out", type=Path, required=True)

    cross = sub_ap.add_parser("cross", help="H3: 複数条件のバースト先頭バイト分布比較")
    cross.add_argument("--iolog", action="append", nargs=2, metavar=("LABEL", "PATH"), required=True)
    cross.add_argument("--out", type=Path, required=True)

    args = ap.parse_args()

    if args.mode == "single":
        events = parse_iolog(args.iolog)
        sub = events["sub"]

        out_lines = []
        out_lines.append(f"# M6h FDCポート解析: {args.label}")
        out_lines.append(f"入力: {args.iolog}")
        out_lines.append(f"sub イベント総数: {len(sub)}")
        out_lines.append("")

        out_lines.append(h1_fa_predicts_fb(sub))
        h2_text, bursts = h2_fb_burst_structure(sub)
        out_lines.append(h2_text)
        out_lines.append(h4_f7_f8_timing(sub, bursts))
        out_lines.append(h5_fa_fe_stability(sub))

        args.out.write_text("\n".join(out_lines), encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        all_bursts: dict[str, list[list[IoEvent]]] = {}
        for label, path in args.iolog:
            events = parse_iolog(Path(path))
            _, bursts = h2_fb_burst_structure(events["sub"])
            all_bursts[label] = bursts

        text = h3_burst_first_byte_by_condition(all_bursts)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
