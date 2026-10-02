; SAVE ,A の本体を置くバンク。
    ORG 0x6000
EXT_BANK2_TEST_ENTRY:
    LD A,0xB2
    RET

    ORG 0x6080
EXT_BANK2_SAVE_ENTRY:
    XOR A
    LD (S2_DONE),A
    LD (S2_WRITE_COUNT),A
    LD A,64
    LD (S2_ERROR_KIND),A
    CALL EXT_BANK2_SAVE_COMMAND
    LD A,(S2_ERROR_FLAG)
    OR A
    RET NZ
    LD A,(S2_DONE)
    OR A
    RET NZ
    LD A,64
    LD (S2_ERROR_KIND),A
    LD A,1
    LD (S2_ERROR_FLAG),A
    RET

    ORG 0x6100
; 共有RAM。表示本文は媒体へ書くまで 9000h 以降にだけ置く。
S2_BUF          EQU 0DF00h
S2_NAME         EQU 0E250h
S2_DRIVE        EQU 0E259h
S2_NAMELEN      EQU 0E25Ah
S2_DIRSEC       EQU 0E25Bh
S2_DIRIDX       EQU 0E25Ch
S2_CHOSEN       EQU 0E25Dh
S2_FOUND        EQU 0E25Eh
S2_OLDUNIT      EQU 0E25Fh
S2_SECTORS      EQU 0E260h
S2_UNITS        EQU 0E261h
S2_INDEX        EQU 0E262h
S2_COUNT        EQU 0E263h
S2_UNIT         EQU 0E264h
S2_NEXT         EQU 0E265h
S2_TRACK        EQU 0E266h
S2_SECTOR       EQU 0E267h
S2_SLOTIDX      EQU 0E268h
S2_FAT          EQU 0E500h
S2_ALLOC        EQU 0E600h
S2_CAPTURE_LEN  EQU 0E243h
S2_CAPTURE_OVER EQU 0E245h
S2_CAPTURE_ACTIVE EQU 0E240h
S2_CAPTURE_PTR EQU 0E241h
S2_CAPTURE_BASE EQU 09000h
S2_DONE         EQU 0E24Bh
S2_WRITE_COUNT  EQU 0E24Ch
S2_WRITE_DRIVE  EQU 0E246h
S2_WRITE_TRACK  EQU 0E247h
S2_WRITE_SECTOR EQU 0E248h
S2_WRITE_SOURCE EQU 0E249h
S2_ERROR_FLAG   EQU 0E880h
S2_ERROR_KIND   EQU 0E8A0h

EXT_BANK2_SAVE_COMMAND:
    CALL s2_filename
    LD A,(S2_ERROR_FLAG)
    OR A
    RET NZ
    JP s2_save_suffix

; SAVE/KILL/NAME共通。明示ドライブと9バイトの名前を大小変換せず読む。
s2_filename:
    CALL s2_skip
    CALL s2_peek
    CP '"'
    JP NZ,s2_syntax
    CALL s2_adv
    CALL s2_peek
    CP '1'
    JR Z,s2_drive1
    CP '2'
    JP NZ,s2_syntax
    LD A,1
    JR s2_drive_set
s2_drive1:
    XOR A
s2_drive_set:
    LD (S2_DRIVE),A
    CALL s2_adv
    CALL s2_peek
    CP ':'
    JP NZ,s2_syntax
    CALL s2_adv
    LD HL,S2_NAME
    LD B,9
    LD A,' '
s2_pad_name:
    LD (HL),A
    INC HL
    DJNZ s2_pad_name
    XOR A
    LD (S2_NAMELEN),A
s2_name_loop:
    CALL s2_end
    JP Z,s2_syntax
    CALL s2_peek
    CP '"'
    JR Z,s2_name_end
    PUSH AF
    LD A,(S2_NAMELEN)
    CP 9
    JP NC,s2_name_long
    LD E,A
    LD D,0
    LD HL,S2_NAME
    ADD HL,DE
    POP AF
    LD (HL),A
    LD A,E
    INC A
    LD (S2_NAMELEN),A
    CALL s2_adv
    JR s2_name_loop
