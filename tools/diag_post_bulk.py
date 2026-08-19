#!/usr/bin/env python3
"""tools/diag_post_bulk.py — **バルク終端以降**に限定して、公式実行と混成実行の
イベント列を突き合わせる（m7bb）。

なぜ要るか: 既存の `tools/diag_l3_mixed.py` の構造的一致プレフィックスは
**バルクより手前**で切れる指標（main側258件）なので、「バルクを終えたあとに
mainが別のコードへ入る」という分岐（m7ba）には使えない。ここでは基準点を
**最後の `sub OUT $FC`（バルク終端）**に取り直して比較する。

比較キーは `(cpu, kind, port)` で、**値は比較にも出力にも使わない**。
連続する同一キーはランレングス圧縮する（ポーリング回数の揺れを分岐と
取り違えないため。diag_l3_mixed と同じ方針）。**つまり「同じ種類の
イベントが何回続いたか」の違いは意図的に検出しない。** 検出できるのは
キー（cpu/kind/port）の並びの違いだけである——この比較器で「分岐なし」
と出ても、回数の違いは残りうる。

出力は位置・件数・キー（cpu/kind/port）だけで、値は1バイトも出さない。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402


def load(path: Path, cpu_filter: str | None):
    rows, masked = m2s.parse_iolog(path)
    ev = sorted(rows, key=lambda e: e.clock)
    bulk = [e for e in ev if e.cpu == "sub" and e.port == "00FC" and e.kind == "OUT"]
    if not bulk:
        raise SystemExit(f"{path}: バルク（sub OUT $FC）が見つからない")
    after = [e for e in ev if e.clock > bulk[-1].clock]
    if cpu_filter:
        after = [e for e in after if e.cpu == cpu_filter]
    keys = [(e.cpu, e.kind, e.port) for e in after]
    collapsed = []
    for k in keys:
        if collapsed and collapsed[-1][0] == k:
            collapsed[-1][1] += 1
        else:
            collapsed.append([k, 1])
    return len(bulk), after, collapsed


def fmt(k, n):
    cpu, kind, port = k
    return f"{cpu} {kind} ${port[-2:]}" + (f"×{n}" if n > 1 else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base", type=Path, help="基準（公式ROM一式）の iolog")
    ap.add_argument("target", type=Path, help="対象（混成）の iolog")
    ap.add_argument("--cpu", choices=["main", "sub"], default=None,
                     help="片側のCPUだけを比較する（既定は両方を時系列でマージ）")
    ap.add_argument("--window", type=int, default=6, help="分岐点の前後に出す件数")
    args = ap.parse_args()

    nb, base_ev, base = load(args.base, args.cpu)
    nt, tgt_ev, tgt = load(args.target, args.cpu)
    print(f"基準: バルク{nb}件、終端以降 {len(base_ev)}イベント（畳み込み後 {len(base)}）")
    print(f"対象: バルク{nt}件、終端以降 {len(tgt_ev)}イベント（畳み込み後 {len(tgt)}）")

    n = min(len(base), len(tgt))
    first = None
    for i in range(n):
        if base[i][0] != tgt[i][0]:
            first = i
            break
    if first is None:
        print(f"畳み込み後 {n} 件まで構造的に一致（短いほうの終端まで）")
        return 0
    print(f"\n最初の構造的分岐: 畳み込み後 {first + 1} 件目")
    lo = max(0, first - args.window)
    print("  --- 基準側 ---")
    for i in range(lo, min(len(base), first + args.window)):
        mark = " <<<" if i == first else ""
        print(f"    {i + 1:>4}: {fmt(*base[i])}{mark}")
    print("  --- 対象側 ---")
    for i in range(lo, min(len(tgt), first + args.window)):
        mark = " <<<" if i == first else ""
        print(f"    {i + 1:>4}: {fmt(*tgt[i])}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
