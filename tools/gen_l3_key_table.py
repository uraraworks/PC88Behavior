#!/usr/bin/env python3
"""
gen_l3_key_table.py — M7段階2b: docs/spec/l3-main.md 第9節・第10節の表から、
ROMへ埋め込むキーコード表を機械的に生成する（手で打ち込まない）。

出力: src/l3_main/key_table_gen.asm
  - BASE_CODE_TAB  : 無修飾時の文字コード（96バイト＝12ポート×8ビット、
                      index = port*8 + bit、port は 0x00-0x0B）
  - KANA_CODE_TAB  : カナ保持中のコード
  - GRPH_CODE_TAB  : GRPH保持中のコード
  - CTRL_CODE_TAB  : CTRL保持中のコード
  - CAPS_CODE_TAB  : CAPS保持中のコード
  値 0x00 は「無視する」の目印（キーが存在しない・no_write・未判定・
  そのポート/ビットでは書かない、のいずれか。文字コード表に0x00は
  一つも登場しないため衝突しない）。「変化なし(同)」の欄は無修飾コード
  そのものを入れておく（呼び出し側は毎回そのまま1回引くだけでよい）。

  - SHIFT_CODE_TAB  : SHIFT保持中のコード（M7段階2c、`e915172`の実測値。
                      l3-main.md 第10節SHIFT列）

## 検査（--check）

l3-main.md 第10節の要約表（各修飾ごとの「変化なし/別コード/書かない/
未判定」の件数）は、この文書のどこにも自動生成されておらず独立に書かれた
文である。生成した表からこの4分類の件数を数え直し、要約表の数値
（カナ 17/47/0/0、GRPH 2/56/6/0、CTRL 17/0/43/4、CAPS 38/26/0/0、
SHIFT 18/46/0/0）と一致することを確認する。手で打ち込んだ行の内容と、
独立に書かれた要約文が一致するかどうかを見るので、単なる自己ループには
ならない。

使い方:
    python3 tools/gen_l3_key_table.py                 # 生成
    python3 tools/gen_l3_key_table.py --check          # 集計検査のみ（生成もする）
"""

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "src" / "l3_main" / "key_table_gen.asm"

# ---------------------------------------------------------------------------
# l3-main.md 第9節「キーの文字コード対応表（無修飾）」。
# 64キー、(port, bit, code)。
# ---------------------------------------------------------------------------
BASE_ROWS = [
    (0x00, 0, 0x30), (0x00, 1, 0x31), (0x00, 2, 0x32), (0x00, 3, 0x33),
    (0x00, 4, 0x34), (0x00, 5, 0x35), (0x00, 6, 0x36), (0x00, 7, 0x37),
    (0x01, 0, 0x38), (0x01, 1, 0x39), (0x01, 2, 0x2A), (0x01, 3, 0x2B),
    (0x01, 4, 0x3D), (0x01, 5, 0x2C), (0x01, 6, 0x2E),
    (0x02, 0, 0x40), (0x02, 1, 0x61), (0x02, 2, 0x62), (0x02, 3, 0x63),
    (0x02, 4, 0x64), (0x02, 5, 0x65), (0x02, 6, 0x66), (0x02, 7, 0x67),
    (0x03, 0, 0x68), (0x03, 1, 0x69), (0x03, 2, 0x6A), (0x03, 3, 0x6B),
    (0x03, 4, 0x6C), (0x03, 5, 0x6D), (0x03, 6, 0x6E), (0x03, 7, 0x6F),
    (0x04, 0, 0x70), (0x04, 1, 0x71), (0x04, 2, 0x72), (0x04, 3, 0x73),
    (0x04, 4, 0x74), (0x04, 5, 0x75), (0x04, 6, 0x76), (0x04, 7, 0x77),
    (0x05, 0, 0x78), (0x05, 1, 0x79), (0x05, 2, 0x7A), (0x05, 3, 0x5B),
    (0x05, 4, 0x5C), (0x05, 5, 0x5D), (0x05, 6, 0x5E), (0x05, 7, 0x2D),
    (0x06, 0, 0x30), (0x06, 1, 0x31), (0x06, 2, 0x32), (0x06, 3, 0x33),
    (0x06, 4, 0x34), (0x06, 5, 0x35), (0x06, 6, 0x36), (0x06, 7, 0x37),
    (0x07, 0, 0x38), (0x07, 1, 0x39), (0x07, 2, 0x3A), (0x07, 3, 0x3B),
    (0x07, 4, 0x2C), (0x07, 5, 0x2E), (0x07, 6, 0x2F),
    (0x0A, 5, 0x2D), (0x0A, 6, 0x2F),
]
assert len(BASE_ROWS) == 64, len(BASE_ROWS)

