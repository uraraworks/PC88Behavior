; files.asm — FILES文の構文入口と拡張ROMバンク1への中継。
;
; 表示・媒体規則は docs/spec/l4-basic.md 第11節、
; docs/spec/l3-disk-format.md 第1〜2節、80桁折返しは
; docs/spec/l3-main.md 第15.1節に従う。セクタREADは配布ビルドに連結済みの
; MAIN_SUB_READ_CHR_RETRYを使う。起動時のREADや初期化は追加しない。
;
; 拡張ROMバンク有効中は0x6000-0x7FFFのmain側コードが見えないため、
; バンク1本体は「READ要求」「16桁セル出力要求」「改行要求」をRAMへ置いて
; RETする状態機械にした。本常駐側はEXT_BANK_CALLが窓をmainへ戻した後だけ
; MAIN_SUB_READ_CHR_RETRY/PRINT_CHAR/NEWLINEを呼ぶ。従って中継の再入も、
; バンク有効中の窓内main呼出しも起こさない（ext-rom-bank.md 第2節）。
;
; RAM配置（実装上の判断）:
;   DF00-DFFF はmain_sub_read.asm既存の256B受信バッファを、その時点の
;   ディレクトリセクタとして共有する。新規の256BバッファはFAT保存用の
;   E100-E1FFだけである。E000-E00Fはmain-sub印、E800以降は画面/L4、
;   C000-DEBFは数値・RUN、EA00-EDFFはプログラム、SPはF000から下向きで
;   使用済みであり、src/のEQU棚卸しでE100-E21Fに既存割当が無いことを
;   確認した。E200-E20Fを16桁セル、E210-E21Fを状態・一時値に使う。

FILES_FAT_BUF       EQU 0E100h ; 256B、割り当て表(18,1,14)の写し
FILES_CELL_BUF      EQU 0E200h ; 16B、画面へ出す固定幅セル
FILES_PHASE         EQU 0E210h
FILES_DRIVE         EQU 0E211h ; 0=A、1=B（MAIN_SUB入力bit0）
FILES_READ_TRACK    EQU 0E212h
FILES_READ_SECTOR   EQU 0E213h
FILES_READ_OK       EQU 0E214h
FILES_DIR_SECTOR    EQU 0E215h
FILES_ENTRY_INDEX   EQU 0E216h
FILES_ENTRY_COUNT   EQU 0E217h
FILES_CHAIN_GUARD   EQU 0E218h
FILES_SIZE_VALUE    EQU 0E219h
FILES_DEC_STARTED   EQU 0E21Ah

FILES_BANK_ENTRY    EQU 06110h ; src/ext_bank/bank1.asmの固定入口
FILES_ACT_DONE      EQU 0
FILES_ACT_READ      EQU 1
FILES_ACT_CELL      EQU 2
FILES_ACT_NEWLINE   EQU 3

; FILES_STMT — FILES [式]。省略時は1、1/2以外はERR 70、文字列はERR 13。
; 直接モードとプログラム実行の両方がこの同じ入口を使う。
FILES_STMT:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,_files_default_drive
    CP ':'
    JR Z,_files_default_drive
    CP '"'
    JR Z,_files_type_error
    ; `$`型の変数・文字列関数は数値式へ渡す前にERR 13へする。
    CALL LEX_IDENT_PEEK
    CP 3
    JR Z,_files_type_error
    CALL PARSE_INT_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,D
    OR A
    JR NZ,_files_drive_error
    LD A,E
    CP 1
    JR Z,_files_drive_one
    CP 2
    JR NZ,_files_drive_error
    LD A,1
    JR _files_start
_files_default_drive:
_files_drive_one:
    XOR A
_files_start:
    LD (FILES_DRIVE),A
    XOR A
    LD (FILES_PHASE),A
    LD (FILES_READ_OK),A

; バンク本体は1回につき1つの外部動作だけを要求して戻る。
_files_dispatch:
    LD A,1
    LD HL,FILES_BANK_ENTRY
    CALL EXT_BANK_CALL
    CP FILES_ACT_READ
    JR Z,_files_do_read
    CP FILES_ACT_CELL
    JR Z,_files_do_cell
    CP FILES_ACT_NEWLINE
    JR Z,_files_do_newline
    XOR A
    LD (ERROR_FLAG),A
    RET

_files_do_read:
    LD A,(FILES_DRIVE)
    PUSH AF
    LD A,(FILES_READ_TRACK)
    LD D,A
    LD A,(FILES_READ_SECTOR)
    LD E,A
    POP AF
    CALL MAIN_SUB_READ_CHR_RETRY
    LD A,0
    JR C,_files_read_record
    INC A
_files_read_record:
    LD (FILES_READ_OK),A
    JR _files_dispatch

_files_do_cell:
    LD HL,FILES_CELL_BUF
    LD B,16
_files_cell_loop:
    LD A,(HL)
    INC HL
    PUSH HL
    ; 通常のPRINT_CHARはBを触らないが、画面下端ではNEWLINE→SCROLLが
    ; B/Cを作業用に使う。ここで保存しないと、そのときだけDJNZが0から
    ; 255へ巻き戻り、セル外を余分に出力してしまう。
    PUSH BC
    CALL PRINT_CHAR
    POP BC
    POP HL
    DJNZ _files_cell_loop
    JR _files_dispatch

_files_do_newline:
    CALL NEWLINE
    JR _files_dispatch

_files_type_error:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,13
    LD (ERROR_KIND),A
    RET

_files_drive_error:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,70
    LD (ERROR_KIND),A
    RET
