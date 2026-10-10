#!/usr/bin/env python3
"""
build_main_rom.py — M7段階2a: ディスク無しで自作バナー→Ok→カーソルまで
出す自作ROM一式（N88.ROM / DISK.ROM / FONT.ROM）を組み立てる。

## 出所

- **N88.ROM の起動処理(L1)部分**: `src/l1_ipl/make_ipl_rom.py` の
  `build_n88()` が発行する命令列（docs/spec/l1-ipl.md 付録Aと組み立て時に
  一致検査済み）を、`tools/asm/asm_emit.py` の `render_asm()` で
  Z80アセンブリのテキストへ書き出したもの。段Aではmake_ipl_rom.pyの
  RAM定数をsrc/memmap.py参照に変更したが、生成する命令列は同じである。
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
import memmap  # noqa: E402

N88_SIZE = make_ipl_rom.N88_SIZE
FILL = make_ipl_rom.FILL

SCREEN_ASM = REPO / "src" / "l3_main" / "screen.asm"
KEYBOARD_ASM = REPO / "src" / "l3_main" / "keyboard.asm"
VSYNC_REGCHECK_ASM = REPO / "src" / "l3_main" / "vsync_regcheck.asm"
KEY_TABLE_ASM = REPO / "src" / "l3_main" / "key_table_gen.asm"
MAIN_SUB_READ_ASM = REPO / "src" / "l3_main" / "main_sub_read.asm"
DISK_READ_RETRY_ASM = REPO / "src" / "l3_main" / "disk_read_retry.asm"
MAIN_SUB_READ_CHR_ASM = REPO / "src" / "l3_main" / "main_sub_read_chr.asm"

# M7段階3b: BASIC核(直接モードPRINT)。src/l4_basic/*.asm・生成物。
L4_TOKENS_ASM = REPO / "src" / "l4_basic" / "tokens.asm"
L4_PRINT_DISPATCH_ASM = REPO / "src" / "l4_basic" / "print_dispatch.asm"
L4_ERRORS_ASM = REPO / "src" / "l4_basic" / "errors.asm"
L4_LEXER_ASM = REPO / "src" / "l4_basic" / "lexer.asm"
L4_MBF_ASM = REPO / "src" / "l4_basic" / "mbf_single.asm"
# M7段階4b-3: 倍精度(mbf_double.asm)を連結する。ヘッダコメントのとおり
# mbf_single.asmの直後に連結して1アセンブル単位にする前提(DA_*/DB_*等
# mbf_single.asm定義済みシンボルを参照する)。
L4_MBF_DOUBLE_ASM = REPO / "src" / "l4_basic" / "mbf_double.asm"
L4_INTERP_ASM = REPO / "src" / "l4_basic" / "interp.asm"
# M7段階5a: プログラムモード(行の入力・保存・LIST・NEW)。program.asm
L4_PROGRAM_ASM = REPO / "src" / "l4_basic" / "program.asm"
# M7段階5b: RUNとプログラムの実行(GOTO/FOR/GOSUB/STOP/変数)。run.asm
L4_RUN_ASM = REPO / "src" / "l4_basic" / "run.asm"
L4_FILES_ASM = REPO / "src" / "l4_basic" / "files.asm"
L4_LOAD_ASM = REPO / "src" / "l4_basic" / "load.asm"
L4_SAVE_ASM = REPO / "src" / "l4_basic" / "save.asm"
L4_LOAD_GAP_ASM = REPO / "src" / "l4_basic" / "load_gap.asm"

# 拡張ROMバンク(4th ROM)の土台。docs/spec/ext-rom-bank.md 参照。
EXT_BANK_DIR = REPO / "src" / "ext_bank"
EXT_BANK_RELAY_ASM = EXT_BANK_DIR / "relay.asm"
EXT_BANK_WINCALL_PROBE_ASM = EXT_BANK_DIR / "wincall_probe.asm"

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
CURSOR_NEW = "    CALL L3_VSYNC_HOOK\n    NOP\n    NOP\n    NOP"
# WIDTH（l4-program.md 5.6.5）: 20行は0x19・25行は0x39を、垂直同期のたびにポート0x31へ出す。
# ハンドラが出す2個の「LD A,0x19／OUT (0x31),A」（各4バイト）を、RAMの現在値を読む形
# （各5バイト）へ置き換える。増える2バイトぶん、上のCURSOR_NEWのNOPを2個減らして
# 全体のバイト数を保つ（VEC_TABLEの256バイト境界を動かさない。上の長い注記と同じ理由）。
P31_OLD = "    LD A,0x19\n    OUT (0x31),A\n"
P31_NEW = "    LD A,(MM_SCR_P31)\n    OUT (0x31),A\n"

# 故障注入（陰性対照専用、tools/vsync_regcheck_selftest.sh）。VSYNC_HANDLER
# 冒頭・末尾のレジスタ退避(PUSH/POP、src/l1_ipl/make_ipl_rom.py
# sub_vsync_handlerの「レジスタ退避」節参照)を無効化し、修正前の
# 「一切PUSH/POPしない」状態を再現する。バイト数を1:1のNOPへ置き換える
# ことで揃える(PUSH AF/BC/DE/HLは1バイト×4、PUSH IX/IYは2バイト×2で
# 計8バイト、POP側も同型に8バイト。CURSOR_OLD/NEWと同じ理由——
# VEC_TABLEの256バイト境界整列はPython側の2パスアセンブラが確定した
# レイアウトなので、置換後もバイト数を変えてはいけない)。
VSYNC_PUSH_OLD = "    PUSH AF\n    PUSH BC\n    PUSH DE\n    PUSH HL\n    PUSH IX\n    PUSH IY"
VSYNC_PUSH_NEW = "    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n    NOP"
VSYNC_POP_OLD = "    POP IY\n    POP IX\n    POP HL\n    POP DE\n    POP BC\n    POP AF"
VSYNC_POP_NEW = "    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n    NOP"

# カーソル追従の故障注入（tools/l3_main_selftest.sh --cursor-fault 相当）。
# SET_CURSOR(keyboard.asm)のCOL/ROWの出力順を1バイトずらす。
# （40桁のX＝2×桁の分岐を SET_CURSOR に足したため、COL出力とROW出力が隣り合わなくなった。
#  ROW出力の側（直後が RET）を1ずらす形に対象を変えた。）
CURSOR_FAULT_OLD = "    LD A,(VAR_ROW)\n    OUT (50h),A\n    RET"
CURSOR_FAULT_NEW = "    LD A,(VAR_ROW)\n    INC A\n    OUT (50h),A\n    RET"

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
# （WIDTH実装でDEFAULT_ATTRの40バイト表をCLEAR_ROWの繰り返しに替えたため、
#  位置バイト0x80を0x81に変える形で既定の並びを壊す。）
DEFAULT_ATTR_FAULT_OLD = (
    "_cr_attr:\n"
    "    LD (HL),080h"
)
DEFAULT_ATTR_FAULT_NEW = (
    "_cr_attr:\n"
    "    LD (HL),081h"
)

# M7段階2c: 故障注入（スクロール範囲を第15節fkey_row_reservedの
# USABLE_ROWS基準からやめ、予約行の1行先まで巻き込んでコピーする）。
# STRIDE*(ROWS-1)ではLDIRの書き込み範囲(2280バイト)がたまたま正常時の
# 連続書き込み長と同じ大きさになり検出力が無かった(クリア分の120バイトが
# LDIR範囲に内包されて別ランに分かれるだけで、2280バイトのランは残る)ため、
# ROWS(=20)そのものを使い2400バイトへずらす(初期化クリアと同じ大きさに
# 重なるほうを選び、"2280バイトのランが無くなる"という明確な違いにする)。
# （CONSOLE実装で書き写しをバンク0 wb_scroll へ移したため、mainのSCROLLで窓の下端の行の
#  あとにもう1行〔下の行＝予約行〕を余計に消す形にする。起動時は書き写し2160バイト＋消去120バイトの
#  連続2280バイトに、さらに120バイトが続いて2400バイトの連続になり、2280バイトの連続が消える。）
SCROLL_RANGE_FAULT_OLD = "    CALL EXT_BANK_CALL\n    JP CLEAR_ROW"
SCROLL_RANGE_FAULT_NEW = "    CALL EXT_BANK_CALL\n    CALL CLEAR_ROW\n    JP CLEAR_ROW"

# 故障注入: 第16節HOME/CLR(08H:0)のSHIFT分岐を反転する（自己検査の陰性
# 対照専用。tools/l3_screen_editor_selftest.sh）。無修飾=clear/SHIFT=home
# という対応が壊れたことを検出できるかを確かめる。
EDITKEY_HOME_CLR_FAULT_OLD = (
    "_kr_home_or_clr:\n"
    "    LD A,(KEY_NEW+MOD_PORT)\n"
    "    BIT SHIFT_BIT,A\n"
    "    JR NZ,_kr_do_clr"
)
EDITKEY_HOME_CLR_FAULT_NEW = (
    "_kr_home_or_clr:\n"
    "    LD A,(KEY_NEW+MOD_PORT)\n"
    "    BIT SHIFT_BIT,A\n"
    "    JR Z,_kr_do_clr"
)

# 故障注入: 第4.2版第8節「キーリピート」の遅延を255フレームへ引き伸ばし、
# テストで使う程度の長押し(数百フレーム未満)では実質発火しないようにする
# （自己検査の陰性対照専用。tools/l3_screen_editor_selftest.sh）。
KEY_REPEAT_DELAY_FAULT_OLD = "KEY_REPEAT_DELAY    EQU 30"
KEY_REPEAT_DELAY_FAULT_NEW = "KEY_REPEAT_DELAY    EQU 255"

# 拡張ROMバンク: 定常状態(STEADY_WAIT、IM2/I/EI設定済み)に入った直後の
# 挿入点。--enable-ext-bank-selftestのときだけ、ここへ
# EXT_BANK_LOOP_TEST(割り込みを有効にしたまま多数回EXT_BANK_CALLを
# 呼ぶ自己検査)の呼び出しを差し込む。STEADY_WAITはHALT/JPで毎フレーム
# 回るループなので、呼び出し先は自前で「実行済みフラグ」を見て
# 2回目以降は素通りする(src/ext_bank/relay.asm EXT_BANK_LOOP_TEST)。
STEADY_WAIT_MARK = "STEADY_WAIT:\n    HALT"

# 拡張ROMバンク: 中継ルーチン(EXT_BANK_CALL)・割り込み処理
# (VSYNC_HANDLER・L3_VSYNC_HOOK)が窓(0x6000-0x7FFF)の外に無ければ
# ならない(docs/spec/ext-rom-bank.md 第2節 制約1・2)。ROM_VERSION予約
# 番地の検査(assemble()内)と同じ「ビルド時に機械的に落とす」流儀で
# 検査する。
EXT_BANK_WINDOW_START = 0x6000
EXT_BANK_INTERRUPT_SAFE_LABELS = (
    "VSYNC_HANDLER", "L3_VSYNC_HOOK", "EXT_BANK_CALL", "EXT_BANK_JUMP_HL",
    "EXT_BANK_MAIN_CALL", "_ext_bank_main_jump", "EXT_BANK_CALL_CAPTURE")

# 拡張ROMバンク: バンク側ルーチンから1回CALLして戻ってよい常駐部ルーチン
# 一覧(docs/spec/ext-rom-bank.md 第2節 制約3(a)〜(c)、
# docs/notes/ext2-relay-to-resident-results.md で測定済み)。まずは単精度の
# 四則演算・比較・FIN/FOUT等、mbf_single.asm の公開ラベル(内部ヘルパは
# 含めない)。いずれも既存の配置(案C、既存モジュールの配置は動かさない)で
# 既に0x6000未満にある(実測: 最も番地の大きいMBF_FOUTでも0x2503付近、
# 窓の先頭0x6000まで大きな余白がある)。制約3(b)(c)(=呼び先が0x71/0x32・
# EXT_BANK_CALLへ触れない、1回CALLされて戻るだけ)は個々の呼び出し側の
# 設計規律であり、ここでは(a)(番地が窓の外にあること)だけを機械的に検査
# する。
EXT_BANK_CALLABLE_RESIDENT_LABELS = (
    "MBF_ADD", "MBF_SUB", "MBF_NEG", "MBF_CMP", "MBF_MUL", "MBF_DIV",
    "MBF_INT_TO_SINGLE", "MBF_UDWORD_TO_SINGLE", "MBF_FIN", "MBF_FOUT",
    "FIN_ACC_TO_SINGLE_AWAY",
    # 2026-09-20追記(SQR、第4.16b節): mbf_double.asmの倍精度ルーチン。
    # bank0.asm EXT_BANK0_SQR_ENTRYがニュートン法(倍精度)で使う。
    "MBF_STOD", "MBF_DADD", "MBF_DDIV", "MBF_DTOS",
    # 2026-09-20追記(SIN/COS/TAN、第4.16a節): TRUNC_TO_SINGLE(0方向への
    # 切り捨て)。bank0.asm SC_RR_REDUCE/SC_SIN_COREが範囲縮約のfloorに使う
    # (呼び出し箇所はいずれも被演算子が非負であることが構造上保証されて
    # いるため、0方向切り捨て=floorとして使える)。
    "TRUNC_TO_SINGLE",
    # 2026-09-20追記(ATN/EXP/LOG、第4.16b節): MBF_CMP(既にリストにある)に
    # 加え、LOGのe_raw→単精度化にMBF_INT_TO_SINGLE(既にリストにある)を
    # 新規に使う。EXPのny→整数化はMBF_ROUND_TO_INT16(run.asm)を呼ぶと
    # その番地がちょうど窓(0x6000以上)へ入ってしまう(ATN/EXP/LOG追加で
    # N88.ROMの総バイト数が伸びたため)ことが分かったため、bank0.asm
    # 側でAEL_EXP_NY_TO_INT16として自己完結に実装し直した(常駐呼び出し
    # にしない、二重実装ではあるが窓外の空きが尽きているための判断)。
)

# バンク1のFILES/LOAD/PRINT USING/ON/WHILE/DIMが窓外中継で呼ぶmain側ルーチン。
# バンクROMを別に組み立てるため、実ビルドのラベル番地を渡す。
EXT_BANK1_MAIN_ADDR_LABELS = {
    "AP_SKIP_ADDR": "SKIP_SPACES",
    "AP_PEEK_ADDR": "PEEK_CHAR",
    "AP_ADV_ADDR": "ADV_PTR",
    "AP_EXPR_ADDR": "LOGIC_OR_EXPR",
    "AP_INT_ADDR": "VAL_TO_INT16_CUR",

    "CI_EXPR_ADDR": "LOGIC_OR_EXPR",
    "CI_ISNEG_ADDR": "VAL_IS_NEGATIVE",
    "CI_TOINT_ADDR": "CUR_TO_INT16",
    "CI_LOADA_ADDR": "VAL_LOAD_CUR_TO_OPA",
    "CI_MUL_ADDR": "MBF_MUL",
    "CI_DIV_ADDR": "MBF_DIV",
    "CI_I2S_ADDR": "MBF_INT_TO_SINGLE",
    "CI_ROUND_ADDR": "MBF_ROUND_TO_INT16",
    "CI_EXTCALL_ADDR": "EXT_BANK_CALL",
    "GP_ISSTR_ADDR": "FN_IS_STRING",
    "GP_STREXPR_ADDR": "STRING_EXPR",
    "GP_EXTCALL_ADDR": "EXT_BANK_CALL",
    "B1_DIM_BODY_ADDR": "ARRAY_DIM",
    "B1_DIM_SKIP_SPACES_ADDR": "SKIP_SPACES",
    "B1_DIM_LEX_IDENT_CONSUME_ADDR": "LEX_IDENT_CONSUME",
    "B1_DIM_PEEK_CHAR_ADDR": "PEEK_CHAR",
    "B1_DIM_ADV_PTR_ADDR": "ADV_PTR",
    "B1_DIM_LOGIC_OR_EXPR_ADDR": "LOGIC_OR_EXPR",
    "B1_DIM_VAL_TO_INT16_CUR_ADDR": "VAL_TO_INT16_CUR",
    "B1_DIM_ARRAY_FIND_ADDR": "ARRAY_FIND",
    "B1_DIM_ARRAY_ALLOC_ADDR": "ARRAY_ALLOC",
    "OW_MAIN_CALL_ADDR": "EXT_BANK_MAIN_CALL",
    "OW_SKIP_ADDR": "SKIP_SPACES",
    "OW_PEEK_ADDR": "PEEK_CHAR",
    "OW_ADV_ADDR": "ADV_PTR",
    "OW_EXPR_ADDR": "LOGIC_OR_EXPR",
    "OW_INT_ADDR": "CUR_TO_INT16",
    "OW_NONZERO_ADDR": "IF_TEST_NONZERO",
    "OW_ERROR_WORD_ADDR": "TRY_MATCH_ERROR",
    "OW_GOTO_WORD_ADDR": "TRY_MATCH_GOTO",
    "OW_GOSUB_WORD_ADDR": "TRY_MATCH_GOSUB",
    "OW_LINENUM_ADDR": "PARSE_LINENUM_CUR",
    "OW_FIND_LINE_ADDR": "RUN_FIND_LINE",
    "OW_ENTER_ADDR": "RUN_ENTER_RECORD",
    "OW_GOSUB_PUSH_ADDR": "RUN_GOSUB_PUSH",
    "OW_FOR_SLOT_ADDR": "FOR_SLOT_ADDR",
    "OW_FOR_ROOM_ADDR": "OW_FOR_ROOM",

    "PU_MAIN_CALL_ADDR": "EXT_BANK_MAIN_CALL",
    "PU_SKIP_ADDR": "SKIP_SPACES",
    "PU_PEEK_ADDR": "PEEK_CHAR",
    "PU_ADV_ADDR": "ADV_PTR",
    "PU_IDENT_ADDR": "LEX_IDENT_PEEK",
    "PU_STRING_ADDR": "STRING_EXPR",
    "PU_EXPR_ADDR": "LOGIC_OR_EXPR",
    "PU_LOAD_D_ADDR": "VAL_LOAD_CUR_TO_OPA_D",
    "PU_DFOUT_ADDR": "MBF_DFOUT",
    "PU_PRINT_ADDR": "PRINT_CHAR",
    "PU_NEWLINE_ADDR": "NEWLINE",
    "BANK1_MAIN_CALL_ADDR": "EXT_BANK_MAIN_CALL",
    "BANK1_SKIP_SPACES_ADDR": "SKIP_SPACES",
    "BANK1_PEEK_CHAR_ADDR": "PEEK_CHAR",
    "BANK1_LEX_IDENT_PEEK_ADDR": "LEX_IDENT_PEEK",
    "BANK1_PARSE_INT_ARG_ADDR": "PARSE_INT_ARG",
    "BANK1_READ_CHR_ADDR": "MAIN_SUB_READ_CHR_RETRY",
    "BANK1_PRINT_CHAR_ADDR": "PRINT_CHAR",
    "BANK1_NEWLINE_ADDR": "NEWLINE",
    "BANK1_ADV_PTR_ADDR": "ADV_PTR",
    "BANK1_AT_END_ADDR": "AT_END",
    "BANK1_PROGRAM_CLEAR_ADDR": "PROGRAM_CLEAR",
    "BANK1_PARSE_LINENUM_ADDR": "PARSE_LINENUM",
    "BANK1_PROGRAM_STORE_LINE_ADDR": "PROGRAM_STORE_LINE",
    "BANK1_SELECT_ERROR_MSG_ADDR": "SELECT_ERROR_MSG",
    "BANK1_ERR_BELL_ADDR": "ERR_BELL",
    "BANK1_PRINT_STR_ADDR": "PRINT_STR",
    "BANK1_OK_TXT_ADDR": "OK_TXT",
}

EXT_BANK2_MAIN_ADDR_LABELS = {
    "AR_PARSE_ADDR": "ARRAY_PARSE",
    "AR_SINGLE_ADDR": "ARRAY_SINGLE",
    "AR_DATA_ADDR": "DATA_READ_ONE",
    "AR_VWRITE_ADDR": "VAR_WRITE_NUMERIC",
    "AR_SWRITE_ADDR": "VAR_WRITE_STRING",
    "AR_SSTORE_ADDR": "ARRAY_STRING_STORE",

    "AR_SKIP_ADDR": "SKIP_SPACES",
    "AR_PEEK_ADDR": "PEEK_CHAR",
    "AR_ADV_ADDR": "ADV_PTR",
    "AR_IDENT_ADDR": "LEX_IDENT_CONSUME",
    "AR_EXPR_ADDR": "LOGIC_OR_EXPR",
    "AR_INT_ADDR": "VAL_TO_INT16_CUR",
    "AR_FIND_ADDR": "ARRAY_FIND",
    "AR_SIZE_ADDR": "ARRAY_SIZE",
    "AR_PAGEFREE_ADDR": "ARRAY_PAGE_FREE",

    "BANK2_MAIN_CALL_ADDR": "EXT_BANK_MAIN_CALL",
    "BANK2_SKIP_SPACES_ADDR": "SKIP_SPACES",
    "BANK2_PEEK_CHAR_ADDR": "PEEK_CHAR",
    "BANK2_ADV_PTR_ADDR": "ADV_PTR",
    "BANK2_AT_END_ADDR": "AT_END",
    "BANK2_READ_CHR_ADDR": "MAIN_SUB_READ_CHR_RETRY",
    "BANK2_SEND_ADDR": "MAIN_SUB_SEND",
    "BANK2_SEND_CONT_ADDR": "MAIN_SUB_SEND_REQUEST_CONT",
    "BANK2_SEND_PAIR_ADDR": "MAIN_SUB_SEND_PAIR",
    "BANK2_RECV_ADDR": "MAIN_SUB_RECV",
    "BANK2_LIST_RENDER_ADDR": "LIST_RENDER_ALL",
    "BANK2_CAPTURE_CHAR_ADDR": "SAVE_CAPTURE_CHAR",
    # グラフィック（src/ext_bank/gfx.asm、l4-graphics.md）
    "GX_EXPECT_ADDR": "EXPECT_CHAR",
    "GX_PARSE_INT_ADDR": "PARSE_INT_ARG",
    "GX_SET_INT_ADDR": "VAL_SET_INT",
    "GX_TEXT_CLS_ADDR": "CLS_SCREEN",
}

EXT_BANK3_MAIN_ADDR_LABELS = {
    "AR_FRE_ADDR": "ARRAY_FRE",
    "AR_READ_STMT_ADDR": "ARRAY_READ_STMT",
    "S9_FN_IS_STRING_ADDR": "FN_IS_STRING",
    "S9E_OPS_ADDR": "CMP_OPS",
    "S9B_EXPR_ADDR": "LOGIC_OR_EXPR",
    "S9B_CLEAR_ADDR": "RUN_CLEAR_STATE",
    "S9_EXPECT_ADDR": "EXPECT_CHAR",
    "S9_PARSE_INT_ADDR": "PARSE_INT_ARG",
    "S9_STRING_EXPR_ADDR": "STRING_EXPR",
    "S9_IDENT_PEEK_ADDR": "LEX_IDENT_PEEK",
    "S9_NUM_ARG_ADDR": "FTNF_NUM_ARG",
    "S9_LOAD_OPA_ADDR": "VAL_LOAD_CUR_TO_OPA",
    "S9_MBF_SUB_ADDR": "MBF_SUB",
    "S9_SET_SINGLE_ADDR": "VAL_SET_SINGLE_FROM_RES",
    "S9_TO_INT_ADDR": "CUR_TO_INT16",
    "S9_SET_INT_ADDR": "VAL_SET_INT",
    "S9_VAR_GET_ADDR": "VAR_GET_OR_CREATE",
    "S9_COPY_ADDR": "STR_COPY_BN",
    "S9_MATCH_NEXT_ADDR": "TRY_MATCH_NEXT",
    "S9_ENTER_RECORD_ADDR": "RUN_ENTER_RECORD",
    "S9_ADV_RECORD_ADDR": "RUN_ADVANCE_RECORD",
    "S9_PARSE_LINE_ADDR": "PARSE_LINENUM_CUR",
    "S9_FIND_LINE_ADDR": "RUN_FIND_LINE",
    "B3_MAIN_CALL_ADDR": "EXT_BANK_MAIN_CALL",
    "LN_FIN_ADDR": "MBF_FIN",
    "LN_DFIN_ADDR": "MBF_DFIN",
    "LN_FOUT_ADDR": "MBF_FOUT",
    "LN_DFOUT_ADDR": "MBF_DFOUT",
    "LN_ERROR_MESSAGE_ADDR": "_l4brl_msg",
    "HEXCONST_DIRECT_RECORD_ADDR": "DIRECT_RECORD",
    "HEXCONST_INPUT_ERROR_ADDR": "_run_error",
    "HEXCONST_NEG_ADDR": "VAL_NEG",
    "B3_SKIP_SPACES_ADDR": "SKIP_SPACES",
    "B3_LEX_IDENT_CONSUME_ADDR": "LEX_IDENT_CONSUME",
    "B3_DATA_READ_ONE_ADDR": "DATA_READ_ONE",
    "B3_VAR_WRITE_NUMERIC_ADDR": "VAR_WRITE_NUMERIC",
    "B3_VAR_WRITE_STRING_ADDR": "VAR_WRITE_STRING",
    "B3_PEEK_CHAR_ADDR": "PEEK_CHAR",
    "B3_ADV_PTR_ADDR": "ADV_PTR",
    "B3_AT_END_ADDR": "AT_END",
}

# EXT_BANK0_SQR_ENTRY(bank0.asm)が参照する常駐ラベル→bank0.asm側EQU名
# の対応。make_ext_rom_banks.pyの--addrへ実測アドレスを渡すのに使う
# (MBF_ADD_ADDRと同じ手法の汎用版、build_ext_bank_roms参照)。
EXT_BANK0_SQR_ADDR_LABELS = {
    "MBF_STOD_ADDR": "MBF_STOD",
    "MBF_DADD_ADDR": "MBF_DADD",
    "MBF_DDIV_ADDR": "MBF_DDIV",
    "MBF_DTOS_ADDR": "MBF_DTOS",
}

# EXT_BANK0_SIN_ENTRY/COS_ENTRY/TAN_ENTRY(bank0.asm、第4.16a節)が参照する
# 常駐ラベル→bank0.asm側EQU名の対応。EXT_BANK0_SQR_ADDR_LABELSと同じ手法。
EXT_BANK0_SINCOS_ADDR_LABELS = {
    "SIN_ADD_ADDR": "MBF_ADD",
    "SIN_SUB_ADDR": "MBF_SUB",
    "SIN_MUL_ADDR": "MBF_MUL",
    "SIN_DIV_ADDR": "MBF_DIV",
    "SIN_NEG_ADDR": "MBF_NEG",
    "SIN_TRUNC_ADDR": "TRUNC_TO_SINGLE",
}

# EXT_BANK0_ATN_ENTRY/EXP_ENTRY/LOG_ENTRY(bank0.asm、第4.16b節)が参照する
# 常駐ラベル→bank0.asm側EQU名の対応。EXT_BANK0_SINCOS_ADDR_LABELSと同じ手法。
# 第4.19節のDEF FN/SWAP/ERASE本体が窓外中継で呼ぶmain番地。
EXT_BANK0_DEFFN_ADDR_LABELS = {
    "FN_ARRAY_NORMALIZE_ADDR": "ARRAY_NORMALIZE",
    "FN_ARRAY_PARSE_ADDR": "ARRAY_PARSE",
    "FN_ARRAY_SIZE_ADDR": "ARRAY_SIZE",
    "FN_ARRAY_ERASE_ADDR": "ARRAY_ERASE",
    "FN_ARRAY_TRIM_ADDR": "ARRAY_TRIM",
    "FN_STR_READ_ADDR": "VAR_READ_STRING",
    "FN_ARRAY_READ_ADDR": "ARRAY_READ",
    "FN_MAIN_CALL_ADDR": "EXT_BANK_MAIN_CALL",
    "FN_SKIP_ADDR": "SKIP_SPACES",
    "FN_PEEK_ADDR": "PEEK_CHAR",
    "FN_ADV_ADDR": "ADV_PTR",
    "FN_IDENT_ADDR": "LEX_IDENT_CONSUME",
    "FN_IDENT_PEEK_ADDR": "LEX_IDENT_PEEK",
    "FN_FOLD_ADDR": "FOLD_UPPER",
    "FN_MATCH_ADDR": "TRY_MATCH_KEYWORD_GENERIC",
    "FN_EXPR_ADDR": "LOGIC_OR_EXPR",
    "FN_STRING_ADDR": "STRING_EXPR",
    "FN_INT_ADDR": "CUR_TO_INT16",
    "FN_SET_INT_ADDR": "VAL_SET_INT",
    "FN_PROMOTE_ADDR": "VAL_PROMOTE_CUR_TO_DOUBLE",
    "FN_VAR_FIND_ADDR": "VAR_FIND",
    "FN_VAR_ALLOC_ADDR": "VAR_ALLOC",
    "FN_VAR_GET_ADDR": "VAR_GET_OR_CREATE",
    "FN_VAR_WRITE_ADDR": "VAR_WRITE_NUMERIC",
    "FN_STR_WRITE_ADDR": "VAR_WRITE_STRING",
    "FN_ARRAY_FIND_ADDR": "ARRAY_FIND",
    "FN_ARRAY_GET_ADDR": "ARRAY_GET_OR_CREATE_DEFAULT",
    "FN_ARRAY_ELEM_ADDR": "ARRAY_ELEM_ADDR",
    "FN_HEAP_FIND_ADDR": "HEAP_FIND_MAIN",
    "FN_HEAP_ALLOC_ADDR": "HEAP_ALLOC_MAIN",
    "FN_BANK3_ADDR": "S9_BANK_CALL",
    "FN_TO_INT_ADDR": "VAL_TO_INT16_CUR",
    # 第4.20節 TAB(・SPC(・POS・CSNG・XOR・EQV・IMP
    "TS_VPUSH_ADDR": "VAL_PUSH",
    "TS_VPOP_ADDR": "VAL_POP",
    "TS_VDISCARD_ADDR": "VAL_POP_DISCARD",
    "TS_ORLEVEL_ADDR": "LOGIC_OR_LEVEL",
    "TS_PUTC_ADDR": "PRINT_CHAR",
    "TS_NEWLINE_ADDR": "NEWLINE",
    "TS_LOADOPA_ADDR": "VAL_LOAD_CUR_TO_OPA",
    "TS_LOADOPB_ADDR": "VAL_LOAD_RHS_TO_OPB",
    "TS_MBFCMP_ADDR": "MBF_CMP",
    "TS_LOADOPA_D_ADDR": "VAL_LOAD_CUR_TO_OPA_D",
    "TS_LOADOPB_D_ADDR": "VAL_LOAD_RHS_TO_OPB_D",
    "TS_DCMP_ADDR": "MBF_DCMP",
    "TS_ZONE_ADDR": "ZONE_PAD",
    # 第4.22節 WIDTH（3000バイト全体の消去）
    "WB_CLEAR_ADDR": "CLEAR_N_ROWS",
    # 第4.21節 型宣言文・プログラム中のRUN
    "DT_LINENUM_ADDR": "PARSE_LINENUM_CUR",
    "DT_FIND_ADDR": "RUN_FIND_LINE",
    "DT_ENTER_ADDR": "RUN_ENTER_RECORD",
    "DT_RESET_ADDR": "RUN_RESET_STATE",
    "DT_TOINT_RHS_ADDR": "VAL_TO_INT16_RHS",
    "DT_SDIV_ADDR": "SDIV16",
    # グラフィック文のバンク0中継部（src/l4_basic/gfxhook.asm）。バンク0からバンク2を呼ぶ
    "GFX_BANKCALL_ADDR": "EXT_BANK_CALL",
}

EXT_BANK0_ATNEXPLOG_ADDR_LABELS = {
    "AEL_ADD_ADDR": "MBF_ADD",
    "AEL_SUB_ADDR": "MBF_SUB",
    "AEL_MUL_ADDR": "MBF_MUL",
    "AEL_DIV_ADDR": "MBF_DIV",
    "AEL_NEG_ADDR": "MBF_NEG",
    "AEL_CMP_ADDR": "MBF_CMP",
    "AEL_TRUNC_ADDR": "TRUNC_TO_SINGLE",
    "AEL_ITOS_ADDR": "MBF_INT_TO_SINGLE",
    "RND_FIN_AWAY_ADDR": "FIN_ACC_TO_SINGLE_AWAY",
}

# 故障注入(自己検査の陰性対照専用、2026-09-20): EXT_BANK_CALLが
# CALL EXT_BANK_JUMP_HLをまたいでC(旧0x32)・E(旧0x71)をスタックへ退避
# する修正(src/ext_bank/relay.asm「2026-09-20の修正」参照、
# docs/notes/l4-c8-transcendental-conformance-scene-results.mdで見つかった
# SQRのハングの原因)を外し、修正前(バンク側ルーチンがBC/DEを自由に
# 使うと窓の復元が壊れる)の状態を再現する。
# tools/l4_sqr_endtoend_selftest.sh 専用。
EXT_BANK_BCDE_SAVE_FAULT_OLD = (
    ";FAULT-INJECT-BCDE-SAVE-BEGIN(故障注入 --inject-ext-bank-bcde-fault が\n"
    "; この2行〈PUSH BC/PUSH DE〉を削る。build_main_rom.pyのテキスト置換用\n"
    "; マーカー、削除しても文法上壊れないようこの節だけで完結させてある)\n"
    "    PUSH BC                       ; C(旧0x32)をスタックへ退避\n"
    "                                   ; ——バンク側ルーチンがBC/DEを自由に\n"
    "                                   ; 使ってよいことにするため(上記\n"
    "                                   ; 「2026-09-20の修正」参照。Bの中身は\n"
    "                                   ; 以後使わないので気にしない)\n"
    "    PUSH DE                       ; E(旧0x71)をスタックへ退避(Dのバンク\n"
    "                                   ; 番号も以後不要)\n"
    ";FAULT-INJECT-BCDE-SAVE-END"
)
EXT_BANK_BCDE_SAVE_FAULT_NEW = (
    "; 故障注入(--inject-ext-bank-bcde-fault): PUSH BC/PUSH DEを削り、\n"
    "; 修正前(バンク側ルーチンがBC/DEを使うと窓復元が壊れる)を再現する。"
)
EXT_BANK_BCDE_RESTORE_FAULT_OLD = (
    ";FAULT-INJECT-BCDE-RESTORE-BEGIN(同上。この2行〈POP DE/POP BC〉を削る)\n"
    "    POP DE                        ; E = 旧0x71を復元(POPはA/Fを変えない)\n"
    "    POP BC                        ; C = 旧0x32を復元(同上)\n"
    ";FAULT-INJECT-BCDE-RESTORE-END"
)
EXT_BANK_BCDE_RESTORE_FAULT_NEW = (
    "; 故障注入(--inject-ext-bank-bcde-fault): POP DE/POP BCを削る(対)。"
)

# main<->sub単一セクタREADの陰性対照。各置換はバイト数を維持し、
# 該当するコード列だけを変える。所定のNOP列は故障箇所通過印の書込みへ置換する。
MAIN_SUB_WAIT_FAULT_OLD = (
    "_ms_send_wait_before_site:\n"
    "    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n"
    "    LD C,002h\n"
    "    CALL MAIN_SUB_WAIT_SET"
)
MAIN_SUB_WAIT_FAULT_NEW = (
    "_ms_send_wait_before_site:\n"
    "    LD A,001h\n"
    "    LD (MAIN_SUB_MARK_FAULT_WAIT),A\n"
    "    LD C,002h\n"
    "    CALL MAIN_SUB_WAIT_CLEAR"
)
MAIN_SUB_CONT_FAULT_OLD = (
    "_ms_cont_call_site:\n"
    "    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n"
    "    CALL MAIN_SUB_SEND_CONT"
)
MAIN_SUB_CONT_FAULT_NEW = (
    "_ms_cont_call_site:\n"
    "    PUSH AF\n"
    "    LD A,001h\n"
    "    LD (MAIN_SUB_MARK_FAULT_CONT),A\n"
    "    POP AF\n"
    "    CALL MAIN_SUB_SEND"
)
MAIN_SUB_PAIR_FAULT_OLD = (
    "_ms_pair_call_site:\n"
    "    NOP\n    NOP\n    NOP\n    NOP\n    NOP\n"
    "    CALL MAIN_SUB_RECV_PAIR"
)
MAIN_SUB_PAIR_FAULT_NEW = (
    "_ms_pair_call_site:\n"
    "    LD A,001h\n"
    "    LD (MAIN_SUB_MARK_FAULT_PAIR),A\n"
    "    CALL MAIN_SUB_RECV_PAIR_BROKEN"
)

# m6i-b（事前登録済みB1〜B5）のmain側介入。既定テキスト全体を
# 腕専用の状態機械へ一度だけ置換する。各腕は、起動前置きの有無だけを
# 変え、通常READ本体 MAIN_SUB_READ_KNOWN には触れない。
M6IB_BOOT_OLD = """MAIN_SUB_READ_INIT:
    XOR A
    LD (MAIN_SUB_BOOT_DONE),A
    RET

MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET
"""

M6IB_COMMON_EQU = """M6IB_FRAME_COUNT          EQU MM_M6IB_FRAME_COUNT
M6IB_STAGE                EQU MM_M6IB_STAGE
M6IB_MARK_B               EQU MM_M6IB_MARK_B
M6IB_MARK_C               EQU MM_M6IB_MARK_C
"""

# 予備走（実I/Oログ）で、STEADY_WAIT進入直後を含む呼出し55回が
# B1〜B5の5腕とも通常READ先頭のframe 60に対応した。最初の2回だけ同一
# frame内、以後は1 frameにつき1回。旧値0x21ではB1/B2/B5がframe 38だった。
# 前置きの長さは腕ごとに違うが、この計数器は待機枝でしか増えないため
# 5腕で同じ値になる。B3・B4も流用ではなく実I/Oログで確かめた
# （read_issue_frame=60）。
M6IB_B1_FRAME_CALL_LIMIT = "037h"
M6IB_B2_FRAME_CALL_LIMIT = "037h"
M6IB_B3_FRAME_CALL_LIMIT = "037h"
M6IB_B4_FRAME_CALL_LIMIT = "037h"
M6IB_B5_FRAME_CALL_LIMIT = "037h"

M6IB_INIT = """MAIN_SUB_READ_INIT:
    XOR A
    LD (MAIN_SUB_BOOT_DONE),A
    LD (M6IB_FRAME_COUNT),A
    LD (M6IB_STAGE),A
    LD (M6IB_MARK_B),A
    LD (M6IB_MARK_C),A
    RET