s2_name_long:
    POP AF
    JP s2_syntax
s2_name_end:
    LD A,(S2_NAMELEN)
    OR A
    JP Z,s2_syntax
    CALL s2_adv
    CALL s2_skip
    RET
s2_save_suffix:
    CALL s2_peek
    CP ','
    JP NZ,s2_unsupported
    CALL s2_adv
    CALL s2_skip
    CALL s2_peek
    AND 0DFh
    CP 'A'
    JP NZ,s2_unsupported
    CALL s2_adv
    CALL s2_skip
    CALL s2_peek
    OR A
    JR Z,s2_parse_done
    CP ':'
    JP NZ,s2_syntax
s2_parse_done:
    ; 書き込み禁止の印を最初に確認する。
    LD D,37
    LD E,13
    CALL s2_read
    JP C,s2_disk_error
    LD A,(S2_BUF)
    AND 010h
    JP NZ,s2_protected
    LD D,37
    LD E,14
    CALL s2_read
    JP C,s2_disk_error
    LD HL,S2_BUF
    LD DE,S2_FAT
    LD BC,256
    LDIR
    CALL s2_find_slot
    LD A,(S2_ERROR_FLAG)
    OR A
    RET NZ
    JP s2_save_dir_done

; 読み取りだけの共通探索。FOUNDは同名、CHOSENは同名または空き枠。
s2_find_slot:
    XOR A
    LD (S2_FOUND),A
    LD (S2_CHOSEN),A
    LD A,1
    LD (S2_DIRSEC),A
s2_dir_sector:
    LD D,37
    LD A,(S2_DIRSEC)
    LD E,A
    CALL s2_read
    JP C,s2_disk_error
    XOR A
    LD (S2_DIRIDX),A
s2_dir_entry:
    LD A,(S2_DIRIDX)
    LD L,A
    LD H,0
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    LD DE,S2_BUF
    ADD HL,DE
    PUSH HL
    POP IX
    LD A,(IX+0)
    CP 0FFh
    JP Z,s2_unused
    OR A
    JR Z,s2_remember_free
    PUSH IX
    POP HL
    LD DE,S2_NAME
    LD B,9
s2_cmp_name:
    LD A,(DE)
    CP (HL)
    JR NZ,s2_cmp_no
    INC DE
    INC HL
    DJNZ s2_cmp_name
    LD A,1
    LD (S2_FOUND),A
    LD (S2_CHOSEN),A
    LD A,(S2_DIRSEC)
    LD (S2_SECTOR),A
    LD A,(S2_DIRIDX)
    LD (S2_SLOTIDX),A
    LD A,(IX+10)
    LD (S2_OLDUNIT),A
    JP s2_dir_done
s2_cmp_no:
    JR s2_next_entry
s2_unused:
    LD A,(S2_CHOSEN)
    OR A
    JP NZ,s2_dir_done
    LD A,1
    LD (S2_CHOSEN),A
    LD A,(S2_DIRSEC)
    LD (S2_SECTOR),A
    LD A,(S2_DIRIDX)
    LD (S2_SLOTIDX),A
    JP s2_dir_done
s2_remember_free:
    LD A,(S2_CHOSEN)
    OR A
    JR NZ,s2_next_entry
    LD A,1
    LD (S2_CHOSEN),A
    LD A,(S2_DIRSEC)
    LD (S2_SECTOR),A
    LD A,(S2_DIRIDX)
    LD (S2_SLOTIDX),A
s2_next_entry:
    LD A,(S2_DIRIDX)
    INC A
    LD (S2_DIRIDX),A
    CP 16
    JP C,s2_dir_entry
    LD A,(S2_DIRSEC)
    INC A
    LD (S2_DIRSEC),A
    CP 13
    JP C,s2_dir_sector
s2_dir_done:
    RET
