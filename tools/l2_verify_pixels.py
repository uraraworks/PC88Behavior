#!/usr/bin/env python3
"""
l2_verify_pixels.py — 「font_mem に届いた」ではなく「画面のピクセルまで出た」ことの検査。

docs/spec/l2-font.md 5節②の「意図した字形が入っていること」の検査は、これまで
font_mem（フォントが載るバッファ）までしか届いていなかった（tools/verify_l2.sh の
3節、CRC32比較）。バッファに届いた ≠ 画面に出た、という点はこのプロジェクトで
繰り返し踏んできた型なので、末端＝実際に描画されたピクセルまで見る。

**公式 ROM は不要。** 見るのは次の2つだけ:
  1. FONT.ROM（自作。src/l2_font/make_font_rom.py が生成したもの）
  2. ハーネスが --screenshot で書き出した PPM（自作 IPL の「フォント見本」
     （src/l1_ipl/make_ipl_rom.py --font-sample）を実際に走らせた結果）

やっていること: FONT.ROM のビット列から「画面はこう見えるはずだ」という
640幅×60高（テキスト画面の先頭3行ぶん。フォント見本が文字を書き込んだ範囲）の
白黒ビットマップを、このファイル自身の実装で組み立てる（8x8を縦2倍にして
20ラスタ行セルの上位16ラインに置く、docs/spec/l2-font.md 2節のルールを
このファイル独自に実装）。それを実際のスクリーンショットと比較する。

独立性について: make_ipl_rom.py の emit_font_sample() が「どの文字コードを
どのセルに書いたか」（0x20始まり、80桁×3行、余りは空白埋め）は両者が
合意する必要がある共通の前提（テストパターンの取り決めであって、検証したい
データではない）なのでそのまま踏襲するが、ビットからピクセルへの展開ロジックは
このファイル独自に書く（make_font_rom.py の rows_to_bytes や、コアの
screen-vram*.h のロジックを一切呼ばない・真似ない）。

使い方:
  python3 tools/l2_verify_pixels.py --font-rom <FONT.ROM> --screenshot <shot.ppm>
  python3 tools/l2_verify_pixels.py --font-rom <FONT.ROM> --screenshot <shot.ppm> --break-expected
      （わざと期待画像を壊して不一致になることを確認する用。CIには使わない）
"""
import argparse
import sys

CELL_W = 8
CELL_H = 20          # docs/spec/l2-font.md 2節: 1文字セルは20ラスタライン
GLYPH_ROWS = 8        # 8x8の元グリフ
COLS = 80             # docs/spec/l1-ipl.md 第0節: 80桁
SAMPLE_ROWS = 3        # emit_font_sample が書き込む行数 (ceil(224/80))
CODE_FIRST = 0x20
CODE_COUNT = 0x100 - 0x20   # 224種（0x20-0xFF）
PAD_CODE = 0x20             # 224に満たない末尾セルの埋め文字（emit_font_sampleと同じ約束）

REGION_W = COLS * CELL_W          # 640
REGION_H = SAMPLE_ROWS * CELL_H    # 60


def read_font_rom(path):
    data = open(path, "rb").read()
    if len(data) < 2048:
        raise ValueError(f"FONT.ROMが小さすぎる: {len(data)} バイト")
    return data


def glyph_bytes(font_rom, code):
    """ANK面（先頭2048バイト）からcodeの8バイトを取り出す。"""
    off = code * 8
    return font_rom[off:off + 8]


def code_at_cell(row, col):
    """emit_font_sample()と同じ規則: 0x20始まりで行優先に並べ、
    224種を使い切ったら空白(PAD_CODE)で埋める。"""
    idx = row * COLS + col
    if idx < CODE_COUNT:
        return CODE_FIRST + idx
    return PAD_CODE


def build_expected_bitmap(font_rom):
    """640x60のビットマップ(0/1, 行優先のflatなリスト)を組み立てる。

    ルール（docs/spec/l2-font.md 2節。仕様書はここでは読まず、コメントとして
    自分の理解を書き下すだけ——実装はこのファイル独自）:
      8x8の元グリフを、20ラスタラインのセルの上位16ライン(0-15)へ、
      1ラスタを2回ずつ出す(縦2倍)形で置く。下位4ライン(16-19)は空白。
    """
    bitmap = [0] * (REGION_W * REGION_H)

    def set_px(x, y):
        if 0 <= x < REGION_W and 0 <= y < REGION_H:
            bitmap[y * REGION_W + x] = 1

    for row in range(SAMPLE_ROWS):
        for col in range(COLS):
            code = code_at_cell(row, col)
            glyph = glyph_bytes(font_rom, code)
            cell_x0 = col * CELL_W
            cell_y0 = row * CELL_H
            for gy in range(GLYPH_ROWS):
                byte = glyph[gy]
                for bit in range(8):
                    on = (byte >> (7 - bit)) & 1
                    if not on:
                        continue
                    x = cell_x0 + bit
                    y = cell_y0 + gy * 2
                    set_px(x, y)
                    set_px(x, y + 1)
    return bitmap


