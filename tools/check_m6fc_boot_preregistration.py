#!/usr/bin/env python3
"""m6f-c 追補1の凍結表 tools/m6fc_boot_frozen.tsv を、追補1の事前登録
docs/notes/m6f-c-addendum1-boot-sector-sweep.md・導出器
tools/derive_m6fc_boot.py・生成器 tools/make_m6fc_blank_disk.py の定数と照合する。
tools/measure_m6fc_boot.sh は腕を1本でも走らせる前に、必ずこの照合を
rc=0で通してから進む（m6f-c本編のG7と同じ設計）。
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import derive_m6fc_boot as derive  # noqa: E402
from make_m6fc_blank_disk import BOOT_SECTOR_COORD  # noqa: E402


class GateError(ValueError):
    pass


KEYSTROKES = 'print chr$(90);chr$(81);"bt"\\n'
ARM_PREFIX = "BX"
ARMS = tuple(f"{ARM_PREFIX}-{x:02X}" for x in range(256))

SINGLETONS = {
    "frozen": "yes",
    "repetitions": "2",
    "frames": "3000",
    "boot_return_frame": "300",
    "stimulus_frame": "700",
    "keystrokes": KEYSTROKES,
    "arm_prefix": ARM_PREFIX,
}

DERIVATIONS = {
    "B1": "boot_capable_values",
    "B2": "next_read",
}

JUDGMENTS = [
    "gate_failed", "derived", "not_found", "m6f_c_boot_addendum1_ok",
]


def load_tsv(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("\t")
        if not sep or not key:
            raise GateError("凍結表の形式")
        out.setdefault(key, []).append(value)
    return out


def one(cfg: dict[str, list[str]], key: str) -> str:
    values = cfg.get(key, [])
    if len(values) != 1:
        raise GateError(f"{key}が一意でない")
    return values[0]


def parse_keyed(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        key, sep, rest = value.partition(":")
        if not sep or key in out:
            raise GateError("キー付き凍結値の形式")
        out[key] = rest
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=HERE / "m6fc_boot_frozen.tsv")
    ap.add_argument(
        "--prereg", type=Path,
        default=REPO / "docs/notes/m6f-c-addendum1-boot-sector-sweep.md",
    )
    args = ap.parse_args()
    try:
        cfg = load_tsv(args.config)
        expected_keys = set(SINGLETONS) | {"derivation", "judgment"}
        if set(cfg) != expected_keys:
            raise GateError("設定キーに不足または余分")
        for key, value in SINGLETONS.items():
            if one(cfg, key) != value:
                raise GateError(f"凍結値不一致: {key}")
        if int(one(cfg, "repetitions")) != 2:
            raise GateError("repetitions")
        if len(ARMS) != 256:
            raise GateError("腕の総数")

        if parse_keyed(cfg["derivation"]) != DERIVATIONS:
            raise GateError("導出規則名")
        if tuple(cfg["judgment"]) != tuple(JUDGMENTS):
            raise GateError("判定名")

        # 生成器・導出器の固定値との照合。
        if BOOT_SECTOR_COORD != (0, 0, 1):
            raise GateError("起動用セクタ座標の固定値")
        if derive.BOOT_COORD != (0, 0, 1):
            raise GateError("導出器の起動用セクタ座標")

        prereg = args.prereg.read_text(encoding="utf-8")
        required = (
            "X は全値を掃引し、特定の値を本命として置かない",
            "空でなければ `derived`",
            "先頭4個と、(0,0,1) を読んだ回数",
            "Xboot の最小値",
            "各2走",
        )
        if any(item not in prereg for item in required):
            raise GateError("事前登録本文")
    except (OSError, UnicodeError, ValueError, GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(args.config.read_bytes()).hexdigest()
    print(f"m6f-c addendum1 preregistration gate: OK sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