# 第10節の修飾ごとの表。同じ64キーの並びに対して、値は
#   "=" … 変化なし(同) → 無修飾コードをそのまま使う
#   int … 別コード（16進値）
#   None … 書かない(無)、または未判定（この版では無視する）
KANA_ROWS = [
    "=", "=", "=", "=", "=", "=", "=", "=",
    "=", "=", "=", "=", "=", "=", "=",
    0xDE, 0xC1, 0xBA, 0xBF, 0xBC, 0xB2, 0xCA, 0xB7,
    0xB8, 0xC6, 0xCF, 0xC9, 0xD8, 0xD3, 0xD0, 0xD7,
    0xBE, 0xC0, 0xBD, 0xC4, 0xB6, 0xC5, 0xCB, 0xC3,
    0xBB, 0xDD, 0xC2, 0xDF, 0xB0, 0xD1, 0xCD, 0xCE,
    0xDC, 0xC7, 0xCC, 0xB1, 0xB3, 0xB4, 0xB5, 0xD4,
    0xD5, 0xD6, 0xB9, 0xDA, 0xC8, 0xD9, 0xD2,
    "=", "=",
]
GRPH_ROWS = [
    0x9A, 0x93, 0x8F, 0x92, 0xE1, 0xE2, 0xE3, 0x98,
    0x91, 0x99, 0x95, 0xE0, 0x96, 0x90, 0x9B,
    0x8A, 0x9E, 0x84, 0x82, 0xE6, 0xE4, 0xE7, 0xEC,
    0xED, 0xE8, 0xEA, 0xEB, 0x8E, 0x86, 0x85, 0xE9,
    0x8D, 0x9C, 0xE5, 0x9F, 0xEE, 0xF0, 0x83, 0x9D,
    0x81, 0xEF, 0x80, None, 0xF1, None, 0x8B, 0x8C,
    0xF7, None, None, None, None, 0xF2, 0xF3, 0xF4,
    0xF5, 0xF6, 0x94, 0x89, 0x87, 0x88, 0x97,
    "=", "=",
]
CTRL_ROWS = [
    "=", "=", "=", "=", "=", "=", "=", "=",
    "=", "=", "=", "=", "=", "=", "=",
    None, None, None, None, None, None, None, None,
    None, None, None, None, None, None, None, None,
    None, None, None, None, None, None, None, None,
    None, None, None, None, None, None, None, None,
    None, None, None, None, None, None, None, None,
    None, None, None, None, None, None, None,
    "=", "=",
]
CAPS_ROWS = [
    "=", "=", "=", "=", "=", "=", "=", "=",
    "=", "=", "=", "=", "=", "=", "=",
    "=", 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47,
    0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F,
    0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57,
    0x58, 0x59, 0x5A, "=", "=", "=", "=", "=",
    "=", "=", "=", "=", "=", "=", "=", "=",
    "=", "=", "=", "=", "=", "=", "=",
    "=", "=",
]

# 第10節SHIFT列（`e915172`実測、取り直し後）。BASE_ROWSと同じ64キーの並び。
SHIFT_ROWS = [
    "=", "=", "=", "=", "=", "=", "=", "=",
    "=", "=", "=", "=", "=", "=", "=",
    0x7E, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47,
    0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F,
    0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57,
    0x58, 0x59, 0x5A, 0x7B, 0x7C, 0x7D, 0x7E, 0x3D,
    "=", 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27,
    0x28, 0x29, 0x2A, 0x2B, 0x3C, 0x3E, 0x3F,
    "=", "=",
]

for name, rows in [("KANA", KANA_ROWS), ("GRPH", GRPH_ROWS), ("CTRL", CTRL_ROWS),
                    ("CAPS", CAPS_ROWS), ("SHIFT", SHIFT_ROWS)]:
    assert len(rows) == 64, f"{name}: {len(rows)}"

# 第10節・要約表（3行目の集計表）の宣言値。生成した表から数え直した値と
# 突き合わせる（--check）。(変化なし, 別コード, 書かない, 未判定)
DECLARED_SUMMARY = {
    "カナ": (17, 47, 0, 0),
    "GRPH": (2, 56, 6, 0),
    "CTRL": (17, 0, 43, 4),
    "CAPS": (38, 26, 0, 0),
    "SHIFT": (18, 46, 0, 0),
}
# CTRLの「未判定4」は本生成表では無視(None)として扱うため、書かない(無)と
# 未判定はどちらもテーブル上は同じ0になる。集計検査ではこの2つの合計を
# 比べる（元の表の分類自体はl3-main.mdの散文に残っている。第15節参照）。


def build_table(rows):
    tab = [0] * 96
    for (port, bit, base_code), val in zip(BASE_ROWS, rows):
        idx = port * 8 + bit
        if val == "=":
            tab[idx] = base_code
        elif val is None:
            tab[idx] = 0
        else:
            tab[idx] = val
    return tab