s2_save_dir_done:
    LD A,(S2_CHOSEN)
    OR A
    JP Z,s2_full
    ; LISTの既存ルーチンを文字出力だけ捕捉して使用する。
    LD HL,09000h
    LD (HL),0
    LD DE,09001h
    LD BC,02FFFh
    LDIR
    CALL s2_capture_begin
    CALL s2_list
    CALL s2_capture_end
    LD A,(S2_CAPTURE_OVER)
    OR A
    JP NZ,s2_full
    LD HL,(S2_CAPTURE_LEN)
    LD A,L
    OR A
    LD A,H
    JR Z,s2_sectors_ready
    INC A
s2_sectors_ready:
    LD (S2_SECTORS),A
    ADD A,7
    SRL A
    SRL A
    SRL A
    LD (S2_UNITS),A
    ; 同名の場合はRAM上で旧鎖を空きへ戻す。媒体への書込みはまだしない。
    LD A,(S2_FOUND)
    OR A
    JR Z,s2_allocate
    CALL s2_release_chain
s2_allocate:
    XOR A
    LD (S2_COUNT),A
    LD HL,s2_order
    LD B,158
s2_find_unit:
    LD A,(HL)
    INC HL
    PUSH HL
    PUSH BC
    LD L,A
    LD H,0
    LD DE,S2_FAT
    ADD HL,DE
    LD A,(HL)
    CP 0FFh
    JR NZ,s2_find_next
    POP BC
    POP HL
    DEC HL
    LD A,(HL)
    INC HL
    PUSH HL
    PUSH BC
    LD E,A
    LD D,0
    LD HL,S2_ALLOC
    LD A,(S2_COUNT)
    LD C,A
    LD B,0
    ADD HL,BC
    LD (HL),E
    INC A
    LD (S2_COUNT),A
    LD C,A
    LD A,(S2_UNITS)
    CP C
    JR Z,s2_alloc_ready
    POP BC
    POP HL
    DJNZ s2_find_unit
    JP s2_full
s2_alloc_ready:
    POP BC
    POP HL
    JR s2_alloc_done
s2_find_next:
    POP BC
    POP HL
    DJNZ s2_find_unit
    JP s2_full
s2_alloc_done:
    ; 鎖をRAM上で先に作る。終端は使用セクタ数。
    XOR A
    LD (S2_INDEX),A
s2_chain_loop:
    LD A,(S2_INDEX)
    LD E,A
    LD D,0
    LD HL,S2_ALLOC
    ADD HL,DE
    LD A,(HL)
    LD L,A
    LD H,0
    LD DE,S2_FAT
    ADD HL,DE
    PUSH HL
    LD A,(S2_INDEX)
    INC A
    LD C,A
    LD A,(S2_UNITS)
    CP C
    JR Z,s2_chain_end
    LD E,C
    LD D,0
    LD HL,S2_ALLOC
    ADD HL,DE
    LD A,(HL)
    JR s2_chain_store
s2_chain_end:
    LD A,(S2_SECTORS)
    AND 7
    JR NZ,s2_chain_count
    LD A,8
s2_chain_count:
    ADD A,0C0h
s2_chain_store:
    POP HL
    LD (HL),A
    LD A,C
    LD (S2_INDEX),A
    LD B,A
    LD A,(S2_UNITS)
    CP B
    JR NZ,s2_chain_loop
    ; 事前判定完了。ここから実際に媒体へ書く。
    XOR A
    LD (S2_INDEX),A
s2_body_loop:
    LD A,(S2_INDEX)
    SRL A
    SRL A
    SRL A
    LD E,A
    LD D,0
    LD HL,S2_ALLOC
    ADD HL,DE
    LD A,(HL)
    LD (S2_UNIT),A
    SRL A
    LD D,A
    LD A,(S2_UNIT)
    AND 1
    ADD A,A
    ADD A,A
    ADD A,A
    LD E,A
    LD A,(S2_INDEX)
    AND 7
    ADD A,E
    INC A
    LD E,A
    LD A,(S2_INDEX)
    ADD A,090h
    LD H,A
    LD L,0
    LD A,(S2_DRIVE)
    CALL s2_write
    JP C,s2_disk_error
    LD A,(S2_INDEX)
    INC A
    LD (S2_INDEX),A
    LD B,A
    LD A,(S2_SECTORS)
    CP B
    JR NZ,s2_body_loop
    CALL s2_flush_fat
    RET C
    LD D,37
    LD A,(S2_SECTOR)
    LD E,A
    CALL s2_read
    JP C,s2_disk_error
    LD A,(S2_SLOTIDX)
    LD L,A
    LD H,0
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    LD DE,S2_BUF
    ADD HL,DE
    PUSH HL
    LD DE,S2_NAME
    LD B,9
