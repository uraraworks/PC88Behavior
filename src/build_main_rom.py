#!/usr/bin/env python3
"""
build_main_rom.py — M7段階2a: ディスク無しで自作バナー→Ok→カーソルまで
出す自作ROM一式（N88.ROM / DISK.ROM / FONT.ROM）を組み立てる。

## 出所

- **N88.ROM の起動処理(L1)部分**: `src/l1_ipl/make_ipl_rom.py` の
  `build_n88()` が発行する命令列（docs/spec/l1-ipl.md 付録Aと組み立て時に
  一致検査済み）を、`tools/asm/asm_emit.py` の `render_asm()` で
  Z80アセンブリのテキストへ書き出したもの。M7段階0の「既存生成器は
  正解役（オラクル）」の方針どおり、既存生成器（make_ipl_rom.py）自体は
  変更しない。
- **画面出力(main側L3)部分**: `src/l3_main/screen.asm`（docs/spec/l3-main.md
  だけを見て書いた新規コード）。
- 両者を `tools/asm/z80text.py`（自作Z80テキストアセンブラ）で1本に
  組み上げる。挿入点は「画面ハードウェア初期化が終わり、IM2/EIで定常状態へ
  入る直前」（`src/l1_ipl/make_ipl_rom.py` の `emit_font_sample()` と同じ
  挿入点）。ここへの CALL 追加は OUT を1つも増やさないので、
  L1 の適合条件（docs/spec/l1-ipl.md 第6節、OUT列だけの比較）には無関係。

- **DISK.ROM**: `src/l3_service/make_subrom.py`（既存・無変更）。
- **FONT.ROM**: `src/l2_font/make_font_rom.py`（既存・無変更。
  vendor/unscii・vendor/misaki の字形データを使う。私物の公式ROMではないので
  CLAUDE.md「パスの扱い」の環境変数縛りの対象外——tools/verify_l2.sh と
  同じ扱い）。

## 使い方

    python3 src/build_main_rom.py <出力先ディレクトリ>
    python3 src/build_main_rom.py <出力先> --extra-lines 25   # スクロール試験
    python3 src/build_main_rom.py <出力先> --inject-address-fault   # 故障注入（自己検査用）
"""

import argparse
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools" / "asm"))
sys.path.insert(0, str(REPO / "src" / "l1_ipl"))

import asm_emit  # noqa: E402
import make_ipl_rom  # noqa: E402
import z80text  # noqa: E402

N88_SIZE = make_ipl_rom.N88_SIZE
FILL = make_ipl_rom.FILL

SCREEN_ASM = REPO / "src" / "l3_main" / "screen.asm"
KEYBOARD_ASM = REPO / "src" / "l3_main" / "keyboard.asm"
KEY_TABLE_ASM = REPO / "src" / "l3_main" / "key_table_gen.asm"

# M7段階3b: BASIC核(直接モードPRINT)。src/l4_basic/*.asm・生成物。
L4_TOKENS_ASM = REPO / "src" / "l4_basic" / "tokens.asm"
L4_PRINT_DISPATCH_ASM = REPO / "src" / "l4_basic" / "print_dispatch.asm"
L4_ERRORS_ASM = REPO / "src" / "l4_basic" / "errors.asm"
L4_LEXER_ASM = REPO / "src" / "l4_basic" / "lexer.asm"
L4_INTERP_ASM = REPO / "src" / "l4_basic" / "interp.asm"

# 故障注入（tools/l4_basic_selftest.sh の陰性対照用）。
# 数値の前置空白(正/0のとき)を出す2行(PUSH HLとLD A,' ')を削り、
# 書式が崩れることを確かめる。
L4_SIGN_SPACE_FAULT_OLD = "_l4pn_pos:\n    PUSH HL\n    LD A,' '\n    CALL PRINT_CHAR\n    POP HL"
L4_SIGN_SPACE_FAULT_NEW = "_l4pn_pos:\n    NOP"

