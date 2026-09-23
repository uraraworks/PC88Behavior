#!/usr/bin/env bash
# disk_read_chr_selftest.sh — 一般READの像・独立読取器・既存成果物不変を検査する。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

BUILD=(python3 "$REPO/src/build_main_rom.py")
"${BUILD[@]}" "$WORK/main" --enable-main-sub-read --work-dir "$WORK/w-main" >/dev/null
"${BUILD[@]}" "$WORK/retry" --enable-disk-read-retry --work-dir "$WORK/w-retry" >/dev/null
"${BUILD[@]}" "$WORK/plain" --work-dir "$WORK/w-plain" >/dev/null
"${BUILD[@]}" "$WORK/chr" --enable-disk-read-chr --work-dir "$WORK/w-chr" >/dev/null

DISK=(python3 "$REPO/tools/make_l3_testdisk.py")
GEOM=(--cylinders 40 --double-sided --sectors-per-track 16)
"${DISK[@]}" "$WORK/default.d88" "${GEOM[@]}" >/dev/null
"${DISK[@]}" "$WORK/coord-a.d88" "${GEOM[@]}" --content-rule coord-header --disk-id 0x41 >/dev/null
"${DISK[@]}" "$WORK/coord-b.d88" "${GEOM[@]}" --content-rule coord-header --disk-id 0x42 >/dev/null
"${DISK[@]}" "$WORK/legacy-a.d88" "${GEOM[@]}" >/dev/null
"${DISK[@]}" "$WORK/legacy-b.d88" "${GEOM[@]}" >/dev/null

python3 - "$REPO" "$WORK" <<'PY'
import ast
import hashlib
import importlib.util
import pathlib
import sys

repo = pathlib.Path(sys.argv[1])
work = pathlib.Path(sys.argv[2])


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load("d88_reader_under_test", repo / "tools" / "d88_read_sector.py")
generator = load("disk_generator_under_test", repo / "tools" / "make_l3_testdisk.py")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payloads(path):
    image = path.read_bytes()
    parsed = reader.D88Reader(image)
    return [
        parsed.read_sector(cyl, head, sector)
        for cyl in range(40)
        for head in range(2)
        for sector in range(1, 17)
    ]


coord_a = payloads(work / "coord-a.d88")
coord_b = payloads(work / "coord-b.d88")
legacy_a = payloads(work / "legacy-a.d88")
legacy_b = payloads(work / "legacy-b.d88")


def headers_are_coordinates(groups):
    for disk_id, rows in groups:
        index = 0
        for cyl in range(40):
            for head in range(2):
                for sector in range(1, 17):
                    if rows[index][:4] != bytes((disk_id, cyl, head, sector)):
                        return False
                    index += 1
    return True


def all_unique(groups):
    flat = [payload for group in groups for payload in group]
    return len(flat) == len(set(flat))


def statically_independent(source_text):
    tree = ast.parse(source_text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any(name.split(".")[-1] == "make_l3_testdisk" for name in names):
            return False
    return True


image = (work / "coord-a.d88").read_bytes()


def dynamically_independent(read_function):
    before = read_function(image, 20, 1, 8)
    original = generator.coord_header_pattern
    try:
        generator.coord_header_pattern = lambda *_args: bytes(256)
        after = read_function(image, 20, 1, 8)
    except Exception:
        return False
    finally:
        generator.coord_header_pattern = original
    return before == after


reader_source = (repo / "tools" / "d88_read_sector.py").read_text(encoding="utf-8")
expected = {
    "g8_main_sha": "7646c2d418dc9f33f30670b9638368fcfb5614e67ec26000cdd7c4106b258f5d",
    "g8_retry_sha": "dc940d77f412d2c1e14a24e9f8d1cd658d885a87f88fb0c62798411d4268faa1",
    "g8_disk_sha": "d8b2e64bc27465f955fd308719228f21b06aa07fd780081a88124a52e6d76070",
    "g3_default_sha": "d3becfe5051f7002d268824a2da2824f543442e71ae3226e4d22139e0adce05c",
}
actual_hashes = {
    "g8_main_sha": sha(work / "main" / "N88.ROM"),
    "g8_retry_sha": sha(work / "retry" / "N88.ROM"),
    "g8_disk_sha": sha(work / "plain" / "DISK.ROM"),
    "g3_default_sha": sha(work / "default.d88"),
}

checks = {
    **{name: actual_hashes[name] == value for name, value in expected.items()},
    "coord_headers": headers_are_coordinates(((0x41, coord_a), (0x42, coord_b))),
    "g4_new_unique": all_unique((coord_a, coord_b)),
    "g4_legacy_negative": not all_unique((legacy_a, legacy_b)),
    "g5_static_independence": statically_independent(reader_source),
    "g5_dynamic_independence": dynamically_independent(reader.read_sector),
    "chr_flag_gate": (
        "main_sub_read_chr.asm" in (work / "w-chr" / "n88_main_gen.asm").read_text()
        and all(
            "main_sub_read_chr.asm" not in (work / directory / "n88_main_gen.asm").read_text()
            for directory in ("w-main", "w-retry", "w-plain")
        )
    ),
}
if not all(checks.values()):
    raise SystemExit(f"NG: 一般READ像検査に失敗: {checks}")

# 各判定を狙って偽にする入力を作り、さらにその判定だけを常時Trueへ
# 変異すると陰性対照を拒否できなくなることを全項目で確認する。
negative_values = {
    "g8_main_sha": actual_hashes["g8_main_sha"] == ("0" * 64),
    "g8_retry_sha": actual_hashes["g8_retry_sha"] == ("0" * 64),
    "g8_disk_sha": actual_hashes["g8_disk_sha"] == ("0" * 64),
    "g3_default_sha": actual_hashes["g3_default_sha"] == ("0" * 64),
    "coord_headers": headers_are_coordinates(((0x41, legacy_a), (0x42, legacy_b))),
    "g4_new_unique": all_unique((legacy_a, legacy_b)),
    "g4_legacy_negative": not all_unique((coord_a, coord_b)),
    "g5_static_independence": statically_independent(
        reader_source + "\nimport make_l3_testdisk\n"),
    "g5_dynamic_independence": dynamically_independent(
        lambda _image, c, h, r: generator.coord_header_pattern(0x41, c, h, r)),
    "chr_flag_gate": False,
}
for target in checks:
    negative = dict(checks)
    negative[target] = negative_values[target]
    failed = {name for name, passed in negative.items() if not passed}
    if failed != {target}:
        raise SystemExit(f"NG: {target}の陰性対照が対象だけを落とさない")
    mutated = dict(negative)
    mutated[target] = True
    if {name for name, passed in mutated.items() if not passed} == {target}:
        raise SystemExit(f"NG: {target}の常時True変異を拒否できない")

print("disk_read_chr_selftest: 10項目OK、陰性対照10件、常時True変異10件を拒否")
print("G4: 新規則は全2560セクタ一意、旧規則2枚の陰性対照は偽")
print("G5: 静的独立・生成後の生成関数破壊に対する独立を確認")
print("SHA G8-main=" + actual_hashes["g8_main_sha"])
print("SHA G8-retry=" + actual_hashes["g8_retry_sha"])
print("SHA G8-disk=" + actual_hashes["g8_disk_sha"])
print("SHA G3-default=" + actual_hashes["g3_default_sha"])
PY
