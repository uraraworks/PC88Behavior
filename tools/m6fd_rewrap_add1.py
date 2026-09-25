#!/usr/bin/env python3
"""m6f-d 追補1 §2 措置2 — 2回目の測定結果(result.json)のentry_fieldsを、
値を変えずに名前キーで包み直す。

背景: docs/notes/m6f-d-addendum1-terminal-and-reserve.md §2。2回目の測定
(tools/measure_m6fd.sh の当時のバージョン)は entry_fields に欄そのもの
({"pos":…,"bytes9_15":…})を入れていた。tools/derive_m6fd.py は名前キーの
辞書({"QZ7A": {…}})を前提に読むため、2回目の記録を捨てずに包み直して
D7 を導出し直す。

規則: IV-R-* の走は entry_fields を {"QZ7A": 元の値} に、I-* の走は
{"QZ7B": 元の値} に包み直す。値そのもの(bytes9_15・pos)は変えない。
entry_fields が既に名前キーの形(dict の値が dict-or-None かつキーが
既知の名前)であれば触らない(冪等)。対象外の腕(II/III/IV-fill/V)は
entry_fields が null のままのはずなので、そのまま通す。

元のファイルは変更しない。出力は別ファイルへ書く。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

KNOWN_NAMES = ("QZ7A", "QZ7B")


class InputError(ValueError):
    pass


def _name_for_arm(arm: str) -> str | None:
    if arm.startswith("IV-R-"):
        return "QZ7A"
    if arm.startswith("I-"):
        return "QZ7B"
    return None


def _already_wrapped(ef: Any) -> bool:
    if not isinstance(ef, dict):
        return False
    if not ef:
        return True  # 空辞書は「包み直し済みで一致が無かった」とみなす
    return all(k in KNOWN_NAMES for k in ef)


def rewrap_run(run: dict[str, Any]) -> dict[str, Any]:
    ef = run.get("entry_fields")
    if ef is None:
        return run
    if _already_wrapped(ef):
        return run
    name = _name_for_arm(run.get("arm", ""))
    if name is None:
        raise InputError(f"entry_fieldsが名前キーでない走の腕を特定できない: {run.get('arm')!r}")
    out = dict(run)
    out["entry_fields"] = {name: ef}
    return out


def rewrap(doc: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        raise InputError("結果JSONの形式")
    out = dict(doc)
    out["runs"] = [rewrap_run(r) for r in doc["runs"]]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("result", type=Path, help="包み直す前のresult.json")
    ap.add_argument("output", type=Path, help="包み直した後の出力先(別ファイル)")
    args = ap.parse_args()
    try:
        if args.output.resolve() == args.result.resolve():
            raise InputError("出力先は入力と別ファイルにすること")
        doc = json.loads(args.result.read_text(encoding="utf-8"))
        out = rewrap(doc)
        text = json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n"
        with args.output.open("x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError:
        print(f"エラー: 出力先が既に存在する: {args.output}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
