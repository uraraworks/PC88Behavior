; 順次ファイル用。SAVE/KILLの既存媒体処理の呼出し表だけを置く。
    ORG 0x6003
SQ_BANK_ENTRY:
    LD A,(MM_SQ_OP)
    ADD A,A
    LD E,A
    LD D,0
    LD HL,SQ_BANK_TABLE
    ADD HL,DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
    JP (HL)
SQ_BANK_TABLE:
    DW s2_find_slot,sq_bread,sq_bwrite,s2_flush_fat
    DW sq_bcreate,s2_release_chain,sq_bfat,sq_bprotect,sq_border
sq_bread:
    LD DE,(MM_SQ_WORK)
    CALL s2_read
    JP C,s2_disk_error
    RET
sq_bwrite:
    LD DE,(MM_SQ_WORK)
    LD HL,(MM_SQ_WORK+2)
    LD A,(S2_DRIVE)
    CALL s2_write
    JP C,s2_disk_error
    RET
sq_bfat:
    LD D,37
    LD E,14
    CALL s2_read
    JP C,s2_disk_error
    LD HL,S2_BUF
    LD DE,S2_FAT
    LD BC,256
    LDIR
    RET
sq_bprotect:
    LD D,37
    LD E,13
    CALL s2_read
    JP C,s2_disk_error
    LD A,(S2_BUF)
    AND 0x10
    RET Z
    JP s2_protected
sq_bcreate:
    XOR A
    LD (MM_BINARY_MODE),A
    LD HL,1
    LD (S2_CAPTURE_LEN),HL
    JP s2_size_hl
