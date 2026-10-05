#!/usr/bin/env bash
# disk_read_retry_selftest.sh — READ再試行実装のバイト不変・構造・検出力検査
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# want_n88はFILES実装コミット(1cc2528)がこのファイルに書き込んだ凍結値。
# 現在の作業ツリーはLOAD実装でメインROMの中身がさらに変わっているため、
# 作業ツリーでビルドすると一致しない（それが正しい）。凍結値を作った
# コミット自身を取り出してビルドし直して照合する。
# 根拠: git log -S<SHA> --format=%H -- tools/disk_read_retry_selftest.sh
FROZEN_COMMIT=1cc25283921d9a59f86eb92c1cad1aa64dcbea91
# build_main_rom.pyはvendor/(フォント素材)をリポジトリの一段上の兄弟
# ディレクトリとして参照するので、同じ相対位置を再現する。
FROZEN_ROOT="$WORK/frozen-root"
FROZEN_SRC="$FROZEN_ROOT/PC88Behavior"
mkdir -p "$FROZEN_SRC"
ln -s "$REPO/../vendor" "$FROZEN_ROOT/vendor"
git -C "$REPO" archive "$FROZEN_COMMIT" src tools | tar -x -C "$FROZEN_SRC"

python3 "$FROZEN_SRC/src/build_main_rom.py" "$WORK/legacy" --enable-main-sub-read \
  --work-dir "$WORK/legacy-work" >/dev/null
python3 "$REPO/src/build_main_rom.py" "$WORK/plain" \
  --work-dir "$WORK/plain-work" >/dev/null
# want_diskも同様に凍結値。sub ROMが1.36aで変わったため、フラグ無しの
# DISK.ROMも凍結コミットのビルドと照合する（作業ツリーのplainは構造検査用）。
python3 "$FROZEN_SRC/src/build_main_rom.py" "$WORK/plain-frozen" \
  --work-dir "$WORK/plain-frozen-work" >/dev/null
python3 "$REPO/src/build_main_rom.py" "$WORK/retry" --enable-disk-read-retry \
  --work-dir "$WORK/retry-work" >/dev/null

want_n88=4f75d314b4e18c0d6d339977fa92fa0963c57733c389e36733ac047a18ccbe50
want_disk=d8b2e64bc27465f955fd308719228f21b06aa07fd780081a88124a52e6d76070
got_n88="$(shasum -a 256 "$WORK/legacy/N88.ROM" | awk '{print $1}')"
got_disk="$(shasum -a 256 "$WORK/plain-frozen/DISK.ROM" | awk '{print $1}')"
[ "$got_n88" = "$want_n88" ] || {
  echo "NG: --enable-main-sub-read N88.ROM SHA-256不一致" >&2; exit 1;
}
[ "$got_disk" = "$want_disk" ] || {
  echo "NG: フラグ無しDISK.ROM SHA-256不一致" >&2; exit 1;
}

python3 - "$REPO" "$WORK/structure" <<'PY'
import pathlib
import sys

repo, work = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(repo))
import src.build_main_rom as build
from src import memmap

ram = memmap.addresses()
mark_success = b"\x3a" + ram["MM_MAIN_SUB_MARK_SUCCESS"].to_bytes(2, "little")
frame_count_addr = ram["MM_M6IB_FRAME_COUNT"].to_bytes(2, "little")

work.mkdir()
text = build.build_combined_asm(
    work, 0, False, enable_main_sub_read=True, enable_disk_read_retry=True)
rom, asm = build.assemble(text, work)


def structural_checks(code, labels):
    """再試行ルーチンの命令範囲とラベル表に対する独立な4述語。"""
    start = labels["MAIN_SUB_READ_KNOWN_RETRY"]
    end = labels["MAIN_SUB_READ_KNOWN_RETRY_END"]
    body = code[start:end]
    read = labels["MAIN_SUB_READ_KNOWN"]
    call_read = bytes((0xCD, read & 0xFF, read >> 8))
    wait_labels = [
        name for name, address in labels.items()
        if start <= address < end and "wait" in name.lower()
    ]
    return {
        "read_calls_exactly_two": body.count(call_read) == 2,
        "mark_success_refs_at_least_two": body.count(mark_success) >= 2,
        "no_frame_count_ref": frame_count_addr not in body,
        "no_wait_label": not wait_labels,
    }


checks = structural_checks(rom, asm.labels)
if not all(checks.values()):
    raise SystemExit(f"NG: 実ビルド構造検査 {checks}")

start = asm.labels["MAIN_SUB_READ_KNOWN_RETRY"]
end = asm.labels["MAIN_SUB_READ_KNOWN_RETRY_END"]
body = bytes(rom[start:end])
read = asm.labels["MAIN_SUB_READ_KNOWN"]
call_read = bytes((0xCD, read & 0xFF, read >> 8))
frame_ref = b"\x3a" + frame_count_addr
base_labels = {
    "MAIN_SUB_READ_KNOWN_RETRY": 0,
    "MAIN_SUB_READ_KNOWN_RETRY_END": len(body),
    "MAIN_SUB_READ_KNOWN": read,
}

# 各入力は狙った述語だけを偽にし、passed=falseだけでなく偽の集合も照合する。
three_call_labels = dict(base_labels)
three_call_labels["MAIN_SUB_READ_KNOWN_RETRY_END"] = len(body + call_read)
frame_ref_labels = dict(base_labels)
frame_ref_labels["MAIN_SUB_READ_KNOWN_RETRY_END"] = len(body + frame_ref)
negative_cases = {
    "read_calls_exactly_two": (body + call_read, three_call_labels),
    "mark_success_refs_at_least_two": (body.replace(mark_success, b"\x00\x00\x00", 1),
                                        dict(base_labels)),
    "no_frame_count_ref": (body + frame_ref, frame_ref_labels),
    "no_wait_label": (body, {**base_labels, "_retry_wait_bad": 1}),
}
for target, (case_code, case_labels) in negative_cases.items():
    actual = structural_checks(case_code, case_labels)
    failed = {name for name, passed in actual.items() if not passed}
    if failed != {target} or all(actual.values()):
        raise SystemExit(
            f"NG: 陰性対照 {target} が狙った検査だけを落とさない: {actual}")

# 各項目の判定結果だけを常にTrueへ変異させ、対応する陰性対照が
# 期待した偽集合を作れなくなる（自己検査が落ちる）ことを実際に確認する。
def negative_control_passes(checker, target, case_code, case_labels):
    result = checker(case_code, case_labels)
    return {name for name, passed in result.items() if not passed} == {target}


for target, (case_code, case_labels) in negative_cases.items():
    if not negative_control_passes(
            structural_checks, target, case_code, case_labels):
        raise SystemExit(f"NG: {target} の陰性対照が変異前から不成立")

    def force_target_true(code, labels, *, _target=target):
        result = structural_checks(code, labels)
        result[_target] = True
        return result

    if negative_control_passes(
            force_target_true, target, case_code, case_labels):
        raise SystemExit(f"NG: {target} の常時True変異を自己検査が拒否しない")

print("構造4項目OK、陰性対照4件は狙った検査だけfalse、全4項目のTrue変異を拒否")
PY

echo "disk_read_retry_selftest: SHA-256 N88=$got_n88 DISK=$got_disk; OK"