"""

# FRAME_COUNTの閾値は実エミュレータのI/Oログで通常READ先頭がframe 60に
# なる値を腕ごとに固定する。STEADY_WAIT進入直後の呼出しも1回と数える。
M6IB_BOOT_B1 = M6IB_COMMON_EQU + M6IB_INIT + f"""
MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,(M6IB_FRAME_COUNT)
    CP {M6IB_B1_FRAME_CALL_LIMIT}
    JR Z,_m6ib_b1_issue
    INC A
    LD (M6IB_FRAME_COUNT),A
    RET
_m6ib_b1_issue:
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET
"""

M6IB_BOOT_B2 = M6IB_COMMON_EQU + M6IB_INIT + f"""
MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,(M6IB_STAGE)
    OR A
    JR NZ,_m6ib_b2_wait
    XOR A
    CALL MAIN_SUB_SEND
    RET C
    LD A,001h
    LD (M6IB_MARK_B),A
    LD (M6IB_STAGE),A
_m6ib_b2_wait:
    LD A,(M6IB_FRAME_COUNT)
    CP {M6IB_B2_FRAME_CALL_LIMIT}
    JR Z,_m6ib_b2_issue
    INC A
    LD (M6IB_FRAME_COUNT),A
    RET
_m6ib_b2_issue:
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET
"""

M6IB_BOOT_B3 = M6IB_COMMON_EQU + M6IB_INIT + f"""
MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    ; 状態直交化介入中もsubへ実行権を渡す。データポートには触れない。
    IN A,(0FEh)
    LD A,(M6IB_FRAME_COUNT)
    CP {M6IB_B3_FRAME_CALL_LIMIT}
    JR Z,_m6ib_b3_issue
    INC A
    LD (M6IB_FRAME_COUNT),A
    RET