# 故障注入: ゾーン幅(interp.asmのZONE_WIDTH EQU 14)を変える。
L4_ZONE_WIDTH_FAULT_OLD = "ZONE_WIDTH EQU 14"
L4_ZONE_WIDTH_FAULT_NEW = "ZONE_WIDTH EQU 10"

# 故障注入: L4_TOKEN_TABLE(tokens.asm)のABSエントリの語長フィールドを
# 3→2に壊す(トークン値自体を変えるだけでは、LEX_SELFTESTが「期待値」も
# 同じ壊れた表から読むため自己参照的に一致してしまい検出できないと判明
# した。語長を壊すと、自己一致に使う語の切り出し長・トークン位置の計算
# 自体がずれるため、LEX_MATCH_WORDの独立な探索結果と食い違い、検出できる)。
L4_TOKEN_FAULT_OLD = '    db 3, "ABS", 0x88'
L4_TOKEN_FAULT_NEW = '    db 2, "ABS", 0x88'

# 故障注入: Missing operand(22、l4-basic.md 第6.1.1節)の判定を外す。
# _l4factor_bad_missingでのERROR_KIND=22の代入だけを削り、被演算子が
# 無いまま式が終わった場合も既定のSyntax error(2)のまま出るようにする。
L4_MISSING_OPERAND_FAULT_OLD = "_l4factor_bad_missing:\n    LD A,22\n    LD (ERROR_KIND),A\n_l4factor_bad_ret:"
L4_MISSING_OPERAND_FAULT_NEW = "_l4factor_bad_missing:\n_l4factor_bad_ret:"

# 挿入点の目印。render_asm() の出力に必ず1回だけ現れる
# （make_ipl_rom.build_n88() の「IM2ベクタページをIへ積む」直前）。
INSERT_MARK = "    LD A,VEC_TABLE>>8"

# 故障注入（tools/l3_main_selftest.sh の陰性対照用）。
# 番地の式（addr = TEXT_BASE + row*STRIDE + col、l3-main.md 第2節）を
# 1バイトずらす。screen.asm 側の該当行はこの文字列で一意に現れる。
FAULT_OLD = "    LD HL,TEXT_BASE\n    LD (VAR_ROWBASE),HL"
FAULT_NEW = "    LD HL,TEXT_BASE+1\n    LD (VAR_ROWBASE),HL"

# M7段階2b: VSYNCハンドラ(make_ipl_rom.sub_vsync_handler)が固定で出す
# カーソル位置(X=22,Y=1)の2個のOUTを、keyboard.asmのL3_VSYNC_HOOK呼び出しへ
# 置き換える。make_ipl_rom.py自体は無変更（render_asm()の出力テキストへの
# 置換であり、INSERT_MARK/FAULT_OLDと同じ手法）。置き換え後もVSYNC
# ハンドラ内のOUT(0x50)は2回のまま(l3-main.mdの番地の式に無関係、
# L1側のCRTCコマンド書式(l1-ipl.md第5d節)のパラメータ2バイトという構造は
# 変わらない)。
#
# 置換前後でバイト数を8バイトのまま変えない（CALL nn=3バイト+NOP×5）。
# render_asm()はmake_ipl_rom.pyがPythonの2パスアセンブラで内部的に確定した
# バイト位置を書き出したものであり、IM2ベクタテーブル直前の詰め物
# （align_page()）は「次のラベルが256バイト境界に来るまで」計算された
# **固定件数**の db として書き出される（z80textの再アセンブル時に
# 動的再計算されるわけではない）。ここでバイト数を変えると詰め物の数が
# 合わなくなり、VEC_TABLEが256バイト境界からずれ、IM2の割り込みベクタ
# 引き（(I<<8)|レベル）が完全に外れて暴走する（実機で確認済み。
# 5バイト短いCALL単体に置き換えたところ、VSYNC割り込みが初めて発生する
# 箇所でCPUが無関係な番地へ飛び、L1適合検査①が344件目で全く別内容に
# 化けて不合格になった）。バイト数を揃えることでこれを避けている。
CURSOR_OLD = "    LD A,0x16\n    OUT (0x50),A\n    LD A,0x01\n    OUT (0x50),A"
CURSOR_NEW = "    CALL L3_VSYNC_HOOK\n    NOP\n    NOP\n    NOP\n    NOP\n    NOP"

