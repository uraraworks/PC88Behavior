#!/usr/bin/env python3
"""tools/diag_l3_mixed.py — 混成ROM実行のI/O列を、公式基準ログと
「ポート/pcレベル」で突き合わせ、最初の分岐点を出す。

## 何のためか

tools/conform_l3.sh の混成ROMステップは「main が IN $FD で受け取る値の列」
（docs/spec/l3-subrom.md 5.2節条件1）が期待値と一致するかどうかしか
判定しない。自作サブROMが最初に公式と食い違うのが「データ以前、
$FE/$FD ハンドシェイクの段階」だった場合、その分岐点を見るには
値ではなく **発生順・方向(IN/OUT)・ポート・発行元PC** の列を比べる必要がある
（docs/PLAN.md の状況認識）。

## なぜ「厳密添字比較」だけでは足りないか（既定をスピン畳み込み比較に変えた理由）

コミット 421f969 時点の比較は (cpu,kind,port,pc) を先頭から添字で厳密に
揃えて比較していた。ユーザーの公式環境での実走（コミット 8e6a513 の
実装後）で、これが誤検出を生むことが分かった。

    基準[7088] IN  port=00FE pc=37DC   ← 4回目のポーリング
    混成[7088] OUT port=00FF pc=37F0   ← 混成は2回で抜けた

`IN $FE pc=37DC` は仕様書1.13節の SEND前ポーリングループで、公式は4回・
混成は2回回っただけであり、以降の並び（OUT $FF→OUT $FD→OUT $FF→
IN $FE→...）は公式と同じ構造をたどっていた。**ポーリング回数は
タイミング依存であり、プロトコル準拠の判定基準ではない**——これは
tools/cmp_io.py が L1 の適合条件で既に踏んだのと同じ理由（IN の回数を
比較対象から外した）であり、docs/spec/l3-subrom.md 5.3節が確立した
「初期化区間は完全一致・定常区間は周期のみ一致（回数は問わない）」という
型とも整合する。添字だけの厳密比較はこの型と噛み合っておらず、
タイミング揺れをすべて「分岐」として報告してしまい、本当の構造的
分岐点を埋もれさせる。

そこで既定の比較を「スピン畳み込み比較」に変えた: 連続する同一
(cpu,kind,port,pc) を1件に畳み込み（ランレングス圧縮）、畳んだ列どうしを
比較する。回数の差は分岐として扱わず、別立てで「回数差」として報告する
（回数が極端に違う場合は無限ループ疑いとして目立たせる——それが実際の
停止位置を示す最良の手がかりになる）。元の厳密添字比較は `--strict` で
残す（消さない。「行き止まりを git reset で消さない」規律と同じ理由で、
比較のしかたを選べるようにしておく）。

## なぜ値を一切見ずに比較してよいか（クリーンルーム規律）

比較キーは (cpu, kind(IN/OUT), port, pc) の4項目だけで、**value 列は
読み込みはしても比較にも表示にも一切使わない**。CLAUDE.md 禁止事項5は
「データポートの値列を伏せてからコミット・比較・表示する」ことを求めており、
この4項目だけの比較はその伏せ字が既に済んでいる前提で動く
（本ツールは redact_iolog.py 適用後のログしか受け取らない）。
value を使わないので、伏せ字が「--」に潰れていようが元の値のままだろうが
結果は変わらない——つまりこの比較ロジック自体は、伏せ字が正しく効いて
いるかどうかに依存しない設計になっている。スピン畳み込み（回数の
カウント）も compare_key だけを見て行うので、この性質は変わらない。

## cmp_io.py との関係（二重実装しない範囲・した範囲）

- **パース(parse_iolog)は cmp_io.py から import して使う。** iolog の
  7列/8列形式を読む・CPU節を切り出す、という処理は完全に同じ
  ロジックが要るため（cmp_io.parse_iolog をそのまま使う）。
- **比較ロジックは新規に書く（cmp_io.py の report_mismatch は流用しない）。**
  理由: report_mismatch は port だけでなく **value まで比較キーに含み、
  かつ食い違い箇所の value を fmt_event() で表示する**設計（値を伏せる
  モードを持たない）。今回必要なのは真逆で「value を比較にも表示にも
  一切使わない」比較なので、value を見ない別の関数として書いたほうが、
  中途半端なフラグ分岐で report_mismatch に手を入れるより安全
  （「触らなければ既存の適合条件判定の挙動を壊さない」）。
  加えて、本ツールは片方向の最初の分岐点だけでなく
  「ポート別内訳」「片側にしか出ないポート」「スピン畳み込み・回数差」も
  出す必要があり、これは cmp_io.py に無い機能なのでどのみち新規実装になる。

終了コード: 分岐なし 0 / 分岐あり 1 / 使い方の誤り・書式エラー 2
"""

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402

