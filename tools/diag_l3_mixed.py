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

## なぜ値を一切見ずに比較してよいか（クリーンルーム規律）

比較キーは (cpu, kind(IN/OUT), port, pc) の4項目だけで、**value 列は
読み込みはしても比較にも表示にも一切使わない**。CLAUDE.md 禁止事項5は
「データポートの値列を伏せてからコミット・比較・表示する」ことを求めており、
この4項目だけの比較はその伏せ字が既に済んでいる前提で動く
（本ツールは redact_iolog.py 適用後のログしか受け取らない）。
value を使わないので、伏せ字が「--」に潰れていようが元の値のままだろうが
結果は変わらない——つまりこの比較ロジック自体は、伏せ字が正しく効いて
いるかどうかに依存しない設計になっている。

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
  「ポート別内訳」「片側にしか出ないポート」も出す必要があり、これは
  cmp_io.py に無い機能なのでどのみち新規実装になる。

終了コード: 分岐なし 0 / 分岐あり 1 / 使い方の誤り・書式エラー 2
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402


def compare_key(e: "cmp_io.Event") -> tuple:
    """比較キー。value を含めないのが要点(モジュールdocstring参照)。"""
    return (e.cpu, e.kind, e.port, e.pc)


def fmt_key_event(e: "cmp_io.Event") -> str:
    """value を出さない表示。"""
    return f"{e.kind:<3} port={e.port} pc={e.pc}  (seq={e.seq} frame={e.frame})"


def find_first_divergence(ref: list, mixed: list) -> int | None:
    """(cpu,kind,port,pc) だけで先頭から比べ、最初に食い違う0-indexedの
    位置を返す。片方が短ければ、短いほうが尽きた位置を返す。
    完全一致なら None。
    """
    n = min(len(ref), len(mixed))
    for i in range(n):
        if compare_key(ref[i]) != compare_key(mixed[i]):
            return i
    if len(ref) != len(mixed):
        return n
    return None


def print_window(ref: list, mixed: list, idx: int, radius: int = 20) -> None:
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


def port_kind_breakdown(events: list, top: int = 10) -> list[tuple[tuple, int]]:
    c = Counter((e.kind, e.port) for e in events)
    return c.most_common(top)


def ports_only_in(a: list, b: list) -> set:
    """a に現れる (kind,port) のうち b に一度も現れないものの集合。"""
    a_set = {(e.kind, e.port) for e in a}
    b_set = {(e.kind, e.port) for e in b}
    return a_set - b_set


def report_cpu_section(cpu: str, ref: list, mixed: list) -> int:
    """1 CPU 分（main または sub）のレポートを表示する。戻り値: 分岐あり1/なし0。"""
    print(f"\n===== {cpu} =====")
    print(f"  基準側 総イベント数: {len(ref)} 件 / 混成側 総イベント数: {len(mixed)} 件")

    idx = find_first_divergence(ref, mixed)
    rc = 0
    if idx is None:
        print("  分岐なし（(kind,port,pc) の列が先頭から完全一致）")
    else:
        rc = 1
        print(f"  最初の分岐点: 通し番号 {idx + 1} 件目")
        print_window(ref, mixed, idx)

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


def run(ref_path: str, mixed_path: str) -> int:
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
        rc = report_cpu_section(cpu, ref_events, mixed_events)
        overall_rc = overall_rc or rc
    return overall_rc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="混成ROM実行のiologを公式基準iologと(cpu,kind,port,pc)だけで"
                     "突き合わせ、最初の分岐点を報告する（valueは一切見ない/出さない）"
    )
    parser.add_argument("ref", help="基準の .iolog.txt(.gz可、伏せ字済み)")
    parser.add_argument("mixed", help="混成ROMの .iolog.txt(伏せ字済み)")
    args = parser.parse_args()

    try:
        return run(args.ref, args.mixed)
    except OSError as e:
        print(f"エラー: ファイルを読めない: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
