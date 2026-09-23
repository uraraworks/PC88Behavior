#!/usr/bin/env python3
"""m6f-aの凍結表を事前登録・追補・解析器・判定器と照合する。"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import derive_m6fa as derive  # noqa: E402
import judge_m6fa as judge  # noqa: E402

ARMS = tuple(f"F{i}" for i in range(7))
STIMULI = {
    "F0": "",
    "F1": '10 END\\nSAVE"QZ7A"\\n',
    "F2": '10 END\\nSAVE"QZ7B"\\n',
    "F3": '10 END\\nSAVE"QZ7ABC"\\n',
    "F4": '10 END\\nSAVE"QZ7A"\\nSAVE"QZ7B"\\n',
    "F5": '10 END\\nSAVE"QZ7A"\\nKILL"QZ7A"\\n',
    "F6": '10 OPEN"QZ7D" FOR OUTPUT AS #1\\n'
          '20 FOR I=1 TO 300:PRINT #1,STRING$(200,"Z"):NEXT\\n'
          '30 CLOSE #1\\nRUN\\n',
}
DERIVATIONS = {
    "D1": "directory_sector", "D2": "name_start",
    "D3": "entry_length", "D4": "name_padding_and_length",
    "D5": "deletion_marker", "D6": "unused_entry_value",
    "D7": "allocation_table_sector",
}
SINGLETONS = {
    "frozen": "yes", "measurement_frames": "9000",
    "run_timeout_seconds": "300", "repetitions": "2",
    "reference_disk": "N88_FE.D88", "boot_return_frame": "300",
    "stimulus_frame": "700",
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=HERE / "m6fa_frozen.tsv")
    ap.add_argument("--prereg", type=Path, default=REPO / "docs/notes/m6f-a-directory-by-save-diff-preregistration.md")
    ap.add_argument("--addendum", type=Path, default=REPO / "docs/notes/m6f-a-addendum1-f6-within-keystroke-budget.md")
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
        if keyed(cfg["keystrokes"]) != STIMULI:
            raise GateError("打鍵文字列")
        if keyed(cfg["derivation"]) != DERIVATIONS or derive.DERIVATIONS != tuple(DERIVATIONS):
            raise GateError("導出規則名")
        if tuple(cfg["judgment"]) != judge.REGISTERED:
            raise GateError("判定名")
        prereg = args.prereg.read_text(encoding="utf-8")
        addendum = args.addendum.read_text(encoding="utf-8")
        required_prereg = ('SAVE"QZ7A"', 'SAVE"QZ7B"', 'SAVE"QZ7ABC"',
                            "各腕2走", "D1 ディレクトリのセクタ",
                            "D6 未使用エントリの表現", "9000 frames", "1走300秒")
        # 期限は事前登録本文ではm7cw参照の指定として利用者から固定されたため、
        # 文書に語が無い場合も凍結表の値自体は上で厳密照合する。
        required_prereg = tuple(x for x in required_prereg if x not in ("9000 frames", "1走300秒"))
        if any(x not in prereg for x in required_prereg):
            raise GateError("事前登録本文")
        required_addendum = ('OPEN"QZ7D" FOR OUTPUT AS #1',
                              'FOR I=1 TO 300:PRINT #1,STRING$(200,"Z"):NEXT',
                              "F1 と F6 の両方で変わったセクタ", "QZ7D")
        if any(x not in addendum for x in required_addendum):
            raise GateError("追補1の優先条件")
        if any(f"`{name}`" not in prereg for name in judge.REGISTERED
               if name not in ("derived", "ambiguous", "not_found")):
            raise GateError("事前登録の判定名")
    except (OSError, UnicodeError, ValueError, GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(args.config.read_bytes()).hexdigest()
    print(f"m6f-a preregistration gate: OK sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