# 回数差のうち、比(大きいほう/小さいほう)がこれ以上なら「無限ループ疑い」
# として目立つ形で報告する。実測(1.13節ポーリング)では公式4回・混成2回
# (比2.0)のようなタイミング差が出るので、それとは桁が違う値を選ぶ。
EXTREME_RATIO = 50.0


def compare_key(e: "cmp_io.Event") -> tuple:
    """比較キー。value を含めないのが要点(モジュールdocstring参照)。"""
    return (e.cpu, e.kind, e.port, e.pc)


def fmt_key_event(e: "cmp_io.Event") -> str:
    """value を出さない表示(厳密比較・--strict 用)。"""
    return f"{e.kind:<3} port={e.port} pc={e.pc}  (seq={e.seq} frame={e.frame})"


@dataclass(frozen=True)
class Run:
    """畳み込み後の1件。同一 (cpu,kind,port,pc) が連続した回数を保持する。"""

    key: tuple
    count: int
    first: "cmp_io.Event"  # 表示用(seq/frame)は先頭イベントのものを使う


def fold_spins(events: list) -> list["Run"]:
    """連続する同一 (cpu,kind,port,pc) を1件に畳み込む(ランレングス圧縮)。

    タイミング依存のポーリング回数を「回数の差」として構造比較から
    分離するための前処理(モジュールdocstring参照)。value は使わない。
    """
    runs: list[Run] = []
    for e in events:
        k = compare_key(e)
        if runs and runs[-1].key == k:
            runs[-1] = Run(k, runs[-1].count + 1, runs[-1].first)
        else:
            runs.append(Run(k, 1, e))
    return runs


def fmt_run(r: "Run") -> str:
    cpu, kind, port, pc = r.key
    cnt = f" x{r.count}" if r.count > 1 else ""
    return f"{kind:<3} port={port} pc={pc}{cnt}  (先頭 seq={r.first.seq} frame={r.first.frame})"


def find_first_divergence(seq_a: list, seq_b: list, key_fn) -> int | None:
    """key_fn(要素) を先頭から比較し、最初に食い違う0-indexedの位置を返す。
    片方が短ければ短いほうが尽きた位置を返す。完全一致なら None。
    厳密比較(Event列)にもスピン畳み込み比較(Run列)にも使う共通ロジック。
    """
    n = min(len(seq_a), len(seq_b))
    for i in range(n):
        if key_fn(seq_a[i]) != key_fn(seq_b[i]):
            return i
    if len(seq_a) != len(seq_b):
        return n
    return None


def print_window_strict(ref: list, mixed: list, idx: int, radius: int = 20) -> None:
    lo = max(0, idx - radius)
    hi = min(max(len(ref), len(mixed)), idx + radius + 1)
    print(f"  --- 基準側 index {lo + 1}〜{hi} ---")
    for i in range(lo, hi):
        marker = "→" if i == idx else " "
        e = ref[i] if i < len(ref) else None
        print(f"  {marker} 基準[{i + 1:>6}] {fmt_key_event(e) if e else '(なし)'}")
    print(f"  --- 混成側 index {lo + 1}〜{hi} ---")
    for i in range(lo, hi):
        marker = "→" if i == idx else " "
        e = mixed[i] if i < len(mixed) else None
        print(f"  {marker} 混成[{i + 1:>6}] {fmt_key_event(e) if e else '(なし)'}")


