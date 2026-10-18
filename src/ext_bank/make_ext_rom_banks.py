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

## 0x6000起点のORG

bank0.asmなどは`ORG 0x6000`以降を前提に書く(各コメント参照)。
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
sys.path.insert(0, str(REPO / "src"))

import z80text  # noqa: E402
import memmap  # noqa: E402

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
# 絶対番地試験を含む先頭部分だけを別に組み立て、通常バンクの同じ位置へ
# 戻す。機能本体のORGには触れず、追加されたORGの置換漏れによる8KB超過
# を防ぐ。通常の配置・呼び先検査は全て行う。
NO_ORG_FAULT_SUBS = (
    ("    ORG 0x6000\n", "    ORG 0x0000\n"),
    ("    ORG 0x6010\n", "    ORG 0x0010\n"),
)

# bank0.asmのEXT_BANK0_MBF_TEST_ENTRY(「バンク0の試験ルーチンが常駐の
# 単精度演算を呼んで正しい結果を返す」自己検査、docs/spec/ext-rom-bank.md
# 第2節 制約3)が参照する、常駐部(N88.ROM)側MBF_ADDの絶対番地の既定値の
# 行。バンクは独立にアセンブルされ、N88.ROM側のレイアウトを直接は参照
# できないため、build_main_rom.pyが実際に組み立てたN88.ROMのMBF_ADDの
# アドレスをここへテキスト置換で渡す(--mbf-add-addr)。渡されない場合は
# bank0.asmの既定値のまま(ズレていれば自己検査が不一致を検出する——
# これ自体が「密結合がズレたこと」の検出になる、安全側の設計)。
MBF_ADD_ADDR_OLD = "MBF_ADD_ADDR EQU 0x1787"

# bank0.asmのEXT_BANK0_SQR_ENTRY（第4.16b節SQR）が参照する常駐部
# (mbf_double.asm)側ルーチンの絶対番地。MBF_ADD_ADDRと同じ理由・同じ
# 手法(build_main_rom.pyが実測値をテキスト置換)で汎用化した
# (--addr NAME=0xNNNN、複数指定可)。EQU名はbank0.asm側の宣言
# 「<NAME> EQU 0x1787」と一致させる。
GENERIC_ADDR_PLACEHOLDER = "0x1787"


def _generic_addr_subs(text: str, addr_overrides: dict) -> str:
    if not addr_overrides:
        return text
    for name, addr in addr_overrides.items():
        old = f"{name} EQU {GENERIC_ADDR_PLACEHOLDER}"
        if old not in text:
            continue
        if text.count(old) != 1:
            raise SystemExit(f"{name}の置換対象が一意でない")
        text = text.replace(old, f"{name} EQU 0x{addr:04X}")
    return text


# bank3.asm の後ろへこの順に連結する。ビルド・器具とも compose_bank_text()
# を使い、差し込み・capacity断片を含むソース合成を一元化する。
BANK3_EXTRA_SOURCES = (
    "src/l4_basic/listnum.asm",
    "src/l4_basic/input.asm",
    "src/ext_bank/inkey.asm",
    "src/l3_main/key_table_gen.asm",
    "src/l4_basic/strfunc.asm",
    "src/l4_basic/key.asm",
    "src/l4_basic/peekpoke.asm",
    "src/l4_basic/hexconst.asm",
    "src/l4_basic/forstack.asm",
)


def insert_capacity_sources(text: str, bank_name: str, addr_overrides: dict) -> str:
    """c1断片を既存ORG区間の後へ挿入し、固定入口を動かさない。"""
    import re
    bank = int(bank_name[4])
    parts = re.split(r"(?=^    ORG )", text, flags=re.M)
    additions = []
    for path in sorted(HERE.glob(f"capacity_{bank}_*.asm")):
        extra = path.read_text(encoding="utf-8")
        org = re.search(r"^    ORG 0x([0-9A-F]+)", extra, re.M)
        if org is None:
            raise SystemExit(f"{path.name}: ORGが無い")
        additions.append((int(org[1], 16), extra))
    chunks = [(int(re.search(r"^    ORG (?:0x)?([0-9A-F]+)", p, re.M)[1], 16), p)
              for p in parts if p.startswith("    ORG ")]
    prefix = "".join(p for p in parts if not p.startswith("    ORG "))
    # RAM別名はmemmapの正典、main呼出先は実アセンブル番地から生成。
    declared = set(re.findall(r"^([A-Za-z_]\w*)\s+EQU", text, re.M))
    for name, expr in CAPACITY_RAM_ALIASES[bank].items():
        if name not in declared:
            prefix += f"{name} EQU {expr}\n"
    for name in (addr_overrides or {}):
        if name.startswith("CAP_") and name not in declared:
            prefix += f"{name} EQU 0x1787\n"
    return prefix + "\n".join(p for _, p in sorted(chunks + additions))

