#!/usr/bin/env python3
"""m6i-iの凍結表・文書・実装定数を起動前に照合する。"""
from __future__ import annotations

import argparse
import ast
import hashlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))
import analyze_m6ii as analyzer  # noqa: E402
import judge_m6ii as judge  # noqa: E402
import src.build_main_rom as mainrom  # noqa: E402

ARMS = ("I-S", "I-F-H", "I-F-D", "I-F-R", "I-F-RETRY")
ROWS = analyzer.ROWS
FAULT_ROWS = {
    "I-F-H": "2,5,7,9,10", "I-F-D": "8,9,10",
    "I-F-R": "1,2,3,4,5,6,7,8,9,10,11", "I-F-RETRY": "retry_b",
}
EXPECTED_SINGLETONS = {
    "frozen": "yes", "measurement_frames": "1800", "repetitions": "2",
    "row_marker_address": "0xE038",
    "normal_media_sha256": "d3becfe5051f7002d268824a2da2824f543442e71ae3226e4d22139e0adce05c",
    "disk_a_sha256": "060613aec5092ce8b750b8233cec3ef88011efa6626f7e9fa6bce7a428ea5bb6",
    "disk_b_sha256": "0006dd541d4743592d9534824c03c81b23ebfe9486a9cf89202f4783dbfcfdd3",
    "main_sub_sha256": "7646c2d418dc9f33f30670b9638368fcfb5614e67ec26000cdd7c4106b258f5d",
    "disk_retry_sha256": "dc940d77f412d2c1e14a24e9f8d1cd658d885a87f88fb0c62798411d4268faa1",
    "disk_chr_sha256": "795a27c9094af493a4fb380e76631c5aaac1f7292a834e82cd8ddb769ed49b56",
    "plain_subrom_sha256": "d8b2e64bc27465f955fd308719228f21b06aa07fd780081a88124a52e6d76070",
}
ARM_HASHES = {
    "I-S": "86aa5ea0d9141050b8692b3bb1a51aaeb24ee9a79e92e708ece731cb391edbae",
    "I-F-H": "639d7b736daeff375e20a729c3f6dec0ded7db0346377e47892108bdd41e7734",
    "I-F-D": "b4ec65c97f92734a2a1c9b9ebc19bab6f768719cea38fd10304e529e67011d8b",
    "I-F-R": "fad10e03d476a399197da4d2fde4d7468046b5496279b31e6bd42c239990cffb",
    "I-F-RETRY": "db09cb9f4407d8924f22ba10e15f727a34fdd00acb6cc45fb0927ef55634600c",
}


class GateError(ValueError):
    pass