def build_base_table():
    tab = [0] * 96
    for port, bit, code in BASE_ROWS:
        tab[port * 8 + bit] = code
    return tab


def summarize(rows):
    same = sum(1 for v in rows if v == "=")
    other = sum(1 for v in rows if isinstance(v, int))
    none_ = sum(1 for v in rows if v is None)
    return same, other, none_


def check():
    ok = True
    for name, rows in [("カナ", KANA_ROWS), ("GRPH", GRPH_ROWS),
                        ("CTRL", CTRL_ROWS), ("CAPS", CAPS_ROWS),
                        ("SHIFT", SHIFT_ROWS)]:
        same, other, none_ = summarize(rows)
        d_same, d_other, d_nowrite, d_undet = DECLARED_SUMMARY[name]
        d_none = d_nowrite + d_undet  # このテーブルでは「書かない」も「未判定」も0にまとめる
        if (same, other, none_) != (d_same, d_other, d_none):
            print(f"NG: {name} の集計が l3-main.md 第10節の要約と食い違う: "
                  f"生成={same}/{other}/{none_} 宣言={d_same}/{d_other}/{d_none}")
            ok = False
        else:
            print(f"OK: {name} 変化なし={same} 別コード={other} 書かない+未判定={none_}"
                  f"（宣言 {d_same}/{d_other}/{d_none} と一致）")
    if len(BASE_ROWS) != 64:
        print("NG: 無修飾コード表の件数が64でない"); ok = False
    else:
        print("OK: 無修飾コード表の件数=64（|K|=64、第9節と一致）")
    # 個別のスポットチェック（代表キー）
    base = build_base_table()
    spot = [
        (0x04, 1, 0x71, "Q 無修飾"),
        (0x0A, 5, 0x2D, "テンキー− 無修飾"),
        (0x07, 7, 0x00, "07:7 no_write→無視"),
        (0x01, 7, 0x00, "01:7 RETURN→表には無い(別扱い)"),
    ]
    shift = build_table(SHIFT_ROWS)
    shift_spot = [
        (0x04, 1, 0x51, "Q SHIFT(第10節 0x20ビットが落ちる)"),
        (0x00, 1, 0x31, "テンキー1 SHIFT=同"),
    ]
    for port, bit, expect, label in shift_spot:
        got = shift[port * 8 + bit]
        if got != expect:
            print(f"NG: スポットチェック失敗 {label}: got={got:#04x} expect={expect:#04x}")
            ok = False
        else:
            print(f"OK: スポットチェック {label} = {got:#04x}")
    for port, bit, expect, label in spot:
        got = base[port * 8 + bit]
        if got != expect:
            print(f"NG: スポットチェック失敗 {label}: got={got:#04x} expect={expect:#04x}")
            ok = False
        else:
            print(f"OK: スポットチェック {label} = {got:#04x}")
    return ok


def render_table(name, tab):
    lines = [f"{name}:"]
    for i in range(0, 96, 8):
        row = ", ".join(f"0x{b:02X}" for b in tab[i:i + 8])
        lines.append(f"    DB {row}")
    return "\n".join(lines)


def generate():
    base = build_base_table()
    kana = build_table(KANA_ROWS)
    grph = build_table(GRPH_ROWS)
    ctrl = build_table(CTRL_ROWS)
    caps = build_table(CAPS_ROWS)
    shift = build_table(SHIFT_ROWS)

    header = (
        "; key_table_gen.asm — tools/gen_l3_key_table.py が生成した。手で編集しない。\n"
        ";\n"
        "; 根拠: docs/spec/l3-main.md 第9節（無修飾コード表）・第10節（修飾ごとの表、\n"
        "; SHIFT列は`e915172`の実測値）。\n"
        "; index = port*8 + bit （port は 0x00-0x0B）。値0x00 = 無視する\n"
        "; （no_write・未判定・キーが存在しないのいずれか。\n"
        "; tools/gen_l3_key_table.py --check で第10節の要約表\n"
        "; （変化なし/別コード/書かない/未判定の件数、SHIFTを含む）との一致を検査済み）。\n"
    )
    body = "\n".join([
        render_table("BASE_CODE_TAB", base),
        render_table("KANA_CODE_TAB", kana),
        render_table("GRPH_CODE_TAB", grph),
        render_table("CTRL_CODE_TAB", ctrl),
        render_table("CAPS_CODE_TAB", caps),
        render_table("SHIFT_CODE_TAB", shift),
    ])
    OUT.write_text(header + "\n" + body + "\n", encoding="utf-8")
    print(f"生成した: {OUT}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="集計検査を表示する（生成もする）")
    args = ap.parse_args()
    generate()
    if args.check:
        ok = check()
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
