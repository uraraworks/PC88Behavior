#!/usr/bin/env python3
"""m6f-h の打鍵と候補を同じ規則から作る。"""
from __future__ import annotations

import hashlib
import itertools

ARMS = ("H-1", "H-2", "H-3", "H-0")
NAMES = {"H-1": b"qha", "H-2": b"qhb", "H-3": b"qhd", "H-0": b"qhz"}
BOOT_FRAME = 300
STIMULUS_FRAME = 700
# m6f-f は短い打鍵を frame 700 から 8000 まで走らせる。H-2 は約
# 70*(10+6+40+改行)文字で同じ --type 一括注入を用いる。q88measure の既定は hold=4 と gap=4 で1文字8フレーム。
# H-2 の3720文字は約29760フレームを使うので、入力後に約9500を確保する。
# 通常512キー上限は m6f-h 専用の M6FH_LONG_TYPING でだけ拡張する。
FRAMES = {"H-1": 8000, "H-2": 40000, "H-3": 8000, "H-0": 8000}
SEPARATORS = {"CRLF": b"\r\n", "CR": b"\r", "LF": b"\n"}
ENDINGS = {"1A": b"\x1a", "00": b"\x00", "NONE": b""}


def program_lines(arm: str) -> list[str]:
    if arm == "H-1":
        return ['10 print 1', '20 print "ab"']
    if arm == "H-2":
        return [f'{number} print "' + ''.join(chr(65 + (number // 10 + i) % 26) for i in range(40)) + '"'
                for number in range(10, 701, 10)]
    if arm == "H-0":
        return []
    raise ValueError("腕が不正")


def keystrokes(arm: str) -> str:
    if arm not in ARMS:
        raise ValueError("腕が不正")
    if arm == "H-3":
        return 'open "2:qhd" for output as #1:print #1,"abc":print #1,"de":close #1\n'
    return 'new\n' + ''.join(line + '\n' for line in program_lines(arm)) + f'save "2:{NAMES[arm].decode().lower()}",a\n'


def candidate_ids(arm: str) -> tuple[str, ...]:
    if arm == "H-0":
        return ("1A", "00", "EMPTY")
    if arm == 'H-3':
        return tuple('_'.join(parts) for parts in itertools.product(SEPARATORS, ENDINGS))
    return tuple('_'.join(parts) for parts in itertools.product(('LIST', 'TYPED'), SEPARATORS, ENDINGS))


def predicted(arm: str, candidate: str) -> bytes:
    if arm == "H-0":
        return {"1A": b"\x1a", "00": b"\x00", "EMPTY": b""}[candidate]
    if arm == 'H-3':
        sep, ending = candidate.split('_')
        lines = ['abc', 'de']
    else:
        form, sep, ending = candidate.split('_')
        # q88measure は英大文字の --type も非SHIFTの英字キーへ写し、
        # BASICへは小文字で届く（m6f-a結果(i)）。H-2の英大文字設計値も
        # 打鍵後の本文候補では小文字へ正規化する。
        lines = [line.lower() for line in program_lines(arm)]
        if form == "LIST":
            # docs/spec/l4-program.md 第2節 2.1〜2.3: 行番号の空白は保持、
            # PRINT 命令語のみ大文字化し、命令後・引用符内の文字は保持する。
            lines = [line.replace(' print ', ' PRINT ', 1) for line in lines]
        elif form != "TYPED":
            raise ValueError("候補が不正")
    return b''.join(line.encode('ascii') + SEPARATORS[sep] for line in lines) + ENDINGS[ending]


def prediction_digest() -> str:
    h = hashlib.sha256()
    for arm in ARMS:
        for cid in candidate_ids(arm):
            data = predicted(arm, cid)
            h.update(f"{arm}\t{cid}\t{len(data)}\t".encode('ascii'))
            h.update(data)
            h.update(b'\n')
    return h.hexdigest()


def escaped(text: str) -> str:
    return text.replace('\n', '\\n')
