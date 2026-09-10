#!/usr/bin/env python3
"""tools/count_fdc_abort_marks.py — 自作サブROMの診断ポート $F9 に立つ
「FDC_ABORT」系の印を数える。

事前登録: docs/notes/m7kt-abort-scene-attribution-preregistration.md
（記録するものの定義・記録しないものの定義はここに固定してある）。

## 印の約束（src/l3_service/make_subrom.py 側の実装。値そのものは
   参考のためコメントに書くが、このスクリプトの出力には一度も出さない）

  - `0xA5` … 既存の FDC_TIMEOUT_MARK（FDCステータス待ちのタイムアウト）
  - `0x5A` … FDC_IN 側で FDC_ABORT が立った
  - `0x5B` … FDC_OUT 側で FDC_ABORT が立った

いずれも sub CPU の `OUT $F9` として現れる。

## コマンド種別の復号

FDCコマンドのオペコード→種別名の復号は `tools/analyze_write_path.py` の
`NAMES` / `parse_commands()` をそのまま import して使う（二重実装しない）。
`tools/analyze_fdc_ports.py` は $FA/$FB のビット相関・バースト構造を見る
解析器であり、コマンド種別の復号ロジックそのものは持っていない
（NAMES/PARAM_COUNTS の定義は analyze_write_path.py 側にある）。

## 出力

TSV（`キー<TAB>値` の行の並び。`tools/hash_io_stream.py` と同じ形）。

  total              … 0x5A と 0x5B の合計件数
  in_side / out_side … それぞれの件数
  timeout_derived    … 直前のsub側I/Oイベントが OUT $F9 の 0xA5 であるものの件数
  by_command.<name>  … 印より前に最後に発行されたFDCコマンドの復号種別名ごとの件数
                        （コマンドが1つも無ければ by_command.NONE）
  read_data          … by_command.READ DATA と同じ値（本測定の主指標）
  f9_events          … $F9 へのイベント総数（0xA5 を含む）
  events             … ログ中の全イベント数（--from-frame を指定した場合はその窓の中）

**出力に一度も出さないもの**（事前登録の禁止節どおり）:
  - $FB の値、シリンダ・セクタ・PCN・結果ステータスの生の値
  - 診断ポートへ書いた値そのもの（0x5A/0x5B/0xA5 の literal）
  - イベントの時刻の値・時刻差（frame番号を含む）
  - 画面本文

使い方:
    tools/count_fdc_abort_marks.py <iolog>
    tools/count_fdc_abort_marks.py <iolog> --from-frame 1200

`--from-frame N` は測定時の `--io-log-from-frame`（採取自体を遅らせる版）
とは別物で、**採取済みの生ログを後処理で frame>=N に絞る**版。既定は窓なし。

終了コード: 正常 0 / 入力・復号エラー 2
"""
from __future__ import annotations

import argparse
import bisect
import sys
from pathlib import Path

# analyze_write_path.py / analyze_main_to_sub.py と同じディレクトリから import。
# コマンド種別の復号ロジックを二重実装しないための唯一の依存。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_write_path as awp  # noqa: E402

PORT_F9 = "00F9"
MARK_IN = 0x5A
MARK_OUT = 0x5B
MARK_TIMEOUT = 0xA5


class AnalysisError(Exception):
    """入力ログから安全に集計できない場合。メッセージに生バイトを含めない。"""


def load_rows(path: Path, from_frame: int | None) -> list:
    rows, _masked = m2s.parse_iolog(path)
    if from_frame is not None:
        rows = [e for e in rows if e.frame >= from_frame]
    return rows


def _command_before(cmds_clocks: list[int], cmds: list, clock: int):
    """clock より前に開始した最後のFDCコマンドを返す（無ければ None）。"""
    idx = bisect.bisect_left(cmds_clocks, clock) - 1
    if idx < 0:
        return None
    return cmds[idx]


def analyze(rows: list) -> dict:
    sub_events = [e for e in rows if e.cpu == "sub"]

    marks = [
        e for e in sub_events
        if e.kind == "OUT" and e.port == PORT_F9 and e.value in (MARK_IN, MARK_OUT)
    ]
    f9_events = [e for e in rows if e.port == PORT_F9]

    cmds: list = []
    if marks:
        try:
            cmds = awp.parse_commands(rows)
        except awp.SafeError:
            # SafeError のメッセージには公開コマンド表に無いオペコードの
            # 値が生のまま入ることがある（analyze_write_path.py 側の設計）。
            # このツールの禁止事項（コマンドの生バイトを出さない）に触れる
            # ので、詳細は握りつぶし、一般化したメッセージだけ伝える。
            raise AnalysisError(
                "FDCコマンド列を復号できない"
                "（$FBが伏せ字化されているか、公開コマンド表に無い語を含む）"
            ) from None
    cmds_clocks = [c.clock for c in cmds]

    in_side = sum(1 for e in marks if e.value == MARK_IN)
    out_side = sum(1 for e in marks if e.value == MARK_OUT)

    sub_index = {id(e): i for i, e in enumerate(sub_events)}
    timeout_derived = 0
    for e in marks:
        i = sub_index[id(e)]
        if i > 0:
            prev = sub_events[i - 1]
            if prev.kind == "OUT" and prev.port == PORT_F9 and prev.value == MARK_TIMEOUT:
                timeout_derived += 1

    by_command: dict[str, int] = {}
    for e in marks:
        cmd = _command_before(cmds_clocks, cmds, e.clock)
        name = awp.NAMES.get(cmd.opcode, "UNKNOWN") if cmd is not None else "NONE"
        by_command[name] = by_command.get(name, 0) + 1

    read_data = by_command.get("READ DATA", 0)

    return {
        "total": len(marks),
        "in_side": in_side,
        "out_side": out_side,
        "timeout_derived": timeout_derived,
        "by_command": by_command,
        "read_data": read_data,
        "f9_events": len(f9_events),
        "events": len(rows),
    }


def format_tsv(result: dict) -> str:
    lines = [
        f"total\t{result['total']}",
        f"in_side\t{result['in_side']}",
        f"out_side\t{result['out_side']}",
        f"timeout_derived\t{result['timeout_derived']}",
    ]
    for name in sorted(result["by_command"]):
        lines.append(f"by_command.{name}\t{result['by_command'][name]}")
    lines.append(f"read_data\t{result['read_data']}")
    lines.append(f"f9_events\t{result['f9_events']}")
    lines.append(f"events\t{result['events']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("iolog", type=Path, help="対象の .iolog.txt (.gz可)")
    ap.add_argument("--from-frame", type=int, default=None, metavar="N",
                     help="採取済みログを frame>=N に絞ってから集計する後処理の窓"
                          "（既定: 窓なし）")
    args = ap.parse_args()

    try:
        rows = load_rows(args.iolog, args.from_frame)
    except OSError as exc:
        print(f"エラー: ログを読めない: {exc}", file=sys.stderr)
        return 2

    if not rows:
        print("エラー: 対象窓にイベントが0件", file=sys.stderr)
        return 2

    try:
        result = analyze(rows)
    except AnalysisError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(format_tsv(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