# カーソル追従の故障注入（tools/l3_main_selftest.sh --cursor-fault 相当）。
# SET_CURSOR(keyboard.asm)のCOL/ROWの出力順を1バイトずらす。
CURSOR_FAULT_OLD = "    LD A,(VAR_COL)\n    OUT (50h),A\n    LD A,(VAR_ROW)\n    OUT (50h),A"
CURSOR_FAULT_NEW = "    LD A,(VAR_COL)\n    OUT (50h),A\n    LD A,(VAR_ROW)\n    INC A\n    OUT (50h),A"

# M7段階3b追記2: 故障注入（SPACE(09H:6)のエコー前進を無効化し、段階3b
# までの「SPACEは書かない」変種へ戻す。l3-main.md 第9節末尾の追記の
# 検出力の陰性対照）。SPACE判定のビット比較先を存在しない値(7、
# SPACE_BITは6)に変え、_kr_not_space側へ必ず抜けさせる(分岐そのものを
# 削ると別の構造に化けるため、判定条件だけを外す)。抜けた後は通常の
# コード表参照に進むが、port 0x09 は BASE_CODE_TAB 等どの表にも
# エントリが無い(0x00=無視)ため、結果的に元の「無視する」挙動に戻る。
KEYBOARD_SPACE_FAULT_OLD = (
    "    LD A,C\n"
    "    CP SPACE_PORT\n"
    "    JR NZ,_kr_not_space\n"
    "    LD A,B\n"
    "    CP SPACE_BIT"
)
KEYBOARD_SPACE_FAULT_NEW = (
    "    LD A,C\n"
    "    CP SPACE_PORT\n"
    "    JR NZ,_kr_not_space\n"
    "    LD A,B\n"
    "    CP 7"
)

# 故障注入（tools/l3_main_selftest.sh の陰性対照用）。BASE_CODE_TAB の
# Q(04H:1、l3-main.md第9節)の1エントリだけを変える
# （tools/gen_l3_key_table.py --check で検査済みの表を、生成後に
# 1バイトだけ壊す）。
KEY_TABLE_FAULT_OLD = "    DB 0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77"
KEY_TABLE_FAULT_NEW = "    DB 0x70, 0x51, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77"

# M7段階2c: 故障注入（SHIFT_CODE_TAB のQ(04H:1)エントリを変える）。
# CAPS_CODE_TABとSHIFT_CODE_TABは04:1の行(0x50,0x51,...)が同一の内容
# なので、直前のGRPH由来の行(0x7E始まり、SHIFT_CODE_TABにしか無い)を
# 含めて3行まとめて置換対象にし、一意に絞る。
KEY_TABLE_SHIFT_FAULT_OLD = (
    "    DB 0x7E, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47\n"
    "    DB 0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F\n"
    "    DB 0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57"
)
KEY_TABLE_SHIFT_FAULT_NEW = (
    "    DB 0x7E, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47\n"
    "    DB 0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F\n"
    "    DB 0x50, 0x99, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57"
)

# M7段階2c: 故障注入（既定の属性域DEFAULT_ATTRの先頭バイトを変える。
# l3-main.md 第14節nonzero_patternの検出力の陰性対照）。
DEFAULT_ATTR_FAULT_OLD = (
    "DEFAULT_ATTR:\n"
    "    DB 080h,000h, 080h,000h, 080h,000h, 080h,000h, 080h,000h"
)
DEFAULT_ATTR_FAULT_NEW = (
    "DEFAULT_ATTR:\n"
    "    DB 081h,000h, 080h,000h, 080h,000h, 080h,000h, 080h,000h"
)