s2_entry_name:
    LD A,(DE)
    LD (HL),A
    INC DE
    INC HL
    DJNZ s2_entry_name
    XOR A
    LD (HL),A
    INC HL
    LD A,(S2_ALLOC)
    LD (HL),A
    INC HL
    LD B,5
    LD A,0FFh
s2_entry_tail:
    LD (HL),A
    INC HL
    DJNZ s2_entry_tail
    POP HL
    LD HL,S2_BUF
    LD D,37
    LD A,(S2_SECTOR)
    LD E,A
    LD A,(S2_DRIVE)
    CALL s2_write
    JP C,s2_disk_error
    XOR A
    LD (S2_ERROR_FLAG),A
    INC A
    LD (S2_DONE),A
    RET
s2_syntax:
    LD A,2
    JR s2_error
s2_unsupported:
    LD A,51
    JR s2_error
s2_protected:
    LD A,61
    JR s2_error
s2_full:
    LD A,68
    JR s2_error
s2_disk_error:
    LD A,64
s2_error:
    LD (S2_ERROR_KIND),A
    LD A,1
    LD (S2_ERROR_FLAG),A
    RET

s2_read:
    LD A,(S2_DRIVE)
    LD IX,BANK2_READ_CHR_ADDR
    JP BANK2_MAIN_CALL_ADDR
s2_write:
    JP s2_write_stream
s2_skip:
    LD IX,BANK2_SKIP_SPACES_ADDR
    JP BANK2_MAIN_CALL_ADDR
s2_peek:
    LD IX,BANK2_PEEK_CHAR_ADDR
    JP BANK2_MAIN_CALL_ADDR
s2_adv:
    LD IX,BANK2_ADV_PTR_ADDR
    JP BANK2_MAIN_CALL_ADDR
s2_end:
    LD IX,BANK2_AT_END_ADDR
    JP BANK2_MAIN_CALL_ADDR
s2_capture_begin:
    LD HL,S2_CAPTURE_BASE
    LD (S2_CAPTURE_PTR),HL
    LD HL,0
    LD (S2_CAPTURE_LEN),HL
    XOR A
    LD (S2_CAPTURE_OVER),A
    INC A
    LD (S2_CAPTURE_ACTIVE),A
    RET
s2_capture_end:
    XOR A
    LD (S2_CAPTURE_ACTIVE),A
    LD A,01Ah
    LD IX,BANK2_CAPTURE_CHAR_ADDR
    JP BANK2_MAIN_CALL_ADDR
s2_list:
    LD IX,BANK2_LIST_RENDER_ADDR
    JP BANK2_MAIN_CALL_ADDR

BANK2_MAIN_CALL_ADDR EQU 0x1787
BANK2_SKIP_SPACES_ADDR EQU 0x1787
BANK2_PEEK_CHAR_ADDR EQU 0x1787
BANK2_ADV_PTR_ADDR EQU 0x1787
BANK2_AT_END_ADDR EQU 0x1787
BANK2_READ_CHR_ADDR EQU 0x1787
BANK2_SEND_ADDR EQU 0x1787
BANK2_SEND_CONT_ADDR EQU 0x1787
BANK2_SEND_PAIR_ADDR EQU 0x1787
BANK2_RECV_ADDR EQU 0x1787
BANK2_LIST_RENDER_ADDR EQU 0x1787
BANK2_CAPTURE_CHAR_ADDR EQU 0x1787

