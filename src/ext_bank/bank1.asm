; src/ext_bank/bank1.asm — 拡張ROMバンク1(N88_1.ROM)。
;
; 0x6000の試験入口は既存の拡張バンク自己検査用。0x6110からは
; docs/spec/l4-basic.md 第11節のFILES本体（ディレクトリ解釈・FAT鎖の
; 単位数・16桁セル組立て）を置く。READと画面出力はバンク有効中に
; main側の窓内コードを呼べないため、共有RAMへ動作要求を置いてRETし、
; src/l4_basic/files.asmがEXT_BANK_CALL復帰後に実行する。

    ORG 0x6000
EXT_BANK1_TEST_ENTRY:
    LD A,0xB1
    RET

    ORG 0x6110

MAIN_SUB_SECTOR_BUF EQU MM_MAIN_SUB_SECTOR_BUF
FILES_FAT_BUF       EQU MM_FILES_FAT_BUF
FILES_CELL_BUF      EQU MM_FILES_CELL_BUF
FILES_PHASE         EQU MM_FILES_PHASE
FILES_READ_TRACK    EQU MM_FILES_READ_TRACK
FILES_READ_SECTOR   EQU MM_FILES_READ_SECTOR
FILES_READ_OK       EQU MM_FILES_READ_OK
FILES_DIR_SECTOR    EQU MM_FILES_DIR_SECTOR
FILES_ENTRY_INDEX   EQU MM_FILES_ENTRY_INDEX
FILES_ENTRY_COUNT   EQU MM_FILES_ENTRY_COUNT
FILES_CHAIN_GUARD   EQU MM_FILES_CHAIN_GUARD
FILES_SIZE_VALUE    EQU MM_FILES_SIZE_VALUE
FILES_DEC_STARTED   EQU MM_FILES_DEC_STARTED

FILES_ACT_DONE      EQU 0
FILES_ACT_READ      EQU 1
FILES_ACT_CELL      EQU 2
FILES_ACT_NEWLINE   EQU 3

; phase 0: FATを要求、1: FATを保存して最初のディレクトリを要求、
; 2: ディレクトリエントリを順に処理、3: 最後の改行後に完了。
EXT_BANK1_FILES_ENTRY:
    LD A,(FILES_PHASE)
    OR A
    JP Z,_fb_init
    CP 1
    JP Z,_fb_have_fat
    CP 2
    JP Z,_fb_scan_dir
    XOR A
    RET

_fb_init:
    LD A,1
    LD (FILES_PHASE),A
    LD A,37                 ; C=18,H=1 -> C*2+H
    LD (FILES_READ_TRACK),A
    LD A,14                 ; FAT3複製は同一。先頭1セクタだけ読む
    LD (FILES_READ_SECTOR),A
    LD A,1
    LD (FILES_DIR_SECTOR),A
    XOR A
    LD (FILES_ENTRY_INDEX),A
    LD (FILES_ENTRY_COUNT),A
    LD A,FILES_ACT_READ
    RET

_fb_have_fat:
    LD A,(FILES_READ_OK)
    OR A
    JP Z,_fb_done
    LD HL,MAIN_SUB_SECTOR_BUF
    LD DE,FILES_FAT_BUF
    LD BC,256
    LDIR
    LD A,2
    LD (FILES_PHASE),A
    LD A,37
    LD (FILES_READ_TRACK),A
    LD A,(FILES_DIR_SECTOR)
    LD (FILES_READ_SECTOR),A
    LD A,FILES_ACT_READ
    RET

_fb_scan_dir:
    LD A,(FILES_READ_OK)
    OR A
    JP Z,_fb_done
    LD A,(FILES_ENTRY_INDEX)
    CP 16
    JP C,_fb_have_entry
    LD A,(FILES_DIR_SECTOR)
    INC A
    LD (FILES_DIR_SECTOR),A
    CP 13
    JP NC,_fb_finish
    XOR A
    LD (FILES_ENTRY_INDEX),A
    LD A,37
    LD (FILES_READ_TRACK),A
    LD A,(FILES_DIR_SECTOR)
    LD (FILES_READ_SECTOR),A
    LD A,FILES_ACT_READ
    RET

