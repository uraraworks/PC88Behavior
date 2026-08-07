#!/usr/bin/env python3
"""
l2_verify_independent.py — FONT.ROM の「意図した字形が入っていること」の二重検査。

docs/spec/l2-font.md 5節②「生成器が出したビットパターンと、unscii-8.hex /
misaki_gothic.bdf から独立に組み直したビットパターンを突き合わせる」を実装する。
`docs/notes/m4-l1-impl.md` の先例（L1での二重検査）と同じく、**検査そのものが
独立であることを実測で示す**ため、`--break-independent-path` で意図的に壊した
状態で実行し、不一致で失敗することを確認できるようにしてある
（実際に壊して確認した記録は docs/notes/l2-font-verify.md）。

半角カナが美咲BDF由来に差し替わったことに伴い（docs/notes/l2-font-misaki-recheck.md）、
この独立実装も追従させてある。片方だけ直すと二重検査が二重でなくなるため。

独立にしている点（`src/l2_font/make_font_rom.py` と比べて）:
  - unscii-8.hex のパースを別の実装（正規表現ではなく行分割 + 手動ニブル変換）で行う
  - 8x8 ASCIIアート → バイト列への変換を別の実装（文字グリッドではなく
    ビット位置ごとの真偽判定の総和）で行う（現在ビルドには使われないが、
    旧経路の独立検査能力として関数自体は残してある）
  - misaki_gothic.bdf のパースを別の実装（行分割の状態機械ではなく、
    ファイル全体への正規表現ブロック抽出）で行う
  - BDFのBBX/BITMAPから8x8セルへの展開を別の実装（生成器はビットマップの
    行を先頭から辿ってセルへ書き込む「前方」変換。ここではセル側の座標
    (行r・列x)から元のビットマップ上の位置を逆算して読みに行く「逆方向」の
    変換にしてあり、計算の向きそのものが違う）で行う
  - セミグラフィックのビット→ブロック展開を別の実装（座標計算の順序が違う）で行う

再利用している点（意図的。データそのものを再入力させる意味は無いため）:
  - `KANA_CODE_TO_UNICODE`・`HALFWIDTH_TO_FULLWIDTH_KATAKANA`・
    `misaki_code_to_unicode`・`latin_code_to_unicode`
    （コード割り当て、docs/notes/l2-code-assignment.md /
    docs/notes/l2-font-misaki-recheck.md）は `src/l2_font/make_font_rom.py`
    からそのまま import する。ここを独立させても「同じ対応表を2回別の変数名で
    書く」だけで検査力が増えない。検査したいのは「BDFの座標系からビットマップへ
    展開するロジックにバグが無いか」であって「コード対応表を写し間違えていないか」
    ではない（この対応表自体は Unicode の標準的な半角/全角互換表であり、
    ROM由来のデータでもない）。

使い方:
  python3 tools/l2_verify_independent.py <FONT.ROMのパス> \
      --unscii-hex <unscii-8.hexのパス> --misaki-bdf <misaki_gothic.bdfのパス>
  python3 tools/l2_verify_independent.py <FONT.ROMのパス> \
      --unscii-hex <path> --misaki-bdf <path> --break-independent-path
      （わざと壊して不一致になることを確認する用。CIには使わない）
"""
import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "l2_font"))
import make_font_rom as gen  # noqa: E402  (データ定義の再利用。上のdocstring参照)

CELL_BYTES = gen.CELL_BYTES
PLANE_BYTES = gen.PLANE_BYTES


def independent_parse_unscii_hex(path):
    """unscii-8.hex を独立実装で読む（正規表現を使わず、行分割+手動変換）。"""
    table = {}
    with open(path, "r") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or ":" not in line:
                continue
            key, data = line.split(":", 1)
            cp = 0
            for ch in key:
                cp = cp * 16 + int(ch, 16)
            # データ部の先頭16文字(8バイト)だけを使う（32文字行はcodepoint0のみ、
            # 今回は未使用。make_font_rom.py側と同じ約束）。
            data = data[:16]
            raw = bytearray()
            for i in range(0, len(data), 2):
                hi = int(data[i], 16)
                lo = int(data[i + 1], 16)
                raw.append(hi * 16 + lo)
            table[cp] = bytes(raw)
    return table