; 1.35a節・1.36節・第68版・m7bz・第223版の受信位相に合わせた書き込み送信。
; 全WRITEは「手前 → subの応答1バイト → 0x11,0x01,D,T,R＋データ256」の同じ形。
; 手前は、最初のWRITEでは長さ2のrun `0x14, D`（1.35a節・第223版）、2回目以降は
; `S=0x06`（長さ1のrun、第68版）。応答は各WRITEの手前の後・0x11の前に1件受ける。
s2_write_stream:
    AND 1
    LD (S2_WRITE_DRIVE),A
    LD A,D
    LD (S2_WRITE_TRACK),A
    LD A,E
    LD (S2_WRITE_SECTOR),A
    LD (S2_WRITE_SOURCE),HL
    LD A,(S2_WRITE_COUNT)
    OR A
    JR NZ,s2_ws_later
    LD A,014h
    CALL s2_send
    RET C
    LD A,(S2_WRITE_DRIVE)
    CALL s2_send_cont
    RET C
    JR s2_ws_recv
s2_ws_later:
    LD A,006h
    CALL s2_send
    RET C
s2_ws_recv:
    CALL s2_recv
    RET C
s2_ws_request:
    LD A,011h
    CALL s2_send
    RET C
    LD A,001h
    CALL s2_send_cont
    RET C
    LD A,(S2_WRITE_DRIVE)
    CALL s2_send_cont
    RET C
    LD A,(S2_WRITE_TRACK)
    CALL s2_send_cont
    RET C
    LD A,(S2_WRITE_SECTOR)
    CALL s2_send_cont
    RET C
    LD HL,(S2_WRITE_SOURCE)
    LD B,128
s2_ws_data:
    CALL s2_send_pair
    RET C
    DJNZ s2_ws_data
    LD A,(S2_WRITE_COUNT)
    INC A
    LD (S2_WRITE_COUNT),A
    OR A
    RET
s2_send:
    LD IX,BANK2_SEND_ADDR
    JP BANK2_MAIN_CALL_ADDR
s2_send_cont:
    LD IX,BANK2_SEND_CONT_ADDR
    JP BANK2_MAIN_CALL_ADDR
s2_send_pair:
    LD IX,BANK2_SEND_PAIR_ADDR
    JP BANK2_MAIN_CALL_ADDR
s2_recv:
    LD IX,BANK2_RECV_ADDR
    JP BANK2_MAIN_CALL_ADDR

; l3-disk-format 2.5節の2単位取得・2単位飛ばし順。
s2_order:
    DB 72,73,68,69,64,65,60,61,56,57,52,53,48,49,44,45
    DB 40,41,36,37,32,33,28,29,24,25,20,21,16,17,12,13
    DB 8,9,4,5,0,1,70,71,66,67,62,63,58,59,54,55
    DB 50,51,46,47,42,43,38,39,34,35,30,31,26,27,22,23
    DB 18,19,14,15,10,11,6,7,2,3,76,77,80,81,84,85
    DB 88,89,92,93,96,97,100,101,104,105,108,109,112,113,116,117
    DB 120,121,124,125,128,129,132,133,136,137,140,141,144,145,148,149
    DB 152,153,156,157,78,79,82,83,86,87,90,91,94,95,98,99
    DB 102,103,106,107,110,111,114,115,118,119,122,123,126,127,130,131
    DB 134,135,138,139,142,143,146,147,150,151,154,155,158,159

; SAVE/KILL共通。単位0〜159だけを解放し、終端のセクタ数を読まない。
s2_release_chain:
    LD A,(S2_OLDUNIT)
    LD (S2_UNIT),A
    LD B,160
s2_release_loop:
    LD A,(S2_UNIT)
    CP 160
    RET NC
    LD L,A
    LD H,0
    LD DE,S2_FAT
    ADD HL,DE
    LD A,(HL)
    LD (S2_NEXT),A
    LD (HL),0FFh
    LD A,(S2_NEXT)
    CP 160
    RET NC
    LD (S2_UNIT),A
    DJNZ s2_release_loop
    RET

; 呼出し側の事前判定が済んだ後だけ使う。
s2_flush_fat:
    LD A,14
    LD (S2_INDEX),A
