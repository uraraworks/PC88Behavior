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

## なぜ sub 側の比較キーから pc を外すのか（第2の既定変更）

実走ログで main/sub とも公式と**方向・ポート・スピン回数まで完全一致**した
にもかかわらず、本ツールは「sub 側は構造的一致プレフィックス0件・分岐点#1」
と誤報したことがある。原因は sub 側の比較キーにも pc を含めていたこと。

**sub 側の pc は自作サブROM自身が発行した番地である。** 公式サブROMの
番地と一致する道理がない——`docs/spec/l3-subrom.md` 1.14節・5.1節が
明言するとおり、サブ内部の実装（ループ本体をどの番地に置くか）は
「実装の目標にはならない」自由な範囲であり、pc が公式と一致したら
むしろ写経を疑うべき値である。したがって sub 側で pc を比較キーに
含めると、実装が正しく独立に書けているほど「分岐あり」と誤検出する
（本末転倒）。

**一方 main 側は両者とも公式 main ROM（同一バイナリ）を走らせているので、
pc が一致するのが正しい。** 実際に一致する（97件）ことが「本当に同じ
コード列を通っている」ことの検査力を持つ。だから main 側は従来どおり
pc を比較キーに含める。

sub の pc は表示からは消さない——`(参考。比較キーに含まず)` と明示して
残す。デバッグ時に「どの番地で止まっているか」の手がかりとして有用であり、
「値を出さない」原則（value は伏せ字対象）とは別の話だからである
（pc はROM由来のバイト列ではなく実行アドレスの列であり、CLAUDE.md
禁止事項5の対象外）。

旧来の「sub も pc を含める」挙動は `--sub-pc` で選べる形で残す
（行き止まりを消さない規律）。

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

## --brief / --full（既定は --brief）

このツールの実走結果は毎回そのままメインセッションのコンテキストに乗るため、
「判断に使う情報」と「毎回同じで判断に使わない情報」を分けた。既定の
--brief では以下だけを削る（消すのではなく「基準側は同じログから毎回
同じ値が出るので、分岐点周辺以外は省く」という判断）。

- 分岐点前後の窓を前後20件→前後5件に縮める
- 基準側（公式ログ側）の畳み込み後「連長上位5件」「末尾10件」を省く
  （基準はリポジトリ内の同じログから出るので毎回同一。混成側は
  実行のたびに変わるので --brief でも従来どおり出す）

一致プレフィックス・分岐点そのもの・回数差（[要注意]含む）・
片側にしか現れない (kind,port) の一覧は --brief でも必ず出す
（異常や不一致に関わる情報は省かない）。--full で従来どおりの
全量表示に戻る。
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


def pc_is_reference_only(cpu: str, sub_pc: bool) -> bool:
    """sub 側で pc を比較キーから外している(既定)かどうか。

    True のとき、表示上の pc は「参考」であって比較には使っていない
    (モジュールdocstring「なぜ sub 側の比較キーから pc を外すのか」参照)。
    """
    return cpu == "sub" and not sub_pc


def compare_key(e: "cmp_io.Event", cpu: str, sub_pc: bool = False) -> tuple:
    """比較キー。value を含めないのが要点(モジュールdocstring参照)。

    main: (kind, port, pc) — 両側とも公式 main ROM なので pc も一致すべき。
    sub : (kind, port)     — sub の pc は自作実装自身の番地で、公式と
          一致する道理がない(1.14節・5.1節)。既定では比較キーから外す。
          --sub-pc 指定時のみ旧来どおり pc を含める。
    """
    if pc_is_reference_only(cpu, sub_pc):
        return (e.kind, e.port)
    return (e.kind, e.port, e.pc)


def fmt_key_event(e: "cmp_io.Event") -> str:
    """value を出さない表示(厳密比較・--strict 用)。--strict は cpu を
    問わず pc を比較キーに含める旧来モードなので、表示にも常に含める。"""
    return f"{e.kind:<3} port={e.port} pc={e.pc}  (seq={e.seq} frame={e.frame})"


@dataclass(frozen=True)
class Run:
    """畳み込み後の1件。同一 compare_key が連続した回数を保持する。"""

    key: tuple
    count: int
    first: "cmp_io.Event"  # 表示用(seq/frame/pc)は先頭イベントのものを使う