# M7段階2c: 故障注入（スクロール範囲を第15節fkey_row_reservedの
# USABLE_ROWS基準からやめ、予約行の1行先まで巻き込んでコピーする）。
# STRIDE*(ROWS-1)ではLDIRの書き込み範囲(2280バイト)がたまたま正常時の
# 連続書き込み長と同じ大きさになり検出力が無かった(クリア分の120バイトが
# LDIR範囲に内包されて別ランに分かれるだけで、2280バイトのランは残る)ため、
# ROWS(=20)そのものを使い2400バイトへずらす(初期化クリアと同じ大きさに
# 重なるほうを選び、"2280バイトのランが無くなる"という明確な違いにする)。
SCROLL_RANGE_FAULT_OLD = "    LD BC,STRIDE*(USABLE_ROWS-1)\n    LDIR"
SCROLL_RANGE_FAULT_NEW = "    LD BC,STRIDE*ROWS\n    LDIR"


def build_combined_asm(work: pathlib.Path, extra_lines: int, inject_fault: bool,
                        inject_cursor_fault: bool = False,
                        inject_key_table_fault: bool = False,
                        inject_shift_fault: bool = False,
                        inject_default_attr_fault: bool = False,
                        inject_scroll_range_fault: bool = False,
                        inject_l4_sign_space_fault: bool = False,
                        inject_l4_zone_width_fault: bool = False,
                        inject_l4_token_fault: bool = False,
                        inject_l3_space_fault: bool = False,
                        inject_l4_missing_operand_fault: bool = False,
                        enable_l4_selftest: bool = False) -> str:
    """IPL(L1)のアセンブリ + 画面出力(L3)のアセンブリを1本に組む。"""
    rom, used, n_out = make_ipl_rom.build_n88(stop_after=None, font_sample=False)
    del rom, used, n_out  # ここでは使わない。組み立て時検査が通ったことだけが重要
    asm_obj = make_ipl_rom._LAST_ASM
    ipl_text = asm_emit.render_asm(
        asm_obj, "M7段階2: make_ipl_rom.build_n88() の発行命令(L1) + l3_main/(画面出力・キー入力)")

    if INSERT_MARK not in ipl_text:
        raise SystemExit(f"挿入点が見つからない: {INSERT_MARK!r}")
    if ipl_text.count(INSERT_MARK) != 1:
        raise SystemExit(f"挿入点が一意でない: {INSERT_MARK!r}")
    # M7段階3b: LEX_SELFTEST(表の全語の照合自己検査)は、ここで無条件に
    # 呼ぶとブート時のCPUサイクル数が増え、l3_main_selftest.shのL1適合
    # 検査4a/4b（frames=60の枠内で350件のI/O列を数える、サイクル数に敏感な
    # 検査）が壊れる（実測: 350件中343件しか出ない）。既定では呼ばず、
    # tools/l4_basic_selftest.sh がこのフラグを立てたビルドでだけ呼ぶ。
    l4_selftest_call = "    CALL LEX_SELFTEST\n" if enable_l4_selftest else ""
    ipl_text = ipl_text.replace(
        INSERT_MARK, "    CALL SCREEN_MAIN\n" + l4_selftest_call + INSERT_MARK)

    if CURSOR_OLD not in ipl_text:
        raise SystemExit(f"カーソル追従の置換点が見つからない: {CURSOR_OLD!r}")
    if ipl_text.count(CURSOR_OLD) != 1:
        raise SystemExit(f"カーソル追従の置換点が一意でない: {CURSOR_OLD!r}")
    ipl_text = ipl_text.replace(CURSOR_OLD, CURSOR_NEW)

    screen_text = SCREEN_ASM.read_text(encoding="utf-8")
    if inject_fault:
        if screen_text.count(FAULT_OLD) != 1:
            raise SystemExit("故障注入の対象行が一意に見つからない（screen.asm が変わった？）")
        screen_text = screen_text.replace(FAULT_OLD, FAULT_NEW)
    if inject_default_attr_fault:
        if screen_text.count(DEFAULT_ATTR_FAULT_OLD) != 1:
            raise SystemExit("既定属性の故障注入の対象行が一意に見つからない（screen.asm が変わった？）")
        screen_text = screen_text.replace(DEFAULT_ATTR_FAULT_OLD, DEFAULT_ATTR_FAULT_NEW)
    if inject_scroll_range_fault:
        if screen_text.count(SCROLL_RANGE_FAULT_OLD) != 1:
            raise SystemExit("スクロール範囲の故障注入の対象行が一意に見つからない（screen.asm が変わった？）")
        screen_text = screen_text.replace(SCROLL_RANGE_FAULT_OLD, SCROLL_RANGE_FAULT_NEW)

    keyboard_text = KEYBOARD_ASM.read_text(encoding="utf-8")
    if inject_cursor_fault:
        if keyboard_text.count(CURSOR_FAULT_OLD) != 1:
            raise SystemExit("カーソル故障注入の対象行が一意に見つからない（keyboard.asm が変わった？）")
        keyboard_text = keyboard_text.replace(CURSOR_FAULT_OLD, CURSOR_FAULT_NEW)
    if inject_l3_space_fault:
        if keyboard_text.count(KEYBOARD_SPACE_FAULT_OLD) != 1:
            raise SystemExit("SPACE故障注入の対象行が一意に見つからない（keyboard.asm が変わった？）")
        keyboard_text = keyboard_text.replace(KEYBOARD_SPACE_FAULT_OLD, KEYBOARD_SPACE_FAULT_NEW)

    screen_path = work / "screen_gen.asm"
    screen_path.write_text(screen_text, encoding="utf-8")
    keyboard_path = work / "keyboard_gen.asm"
    keyboard_path.write_text(keyboard_text, encoding="utf-8")
    key_table_text = KEY_TABLE_ASM.read_text(encoding="utf-8")
    if inject_key_table_fault:
        if key_table_text.count(KEY_TABLE_FAULT_OLD) != 1:
            raise SystemExit("表の故障注入の対象行が一意に見つからない（key_table_gen.asm が変わった？）")
        key_table_text = key_table_text.replace(KEY_TABLE_FAULT_OLD, KEY_TABLE_FAULT_NEW)
    if inject_shift_fault:
        if key_table_text.count(KEY_TABLE_SHIFT_FAULT_OLD) != 1:
            raise SystemExit("SHIFT表の故障注入の対象行が一意に見つからない（key_table_gen.asm が変わった？）")
        key_table_text = key_table_text.replace(KEY_TABLE_SHIFT_FAULT_OLD, KEY_TABLE_SHIFT_FAULT_NEW)
    key_table_path = work / "key_table_gen.asm"
    key_table_path.write_text(key_table_text, encoding="utf-8")

    # M7段階3b: BASIC核(直接モードPRINT)。tokens.asm/print_dispatch.asm/
    # errors.asmは生成物(手で編集しない)、lexer.asm/interp.asmは新規実装。
    tokens_text = L4_TOKENS_ASM.read_text(encoding="utf-8")
    if inject_l4_token_fault:
        if tokens_text.count(L4_TOKEN_FAULT_OLD) != 1:
            raise SystemExit("トークン表の故障注入の対象行が一意に見つからない（tokens.asmが変わった？）")
        tokens_text = tokens_text.replace(L4_TOKEN_FAULT_OLD, L4_TOKEN_FAULT_NEW)
    tokens_path = work / "l4_tokens_gen.asm"
    tokens_path.write_text(tokens_text, encoding="utf-8")

    print_dispatch_path = work / "l4_print_dispatch_gen.asm"
    print_dispatch_path.write_text(L4_PRINT_DISPATCH_ASM.read_text(encoding="utf-8"), encoding="utf-8")

    errors_path = work / "l4_errors_gen.asm"
    errors_path.write_text(L4_ERRORS_ASM.read_text(encoding="utf-8"), encoding="utf-8")

    lexer_path = work / "l4_lexer_gen.asm"
    lexer_path.write_text(L4_LEXER_ASM.read_text(encoding="utf-8"), encoding="utf-8")

    interp_text = L4_INTERP_ASM.read_text(encoding="utf-8")
    if inject_l4_sign_space_fault:
        if interp_text.count(L4_SIGN_SPACE_FAULT_OLD) != 1:
            raise SystemExit("符号前置空白の故障注入の対象行が一意に見つからない（interp.asmが変わった？）")
        interp_text = interp_text.replace(L4_SIGN_SPACE_FAULT_OLD, L4_SIGN_SPACE_FAULT_NEW)
    if inject_l4_zone_width_fault:
        if interp_text.count(L4_ZONE_WIDTH_FAULT_OLD) != 1:
            raise SystemExit("ゾーン幅の故障注入の対象行が一意に見つからない（interp.asmが変わった？）")
        interp_text = interp_text.replace(L4_ZONE_WIDTH_FAULT_OLD, L4_ZONE_WIDTH_FAULT_NEW)
    if inject_l4_missing_operand_fault:
        if interp_text.count(L4_MISSING_OPERAND_FAULT_OLD) != 1:
            raise SystemExit("Missing operand判定の対象行が一意に見つからない（interp.asmが変わった？）")
        interp_text = interp_text.replace(L4_MISSING_OPERAND_FAULT_OLD, L4_MISSING_OPERAND_FAULT_NEW)
    interp_path = work / "l4_interp_gen.asm"
    interp_path.write_text(interp_text, encoding="utf-8")

    combined = (
        f"; EXTRA_LINES: --extra-lines で指定された値（スクロール試験用の埋め草行数）\n"
        f"EXTRA_LINES EQU {extra_lines}\n"
        + ipl_text
        + f'\nINCLUDE "{screen_path}"\n'
        + f'\nINCLUDE "{keyboard_path}"\n'
        + f'\nINCLUDE "{key_table_path}"\n'
        + f'\nINCLUDE "{tokens_path}"\n'
        + f'\nINCLUDE "{print_dispatch_path}"\n'
        + f'\nINCLUDE "{errors_path}"\n'
        + f'\nINCLUDE "{lexer_path}"\n'
        + f'\nINCLUDE "{interp_path}"\n'
    )
    return combined