s2_fat_loop:
    LD D,37
    LD A,(S2_INDEX)
    LD E,A
    CALL s2_read
    JR C,s2_flush_error
    LD HL,S2_FAT
    LD DE,S2_BUF
    LD BC,160
    LDIR
    LD D,37
    LD A,(S2_INDEX)
    LD E,A
    LD HL,S2_BUF
    LD A,(S2_DRIVE)
    CALL s2_write
    JR C,s2_flush_error
    LD A,(S2_INDEX)
    INC A
    LD (S2_INDEX),A
    CP 17
    JR C,s2_fat_loop
    OR A
    RET
s2_flush_error:
    CALL s2_disk_error
    SCF
    RET

; 文字列で保存する処理系なので tokens.tsv の KILL=D8/NAME=F4 に対応する
; 文キーワードをここで大小を区別せず照合する。名前欄は折り畳まない。
    ORG 0x7000
EXT_BANK2_DISK_MATCH:
K2_CUR_PTR EQU 0E883h
K2_LINE_END EQU 0E881h
K2_MATCH_KIND EQU 0E276h
K2_MATCH_LEN EQU 0E277h
    LD IX,k2_words
k2_match_word:
    LD A,(IX+0)
    OR A
    RET Z
    LD (K2_MATCH_LEN),A
    LD A,(IX+1)
    LD (K2_MATCH_KIND),A
    LD HL,(K2_LINE_END)
    LD DE,(K2_CUR_PTR)
    OR A
    SBC HL,DE
    LD A,(K2_MATCH_LEN)
    CP L
    JR Z,k2_match_compare
    JR NC,k2_match_next
k2_match_compare:
    LD HL,(K2_CUR_PTR)
    PUSH IX
    POP DE
    INC DE
    INC DE
    LD A,(K2_MATCH_LEN)
    LD B,A