_m6ib_b3_issue:
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET
"""

M6IB_BOOT_B4 = M6IB_COMMON_EQU + M6IB_INIT + f"""
MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,(M6IB_STAGE)
    OR A
    JR NZ,_m6ib_b4_wait
    XOR A
    CALL MAIN_SUB_SEND
    RET C
    LD A,001h
    LD (M6IB_MARK_B),A
    LD (M6IB_STAGE),A
_m6ib_b4_wait:
    LD A,(M6IB_FRAME_COUNT)
    CP {M6IB_B4_FRAME_CALL_LIMIT}
    JR Z,_m6ib_b4_issue
    INC A
    LD (M6IB_FRAME_COUNT),A
    RET
_m6ib_b4_issue:
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET
"""

M6IB_BOOT_B5 = M6IB_COMMON_EQU + M6IB_INIT + f"""
MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,(M6IB_STAGE)
    OR A
    JR NZ,_m6ib_b5_wait
    XOR A
    CALL MAIN_SUB_SEND
    RET C
    LD A,001h
    LD (M6IB_MARK_B),A
    XOR A
    CALL MAIN_SUB_SEND
    RET C
    LD A,007h
    CALL MAIN_SUB_SEND_CONT
    RET C
    CALL MAIN_SUB_RECV
    RET C
    LD A,001h
    LD (M6IB_MARK_C),A
    LD (M6IB_STAGE),A
_m6ib_b5_wait:
    LD A,(M6IB_FRAME_COUNT)
    CP {M6IB_B5_FRAME_CALL_LIMIT}
    JR Z,_m6ib_b5_issue
    INC A
    LD (M6IB_FRAME_COUNT),A
    RET
_m6ib_b5_issue:
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET
"""

# m6i-h（固定フレーム待ちを持たない2腕）。0xE00Dはm6i-bの共通領域で
# 未使用の1バイトであり、H-Bが2回目のREADを呼んだ事実だけに割り当てる。
M6IH_COMMON_EQU = M6IB_COMMON_EQU + "M6IH_MARK_RETRY          EQU MM_M6IH_MARK_RETRY\n"

M6IH_BOOT_A = M6IH_COMMON_EQU + """MAIN_SUB_READ_INIT:
    XOR A
    LD (MAIN_SUB_BOOT_DONE),A
    LD (M6IB_MARK_B),A
    RET

MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    XOR A
    CALL MAIN_SUB_SEND
    RET C
    LD A,001h
    LD (M6IB_MARK_B),A
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET
"""

M6IH_BOOT_B = M6IH_COMMON_EQU + """MAIN_SUB_READ_INIT:
    XOR A
    LD (MAIN_SUB_BOOT_DONE),A
    LD (M6IH_MARK_RETRY),A
    RET

MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A
    RET NZ
    LD A,001h
    LD (M6IH_MARK_RETRY),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET
"""

# m6i-i: 任意座標READの11行掃引。各READの直前に行番号を0xE038へ書く。
# 0xE038は既存の測定用RAM（M6IA_REPEAT_LEFT=0xE036、2バイト）の直後で、
# tools/check_m6ii_preregistration.py が全EQUとの非衝突を機械検査する。
M6II_ROW_MARKER_ADDRESS = memmap.addresses()["MM_M6II_ROW_MARKER"]
M6II_BOOT_SWEEP = """M6II_ROW_MARKER          EQU MM_M6II_ROW_MARKER
MAIN_SUB_READ_INIT:
    XOR A
    LD (MAIN_SUB_BOOT_DONE),A
    LD (M6II_ROW_MARKER),A
    RET

MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    LD HL,M6II_SWEEP_TABLE
    LD B,00Bh
_m6ii_sweep_loop:
    LD A,(HL)
    LD (M6II_ROW_MARKER),A
    INC HL
    LD A,(HL)
    INC HL
    LD D,(HL)
    INC HL
    LD E,(HL)
    INC HL
    CALL MAIN_SUB_READ_CHR_RETRY
    DJNZ _m6ii_sweep_loop
    RET

; 行番号, drive, 論理track(C*2+H), R。事前登録の順序を固定する。
M6II_SWEEP_TABLE:
    DB 01h,00h,00h,01h
    DB 02h,00h,01h,01h
    DB 03h,00h,02h,01h
    DB 04h,00h,00h,10h
    DB 05h,00h,4Fh,10h
    DB 06h,00h,28h,08h
    DB 07h,00h,0Bh,0Bh
    DB 08h,01h,00h,01h
    DB 09h,01h,01h,01h
    DB 0Ah,01h,4Fh,10h
    DB 0Bh,00h,00h,01h
"""

# m6i-k: 測定専用。既定ビルドには注入しない。
M6IK_ROWS = ((0, 0, 1), (0, 37, 13), (1, 37, 13),
             (1, 1, 1), (0, 1, 1), (1, 0, 1))
M6IK_ARMS = {
    "K-00": (None, 0), "K-01": (None, 1),
    "K-F0": (15, 0), "K-F1": (15, 1),
    "K-M1": (1, 1), "K-FR": (15, 1),
}
# 第223版: 既定のmainは0x17,0x0Fを1回送り(MAIN_SUB_SEND_LOGICAL_ONCE)P1=0x01で
# 要求するようになった。m6i-kの器具は「0x17の有無×P1」を腕ごとに自分で振る
# 測定装置なので、既定側の送信を器具ビルドでは外し、P1送出点だけを置換する。
M6IK_ONCE_OLD = "    CALL MAIN_SUB_SEND_LOGICAL_ONCE\n    JP C,_ms_read_timeout\n"
M6IK_P1_OLD = ("    LD A,001h                   ; P1=0x01（1.36a節）\n"
               "    CALL MAIN_SUB_SEND_REQUEST_CONT\n    JP C,_ms_read_timeout")
M6IK_R_OLD = "    LD A,(MAIN_SUB_CHR_SECTOR)\n    CALL MAIN_SUB_SEND_REQUEST_CONT"


def m6ik_boot(arm: str) -> str:
    pre, _p1 = M6IK_ARMS[arm]
    presend = ("" if pre is None else f"""    LD A,017h
    CALL MAIN_SUB_SEND
    RET C
    LD A,0{pre:02X}h
    CALL MAIN_SUB_SEND_REQUEST_CONT
    RET C
""")
    table = "\n".join(
        f"    DB 0{i:02X}h,0{drive:02X}h,0{track:02X}h,0{sector:02X}h"
        for i, (drive, track, sector) in enumerate(M6IK_ROWS, 1))
    return f"""M6IK_ROW_MARKER EQU MM_M6IK_ROW_MARKER
M6IK_PRE_MARKER EQU MM_M6IK_PRE_MARKER
M6IK_NEXT_ROW EQU MM_M6IK_NEXT_ROW
MAIN_SUB_READ_INIT:
    XOR A
    LD (MAIN_SUB_BOOT_DONE),A
    LD (M6IK_ROW_MARKER),A
    LD (M6IK_PRE_MARKER),A
    LD (M6IK_NEXT_ROW),A
    RET
MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    JR NZ,_m6ik_next
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_SEND
    RET C
{presend}    LD A,001h
    LD (M6IK_PRE_MARKER),A
_m6ik_next:
    LD A,(M6IK_NEXT_ROW)
    CP 006h
    RET NC
    LD E,A
    LD D,000h
    LD HL,M6IK_TABLE
    ADD HL,DE
    ADD HL,DE
    ADD HL,DE
    ADD HL,DE
    LD A,(HL)
    LD (M6IK_ROW_MARKER),A
    INC HL
    LD A,(HL)
    INC HL
    LD D,(HL)
    INC HL
    LD E,(HL)
    CALL MAIN_SUB_READ_CHR_RETRY
    LD A,(M6IK_NEXT_ROW)
    INC A
    LD (M6IK_NEXT_ROW),A
    RET
M6IK_TABLE:
{table}
"""

# m6i-i故障注入。いずれも一般READの原文へだけ適用し、置換点が一意で
# なければビルドを止める。既定および--enable-disk-read-chr単独は不変。
M6II_H_FAULT_OLD = "    LD A,D\n    LD (MAIN_SUB_CHR_LOGICAL_TRACK),A"
M6II_H_FAULT_NEW = "    LD A,D\n    AND 0FEh\n    LD (MAIN_SUB_CHR_LOGICAL_TRACK),A"
M6II_D_FAULT_OLD = "    AND 001h\n    LD (MAIN_SUB_DRIVE_SELECT),A"
M6II_D_FAULT_NEW = "    XOR A\n    LD (MAIN_SUB_DRIVE_SELECT),A"
M6II_R_FAULT_OLD = (
    "    LD A,(MAIN_SUB_CHR_SECTOR)\n"
    "    CALL MAIN_SUB_SEND_REQUEST_CONT"
)
M6II_R_FAULT_NEW = (
    "    LD A,(MAIN_SUB_CHR_SECTOR)\n"
    "    INC A\n"
    "    CALL MAIN_SUB_SEND_REQUEST_CONT"
)
M6II_RETRY_FAULT_OLD = """MAIN_SUB_READ_CHR_RETRY:
    PUSH AF
    PUSH DE
    CALL MAIN_SUB_READ_CHR
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A
    JR NZ,_ms_chr_retry_first_success
    POP DE                       ; 入口D/Eを2回目へ戻す
    POP AF                       ; 入口Aとフラグを2回目へ戻す
    CALL MAIN_SUB_READ_CHR
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A                         ; 成功時CY=0を明示
    RET NZ
    SCF
    RET
_ms_chr_retry_first_success:
    POP DE
    POP AF
    OR A                         ; 保存されていたCYに依存せず成功CY=0
    RET"""
M6II_RETRY_FAULT_NEW = """MAIN_SUB_READ_CHR_RETRY:
    PUSH DE
    CALL MAIN_SUB_READ_CHR
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A
    JR NZ,_ms_chr_retry_first_success
    POP DE                       ; D/Eだけを2回目へ戻し、Aは保存しない
    CALL MAIN_SUB_READ_CHR
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A                         ; 成功時CY=0を明示
    RET NZ
    SCF
    RET
