#!/usr/bin/env python3
"""PC88Behavior: バルク転送後の「レコード境界」を、2通りの独立した窓の取り方で
確定する（m7bi）。

背景: `docs/notes/m7bh-post-bulk-read-coordinates.md` で、バルク直後の最初の
READが公式では**受信5件の時点**で行われており、自作の6バイトレコード規則
（m7ax）とは異なる区切り方をしていることが分かった。ただし値までは見ていない
（伏せ字済みログが入力のため）。本スクリプトは値を一切扱わず、
**sub側の受信イベント（IN $FC）が連続する「run」の長さ**と、
**バルク直後の最初のrunがどう終わるか**を、2通りの窓で独立に測る。

窓(a): sub視点で、連続するIN $FC の間に sub OUT $FB か sub OUT $FD が
       割り込んだら、そこでrunを切る（データ方向の切り替わりを検出）。
窓(b): 1.12節で確定した$FFフェーズコード語彙のうち、RECVプリミティブの
       完了(OUT $FF 0x0C)の直後に**再アーム**(OUT $FF 0x0B)が来るかどうかで
       runを切る（続けて次のバイトを受信する気があるかどうかを検出）。

両者は独立な観測（(a)はFB/FDという別ポートの出現、(b)は$FFの語彙）なので、
一致すれば結論の裏付けになり、食い違えばそこが未解明として残る
（`docs/notes/m6n-run-boundary.md` の「窓を変えたら結論も変えて確かめ直す」を
先取りして両方実装する）。

出力するのは件数・run長・clock位置・フェーズコード（$FE/$FF、これは
データポートではないため伏せ字対象外）だけ。**$FB/$FC/$FD の値は
一切扱わない**（伏せ字済みログが入力なので元々値は無いが、コードとしても
触らない）。入力ログのデータポートが伏せ字されていない場合は、
解析せず拒否する（CLAUDE.md禁止事項5違反を検出器自身が起こさないため）。

再実行方法:
    python3 tools/analyze_record_boundaries.py \\
        --iolog measurements/m6g-d0-boot-run1.iolog.txt.gz \\
        --label official-run1 \\
        --out /tmp/m7bi-run1.txt
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

# 既存のパーサを再利用する(二重実装しない)。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402

Ev = m2s.Ev

DATA_PORTS = ("00FB", "00FC", "00FD")

# 1.12節で確定した$FFフェーズコード語彙(main/sub共通)。
RECV_FINISH = 0x0C  # RECVプリミティブ完了(1.15節手順7)
RECV_REARM = 0x0B  # RECVプリミティブ再武装(1.15節手順1)


class UnanalyzableError(Exception):
    """伏せ字されていない、または壊れた入力で解析を拒否するときの例外。"""


def check_redacted(rows: list[Ev]) -> None:
    """データポート($FB/$FC/$FD)の値が伏せ字(None)以外に残っていないか
    確認する。残っていれば解析を拒否する(黙って値を扱わない)。"""
    leaked = [e for e in rows if e.port in DATA_PORTS and e.value is not None]
    if leaked:
        raise UnanalyzableError(
            f"データポート({sorted({e.port for e in leaked})})に伏せ字されて"
            f"いない値が{len(leaked)}件残っている。解析を拒否する。"
        )


def sub_fc_indices(sub_rows: list[Ev]) -> list[int]:
    return [i for i, e in enumerate(sub_rows) if e.kind == "IN" and e.port == "00FC"]


def last_bulk_out_clock(sub_rows: list[Ev]) -> int | None:
    """バルク終端 = 最後の sub OUT $FC のclock。バルクが無いログではNone。"""
    bulk = [e for e in sub_rows if e.kind == "OUT" and e.port == "00FC"]
    if not bulk:
        return None
    return bulk[-1].clock


# --- 窓(a): OUT $FB / OUT $FD の割り込みで切る ------------------------------


def window_a_runs(sub_rows: list[Ev], fc_idx: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    cur: list[int] = []
    for j, i in enumerate(fc_idx):
        if cur:
            prev_i = fc_idx[j - 1]
            between = sub_rows[prev_i + 1:i]
            broke = any(
                e.kind == "OUT" and e.port in ("00FB", "00FD") for e in between
            )
            if broke:
                runs.append(cur)
                cur = []
        cur.append(i)
    if cur:
        runs.append(cur)
    return runs


# --- 窓(b): $FF 0B/0C の再アーム有無で切る ----------------------------------


def _finish_after(sub_rows: list[Ev], i: int, n: int) -> int | None:
    """i(IN $FC)の直後、次のIN $FCより前に来る最初の OUT $FF=0x0C(完了)の
    インデックス。次のIN $FCより先に見つからなければNone。"""
    for j in range(i + 1, n):
        e = sub_rows[j]
        if e.kind == "OUT" and e.port == "00FF" and e.value == RECV_FINISH:
            return j
        if e.kind == "IN" and e.port == "00FC":
            return None
    return None


def window_b_runs(sub_rows: list[Ev], fc_idx: list[int]) -> list[list[int]]:
    n = len(sub_rows)
    runs: list[list[int]] = []
    cur: list[int] = []
    for i in fc_idx:
        cur.append(i)
        fin = _finish_after(sub_rows, i, n)
        cont = False
        if fin is not None and fin + 1 < n:
            nxt = sub_rows[fin + 1]
            cont = nxt.kind == "OUT" and nxt.port == "00FF" and nxt.value == RECV_REARM
        if not cont:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


# --- run終了後の最初の行動 --------------------------------------------------


def describe_event(e: Ev | None) -> str:
    if e is None:
        return "(ログ終端)"
    if e.kind == "OUT" and e.port == "00FF" and e.value == RECV_REARM:
        return "再アーム(sub OUT $FF 0B)"
    if e.port in ("00FB", "00FD"):
        return f"sub {e.kind} ${e.port[-2:]}"
    if e.port == "00FF" and e.value is not None:
        return f"sub {e.kind} $FF {e.value:02X}"
    return f"sub {e.kind} ${e.port[-2:]}"


def run_end_action(sub_rows: list[Ev], run: list[int]) -> str:
    """runの最後のIN $FCが完了(OUT $FF=0x0C)したあと、最初に来るsubの行動。
    完了マーカーが見つからない場合(次のFCより先に来ない、あるいはログ終端)は
    その旨を返す。"""
    n = len(sub_rows)
    last_i = run[-1]
    fin = _finish_after(sub_rows, last_i, n)
    if fin is None:
        return "(完了マーカー未検出)"
    if fin + 1 >= n:
        return "(ログ終端)"
    return describe_event(sub_rows[fin + 1])


# --- 集計・レポート ---------------------------------------------------------


def split_pre_post(
    sub_rows: list[Ev], runs: list[list[int]], bulk_clock: int | None
) -> tuple[list[list[int]], list[list[int]]]:
    if bulk_clock is None:
        return runs, []
    pre = [r for r in runs if sub_rows[r[0]].clock <= bulk_clock]
    post = [r for r in runs if sub_rows[r[0]].clock > bulk_clock]
    return pre, post


def run_len_hist(runs: list[list[int]]) -> Counter:
    return Counter(len(r) for r in runs)


def run_lengths(runs: list[list[int]]) -> list[int]:
    return [len(r) for r in runs]


def analyze(rows: list[Ev], label: str) -> dict:
    check_redacted(rows)
    sub_rows = [e for e in rows if e.cpu == "sub"]
    fc_idx = sub_fc_indices(sub_rows)
    bulk_clock = last_bulk_out_clock(sub_rows)

    runs_a = window_a_runs(sub_rows, fc_idx)
    runs_b = window_b_runs(sub_rows, fc_idx)

    pre_a, post_a = split_pre_post(sub_rows, runs_a, bulk_clock)
    pre_b, post_b = split_pre_post(sub_rows, runs_b, bulk_clock)

    return {
        "label": label,
        "total_fc": len(fc_idx),
        "bulk_clock": bulk_clock,
        "a": {
            "hist": run_len_hist(runs_a),
            "n_runs": len(runs_a),
            "post_lengths": run_lengths(post_a),
            "post_runs": post_a,
        },
        "b": {
            "hist": run_len_hist(runs_b),
            "n_runs": len(runs_b),
            "post_lengths": run_lengths(post_b),
            "post_runs": post_b,
        },
        "sub_rows": sub_rows,
    }


def write_report(result: dict, out) -> None:
    label = result["label"]
    print(f"# レコード境界解析: {label}", file=out)
    print(file=out)
    print(f"sub IN $FC 総数: {result['total_fc']}", file=out)
    bc = result["bulk_clock"]
    print(f"バルク終端(最後の sub OUT $FC)のclock: {bc if bc is not None else '(バルクなし)'}", file=out)
    print(file=out)

    for key, jp in (("a", "窓(a): OUT $FB/$FD 割り込みで切る"),
                     ("b", "窓(b): $FF 0B/0C 再アーム有無で切る")):
        w = result[key]
        print(f"## {jp}", file=out)
        print(f"  run数: {w['n_runs']}", file=out)
        print(f"  run長ヒストグラム(全体): {dict(sorted(w['hist'].items()))}", file=out)
        print(f"  バルク後のrun長(出現順): {w['post_lengths']}", file=out)
        print(file=out)

    hist_a = result["a"]["hist"]
    hist_b = result["b"]["hist"]
    print("## 窓(a)と窓(b)の一致/不一致", file=out)
    if hist_a == hist_b:
        print("  全体run長ヒストグラム: 一致", file=out)
    else:
        print(f"  全体run長ヒストグラム: 不一致  a={dict(sorted(hist_a.items()))}  b={dict(sorted(hist_b.items()))}", file=out)
    post_a = result["a"]["post_lengths"]
    post_b = result["b"]["post_lengths"]
    if post_a == post_b:
        print(f"  バルク後run長(出現順): 一致  {post_a}", file=out)
    else:
        print(f"  バルク後run長(出現順): 不一致  a={post_a}  b={post_b}", file=out)
    print(file=out)

    print("## バルク後の各runについて、run終了後に最初に来たsubの行動", file=out)
    sub_rows = result["sub_rows"]
    for key, jp in (("a", "窓(a)"), ("b", "窓(b)")):
        print(f"  {jp}:", file=out)
        for idx, run in enumerate(result[key]["post_runs"], start=1):
            action = run_end_action(sub_rows, run)
            print(f"    run{idx}(長さ{len(run)}): {action}", file=out)
    print(file=out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", type=Path, default=None, help="省略時は標準出力")
    args = ap.parse_args()

    rows, _masked = m2s.parse_iolog(args.iolog)
    try:
        result = analyze(rows, args.label)
    except UnanalyzableError as ex:
        msg = f"解析不可: {ex}"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("w", encoding="utf-8") as out:
                print(msg, file=out)
        else:
            print(msg)
        print(msg, file=sys.stderr)
        return 1

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as out:
            write_report(result, out)
        print(f"written: {args.out}")
    else:
        write_report(result, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