k2_match_chars:
    LD A,(HL)
    CALL k2_upper
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,k2_match_next
    INC HL
    INC DE
    DJNZ k2_match_chars
    LD DE,(K2_LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    POP HL
    JR Z,k2_match_ok
    LD A,(HL)
    CALL k2_upper
    CP 'A'
    JR C,k2_match_ok
    CP 'Z'+1
    JR C,k2_match_next
k2_match_ok:
    LD (K2_CUR_PTR),HL
    LD A,(K2_MATCH_KIND)
    RET
k2_match_next:
    PUSH IX
    POP HL
    LD A,(K2_MATCH_LEN)
    ADD A,2
    LD E,A
    LD D,0
    ADD HL,DE
    PUSH HL
    POP IX
    JR k2_match_word
k2_upper:
    CP 'a'
    RET C
    CP 'z'+1
    RET NC
    SUB 32
    RET
k2_words:
    DB 5,8,"FILES",4,9,"LOAD",4,10,"SAVE",4,11,"KILL",4,12,"NAME",0

    ORG 0x7100
EXT_BANK2_KILL_ENTRY:
    CALL k2_init
    JP k2_kill
    ORG 0x7110
EXT_BANK2_NAME_ENTRY:
    CALL k2_init
    JP k2_name

; SAVEの共有領域の直後。旧枠は新名探索が上書きするS2_*とは別に保存する。
K2_OLDSEC EQU 0E269h
K2_OLDSLOT EQU 0E26Ah
K2_OLDDRIVE EQU 0E26Bh
k2_init:
    XOR A
    LD (S2_DONE),A
    LD (S2_WRITE_COUNT),A
    LD (S2_ERROR_FLAG),A
    LD A,64
    LD (S2_ERROR_KIND),A
    RET
k2_kill:
    CALL s2_filename
    LD A,(S2_ERROR_FLAG)
    OR A
    RET NZ
    CALL k2_end_statement
    RET C
    ; 保護判定はSAVEと同じREADと同じ印を使う。
    LD D,37
    LD E,13
    CALL s2_read
    JP C,s2_disk_error
    LD A,(S2_BUF)
    AND 010h
    JP NZ,s2_protected
    CALL k2_find_old
    RET C
    LD D,37
    LD E,14
    CALL s2_read
    JP C,s2_disk_error
    LD HL,S2_BUF
    LD DE,S2_FAT
    LD BC,256
    LDIR
    CALL s2_release_chain
    ; ERR53/61の判定は完了した。3複製の0〜159だけを変更する。
    CALL s2_flush_fat
    RET C
    CALL k2_read_old
    RET C
    LD (HL),0
    JP k2_write_old
k2_name:
    CALL s2_filename
    LD A,(S2_ERROR_FLAG)
    OR A
    RET NZ
    CALL k2_find_old
    RET C
    CALL s2_peek
    CALL k2_upper
    CP 'A'
    JP NZ,s2_syntax
    CALL s2_adv
    CALL s2_peek
    CALL k2_upper
    CP 'S'
    JP NZ,s2_syntax
    CALL s2_adv
    CALL s2_skip
    CALL s2_peek
    CP '"'
    JP NZ,s2_syntax
    ; 新名は明示ドライブが必要。跨るNAMEは未測定のためERR73とする。
    CALL s2_adv
    CALL s2_peek
    CP '1'
    JR Z,k2_new_drive1
    CP '2'
    JP NZ,k2_drive_error
    LD A,1
    JR k2_new_drive
k2_new_drive1:
    XOR A
k2_new_drive:
    LD B,A
    LD A,(K2_OLDDRIVE)
    CP B
    JP NZ,k2_drive_error
    CALL s2_adv
    CALL s2_peek
    CP ':'
    JP NZ,k2_drive_error
    ; 共通のファイル名パーサへ引用符の位置から渡す。
    LD HL,(K2_CUR_PTR)
    DEC HL
    DEC HL
    LD (K2_CUR_PTR),HL
    CALL s2_filename
    LD A,(S2_ERROR_FLAG)
    OR A
    RET NZ
    CALL k2_end_statement
    RET C
    CALL s2_find_slot
    LD A,(S2_ERROR_FLAG)
    OR A
    RET NZ
    LD A,(S2_FOUND)
    OR A
    JP NZ,k2_exists
    ; 印のセクタ・FATには触れず、旧枠の名前欄だけを書き換える。
    CALL k2_read_old
    RET C
    LD DE,S2_NAME
    LD B,9
k2_rename_bytes:
    LD A,(DE)
    LD (HL),A
    INC HL
    INC DE
    DJNZ k2_rename_bytes
k2_write_old:
    LD HL,S2_BUF
    LD D,37
    LD A,(K2_OLDSEC)
    LD E,A
    LD A,(K2_OLDDRIVE)
    CALL s2_write
    JP C,s2_disk_error
    XOR A
    LD (S2_ERROR_FLAG),A
    INC A
    LD (S2_DONE),A
    RET
k2_find_old:
    CALL s2_find_slot
    LD A,(S2_ERROR_FLAG)
    OR A
    JR NZ,k2_carry
    LD A,(S2_FOUND)
    OR A
    JR Z,k2_missing
    LD A,(S2_SECTOR)
    LD (K2_OLDSEC),A
    LD A,(S2_SLOTIDX)
    LD (K2_OLDSLOT),A
    LD A,(S2_DRIVE)
    LD (K2_OLDDRIVE),A
    OR A
    RET
k2_missing:
    LD A,53
    CALL s2_error
k2_carry:
    SCF
    RET
k2_read_old:
    LD A,(K2_OLDDRIVE)
    LD (S2_DRIVE),A
    LD D,37
    LD A,(K2_OLDSEC)
    LD E,A
    CALL s2_read
    JR C,k2_read_error
    LD A,(K2_OLDSLOT)
    LD L,A
    LD H,0
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    LD DE,S2_BUF
    ADD HL,DE
    OR A
    RET
k2_read_error:
    CALL s2_disk_error
    SCF
    RET
k2_end_statement:
    CALL s2_skip
    CALL s2_peek
    OR A
    RET Z
    CP ':'
    JR Z,k2_end_ok
    CALL s2_syntax
    SCF
    RET
k2_end_ok:
    OR A
    RET
k2_exists:
    LD A,65
    JP s2_error
k2_drive_error:
    LD A,73
    JP s2_error