_ms_chr_retry_first_success:
    POP DE
    OR A                         ; 保存されていたCYに依存せず成功CY=0
    RET"""


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
                        inject_editkey_home_clr_fault: bool = False,
                        inject_key_repeat_fault: bool = False,
                        enable_l4_selftest: bool = False,
                        enable_ext_bank_selftest: bool = False,
                        inject_ext_bank_window_fault: bool = False,
                        inject_ext_bank_bcde_fault: bool = False,
                        enable_vsync_regcheck: bool = False,
                        inject_vsync_no_save_fault: bool = False,
                        enable_main_sub_read: bool = False,
                        enable_disk_read_retry: bool = False,
                        enable_disk_read_chr: bool = False,
                        enable_main_sub_boot: bool = True,
                        inject_main_sub_wait_fault: bool = False,
                        inject_main_sub_cont_fault: bool = False,
                        inject_main_sub_pair_fault: bool = False,
                        inject_m6ib_b1: bool = False,
                        inject_m6ib_b2: bool = False,
                        inject_m6ib_b3: bool = False,
                        inject_m6ib_b4: bool = False,
                        inject_m6ib_b5: bool = False,
                        inject_m6ih_a: bool = False,
                        inject_m6ih_b: bool = False,
                        inject_m6ii_sweep: bool = False,
                        inject_m6ii_fault_h: bool = False,
                        inject_m6ii_fault_d: bool = False,
                        inject_m6ii_fault_r: bool = False,
                        inject_m6ii_fault_retry: bool = False,
                        inject_m6ik_arm: str | None = None) -> str:
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
    # 拡張ROMバンク: 割り込み無しで行える範囲の自己検査(常駐部からの
    # 呼び出し・窓の中からの呼び出し)はSCREEN_MAINと同じ挿入点(まだ
    # IM2/I/EIの設定前)で呼べる。l4_selftest_callと同じ理由で既定offにする
    # (無条件で呼ぶとL1適合検査のOUT件数・サイクル数が変わる)。
    ext_bank_selftest_call = "    CALL EXT_BANK_SELFTEST\n" if enable_ext_bank_selftest else ""
    if enable_main_sub_boot and enable_disk_read_retry:
        main_sub_init_call = "    CALL DISK_READ_RETRY_INIT\n"
    elif enable_main_sub_boot and enable_main_sub_read:
        main_sub_init_call = "    CALL MAIN_SUB_READ_INIT\n"
    else:
        main_sub_init_call = ""
    # 段B: 専用域に移したDONEはINKEYの初期化と共用しない。
    vsync_regcheck_init = ("    XOR A\n    LD (MM_VSYNC_REGCHECK_DONE),A\n"
                          if enable_vsync_regcheck else "")
    # 拡張ROMバンク: EXT_BANK_BUSY(再入検出フラグ)の初期化は
    # selftestフラグの有無と無関係に必ず行う(src/ext_bank/relay.asmの
    # EXT_BANK_INITコメント参照。RAMがゼロ初期化される保証が無いため、
    # ここで明示的に0にしないと拡張ROMバンクを実際に使う将来の機能が
    # 「常に再入中」と誤検出されて一切動かなくなる)。
    ipl_text = ipl_text.replace(
        INSERT_MARK,
        "    CALL SCREEN_MAIN\n    CALL EXT_BANK_INIT\n"
        + l4_selftest_call + ext_bank_selftest_call + main_sub_init_call
        + vsync_regcheck_init + INSERT_MARK)

    # STEADY_WAIT(IM2/I/EI設定済みの定常状態)へ入った直後に呼ぶ自己検査
    # 呼び出し列。複数のフラグが同時に立っても1回のtext置換で済むよう、
    # ここへ積み上げてからまとめて置換する。
    #
    # - 拡張ROMバンク: 割り込みを有効にしたまま多数回呼ぶ自己検査
    #   (EXT_BANK_LOOP_TEST)は、IM2/I/EI設定済みの定常状態に入ってから
    #   呼ぶ(src/ext_bank/relay.asmのコメント参照。EIより前に割り込みを
    #   有効化するとベクタ引きが外れて暴走しうるため)。
    # - VSYNCハンドラのレジスタ退避自己検査(VSYNC_REGCHECK)も同じ理由で
    #   ここから呼ぶ(src/l3_main/vsync_regcheck.asm参照。実際に1回
    #   VSYNCを受理させて確認する必要があるため、定常状態でなければ
    #   意味が無い)。
    steady_wait_calls = ""
    if enable_ext_bank_selftest:
        steady_wait_calls += "    CALL EXT_BANK_LOOP_TEST\n"
    if enable_vsync_regcheck:
        steady_wait_calls += "    CALL VSYNC_REGCHECK\n"
    if enable_main_sub_boot and enable_disk_read_retry:
        steady_wait_calls += "    CALL DISK_READ_RETRY_BOOT_ONCE\n"
    elif enable_main_sub_boot and enable_main_sub_read:
        steady_wait_calls += "    CALL MAIN_SUB_READ_BOOT_ONCE\n"
    if steady_wait_calls:
        if STEADY_WAIT_MARK not in ipl_text:
            raise SystemExit(f"STEADY_WAITの挿入点が見つからない: {STEADY_WAIT_MARK!r}")
        if ipl_text.count(STEADY_WAIT_MARK) != 1:
            raise SystemExit(f"STEADY_WAITの挿入点が一意でない: {STEADY_WAIT_MARK!r}")
        ipl_text = ipl_text.replace(
            STEADY_WAIT_MARK, "STEADY_WAIT:\n" + steady_wait_calls + "    HALT")

    if inject_vsync_no_save_fault:
        for old, new, name in (
            (VSYNC_PUSH_OLD, VSYNC_PUSH_NEW, "PUSH"),
            (VSYNC_POP_OLD, VSYNC_POP_NEW, "POP"),
        ):
            if ipl_text.count(old) != 1:
                raise SystemExit(f"VSYNCハンドラの{name}退避の置換点が一意でない: {old!r}")
            ipl_text = ipl_text.replace(old, new)

    if CURSOR_OLD not in ipl_text:
        raise SystemExit(f"カーソル追従の置換点が見つからない: {CURSOR_OLD!r}")
    if ipl_text.count(CURSOR_OLD) != 1:
        raise SystemExit(f"カーソル追従の置換点が一意でない: {CURSOR_OLD!r}")
    ipl_text = ipl_text.replace(CURSOR_OLD, CURSOR_NEW)
    # VSYNCハンドラ（"VSYNC_HANDLER:" から "T_USART:" の手前まで）の中だけで0x31の値をRAM参照にする
    vs_a = ipl_text.index("VSYNC_HANDLER:\n")
    vs_b = ipl_text.index("T_USART:\n", vs_a)
    vs_body = ipl_text[vs_a:vs_b]
    if vs_body.count(P31_OLD) != 2:
        raise SystemExit("VSYNCハンドラのポート0x31の出力が2個見つからない（make_ipl_rom.py が変わった？）")
    ipl_text = ipl_text[:vs_a] + vs_body.replace(P31_OLD, P31_NEW) + ipl_text[vs_b:]

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
    if inject_editkey_home_clr_fault:
        if keyboard_text.count(EDITKEY_HOME_CLR_FAULT_OLD) != 1:
            raise SystemExit("HOME/CLR故障注入の対象行が一意に見つからない（keyboard.asm が変わった？）")
        keyboard_text = keyboard_text.replace(EDITKEY_HOME_CLR_FAULT_OLD, EDITKEY_HOME_CLR_FAULT_NEW)
    if inject_key_repeat_fault:
        if keyboard_text.count(KEY_REPEAT_DELAY_FAULT_OLD) != 1:
            raise SystemExit("キーリピート故障注入の対象行が一意に見つからない（keyboard.asm が変わった？）")
        keyboard_text = keyboard_text.replace(KEY_REPEAT_DELAY_FAULT_OLD, KEY_REPEAT_DELAY_FAULT_NEW)

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

    vsync_regcheck_path = work / "vsync_regcheck_gen.asm"
    vsync_regcheck_path.write_text(VSYNC_REGCHECK_ASM.read_text(encoding="utf-8"), encoding="utf-8")

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

    mbf_path = work / "l4_mbf_gen.asm"
    mbf_path.write_text(L4_MBF_ASM.read_text(encoding="utf-8"), encoding="utf-8")

    mbf_double_path = work / "l4_mbf_double_gen.asm"
    mbf_double_path.write_text(L4_MBF_DOUBLE_ASM.read_text(encoding="utf-8"), encoding="utf-8")

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

    program_path = work / "l4_program_gen.asm"
    program_path.write_text(L4_PROGRAM_ASM.read_text(encoding="utf-8"), encoding="utf-8")

    run_path = work / "l4_run_gen.asm"
    run_text = L4_RUN_ASM.read_text(encoding="utf-8")
    run_path.write_text(run_text, encoding="utf-8")

    files_path = work / "l4_files_gen.asm"
    files_path.write_text(L4_FILES_ASM.read_text(encoding="utf-8"), encoding="utf-8")

    load_path = work / "l4_load_gen.asm"
    load_path.write_text(L4_LOAD_ASM.read_text(encoding="utf-8"), encoding="utf-8")
    save_path = work / "l4_save_gen.asm"
    save_path.write_text(L4_SAVE_ASM.read_text(encoding="utf-8"), encoding="utf-8")

    # 拡張ROMバンク: 中継ルーチン(EXT_BANK_CALL)は窓(0x6000-0x7FFF)の外に
    # 無ければならない(docs/spec/ext-rom-bank.md 第2節 制約1)。通常ビルドは
    # 他のどのモジュールより前(IPL直後・screen.asmより前)にINCLUDEし、
    # 十分な余白を持って0x6000未満に収める。
    #
    # --inject-ext-bank-window-fault(自己検査の陰性対照専用)のときだけ、
    # わざと窓の中(run.asmの埋め草 AEL_ROM_LAYOUT_PAD の直前、0x79D7の手前)に
    # INCLUDEする。中継ルーチンも窓の中に来て、
    # check_ext_bank_relay_below_window()のビルド時検査が失敗するはずである。
    # 以前は「最後(run.asmの後)」に置いていたが、そこはROM末尾の空きに
    # 中継ルーチンの大きさぶんの余裕を要求し、LISTの整形(l4-s5h)で末尾の
    # 空きが減ると「ROM に収まらない」という別の理由で落ちて検査が
    # 空振りした。埋め草の直前なら中継ルーチンが早い側から抜けたぶん
    # だけ埋め草が減り、他のモジュールの配置・ROM末尾の使用量は変わらない
    # (ext_bank_relay_pathの挿入位置だけが変わる)。
    ext_bank_relay_text = EXT_BANK_RELAY_ASM.read_text(encoding="utf-8")
    if inject_ext_bank_bcde_fault:
        if ext_bank_relay_text.count(EXT_BANK_BCDE_SAVE_FAULT_OLD) != 1:
            raise SystemExit("EXT_BANK_CALL BC/DE退避の故障注入対象(退避側)が一意に見つからない（relay.asmが変わった？）")
        if ext_bank_relay_text.count(EXT_BANK_BCDE_RESTORE_FAULT_OLD) != 1:
            raise SystemExit("EXT_BANK_CALL BC/DE退避の故障注入対象(復元側)が一意に見つからない（relay.asmが変わった？）")
        ext_bank_relay_text = ext_bank_relay_text.replace(
            EXT_BANK_BCDE_SAVE_FAULT_OLD, EXT_BANK_BCDE_SAVE_FAULT_NEW)
        ext_bank_relay_text = ext_bank_relay_text.replace(
            EXT_BANK_BCDE_RESTORE_FAULT_OLD, EXT_BANK_BCDE_RESTORE_FAULT_NEW)
    ext_bank_relay_path = work / "ext_bank_relay_gen.asm"
    ext_bank_relay_path.write_text(ext_bank_relay_text, encoding="utf-8")
    ext_bank_relay_include = f'\nINCLUDE "{ext_bank_relay_path}"\n'

    # 「窓の中から呼んでも戻れる」自己検査用プローブ(src/ext_bank/
    # wincall_probe.asm)。窓の中の常駐コードとして振る舞わせたいので、
    # 常にrun.asmの直後(=既存モジュールの末尾)にINCLUDEする
    # (--inject-ext-bank-window-faultの影響を受けない)。
    ext_bank_wincall_probe_path = work / "ext_bank_wincall_probe_gen.asm"
    ext_bank_wincall_probe_path.write_text(
        EXT_BANK_WINCALL_PROBE_ASM.read_text(encoding="utf-8"), encoding="utf-8")

    if inject_ext_bank_window_fault:
        pad_mark = "AEL_ROM_LAYOUT_PAD:\n"
        if run_text.count(pad_mark) != 1:
            raise SystemExit("埋め草 AEL_ROM_LAYOUT_PAD が run.asm に一意に見つからない")
        run_text = run_text.replace(
            pad_mark, ext_bank_relay_include + pad_mark)
        run_path.write_text(run_text, encoding="utf-8")

    combined = (
        f"; EXTRA_LINES: --extra-lines で指定された値（スクロール試験用の埋め草行数）\n"
        f"EXTRA_LINES EQU {extra_lines}\n"
        + ipl_text
    )
    if not inject_ext_bank_window_fault:
        combined += ext_bank_relay_include
    combined += (
        f'\nINCLUDE "{screen_path}"\n'
        + f'\nINCLUDE "{keyboard_path}"\n'
        + f'\nINCLUDE "{key_table_path}"\n'
        + f'\nINCLUDE "{vsync_regcheck_path}"\n'
        + f'\nINCLUDE "{tokens_path}"\n'
        + f'\nINCLUDE "{print_dispatch_path}"\n'
        + f'\nINCLUDE "{errors_path}"\n'
        + f'\nINCLUDE "{lexer_path}"\n'
        + f'\nINCLUDE "{mbf_path}"\n'
        + f'\nINCLUDE "{mbf_double_path}"\n'
        + f'\nINCLUDE "{interp_path}"\n'
        + f'\nINCLUDE "{program_path}"\n'
        + f'\nINCLUDE "{run_path}"\n'
        + f'\nINCLUDE "{files_path}"\n'
        + f'\nINCLUDE "{load_path}"\n'
        + f'\nINCLUDE "{save_path}"\n'
    )
    combined += f'\nINCLUDE "{ext_bank_wincall_probe_path}"\n'
    if enable_main_sub_read:
        main_sub_read_text = MAIN_SUB_READ_ASM.read_text(encoding="utf-8")
        for enabled, old, new, name in (
            (inject_main_sub_wait_fault, MAIN_SUB_WAIT_FAULT_OLD,
             MAIN_SUB_WAIT_FAULT_NEW, "待ちビット判定"),
            (inject_main_sub_cont_fault, MAIN_SUB_CONT_FAULT_OLD,
             MAIN_SUB_CONT_FAULT_NEW, "継続SEND"),
            (inject_main_sub_pair_fault, MAIN_SUB_PAIR_FAULT_OLD,
             MAIN_SUB_PAIR_FAULT_NEW, "2位置PAIR"),
        ):
            if enabled:
                if main_sub_read_text.count(old) != 1:
                    raise SystemExit(
                        f"main<->sub {name}故障注入の対象が一意に見つからない")
                main_sub_read_text = main_sub_read_text.replace(old, new)
        m6ib_variants = [
            (inject_m6ib_b1, M6IB_BOOT_B1, "B1"),
            (inject_m6ib_b2, M6IB_BOOT_B2, "B2"),
            (inject_m6ib_b3, M6IB_BOOT_B3, "B3"),
            (inject_m6ib_b4, M6IB_BOOT_B4, "B4"),
            (inject_m6ib_b5, M6IB_BOOT_B5, "B5"),
            (inject_m6ih_a, M6IH_BOOT_A, "H-A"),
            (inject_m6ih_b, M6IH_BOOT_B, "H-B"),
            (inject_m6ii_sweep, M6II_BOOT_SWEEP, "I-S"),
            (inject_m6ik_arm is not None, m6ik_boot(inject_m6ik_arm)
             if inject_m6ik_arm is not None else "", "m6i-k"),
        ]
        enabled_m6ib = [(text, arm) for enabled, text, arm in m6ib_variants if enabled]
        if len(enabled_m6ib) > 1:
            raise SystemExit("m6i-b/m6i-h/m6i-i main介入は1つだけ指定する")
        if enabled_m6ib:
            replacement, arm = enabled_m6ib[0]
            if main_sub_read_text.count(M6IB_BOOT_OLD) != 1:
                raise SystemExit(f"m6i-b {arm} main介入の対象が一意に見つからない")
            main_sub_read_text = main_sub_read_text.replace(M6IB_BOOT_OLD, replacement)
        main_sub_read_path = work / "main_sub_read_gen.asm"
        main_sub_read_path.write_text(main_sub_read_text, encoding="utf-8")
        combined += f'\nINCLUDE "{main_sub_read_path}"\n'
    if enable_disk_read_retry:
        combined += f'\nINCLUDE "{DISK_READ_RETRY_ASM}"\n'
    if enable_disk_read_chr:
        main_sub_chr_text = MAIN_SUB_READ_CHR_ASM.read_text(encoding="utf-8")
        chr_fault_enabled = any((inject_m6ii_fault_h, inject_m6ii_fault_d,
                                 inject_m6ii_fault_r, inject_m6ii_fault_retry,
                                 inject_m6ik_arm is not None))
        for enabled, old, new, name in (
            (inject_m6ii_fault_h, M6II_H_FAULT_OLD, M6II_H_FAULT_NEW, "I-F-H"),
            (inject_m6ii_fault_d, M6II_D_FAULT_OLD, M6II_D_FAULT_NEW, "I-F-D"),
            (inject_m6ii_fault_r, M6II_R_FAULT_OLD, M6II_R_FAULT_NEW, "I-F-R"),
            (inject_m6ii_fault_retry, M6II_RETRY_FAULT_OLD,
             M6II_RETRY_FAULT_NEW, "I-F-RETRY"),
        ):
            if enabled:
                if main_sub_chr_text.count(old) != 1:
                    raise SystemExit(f"m6i-i {name}故障注入の対象が一意に見つからない")
                main_sub_chr_text = main_sub_chr_text.replace(old, new)
        if inject_m6ik_arm is not None:
            p1 = M6IK_ARMS[inject_m6ik_arm][1]
            replacement = (f"    LD A,0{p1:02X}h\n" +
                           "    CALL MAIN_SUB_SEND_REQUEST_CONT\n"
                           "    JP C,_ms_read_timeout")
            if (main_sub_chr_text.count(M6IK_P1_OLD) != 1
                    or main_sub_chr_text.count(M6IK_R_OLD) != 1
                    or main_sub_chr_text.count(M6IK_ONCE_OLD) != 1):
                raise SystemExit("m6i-k 注入位置が一意でない")
            main_sub_chr_text = main_sub_chr_text.replace(M6IK_ONCE_OLD, "")
            main_sub_chr_text = main_sub_chr_text.replace(M6IK_P1_OLD, replacement)
            main_sub_chr_text = main_sub_chr_text.replace(
                M6IK_R_OLD, "    LD A,(MAIN_SUB_CHR_SECTOR)\n    " +
                ("INC A" if inject_m6ik_arm == "K-FR" else "NOP") +
                "\n    CALL MAIN_SUB_SEND_REQUEST_CONT")
        if chr_fault_enabled:
            main_sub_chr_path = work / "main_sub_read_chr_gen.asm"
            main_sub_chr_path.write_text(main_sub_chr_text, encoding="utf-8")
            combined += f'\nINCLUDE "{main_sub_chr_path}"\n'
        else:
            combined += f'\nINCLUDE "{MAIN_SUB_READ_CHR_ASM}"\n'
    return memmap.asm_prelude() + combined



# N88.ROM 0x79D7 は予約番地(FILLのまま固定する)。エミュレータ(QUASI88、
# vendor/quasi88-libretro/src/memory.h:48 の`ROM_VERSION main_rom[0x79d7]`)
# が、この1バイトを文字コードとして読み機種を切り替える('4'以上でV2既定・
# '8'以上でFH/MH相当のポート挙動、src/pc88main.c:1051・1393・1399・2688・
# 2698)。公式ROMの同じ番地の値は読まない・合わせない(禁止事項1-2の対象外の
# 話——これはエミュレータ側の実装の事実であって公式ROMの内部構造ではない)。
# これまでの適合テストは全て「この番地がFILLのまま(機種判定に既定値が
# 使われる)」状態で通っているため、コードが伸びてここへ命令の1バイトが
# 来ると機種が偶然変わり、原因の分かりにくい食い違いを生む。
ROM_VERSION_RESERVED_ADDR = 0x79D7
MAIN_SUB_LINK_MAX_SIZE = 1160


def assemble(text: str, work: pathlib.Path) -> "tuple[bytes, z80text.Assembler]":
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
    if rom[ROM_VERSION_RESERVED_ADDR] != FILL:
        raise SystemExit(
            f"ROM_VERSION予約番地0x{ROM_VERSION_RESERVED_ADDR:04X}が埋め草"
            f"(0x{FILL:02X})のままではない(0x{rom[ROM_VERSION_RESERVED_ADDR]:02X})。"
            "コード/表がここへ届き、QUASI88の機種判定(memory.h ROM_VERSION)が"
            "偶然変わってしまう。この番地の手前でレイアウトを分けること。"
        )
    link_start = asm.labels.get("MAIN_SUB_LINK_START")
    link_end = asm.labels.get("MAIN_SUB_LINK_END")
    if (link_start is None) != (link_end is None):
        raise SystemExit("main<->sub常駐部の境界ラベルが片方しかない")
    if link_start is not None:
        link_size = link_end - link_start
        if link_size > MAIN_SUB_LINK_MAX_SIZE:
            raise SystemExit(
                f"main<->sub常駐部が末尾空き1160Bを超えた: "
                f"{link_size} > {MAIN_SUB_LINK_MAX_SIZE}")
    check_ext_bank_relay_below_window(asm)
    check_ext_bank_callable_labels_below_window(asm)
    return bytes(rom), asm


def check_ext_bank_relay_below_window(asm: "z80text.Assembler"):
    """拡張ROMバンク: 中継ルーチン・割り込み処理が窓(0x6000-0x7FFF)の外に
    あることをビルド時に機械的に検査する(docs/spec/ext-rom-bank.md
    第2節 制約1・2)。ROM_VERSION予約番地の検査と同じ「落ちたら書き出さ
    ない」流儀。--inject-ext-bank-window-fault の陰性対照はここで落ちる
    ことを確かめる。
    """
    problems = []
    for name in EXT_BANK_INTERRUPT_SAFE_LABELS:
        addr = asm.labels.get(name)
        if addr is None:
            problems.append(f"{name}: ラベルが見つからない(ビルド構成が変わった？)")
            continue
        if addr >= EXT_BANK_WINDOW_START:
            problems.append(
                f"{name} が窓の中(0x{addr:04X} >= 0x{EXT_BANK_WINDOW_START:04X})にある")
    if problems:
        raise SystemExit(
            "拡張ROMバンク: 中継ルーチン/割り込み処理の配置検査に失敗"
            "(docs/spec/ext-rom-bank.md 第2節 制約1・2):\n  " + "\n  ".join(problems)
        )


def check_ext_bank_callable_labels_below_window(asm: "z80text.Assembler"):
    """拡張ROMバンク: バンク側ルーチンから1回CALLして戻ってよい常駐部
    ルーチン(EXT_BANK_CALLABLE_RESIDENT_LABELS)が窓(0x6000-0x7FFF)の外に
    あることをビルド時に機械的に検査する(docs/spec/ext-rom-bank.md 第2節
    制約3(a)、docs/notes/ext2-relay-to-resident-results.mdで測定済みの
    条件のうち機械的に検査できる部分)。check_ext_bank_relay_below_window()
    と同じ「落ちたら書き出さない」流儀。
    """
    problems = []
    for name in EXT_BANK_CALLABLE_RESIDENT_LABELS:
        addr = asm.labels.get(name)
        if addr is None:
            problems.append(f"{name}: ラベルが見つからない(mbf_single.asmが変わった？)")
            continue
        if addr >= EXT_BANK_WINDOW_START:
            problems.append(
                f"{name} が窓の中(0x{addr:04X} >= 0x{EXT_BANK_WINDOW_START:04X})にある。"
                "バンク側から呼んでよい常駐ルーチンの前提(制約3(a))が崩れている。")
    if problems:
        raise SystemExit(
            "拡張ROMバンク: バンクから呼んでよい常駐ルーチンの配置検査に失敗"
            "(docs/spec/ext-rom-bank.md 第2節 制約3(a)):\n  " + "\n  ".join(problems)
        )


def build_disk_rom(outdir: pathlib.Path, m6ib_arm: str | None = None,
                   inject_m6ie_single_read: bool = False,
                   inject_m6ie_nops_only: bool = False):
    cmd = [sys.executable, str(REPO / "src" / "l3_service" / "make_subrom.py"), str(outdir)]
    if m6ib_arm is not None:
        cmd.append(f"--inject-m6ib-{m6ib_arm.lower()}")
    if inject_m6ie_single_read:
        cmd.append("--inject-m6ie-single-read")
    if inject_m6ie_nops_only:
        cmd.append("--inject-m6ie-nops-only")
    subprocess.run(
        cmd,
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build_font_rom(outdir: pathlib.Path, unscii_hex: pathlib.Path, misaki_bdf: pathlib.Path):
    subprocess.run(
        [sys.executable, str(REPO / "src" / "l2_font" / "make_font_rom.py"), str(outdir),
         "--unscii-hex", str(unscii_hex), "--misaki-bdf", str(misaki_bdf)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build_ext_bank_roms(outdir: pathlib.Path, inject_no_org_fault: bool = False,
                         mbf_add_addr: int = None, addr_overrides: dict = None):
    """拡張ROMバンク N88_0.ROM〜N88_3.ROM(docs/spec/ext-rom-bank.md)。

    mbf_add_addr: 常駐部(N88.ROM)側のMBF_ADDの実アドレス。バンクは独立に
    アセンブルされる(make_ext_rom_banks.py)ため、bank0.asmの
    EXT_BANK0_MBF_TEST_ENTRY(「バンク0の試験ルーチンが常駐の単精度演算を
    呼んで正しい結果を返す」自己検査、docs/spec/ext-rom-bank.md 第2節
    制約3)が参照する絶対番地を、この実測値でテキスト置換する
    (--mbf-add-addr)。渡さない場合はbank0.asm既定値のまま(ズレていれば
    自己検査が不一致を検出する)。

    addr_overrides: 同じ手法の汎用版({EQU名: 実アドレス}、--addr NAME=0x..
    を複数渡す)。EXT_BANK0_SQR_ENTRYが参照するMBF_STOD_ADDR等に使う。
    """
    cmd = [sys.executable, str(REPO / "src" / "ext_bank" / "make_ext_rom_banks.py"), str(outdir)]
    if inject_no_org_fault:
        cmd.append("--inject-no-org-fault")
    if mbf_add_addr is not None:
        cmd += ["--mbf-add-addr", f"0x{mbf_add_addr:04X}"]
    if addr_overrides:
        for name, addr in addr_overrides.items():
            cmd += ["--addr", f"{name}=0x{addr:04X}"]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
    ap.add_argument("--inject-editkey-home-clr-fault", action="store_true",
                     help="故障注入: 第16節HOME/CLR(08H:0)のSHIFT分岐を反転する"
                          "（自己検査の陰性対照専用）")
    ap.add_argument("--inject-key-repeat-fault", action="store_true",
                     help="故障注入: 第4.2版第8節キーリピートの遅延を255フレームへ"
                          "引き伸ばし実質無効化する（自己検査の陰性対照専用）")
    ap.add_argument("--enable-l4-selftest", action="store_true",
                     help="ブート時にLEX_SELFTESTを呼ぶ（l3_main_selftest.shのL1タイミング検査を"
                          "壊すため既定offにしてある。tools/l4_basic_selftest.sh専用）")
    ap.add_argument("--enable-ext-bank-selftest", action="store_true",
                     help="ブート時にEXT_BANK_SELFTEST/EXT_BANK_LOOP_TESTを呼ぶ"
                          "（L1タイミング検査を壊すため既定offにしてある。"
                          "拡張ROMバンクの自己検査専用）")
    ap.add_argument("--inject-ext-bank-window-fault", action="store_true",
                     help="故障注入: 中継ルーチン(EXT_BANK_CALL)を窓(0x6000-0x7FFF)の中へ"
                          "INCLUDE順序ごと移し、ビルド時検査"
                          "(check_ext_bank_relay_below_window)が落ちることを確かめる"
                          "（自己検査の陰性対照専用）")
    ap.add_argument("--inject-ext-bank-bcde-fault", action="store_true",
                     help="故障注入: EXT_BANK_CALLがCALL EXT_BANK_JUMP_HLをまたいで"
                          "C(旧0x32)・E(旧0x71)をスタックへ退避する修正(2026-09-20、"
                          "l4-c8で見つかったSQRハングの修正)を外し、バンク側ルーチンが"
                          "BC/DEを使うと窓復元が壊れる修正前の状態を再現する"
                          "（自己検査の陰性対照専用。tools/l4_sqr_endtoend_selftest.sh）")
    ap.add_argument("--enable-vsync-regcheck", action="store_true",
                     help="ブート時にVSYNC_REGCHECKを呼ぶ（L1タイミング検査を壊すため既定offに"
                          "してある。VSYNCハンドラのレジスタ退避の自己検査専用）")
    ap.add_argument("--inject-vsync-no-save-fault", action="store_true",
                     help="故障注入: VSYNC_HANDLERのレジスタ退避(PUSH/POP)をNOPへ置き換え、"
                          "修正前の状態を再現する（自己検査の陰性対照専用）")
    ap.add_argument("--inject-ext-bank-no-org-fault", action="store_true",
                     help="故障注入: src/ext_bank/bank0.asmのORG 0x6000/0x6010を0始まりへ"
                          "書き換えて拡張ROMバンクを組み立てる"
                          "（自己検査の陰性対照専用。絶対番地参照がズレる）")
    ap.add_argument("--inject-ext-bank-mbf-addr-fault", action="store_true",
                     help="故障注入: bank0.asmへ渡すMBF_ADDの絶対番地を1バイトずらし、"
                          "EXT_BANK0_MBF_TEST_ENTRYが誤った番地をCALLするようにする"
                          "（自己検査の陰性対照専用）")
    ap.add_argument("--enable-main-sub-read", action="store_true",
                    help="検査用ビルドにmain<->sub通信と既知1セクタREAD入口を入れ、"
                         "定常状態でドライブAを1回読む（ルーチン自体は配布ビルドにも入る）")
    ap.add_argument("--enable-disk-read-retry", action="store_true",
                    help="検査用ビルドで既知1セクタREADを待ち・空送信なし、"
                         "失敗時1回だけ再試行する")
    ap.add_argument("--enable-disk-read-chr", action="store_true",
                    help="検査用ビルドで任意のドライブ・論理トラック・Rを読む入口と"
                         "再試行口を連結する")
    ap.add_argument("--disable-main-sub-read", action="store_true",
                    help="main<->sub READの3ルーチンをすべて配布ビルドから外す")
    ap.add_argument("--disable-disk-read-retry", action="store_true",
                    help="既知座標READの再試行ルーチンだけを配布ビルドから外す")
    ap.add_argument("--disable-disk-read-chr", action="store_true",
                    help="任意座標READとその再試行ルーチンだけを配布ビルドから外す")
    ap.add_argument("--inject-main-sub-wait-fault", action="store_true",
                    help="故障注入: SEND前のbit1待ちを反対(bit1=0)にする。"
                         "main-sub READを暗黙に有効化する")
    ap.add_argument("--inject-main-sub-cont-fault", action="store_true",
                    help="故障注入: 5位置すべてでOUT $FF,0Fを出す。"
                         "main-sub READを暗黙に有効化する")
    ap.add_argument("--inject-main-sub-pair-fault", action="store_true",
                    help="故障注入: 2位置PAIRを単発RECV 2回へ置換する。"
                         "main-sub READを暗黙に有効化する")
    ap.add_argument("--inject-m6ib-b1", action="store_true",
                    help="m6i-b B1: frame 60まで通信せず、subをリセット入口で停止する")
    ap.add_argument("--inject-m6ib-b2", action="store_true",
                    help="m6i-b B2: 起動専用RECV後、最初のFDC初期化I/O直前で停止する")
    ap.add_argument("--inject-m6ib-b3", action="store_true",
                    help="m6i-b B3: 起動専用RECVを保留してFDC初期化7 batch後に停止する")
    ap.add_argument("--inject-m6ib-b4", action="store_true",
                    help="m6i-b B4: 起動順b→a完了後、ラウンド#0前で停止する")
    ap.add_argument("--inject-m6ib-b5", action="store_true",
                    help="m6i-b B5: 起動順b→a→c完了後に停止する")
    ap.add_argument("--inject-m6ih-a", action="store_true",
                    help="m6i-h H-A: 起動専用SEND直後、固定待ちなしでREADする")
    ap.add_argument("--inject-m6ih-b", action="store_true",
                    help="m6i-h H-B: 固定待ちなしでREADし、失敗時だけ1回再試行する")
    ap.add_argument("--inject-m6ii-sweep", action="store_true",
                    help="m6i-i I-S: 任意座標READの登録済11行を起動時に掃引する")
    ap.add_argument("--inject-m6ii-fault-h", action="store_true",
                    help="m6i-i I-F-H: 論理トラックbit0を落とす")
    ap.add_argument("--inject-m6ii-fault-d", action="store_true",
                    help="m6i-i I-F-D: ドライブ選択を0に固定する")
    ap.add_argument("--inject-m6ii-fault-r", action="store_true",
                    help="m6i-i I-F-R: 送信するRに1を足す")
    ap.add_argument("--inject-m6ii-fault-retry", action="store_true",
                    help="m6i-i I-F-RETRY: 再試行口の入力A退避・復元を外す")
    ap.add_argument("--inject-m6ik-arm", choices=M6IK_ARMS,
                    help="m6i-k 測定専用の腕")
    ap.add_argument("--inject-m6ie-single-read", action="store_true",
                    help="m6i-e E2: B5と同じmainでsubへIN $FEとNOP 4個を挿入する")
    ap.add_argument("--inject-m6ie-nops-only", action="store_true",
                    help="m6i-e E3: B5と同じmainでsubへNOP 6個を挿入する")
    ap.add_argument("--work-dir", type=pathlib.Path, default=None,
                     help="中間.asmファイルの置き場（既定は一時ディレクトリ、後始末しない）")
    ap.add_argument("--unscii-hex", type=pathlib.Path,
                     default=REPO.parent / "vendor" / "unscii" / "unscii-8.hex")
    ap.add_argument("--misaki-bdf", type=pathlib.Path,
                     default=REPO.parent / "vendor" / "misaki" / "misaki_gothic.bdf")
    ap.add_argument("--keep-work", action="store_true",
                     help="--work-dir を指定しない場合でも中間ファイルを残す")
    args = ap.parse_args()

    m6ib_flags = (args.inject_m6ib_b1, args.inject_m6ib_b2,
                   args.inject_m6ib_b3, args.inject_m6ib_b4,
                   args.inject_m6ib_b5)
    m6ih_flags = (args.inject_m6ih_a, args.inject_m6ih_b)
    m6ii_fault_flags = (args.inject_m6ii_fault_h, args.inject_m6ii_fault_d,
                         args.inject_m6ii_fault_r, args.inject_m6ii_fault_retry)
    insertion_flags = (*m6ib_flags, *m6ih_flags, args.inject_m6ie_single_read,
                       args.inject_m6ie_nops_only, args.inject_m6ii_sweep,
                       args.inject_m6ik_arm is not None)
    if sum(bool(value) for value in insertion_flags) > 1:
        ap.error("m6i-b/m6i-e/m6i-h/m6i-iの挿入フラグは併用不可")
    if sum(bool(value) for value in m6ii_fault_flags) > 1:
        ap.error("m6i-iの故障注入は1種類だけ指定する")
    if any(m6ii_fault_flags) and not args.inject_m6ii_sweep:
        ap.error("m6i-iの故障注入は--inject-m6ii-sweepと併用する")
    m6ib_arm = next((arm for enabled, arm in zip(m6ib_flags,
                      ("B1", "B2", "B3", "B4", "B5"))
                      if enabled), None)
    main_sub_fault_enabled = (
        args.inject_main_sub_wait_fault or args.inject_main_sub_cont_fault
        or args.inject_main_sub_pair_fault or m6ib_arm is not None
        or any(m6ih_flags)
        or args.inject_m6ii_sweep or args.inject_m6ik_arm is not None
        or args.inject_m6ie_single_read or args.inject_m6ie_nops_only)
    if args.disable_main_sub_read and any((args.enable_main_sub_read,
                                           args.enable_disk_read_retry,
                                           args.enable_disk_read_chr,
                                           main_sub_fault_enabled)):
        ap.error("--disable-main-sub-readはmain-sub READの検査用有効化と併用不可")
    if args.disable_disk_read_retry and args.enable_disk_read_retry:
        ap.error("--disable-disk-read-retryと--enable-disk-read-retryは併用不可")
    if args.disable_disk_read_chr and (args.enable_disk_read_chr or args.inject_m6ii_sweep
                                      or args.inject_m6ik_arm is not None):
        ap.error("--disable-disk-read-chrは一般READの検査用有効化と併用不可")
    if args.enable_disk_read_retry and any((*m6ib_flags, *m6ih_flags)):
        ap.error("--enable-disk-read-retryはm6i-b/m6i-hの挿入フラグと併用不可")
    # 無指定の配布ビルドには3ルーチンを常駐させる。ただし --enable-* と
    # m6i故障注入は、既存の測定成果物を再生成するための「起動時にREADする」
    # 専用構成なので、従来どおり指定されたルーチンだけを連結する。
    main_sub_measure_build = any((args.enable_main_sub_read,
                                  args.enable_disk_read_retry,
                                  args.enable_disk_read_chr,
                                  main_sub_fault_enabled))
    if main_sub_measure_build:
        enable_disk_read_retry = args.enable_disk_read_retry
        enable_disk_read_chr = (args.enable_disk_read_chr or args.inject_m6ii_sweep
                                or args.inject_m6ik_arm is not None)
        enable_main_sub_read = True
    else:
        enable_main_sub_read = not args.disable_main_sub_read
        enable_disk_read_retry = (enable_main_sub_read
                                  and not args.disable_disk_read_retry)
        enable_disk_read_chr = (enable_main_sub_read
                                and not args.disable_disk_read_chr)

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
                                       inject_editkey_home_clr_fault=args.inject_editkey_home_clr_fault,
                                       inject_key_repeat_fault=args.inject_key_repeat_fault,
                                       enable_l4_selftest=args.enable_l4_selftest,
                                       enable_ext_bank_selftest=args.enable_ext_bank_selftest,
                                       inject_ext_bank_window_fault=args.inject_ext_bank_window_fault,
                                       inject_ext_bank_bcde_fault=args.inject_ext_bank_bcde_fault,
                                       enable_vsync_regcheck=args.enable_vsync_regcheck,
                                       inject_vsync_no_save_fault=args.inject_vsync_no_save_fault,
                                       enable_main_sub_read=enable_main_sub_read,
                                       enable_disk_read_retry=enable_disk_read_retry,
                                       enable_disk_read_chr=enable_disk_read_chr,
                                       enable_main_sub_boot=main_sub_measure_build,
                                       inject_main_sub_wait_fault=args.inject_main_sub_wait_fault,
                                       inject_main_sub_cont_fault=args.inject_main_sub_cont_fault,
                                       inject_main_sub_pair_fault=args.inject_main_sub_pair_fault,
                                       inject_m6ib_b1=args.inject_m6ib_b1,
                                       inject_m6ib_b2=args.inject_m6ib_b2,
                                       inject_m6ib_b3=args.inject_m6ib_b3,
                                       inject_m6ib_b4=args.inject_m6ib_b4,
                                       inject_m6ib_b5=(args.inject_m6ib_b5
                                                        or args.inject_m6ie_single_read
                                                        or args.inject_m6ie_nops_only),
                                       inject_m6ih_a=args.inject_m6ih_a,
                                       inject_m6ih_b=args.inject_m6ih_b,
                                       inject_m6ii_sweep=args.inject_m6ii_sweep,
                                       inject_m6ii_fault_h=args.inject_m6ii_fault_h,
                                       inject_m6ii_fault_d=args.inject_m6ii_fault_d,
                                       inject_m6ii_fault_r=args.inject_m6ii_fault_r,
                                       inject_m6ii_fault_retry=args.inject_m6ii_fault_retry,
                                       inject_m6ik_arm=args.inject_m6ik_arm)
        rom, asm = assemble(combined, work)

        args.outdir.mkdir(parents=True, exist_ok=True)
        (args.outdir / "N88.ROM").write_bytes(rom)
        build_disk_rom(args.outdir, m6ib_arm=m6ib_arm,
                       inject_m6ie_single_read=args.inject_m6ie_single_read,
                       inject_m6ie_nops_only=args.inject_m6ie_nops_only)
        build_font_rom(args.outdir, args.unscii_hex, args.misaki_bdf)
        mbf_add_addr = asm.labels.get("MBF_ADD")
        if args.inject_ext_bank_mbf_addr_fault and mbf_add_addr is not None:
            # 故障注入(自己検査の陰性対照専用): わざとMBF_SUBの番地を渡し、
            # bank0.asmのEXT_BANK0_MBF_TEST_ENTRYが「1.0+2.0のつもりで
            # 実際にはMBF_SUB(1.0-2.0=-1.0)」を呼ぶことになる(密結合が
            # ズレた場合の検出力の確認。1バイトずらす程度では、たまたま
            # ズレた番地の先も有効な同等コード列に再収束して結果が変わらない
            # ことがあると実測で分かったため、別ルーチンへ丸ごと誤って
            # 結びつく場合で検出力を確かめる)。
            mbf_sub_addr = asm.labels.get("MBF_SUB")
            if mbf_sub_addr is not None:
                mbf_add_addr = mbf_sub_addr
        addr_overrides = {}
        for eqname, label in EXT_BANK0_SQR_ADDR_LABELS.items():
            addr = asm.labels.get(label)
            if addr is not None:
                addr_overrides[eqname] = addr
        for eqname, label in EXT_BANK0_SINCOS_ADDR_LABELS.items():
            addr = asm.labels.get(label)
            if addr is not None:
                addr_overrides[eqname] = addr
        for eqname, label in (EXT_BANK0_ATNEXPLOG_ADDR_LABELS |
                              EXT_BANK0_DEFFN_ADDR_LABELS).items():
            addr = asm.labels.get(label)
            if addr is not None:
                addr_overrides[eqname] = addr
        for eqname, label in EXT_BANK1_MAIN_ADDR_LABELS.items():
            addr = asm.labels.get(label)
            # READ無効構成など、呼び先を意図的に組まない構成がある。番地の
            # ずれは make_ext_rom_banks の不一致検査で止める。
            if addr is not None:
                addr_overrides[eqname] = addr
        for eqname, label in EXT_BANK2_MAIN_ADDR_LABELS.items():
            addr = asm.labels.get(label)
            if addr is not None:
                addr_overrides[eqname] = addr
        for eqname, label in EXT_BANK3_MAIN_ADDR_LABELS.items():
            addr = asm.labels.get(label)
            if addr is not None:
                addr_overrides[eqname] = addr
        build_ext_bank_roms(args.outdir, inject_no_org_fault=args.inject_ext_bank_no_org_fault,
                             mbf_add_addr=mbf_add_addr, addr_overrides=addr_overrides)

        used = len(combined.splitlines())
        print(f"生成した: {args.outdir} (N88.ROM {N88_SIZE} bytes / DISK.ROM / FONT.ROM / "
              f"N88_0.ROM〜N88_3.ROM 各0x2000 bytes)")
        print(f"  組み合わせ.asm行数={used} extra_lines={args.extra_lines} "
              f"inject_address_fault={args.inject_address_fault} "
              f"inject_cursor_fault={args.inject_cursor_fault}")
    finally:
        if cleanup:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
