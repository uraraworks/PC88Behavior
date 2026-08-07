#!/usr/bin/env python3
"""tools/cmp_io.py — q88measure --io-log の出力を比較する。

docs/spec/l1-ipl.md 第6節「実装要件（適合条件）」・第7節「検証方法」を
実行可能にしたもの。自作 IPL を書く前に用意する物差し。

使い方:
    tools/cmp_io.py <基準.iolog.txt> <対象.iolog.txt> [--cpu main|sub] [--with-in]

既定（OUT のみ）が適合条件そのもの。--with-in は構造比較の参考情報であり、
適合条件ではない（第6節「比較しないもの」）。

終了コード: 一致 0 / 不一致 1 / 使い方の誤り 2
"""

import argparse
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    seq: int
    frame: int
    cpu: str
    kind: str  # "IN" / "OUT"
    port: str
    value: str
    pc: str


class FormatError(Exception):
    """入力ファイルの書式が壊れている。"""


def parse_iolog(path: str, cpu: str) -> list[Event]:
    """指定 CPU (main/sub) の節から全イベントを読み取る。

    節が見つからない、または列数が足りない行があれば FormatError。
    """
    section_header = f"# {cpu}"
    events: list[Event] = []
    in_section = False
    section_found = False
    saw_any_line_in_section = False

    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.rstrip("\n")
            stripped = line.strip()

            if stripped == section_header:
                in_section = True
                section_found = True
                continue

            if not in_section:
                continue

            # 次の節（"# main" / "# sub"）に入ったら終わり
            if stripped.startswith("# ") and stripped not in (
                section_header,
                "# seq  frame  cpu   kind  port  value  pc",
            ):
                # 他のコメント行（ヘッダ再掲・注記等）は読み飛ばす
                if stripped.startswith("# main") or stripped.startswith("# sub"):
                    break
                continue

            if stripped == "" or stripped.startswith("#"):
                continue

            saw_any_line_in_section = True
            fields = stripped.split()
            if len(fields) != 7:
                raise FormatError(
                    f"{path}:{lineno}: 列数が7でない({len(fields)}列): {stripped!r}"
                )
            seq_s, frame_s, ev_cpu, kind, port, value, pc = fields
            if kind not in ("IN", "OUT"):
                raise FormatError(
                    f"{path}:{lineno}: kind が IN/OUT でない: {stripped!r}"
                )
            try:
                seq = int(seq_s)
                frame = int(frame_s)
            except ValueError as e:
                raise FormatError(f"{path}:{lineno}: seq/frame が整数でない: {stripped!r}") from e

            events.append(Event(seq, frame, ev_cpu, kind, port, value, pc))

    if not section_found:
        raise FormatError(f"{path}: '# {cpu}' 節が見つからない")

    _ = saw_any_line_in_section  # 0件自体はエラーにしない（節はあるが本当に0件の場合がある）
    return events


def filter_out_only(events: list[Event]) -> list[Event]:
    return [e for e in events if e.kind == "OUT"]


def fold_in_runs(events: list[Event]) -> list[Event]:
    """--with-in 用: 同一ポートへの連続する IN を1件に畳む（最後の値を残す）。

    OUT はそのまま通す。連続 IN の連なりが終わったら、その連なりの
    最後のイベント（ポートと最終値）だけを列に加える。
    """
    result: list[Event] = []
    run: list[Event] = []

    def flush():
        if run:
            result.append(run[-1])
            run.clear()

    for e in events:
        if e.kind == "IN":
            if run and run[-1].port == e.port:
                run.append(e)
            else:
                flush()
                run.append(e)
        else:
            flush()
            result.append(e)
    flush()
    return result


def classify_mismatch(base: list[Event], target: list[Event], idx: int) -> str:
    """idx 番目（0-indexed）での食い違いの種類を分類する。"""
    base_has = idx < len(base)
    target_has = idx < len(target)
    if not base_has and target_has:
        return "対象側が長い（余分）"
    if base_has and not target_has:
        return "基準側が長い（対象に足りない）"
    b, t = base[idx], target[idx]
    if b.port != t.port:
        return "ポートが違う"
    if b.value != t.value:
        return "値が違う"
    return "種別が違う" if b.kind != t.kind else "不明な差異"


def fmt_event(e: Event | None) -> str:
    if e is None:
        return "(なし)"
    return f"{e.kind:<3} port={e.port} value={e.value}  (seq={e.seq} frame={e.frame} pc={e.pc})"


def report_mismatch(base: list[Event], target: list[Event], mode_label: str) -> int:
    n = min(len(base), len(target))
    first_diff = None
    for i in range(n):
        b, t = base[i], target[i]
        if b.port != t.port or b.value != t.value or b.kind != t.kind:
            first_diff = i
            break
    if first_diff is None:
        if len(base) != len(target):
            first_diff = n  # 片方が末尾で尽きている
        else:
            # 完全一致
            return 0

    kind = classify_mismatch(base, target, first_diff)

    print(f"[{mode_label}] 不一致: {first_diff + 1} 件目で食い違い")
    print(f"  種類: {kind}")
    print(f"  基準側: 総 {len(base)} 件 / 対象側: 総 {len(target)} 件")
    print(f"  ここまで一致: {first_diff} 件")
    print()

    lo = max(0, first_diff - 5)
    hi = min(max(len(base), len(target)), first_diff + 6)
    print(f"  --- 前後 (基準側 index {lo+1}〜{hi} ) ---")
    for i in range(lo, hi):
        marker = "→" if i == first_diff else " "
        b = base[i] if i < len(base) else None
        print(f"  {marker} 基準[{i+1:>6}] {fmt_event(b)}")
    print()
    print(f"  --- 前後 (対象側 index {lo+1}〜{hi} ) ---")
    for i in range(lo, hi):
        marker = "→" if i == first_diff else " "
        t = target[i] if i < len(target) else None
        print(f"  {marker} 対象[{i+1:>6}] {fmt_event(t)}")

    return 1


def run_compare(base_events: list[Event], target_events: list[Event], with_in: bool) -> int:
    if with_in:
        base_seq = fold_in_runs(base_events)
        target_seq = fold_in_runs(target_events)
        label = "--with-in（参考情報。これは適合条件ではない）"
    else:
        base_seq = filter_out_only(base_events)
        target_seq = filter_out_only(target_events)
        label = "OUT のみ（適合条件）"

    if len(base_seq) == 0 and len(target_seq) == 0:
        print(f"[{label}] エラー: 両側とも比較対象のイベントが0件。比較になっていない。", file=sys.stderr)
        return 2

    rc = report_mismatch(base_seq, target_seq, label)
    if rc == 0:
        kind_word = "イベント" if with_in else "OUT"
        print(f"[{label}] 一致（{kind_word} {len(base_seq)}件）")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="q88measure --io-log の出力2つを比較する（docs/spec/l1-ipl.md 第6・7節）"
    )
    parser.add_argument("base", help="基準の .iolog.txt")
    parser.add_argument("target", help="対象の .iolog.txt")
    parser.add_argument("--cpu", choices=["main", "sub"], default="main", help="比較する CPU（既定: main）")
    parser.add_argument("--with-in", action="store_true", help="畳んだ IN も含めて構造を比較する（参考。適合条件ではない）")
    args = parser.parse_args()

    try:
        base_events = parse_iolog(args.base, args.cpu)
        target_events = parse_iolog(args.target, args.cpu)
    except FormatError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"エラー: ファイルを読めない: {e}", file=sys.stderr)
        return 2

    return run_compare(base_events, target_events, args.with_in)


if __name__ == "__main__":
    sys.exit(main())
