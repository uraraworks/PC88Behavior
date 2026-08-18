#!/usr/bin/env python3
"""tools/check_l3_cond3.py — 適合条件3（サブの割り込み受理が、mainの直接の
I/O操作を直前イベントとしないこと。docs/spec/l3-subrom.md 1.3節・5.2節3項）を
判定する。

`tools/analyze_sub_proto.py` の Q3 と同じ計算（共通クロックで main+sub の
I/Oイベントを1本にマージし、各割り込み受理点の**直前1件**がどちらのCPUの
イベントかを数える）を、判定に必要な数字だけ出す形で行う。

出力は件数のみ。**値（ポートに流れたバイト）は一切出力しない。**

終了コード: 直前1件がmain側だった受理点が0件なら0、1件以上なら1。
受理点が0件のときは判定不能として2を返す（黙って合格にしない）。
"""
import argparse
import bisect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_sub_proto as asp  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--intlog", required=True, type=Path)
    args = ap.parse_args()

    io, _masked = asp.parse_iolog(args.iolog)
    intlog = asp.parse_intlog(args.intlog)

    sub_int = intlog["sub"]
    merged = sorted(io["main"] + io["sub"], key=lambda e: e.clock)
    clocks = [e.clock for e in merged]

    considered = 0
    immediate_main = 0
    for ie in sub_int:
        idx = bisect.bisect_left(clocks, ie.clock)
        if idx == 0:
            continue          # 受理点より前にI/Oイベントが無い
        considered += 1
        if merged[idx - 1].cpu == "main":
            immediate_main += 1

    print(f"sub割り込み受理点: {len(sub_int)} 件（判定対象 {considered} 件）")
    print(f"直前1件がmain側だった受理点: {immediate_main} 件")
    if considered == 0:
        print("判定不能: 判定対象の受理点が0件（この測定では条件3を判定できない）")
        return 2
    return 1 if immediate_main else 0


if __name__ == "__main__":
    raise SystemExit(main())