def load_tsv(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("\t")
        if sep != "\t" or not key or not value:
            raise GateError("凍結表の形式")
        result.setdefault(key, []).append(value)
    return result


def one(cfg: dict[str, list[str]], key: str) -> str:
    values = cfg.get(key, [])
    if len(values) != 1:
        raise GateError(f"{key}が一意でない")
    return values[0]


def keyed(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, sep, rest = value.partition(":")
        if sep != ":" or key in result:
            raise GateError("キー付き凍結値の形式")
        result[key] = rest
    return result


def numeric_equ_definitions() -> list[tuple[str, int, Path]]:
    pattern = re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s+EQU\s+"
                         r"(0x[0-9A-Fa-f]+|[0-9A-Fa-f]+h|[0-9]+)\b")
    paths = list((REPO / "src").rglob("*.asm"))
    paths += [REPO / "src" / "build_main_rom.py"]
    paths += list((REPO / "tools").glob("build_*measure_rom.py"))
    found = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for name, raw in pattern.findall(text):
            if raw.lower().startswith("0x"):
                value = int(raw, 16)
            elif raw.lower().endswith("h"):
                value = int(raw[:-1], 16)
            else:
                value = int(raw)
            found.append((name, value, path))
    return found


def equ_address_is_free(address: int) -> bool:
    """m6i-i自身のEQUを除き、既存EQUを全列挙して同値がないか調べる。"""
    return not any(value == address and name != "M6II_ROW_MARKER"
                   for name, value, _path in numeric_equ_definitions())


def no_generator_import(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        if any(name.split(".")[-1] == "make_l3_testdisk" for name in names):
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=HERE / "m6ii_frozen.tsv")
    ap.add_argument("--prereg", type=Path,
                    default=REPO / "docs/notes/m6i-i-arbitrary-coordinate-read-preregistration.md")
    ap.add_argument("--addendum", type=Path,
                    default=REPO / "docs/notes/m6i-i-addendum1-no-data-rows.md")
    args = ap.parse_args()
    try:
        cfg = load_tsv(args.config)
        expected_keys = set(EXPECTED_SINGLETONS) | {
            "disk_id", "arm_sha256", "arm", "row", "fault_rows", "judgment"}
        if set(cfg) != expected_keys:
            raise GateError("設定キーに不足または余分")
        for key, value in EXPECTED_SINGLETONS.items():
            if one(cfg, key) != value:
                raise GateError(f"凍結値不一致: {key}")
        if tuple(cfg["arm"]) != ARMS or analyzer.ARMS != ARMS or judge.ARMS != ARMS:
            raise GateError("腕名または順序")
        expected_rows = tuple(f"{n}:{d}:{c}:{h}:{r}" for n, d, c, h, r in ROWS)
        if tuple(cfg["row"]) != expected_rows:
            raise GateError("座標列または順序")
        if keyed(cfg["fault_rows"]) != FAULT_ROWS:
            raise GateError("故障注入の必須不一致行")
        if keyed(cfg["disk_id"]) != {"A": "0xA1", "B": "0xB2"}:
            raise GateError("ディスク識別値")
        if keyed(cfg["arm_sha256"]) != ARM_HASHES:
            raise GateError("腕ROM SHA-256")
        if len(cfg["judgment"]) != len(set(cfg["judgment"])) \
                or tuple(cfg["judgment"]) != judge.REGISTERED:
            raise GateError("判定名")
        marker = int(one(cfg, "row_marker_address"), 0)
        if marker != analyzer.ROW_MARKER_ADDRESS \
                or marker != mainrom.M6II_ROW_MARKER_ADDRESS \
                or not 0xDF00 <= marker <= 0xE038:
            raise GateError("行番号番地")
        if not equ_address_is_free(marker):
            raise GateError("行番号番地が既存EQUと衝突")
        if marker in range(0xE036, 0xE038):
            raise GateError("行番号番地が既存2バイト領域と衝突")

        chr_source = (REPO / "src/l3_main/main_sub_read_chr.asm").read_text(encoding="utf-8")
        for name in ("H", "D", "R", "RETRY"):
            old = getattr(mainrom, f"M6II_{name}_FAULT_OLD")
            if chr_source.count(old) != 1:
                raise GateError(f"{name}置換対象が一意でない")
        for number, drive, cyl, head, sector in ROWS:
            logical = cyl * 2 + head
            line = f"    DB {number:02X}h,{0 if drive == 'A' else 1:02X}h,{logical:02X}h,{sector:02X}h"
            if mainrom.M6II_BOOT_SWEEP.count(line) != 1:
                raise GateError("ROM内の座標表")

        analyzer_path = HERE / "analyze_m6ii.py"
        if not no_generator_import(analyzer_path):
            raise GateError("G5: 解析器が生成器をimport")
        analyzer_text = analyzer_path.read_text(encoding="utf-8")
        forbidden = ("iterdir(", ".glob(", ".rglob(", "rom-dir", "rom_dir", "N88.ROM")
        if any(token in analyzer_text for token in forbidden):
            raise GateError("G10: 到達判定が走で変わるROMディレクトリを参照")

        prereg = args.prereg.read_text(encoding="utf-8")
        addendum = args.addendum.read_text(encoding="utf-8")
        required_prereg = tuple(f"| {arm} |" for arm in ARMS[1:]) + tuple(
            f"| {n} | {d} | {c} | {h} | {r} |" for n, d, c, h, r in ROWS)
        if any(text not in prereg for text in required_prereg):
            raise GateError("事前登録の腕または座標")
        required_fault_text = ("#2, #5, #7, #9, #10", "#8, #9, #10",
                               "I-F-R | R を1ずらす | すべての行",
                               "再試行が起きた行のうち、ドライブBのもの")
        if any(text not in prereg for text in required_fault_text):
            raise GateError("事前登録の故障注入対応表")
        if any(f"`{name}`" not in prereg + addendum for name in judge.REGISTERED):
            raise GateError("事前登録・追補の判定名")
        required_addendum = ("最後の完全な256位置", "row_no_data", "1800 frames", "各腕2走",
                             "`0xA1`", "`0xB2`", "座標列の順に11個すべて観測される")
        if any(text not in addendum for text in required_addendum):
            raise GateError("追補1の優先条件")
    except (OSError, UnicodeError, ValueError, SyntaxError, GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(args.config.read_bytes()).hexdigest()
    print(f"m6i-i preregistration gate: OK sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