# --------------------------------------------------------------------------
# 美咲BDF（半角カナ63字の現行ソース）— 独立実装
# --------------------------------------------------------------------------
_BDF_BLOCK_RE = re.compile(
    r"^STARTCHAR .*?\n"
    r"ENCODING (-?\d+)\n"
    r"SWIDTH.*?\n"
    r"DWIDTH (-?\d+) -?\d+\n"
    r"BBX (\d+) (\d+) (-?\d+) (-?\d+)\n"
    r"BITMAP\n"
    r"((?:[0-9A-Fa-f]+\n)*)"
    r"ENDCHAR$",
    re.M,
)


def independent_parse_misaki_bdf(path):
    """misaki_gothic.bdf を独立実装で読む。

    生成器側（`make_font_rom.parse_misaki_bdf`）は行を1行ずつ読み進める
    状態機械。ここではファイル全体を一度に読み、正規表現でグリフブロックを
    まとめて抜き出す、という別の道筋にしてある。
    """
    text = pathlib.Path(path).read_text(encoding="ascii", errors="strict")

    ascent_m = re.search(r"^FONT_ASCENT (\d+)$", text, re.M)
    descent_m = re.search(r"^FONT_DESCENT (\d+)$", text, re.M)
    if not ascent_m or not descent_m:
        raise ValueError(f"{path}: FONT_ASCENT/FONT_DESCENT が見つからない")
    ascent = int(ascent_m.group(1))
    descent = int(descent_m.group(1))

    glyphs = {}
    for m in _BDF_BLOCK_RE.finditer(text):
        enc = int(m.group(1))
        dwidth = int(m.group(2))
        w, h, xoff, yoff = (int(m.group(i)) for i in (3, 4, 5, 6))
        bitmap_text = m.group(7)
        rows = bitmap_text.splitlines()  # 各行が16進1バイト以上(末尾の\nは含めない)
        glyphs[enc] = {"dwidth": dwidth, "bbx": (w, h, xoff, yoff), "bitmap": rows}
    return ascent, descent, glyphs


def independent_misaki_glyph_bytes(ascent, descent, glyph, break_it=False):
    """美咲BDFの1グリフを8x8セルのバイト列へ組み立てる独立実装。

    生成器側（`make_font_rom.misaki_glyph_to_rows`）はビットマップの行を
    先頭から辿り、セル側の位置を計算して書き込む「前方」変換。
    ここではセル側の行r・列xを先に総なめし、それぞれについて元の
    ビットマップ上の位置を逆算して読みに行く「逆方向」の変換にしてある。
    さらに、ビット抽出も文字列(2進数の zfill)ではなく整数のビットシフトで行う。
    """
    width, height, xoff, yoff = glyph["bbx"]

    # 各ビットマップ行を、あらかじめ「立っているビットのビット位置集合」に
    # 展開しておく（生成器側は行ごとに文字列へ変換するが、ここでは整数の
    # ビット演算だけで完結させる）。
    row_bits = []
    for hexrow in glyph["bitmap"]:
        n = int(hexrow, 16) if hexrow else 0
        nbits = len(hexrow) * 4
        row_bits.append((n, nbits))

    out = bytearray(CELL_BYTES)
    for r in range(CELL_BYTES):
        y = (ascent - 1) - r
        i = yoff + height - 1 - y  # セル行rが元のビットマップの何行目か
        if break_it:
            i += 1  # わざと壊す: 参照する行を1つずらす
        if not (0 <= i < len(row_bits)):
            continue
        n, nbits = row_bits[i]
        b = 0
        for x in range(CELL_BYTES):
            c = x - xoff
            if not (0 <= c < width and c < nbits):
                continue
            bit = (n >> (nbits - 1 - c)) & 1
            if bit:
                b |= 0x80 >> x
        out[r] = b
    return bytes(out)


def independent_pack_glyph(rows, break_it=False):
    """8x8 ASCIIアート(8行の文字列)を8バイトへ変換する独立実装。

    make_font_rom.rows_to_bytes は「列インデックスxに対してビット(0x80>>x)を立てる」
    実装。ここでは同じ意味を「ビット位置bごとに、そのビットに対応する列の文字を見る」
    という逆向きのループで書き、さらに合計をビット演算ではなく2進文字列の変換
    (int(..., 2)) で求める、という別経路にする。
    """
    out = bytearray(CELL_BYTES)
    for y, row in enumerate(rows):
        bits = "".join("1" if ch == "#" else "0" for ch in row)
        if break_it:
            bits = bits[::-1]  # わざと壊す: ビット順を反転させる
        out[y] = int(bits, 2)
    return bytes(out)