_fb_have_entry:
    ; IX = DF00 + entry_index*16
    LD L,A
    LD H,0
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    LD DE,MAIN_SUB_SECTOR_BUF
    ADD HL,DE
    PUSH HL
    POP IX
    LD A,(IX+0)
    CP 0FFh
    JP Z,_fb_finish
    OR A
    JP Z,_fb_skip_entry

    ; 16桁セルを先に空白で埋める。
    LD HL,FILES_CELL_BUF
    LD B,16
    LD A,' '
_fb_clear_cell:
    LD (HL),A
    INC HL
    DJNZ _fb_clear_cell

    ; 名前6、印、拡張子3。docs/spec/l4-basic.md第3.12版11.1節規則3:
    ; 0x80(SAVE)・0xA0(SAVE ,P)はピリオド、0x00(データ・SAVE ,A)は
    ; 初期空白のまま、0x01(BSAVE)はアスタリスク（0xA0・0x01はm6f-g）。
    ; それ以外の値の印は第11.3節のとおり未確定なので、現状どおり空白。
    PUSH IX
    POP HL
    LD DE,FILES_CELL_BUF
    LD B,6
_fb_copy_name:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _fb_copy_name
    LD A,(IX+9)
    CP 080h
    JP Z,_fb_mark_period
    CP 0A0h
    JP Z,_fb_mark_period
    CP 001h
    JP Z,_fb_mark_asterisk
    JP _fb_copy_ext
_fb_mark_period:
    LD A,'.'
    LD (FILES_CELL_BUF+6),A
    JP _fb_copy_ext
_fb_mark_asterisk:
    LD A,'*'
    LD (FILES_CELL_BUF+6),A
_fb_copy_ext:
    PUSH IX
    POP HL
    LD DE,6
    ADD HL,DE
    LD DE,FILES_CELL_BUF+7
    LD B,3
_fb_copy_ext_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _fb_copy_ext_loop

    ; エントリ10バイト目の先頭単位から、T[k]<160の間だけ次をたどる。
    ; 壊れた循環鎖は第11.3節で未確定なので、媒体外へ暴走しないよう
    ; 160単位で打ち切る（正しい媒体では終端0xC1〜0xC8が先に来る）。
    LD C,(IX+10)
    LD B,0
    LD A,160
    LD (FILES_CHAIN_GUARD),A
_fb_chain_loop:
    INC B
    LD A,(FILES_CHAIN_GUARD)
    DEC A
    LD (FILES_CHAIN_GUARD),A
    JP Z,_fb_chain_done
    LD A,C
    LD L,A
    LD H,0
    LD DE,FILES_FAT_BUF
    ADD HL,DE
    LD A,(HL)
    LD C,A
    CP 160
    JP C,_fb_chain_loop
_fb_chain_done:
    LD A,B
    LD (FILES_SIZE_VALUE),A

    ; 大きさを最小桁数の10進でセル11桁目から置く（最大160）。
    LD HL,FILES_CELL_BUF+11
    XOR A
    LD (FILES_DEC_STARTED),A
    LD A,(FILES_SIZE_VALUE)
    LD C,0
_fb_hundreds:
    CP 100
    JP C,_fb_hundreds_done
    SUB 100
    INC C
    JP _fb_hundreds
_fb_hundreds_done:
    LD B,A
    LD A,C
    OR A
    JP Z,_fb_tens_start
    ADD A,'0'
    LD (HL),A
    INC HL
    LD A,1
    LD (FILES_DEC_STARTED),A
_fb_tens_start:
    LD A,B
    LD C,0
_fb_tens:
    CP 10
    JP C,_fb_tens_done
    SUB 10
    INC C
    JP _fb_tens
_fb_tens_done:
    LD B,A
    LD A,C
    OR A
    JP NZ,_fb_emit_tens
    LD A,(FILES_DEC_STARTED)
    OR A
    JP Z,_fb_emit_ones
    XOR A
_fb_emit_tens:
    ADD A,'0'
    LD (HL),A
    INC HL
_fb_emit_ones:
    LD A,B
    ADD A,'0'
    LD (HL),A

    LD A,(FILES_ENTRY_INDEX)
    INC A
    LD (FILES_ENTRY_INDEX),A
    LD A,(FILES_ENTRY_COUNT)
    INC A
    LD (FILES_ENTRY_COUNT),A
    LD A,FILES_ACT_CELL
    RET