def print_window_folded(ref_runs: list, mixed_runs: list, idx: int, radius: int = 20) -> None:
    lo = max(0, idx - radius)
    hi = min(max(len(ref_runs), len(mixed_runs)), idx + radius + 1)
    print(f"  --- 基準側 畳み込み後index {lo + 1}〜{hi} ---")
    for i in range(lo, hi):
        marker = "→" if i == idx else " "
        r = ref_runs[i] if i < len(ref_runs) else None
        print(f"  {marker} 基準[{i + 1:>6}] {fmt_run(r) if r else '(なし)'}")
    print(f"  --- 混成側 畳み込み後index {lo + 1}〜{hi} ---")
    for i in range(lo, hi):
        marker = "→" if i == idx else " "
        r = mixed_runs[i] if i < len(mixed_runs) else None
        print(f"  {marker} 混成[{i + 1:>6}] {fmt_run(r) if r else '(なし)'}")


def port_kind_breakdown(events: list, top: int = 10) -> list[tuple[tuple, int]]:
    c = Counter((e.kind, e.port) for e in events)
    return c.most_common(top)


def ports_only_in(a: list, b: list) -> set:
    """a に現れる (kind,port) のうち b に一度も現れないものの集合。"""
    a_set = {(e.kind, e.port) for e in a}
    b_set = {(e.kind, e.port) for e in b}
    return a_set - b_set


def count_diff_report(ref_runs: list, mixed_runs: list, matched_prefix: int) -> list[tuple]:
    """畳み込み後の一致プレフィックス内で、キーは同じだが回数が違う箇所を集める。

    戻り値の各要素: (畳み込み後index, key, 基準回数, 混成回数, 比)
    """
    diffs = []
    for i in range(matched_prefix):
        rr, mr = ref_runs[i], mixed_runs[i]
        if rr.count != mr.count:
            lo, hi = min(rr.count, mr.count), max(rr.count, mr.count)
            ratio = hi / lo if lo else float("inf")
            diffs.append((i, rr.key, rr.count, mr.count, ratio))
    return diffs


def print_count_diffs(diffs: list, max_show: int = 30) -> None:
    if not diffs:
        print("    (無し)")
        return
    diffs_sorted = sorted(diffs, key=lambda d: d[4], reverse=True)
    extreme = [d for d in diffs_sorted if d[4] >= EXTREME_RATIO]
    if extreme:
        print(
            f"  [要注意] 比が{EXTREME_RATIO:.0f}倍以上の回数差 {len(extreme)}件"
            "（無限ループの疑い。実際の停止位置を示す最良の手がかり）:"
        )
        for i, key, rc, mc, ratio in extreme:
            cpu, kind, port, pc = key
            print(
                f"    畳み込み後#{i + 1}  {kind:<3} port={port} pc={pc}"
                f"  基準={rc}回  混成={mc}回  比={ratio:.1f}倍"
            )
    shown = diffs_sorted[:max_show]
    print(
        f"\n  --- 回数差一覧（構造一致・回数不一致、上位{len(shown)}/{len(diffs_sorted)}件、比の降順） ---"
    )
    for i, key, rc, mc, ratio in shown:
        cpu, kind, port, pc = key
        print(
            f"    畳み込み後#{i + 1}  {kind:<3} port={port} pc={pc}"
            f"  基準={rc}回  混成={mc}回  比={ratio:.1f}倍"
        )


