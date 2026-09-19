#!/usr/bin/env python3
"""PC88Behavior: l4-s1h キーリピート（自動繰り返し）— 測定道具。

事前登録 docs/notes/l4-s1h-key-repeat-preregistration.md
（`c9d5935`）どおりに、キーリピートの遅延・間隔（Q1）、→キーへの
外挿（Q2）、→単発での列79越え（Q3）を測る。

`tools/l4_editor_conform_record.py`（l4-c6、既に確立済みの器具）を
そのまま再利用する: SETTLE（G11のsettle手順）・build_tokens・
run_q88（q88measureの呼び出しとVRAM写しの回収）・diff_cells
（押す前が空白だったセルの座標・件数だけを返す差分）・nonblank_rows。
本ファイルはこれらに薄く積むだけで、q88measureの呼び出し方・写しの
比較方法を作り直さない。

出力してよいもの（CLAUDE.md禁止事項7、l4_editor_conform_record.pyの
docstringと同じ規律）:
  1. 変化したセルの座標(row0,col0)・「押す前が空白だったか」・件数
  2. 押す前が空白だったセルについてだけ、自分で打った文字
     （`q`/`w`）のコード
  3. 上記から計算した集計値（フレームオフセットごとの件数の時系列等）

画面本文（行内容の並びそのもの）・一括ダンプは一切出さない。
写し(.bin)自体は呼び出し元(--workdir、リポジトリ外)に残るが、
本ファイルのどの関数もその中身を読み上げて表示することはしない。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l4_editor_conform_record as ec  # noqa: E402

GAP = 8
D = 10  # 反映の遅れ(docs/spec/l3-main.md 第8節)
Q_KEY = ec.CHAR["q"]      # 04:1
RIGHT_KEY = ec.SPECIAL["RIGHT"]  # 08:2
W_KEY = ec.CHAR["w"]      # 04:7


def _run(romdir, kms, dumps, prefix, total_frames):
    rc, paths, err = ec.run_q88(romdir, kms, dumps, prefix, total_frames)
    if rc != 0:
        return rc, None, err
    return rc, paths, err


# ---- Q1: qキーの繰り返し時系列（G4陽性対照・G5陰性対照もこれで撮れる） ----

def run_sweep(romdir: str, workdir: Path, prefix: str, offsets: list[int],
              hold: "int | None", press_extra: int = 0) -> dict:
    """HOME/CLR後に q を hold フレーム押し、offsets(フレーム、押下開始
    からの相対値)ごとに写しを撮る。hold=None なら q を押さず(G5陰性対照)。
    press_extra: 押し始めのフレームをさらにこの分だけ遅らせる
    (Q4の位相依存確認用。既定0で従来どおり)。
    """
    km, end = ec.build_tokens(["HOME"])
    press_frame = end + 16 + press_extra
    dump_before = press_frame - 2
    dumps = [("d0", dump_before)]
    for i, off in enumerate(offsets):
        dumps.append((f"d{i + 1}", press_frame + off))
    if hold is not None:
        km.append((Q_KEY[0], Q_KEY[1], press_frame, hold))
    total = dumps[-1][1] + 40
    rc, paths, err = _run(romdir, ec.SETTLE + km, dumps, str(workdir / prefix), total)
    if rc != 0:
        return {"rc": rc, "err_tail": err[-300:]}
    d0_path = paths[0]
    series = []
    for off, path in zip(offsets, paths[1:]):
        diffs = ec.diff_cells(d0_path, path)
        blank_new = sum(1 for e in diffs if e["was_blank"])
        series.append({"offset": off, "blank_new_count": blank_new,
                        "total_diff_count": len(diffs)})
    return {"rc": rc, "press_frame": press_frame, "hold": hold, "series": series,
            "_paths": paths}


def run_fault_injection(sweep_result: dict) -> dict:
    """G8: Q1本走の同じ写し(sweep_resultの_paths)に対し、誤った基準
    (D0の代わりにD1=最初の写し)で集計し直す。使い捨ての検査。"""
    paths = sweep_result["_paths"]
    if len(paths) < 3:
        return {"note": "写し不足のため実施できず"}
    d1_path = paths[1]
    wrong_series = []
    for off, path in zip([s["offset"] for s in sweep_result["series"][1:]], paths[2:]):
        diffs = ec.diff_cells(d1_path, path)
        blank_new = sum(1 for e in diffs if e["was_blank"])
        wrong_series.append({"offset": off, "blank_new_count_wrong_baseline": blank_new})
    # 変種B: was_blank条件を外して全変化セルを数える(D0基準のまま)
    d0_path = paths[0]
    no_filter_series = []
    for off, path in zip([s["offset"] for s in sweep_result["series"]], paths[1:]):
        diffs = ec.diff_cells(d0_path, path)
        no_filter_series.append({"offset": off, "all_changed_count": len(diffs)})
    return {"wrong_baseline_series": wrong_series, "no_blank_filter_series": no_filter_series}


# ---- Q2/Q3: →キー、着地列の確認 ----

def _landing_from_marker(before_mark_path: str, after_mark_path: str):
    diffs = ec.diff_cells(before_mark_path, after_mark_path)
    for e in diffs:
        if e["was_blank"]:
            return {"row0": e["row0"], "col0": e["col0"], "char_after": e["char_after"]}
    return None


def run_arrow_arm(romdir: str, workdir: Path, prefix: str, hold: int,
                   start_tokens: list[str] = ("HOME",), press_extra: int = 0) -> dict:
    """start_tokens で起点へ移動した後、→(RIGHT)を hold フレーム押し、
    離した後に目印 w を打って着地セルを座標で返す(Q2の各腕・Q3-main)。
    press_extra: →キーを押すフレームをさらにこの分だけ遅らせる
    (Q4の位相依存確認用。既定0で従来どおり)。
    """
    km, end = ec.build_tokens(list(start_tokens))
    target_frame = end + 16 + press_extra
    dump_before = target_frame - 2
    km.append((RIGHT_KEY[0], RIGHT_KEY[1], target_frame, hold))
    after_target = target_frame + hold + D
    mark_frame = after_target + 24
    km.append((W_KEY[0], W_KEY[1], mark_frame, 4))
    after_mark = mark_frame + 4 + D
    total = after_mark + 30
    dumps = [("before", dump_before), ("aftertarget", after_target), ("aftermark", after_mark)]
    rc, paths, err = _run(romdir, ec.SETTLE + km, dumps, str(workdir / prefix), total)
    if rc != 0:
        return {"rc": rc, "err_tail": err[-300:]}
    before_p, at_p, am_p = paths
    pretarget_diff = ec.diff_cells(before_p, at_p)
    landing = _landing_from_marker(at_p, am_p)
    return {"rc": rc, "hold": hold, "pretarget_diff_count": len(pretarget_diff),
            "landing": landing}


def run_position_check(romdir: str, workdir: Path, prefix: str,
                        start_tokens: list[str]) -> dict:
    """対象キーを押さず、目印 w だけを打って現在位置を確認する(関門P/Q3-P)。"""
    km, end = ec.build_tokens(list(start_tokens))
    mark_frame = end + D
    dump_before = mark_frame - 2
    km.append((W_KEY[0], W_KEY[1], mark_frame, 4))
    after_mark = mark_frame + 4 + D
    total = after_mark + 30
    dumps = [("before", dump_before), ("after", after_mark)]
    rc, paths, err = _run(romdir, ec.SETTLE + km, dumps, str(workdir / prefix), total)
    if rc != 0:
        return {"rc": rc, "err_tail": err[-300:]}
    before_p, after_p = paths
    landing = _landing_from_marker(before_p, after_p)
    return {"rc": rc, "landing": landing}


def run_g11_check(romdir: str, workdir: Path, prefix: str) -> dict:
    """settle(SETTLE内の2回目RETURN)の前後で非空白件数が変化しないことを
    確認する(G11)。SETTLEは frame700 と frame1000 のRETURNなので、
    995(直前)と1030(直後、D込み)で比較する。"""
    dumps = [("before", 995), ("after", 1030)]
    rc, paths, err = _run(romdir, ec.SETTLE, dumps, str(workdir / prefix), 1200)
    if rc != 0:
        return {"rc": rc, "err_tail": err[-300:]}
    before_p, after_p = paths
    nb_before = ec.nonblank_rows(before_p)
    nb_after = ec.nonblank_rows(after_p)
    return {"rc": rc, "unchanged": nb_before == nb_after,
            "nb_before_rowcount": len(nb_before), "nb_after_rowcount": len(nb_after)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom-dir", required=True)
    ap.add_argument("--workdir", required=True, help="写しを書く作業ディレクトリ(リポジトリ外)")
    ap.add_argument("--action", required=True,
                     choices=["g11", "q3p", "sweep", "fault", "arrow", "q3main"])
    ap.add_argument("--prefix", default="run")
    ap.add_argument("--hold", type=int, default=None)
    ap.add_argument("--offsets", default=None, help="カンマ区切りのフレームオフセット")
    ap.add_argument("--start-tokens", default="HOME", help="カンマ区切り(HOME,DOWN,LEFT等)")
    ap.add_argument("--sweep-json", default=None, help="faultアクション用: sweepの出力JSON")
    ap.add_argument("--press-extra", type=int, default=0,
                     help="押し始めのフレームをさらにこの分遅らせる(Q4位相依存確認用)")
    args = ap.parse_args()

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    if args.action == "g11":
        result = run_g11_check(args.rom_dir, workdir, args.prefix)
    elif args.action == "q3p":
        result = run_position_check(args.rom_dir, workdir, args.prefix,
                                     args.start_tokens.split(","))
    elif args.action == "sweep":
        offsets = [int(x) for x in args.offsets.split(",")]
        result = run_sweep(args.rom_dir, workdir, args.prefix, offsets, args.hold,
                            press_extra=args.press_extra)
        # _paths はファイルパス文字列の配列(画面本文ではない)。fault
        # アクションが同じ写しを再解析するために必要なので残す。
    elif args.action == "fault":
        with open(args.sweep_json, encoding="utf-8") as f:
            # ここで読み込むのは "_paths"(ファイルパス文字列の配列)と
            # series(件数)のみ。画面本文は含まない。
            sweep_full = json.load(f)
        result = run_fault_injection(sweep_full)
    elif args.action == "arrow":
        result = run_arrow_arm(args.rom_dir, workdir, args.prefix, args.hold,
                                args.start_tokens.split(","), press_extra=args.press_extra)
    elif args.action == "q3main":
        result = run_arrow_arm(args.rom_dir, workdir, args.prefix, args.hold,
                                ["HOME", "DOWN", "LEFT"], press_extra=args.press_extra)
    else:
        raise SystemExit(2)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("rc", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