def read_ppm_p6(path):
    """外部ライブラリを使わずPPM(P6,バイナリ)を読む。"""
    with open(path, "rb") as f:
        magic = f.readline().strip()
        if magic != b"P6":
            raise ValueError(f"P6形式でない: {magic!r}")

        def next_token_line():
            line = f.readline()
            while line.startswith(b"#"):
                line = f.readline()
            return line

        dims = next_token_line().split()
        w, h = int(dims[0]), int(dims[1])
        maxval_line = next_token_line()
        maxval = int(maxval_line.strip())
        if maxval != 255:
            raise ValueError(f"maxval=255以外は未対応: {maxval}")
        data = f.read(w * h * 3)
        if len(data) != w * h * 3:
            raise ValueError(f"データが足りない: {len(data)} != {w*h*3}")
    return w, h, data


def screenshot_bitmap(w, h, rgb, threshold=128):
    """スクリーンショットの左上 REGION_W x REGION_H を 0/1 ビットマップへ。

    白黒モードなので、輝度がthresholdを超えたら点灯とみなす
    （パレット値そのものをハードコードしない——実装の正確な白のRGB値に
    依存させないための単純な二値化）。
    """
    if w < REGION_W or h < REGION_H:
        raise ValueError(f"スクリーンショットが小さすぎる: {w}x{h}")
    bitmap = [0] * (REGION_W * REGION_H)
    for y in range(REGION_H):
        row_off = y * w * 3
        for x in range(REGION_W):
            o = row_off + x * 3
            r, g, b = rgb[o], rgb[o + 1], rgb[o + 2]
            lum = (r + g + b) // 3
            bitmap[y * REGION_W + x] = 1 if lum > threshold else 0
    return bitmap


def diff_bitmaps(expected, actual):
    mismatches = []
    for i in range(REGION_W * REGION_H):
        if expected[i] != actual[i]:
            mismatches.append(i)
    return mismatches


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--font-rom", required=True, help="src/l2_font/make_font_rom.py が生成したFONT.ROM")
    ap.add_argument("--screenshot", required=True, help="q88measure --screenshot が書き出したPPM(P6)")
    ap.add_argument("--break-expected", action="store_true",
                     help="わざと期待ビットマップの1文字ぶんを反転させ、不一致になることを確認する（自己検査用）")
    args = ap.parse_args()

    font_rom = read_font_rom(args.font_rom)
    expected = build_expected_bitmap(font_rom)

    if args.break_expected:
        # 1文字ぶん(セル(0,1)、80桁目の2文字目)を丸ごとビット反転させる。
        # 「生成器が出すグリフを1文字だけ潰したら、画面比較が落ちるか」の自己検査。
        col, row = 1, 0
        for gy in range(GLYPH_ROWS):
            for bit in range(8):
                x = col * CELL_W + bit
                y = row * CELL_H + gy * 2
                for yy in (y, y + 1):
                    idx = yy * REGION_W + x
                    expected[idx] ^= 1
        print("[l2_verify_pixels] わざと (col=1,row=0) の1文字ぶんを反転させた")

    w, h, rgb = read_ppm_p6(args.screenshot)
    actual = screenshot_bitmap(w, h, rgb)

    mismatches = diff_bitmaps(expected, actual)
    if mismatches:
        first = mismatches[0]
        fy, fx = divmod(first, REGION_W)
        fcol, frow = fx // CELL_W, fy // CELL_H
        print(f"NG: {len(mismatches)} ピクセル不一致"
              f"（最初の食い違い: x={fx} y={fy} セル(col={fcol},row={frow})）")
        return 1

    print(f"OK: 先頭{SAMPLE_ROWS}行ぶん（{REGION_W}x{REGION_H}ピクセル）が"
          f"FONT.ROMからの期待どおりに描画されている（完全一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
