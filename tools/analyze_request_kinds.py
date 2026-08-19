#!/usr/bin/env python3
"""PC88Behavior: sub受信run（IN $FC の連続列）の「先頭バイト→run長」対応と、
そのrunに続くFDCコマンドの種別・座標フィールドの位置対応を確定する（m7bj）。

背景: `docs/notes/m7bh-post-bulk-read-coordinates.md` / `m7bi` で、バルク直後の
最初のREADが公式では受信5件の時点で行われることまでは値を見ずに確定した。
本スクリプトはその先——**値そのものを使って**、sub受信runを先頭バイトで
分類し、run長・直後のFDCコマンド種別・座標フィールド(C/H/R)の末尾相対位置が
先頭バイトごとに一意に決まるかを全数集計する。

`tools/analyze_record_boundaries.py` の窓(a)（連続する IN $FC の間に
sub OUT $FB か sub OUT $FD が割り込んだらそこでrunを切る）をそのまま再利用
する（二重実装しない）。ただし record_boundaries.py は「伏せ字済みログ**しか**
受け付けない」設計なのに対し、本スクリプトは逆に**伏せ字されていない生ログ
でなければ動かない**（先頭バイトの値そのものが解析対象のため）。

FDCコマンドの分解は `tools/analyze_write_path.py` の `parse_commands` を
そのまま再利用する（同上、二重実装しない）。

**出力の既定は値を伏せた記号（K00, K01, …）である。** `--emit-spec-table` を
付けたときだけ、先頭バイトの実際の値を含む表を出す（仕様書へ転記する用途）。
`measurements/` へ保存する成果物は記号版だけにすること。

再実行方法:
    python3 tools/analyze_request_kinds.py \\
        --iolog "$TMP/d0.txt" "$TMP/d1.txt" "$TMP/d2.txt" \\
        --label boot files save \\
        --out measurements/m7bj-request-kinds.txt
"""
from __future__ import annotations

import argparse
import bisect
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_record_boundaries as arb  # noqa: E402  (window_a_runs を再利用)
import analyze_write_path as awp  # noqa: E402  (parse_commands を再利用)

Ev = m2s.Ev
DATA_PORTS = ("00FB", "00FC", "00FD")
READ_OPCODE = 0x06  # READ DATA (μPD765/8272 公開コマンド表)


class UnanalyzableError(Exception):
    """入力が本スクリプトの前提(値あり・伏せ字なし)を満たさないときに使う。"""


def check_unredacted(rows: list[Ev]) -> None:
    """データポートに伏せ字(value=None)が残っていたら拒否する。

    record_boundaries.py とは逆方向の検査:
    あちらは「伏せ字されていない値が残っていたら拒否」、
    こちらは「伏せ字されていて値が読めなかったら拒否」。
    どちらも「入力の前提を検出器自身が検査してから解析する」という
    同じ規律（クリーンルーム規律・検出力の自己確認）に基づく。
    """
    masked = [e for e in rows if e.port in DATA_PORTS and e.value is None]
    if masked:
        raise UnanalyzableError(
            f"データポート({sorted({e.port for e in masked})})に伏せ字(--)が"
            f"{len(masked)}件含まれる。この解析は値を必要とするため、伏せ字済み"
            f"ログでは実行できない。生ログ(リポジトリの外の一時ディレクトリ)を"
            f"使うこと。"
        )


@dataclass
class RunInfo:
    label: str
    head: int
    length: int
    values: list[int]          # 内部計算専用。標準出力にも --out にも生値のまま出さない
    command: awp.Command | None
    gap: int | None            # run終了clockから直後コマンドclockまでの差


def collect_runs(rows: list[Ev], label: str) -> list[RunInfo]:
    sub_rows = [e for e in rows if e.cpu == "sub"]
    fc_idx = arb.sub_fc_indices(sub_rows)
    runs_idx = arb.window_a_runs(sub_rows, fc_idx)
    cmds = awp.parse_commands(rows)
    cmd_clocks = [c.clock for c in cmds]

    # 実測(m7bj)で判明した経緯: runの直後に来る「最も近い」FDCコマンドは
    # 単純な1:1対応ではない。1つのrunのあとにSEEK/SENSE_INTERRUPT/
    # SENSE_DRIVE_STATUSといった準備コマンドの束が挟まり、そのバッチの
    # 中に READ DATA/WRITE系が1回だけ現れる（docs/spec/l3-subrom.md
    # 1.26〜1.29節の手順どおり）。そのため「次のrunが始まるまでの区間に
    # READ/WRITE系コマンドが現れるか」で判定する(最初に出た1件を採る)。
    run_end_clocks = []
    for run in runs_idx:
        values = [sub_rows[i].value for i in run]
        if any(v is None for v in values):
            raise UnanalyzableError(f"{label}: run内に伏せ字イベントが混在している")
        run_end_clocks.append(sub_rows[run[-1]].clock)

    infos: list[RunInfo] = []
    for idx, run in enumerate(runs_idx):
        values = [sub_rows[i].value for i in run]
        end_clock = run_end_clocks[idx]
        window_end = (
            sub_rows[runs_idx[idx + 1][0]].clock
            if idx + 1 < len(runs_idx)
            else None
        )
        lo = bisect.bisect_right(cmd_clocks, end_clock)
        hi = (
            bisect.bisect_left(cmd_clocks, window_end)
            if window_end is not None
            else len(cmds)
        )
        cmd = None
        for c in cmds[lo:hi]:
            if c.opcode == READ_OPCODE or c.opcode in awp.WRITE_OPCODES:
                cmd = c
                break
        gap = (cmd.clock - end_clock) if cmd is not None else None
        infos.append(RunInfo(label, values[0], len(values), values, cmd, gap))
    return infos