_fb_skip_entry:
    LD A,(FILES_ENTRY_INDEX)
    INC A
    LD (FILES_ENTRY_INDEX),A
    JP _fb_scan_dir

_fb_finish:
    LD A,(FILES_ENTRY_COUNT)
    OR A
    JP Z,_fb_done
    LD A,3
    LD (FILES_PHASE),A
    LD A,FILES_ACT_NEWLINE
    RET

_fb_done:
    XOR A
    RET

; LOAD状態機械。1=READ要求、2=名前発見(常駐側でNEW)、3=行登録、
; 4=名前なし、5=種別不適、6=READ失敗、0=正常終了。
; FILESと同じDF00受信/E100 FAT写しを使い、main側の関数は呼ばない。
    ORG 0x6400
LOAD_PHASE       EQU MM_LOAD_PHASE
LOAD_NAME        EQU MM_LOAD_NAME
LOAD_READ_TRACK  EQU MM_LOAD_READ_TRACK
LOAD_READ_SECTOR EQU MM_LOAD_READ_SECTOR
LOAD_READ_OK     EQU MM_LOAD_READ_OK
LOAD_DIR_SECTOR  EQU MM_LOAD_DIR_SECTOR
LOAD_ENTRY_INDEX EQU MM_LOAD_ENTRY_INDEX
LOAD_UNIT        EQU MM_LOAD_UNIT
LOAD_UNIT_SECTOR EQU MM_LOAD_UNIT_SECTOR
LOAD_BYTE_OFFSET EQU MM_LOAD_BYTE_OFFSET
LOAD_LINE_LEN    EQU MM_LOAD_LINE_LEN
LOAD_SKIP_LF     EQU MM_LOAD_SKIP_LF
LOAD_CHAIN_GUARD EQU MM_LOAD_CHAIN_GUARD
LOAD_LINE_BUF    EQU MM_LINE_BUF

EXT_BANK1_LOAD_ENTRY:
    LD A,(LOAD_PHASE)
    OR A
    JP Z,_lb_init
    CP 1
    JP Z,_lb_have_fat
    CP 2
    JP Z,_lb_scan
    CP 3
    JP Z,_lb_schedule
    JP _lb_consume

_lb_init:
    LD A,1
    LD (LOAD_PHASE),A
    LD A,37
    LD (LOAD_READ_TRACK),A
    LD A,14
    LD (LOAD_READ_SECTOR),A
    LD A,1
    LD (LOAD_DIR_SECTOR),A
    XOR A
    LD (LOAD_ENTRY_INDEX),A
    LD A,1
    RET

_lb_have_fat:
    LD A,(LOAD_READ_OK)
    OR A
    JP Z,_lb_io_error
    LD HL,MAIN_SUB_SECTOR_BUF
    LD DE,FILES_FAT_BUF
    LD BC,256
    LDIR
    LD A,2
    LD (LOAD_PHASE),A
    JP _lb_request_dir

_lb_request_dir:
    LD A,37
    LD (LOAD_READ_TRACK),A
    LD A,(LOAD_DIR_SECTOR)
    LD (LOAD_READ_SECTOR),A
    LD A,1
    RET

_lb_scan:
    LD A,(LOAD_READ_OK)
    OR A
    JP Z,_lb_io_error
_lb_scan_next:
    LD A,(LOAD_ENTRY_INDEX)
    CP 16
    JR C,_lb_entry
    LD A,(LOAD_DIR_SECTOR)
    INC A
    LD (LOAD_DIR_SECTOR),A
    CP 13
    JP NC,_lb_not_found
    XOR A
    LD (LOAD_ENTRY_INDEX),A
    JP _lb_request_dir
_lb_entry:
    LD L,A
    LD H,0
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    LD DE,MAIN_SUB_SECTOR_BUF
    ADD HL,DE
    PUSH HL
    POP IX
    LD A,(IX+0)
    CP 0FFh
    JP Z,_lb_not_found
    OR A
    JR Z,_lb_next_entry
    PUSH IX
    POP HL
    LD DE,LOAD_NAME
    LD B,9
