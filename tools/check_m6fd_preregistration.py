#!/usr/bin/env python3
"""m6f-d の凍結表 tools/m6fd_frozen.tsv を、事前登録・打鍵テンプレートの
定数と照合する。tools/measure_m6fd.sh は腕を1本でも走らせる前に、
必ずこの照合をrc=0で通してから進む（事前登録 第6節 G7 相当）。

事前登録: docs/notes/m6f-d-disk-rules-preregistration.md。

このファイルが唯一の真実の源（ARMS/FRAMES/SEGMENTS/DERIVATIONS/
JUDGMENTS）。tools/m6fd_frozen.tsv はこのモジュールから機械生成した
写しであり、改ざん検出は「このモジュールの値と凍結表の内容が一致するか」
で行う（tools/check_m6fd_preregistration_selftest.sh の陰性対照）。
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import check_m6fc_preregistration as mfc  # noqa: E402  (SW打鍵・rec_tplの再利用元)


class GateError(ValueError):
    pass


# --- 打鍵テンプレート（事前登録・作業指示の文言をそのまま定数化する） --------

def rec_tpl(n: int) -> str:
    """I-n（n=250,1,3,6,10,17）。m6fc の A3/A4 と同じ形（QZ7B、n件）。"""
    return mfc.rec_tpl(n)


# II-d/II-neg1/II-neg2 の2段目（QZ7R、17件読み戻す）。
II_STAGE2 = ('10 on error goto 90:f$="2:"+chr$(81)+chr$(90)+chr$(55)+chr$(82):n=17\n'
             '30 open f$ for input as #1:m=0:for i=1 to n:input #1,a$:if val(left$(a$,5))<>i then m=m+1\n'
             '40 next:close #1:print chr$(90);chr$(81);"rb";m:end\n'
             '90 print chr$(90);chr$(81);"er";err;erl:end\n'
             'run\n')

# II-p（m6fcのA2_1と同じ、q7lへsave）。
II_P_STAGE1 = '10 print chr$(90);chr$(81);"ld"\nsave"2:q7l"\n'
II_P_STAGE2A = 'load"2:q7r"\n'
II_P_STAGE2B = 'run\n'


def iii_stage2_tpl(rr: str) -> str:
    """III-FF-rr/III-00-rr/III-none の2段目（rrは2桁の名前QDrr）。"""
    return ('10 on error goto 90:f$="2:"+chr$(81)+chr$(68)+"%s":open f$ for input as #1:'
            'input #1,a$:close #1:if val(left$(a$,5))=1 then print chr$(90);chr$(81);"ok":end\n'
            '20 print chr$(90);chr$(81);"ng":end\n'
            '90 print chr$(90);chr$(81);"er";err;erl:end\n'
            'run\n') % rr


# IV-R-XX: 事前登録 §4.4 の要求どおり、m6fc SW行と完全一致（打鍵は同一）。
IV_R_TEXT = mfc.SW

# IV-fill-free/IV-fill-res: 事前登録 §4.4 のプログラムそのまま。
IV_FILL_TEXT = (
    '10 on error goto 90:for n=1 to 200:f$="2:"+chr$(81)+right$(str$(1000+n),3):'
    'open f$ for output as #1:print #1,"x":close #1:next\n'
    '20 print chr$(90);chr$(81);"nf":goto 100\n'
    '90 print chr$(90);chr$(81);"fe";err;n:resume 100\n'
    '100 on error goto 190:f$="2:"+chr$(81)+"001":open f$ for input as #1:input #1,a$:'
    'close #1:print chr$(90);chr$(81);"ck";-(a$="x"):end\n'
    '190 print chr$(90);chr$(81);"cx";err:end\n'
    'run\n'
)

# V-*: 事前登録 §4.5 の打鍵そのまま。
V_TEXT = (
    'print chr$(90);chr$(81);"bt"\n'
    '10 on error goto 90:open "qz" for output as #1:print #1,"x":close #1:'
    'print chr$(90);chr$(81);"ok":end\n'
    '90 print chr$(90);chr$(81);"er";err;erl:end\n'
    'run\n'
)

MAX_KEYSTROKES = 512

# --- 腕の一覧 ----------------------------------------------------------------

ARMS_I = ["I-250", "I-1", "I-3", "I-6", "I-10", "I-17"]
ARMS_II = ["II-d", "II-p", "II-neg1", "II-neg2"]
ARMS_III = ([f"III-FF-{r:02d}" for r in range(1, 13)]
            + [f"III-00-{r:02d}" for r in range(1, 13)]
            + ["III-none"])
ARMS_IV_R = [f"IV-R-{v:02X}" for v in range(256)]
ARMS_IV_FILL = ["IV-fill-free", "IV-fill-res"]
ARMS_V = ["V-missing", "V-crc", "V-deleted", "V-single", "V-ff", "V-c9"]

ARMS = ARMS_I + ARMS_II + ARMS_III + ARMS_IV_R + ARMS_IV_FILL + ARMS_V

# 2段の腕（付け替えを挟んで2回計測する）。III-noneは1段目が無い単発腕。
TWO_STAGE_ARMS = frozenset(
    ["II-d", "II-p", "II-neg1", "II-neg2"]
    + [f"III-FF-{r:02d}" for r in range(1, 13)]
    + [f"III-00-{r:02d}" for r in range(1, 13)]
)

# --- 走行フレーム数（腕名の完全一致優先、無ければ"key-"接頭辞） -------------
# キーは "腕(または接頭辞):フェーズ"。単発腕/2段でない場合フェーズは "".

FRAMES1 = {  # 2段の腕の1段目
    "II-d": 12000, "II-neg1": 12000, "II-neg2": 12000, "II-p": 8000,
    "III-FF": 12000, "III-00": 12000,
}
FRAMES2 = {  # 2段の腕の2段目
    "II-d": 12000, "II-neg1": 12000, "II-neg2": 12000, "II-p": 8000,
    "III-FF": 8000, "III-00": 8000,
}
FRAMES_SINGLE = {  # 単発腕
    "I-250": 30000, "I-1": 12000, "I-3": 12000, "I-6": 12000, "I-10": 12000, "I-17": 12000,
    "III-none": 8000,
    "IV-R": 8000,
    "IV-fill-free": 60000, "IV-fill-res": 60000,
    "V-missing": 8000, "V-crc": 8000, "V-deleted": 8000, "V-single": 8000,
    "V-ff": 8000, "V-c9": 8000,
}


def _resolve(table: dict[str, int], arm: str) -> int:
    if arm in table:
        return table[arm]
    for key, value in table.items():
        if arm.startswith(key + "-"):
            return value
    raise GateError(f"framesを解決できない腕: {arm}")


def resolve_frames_single(arm: str) -> int:
    return _resolve(FRAMES_SINGLE, arm)


def resolve_frames_phase(arm: str, phase: str) -> int:
    table = FRAMES1 if phase == "1" else FRAMES2
    return _resolve(table, arm)


def is_two_stage(arm: str) -> bool:
    return arm in TWO_STAGE_ARMS


# --- 区間（打鍵） -------------------------------------------------------------
# (腕またはグループ接頭辞, フェーズ("1"/"2"/None), フレーム, 打鍵テキスト)

SEGMENTS: list[tuple[str, str | None, int, str]] = (
    [(a, None, 700, rec_tpl(n)) for a, n in
     [("I-250", 250), ("I-1", 1), ("I-3", 3), ("I-6", 6), ("I-10", 10), ("I-17", 17)]]
    + [("II-d", "1", 700, rec_tpl(17)), ("II-d", "2", 700, II_STAGE2)]
    + [("II-neg1", "1", 700, rec_tpl(17)), ("II-neg1", "2", 700, II_STAGE2)]
    + [("II-neg2", "1", 700, rec_tpl(17)), ("II-neg2", "2", 700, II_STAGE2)]
    + [("II-p", "1", 700, II_P_STAGE1), ("II-p", "2", 700, II_P_STAGE2A),
       ("II-p", "2", 2000, II_P_STAGE2B)]
    + [("III-FF", "1", 700, rec_tpl(1)), ("III-00", "1", 700, rec_tpl(1))]
    + [(f"III-FF-{r:02d}", "2", 700, iii_stage2_tpl(f"{r:02d}")) for r in range(1, 13)]
    + [(f"III-00-{r:02d}", "2", 700, iii_stage2_tpl(f"{r:02d}")) for r in range(1, 13)]
    + [("III-none", None, 700, iii_stage2_tpl("01"))]
    + [("IV-R", None, 700, IV_R_TEXT)]
    + [("IV-fill-free", None, 700, IV_FILL_TEXT), ("IV-fill-res", None, 700, IV_FILL_TEXT)]
    + [(a, None, 700, V_TEXT) for a in ARMS_V]
)


def resolve_segments(arm: str, phase: str | None) -> list[tuple[int, str]]:
    exact = [(frame, text) for a, p, frame, text in SEGMENTS if a == arm and p == phase]
    if exact:
        return exact
    return [(frame, text) for a, p, frame, text in SEGMENTS
            if arm.startswith(a + "-") and p == phase]


DERIVATIONS = {
    "D1": "unit_size_and_offset", "D2": "chain", "D3": "terminal_value",
    "D4": "entry_head_unit_field", "D5": "relocated_readable", "D6": "directory_extent",
    "D7": "used_mark_values", "D8": "reserve_mark_necessity", "D9": "boot",
}

JUDGMENTS = [
    "gate_failed", "derived", "ambiguous", "not_found",
    "relocated_readable", "not_readable", "control_failed",
    "stops_at_unused", "scans_past_unused",
    "reserve_needed", "reserve_not_needed", "reserve_other",
    "disk_basic", "nondisk_basic", "error_after_boot", "no_basic", "control_changed",
    "m6f_d_rules_confirmed", "m6f_d_incomplete",
]

SINGLETONS = {
    "frozen": "yes", "repetitions": "2", "run_timeout_seconds": "300",
    "boot_return_frame": "300", "stimulus_frame": "700",
    "reference_disk": "N88_FE.D88",
    "drive_layout_default": "drive1=reference_copy_protected;drive2=generated",
    "drive_layout_V": "drive1=generated;drive2=none",
}


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


def parse_keyed(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        key, sep, rest = value.partition(":")
        if not sep or key in out:
            raise GateError("キー付き凍結値の形式")
        out[key] = rest
    return out


def expected_segment_lines() -> list[str]:
    out = []
    for arm, phase, frame, text in SEGMENTS:
        phase_field = phase if phase is not None else ""
        out.append(f"{arm}\t{phase_field}\t{frame}\t{text.replace(chr(10), chr(92) + 'n')}")
    return out


def expected_frame_lines() -> list[str]:
    out = []
    for key, value in FRAMES_SINGLE.items():
        out.append(f"{key}\t\t{value}")
    for key, value in FRAMES1.items():
        out.append(f"{key}\t1\t{value}")
    for key, value in FRAMES2.items():
        out.append(f"{key}\t2\t{value}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=HERE / "m6fd_frozen.tsv")
    ap.add_argument("--prereg", type=Path,
                     default=REPO / "docs/notes/m6f-d-disk-rules-preregistration.md")
    args = ap.parse_args()
    try:
        cfg = load_tsv(args.config)
        expected_keys = set(SINGLETONS) | {"arm", "frame", "segment", "derivation", "judgment"}
        if set(cfg) != expected_keys:
            raise GateError("設定キーに不足または余分")
        for key, value in SINGLETONS.items():
            if one(cfg, key) != value:
                raise GateError(f"凍結値不一致: {key}")
        if tuple(cfg["arm"]) != tuple(ARMS):
            raise GateError("腕名または順序")
        if len(ARMS) != 6 + 4 + 25 + 256 + 2 + 6:
            raise GateError("腕の総数")

        if list(cfg["frame"]) != expected_frame_lines():
            raise GateError("frameの内容")
        if list(cfg["segment"]) != expected_segment_lines():
            raise GateError("segmentの内容または順序")

        for arm, phase, _frame, text in SEGMENTS:
            if typed_length(text) > MAX_KEYSTROKES:
                raise GateError(f"512打鍵超過: {arm}:{phase}")

        if parse_keyed(cfg["derivation"]) != DERIVATIONS:
            raise GateError("導出規則名")
        if tuple(cfg["judgment"]) != tuple(JUDGMENTS):
            raise GateError("判定名")

        prereg = args.prereg.read_text(encoding="utf-8")
        # 事前登録本文の主要語だけを確認する（表記そのままの部分文字列）。
        loose_required = ("各腕2走", "打鍵は小文字", "ドライブ1に媒体、ドライブ2は空", "R\\*")
        for item in loose_required:
            if item not in prereg:
                raise GateError(f"事前登録本文に無い表現: {item}")
        for name in ("m6f_d_rules_confirmed", "m6f_d_incomplete"):
            if f"**`{name}`**" not in prereg and f"`{name}`" not in prereg:
                raise GateError(f"事前登録の総合判定名が無い: {name}")
    except (OSError, UnicodeError, ValueError, GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(args.config.read_bytes()).hexdigest()
    print(f"m6f-d preregistration gate: OK sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
