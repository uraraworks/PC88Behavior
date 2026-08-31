#!/usr/bin/env python3
"""make_n88_blank_disk.py の決定論性・構造・空状態と故障検出力を検査する。"""
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "blank", HERE / "make_n88_blank_disk.py")
assert SPEC and SPEC.loader
blank = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(blank)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_failure(label: str, action) -> None:
    try:
        action()
    except blank.BlankDiskError:
        print(f"OK: 陰性対照 {label} を実際に不合格にした")
        return
    raise SystemExit(f"NG: 陰性対照 {label} を誤って合格にした")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pc88-n88-blank-selftest.") as td:
        root = Path(td)
        a = blank.build_disk()
        b = blank.build_disk()
        (root / "a.d88").write_bytes(a)
        (root / "b.d88").write_bytes(b)
        if a != b or digest(a) != digest(b):
            raise SystemExit("NG: 独立2回生成が一致しない")
        print("OK: 陽性対照 独立2回生成のSHA-256が完全一致")
        blank.check_structure(a)
        print("OK: 陽性対照 公開D88構造が固定規則へ完全一致")
        empty = blank.check_empty(a)
        if empty["used_file_entries"] != 0:
            raise SystemExit("NG: 使用中ファイル項目が0件でない")
        print("OK: 陽性対照 使用中ファイル項目0件")

        structure_fault = bytearray(a)
        structure_fault[blank.data_offset(a, 0, 1)] ^= 0x01
        structure_fault = bytes(structure_fault)
        if digest(structure_fault) == digest(a):
            raise SystemExit("NG: 構造故障注入で成果物が変化しない")
        print("OK: 構造故障注入で成果物SHA-256が変化")
        require_failure("1バイト構造破壊", lambda: blank.check_structure(structure_fault))

        used_fault = bytearray(a)
        used_fault[blank.data_offset(a, blank.DIRECTORY_TRACK, 1)] = ord("Q")
        used_fault = bytes(used_fault)
        if digest(used_fault) == digest(a):
            raise SystemExit("NG: 使用中項目故障注入で成果物が変化しない")
        print("OK: 使用中項目故障注入で成果物SHA-256が変化")
        require_failure("使用中項目1件", lambda: blank.check_empty(used_fault))
    print("自己検査: OK=7 NG=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