_lb_cmp_name:
    LD A,(DE)
    CP (HL)
    JR NZ,_lb_next_entry
    INC HL
    INC DE
    DJNZ _lb_cmp_name
    LD A,(IX+9)
    OR A
    JP NZ,_lb_wrong_type
    LD A,(IX+10)
    LD (LOAD_UNIT),A
    XOR A
    LD (LOAD_UNIT_SECTOR),A
    LD (LOAD_BYTE_OFFSET),A
    LD (LOAD_LINE_LEN),A
    LD (LOAD_SKIP_LF),A
    LD A,160
    LD (LOAD_CHAIN_GUARD),A
    LD A,3
    LD (LOAD_PHASE),A
    LD A,2
    RET
_lb_next_entry:
    LD A,(LOAD_ENTRY_INDEX)
    INC A
    LD (LOAD_ENTRY_INDEX),A
    JP _lb_scan_next

_lb_schedule:
    LD A,(LOAD_UNIT)
    CP 160
    JP NC,_lb_io_error
    LD L,A
    LD H,0
    LD DE,FILES_FAT_BUF
    ADD HL,DE
    LD C,(HL)             ; C=T[unit]
    LD A,(LOAD_UNIT_SECTOR)
    CP 8
    JR C,_lb_same_unit
    LD A,C
    CP 160
    JP NC,_lb_done
    LD (LOAD_UNIT),A
    XOR A
    LD (LOAD_UNIT_SECTOR),A
    LD A,(LOAD_CHAIN_GUARD)
    DEC A
    LD (LOAD_CHAIN_GUARD),A
    JP Z,_lb_io_error
    JP _lb_schedule
_lb_same_unit:
    LD B,A
    LD A,C
    CP 0C0h
    JR C,_lb_track
    CP 0C9h
    JP NC,_lb_io_error
    SUB 0C0h
    CP B
    JP Z,_lb_done
    JP C,_lb_done
_lb_track:
    LD A,(LOAD_UNIT)
    SRL A                 ; unit/2 = C*2+H
    LD (LOAD_READ_TRACK),A
    LD A,(LOAD_UNIT)
    AND 1
    RLCA
    RLCA
    RLCA                   ; 0/8
    LD C,A
    LD A,(LOAD_UNIT_SECTOR)
    ADD A,C
    INC A
    LD (LOAD_READ_SECTOR),A
    LD A,4
    LD (LOAD_PHASE),A
    LD A,1
    RET

_lb_consume:
    LD A,(LOAD_READ_OK)
    OR A
    JP Z,_lb_io_error
_lb_byte:
    LD A,(LOAD_BYTE_OFFSET)
    LD L,A
    LD H,0
    LD DE,MAIN_SUB_SECTOR_BUF
    ADD HL,DE
    LD C,(HL)
    LD A,(LOAD_BYTE_OFFSET)
    INC A
    LD (LOAD_BYTE_OFFSET),A
    LD A,(LOAD_SKIP_LF)
    OR A
    JR Z,_lb_regular
    XOR A
    LD (LOAD_SKIP_LF),A
    LD A,C
    CP 0Ah
    JR Z,_lb_advance_byte
_lb_regular:
    LD A,C
    CP 01Ah
    JP Z,_lb_done
    CP 0Dh
    JR Z,_lb_line
    LD A,(LOAD_LINE_LEN)
    CP 80
    JP NC,_lb_io_error
    LD L,A
    LD H,0
    LD DE,LOAD_LINE_BUF
    ADD HL,DE
    LD (HL),C
    LD A,(LOAD_LINE_LEN)
    INC A
    LD (LOAD_LINE_LEN),A
_lb_advance_byte:
    LD A,(LOAD_BYTE_OFFSET)
    OR A
    JP NZ,_lb_byte
    LD A,(LOAD_UNIT_SECTOR)
    INC A
    LD (LOAD_UNIT_SECTOR),A
    LD A,3
    LD (LOAD_PHASE),A
    JP _lb_schedule
_lb_line:
    LD A,1
    LD (LOAD_SKIP_LF),A
    LD A,(LOAD_BYTE_OFFSET)
    OR A
    JR NZ,_lb_line_ready
    LD A,(LOAD_UNIT_SECTOR)
    INC A
    LD (LOAD_UNIT_SECTOR),A
    LD A,3
    LD (LOAD_PHASE),A
_lb_line_ready:
    LD A,3
    RET

_lb_not_found:
    LD A,4
    RET
