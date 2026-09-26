#!/usr/bin/env bash
# m6f-e 媒体生成器・独立検査器の正例、項目別陰性対照、manifest凍結を検査する。
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if ! python3 "$REPO/tools/make_m6fe_disk.py" "$WORK/out1" >/dev/null; then
  printf '%s\n' 'NG generator'
  exit 1
fi
if ! python3 "$REPO/tools/make_m6fe_disk.py" "$WORK/out2" >/dev/null; then
  printf '%s\n' 'NG generator_repeat'
  exit 1
fi

REPO="$REPO" WORK="$WORK" python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import struct
import subprocess
import sys


repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
out1 = work / "out1"
out2 = work / "out2"
checker = repo / "tools/check_m6fe_disk.py"
generator = repo / "tools/make_m6fe_disk.py"
manifest_path = out1 / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="ascii"))


def fail(label: str) -> None:
    print(f"NG {label}")
    raise SystemExit(1)


def sector_offsets(image: bytes) -> dict[tuple[int, int, int], int]:
    """自己検査側でD88を走査する。生成器・検査器はimportしない。"""
    starts = [struct.unpack_from("<I", image, 32 + index * 4)[0] for index in range(164)]
    starts = sorted(value for value in starts if value)
    result = {}
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(image)
        pos = start
        while pos < end:
            size = struct.unpack_from("<H", image, pos + 14)[0]
            result[(image[pos], image[pos + 1], image[pos + 2])] = pos + 16
            pos += 16 + size
    return result


def directory_offset(offsets: dict, position: int) -> int:
    sector = 1 + position // 16
    within = (position % 16) * 16
    return offsets[(18, 1, sector)] + within


def fat_offset(offsets: dict, copy_index: int, unit: int) -> int:
    return offsets[(18, 1, 14 + copy_index)] + unit


def run_checker(media_id: str, image_path: pathlib.Path) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(checker), str(manifest_path),
         "--media", media_id, "--image", str(image_path), "--json"],
        text=True, capture_output=True, check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        fail("checker_json")
    return proc.returncode, payload


def expect_single(media_id: str, label: str, mutate) -> None:
    image = bytearray((out1 / manifest["media"][media_id]["file"]).read_bytes())
    offsets = sector_offsets(image)
    mutate(image, offsets)
    path = work / f"bad-{label}.d88"
    path.write_bytes(image)
    rc, payload = run_checker(media_id, path)
    expected = {"failures": {media_id: [label]}}
    if rc != 1 or payload != expected:
        fail(f"negative_{label}")
    print(f"negative_{label}=ok")


# 正例と、検査器が生成器をimportしないこと。
positive = subprocess.run(
    [sys.executable, str(checker), str(manifest_path), "--image-dir", str(out1), "--json"],
    text=True, capture_output=True, check=False,
)
if positive.returncode != 0 or json.loads(positive.stdout) != {"failures": {}}:
    fail("positive")
checker_source = checker.read_text(encoding="utf-8")
if "from make_m6fe_disk import" in checker_source or "import make_m6fe_disk" in checker_source:
    fail("checker_independence")
print("positive=ok")
print("checker_independence=ok")


# D88外形。
expect_single("L4", "d88_shape", lambda image, offsets: image.__setitem__(26, 1))


# ディレクトリ位置: 正しいエントリを、空きで未割当の別セクタにも複製する。
def break_directory_location(image, offsets):
    source = directory_offset(offsets, 0)
    target = offsets[(39, 1, 16)]
    image[target:target + 16] = image[source:source + 16]


expect_single("L4", "directory_location", break_directory_location)
expect_single("L4", "first_unused", lambda image, offsets:
              image.__setitem__(directory_offset(offsets, 4) + 15, 0xFE))
expect_single("L11", "deleted_positions", lambda image, offsets:
              image.__setitem__(directory_offset(offsets, 2), 0x01))


def break_name_length(image, offsets):
    pos = directory_offset(offsets, 0)
    image[pos + manifest["media"]["L11"]["entries"][0]["name_length"]] = ord("X")


expect_single("L11", "name_length", break_name_length)
expect_single("L4", "file_type", lambda image, offsets:
              image.__setitem__(directory_offset(offsets, 0) + 9, 0x01))
expect_single("L4", "entry_reserved", lambda image, offsets:
              image.__setitem__(directory_offset(offsets, 0) + 11, 0xFE))


def break_entry_order(image, offsets):
    first = directory_offset(offsets, 0)
    second = directory_offset(offsets, 1)
    a = bytes(image[first:first + 9])
    b = bytes(image[second:second + 9])
    image[first:first + 9], image[second:second + 9] = b, a