def fold_spins(events: list, cpu: str, sub_pc: bool = False) -> list["Run"]:
    """連続する同一 compare_key を1件に畳み込む(ランレングス圧縮)。

    タイミング依存のポーリング回数を「回数の差」として構造比較から
    分離するための前処理(モジュールdocstring参照)。value は使わない。
    sub 側は既定で pc を畳み込みキーに含めない(隣接する別 pc の同一
    (kind,port) も1つに畳まれる)。main / sub とも同じ規則
    (「同じキー定義で畳み込む」)を適用しており、扱いを変えているのは
    pc をキーに含めるかどうかだけである。
    """
    runs: list[Run] = []
    for e in events:
        k = compare_key(e, cpu, sub_pc)
        if runs and runs[-1].key == k:
            runs[-1] = Run(k, runs[-1].count + 1, runs[-1].first)
        else:
            runs.append(Run(k, 1, e))
    return runs


def fmt_run(r: "Run", cpu: str, sub_pc: bool = False) -> str:
    e = r.first
    cnt = f" x{r.count}" if r.count > 1 else ""
    pc_note = " (参考。比較キーに含まず)" if pc_is_reference_only(cpu, sub_pc) else ""
    return (
        f"{e.kind:<3} port={e.port} pc={e.pc}{pc_note}{cnt}"
        f"  (先頭 seq={r.first.seq} frame={r.first.frame})"
    )


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


def print_window_strict(ref: list, mixed: list, idx: int, radius: int = 5) -> None:
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


def print_window_folded(
    ref_runs: list, mixed_runs: list, idx: int, cpu: str, sub_pc: bool = False, radius: int = 5
) -> None:
    lo = max(0, idx - radius)
    hi = min(max(len(ref_runs), len(mixed_runs)), idx + radius + 1)
    print(f"  --- 基準側 畳み込み後index {lo + 1}〜{hi} ---")
    for i in range(lo, hi):
        marker = "→" if i == idx else " "
        r = ref_runs[i] if i < len(ref_runs) else None
        print(f"  {marker} 基準[{i + 1:>6}] {fmt_run(r, cpu, sub_pc) if r else '(なし)'}")
    print(f"  --- 混成側 畳み込み後index {lo + 1}〜{hi} ---")
    for i in range(lo, hi):
        marker = "→" if i == idx else " "
        r = mixed_runs[i] if i < len(mixed_runs) else None
        print(f"  {marker} 混成[{i + 1:>6}] {fmt_run(r, cpu, sub_pc) if r else '(なし)'}")


def top_runs_by_count(runs: list, top: int = 5) -> list[tuple[int, "Run"]]:
    """畳み込み後の連長(count)が大きい順に上位 top 件を返す。

    戻り値は (畳み込み後index(1始まり), Run) のリスト。分岐点の有無・
    位置とは無関係に常に計算できる(無限スピンの位置を見るための機能。
    欠陥2参照: 分岐点の前後だけを見る窓では、分岐が起きない側の
    巨大スピンが視界に入らなかった)。
    """
    indexed = list(enumerate(runs, start=1))
    indexed.sort(key=lambda ir: ir[1].count, reverse=True)
    return indexed[:top]


def print_top_runs(label: str, runs: list, cpu: str, sub_pc: bool = False, top: int = 5) -> None:
    print(f"\n  --- {label} 畳み込み後 連長上位{top}件（分岐点と無関係に常に表示） ---")
    if not runs:
        print("    (無し)")
        return
    for pos, r in top_runs_by_count(runs, top):
        print(f"    畳み込み後#{pos}  {fmt_run(r, cpu, sub_pc)}")