_lb_wrong_type:
    LD A,5
    RET
_lb_io_error:
    LD A,6
    RET
_lb_done:
    XOR A
    RET

; FILES/LOAD のRAM作業域とmain常駐部の共有引数。
FILES_DRIVE EQU MM_FILES_DRIVE
LOAD_NAME_LEN EQU MM_LOAD_NAME_LEN
LOAD_DRIVE EQU MM_LOAD_DRIVE
B1_ERROR_FLAG EQU MM_ERROR_FLAG
B1_ERROR_KIND EQU MM_ERROR_KIND
B1_RUN_CTRL EQU MM_RUN_CTRL
B1_VAR_LINELEN EQU MM_VAR_LINELEN
B1_LINE_BUF EQU MM_LINE_BUF
B1_RUN_ERROR_HANDLER_LINE EQU MM_RUN_ERROR_HANDLER_LINE
B1_RUN_ERROR_ACTIVE EQU MM_RUN_ERROR_ACTIVE
LOAD_BANK_ENTRY EQU 06400h

    ORG 0x6600
EXT_BANK1_FILES_COMMAND:
    CALL _b1_call_skip_spaces
    CALL _b1_call_peek_char
    OR A
    JR Z,_files_default_drive
    CP ':'
    JR Z,_files_default_drive
    CP '"'
    JR Z,_files_type_error
    ; `$`型の変数・文字列関数は数値式へ渡す前にERR 13へする。
    CALL _b1_call_lex_ident_peek
    CP 3
    JR Z,_files_type_error
    CALL _b1_call_parse_int_arg
    LD A,(B1_ERROR_FLAG)
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
    CALL EXT_BANK1_FILES_ENTRY
    CP FILES_ACT_READ
    JR Z,_files_do_read
    CP FILES_ACT_CELL
    JR Z,_files_do_cell
    CP FILES_ACT_NEWLINE
    JR Z,_files_do_newline
    XOR A
    LD (B1_ERROR_FLAG),A
    RET

_files_do_read:
    LD A,(FILES_DRIVE)
    PUSH AF
    LD A,(FILES_READ_TRACK)
    LD D,A
    LD A,(FILES_READ_SECTOR)
    LD E,A
    POP AF
    CALL _b1_call_read_chr
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
    CALL _b1_call_print_char
    POP BC
    POP HL
    DJNZ _files_cell_loop
    JR _files_dispatch

_files_do_newline:
    CALL _b1_call_newline
    JR _files_dispatch

_files_type_error:
    LD A,1
    LD (B1_ERROR_FLAG),A
    LD A,13
    LD (B1_ERROR_KIND),A
    RET

_files_drive_error:
    LD A,1
    LD (B1_ERROR_FLAG),A
    LD A,70
    LD (B1_ERROR_KIND),A
    RET

    ORG 0x6800
EXT_BANK1_LOAD_COMMAND:
    CALL _b1_call_skip_spaces
    CALL _b1_call_peek_char
    CP '"'
    JP NZ,_load_syntax
    CALL _b1_call_adv_ptr
    CALL _b1_call_peek_char
    CP '1'
    JR Z,_load_drive1
    CP '2'
    JP NZ,_load_syntax
    LD A,1
    JR _load_drive_set
_load_drive1:
    XOR A
_load_drive_set:
    LD (LOAD_DRIVE),A
    CALL _b1_call_adv_ptr
    CALL _b1_call_peek_char
    CP ':'
    JP NZ,_load_syntax
    CALL _b1_call_adv_ptr
    LD HL,LOAD_NAME
    LD B,9
    LD A,' '
_load_pad:
    LD (HL),A
    INC HL
    DJNZ _load_pad
    XOR A
    LD (LOAD_NAME_LEN),A
_load_name_loop:
    CALL _b1_call_at_end
    JP Z,_load_syntax
    CALL _b1_call_peek_char
    CP '"'
    JR Z,_load_name_end
    PUSH AF
    LD A,(LOAD_NAME_LEN)
    CP 9
    JR NC,_load_name_too_long
    LD E,A
    LD D,0
    LD HL,LOAD_NAME
    ADD HL,DE
    POP AF
    LD (HL),A
    LD A,E
    INC A
    LD (LOAD_NAME_LEN),A
    CALL _b1_call_adv_ptr
    JR _load_name_loop