expect_single("L4", "entry_order", break_entry_order)
expect_single("L11", "fat_copies", lambda image, offsets:
              image.__setitem__(fat_offset(offsets, 1, 9), image[fat_offset(offsets, 1, 9)] ^ 1))


def set_all_fats(image, offsets, unit, value):
    for copy_index in range(3):
        image[fat_offset(offsets, copy_index, unit)] = value


expect_single("L11", "chain", lambda image, offsets: set_all_fats(image, offsets, 9, 30))
expect_single("L11", "terminal", lambda image, offsets: set_all_fats(image, offsets, 18, 0xC2))
expect_single("L4", "unit_unique", lambda image, offsets:
              image.__setitem__(directory_offset(offsets, 1) + 10, 0))
expect_single("L4", "fat_free", lambda image, offsets: set_all_fats(image, offsets, 10, 0xA0))
expect_single("L4", "reserved_units", lambda image, offsets: set_all_fats(image, offsets, 74, 0xFF))
expect_single("L4", "write_marker", lambda image, offsets:
              image.__setitem__(offsets[(18, 1, 13)], 1))
expect_single("L4", "body", lambda image, offsets:
              image.__setitem__(offsets[(0, 0, 1)], image[offsets[(0, 0, 1)]] ^ 1))


# manifestの内容・決定性・SHA-256凍結と、その陰性対照。
if len(manifest["arms"]) != 15 or [arm["runs"] for arm in manifest["arms"]] != [2] * 15:
    fail("manifest_arms")
if manifest["media_order"] != ["L0", "L1", "L4", "L5", "L6", "L11", "L96", "D1", "D2"]:
    fail("manifest_media")
if [item["position"] for item in manifest["media"]["L11"]["deleted"]] != [2, 6, 11]:
    fail("manifest_deleted")
if [entry["name"] for entry in manifest["media"]["L11"]["entries"]][-2:] != ["CHAIN10U", "LAST8SEC"]:
    fail("manifest_names")
if [entry["terminal"] for entry in manifest["media"]["L11"]["entries"]][-2:] != [0xC1, 0xC8]:
    fail("manifest_terminals")
if [len(entry["units"]) for entry in manifest["media"]["L11"]["entries"]][-2:] != [10, 1]:
    fail("manifest_units")
arms = {arm["id"]: arm for arm in manifest["arms"]}
if arms["L96"]["final_frame"] != 12000 or arms["L11"]["final_frame"] != 8000:
    fail("manifest_frames")
if arms["D-expr"]["command"] != "CLS:FILES 1+1":
    fail("manifest_commands")
if arms["D-1"]["events"][0]["time"] != "after_boot_complete_before_command":
    fail("manifest_exchange")
if arms["N-wait"]["events"][0]["frame"] != 1200 or arms["N-wait"]["final_frame"] != 4000:
    fail("manifest_insert")

raw1 = manifest_path.read_bytes()
raw2 = (out2 / "manifest.json").read_bytes()
if raw1 != raw2:
    fail("manifest_determinism")
digest = hashlib.sha256(raw1).hexdigest()
if (out1 / "manifest.sha256").read_text(encoding="ascii").split()[0] != digest:
    fail("manifest_digest")
frozen_lines = (repo / "tools/m6fe_frozen.tsv").read_text(encoding="ascii").splitlines()
frozen_fields = dict(line.split("\t") for line in frozen_lines)
if (set(frozen_fields) != {"manifest_sha256", "candidates_sha256"}
        or frozen_fields["manifest_sha256"] != digest
        or len(frozen_fields["candidates_sha256"]) != 64):
    fail("manifest_frozen_value")
wrong = subprocess.run(
    [sys.executable, str(generator), str(work / "reject"),
     "--expected-manifest-sha256", "0" * 64],
    text=True, capture_output=True, check=False,
)
if wrong.returncode != 1:
    fail("generator_hash_negative")
overwrite = subprocess.run(
    [sys.executable, str(generator), str(out1)],
    text=True, capture_output=True, check=False,
)
if overwrite.returncode != 2:
    fail("generator_overwrite_negative")
changed_manifest = work / "changed-manifest.json"
changed_manifest.write_bytes(raw1 + b" ")
changed = subprocess.run(
    [sys.executable, str(checker), str(changed_manifest), "--image-dir", str(out1), "--json"],
    text=True, capture_output=True, check=False,
)
if changed.returncode != 1 or json.loads(changed.stdout) != {"failures": {"manifest": ["manifest_sha256"]}}:
    fail("checker_hash_negative")
print("manifest_freeze=ok")
print("all=ok")
PY
