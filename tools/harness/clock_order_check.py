#!/usr/bin/env python3
"""
clock_order_check.py — 共通クロック（M6c）が真の発生順を表しているかの検査。

clock_selftest.sh から呼ばれる。単体では以下を検証する:

  1. 一意性: main の iolog / intlog を合わせた clock 値に重複が無い
     （同じ値が二度と返らない、という q88h_clock.h の約束の確認）
  2. 単調性: 同一バッファ（main iolog 節・main intlog 節）内では、
     ファイル出現順（＝ seq の昇順＝記録された順そのもの）と clock の
     大小関係が一致する
  3. 既知の真の前後関係との一致（本命）:
     make_test_rom.py --enable-int が生成する合成ROMは、次の順序が
     プログラムの構造上確定している（ソース参照: make_test_rom.py 冒頭コメント）:

       OUT(E4)[初期アーム] < OUT(E6)[初期アーム]
         < 割り込み受理#1 < OUT(E4)[再アーム#1]
         < 割り込み受理#2 < OUT(E4)[再アーム#2]
         < ...

     つまり k 番目の割り込み受理は、k 番目の OUT(E4) より後、
     (k+1) 番目の OUT(E4) より前に起きたと確定している
     （0番目=初期アーム、1番目以降=ハンドラ内の再アーム）。
     これは main CPU 内で iolog（I/O記録）と intlog（割り込み受理記録）
     という別バッファにまたがる前後関係であり、frame だけでは検証できない
     （1フレームに複数の OUT(E4) が起きうるため）。
     共通クロックが正しく機能していれば、この確定した前後関係が
     clock の大小として観測されるはずである——それを実際に確認する。

わざと壊して検出できることの確認について: q88h_clock_tick を「常に同じ値を
返す」ように壊した版でこのスクリプトを走らせ、検査1（一意性）と検査3
（既知の前後関係）が NG になることを開発時に確認済み
（docs/notes/m6-sub-clock.md 参照）。
"""
import re
import sys


def parse_section(path, section):
    """iolog/intlog のテキスト出力から指定節（main/sub）のイベント行を取り出す。
    各行は '# main' か '# sub' の見出しの下にあり、空白区切りで
    先頭2列が seq, clock という共通レイアウト（q88measure の出力形式）。"""
    events = []
    in_section = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.rstrip("\n")
            if re.match(r"^# (main|sub)$", stripped):
                in_section = (stripped == f"# {section}")
                continue
            if not in_section:
                continue
            if stripped.startswith("#") or not stripped.strip():
                continue
            cols = stripped.split()
            # 先頭2列は seq, clock。3列目 frame、4列目 cpu名（"main"/"sub"）。
            if len(cols) < 4:
                continue
            try:
                seq = int(cols[0])
                clock = int(cols[1])
            except ValueError:
                continue
            events.append({"seq": seq, "clock": clock, "cols": cols})
    return events


def fail(msg):
    print(f"NG: {msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg):
    print(f"OK: {msg}")


def main():
    if len(sys.argv) != 3:
        print(f"使い方: {sys.argv[0]} <iolog.txt> <intlog.txt>", file=sys.stderr)
        sys.exit(2)

    iolog_path, intlog_path = sys.argv[1], sys.argv[2]

    io_main = parse_section(iolog_path, "main")
    io_sub = parse_section(iolog_path, "sub")
    int_main = parse_section(intlog_path, "main")
    int_sub = parse_section(intlog_path, "sub")

    if not io_main:
        fail("iolog main 節にイベントが1件も無い")
    if not int_main:
        fail("intlog main 節にイベントが1件も無い")

    # ---- 検査1: 一意性 ----------------------------------------------------
    all_clocks = [e["clock"] for e in io_main + io_sub + int_main + int_sub]
    if len(all_clocks) != len(set(all_clocks)):
        dupes = len(all_clocks) - len(set(all_clocks))
        fail(f"clock 値に重複が {dupes} 件ある（一意性が壊れている）")
    ok(f"clock 値はすべて一意（{len(all_clocks)}件）")

    # ---- 検査2: 単調性（同一バッファ内で seq の順=clock の順） -------------
    for name, evs in (("iolog main", io_main), ("intlog main", int_main)):
        clocks = [e["clock"] for e in evs]
        if clocks != sorted(clocks):
            fail(f"{name} 節で clock がファイル出現順（=seq順）と一致しない"
                 "（単調増加になっていない）")
    ok("iolog main / intlog main とも、節内では clock がファイル出現順と一致")

    # ---- 検査3: 既知の前後関係（本命） --------------------------------------
    # iolog の列: seq clock frame cpu kind port value pc
    out_e4 = [e for e in io_main
              if e["cols"][4] == "OUT" and e["cols"][5].upper() == "00E4"]
    if len(out_e4) < 2:
        fail(f"OUT(E4) イベントが少なすぎる（{len(out_e4)}件）。"
             "--enable-int の合成ROMを使っているか確認すること")

    n_pairs = min(len(int_main), len(out_e4) - 1)
    if n_pairs < 5:
        fail(f"検証できるペア数が少なすぎる（{n_pairs}件）。frames を増やすこと")

    for k in range(n_pairs):
        before = out_e4[k]["clock"]      # k番目のOUT(E4)（0=初期アーム、以降=再アーム）
        interrupt = int_main[k]["clock"]  # (k+1)番目の割り込み受理
        after = out_e4[k + 1]["clock"]   # (k+1)番目のOUT(E4)（再アーム）
        if not (before < interrupt < after):
            fail(
                f"{k+1}番目の割り込み受理の前後関係が既知の順序と食い違う: "
                f"OUT(E4)#{k}(clock={before}) < 割り込み#{k+1}(clock={interrupt}) "
                f"< OUT(E4)#{k+1}(clock={after}) が成り立たない"
            )
    ok(f"{n_pairs}件すべてで「OUT(E4) < 割り込み受理 < 次のOUT(E4)」という"
       "既知の真の前後関係と clock の大小が一致")

    print()
    print("合格: 共通クロックは main CPU 内での iolog/intlog 横断の"
          "真の発生順を正しく表している。")


if __name__ == "__main__":
    main()
