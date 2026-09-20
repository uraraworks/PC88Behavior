#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/l4_bank_dup_equ.py — bank0.asm と mbf_single.asm/mbf_double.asm を
1本の.asmとして連結してアセンブルする照合器(tools/l4_sqr_bank_conform.py・
tools/l4_sincos_bank_conform.py・tools/l4_atnexplog_bank_conform.py)が
共通で使う、EQU重複行の検出・除去ロジック。

背景(2026-09-20、親からの指摘): bank0.asmは本番ビルドで単独assembleされる
前提でMBF_OPA/OPB/RES等を自前でEQU宣言している(値はmbf_single.asmと同じ)。
上記3照合器はmbf_src(mbf_single.asm+mbf_double.asm)とbank0.asmを連結して
assembleするため、同名EQUの重複定義になる(z80textはラベル重複をエラーに
する)。mbf_src側の定義を生かし、bank0.asm側の重複行だけをこの照合器専用に
取り除く(bank0.asm本体は変更しない、二重実装の解消であって挙動は変えない)。

**以前の実装(3ファイルへ手書きリストDUP_EQU_LINESを複製)の問題**:
bank0.asmにMBF_STATUS/MBF_IN_INT/MBF_OUT_CMPのEQUが追加された(b00bf21)
際、このリストを更新したのはtools/l4_atnexplog_bank_conform.py側だけで、
同じbank0.asmを連結する他の2ファイルは更新されず「ラベル重複: MBF_STATUS」
でアセンブルが落ちる退行になった。固定リストの手書き複製こそが原因だった
ため、3ファイル共通のこのモジュールへ集約し、以後bank0.asm側へEQUが
増えても3ファイルどれも追随不要にする(自動検出)。

**自動検出の方式(ラベル名+値の一致、行の完全一致ではない)**: 最初の実装は
「bank0.asmの行が、mbf_src側にも一字一句同じ行として存在するか」を見て
いたが、mbf_single.asm側はEQUをコメント付き・複数スペースで整形して
いる(例: `MBF_OPA     EQU 0xC000   ; 被演算子A...`)のに対しbank0.asm側は
コメント無し・単一スペース(`MBF_OPA EQU 0xC000`)であり、行として一致
しない。これでは何も検出できず、逆に「何も除去されない」という別の
壊れ方になる(自己検査selftest_negativeで確認済み、下記参照)。ラベル名を
抽出して両側のEQU宣言を突き合わせ、同名かつ同値なら重複とみなす方式に
直した。**値が食い違う同名ラベルは重複とみなさずエラーにする**
(黙って取り除くと本物のバグを隠すため)。
"""
from __future__ import annotations

import re

_EQU_RE = re.compile(r"^(\w+)\s+EQU\s+(0x[0-9A-Fa-f]+)\b")


def _parse_equ(text: str) -> dict[str, str]:
    """テキスト中のEQU宣言を{ラベル名: 値の文字列}へ集める。
    同名が複数回出ても最初の1回だけを採る(そのテキスト内で既に
    重複しているかどうかはz80text.py本体の仕事なので、ここでは判定
    しない)。
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _EQU_RE.match(line.strip())
        if m:
            out.setdefault(m.group(1), m.group(2))
    return out


def dup_equ_lines(mbf_src: str, bank0_text: str) -> list[str]:
    """bank0_text中のEQU行のうち、mbf_src側にも同名で存在するものを
    「bank0_text中の元の行そのもの」のリストで返す(呼び出し側は
    この行を`bank0_text.replace(line + "\\n", "", 1)`で1つずつ取り除く
    想定)。同名だが値が食い違うラベルがあれば、黙って見逃さずに
    SystemExitで止める(値が違うのに重複扱いで消すと、本物の実装差異を
    隠してしまうため)。
    """
    mbf_equ = _parse_equ(mbf_src)
    dups: list[str] = []
    for line in bank0_text.splitlines():
        m = _EQU_RE.match(line.strip())
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        if name not in mbf_equ:
            continue
        if mbf_equ[name] != value:
            raise SystemExit(
                f"EQU値の食い違い: {name} はmbf_src側={mbf_equ[name]} "
                f"bank0.asm側={value}(重複除去の対象にできない、"
                "本物の実装差異の可能性が高い)"
            )
        dups.append(line.strip())
    return dups


def strip_dup_equ(mbf_src: str, bank0_text: str) -> str:
    """bank0_textから、mbf_src側と同名同値のEQU行を取り除いたテキストを
    返す。各行は1回だけ出現する前提(2回以上出現する場合は
    その時点でbank0.asm自体が壊れているとみなしSystemExit)。
    """
    text = bank0_text
    for line in dup_equ_lines(mbf_src, bank0_text):
        old = line + "\n"
        count = text.count(old)
        if count == 0:
            # インデント等の細部が違って厳密一致しない場合はスキップ
            # (呼び出し元のアセンブルで重複エラーとして表面化する)。
            continue
        if count > 1:
            raise SystemExit(f"重複除去の対象行が一意でない: {line!r}")
        text = text.replace(old, "", 1)
    return text