def independent_semigraphic(code):
    """セミグラフィックのブロック展開を独立実装で行う。

    make_font_rom.semigraphic_glyph は「文字グリッドを作ってから8バイトへ変換」の
    2段階。ここでは1段階で直接バイト値を組み立てる（ビット→行バイトの対応表を
    先に作り、行ごとにORで畳み込む）別経路にする。
    """
    # 格子: bit b -> (col=b%2, row=b//2)。列0は左4px(0xF0)、列1は右4px(0x0F)。
    # 行row は画素行 row*2, row*2+1 の2行に効く。
    row_bytes = [0] * 8
    for b in range(8):
        if not ((code >> b) & 1):
            continue
        col = b % 2
        row = b // 2
        mask = 0xF0 if col == 0 else 0x0F
        row_bytes[row * 2] |= mask
        row_bytes[row * 2 + 1] |= mask
    return bytes(row_bytes)


def independent_overline():
    """0x7E（オーバーライン、U+203E）を独立実装で組み立てる。

    make_font_rom.overline_glyph は「8行のASCIIアート文字列を作ってから
    rows_to_bytes で変換する」という他のグリフと同じ経路を通る。
    ここでは経路そのものを変え、ASCIIアートを経由せず整数演算で直接
    バイト列を組む（最上段=0xFF、残り7行=0x00、というビット演算の結果を
    直接 bytes() に渡す）。値が一致していても「文字グリッドの記述」と
    「バイト値の直接計算」という別の道筋から同じ結論に達している。
    """
    return bytes([0xFF] + [0x00] * (CELL_BYTES - 1))


def build_independent_rom(unscii_hex_path, misaki_bdf_path, break_it=False):
    unscii_table = independent_parse_unscii_hex(unscii_hex_path)
    misaki_ascent, misaki_descent, misaki_glyphs = independent_parse_misaki_bdf(misaki_bdf_path)
    ank = bytearray(PLANE_BYTES)
    for code in range(256):
        if code == 0x7E:
            glyph = independent_overline()
        elif code in gen.KANA_CODE_TO_UNICODE:
            cp = gen.misaki_code_to_unicode(code)
            info = misaki_glyphs.get(cp)
            if info is None:
                raise ValueError(f"美咲BDFにU+{cp:04X}が無い（独立実装側）")
            glyph = independent_misaki_glyph_bytes(
                misaki_ascent, misaki_descent, info, break_it=break_it)
        elif 0x21 <= code <= 0x7D:
            cp = gen.latin_code_to_unicode(code)
            data = unscii_table.get(cp)
            if data is None:
                raise ValueError(f"U+{cp:04X} が無い")
            glyph = data
        else:
            glyph = bytes(CELL_BYTES)
        ank[code * CELL_BYTES:(code + 1) * CELL_BYTES] = glyph

    graph = bytearray(PLANE_BYTES)
    for code in range(256):
        graph[code * CELL_BYTES:(code + 1) * CELL_BYTES] = independent_semigraphic(code)

    return bytes(ank) + bytes(graph)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("font_rom", help="make_font_rom.py が生成した FONT.ROM")
    ap.add_argument("--unscii-hex", required=True)
    ap.add_argument("--misaki-bdf", required=True)
    ap.add_argument("--break-independent-path", action="store_true",
                     help="わざと壊して不一致になることを確認する（自己検査用）")
    args = ap.parse_args()

    generator_rom = pathlib.Path(args.font_rom).read_bytes()
    independent_rom = build_independent_rom(
        args.unscii_hex, args.misaki_bdf, break_it=args.break_independent_path)

    if len(generator_rom) != len(independent_rom):
        print(f"NG: サイズが違う 生成器={len(generator_rom)} 独立側={len(independent_rom)}")
        return 1

    mismatches = [i for i in range(len(generator_rom)) if generator_rom[i] != independent_rom[i]]
    if mismatches:
        print(f"NG: {len(mismatches)} バイト不一致（最初の食い違い: オフセット 0x{mismatches[0]:04X}"
              f" 生成器=0x{generator_rom[mismatches[0]]:02X}"
              f" 独立側=0x{independent_rom[mismatches[0]]:02X}）")
        return 1

    print(f"OK: 生成器の出力と独立実装の再構成が {len(generator_rom)} バイト完全一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
