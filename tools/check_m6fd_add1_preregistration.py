#!/usr/bin/env python3
"""m6f-d 追補1 の凍結表 tools/m6fd_add1_frozen.tsv を、追補1
docs/notes/m6f-d-addendum1-terminal-and-reserve.md の定数と照合する。
tools/measure_m6fd_add1.sh は腕を1本でも走らせる前に、必ずこの照合を
rc=0で通してから進む（m6f-d 事前登録 第6節 G7 と同じ位置づけ）。

このファイルが唯一の真実の源。tools/m6fd_add1_frozen.tsv はこのモジュールから
機械生成した写しであり、改ざん検出は「このモジュールの値と凍結表の内容が
一致するか」で行う（tools/check_m6fd_add1_preregistration_selftest.sh）。

打鍵の形は tools/m6fd_frozen.tsv（tools/check_m6fd_preregistration.py）の
I-n・IV-fillの文字列と同じ形（追補1 §3.2「m6fd_frozen.tsv の I-n と
IV-fill の文字列と同じ形でnだけ変えたもの」）なので、rec_tpl と
IV_FILL_TEXT はそのまま再利用する。
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import check_m6fd_preregistration as mfd  # noqa: E402  (rec_tpl・IV_FILL_TEXTの再利用元)


class GateError(ValueError):
    pass


# --- 腕の一覧 ----------------------------------------------------------------

E_ARM_N = {"E-2": 2, "E-4": 4, "E-8": 8, "E-12": 12, "E-20": 20, "E-33": 33}
ARMS_E = ["E-2", "E-4", "E-8", "E-12", "E-20", "E-33"]
ARMS_IV_FILL = ["IV-fill-free", "IV-fill-res"]
ARMS = ARMS_E + ARMS_IV_FILL

# --- フレーム数 ---------------------------------------------------------------
# 追補1 §3.1: E-n はフレーム12000（打鍵はm6fdのI-nと同じ形で700に打つ）。
# 追補1 §3.2: IV-fill-free/IV-fill-res はm6fd事前登録どおり60000。

FRAMES_SINGLE = {a: 12000 for a in ARMS_E}
FRAMES_SINGLE["IV-fill-free"] = 60000
FRAMES_SINGLE["IV-fill-res"] = 60000

# --- 区間（打鍵） -------------------------------------------------------------
# 打鍵はm6fd_frozen.tsvのI-nと同じ形（rec_tpl）でnだけ変えたもの、
# IV-fillはm6fd_frozen.tsvと文字一致（同じ関数を再利用しているため自動的に一致）。

SEGMENTS: list[tuple[str, int, str]] = (
    [(a, 700, mfd.rec_tpl(n)) for a, n in E_ARM_N.items()]
    + [("IV-fill-free", 700, mfd.IV_FILL_TEXT), ("IV-fill-res", 700, mfd.IV_FILL_TEXT)]
)


def resolve_frames_single(arm: str) -> int:
    if arm not in FRAMES_SINGLE:
        raise GateError(f"framesを解決できない腕: {arm}")
    return FRAMES_SINGLE[arm]


def resolve_segment(arm: str) -> tuple[int, str]:
    for a, frame, text in SEGMENTS:
        if a == arm:
            return frame, text
    raise GateError(f"segmentを解決できない腕: {arm}")


MAX_KEYSTROKES = 512

SINGLETONS = {
    "frozen": "yes", "repetitions": "2", "run_timeout_seconds": "300",
    "boot_return_frame": "300", "stimulus_frame": "700",
    "reference_disk": "N88_FE.D88",
    "drive_layout_default": "drive1=reference_copy_protected;drive2=generated",
}

JUDGMENTS = [
    "gate_failed", "derived", "ambiguous", "not_found",
    "end_plus_used_sectors", "end_constant", "end_other", "chain_broken",
    "reserve_needed", "reserve_not_needed", "reserve_other",
    "m6f_d_add1_rules_confirmed", "m6f_d_add1_incomplete",
]


def typed_length(value: str) -> int:
    if value.replace("\\n", "").find("\\") >= 0:
        raise GateError("未知の打鍵エスケープ")
    return len(value.replace("\\n", "\n"))


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


def expected_segment_lines() -> list[str]:
    out = []
    for arm, frame, text in SEGMENTS:
        out.append(f"{arm}\t{frame}\t{text.replace(chr(10), chr(92) + 'n')}")
    return out


def expected_frame_lines() -> list[str]:
    return [f"{key}\t{value}" for key, value in FRAMES_SINGLE.items()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=HERE / "m6fd_add1_frozen.tsv")
    ap.add_argument("--addendum", type=Path,
                     default=REPO / "docs/notes/m6f-d-addendum1-terminal-and-reserve.md")
    args = ap.parse_args()
    try:
        cfg = load_tsv(args.config)
        expected_keys = set(SINGLETONS) | {"arm", "frame", "segment", "judgment"}
        if set(cfg) != expected_keys:
            raise GateError("設定キーに不足または余分")
        for key, value in SINGLETONS.items():
            if one(cfg, key) != value:
                raise GateError(f"凍結値不一致: {key}")
        if tuple(cfg["arm"]) != tuple(ARMS):
            raise GateError("腕名または順序")
        if len(ARMS) != 6 + 2:
            raise GateError("腕の総数")
        if list(cfg["frame"]) != expected_frame_lines():
            raise GateError("frameの内容")
        if list(cfg["segment"]) != expected_segment_lines():
            raise GateError("segmentの内容または順序")
        for arm, _frame, text in SEGMENTS:
            if typed_length(text) > MAX_KEYSTROKES:
                raise GateError(f"512打鍵超過: {arm}")
        if tuple(cfg["judgment"]) != tuple(JUDGMENTS):
            raise GateError("判定名")

        addendum = args.addendum.read_text(encoding="utf-8")
        loose_required = ("各2走", "0xC0", "end_plus_used_sectors", "end_constant", "end_other")
        for item in loose_required:
            if item not in addendum:
                raise GateError(f"追補1本文に無い表現: {item}")
    except (OSError, UnicodeError, ValueError, GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(args.config.read_bytes()).hexdigest()
    print(f"m6f-d addendum1 preregistration gate: OK sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
