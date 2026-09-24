#!/usr/bin/env python3
"""m6f-c の凍結表 tools/m6fc_frozen.tsv を、事前登録・導出器・判定器・
生成器の定数と照合する。measure_m6fc.sh は腕を1本でも走らせる前に、
必ずこの照合をrc=0で通してから進む(事前登録 第6節 G7)。
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import derive_m6fc as derive  # noqa: E402
import judge_m6fc as judge  # noqa: E402
from make_m6fc_blank_disk import ALLOCATION_TABLE_COORDS  # noqa: E402


class GateError(ValueError):
    pass


def rec_tpl(n: int) -> str:
    return ('10 on error goto 90:f$=chr$(81)+chr$(90)+chr$(55)+chr$(66):n=%d\n'
            '20 open f$ for output as #1:for i=1 to n:print #1,right$(str$(100000!+i),5);'
            'string$(120,"v"):next:close #1\n'
            '30 open f$ for input as #1:m=0:for i=1 to n:input #1,a$:if val(left$(a$,5))<>i then m=m+1\n'
            '40 next:close #1:print chr$(90);chr$(81);"rb";m:end\n'
            '90 print chr$(90);chr$(81);"er";err;erl:end\n'
            'run\n') % n


BT = 'print chr$(90);chr$(81);"bt"\n'
SW = ('10 on error goto 90:f$=chr$(81)+chr$(90)+chr$(55)+chr$(65)\n'
      '20 open f$ for output as #1:print #1,"x":close #1\n'
      '30 open f$ for input as #1:input #1,a$:close #1\n'
      '40 if a$="x" then print chr$(90);chr$(81);"ok":end\n'
      '50 print chr$(90);chr$(81);"ng":end\n'
      '90 print chr$(90);chr$(81);"er";err;erl:end\n'
      'run\n')
A1_TEXT = ('10 on error goto 90:files:print chr$(90);chr$(81);"ok":end\n'
           '90 print chr$(90);chr$(81);"er";err;erl:end\n'
           'run\n')
A1B_TEXT = ('10 on error goto 90:f$=chr$(81)+chr$(90)+chr$(55)+chr$(65)\n'
            '20 open f$ for output as #1:print #1,"x":close #1\n'
            '30 files:print chr$(90);chr$(81);"ok":end\n'
            '90 print chr$(90);chr$(81);"er";err;erl:end\n'
            'run\n')
A2_1 = '10 print chr$(90);chr$(81);"ld"\nsave"q7l"\n'
A2_2 = 'new\nload"q7l"\n'
A2_3 = 'run\n'
A5_TEXT = ('10 on error goto 90:for n=1 to 400:f$=chr$(81)+right$(str$(1000+n),3):'
           'open f$ for output as #1:close #1:next:print chr$(90);chr$(81);"ok";n:end\n'
           '90 print chr$(90);chr$(81);"er";err;n:end\n'
           'run\n')
A5B_TEXT = A5_TEXT.replace('close #1:next', 'close #1:kill f$:next')

ARMS = (["GB-FF", "GB-00"] + [f"SW-{i:02X}" for i in range(256)] +
        ["A0", "A1", "A1b", "A2", "A3", "A4-1", "A4-3", "A4-6", "A4-10", "A4-17",
         "A5", "A5b", "A6"])

FRAMES = {
    "GB-FF": 3000, "GB-00": 3000, "SW": 8000, "A0": 8000, "A1": 8000, "A1b": 8000,
    "A2": 12000, "A3": 30000, "A4-1": 12000, "A4-3": 12000, "A4-6": 12000,
    "A4-10": 12000, "A4-17": 12000, "A5": 60000, "A5b": 60000, "A6": 12000,
}

SEGMENTS = [
    ("GB-FF", 700, BT), ("GB-00", 700, BT), ("SW", 700, SW),
    ("A1", 700, A1_TEXT), ("A1b", 700, A1B_TEXT),
    ("A2", 700, A2_1), ("A2", 2500, A2_2), ("A2", 4000, A2_3),
    ("A3", 700, rec_tpl(250)),
    ("A4-1", 700, rec_tpl(1)), ("A4-3", 700, rec_tpl(3)), ("A4-6", 700, rec_tpl(6)),
    ("A4-10", 700, rec_tpl(10)), ("A4-17", 700, rec_tpl(17)),
    ("A5", 700, A5_TEXT), ("A5b", 700, A5B_TEXT),
    ("A6", 700, A2_1), ("A6", 2500, A2_2), ("A6", 4000, A2_3),
]

DERIVATIONS = {
    "C0": "filler_and_free_mark_gate", "C1": "free_mark", "C2": "acceptance",
    "C3": "allocation_table_replicas", "C4": "unit_size_and_offset", "C5": "chain",
    "C6": "terminal_value", "C7": "entry_head_unit_field", "C8": "directory_start",
    "C9": "directory_extent", "C10": "files_read_sectors", "C11": "body_location",
}

SINGLETONS = {
    "frozen": "yes", "repetitions": "2", "run_timeout_seconds": "300",
    "boot_return_frame": "300", "stimulus_frame": "700",
    "fat_sectors": "18,1,14;18,1,15;18,1,16",
}

JUDGMENTS = [
    "gate_failed", "derived", "ambiguous", "not_found",
    "run_disagreement",
    "accepted", "not_accepted",
    "replicas_identical", "replicas_differ",
    "link_is_next_index", "link_other",
    "end_constant", "end_plus_used_sectors", "end_other",
    "deleted_slot_reused", "directory_bound", "lower_bound_only",
    "body_in_track18", "body_outside_track18",
    "m6f_c_boot_blocked", "m6f_c_no_free_mark",
    "m6f_c_blank_disk_accepted", "m6f_c_blank_disk_not_accepted",
]

MAX_KEYSTROKES = 512


def resolve_frames(arm: str) -> int:
    """measure_m6fc.sh もこれを使う。腕名の完全一致を優先し、無ければ
    'SW-00'→'SW' のようなグループ接頭辞(ハイフン区切り)に解決する。"""
    if arm in FRAMES:
        return FRAMES[arm]
    for key, value in FRAMES.items():
        if arm.startswith(key + "-"):
            return value
    raise GateError(f"framesを解決できない腕: {arm}")


def resolve_segments(arm: str) -> list[tuple[int, str]]:
    """measure_m6fc.sh もこれを使う。完全一致する腕の区間があればそれを、
    無ければグループ接頭辞に一致する区間を、登録順のまま返す。"""
    exact = [(frame, text) for a, frame, text in SEGMENTS if a == arm]
    if exact:
        return exact
    return [(frame, text) for a, frame, text in SEGMENTS if arm.startswith(a + "-")]


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


def typed_length(value: str) -> int:
    if value.replace("\\n", "").find("\\") >= 0:
        raise GateError("未知の打鍵エスケープ")
    return len(value.replace("\\n", "\n"))


def parse_frames(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key, sep, num = value.partition(":")
        if not sep or key in out or not num.isdigit():
            raise GateError("framesの形式")
        out[key] = int(num)
    return out


def parse_segments(values: list[str]) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for value in values:
        parts = value.split(":", 2)
        if len(parts) != 3 or not parts[1].isdigit():
            raise GateError("segmentの形式")
        arm, frame, text = parts
        out.append((arm, int(frame), text))
    return out


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
    ap.add_argument("--config", type=Path, default=HERE / "m6fc_frozen.tsv")
    ap.add_argument("--prereg", type=Path,
                    default=REPO / "docs/notes/m6f-c-blank-disk-acceptance-preregistration.md")
    args = ap.parse_args()
    try:
        cfg = load_tsv(args.config)
        expected_keys = set(SINGLETONS) | {"arm", "frames", "segment", "derivation", "judgment"}
        if set(cfg) != expected_keys:
            raise GateError("設定キーに不足または余分")
        for key, value in SINGLETONS.items():
            if one(cfg, key) != value:
                raise GateError(f"凍結値不一致: {key}")
        if tuple(cfg["arm"]) != tuple(ARMS):
            raise GateError("腕名または順序")
        if len(ARMS) != 2 + 256 + 13:
            raise GateError("腕の総数")

        frames = parse_frames(cfg["frames"])
        if frames != FRAMES:
            raise GateError("framesの内容")

        segments = parse_segments(cfg["segment"])
        expected_segments = [(arm, frame, esc) for arm, frame, text in SEGMENTS
                              for esc in [text.replace("\n", "\\n")]]
        if segments != expected_segments:
            raise GateError("segmentの内容または順序")
        for arm, _frame, text in segments:
            if typed_length(text) > MAX_KEYSTROKES:
                raise GateError(f"512打鍵超過: {arm}")

        # frames/segment のキー解決先がすべて実在の腕であること。
        def resolves(key: str) -> bool:
            return key in ARMS or any(a.startswith(key + "-") for a in ARMS)

        for key in frames:
            if not resolves(key):
                raise GateError(f"framesキーが腕に解決できない: {key}")
        for arm, _frame, _text in segments:
            if not resolves(arm):
                raise GateError(f"segment腕が腕に解決できない: {arm}")

        if parse_keyed(cfg["derivation"]) != DERIVATIONS:
            raise GateError("導出規則名")
        if tuple(cfg["judgment"]) != tuple(JUDGMENTS):
            raise GateError("判定名")

        # 導出器・判定器・生成器の固定値との照合。
        if derive.FAT_SECTORS != ((18, 1, 14), (18, 1, 15), (18, 1, 16)):
            raise GateError("割り当て表セクタの固定値")
        if set(derive.FAT_SECTORS) != set(ALLOCATION_TABLE_COORDS):
            raise GateError("導出器と生成器で割り当て表セクタが食い違う")
        # 事前登録 §5.1 の明確化（0始まり 10〜15、トラック18は両ヘッド）。
        if derive.ENTRY_FIELD_OFFSETS != (10, 11, 12, 13, 14, 15):
            raise GateError("エントリ先頭単位欄の候補オフセット")
        if set(derive.TRACK18_COORDS) != {(18, h, r) for h in (0, 1) for r in range(1, 17)}:
            raise GateError("トラック18の範囲")
        if judge.DERIVATION_NAMES != tuple(DERIVATIONS):
            raise GateError("判定器の導出名")
        if set(judge.OVERALL) - set(JUDGMENTS):
            raise GateError("判定器の総合判定名が凍結表に無い")
        if set(judge.REGISTERED) - set(JUDGMENTS) - {"derived", "ambiguous", "not_found", "gate_failed"}:
            raise GateError("判定器の登録判定名が凍結表に無い")

        prereg = args.prereg.read_text(encoding="utf-8")
        required = (
            "空きの印は 0x00〜0xFF の全値を掃引",
            "各腕 2 走",
            "は §5 C1 が決めた値",
            "打鍵は小文字で届く",
            "1記録は1セクタより短い",
        )
        if any(item not in prereg for item in required):
            raise GateError("事前登録本文")
        if any(f"`{name}`" not in prereg for name in judge.OVERALL):
            raise GateError("事前登録の総合判定名")
    except (OSError, UnicodeError, ValueError, GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(args.config.read_bytes()).hexdigest()
    print(f"m6f-c preregistration gate: OK sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