def assemble(text: str, work: pathlib.Path) -> bytes:
    src_path = work / "n88_main_gen.asm"
    src_path.write_text(text, encoding="utf-8")
    asm = z80text.Assembler()
    try:
        code = asm.assemble(src_path)
    except z80text.AsmError as e:
        raise SystemExit(f"z80text アセンブルエラー: {e}")
    if len(code) > N88_SIZE:
        raise SystemExit(f"ROM に収まらない: {len(code)} > {N88_SIZE}")
    rom = bytearray([FILL] * N88_SIZE)
    rom[:len(code)] = code
    return bytes(rom)


def build_disk_rom(outdir: pathlib.Path):
    subprocess.run(
        [sys.executable, str(REPO / "src" / "l3_service" / "make_subrom.py"), str(outdir)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build_font_rom(outdir: pathlib.Path, unscii_hex: pathlib.Path, misaki_bdf: pathlib.Path):
    subprocess.run(
        [sys.executable, str(REPO / "src" / "l2_font" / "make_font_rom.py"), str(outdir),
         "--unscii-hex", str(unscii_hex), "--misaki-bdf", str(misaki_bdf)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--extra-lines", type=int, default=0,
                     help="バナーとOkの間に挟む埋め草行の数（スクロール試験用）")
    ap.add_argument("--inject-address-fault", action="store_true",
                     help="故障注入: 番地の式を1バイトずらす（自己検査の陰性対照専用）")
    ap.add_argument("--inject-cursor-fault", action="store_true",
                     help="故障注入: カーソル追従(SET_CURSOR)のROW出力を1ずらす（自己検査の陰性対照専用）")
    ap.add_argument("--inject-key-table-fault", action="store_true",
                     help="故障注入: キーコード表(Q)の1エントリを変える（自己検査の陰性対照専用）")
    ap.add_argument("--inject-shift-fault", action="store_true",
                     help="故障注入: SHIFT表(Q)の1エントリを変える（自己検査の陰性対照専用）")
    ap.add_argument("--inject-default-attr-fault", action="store_true",
                     help="故障注入: 既定の属性域(DEFAULT_ATTR)の1バイトを変える（自己検査の陰性対照専用）")
    ap.add_argument("--inject-scroll-range-fault", action="store_true",
                     help="故障注入: スクロール範囲をファンクションキー行予約前(ROWS基準)へ戻す（自己検査の陰性対照専用）")
    ap.add_argument("--inject-l4-sign-space-fault", action="store_true",
                     help="故障注入: PRINTの数値前置空白(正/0)を消す（自己検査の陰性対照専用）")
    ap.add_argument("--inject-l4-zone-width-fault", action="store_true",
                     help="故障注入: PRINTのゾーン幅を14から10へ変える（自己検査の陰性対照専用）")
    ap.add_argument("--inject-l4-token-fault", action="store_true",
                     help="故障注入: L4_TOKEN_TABLE(ABS)のトークン値を1つずらす（自己検査の陰性対照専用）")
    ap.add_argument("--inject-l3-space-fault", action="store_true",
                     help="故障注入: SPACE(09H:6)のエコー前進を無効化し、段階3bまでの"
                          "「書かない」変種へ戻す（自己検査の陰性対照専用）")
    ap.add_argument("--inject-l4-missing-operand-fault", action="store_true",
                     help="故障注入: Missing operand(22)の判定を外し、常にSyntax error(2)の"
                          "ままにする（自己検査の陰性対照専用）")
    ap.add_argument("--enable-l4-selftest", action="store_true",
                     help="ブート時にLEX_SELFTESTを呼ぶ（l3_main_selftest.shのL1タイミング検査を"
                          "壊すため既定offにしてある。tools/l4_basic_selftest.sh専用）")
    ap.add_argument("--work-dir", type=pathlib.Path, default=None,
                     help="中間.asmファイルの置き場（既定は一時ディレクトリ、後始末しない）")
    ap.add_argument("--unscii-hex", type=pathlib.Path,
                     default=REPO.parent / "vendor" / "unscii" / "unscii-8.hex")
    ap.add_argument("--misaki-bdf", type=pathlib.Path,
                     default=REPO.parent / "vendor" / "misaki" / "misaki_gothic.bdf")
    ap.add_argument("--keep-work", action="store_true",
                     help="--work-dir を指定しない場合でも中間ファイルを残す")
    args = ap.parse_args()

    if args.extra_lines < 0 or args.extra_lines > 255:
        raise SystemExit("--extra-lines は 0-255")

    import tempfile
    work = args.work_dir
    cleanup = False
    if work is None:
        work = pathlib.Path(tempfile.mkdtemp(prefix="pc88_l3main_"))
        cleanup = not args.keep_work
    work.mkdir(parents=True, exist_ok=True)

    try:
        combined = build_combined_asm(work, args.extra_lines, args.inject_address_fault,
                                       args.inject_cursor_fault, args.inject_key_table_fault,
                                       args.inject_shift_fault, args.inject_default_attr_fault,
                                       args.inject_scroll_range_fault,
                                       args.inject_l4_sign_space_fault,
                                       args.inject_l4_zone_width_fault,
                                       args.inject_l4_token_fault,
                                       inject_l3_space_fault=args.inject_l3_space_fault,
                                       inject_l4_missing_operand_fault=args.inject_l4_missing_operand_fault,
                                       enable_l4_selftest=args.enable_l4_selftest)
        rom = assemble(combined, work)

        args.outdir.mkdir(parents=True, exist_ok=True)
        (args.outdir / "N88.ROM").write_bytes(rom)
        build_disk_rom(args.outdir)
        build_font_rom(args.outdir, args.unscii_hex, args.misaki_bdf)

        used = len(combined.splitlines())
        print(f"生成した: {args.outdir} (N88.ROM {N88_SIZE} bytes / DISK.ROM / FONT.ROM)")
        print(f"  組み合わせ.asm行数={used} extra_lines={args.extra_lines} "
              f"inject_address_fault={args.inject_address_fault} "
              f"inject_cursor_fault={args.inject_cursor_fault}")
    finally:
        if cleanup:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
