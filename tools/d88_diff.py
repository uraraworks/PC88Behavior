#!/usr/bin/env python3
"""2個のD88像を比較し、変更されたデータ部のバイトだけを安全に出す。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.resolve()
sys.path.insert(0, str(HERE))
from d88_read_sector import D88Error, D88Reader, EXPECTED_SECTOR_SIZE  # noqa: E402

# 自己検査は一時領域に作った複製でこの2行だけを反転し、境界検査の
# 検出力を確かめる。通常CLIから危険な動作を選ぶ経路は設けない。
USE_RANGE_OLD_POLICY_FOR_SELFTEST = False
INCLUDE_UNCHANGED_FOR_SELFTEST = False


class DiffError(ValueError):
    pass


def path_is_inside_repo(path: Path) -> bool:
    """未作成ファイルも実体の親を解決し、repo内なら真を返す。"""
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(REPO)
        return True
    except ValueError:
        return False


def _sector_map(image: bytes) -> dict[tuple[int, int, int], bytes]:
    # D88Readerが一度だけ行う構造検査と重複走査を避ける。値はコピーして
    # 返されるため、呼出側からreader内部を変更することはできない。
    sectors = dict(D88Reader(image)._sectors)
    if any(len(payload) != EXPECTED_SECTOR_SIZE for payload in sectors.values()):
        raise D88Error("256バイトでないセクタを含む")
    return sectors


def _coord(key: tuple[int, int, int]) -> dict[str, int]:
    return {"c": key[0], "h": key[1], "r": key[2]}


def compare_images(before: bytes, after: bytes) -> dict[str, object]:
    old_sectors = _sector_map(before)
    new_sectors = _sector_map(after)
    old_keys, new_keys = set(old_sectors), set(new_sectors)
    if old_keys != new_keys:
        # 構成不一致時はその集合差だけを報告し、共通セクタの内容も含めて
        # データ部を1バイトも出さない（事前登録§1-2/3の安全側）。
        return {
            "schema": 1, "sector_layout_equal": False,
            "before_only": [_coord(k) for k in sorted(old_keys - new_keys)],
            "after_only": [_coord(k) for k in sorted(new_keys - old_keys)],
            "changed_sectors": 0, "changed_bytes": 0, "changes": [],
        }
    common = sorted(old_keys & new_keys)
    changes: list[dict[str, object]] = []
    total = 0
    for key in common:
        old, new = old_sectors[key], new_sectors[key]
        if len(old) != len(new):
            raise DiffError(f"同一(C,H,R)のデータ長が不一致: {key}")
        selected = [i for i, (a, b) in enumerate(zip(old, new))
                    if a != b or INCLUDE_UNCHANGED_FOR_SELFTEST]
        if not selected:
            continue
        changed_old = [old[i] for i in selected]
        sector_old_uniform = (len(selected) >= 8 and len(set(changed_old)) == 1)
        ranges: list[dict[str, object]] = []
        start = previous = selected[0]
        for offset in selected[1:] + [len(old) + 1]:
            if offset == previous + 1:
                previous = offset
                continue
            stop = previous + 1
            old_part, new_part = old[start:stop], new[start:stop]
            # 通常は区間に旧値を持たせない。変異フラグは追補2前の
            # 「区間ごとに一様なら1値を出す」挙動だけを再現する。
            old_field = (f"{old_part[0]:02X}"
                         if USE_RANGE_OLD_POLICY_FOR_SELFTEST
                         and len(set(old_part)) == 1 else "withheld")
            ranges.append({"offset": start, "length": stop - start,
                           "new": new_part.hex().upper(), "old": old_field})
            total += stop - start
            start = previous = offset
        sector_change: dict[str, object] = {
            **_coord(key),
            "changed_bytes": sum(int(x["length"]) for x in ranges),
            "ranges": ranges,
        }
        if sector_old_uniform:
            sector_change["old_uniform"] = f"{changed_old[0]:02X}"
        changes.append(sector_change)
    return {
        "schema": 1,
        "sector_layout_equal": True,
        "before_only": [_coord(k) for k in sorted(old_keys - new_keys)],
        "after_only": [_coord(k) for k in sorted(new_keys - old_keys)],
        "changed_sectors": len(changes),
        "changed_bytes": total,
        "changes": changes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    try:
        if path_is_inside_repo(args.output):
            raise DiffError("出力先がリポジトリ内を指している (G6)")
        result = compare_images(args.before.read_bytes(), args.after.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"))
            fp.write("\n")
    except (OSError, D88Error, DiffError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