def categorize(cmd: awp.Command | None) -> str:
    if cmd is None:
        return "なし"
    if cmd.opcode == READ_OPCODE:
        return "READ"
    if cmd.opcode in awp.WRITE_OPCODES:
        return "WRITE"
    return "その他"


def offset_stats(
    targets: list[tuple[list[int], int, int, int]]
) -> tuple[list[int], list[int], int]:
    """targets: [(run全体の値列, C, H, R), ...]。

    戻り値: (lt_counts, r_counts, total)。lt_counts[offset] は
    「run末尾から offset 個手前の値が (v>>1==C and v&1==H) を満たす」件数、
    r_counts[offset] は「同じ位置の値が R と一致する」件数。
    offset 0 = run末尾(最後に受信したバイト)。
    """
    total = len(targets)
    if total == 0:
        return [], [], 0
    minlen = min(len(values) for values, _, _, _ in targets)
    lt_counts = [0] * minlen
    r_counts = [0] * minlen
    for values, c, h, r in targets:
        n = len(values)
        for offset in range(minlen):
            v = values[n - 1 - offset]
            if (v >> 1) == c and (v & 1) == h:
                lt_counts[offset] += 1
            if v == r:
                r_counts[offset] += 1
    return lt_counts, r_counts, total


def best_offset(counts: list[int], total: int) -> tuple[int | None, int]:
    """countsの中で最も一致件数が多いoffsetを返す(offset, count)。
    total==0 または counts が空なら (None, 0)。"""
    if not counts or total == 0:
        return None, 0
    best_i = max(range(len(counts)), key=lambda i: counts[i])
    return best_i, counts[best_i]


def fmt_offset(offset: int | None) -> str:
    if offset is None:
        return "(対象なし)"
    return "0(末尾)" if offset == 0 else f"-{offset}"


def fmt_position(offset: int | None, count: int, total: int) -> str:
    if offset is None or total == 0:
        return "未確定(対象なし)"
    tag = fmt_offset(offset)
    if count == total:
        return f"位置{tag}で{count}/{total}"
    return f"未確定(最良でも位置{tag}で{count}/{total})"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--iolog", nargs="+", required=True, type=Path)
    ap.add_argument("--label", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=None, help="省略時は標準出力")
    ap.add_argument(
        "--emit-spec-table",
        action="store_true",
        help="先頭バイトの実際の値を含む表を出す(仕様書への転記用。既定では出さない)",
    )
    args = ap.parse_args()
    if len(args.iolog) != len(args.label):
        print("--iolog と --label の数が違う", file=sys.stderr)
        return 2

    all_infos: list[RunInfo] = []
    per_label: dict[str, int] = {}
    for path, label in zip(args.iolog, args.label):
        rows, _masked = m2s.parse_iolog(path)
        try:
            check_unredacted(rows)
            infos = collect_runs(rows, label)
        except UnanalyzableError as ex:
            msg = f"解析不可: {label}: {ex}"
            print(msg, file=sys.stderr)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(msg + "\n", encoding="utf-8")
            else:
                print(msg)
            return 3
        all_infos.extend(infos)
        per_label[label] = len(infos)

    lines: list[str] = []
    w = lines.append
    w("# 要求種別テーブル(先頭バイト→run長→直後FDCコマンド)")
    w("")
    w(f"対象ログ: {', '.join(args.label)}")
    for label, n in per_label.items():
        w(f"  {label}: 受信run {n}件")
    w(f"合計run数: {len(all_infos)}")
    w("")

    heads = sorted({info.head for info in all_infos})
    symbol_of = {h: f"K{idx:02d}" for idx, h in enumerate(heads)}
    w(f"相異なる先頭バイト: {len(heads)}種")
    w("")

    exceptions = 0
    for h in heads:
        infos = [i for i in all_infos if i.head == h]
        lengths = sorted({i.length for i in infos})
        unique = len(lengths) == 1
        if not unique:
            exceptions += 1
        length_repr = str(lengths[0]) if unique else f"不一致{lengths}"

        cats = Counter(categorize(i.command) for i in infos)
        cats_repr = ", ".join(f"{k}:{v}" for k, v in sorted(cats.items(), key=lambda kv: -kv[1]))

        targets = []
        for i in infos:
            cmd = i.command
            if cmd is None or cmd.param_values is None or len(cmd.param_values) < 4:
                continue
            if categorize(cmd) not in ("READ", "WRITE"):
                continue
            c, h_, r = cmd.param_values[1], cmd.param_values[2], cmd.param_values[3]
            targets.append((i.values, c, h_, r))
        lt_counts, r_counts, total = offset_stats(targets)
        lt_off, lt_cnt = best_offset(lt_counts, total)
        r_off, r_cnt = best_offset(r_counts, total)

        sym = symbol_of[h]
        head_note = f"(0x{h:02X})" if args.emit_spec_table else ""
        w(f"## {sym}{head_note}: 件数={len(infos)} 長さ={length_repr} "
          f"直後コマンド種別=[{cats_repr}]")
        w(f"   論理トラック規則(v>>1==C, v&1==H)の一致位置: "
          f"{fmt_position(lt_off, lt_cnt, total)}")
        w(f"   R一致位置: {fmt_position(r_off, r_cnt, total)}")
        w("")

    w(f"先頭バイトがrun長を一意に決めない例外: {exceptions}件")

    text = "\n".join(lines) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