def report_cpu_section(cpu: str, ref: list, mixed: list, strict: bool = False) -> int:
    """1 CPU 分（main または sub）のレポートを表示する。戻り値: 分岐あり1/なし0。"""
    print(f"\n===== {cpu} =====")
    print(f"  基準側 総イベント数: {len(ref)} 件 / 混成側 総イベント数: {len(mixed)} 件")

    rc = 0
    if strict:
        idx = find_first_divergence(ref, mixed, compare_key)
        if idx is None:
            print("  分岐なし（(kind,port,pc) の列が先頭から完全一致・厳密比較）")
        else:
            rc = 1
            print(f"  最初の分岐点(厳密比較): 通し番号 {idx + 1} 件目")
            print_window_strict(ref, mixed, idx)
    else:
        ref_runs = fold_spins(ref)
        mixed_runs = fold_spins(mixed)
        print(
            f"  畳み込み後件数: 基準側 {len(ref_runs)} 件 / 混成側 {len(mixed_runs)} 件"
            "（連続する同一(kind,port,pc)をランレングス圧縮。既定の比較モード）"
        )

        idx = find_first_divergence(ref_runs, mixed_runs, lambda r: r.key)
        matched_prefix = idx if idx is not None else min(len(ref_runs), len(mixed_runs))
        ref_prefix_raw = sum(r.count for r in ref_runs[:matched_prefix])
        mixed_prefix_raw = sum(r.count for r in mixed_runs[:matched_prefix])
        print(
            f"  構造的一致プレフィックス: 畳み込み後 {matched_prefix} 件"
            f"（元イベント数換算: 基準側 {ref_prefix_raw} 件 / 混成側 {mixed_prefix_raw} 件）"
        )

        if idx is None:
            print("  構造的分岐なし（畳み込み後の (kind,port,pc) の列が先頭から完全一致）")
        else:
            rc = 1
            print(f"  最初の構造的分岐点: 畳み込み後 通し番号 {idx + 1} 件目")
            print_window_folded(ref_runs, mixed_runs, idx)

        print("\n  --- 回数差（構造一致・回数不一致の箇所、畳み込み後） ---")
        diffs = count_diff_report(ref_runs, mixed_runs, matched_prefix)
        print_count_diffs(diffs)

    print("\n  --- 基準側 ポート別内訳（上位10件、(kind,port)） ---")
    for (kind, port), cnt in port_kind_breakdown(ref):
        print(f"    {kind:<3} {port}: {cnt} 件")
    print("  --- 混成側 ポート別内訳（上位10件、(kind,port)） ---")
    for (kind, port), cnt in port_kind_breakdown(mixed):
        print(f"    {kind:<3} {port}: {cnt} 件")

    only_ref = ports_only_in(ref, mixed)
    only_mixed = ports_only_in(mixed, ref)
    print("\n  --- 公式側にはあるが混成側に一度も現れない (kind,port) ---")
    if only_ref:
        for kind, port in sorted(only_ref):
            print(f"    {kind:<3} {port}")
    else:
        print("    (無し)")
    print("  --- 混成側にはあるが公式側に一度も現れない (kind,port) ---")
    if only_mixed:
        for kind, port in sorted(only_mixed):
            print(f"    {kind:<3} {port}")
    else:
        print("    (無し)")

    return rc


def run(ref_path: str, mixed_path: str, strict: bool = False) -> int:
    overall_rc = 0
    for cpu in ("main", "sub"):
        try:
            ref_events = cmp_io.parse_iolog(ref_path, cpu)
        except cmp_io.FormatError as e:
            print(f"エラー: 基準ログの読み込みに失敗（{cpu}）: {e}", file=sys.stderr)
            return 2
        try:
            mixed_events = cmp_io.parse_iolog(mixed_path, cpu)
        except cmp_io.FormatError as e:
            print(f"エラー: 混成ログの読み込みに失敗（{cpu}）: {e}", file=sys.stderr)
            return 2
        rc = report_cpu_section(cpu, ref_events, mixed_events, strict=strict)
        overall_rc = overall_rc or rc
    return overall_rc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="混成ROM実行のiologを公式基準iologと(cpu,kind,port,pc)だけで"
        "突き合わせ、最初の構造的分岐点を報告する（valueは一切見ない/出さない）。"
        "既定はスピン畳み込み比較(タイミング依存のポーリング回数差は分岐扱いしない)。"
    )
    parser.add_argument("ref", help="基準の .iolog.txt(.gz可、伏せ字済み)")
    parser.add_argument("mixed", help="混成ROMの .iolog.txt(伏せ字済み)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="厳密比較(添字を揃えた完全一致比較。スピン回数の畳み込みをしない旧来モード)",
    )
    args = parser.parse_args()

    try:
        return run(args.ref, args.mixed, strict=args.strict)
    except OSError as e:
        print(f"エラー: ファイルを読めない: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