_load_name_too_long:
    POP AF
    JP _load_syntax
_load_name_end:
    LD A,(LOAD_NAME_LEN)
    OR A
    JP Z,_load_syntax
    CALL _b1_call_adv_ptr
    XOR A
    LD (LOAD_PHASE),A
    LD (LOAD_READ_OK),A
_load_dispatch:
    CALL EXT_BANK1_LOAD_ENTRY
    CP 1
    JR Z,_load_read
    CP 2
    JR Z,_load_found
    CP 3
    JP Z,_load_line
    CP 4
    JP Z,_load_not_found
    CP 5
    JP Z,_load_wrong_type
    CP 6
    JP Z,_load_disk_error
    ; 通常完了。LINE_FINISH側の通常のOkに先立ち、LOAD自身のOkを出す。
    LD HL,BANK1_OK_TXT_ADDR
    CALL _b1_call_print_str
    CALL _b1_call_newline
    XOR A
    LD (B1_ERROR_FLAG),A
    LD A,2
    LD (B1_RUN_CTRL),A
    RET
_load_read:
    LD A,(LOAD_DRIVE)
    PUSH AF
    LD A,(LOAD_READ_TRACK)
    LD D,A
    LD A,(LOAD_READ_SECTOR)
    LD E,A
    POP AF
    CALL _b1_call_read_chr
    LD A,0
    JR C,_load_read_record
    INC A
_load_read_record:
    LD (LOAD_READ_OK),A
    JR _load_dispatch
_load_found:
    CALL _b1_call_program_clear
    ; NEW相当。消えたON ERRORの捕捉先と実行中の行番号を参照しない。
    LD HL,0
    LD (B1_RUN_ERROR_HANDLER_LINE),HL
    XOR A
    LD (B1_RUN_ERROR_ACTIVE),A
    JP _load_dispatch

; 0x79D7前の空きへ置くLOAD行登録・エラー処理。
_load_line:
    LD A,(LOAD_LINE_LEN)
    LD (B1_VAR_LINELEN),A
    OR A
    JR Z,_load_direct_line
    LD A,(B1_LINE_BUF)
    CP '0'
    JR C,_load_direct_line
    CP '9'+1
    JR NC,_load_direct_line
    CALL _b1_call_parse_linenum
    JR C,_load_direct_line
    CALL _b1_call_program_store_line
    XOR A
    LD (LOAD_LINE_LEN),A
    JP _load_dispatch
_load_direct_line:
    LD A,57
    JR _load_error_after_clear
_load_not_found:
    LD A,53
    JR _load_error_before_clear
_load_wrong_type:
    LD A,51
    JR _load_error_before_clear
_load_disk_error:
    LD A,64
    JR _load_error_before_clear
_load_syntax:
    LD A,2
_load_error_before_clear:
    LD (B1_ERROR_KIND),A
    LD A,1
    LD (B1_ERROR_FLAG),A
    RET
_load_error_after_clear:
    LD (B1_ERROR_KIND),A
    CALL _b1_call_err_bell      ; 第4.22.7節: 表示される誤りは鳴る（メッセージの前。mainの経路と同じ）
    CALL _b1_call_select_error_msg
    CALL _b1_call_print_str
    CALL _b1_call_newline
    XOR A
    LD (B1_ERROR_FLAG),A
    LD A,2
    LD (B1_RUN_CTRL),A
    RET


; IXで指定したmain番地へ渡す。値とフラグは汎用窓外中継が保つ。
BANK1_ADV_PTR_ADDR EQU 0x1787
_b1_call_adv_ptr:
    LD IX,BANK1_ADV_PTR_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_AT_END_ADDR EQU 0x1787
_b1_call_at_end:
    LD IX,BANK1_AT_END_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_LEX_IDENT_PEEK_ADDR EQU 0x1787
_b1_call_lex_ident_peek:
    LD IX,BANK1_LEX_IDENT_PEEK_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_NEWLINE_ADDR EQU 0x1787
_b1_call_newline:
    LD IX,BANK1_NEWLINE_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_PARSE_INT_ARG_ADDR EQU 0x1787
_b1_call_parse_int_arg:
    LD IX,BANK1_PARSE_INT_ARG_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_PARSE_LINENUM_ADDR EQU 0x1787
