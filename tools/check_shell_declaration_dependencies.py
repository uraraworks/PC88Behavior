#!/usr/bin/env python3
"""同一 local/declare/readonly 文内の代入間依存を検出する。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


DECLARATIONS = {"local", "declare", "readonly"}
SHELL_SUFFIXES = {".sh", ".bash", ".zsh", ".ksh"}
SHELL_SHEBANG = re.compile(rb"^#![^\n]*(?:/|env\s+)(?:ba|z|k)?sh(?:\s|$)")
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
REFERENCE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}|([A-Za-z_][A-Za-z0-9_]*))")
COMMAND_SEPARATORS = {";", "&", "&&", "|", "||", "(", ")", "{", "}"}
COMMAND_KEYWORDS = {"then", "do", "else", "elif"}


def shell_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in {".git", "private"} for part in path.parts):
            continue
        if path.suffix in SHELL_SUFFIXES:
            found.append(path)
            continue
        try:
            with path.open("rb") as stream:
                first = stream.readline(512)
        except OSError:
            continue
        if SHELL_SHEBANG.match(first):
            found.append(path)
    return sorted(found)


def tokens(text: str) -> list[tuple[str, int]]:
    """引用を保ったまま、単純コマンドの判定に必要な字句へ分割する。"""
    result: list[tuple[str, int]] = []
    word: list[str] = []
    word_line = 1
    line = 1
    quote = ""
    escaped = False

    def flush() -> None:
        nonlocal word
        if word:
            result.append(("".join(word), word_line))
            word = []

    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            if quote or escaped:
                if word:
                    word.append(ch)
            else:
                flush()
                result.append((";", line))
            line += 1
            escaped = False
            i += 1
            continue
        if escaped:
            word.append(ch)
            escaped = False
            i += 1
            continue
        if ch == "\\" and quote != "'":
            if not word:
                word_line = line
            word.append(ch)
            escaped = True
            i += 1
            continue
        if quote:
            word.append(ch)
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "'\"":
            if not word:
                word_line = line
            word.append(ch)
            quote = ch
            i += 1
            continue
        if ch == "#" and not word:
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        if ch.isspace():
            flush()
            i += 1
            continue
        if ch in ";&|(){}":
            flush()
            op = ch
            if i + 1 < len(text) and text[i : i + 2] in {"&&", "||"}:
                op = text[i : i + 2]
                i += 1
            result.append((op, line))
            i += 1
            continue
        if not word:
            word_line = line
        word.append(ch)
        i += 1
    flush()
    return result


def findings(path: Path) -> list[tuple[int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    stream = tokens(text)
    result: list[tuple[int, str, str]] = []
    command_start = True
    i = 0
    while i < len(stream):
        token, line = stream[i]
        if token in COMMAND_SEPARATORS or token in COMMAND_KEYWORDS:
            command_start = True
            i += 1
            continue
        if command_start and token in DECLARATIONS:
            assigned: set[str] = set()
            declaration = token
            i += 1
            while i < len(stream) and stream[i][0] not in COMMAND_SEPARATORS:
                word, word_line = stream[i]
                match = ASSIGNMENT.match(word)
                if match:
                    name, value = match.groups()
                    refs = {a or b for a, b in REFERENCE.findall(value)}
                    for ref in sorted(refs & assigned):
                        result.append((word_line, declaration, ref))
                    assigned.add(name)
                i += 1
            command_start = True
            continue
        command_start = False
        i += 1
    return result


def main(argv: list[str]) -> int:
    roots = [Path(arg).resolve() for arg in argv[1:]]
    if not roots:
        roots = [Path(__file__).resolve().parent.parent]
    files = sorted({path for root in roots for path in shell_files(root)})
    print(f"検査開始: shellスクリプト {len(files)} ファイル")
    count = 0
    for path in files:
        for line, declaration, ref in findings(path):
            count += 1
            try:
                shown = path.relative_to(Path.cwd())
            except ValueError:
                shown = path
            print(f"{shown}:{line}: 同一 {declaration} 文内で先行代入 ${ref} を参照")
    if count:
        print(f"検査完了: NG（{count}件検出）")
        return 1
    print(f"検査完了: OK（{len(files)}ファイルを走査、0件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
