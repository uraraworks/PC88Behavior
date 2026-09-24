#!/usr/bin/env python3
"""m6f-c 追補3の凍結表 tools/m6fc_protect_frozen.tsv を、追補3の事前登録
docs/notes/m6f-c-addendum3-write-protect-sectors.md・導出器
tools/derive_m6fc_protect.py・生成器 tools/make_m6fc_blank_disk.py・
凍結表 tools/m6fc_frozen.tsv(SWの打鍵文字列)の定数と照合する。
tools/measure_m6fc_protect.sh は腕を1本でも走らせる前に、必ずこの照合を
rc=0で通してから進む(m6f-c本編のG7・追補1と同じ設計)。
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import derive_m6fc_protect as derive  # noqa: E402
from make_m6fc_blank_disk import ALLOCATION_TABLE_COORDS  # noqa: E402


class GateError(ValueError):
    pass


KEYSTROKES = (
    '10 on error goto 90:f$="2:"+chr$(81)+chr$(90)+chr$(55)+chr$(65)\\n'
    '20 open f$ for output as #1:print #1,"x":close #1\\n'
    '30 open f$ for input as #1:input #1,a$:close #1\\n'
    '40 if a$="x" then print chr$(90);chr$(81);"ok":end\\n'
    '50 print chr$(90);chr$(81);"ng":end\\n'
    '90 print chr$(90);chr$(81);"er";err;erl:end\\n'
    'run\\n'
)

SINGLETONS = {
    "frozen": "yes",
    "repetitions": "2",
    "frames": "8000",
    "boot_return_frame": "300",
    "stimulus_frame": "700",
    "reference_disk": "N88_FE.D88",
    "drive_layout": "drive1=reference_copy_protected;drive2=generated",
    "keystrokes": KEYSTROKES,
}

TARGETS = {
    "P13": (18, 1, 13),
    "P1": (18, 1, 1),
}

DERIVATIONS = {
    "Q1": "wclear_for_sweep",
    "Q2": "protect_sector",
    "Q3": "classification_and_io_sequence",
}

JUDGMENTS = [
    "gate_failed", "derived", "not_found", "run_disagreement",
    "m6f_c_protect_sector_derived", "protect_sector_not_found",
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


def parse_targets(values: list[str]) -> dict[str, tuple[int, int, int]]:
    out: dict[str, tuple[int, int, int]] = {}
    for value in values:
        key, sep, coord_str = value.partition(":")
        if not sep or key in out:
            raise GateError("targetの形式")
        parts = coord_str.split(",")
        if len(parts) != 3:
            raise GateError("target座標の形式")
        try:
            c, h, r = (int(v) for v in parts)
        except ValueError:
            raise GateError("target座標の数値変換") from None
        out[key] = (c, h, r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=HERE / "m6fc_protect_frozen.tsv")
    ap.add_argument(
        "--prereg", type=Path,
        default=REPO / "docs/notes/m6f-c-addendum3-write-protect-sectors.md",
    )
    ap.add_argument(
        "--sw-config", type=Path, default=HERE / "m6fc_frozen.tsv",
        help="SWの打鍵文字列の出所(m6f-c本編の凍結表)",
    )
    args = ap.parse_args()
    try:
        cfg = load_tsv(args.config)
        expected_keys = set(SINGLETONS) | {"target", "derivation", "judgment"}
        if set(cfg) != expected_keys:
            raise GateError("設定キーに不足または余分")
        for key, value in SINGLETONS.items():
            if one(cfg, key) != value:
                raise GateError(f"凍結値不一致: {key}")
        if int(one(cfg, "repetitions")) != 2:
            raise GateError("repetitions")

        targets = parse_targets(cfg["target"])
        if targets != TARGETS:
            raise GateError("targetの内容")
        if targets != derive.SWEEP_COORDS:
            raise GateError("targetが導出器のSWEEP_COORDSと食い違う")
        if tuple(targets) != derive.SWEEP_ORDER:
            raise GateError("targetの順序(P13優先)が導出器のSWEEP_ORDERと食い違う")
        for coord in targets.values():
            if coord in ALLOCATION_TABLE_COORDS:
                raise GateError("targetが割り当て表セクタと重なっている")

        if parse_keyed(cfg["derivation"]) != DERIVATIONS:
            raise GateError("導出規則名")
        if tuple(cfg["judgment"]) != tuple(JUDGMENTS):
            raise GateError("判定名")

        if derive.PROTECT_ERR != 61:
            raise GateError("書き込み禁止のERR番号の固定値")

        # SWの打鍵文字列は m6f-c本編の凍結表 SW区間(700フレーム)と
        # **完全に同じ文字列**であること（事前登録の要件）。
        sw_cfg = load_tsv(args.sw_config)
        sw_segment = None
        for value in sw_cfg.get("segment", []):
            arm, frame, text = value.split(":", 2)
            if arm == "SW" and frame == "700":
                sw_segment = text
                break
        if sw_segment is None:
            raise GateError("m6f-c本編の凍結表にSWの700区間が無い")
        if sw_segment != KEYSTROKES:
            raise GateError("keystrokesがm6f-c本編のSW区間と一致しない")
        if one(cfg, "keystrokes") != sw_segment:
            raise GateError("凍結表のkeystrokesがSW区間と一致しない")

        prereg = args.prereg.read_text(encoding="utf-8")
        required = (
            "W は全値を掃引し、特定の値を本命として置かない",
            "打鍵は SW と同じ",
            "書き込み禁止を外す値",
            "min(Wclear13)",
            "min(Wclear1)",
            "protect_sector_not_found",
        )
        if any(item not in prereg for item in required):
            raise GateError("事前登録本文")
    except (OSError, UnicodeError, ValueError, GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(args.config.read_bytes()).hexdigest()
    print(f"m6f-c addendum3 preregistration gate: OK sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