CAPACITY_RAM_ALIASES = {0: {'CUR_DATA': 'MM_CUR_DATA', 'RUN_ARG1': 'MM_RUN_ARG1', 'RUN_STR_TMP_LEN': 'MM_RUN_STR_TMP_LEN', 'RUN_STR_ARG1_BUF': 'MM_RUN_STR_ARG1_BUF', 'CUR_TYPE': 'MM_CUR_TYPE', 'RUN_STR_ARG1_LEN': 'MM_RUN_STR_ARG1_LEN', 'ERROR_FLAG': 'MM_ERROR_FLAG', 'RUN_STR_TMP_BUF': 'MM_RUN_STR_TMP_BUF', 'RUN_TMP16': 'MM_RUN_TMP16'}, 1: {'PROG_REND_PTR': 'MM_PROG_REND_PTR', 'ERROR_KIND': 'MM_ERROR_KIND', 'RUN_DATA_MAIN_SAVE_END': 'MM_RUN_DATA_MAIN_SAVE_END', 'PROG_REND_PREV': 'MM_PROG_REND_PREV', 'RUN_DATA_STATE': 'MM_RUN_DATA_STATE', 'ERROR_FLAG': 'MM_ERROR_FLAG', 'PROGRAM_AREA': 'MM_PROGRAM_AREA', 'PROG_REND_LEN': 'MM_PROG_REND_LEN', 'PROG_REND_MODE': 'MM_PROG_REND_MODE', 'RUN_DATA_WANT_KIND': 'MM_RUN_DATA_WANT_KIND', 'RUN_DATA_END': 'MM_RUN_DATA_END', 'RUN_DATA_MAIN_SAVE_PTR': 'MM_RUN_DATA_MAIN_SAVE_PTR', 'CUR_PTR': 'MM_CUR_PTR', 'PROG_REND_INNAME': 'MM_PROG_REND_INNAME', 'RUN_DATA_REC': 'MM_RUN_DATA_REC', 'RUN_DATA_PTR': 'MM_RUN_DATA_PTR', 'LINE_END': 'MM_LINE_END'}, 2: {'FOUT_SIGN': 'MM_FOUT_SIGN', 'CUR_TYPE': 'MM_CUR_TYPE', 'RUN_STR_TMP_BUF': 'MM_RUN_STR_TMP_BUF', 'PUD_DIGIT': 'MM_PUD_DIGIT', 'CUR_DATA': 'MM_CUR_DATA', 'UA_EXP': 'MM_UA_EXP', 'PUD_VALUE': 'MM_PUD_VALUE', 'PUD_PLACE': 'MM_PUD_PLACE', 'FOUT_LEN': 'MM_FOUT_LEN', 'PUD_STARTED': 'MM_PUD_STARTED', 'RUN_STR_TMP_LEN': 'MM_RUN_STR_TMP_LEN', 'RUN_ARRAY_ASSIGN_ADDR': 'MM_RUN_ARRAY_ASSIGN_ADDR', 'FOUT_BUF': 'MM_FOUT_BUF', 'RUN_ASSIGN_KIND': 'MM_RUN_ASSIGN_KIND'}, 3: {'IDENT_BUF': 'MM_IDENT_BUF', 'ERROR_KIND': 'MM_ERROR_KIND', 'RUN_STR_TMP_BUF': 'MM_RUN_STR_TMP_BUF', 'RUN_ARG1': 'MM_RUN_ARG1', 'RUN_STR_ARG1_LEN': 'MM_RUN_STR_ARG1_LEN', 'ERROR_FLAG': 'MM_ERROR_FLAG', 'MBF_STATUS': 'MM_MBF_STATUS', 'RUN_ASSIGN_NAME': 'MM_RUN_ASSIGN_NAME', 'LIT_HASSUFFIX': 'MM_LIT_HASSUFFIX', 'LIT_HASDOT': 'MM_LIT_HASDOT', 'LIT_HASEXP': 'MM_LIT_HASEXP', 'RUN_STR_TMP_LEN': 'MM_RUN_STR_TMP_LEN', 'RUN_STR_ARG1_BUF': 'MM_RUN_STR_ARG1_BUF', 'RUN_DATA_NEG': 'MM_RUN_DATA_NEG', 'RUN_ASSIGN_KIND': 'MM_RUN_ASSIGN_KIND'}}


