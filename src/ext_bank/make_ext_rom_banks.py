#!/usr/bin/env python3
"""
src/ext_bank/make_ext_rom_banks.py — 拡張ROMバンク(4th ROM)N88_0.ROM〜
N88_3.ROMを組み立てる。

## 出所

根拠は docs/spec/ext-rom-bank.md だけである。各バンクは8KB(0x2000)、
窓(0x6000-0x7FFF)の内容としてそのまま読まれる(第1節)。埋め草はN88.ROM
本体(src/l1_ipl/make_ipl_rom.py の FILL=0x00)と揃える。

段階2の今回は「バンク切り替えの土台」を作るところまでが対象
(docs/spec/ext-rom-bank.md 第0節「位置づけ(実装スコープ)」配置案C)。
各バンクの中身は自己検査用の固定値を返す試験ルーチン(bank0.asm〜
bank3.asm)。新しいBASICの機能はまだ置かない。

## 0x6000起点のORG(bank0.asmのみ)

bank0.asmは`ORG 0x6000`・`ORG 0x6010`を前提に書く(コメント参照)。
z80textはORGで前方へ飛ぶと、その分を0で埋めたバイト列を返す仕様
(`z80text.Assembler.pass2`)なので、ここではアセンブル後に先頭0x6000
バイト(詰め物)を切り落として実際の8KBバンクファイルにする。
絶対番地のCALL・JP・LD A,(nn)等は、この「窓として見える実番地
(0x6000-0x7FFF)」でエンコードされて初めて正しく動く。

## 使い方

    python3 src/ext_bank/make_ext_rom_banks.py <出力先ディレクトリ>
    python3 src/ext_bank/make_ext_rom_banks.py <出力先> --inject-no-org-fault
        # 故障注入: bank0.asmのORG 0x6000/0x6010を0x0000/0x0010へ
        # テキスト置換してから組み立てる(自己検査の陰性対照専用。
        # 絶対番地参照が実際の窓の番地とズレる)
"""

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "tools" / "asm"))

import z80text  # noqa: E402

BANK_SIZE = 0x2000     # 8KB。窓(0x6000-0x7FFF)と同じ大きさ
BANK_ORG = 0x6000      # 窓の先頭番地
FILL = 0x00            # src/l1_ipl/make_ipl_rom.py の FILL と揃える

BANK_FILES = (
    ("N88_0.ROM", "bank0.asm"),
    ("N88_1.ROM", "bank1.asm"),
    ("N88_2.ROM", "bank2.asm"),
    ("N88_3.ROM", "bank3.asm"),
)

# 故障注入(--inject-no-org-fault、自己検査の陰性対照専用)。
# bank0.asmのORG 0x6000/0x6010を0x0000/0x0010へ書き換える
# (build_main_rom.pyのCURSOR_OLD/NEW等と同じテキスト置換の手法)。
NO_ORG_FAULT_SUBS = (
    ("    ORG 0x6000\n", "    ORG 0x0000\n"),
    ("    ORG 0x6010\n", "    ORG 0x0010\n"),
)


def assemble_bank(rom_name: str, asm_path: pathlib.Path, work: pathlib.Path,
                   inject_no_org_fault: bool = False) -> bytes:
    text = asm_path.read_text(encoding="utf-8")
    # bank0.asmのように明示的に「ORG 0x6000」で始まるファイルだけ、
    # 詰め物(baseバイト)を切り落とす対象にする。ORGを使わない
    # bank1-3.asmはPC 0始まり=そのままファイル先頭が窓の先頭を意味する
    # ので、base=0(無変更)のままでよい。
    has_org = "    ORG 0x6000\n" in text
    base = BANK_ORG if has_org else 0
    if inject_no_org_fault and has_org:
        for old, new in NO_ORG_FAULT_SUBS:
            if old in text:
                if text.count(old) != 1:
                    raise SystemExit(
                        f"{asm_path.name}: 故障注入の置換対象が一意でない: {old!r}")
                text = text.replace(old, new)
                base = 0
    src_path = work / f"{asm_path.stem}_gen.asm"
    src_path.write_text(text, encoding="utf-8")

    asm = z80text.Assembler()
    try:
        code = asm.assemble(src_path)
    except z80text.AsmError as e:
        raise SystemExit(f"{asm_path.name}: z80text アセンブルエラー: {e}")

    # ORGによる先頭の詰め物(baseバイト)を切り落として、ファイル先頭
    # (=実行時は常に窓の先頭0x6000)からの内容にする。ORGを使わない
    # バンク(bank1-3)はbase=0でここは無害な no-op。
    if len(code) < base:
        raise SystemExit(
            f"{asm_path.name}: ORG 0x{base:04X} の詰め物が想定より短い"
            f"(コードが{len(code)}バイトしか無い)")
    code = code[base:]

    if len(code) > BANK_SIZE:
        raise SystemExit(
            f"{asm_path.name}: バンク(8KB)に収まらない: {len(code)} > {BANK_SIZE}")
    rom = bytearray([FILL] * BANK_SIZE)
    rom[: len(code)] = code
    return bytes(rom)


def build_banks(outdir: pathlib.Path, inject_no_org_fault: bool = False):
    import tempfile
    outdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pc88_extbank_") as work_s:
        work = pathlib.Path(work_s)
        for rom_name, asm_name in BANK_FILES:
            rom = assemble_bank(rom_name, HERE / asm_name, work, inject_no_org_fault)
            (outdir / rom_name).write_bytes(rom)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--inject-no-org-fault", action="store_true",
                     help="故障注入: bank0.asmのORGを0始まりへ書き換えて組み立てる"
                          "（自己検査の陰性対照専用）")
    args = ap.parse_args()
    build_banks(args.outdir, args.inject_no_org_fault)
    print(f"生成した: {args.outdir} (N88_0.ROM〜N88_3.ROM 各{BANK_SIZE}バイト)")


if __name__ == "__main__":
    main()