def print_tail_runs(label: str, runs: list, cpu: str, sub_pc: bool = False, n: int = 10) -> None:
    print(f"\n  --- {label} 畳み込み後 末尾{n}件 ---")
    if not runs:
        print("    (無し)")
        return
    start = max(0, len(runs) - n)
    for i in range(start, len(runs)):
        print(f"    畳み込み後#{i + 1}  {fmt_run(runs[i], cpu, sub_pc)}")


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

    戻り値の各要素: (畳み込み後index, ref側Run, mixed側Run, 比)。
    pc の表示は呼び出し側(print_count_diffs)が cpu/sub_pc を見て決める
    (rr.first.pc は常に持っているので、sub でも「参考」として出せる)。
    """
    diffs = []
    for i in range(matched_prefix):
        rr, mr = ref_runs[i], mixed_runs[i]
        if rr.count != mr.count:
            lo, hi = min(rr.count, mr.count), max(rr.count, mr.count)
            ratio = hi / lo if lo else float("inf")
            diffs.append((i, rr, mr, ratio))
    return diffs


def _fmt_diff_row(i: int, rr: "Run", mr: "Run", ratio: float, cpu: str, sub_pc: bool) -> str:
    e = rr.first
    pc_note = " (参考)" if pc_is_reference_only(cpu, sub_pc) else ""
    return (
        f"    畳み込み後#{i + 1}  {e.kind:<3} port={e.port} pc={e.pc}{pc_note}"
        f"  基準={rr.count}回  混成={mr.count}回  比={ratio:.1f}倍"
    )


def print_count_diffs(diffs: list, cpu: str, sub_pc: bool = False, max_show: int = 30) -> None:
    if not diffs:
        print("    (無し)")
        return
    diffs_sorted = sorted(diffs, key=lambda d: d[3], reverse=True)
    extreme = [d for d in diffs_sorted if d[3] >= EXTREME_RATIO]
    if extreme:
        print(
            f"  [要注意] 比が{EXTREME_RATIO:.0f}倍以上の回数差 {len(extreme)}件"
            "（無限ループの疑い。実際の停止位置を示す最良の手がかり）:"
        )
        for i, rr, mr, ratio in extreme:
            print(_fmt_diff_row(i, rr, mr, ratio, cpu, sub_pc))
    shown = diffs_sorted[:max_show]
    print(
        f"\n  --- 回数差一覧（構造一致・回数不一致、上位{len(shown)}/{len(diffs_sorted)}件、比の降順） ---"
    )
    for i, rr, mr, ratio in shown:
        print(_fmt_diff_row(i, rr, mr, ratio, cpu, sub_pc))


def report_cpu_section(
    cpu: str, ref: list, mixed: list, strict: bool = False, sub_pc: bool = False, brief: bool = True
) -> int:
    """1 CPU 分（main または sub）のレポートを表示する。戻り値: 分岐あり1/なし0。

    brief=True（既定）では、分岐点前後の窓を狭め（前後5件）、基準側の
    連長上位5件・末尾10件（毎回同一ログから出るので判断に使わない）を
    省く。一致プレフィックス・分岐点・回数差（[要注意]含む）・
    片側にしか現れないポート一覧は brief でも必ず出す
    （モジュールdocstring「--brief / --full」参照）。
    """
    radius = 5 if brief else 20
    print(f"\n===== {cpu} =====")
    print(f"  基準側 総イベント数: {len(ref)} 件 / 混成側 総イベント数: {len(mixed)} 件")

    key_note = (
        "(kind,port) のみ。pc は自作サブROM自身の番地で公式と一致する道理がなく"
        "比較キーから除外（仕様書1.14節・5.1節。--sub-pc で従来どおり pc を含める挙動に戻せる）"
        if pc_is_reference_only(cpu, sub_pc)
        else "(kind,port,pc)。両側とも公式 main ROM なので pc も一致すべき"
    )
    print(f"  比較キー: {key_note}")

    rc = 0
    if strict:
        key_fn = lambda e: compare_key(e, cpu, True)  # noqa: E731  strictは常にpc込み
        idx = find_first_divergence(ref, mixed, key_fn)
        if idx is None:
            print("  分岐なし（(kind,port,pc) の列が先頭から完全一致・厳密比較）")
        else:
            rc = 1
            print(f"  最初の分岐点(厳密比較): 通し番号 {idx + 1} 件目")
            print_window_strict(ref, mixed, idx, radius=radius)
    else:
        ref_runs = fold_spins(ref, cpu, sub_pc)
        mixed_runs = fold_spins(mixed, cpu, sub_pc)
        print(
            f"  畳み込み後件数: 基準側 {len(ref_runs)} 件 / 混成側 {len(mixed_runs)} 件"
            "（連続する同一の比較キーをランレングス圧縮。既定の比較モード）"
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
            print("  構造的分岐なし（畳み込み後の比較キーの列が先頭から完全一致）")
        else:
            rc = 1
            print(f"  最初の構造的分岐点: 畳み込み後 通し番号 {idx + 1} 件目")
            print_window_folded(ref_runs, mixed_runs, idx, cpu, sub_pc, radius=radius)

        print("\n  --- 回数差（構造一致・回数不一致の箇所、畳み込み後） ---")
        diffs = count_diff_report(ref_runs, mixed_runs, matched_prefix)
        print_count_diffs(diffs, cpu, sub_pc)

        # 欠陥2対応: 分岐点の前後窓だけでは、分岐が起きない側で回っている
        # 巨大スピン(無限ループ疑い)の位置が視界に入らない。分岐の有無・
        # 位置と無関係に常に表示する。
        # brief（既定）では基準側だけ省く: 基準はリポジトリ内の同じログ
        # から出るので毎回同一で、判断には使わない（--full で表示）。
        # 混成側は実行のたびに変わるので brief でも常に出す。
        if not brief:
            print_top_runs("基準側", ref_runs, cpu, sub_pc)
        print_top_runs("混成側", mixed_runs, cpu, sub_pc)
        if not brief:
            print_tail_runs("基準側", ref_runs, cpu, sub_pc)
        print_tail_runs("混成側", mixed_runs, cpu, sub_pc)
        if brief:
            print(
                "\n  （基準側の連長上位5件・末尾10件は --brief では省略。"
                "--full で表示）"
            )

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


def run(
    ref_path: str, mixed_path: str, strict: bool = False, sub_pc: bool = False, brief: bool = True
) -> int:
    if brief:
        note = "（--brief 既定: 分岐点前後の窓は前後5件"
        if not strict:
            note += "、基準側の連長上位5件・末尾10件は省略"
        note += "。--full で従来どおり全て表示）"
        print(note)
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
        rc = report_cpu_section(cpu, ref_events, mixed_events, strict=strict, sub_pc=sub_pc, brief=brief)
        overall_rc = overall_rc or rc
    return overall_rc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="混成ROM実行のiologを公式基準iologと(kind,port[,pc])だけで"
        "突き合わせ、最初の構造的分岐点を報告する（valueは一切見ない/出さない）。"
        "既定はスピン畳み込み比較(タイミング依存のポーリング回数差は分岐扱いしない)。"
        "main は pc も比較キーに含める。sub は既定で pc を比較キーから除外する"
        "(sub の pc は自作実装自身の番地で公式と一致する道理がないため。"
        "仕様書1.14節・5.1節)。"
    )
    parser.add_argument("ref", help="基準の .iolog.txt(.gz可、伏せ字済み)")
    parser.add_argument("mixed", help="混成ROMの .iolog.txt(伏せ字済み)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="厳密比較(添字を揃えた完全一致比較。スピン回数の畳み込みをしない旧来モード。"
        "cpu を問わず pc を比較キーに含める)",
    )
    parser.add_argument(
        "--sub-pc",
        action="store_true",
        help="sub 側でも pc を比較キーに含める旧来の挙動に戻す"
        "(既定は sub の pc を比較キーから除外。上のdescription参照)",
    )
    parser.add_argument(
        "--brief",
        dest="brief",
        action="store_true",
        help="出力を絞る(既定)。分岐点前後の窓を前後5件にし、基準側(公式ログ側、"
        "毎回同一)の連長上位5件・末尾10件を省く。一致プレフィックス・分岐点・"
        "回数差([要注意]含む)・片側限定ポート一覧は省かない",
    )
    parser.add_argument(
        "--full",
        dest="brief",
        action="store_false",
        help="従来どおりの全量表示に戻す(--brief の反対)",
    )
    parser.set_defaults(brief=True)
    args = parser.parse_args()

    try:
        return run(args.ref, args.mixed, strict=args.strict, sub_pc=args.sub_pc, brief=args.brief)
    except OSError as e:
        print(f"エラー: ファイルを読めない: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
