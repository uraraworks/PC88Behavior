#!/usr/bin/env bash
# main_sub_link_selftest.sh — main<->sub通信・既知1セクタREAD入口の短い自己検査
# エミュレータ実走は行わない。実ビルド、既定組込み・末尾1160B・予約番地、sub不変、
# および3種の故障注入が対応コード列を変えることだけを検査する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
BUILD="$REPO/src/build_main_rom.py"

python3 "$BUILD" "$WORK/dist" >/dev/null || {
    echo "NG: 配布構成の実ビルドに失敗" >&2
    exit 1
}
python3 "$BUILD" "$WORK/disabled" --disable-main-sub-read >/dev/null || {
    echo "NG: main-sub READ無効構成の実ビルドに失敗" >&2
    exit 1
}
python3 "$BUILD" "$WORK/enabled" --enable-main-sub-read >/dev/null || {
    echo "NG: main-sub READ有効構成の実ビルドに失敗" >&2
    exit 1
}
for fault in wait cont pair; do
    python3 "$BUILD" "$WORK/fault_$fault" "--inject-main-sub-${fault}-fault" \
        >/dev/null || {
        echo "NG: ${fault}故障注入構成の実ビルドに失敗" >&2
        exit 1
    }
done

if ! cmp -s "$WORK/dist/DISK.ROM" "$WORK/enabled/DISK.ROM"; then
    echo "NG: main-sub READ有効化でsub ROMが変化した" >&2
    exit 1
fi
for fault in wait cont pair; do
    if ! cmp -s "$WORK/dist/DISK.ROM" "$WORK/fault_$fault/DISK.ROM"; then
        echo "NG: ${fault}故障注入でsub ROMが変化した" >&2
        exit 1
    fi
done

python3 - "$WORK/asm" <<'PY'
import pathlib
import sys

root = pathlib.Path.cwd()
sys.path.insert(0, str(root))
import src.build_main_rom as build
import z80text

base = pathlib.Path(sys.argv[1])
base.mkdir(parents=True, exist_ok=True)


def make(name, **kwargs):
    work = base / name
    work.mkdir()
    text = build.build_combined_asm(work, 0, False, **kwargs)
    rom, asm = build.assemble(text, work)
    code_asm = z80text.Assembler()
    code = code_asm.assemble(work / "n88_main_gen.asm")
    return rom, asm, code


dist_rom, dist_asm, dist_code = make(
    "dist", enable_main_sub_read=True, enable_disk_read_retry=True,
    enable_disk_read_chr=True, enable_main_sub_boot=False)
disabled_rom, disabled_asm, disabled_code = make("disabled")
normal_rom, normal_asm, normal_code = make(
    "normal", enable_main_sub_read=True)
faults = {
    "wait": make("wait", enable_main_sub_read=True,
                 inject_main_sub_wait_fault=True),
    "cont": make("cont", enable_main_sub_read=True,
                 inject_main_sub_cont_fault=True),
    "pair": make("pair", enable_main_sub_read=True,
                 inject_main_sub_pair_fault=True),
}

base_required = (
    "MAIN_SUB_LINK_START", "MAIN_SUB_LINK_END", "MAIN_SUB_SEND",
    "MAIN_SUB_SEND_CONT", "MAIN_SUB_SEND_PAIR", "MAIN_SUB_RECV",
    "MAIN_SUB_RECV_PAIR", "MAIN_SUB_READ_KNOWN",
)
retry_required = ("MAIN_SUB_READ_KNOWN_RETRY", "DISK_READ_RETRY_BOOT_ONCE")
chr_required = ("MAIN_SUB_READ_CHR", "MAIN_SUB_READ_CHR_RETRY")
required = base_required + retry_required + chr_required
if any(label in disabled_asm.labels for label in required):
    raise SystemExit("NG: 無効構成にmain-sub READ入口が残った")
if any(label not in dist_asm.labels for label in required):
    raise SystemExit("NG: 配布構成の必須ラベルが不足")
if any(label not in normal_asm.labels for label in base_required):
    raise SystemExit("NG: 有効構成の必須ラベルが不足")
if any(label in normal_asm.labels for label in retry_required + chr_required):
    raise SystemExit("NG: main単独の測定構成に別ルーチンが混入した")

dist_text = (base / "dist" / "n88_main_gen.asm").read_text(encoding="utf-8")
for call in (
    "    CALL MAIN_SUB_READ_INIT\n", "    CALL DISK_READ_RETRY_INIT\n",
    "    CALL MAIN_SUB_READ_BOOT_ONCE\n", "    CALL DISK_READ_RETRY_BOOT_ONCE\n",
):
    if call in dist_text:
        raise SystemExit(f"NG: 配布構成の起動経路に検査呼出しが混入: {call.strip()}")

start = dist_asm.labels["MAIN_SUB_LINK_START"]
end = dist_asm.labels["MAIN_SUB_READ_CHR_RETRY_END"]
link_size = end - start
increase = len(dist_code) - len(disabled_code)
if start < len(disabled_code) or end != len(dist_code):
    raise SystemExit("NG: main-sub常駐部がmain ROM末尾へ配置されていない")
if link_size > build.MAIN_SUB_LINK_MAX_SIZE:
    raise SystemExit(f"NG: 3ルーチンが1160B超過: {link_size}")
if increase > build.MAIN_SUB_LINK_MAX_SIZE:
    raise SystemExit(f"NG: main ROM増分が1160B超過: {increase}")
if dist_rom[build.ROM_VERSION_RESERVED_ADDR] != build.FILL:
    raise SystemExit("NG: 0x79D7予約バイトが埋め草でない")
before_reserved = dist_rom[:build.ROM_VERSION_RESERVED_ADDR]
reserved_margin = len(before_reserved) - len(before_reserved.rstrip(bytes((build.FILL,))))
if reserved_margin <= 0:
    raise SystemExit("NG: 0x79D7予約番地の直前に余白がない")

sites = {
    "wait": ("_ms_send_wait_before_site", "_ms_send_wait_before_site_end"),
    "cont": ("_ms_cont_call_site", "_ms_cont_call_site_end"),
    "pair": ("_ms_pair_call_site", "_ms_pair_call_site_end"),
}


def site_bytes(rom, asm, site):
    first, last = sites[site]
    return rom[asm.labels[first]:asm.labels[last]]


for fault_name, (fault_rom, fault_asm, fault_code) in faults.items():
    if len(fault_code) != len(normal_code):
        raise SystemExit(f"NG: {fault_name}故障注入で配置長が変化した")
    if fault_rom[build.ROM_VERSION_RESERVED_ADDR] != build.FILL:
        raise SystemExit(f"NG: {fault_name}故障版が0x79D7予約バイトを破壊")
    for site in sites:
        changed = (site_bytes(normal_rom, normal_asm, site)
                   != site_bytes(fault_rom, fault_asm, site))
        if changed != (site == fault_name):
            raise SystemExit(
                f"NG: {fault_name}故障版の{site}コード列 changed={changed}")

print(f"OK: build/placement/faults increase={increase} link={link_size} "
      f"reserved_margin={reserved_margin}")
PY
