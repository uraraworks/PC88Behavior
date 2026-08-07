#!/usr/bin/env python3
"""
l2_verify_independent.py — FONT.ROM の「意図した字形が入っていること」の二重検査。

docs/spec/l2-font.md 5節②「生成器が出したビットパターンと、unscii-8.hex /
ASCIIアート原本から独立に組み直したビットパターンを突き合わせる」を実装する。
`docs/notes/m4-l1-impl.md` の先例（L1での二重検査）と同じく、**検査そのものが
独立であることを実測で示す**ため、`--break-independent-path` で意図的に壊した
状態で実行し、不一致で失敗することを確認できるようにしてある
（実際に壊して確認した記録は docs/notes/l2-font-verify.md）。

独立にしている点（`src/l2_font/make_font_rom.py` と比べて）:
  - unscii-8.hex のパースを別の実装（正規表現ではなく行分割 + 手動ニブル変換）で行う
  - 8x8 ASCIIアート → バイト列への変換を別の実装（文字グリッドではなく
    ビット位置ごとの真偽判定の総和）で行う
  - セミグラフィックのビット→ブロック展開を別の実装（座標計算の順序が違う）で行う

再利用している点（意図的。データそのものを再入力させる意味は無いため）:
  - `KANA_ART`（63字のASCIIアート原本）と `KANA_CODE_TO_UNICODE`・
    `latin_code_to_unicode`（コード割り当て、docs/notes/l2-code-assignment.md）
    は `src/l2_font/make_font_rom.py` からそのまま import する。
    ここを独立させても「同じ絵を2回別の変数名で書く」だけで検査力が増えない。
    検査したいのは「変換ロジックにバグが無いか」であって「原本を写し間違えていないか」ではない。

使い方:
  python3 tools/l2_verify_independent.py <FONT.ROMのパス> --unscii-hex <unscii-8.hexのパス>
  python3 tools/l2_verify_independent.py <FONT.ROMのパス> --unscii-hex <path> --break-independent-path
      （わざと壊して不一致になることを確認する用。CIには使わない）
"""
import argparse
import pathlib
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


def build_independent_rom(unscii_hex_path, break_it=False):
    unscii_table = independent_parse_unscii_hex(unscii_hex_path)
    ank = bytearray(PLANE_BYTES)
    for code in range(256):
        if code in gen.KANA_CODE_TO_UNICODE:
            cp = gen.KANA_CODE_TO_UNICODE[code]
            glyph = independent_pack_glyph(gen.KANA_ART[cp], break_it=break_it)
        elif 0x21 <= code <= 0x7E:
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
    ap.add_argument("--break-independent-path", action="store_true",
                     help="わざと壊して不一致になることを確認する（自己検査用）")
    args = ap.parse_args()

    generator_rom = pathlib.Path(args.font_rom).read_bytes()
    independent_rom = build_independent_rom(args.unscii_hex, break_it=args.break_independent_path)

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
