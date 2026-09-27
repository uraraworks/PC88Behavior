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

MAIN_SUB_SECTOR_BUF EQU 0DF00h
FILES_FAT_BUF       EQU 0E100h
FILES_CELL_BUF      EQU 0E200h
FILES_PHASE         EQU 0E210h
FILES_READ_TRACK    EQU 0E212h
FILES_READ_SECTOR   EQU 0E213h
FILES_READ_OK       EQU 0E214h
FILES_DIR_SECTOR    EQU 0E215h
FILES_ENTRY_INDEX   EQU 0E216h
FILES_ENTRY_COUNT   EQU 0E217h
FILES_CHAIN_GUARD   EQU 0E218h
FILES_SIZE_VALUE    EQU 0E219h
FILES_DEC_STARTED   EQU 0E21Ah

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
