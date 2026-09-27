#!/usr/bin/env python3
"""m6ff_keystrokes.py — m6f-f: 6腕の打鍵テキストの唯一の真実の源。

事前登録 docs/notes/m6f-f-type-byte-by-save-mode-preregistration.md 第3節と
追補1 docs/notes/m6f-f-addendum1-bsave-address.md 第2節のとおりの文字列を
ここに定数化する。tools/measure_m6ff.sh・tools/make_m6ff_frozen.py・
tools/check_m6ff_preregistration.py は、いずれもこのモジュールの関数を
呼ぶだけで、打鍵テキストを別々に書き写さない（二重実装を避ける。
m6f-dの tools/check_m6fd_preregistration.py と同じ思想）。

打鍵は小文字で届く（m6f-a 結果(i)・m6f-b 結果E1）ので、ここに置く文字列は
すべて小文字にする。F-B の番地は追補1のとおり --bsave-addr で受け取り、
`&h` + 小文字4桁16進 の形でテキストへ埋め込む（`clear ,&hcfff` の上限は
番地に関係なく固定）。

ROM のワークエリア番地の資料は使わない。番地はマニュアルの言語仕様
（追補1 第1節）だけに基づいて --bsave-addr 経由で親が渡す。
"""
from __future__ import annotations

ARMS = ("F-S", "F-A", "F-P", "F-B", "F-D", "F-0")

# 名前欄に自分で与える4文字（打鍵は小文字で届き、ROMは与えたとおりに
# 格納する — m6f-b 結果E1）。F-0 は何も保存しないので名前を持たない。
ENTRY_NAMES: dict[str, str] = {
    "F-S": "qzs",
    "F-A": "qza",
    "F-P": "qzp",
    "F-B": "qzb",
    "F-D": "qzd",
}

BOOT_FRAME = 300
STIMULUS_FRAME = 700
RUN_FRAMES = 8000  # 事前登録 第2節「フレーム8000」

CLEAR_LINE = "clear ,&hcfff\n"


class KeystrokeError(ValueError):
    pass


def _validate_addr(addr: int) -> int:
    if not isinstance(addr, int) or isinstance(addr, bool):
        raise KeystrokeError("bsave_addr は整数で指定すること")
    if not (0 <= addr <= 0xFFFF):
        raise KeystrokeError("bsave_addr は0〜0xFFFFの範囲で指定すること")
    return addr


def parse_addr(text: str) -> int:
    """10進、または &H/&h 接頭辞つき16進の文字列を整数へ変換する。"""
    s = text.strip()
    if s[:2].lower() == "&h":
        digits = s[2:]
        if not digits:
            raise KeystrokeError("bsave_addr の16進表記が空")
        try:
            return _validate_addr(int(digits, 16))
        except ValueError:
            raise KeystrokeError(f"bsave_addr の16進表記が不正: {text!r}") from None
    try:
        return _validate_addr(int(s, 10))
    except ValueError:
        raise KeystrokeError(f"bsave_addr の表記が不正: {text!r}") from None


def format_addr(addr: int) -> str:
    """&h + 小文字4桁16進（打鍵は小文字で届くため）。"""
    return f"&h{_validate_addr(addr):04x}"


def keystrokes(arm: str, bsave_addr: int | None = None) -> str:
    """腕の打鍵テキストを返す。改行は本物の \\n（呼び出し側が \\n 表記へ
    変換するのは凍結表照合・比較の場面だけに限る）。"""
    if arm not in ARMS:
        raise KeystrokeError(f"未知の腕: {arm}")
    if arm == "F-S":
        return 'new\n10 print 1\nsave "2:qzs"\n'
    if arm == "F-A":
        return 'new\n10 print 1\nsave "2:qza",a\n'
    if arm == "F-P":
        return 'new\n10 print 1\nsave "2:qzp",p\n'
    if arm == "F-B":
        if bsave_addr is None:
            raise KeystrokeError("F-B には bsave_addr が必要")
        a = format_addr(bsave_addr)
        return (CLEAR_LINE
                + f"for i=0 to 15:poke {a}+i,65:next:bsave \"2:qzb\",{a},16\n")
    if arm == "F-D":
        return 'open "2:qzd" for output as #1:print #1,"x":close #1\n'
    if arm == "F-0":
        return ""  # 何も保存しない(陰性対照)。stimulus_frameでの打鍵は無い。
    raise KeystrokeError(f"未知の腕: {arm}")  # pragma: no cover


def escaped(text: str) -> str:
    """凍結表・比較用に \\n をリテラル2文字へ変換する（本物の改行は
    含めない約束。m6f-dのexpected_segment_linesと同じ流儀）。"""
    if "\\" in text:
        raise KeystrokeError("打鍵テキストに想定外のバックスラッシュ")
    return text.replace("\n", "\\n")