def compose_bank_text(asm_path: pathlib.Path, addr_overrides: dict = None,
                      mbf_add_addr: int = None, *,
                      include_extensions: bool = True) -> str:
    """RAM宣言と呼出先置換済みのソースをビルド・器具で共有する。

    通常は差し込み・追加ソース・capacity断片をすべて含める。
    演算単体の照合器は、追加領域を試験ベクトル表に使うため
    include_extensions=Falseで本体だけをハーネスに連結する。
    """
    text = asm_path.read_text(encoding="utf-8")
    if include_extensions:
        if asm_path.name == "bank0.asm":
            # gfxhook.asm は 0x6A34（bank0.asm の末尾 0x6A33 と deffn.asm の先頭 0x6B00 の間の空き）。ORGは前へ戻せないのでこの順。
            text += "\n" + (REPO / "src/l4_basic/gfxhook.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/l4_basic/deffn.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/l4_basic/tabspc.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/l4_basic/deftype.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/l4_basic/widthbeep.asm").read_text(encoding="utf-8")
        if asm_path.name == "bank2.asm":
            text = text.replace("    ORG 0x7000", (REPO / "src/ext_bank/array.asm").read_text(encoding="utf-8") + "\n" + (REPO / "src/ext_bank/getput.asm").read_text(encoding="utf-8") + "\n" + (REPO / "src/ext_bank/linefast.asm").read_text(encoding="utf-8") + "\n    ORG 0x7000", 1)
            text += "\n" + (REPO / "src/ext_bank/gfx.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/ext_bank/line.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/ext_bank/paintp.asm").read_text(encoding="utf-8")
        if asm_path.name == "bank3.asm":
            text = text.replace("    ORG 0x6100", (REPO / "src/l4_basic/portio_reserved.asm").read_text(encoding="utf-8") + "\n    ORG 0x6100", 1)
            text = text.replace("    ORG 0x6180", (REPO / "src/l4_basic/portio_lhs.asm").read_text(encoding="utf-8") + "\n    ORG 0x6180", 1)
            for rel in BANK3_EXTRA_SOURCES:
                extra = (REPO / rel).read_text(encoding="utf-8")
                if rel.endswith("inkey.asm"):
                    extra = (REPO / "src/l4_basic/portio_words.asm").read_text(encoding="utf-8") + "\n" + extra
                if rel.endswith("peekpoke.asm"):
                    extra = (REPO / "src/l4_basic/portio.asm").read_text(encoding="utf-8") + "\n" + extra
                text += "\n" + extra
        if asm_path.name == "bank1.asm":
            text = text.replace("    ORG 0x6400", (REPO / "src/l4_basic/keyrow.asm").read_text(encoding="utf-8") + "\n    ORG 0x6400", 1)
            text = text.replace("    ORG 0x6C00", (REPO / "src/l4_basic/input_token.asm").read_text(encoding="utf-8") + "\n    ORG 0x6C00", 1)
            text += "\n" + (REPO / "src/l4_basic/pusing.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/l4_basic/onwhile.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/ext_bank/dim.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/ext_bank/array_parse.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/ext_bank/circle.asm").read_text(encoding="utf-8")
            text += "\n" + (REPO / "src/ext_bank/paint.asm").read_text(encoding="utf-8")
        # c1: 既存の固定入口の間へ低頻度処理を置く。ORGは必ず昇順。
        text = insert_capacity_sources(text, asm_path.name, addr_overrides)
    if mbf_add_addr is not None and MBF_ADD_ADDR_OLD in text:
        if text.count(MBF_ADD_ADDR_OLD) != 1:
            raise SystemExit(f"{asm_path.name}: MBF_ADD_ADDRの置換対象が一意でない")
        text = text.replace(MBF_ADD_ADDR_OLD, f"MBF_ADD_ADDR EQU 0x{mbf_add_addr:04X}")
    # RAMの正典はROM呼び先の実測置換と独立。アセンブル単位ごとに一度配る。
    text = memmap.asm_prelude() + _generic_addr_subs(text, addr_overrides)
    return text


