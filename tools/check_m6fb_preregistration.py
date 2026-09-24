#!/usr/bin/env python3
"""m6f-b の凍結表を事前登録・導出器・判定器と照合する。"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import derive_m6fb as derive  # noqa: E402
import judge_m6fb as judge  # noqa: E402

ARMS = tuple(f"G{i}" for i in range(9))
STIMULI = {
    "G0": "",
    "G1": '10 F$=CHR$(81)+CHR$(90)+CHR$(55)+CHR$(65):OPEN F$ FOR OUTPUT AS #1:PRINT #1,"X":CLOSE #1\\nRUN\\n',
    "G2": '10 F$=CHR$(113)+CHR$(122)+CHR$(55)+CHR$(97):OPEN F$ FOR OUTPUT AS #1:PRINT #1,"Y":CLOSE #1\\nRUN\\n',
    "G3": '10 OPEN "QZ7A" FOR OUTPUT AS #1:PRINT #1,"W":CLOSE #1\\nRUN\\n',
    "G4": '10 F$=CHR$(81)+CHR$(90)+CHR$(55)+CHR$(65):G$=CHR$(81)+CHR$(90)+CHR$(55)+CHR$(66):OPEN F$ FOR OUTPUT AS #1:PRINT #1,"X":CLOSE #1:OPEN G$ FOR OUTPUT AS #1:PRINT #1,"X":CLOSE #1\\nRUN\\n',
    "G5": '10 F$=CHR$(81)+CHR$(90)+CHR$(55)+CHR$(65):OPEN F$ FOR OUTPUT AS #1:PRINT #1,"X":CLOSE #1:KILL F$\\nRUN\\n',
    "G6": '10 F$=CHR$(81)+CHR$(90)+CHR$(55)+CHR$(65)+CHR$(66)+CHR$(67):OPEN F$ FOR OUTPUT AS #1:PRINT #1,"X":CLOSE #1\\nRUN\\n',
    "G7": '10 F$=CHR$(81)+CHR$(90)+CHR$(55)+CHR$(68):OPEN F$ FOR OUTPUT AS #1:FOR I=1 TO 300:PRINT #1,STRING$(200,"V"):NEXT:CLOSE #1\\nRUN\\n',
    "G8": '10 END\\nSAVE"QZ7E"\\n',
}
DERIVATIONS = {
    "E1": "case_handling", "E2": "name_start", "E3": "entry_length",
    "E4": "name_padding_and_length", "E5": "deletion_marker",
    "E6": "unused_entry_value", "E7": "allocation_table_sectors",
    "E8": "program_data_difference",
}
SINGLETONS = {
    "frozen": "yes", "measurement_frames": "9000",
    "run_timeout_seconds": "300", "repetitions": "2",
    "reference_disk": "N88_FE.D88", "boot_return_frame": "300",
    "stimulus_frame": "700", "directory_sector": "18,1,3",
}


class GateError(ValueError):
    pass


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


def keyed(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        key, sep, rest = value.partition(":")
        if not sep or key in out:
            raise GateError("キー付き凍結値の形式")
        out[key] = rest
    return out


def typed_length(value: str) -> int:
    # 凍結表で認める唯一のエスケープは改行を表す二文字の \n。
    if value.replace("\\n", "").find("\\") >= 0:
        raise GateError("未知の打鍵エスケープ")
    return len(value.replace("\\n", "\n"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=HERE / "m6fb_frozen.tsv")
    ap.add_argument("--prereg", type=Path, default=REPO / "docs/notes/m6f-b-directory-entry-fields-preregistration.md")
    args = ap.parse_args()
    try:
        cfg = load_tsv(args.config)
        if set(cfg) != set(SINGLETONS) | {"arm", "keystrokes", "derivation", "judgment"}:
            raise GateError("設定キーに不足または余分")
        for key, value in SINGLETONS.items():
            if one(cfg, key) != value:
                raise GateError(f"凍結値不一致: {key}")
        if tuple(cfg["arm"]) != ARMS or derive.ARMS != ARMS or judge.ARMS != ARMS:
            raise GateError("腕名または順序")
        if derive.DIRECTORY != (18, 1, 3) or derive.U != bytes.fromhex("51 5A 37 41") \
                or derive.L != bytes.fromhex("71 7A 37 61"):
            raise GateError("SまたはU/Lの固定値")
        if judge.GATES != tuple([f"G{i}" for i in range(1, 9)] + ["G5b"]):
            raise GateError("関門名")
        stimuli = keyed(cfg["keystrokes"])
        if stimuli != STIMULI:
            raise GateError("打鍵文字列")
        if any(typed_length(value) > 512 for value in stimuli.values()):
            raise GateError("512打鍵超過")
        if keyed(cfg["derivation"]) != DERIVATIONS or derive.DERIVATIONS != tuple(DERIVATIONS):
            raise GateError("導出規則名")
        if tuple(cfg["judgment"]) != judge.REGISTERED:
            raise GateError("判定名")
        prereg = args.prereg.read_text(encoding="utf-8")
        required = ("S = (18, 1, 3)", "各腕2走",
                    "E1 大文字・小文字", "E8 プログラムとデータの違い",
                    'CHR$(81)+CHR$(90)+CHR$(55)+CHR$(65)', 'STRING$(200,"V")')
        if any(item not in prereg for item in required):
            raise GateError("事前登録本文")
        if any(f"`{name}`" not in prereg for name in judge.OVERALL):
            raise GateError("事前登録の総合判定名")
        if any(f"`{name}`" not in prereg for name in judge.REGISTERED
               if name not in ("derived", "ambiguous", "not_found")):
            raise GateError("事前登録の判定名")
    except (OSError, UnicodeError, ValueError, GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(args.config.read_bytes()).hexdigest()
    print(f"m6f-b preregistration gate: OK sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