_b1_call_parse_linenum:
    LD IX,BANK1_PARSE_LINENUM_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_PEEK_CHAR_ADDR EQU 0x1787
_b1_call_peek_char:
    LD IX,BANK1_PEEK_CHAR_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_PRINT_CHAR_ADDR EQU 0x1787
_b1_call_print_char:
    LD IX,BANK1_PRINT_CHAR_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_PRINT_STR_ADDR EQU 0x1787
_b1_call_print_str:
    LD IX,BANK1_PRINT_STR_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_PROGRAM_CLEAR_ADDR EQU 0x1787
_b1_call_program_clear:
    LD IX,BANK1_PROGRAM_CLEAR_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_PROGRAM_STORE_LINE_ADDR EQU 0x1787
_b1_call_program_store_line:
    LD IX,BANK1_PROGRAM_STORE_LINE_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_READ_CHR_ADDR EQU 0x1787
_b1_call_read_chr:
    LD IX,BANK1_READ_CHR_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_SELECT_ERROR_MSG_ADDR EQU 0x1787
_b1_call_select_error_msg:
    LD IX,BANK1_SELECT_ERROR_MSG_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_SKIP_SPACES_ADDR EQU 0x1787
_b1_call_skip_spaces:
    LD IX,BANK1_SKIP_SPACES_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_ERR_BELL_ADDR EQU 0x1787
_b1_call_err_bell:
    LD IX,BANK1_ERR_BELL_ADDR
    JP BANK1_MAIN_CALL_ADDR
BANK1_MAIN_CALL_ADDR EQU 0x1787
BANK1_OK_TXT_ADDR EQU 0x1787

; 段D/Eの記号ヒープ。ディスク文との同時実行はない。
    ORG 0x6C00
B1_HEAP_FIND_ENTRY:
    JP B1_HEAP_FIND
    ORG 0x6C08
B1_HEAP_ALLOC_ENTRY:
    JP B1_HEAP_ALLOC
; USED欄(offset 8)は単純変数1、配列2、DEF 3、FN呼出枠4。bit7は空き印。
; 追記だけなので、評価途中のレコード/要素ポインタは変わらない。
B1_HEAP_FIND:
    LD HL,(MM_HEAP_START)
b1_heap_loop:
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    ADD HL,DE
    JR Z,b1_heap_missing
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(MM_HEAP_KIND)
    CP (HL)
    POP HL
    JR NZ,b1_heap_next
    PUSH HL
    LD DE,MM_IDENT_BUF
    LD B,8
b1_heap_name:
    LD A,(DE)
    CP (HL)
    JR NZ,b1_heap_name_fail
    INC HL
    INC DE
    DJNZ b1_heap_name
    POP HL
    LD A,1
    RET
b1_heap_name_fail:
    POP HL
b1_heap_next:
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    POP HL
    CALL B1_HEAP_SIZE
    ADD HL,DE
    JR b1_heap_loop
b1_heap_missing:
    XOR A
    RET
B1_HEAP_SIZE:
    AND 07Fh
    LD DE,42
    CP 1
    RET Z
    LD DE,298
    RET
B1_HEAP_ALLOC:
    ; 未測定・自作判断: 空き印付きの同サイズ枠を先に再利用。移動はしない。
    LD HL,(MM_HEAP_START)
b1_heap_reuse:
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    ADD HL,DE
    JR Z,b1_heap_append
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(MM_HEAP_KIND)
    OR 080h
    CP (HL)
    POP HL
    JR Z,b1_heap_reused
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    POP HL
    CALL B1_HEAP_SIZE
    ADD HL,DE
    JR b1_heap_reuse
b1_heap_reused:
    LD A,1
    RET
b1_heap_append:
    LD A,(MM_HEAP_KIND)
    CALL B1_HEAP_SIZE
    LD HL,(MM_HEAP_END)
    PUSH HL
    ADD HL,DE
    JR C,b1_heap_full
    LD DE,(MM_FREE_TOP)
    OR A
    SBC HL,DE
    JR C,b1_heap_room
    JR NZ,b1_heap_full
b1_heap_room:
    ADD HL,DE
    LD (MM_HEAP_END),HL
    POP HL
    LD A,1
    RET
b1_heap_full:
    POP HL
    XOR A
    RET