def assemble_bank(rom_name: str, asm_path: pathlib.Path, work: pathlib.Path,
                   inject_no_org_fault: bool = False,
                   mbf_add_addr: int = None,
                   addr_overrides: dict = None) -> bytes:
    text = compose_bank_text(asm_path, addr_overrides, mbf_add_addr)
    # 明示的に「ORG 0x6000」で始まるファイルは、先頭の詰め物を切り落とす。
    # ORGを使わない構成ならPC 0始まりなのでbase=0でよい。
    has_org = "    ORG 0x6000\n" in text
    base = BANK_ORG if has_org else 0
    src_path = work / f"{asm_path.stem}_gen.asm"
    src_path.write_text(text, encoding="utf-8")

    asm = z80text.Assembler()
    try:
        code = asm.assemble(src_path)
    except z80text.AsmError as e:
        raise SystemExit(f"{asm_path.name}: z80text アセンブルエラー: {e}")

    # mainの実ラベルから渡したEQUが、バンクの呼び先にも反映されたか検査。
    for name, addr in (addr_overrides or {}).items():
        if name in asm.labels and asm.labels[name] != addr:
            raise SystemExit(f"error: {asm_path.name}: {name} の呼び先番地が不一致")

    # ORGによる先頭の詰め物(baseバイト)を切り落として、ファイル先頭
    # (=実行時は常に窓の先頭0x6000)からの内容にする。ORGを使わない
    # バンクはbase=0でここは無害な no-op。
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
    if inject_no_org_fault and asm_path.name == "bank0.asm":
        # 0x6030以降は常駐MBF呼出し試験と機能本体。そこは通常ビルドと同一。
        boundary = "    ORG 0x6030\n"
        if text.count(boundary) != 1:
            raise SystemExit("bank0.asm: ORG故障注入の終端が一意でない")
        fault_text = text.split(boundary, 1)[0]
        for old, new in NO_ORG_FAULT_SUBS:
            if fault_text.count(old) != 1:
                raise SystemExit(f"bank0.asm: 故障注入の置換対象が一意でない: {old!r}")
            fault_text = fault_text.replace(old, new)
        fault_path = work / "bank0_no_org_test_gen.asm"
        fault_path.write_text(fault_text, encoding="utf-8")
        fault_asm = z80text.Assembler()
        try:
            fault_code = fault_asm.assemble(fault_path)
        except z80text.AsmError as e:
            raise SystemExit(f"bank0.asm: ORG故障注入のアセンブルエラー: {e}")
        # 注入がMBF試験以降に及んだ場合はビルドを止める。
        test_end = asm.labels["EXT_BANK0_ABS_TABLE"] + 1 - base
        if len(fault_code) != test_end or test_end > 0x30:
            raise SystemExit("bank0.asm: ORG故障注入が絶対番地試験の範囲を超えた")
        rom[:test_end] = fault_code
    return bytes(rom)


def build_banks(outdir: pathlib.Path, inject_no_org_fault: bool = False,
                 mbf_add_addr: int = None, addr_overrides: dict = None):
    import tempfile
    outdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pc88_extbank_") as work_s:
        work = pathlib.Path(work_s)
        for rom_name, asm_name in BANK_FILES:
            rom = assemble_bank(rom_name, HERE / asm_name, work, inject_no_org_fault,
                                 mbf_add_addr=mbf_add_addr, addr_overrides=addr_overrides)
            (outdir / rom_name).write_bytes(rom)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--inject-no-org-fault", action="store_true",
                     help="故障注入: bank0.asmのORGを0始まりへ書き換えて組み立てる"
                          "（自己検査の陰性対照専用）")
    ap.add_argument("--mbf-add-addr", type=lambda s: int(s, 0), default=None,
                     help="bank0.asmのEXT_BANK0_MBF_TEST_ENTRYが参照する常駐部"
                          "MBF_ADDの絶対番地(例: 0x1787)。build_main_rom.pyが"
                          "実測値を渡す。省略時はbank0.asmの既定値のまま")
    ap.add_argument("--addr", action="append", default=[],
                     metavar="NAME=0xNNNN",
                     help="bank0.asm等が参照する常駐部ルーチンの絶対番地を"
                          "汎用的に置換する(例: --addr MBF_STOD_ADDR=0x1234)。"
                          "複数指定可。EXT_BANK0_SQR_ENTRY用のMBF_STOD_ADDR/"
                          "MBF_DADD_ADDR/MBF_DDIV_ADDR/MBF_DTOS_ADDRなど。")
    args = ap.parse_args()
    addr_overrides = {}
    for item in args.addr:
        if "=" not in item:
            raise SystemExit(f"--addr は NAME=0xNNNN 形式: {item!r}")
        name, val = item.split("=", 1)
        addr_overrides[name] = int(val, 0)
    build_banks(args.outdir, args.inject_no_org_fault, mbf_add_addr=args.mbf_add_addr,
                addr_overrides=addr_overrides)
    print(f"生成した: {args.outdir} (N88_0.ROM〜N88_3.ROM 各{BANK_SIZE}バイト)")


if __name__ == "__main__":
    main()
