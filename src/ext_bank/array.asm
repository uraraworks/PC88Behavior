; docs/spec/l4-program.md 第14.16版4.10から独立実装。
; 自作配置: 名前8、種別1、物理長2、FRE消費長2、次元1、要素幅1、extent[次元]、要素。
; 先頭添字が最速。整数はリトルエンディアン2Bが連続する。
; 空き枠を再利用し、生きたポインタを移動しない。FREでは空き枠と管理用8Bを除く。
    ORG 0x6650
    JP ar_dim
    ORG 0x6660
    JP ar_alloc
    ORG 0x6668
    JP ar_default
    ORG 0x6670
    LD HL,(MM_AR_REC)
    JP ar_elem
    ORG 0x6678
    JP ar_parse
    ORG 0x6680
    JP ar_resolve
    ORG 0x6688
    JP ar_read
    ORG 0x6690
    JP ar_fre
    ORG 0x6698
    JP ar_trim
    ORG 0x66A0
    JP ar_erase
    ORG 0x66A8
    JP ar_read_stmt

ar_dim:
    CALL ar_skip
    CALL ar_ident
    OR A
    JP Z,ar_syntax
    CALL ar_skip
    CALL ar_peek
    CP '('
    JP NZ,ar_syntax
    CALL ar_parse
    RET NZ
    CALL ar_find
    OR A
    JR NZ,ar_duplicate
    CALL ar_alloc
    OR A
    RET Z
    CALL ar_skip
    CALL ar_peek
    CP ','
    RET NZ
    CALL ar_adv
    JR ar_dim
ar_duplicate:
    LD A,10
    JP ar_error

ar_default:
    CALL ar_find
    OR A
    RET NZ
    ; 参照した添字を保存して、同じ次元数の上限10で確保。
    LD A,(MM_AR_NDIM)
    LD B,A
    LD HL,MM_AR_ARGS
ar_def_push:
    LD E,(HL)
    INC HL
    LD D,(HL)
    DEC HL
    PUSH DE
    LD (HL),10
    INC HL
    LD (HL),0
    INC HL
    DJNZ ar_def_push
    CALL ar_alloc
    PUSH AF
    PUSH HL
    LD A,(MM_AR_NDIM)
    LD B,A
    LD L,A
    LD H,0
    ADD HL,HL
    LD DE,MM_AR_ARGS
    ADD HL,DE
    ; 戻り値を一旦別レジスタへ置き、添字を戻す。
    POP IX
    POP AF
    LD C,A
ar_def_pop:
    POP DE
    DEC HL
    LD (HL),D
    DEC HL
    LD (HL),E
    DJNZ ar_def_pop
    PUSH IX
    POP HL
    LD A,C
    OR A
    RET

ar_alloc:
    CALL ar_size
    LD (MM_AR_SIZE),A
    LD A,(MM_AR_NDIM)
    LD B,A
    LD IX,MM_AR_ARGS
    LD HL,1
ar_product:
    LD E,(IX+0)
    LD D,(IX+1)
    INC DE
    BIT 7,D
    JP NZ,ar_alloc_range
    CALL ar_mul
    JP C,ar_alloc_range
    INC IX
    INC IX
    DJNZ ar_product
    LD A,(MM_AR_SIZE)
    LD E,A
    LD D,0
    CALL ar_mul
    JP C,ar_alloc_range
    LD A,(MM_AR_NDIM)
    ADD A,A
    LD E,A
    LD D,0
    ADD HL,DE
    JP C,ar_alloc_memory
    LD DE,7
    ADD HL,DE
    JP C,ar_alloc_memory
    LD (MM_AR_LOGICAL),HL
    LD DE,8
    ADD HL,DE
    JP C,ar_alloc_memory
    LD (MM_AR_TOTAL),HL
    ; 配列の容量予算は第4.10.3と第20節の通常空き量から導く。
    ; 本文の物理配置は自作。本文との実衝突も別に検査する。
    CALL ar_fre
    BIT 7,H
    JP NZ,ar_alloc_memory
    LD DE,(MM_AR_LOGICAL)
    OR A
    SBC HL,DE
    JP C,ar_alloc_memory
    LD HL,(MM_HEAP_START)
ar_alloc_scan:
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    ADD HL,DE
    JR Z,ar_alloc_append
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    POP HL
    CP 0x82
    JR NZ,ar_alloc_next
    CALL ar_record_size
    PUSH HL
    EX DE,HL
    LD DE,(MM_AR_TOTAL)
    OR A
    SBC HL,DE
    POP HL
    JR NC,ar_alloc_init
ar_alloc_next:
    CALL ar_record_size
    ADD HL,DE
    JR ar_alloc_scan
ar_alloc_append:
    PUSH HL
    LD DE,(MM_AR_TOTAL)
    ADD HL,DE
    JR C,ar_alloc_full
    LD DE,(MM_FREE_TOP)
    OR A
    SBC HL,DE
    JR C,ar_alloc_room
    JR NZ,ar_alloc_full
ar_alloc_room:
    ADD HL,DE
    LD (MM_HEAP_END),HL
    POP HL
    PUSH HL
    LD DE,9
    ADD HL,DE
    LD DE,(MM_AR_TOTAL)
    LD (HL),E
    INC HL
    LD (HL),D
    POP HL
ar_alloc_init:
    LD (MM_AR_REC),HL
    LD DE,MM_IDENT_BUF
    LD B,8
ar_alloc_name:
    LD A,(DE)
    LD (HL),A
    INC HL
    INC DE
    DJNZ ar_alloc_name
    LD (HL),2
    INC HL
    INC HL
    INC HL
    LD DE,(MM_AR_LOGICAL)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD A,(MM_AR_NDIM)
    LD (HL),A
    INC HL
    LD A,(MM_AR_SIZE)
    LD (HL),A
    INC HL
    LD A,(MM_AR_NDIM)
    LD B,A
    LD IX,MM_AR_ARGS
ar_alloc_bounds:
    LD E,(IX+0)
    LD D,(IX+1)
    INC DE
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    INC IX
    INC IX
    DJNZ ar_alloc_bounds
    PUSH HL
    LD HL,(MM_AR_TOTAL)
    LD A,(MM_AR_NDIM)
    ADD A,A
    ADD A,15
    LD E,A
    LD D,0
    OR A
    SBC HL,DE
    LD B,H
    LD C,L
    POP HL
ar_alloc_zero:
    LD (HL),0
    INC HL
    DEC BC
    LD A,B
    OR C
    JR NZ,ar_alloc_zero
    LD HL,(MM_AR_REC)
    XOR A
    LD (MM_ERROR_FLAG),A
    INC A
    RET
ar_alloc_full:
    POP HL
ar_alloc_memory:
    LD A,7
    JR ar_alloc_error
ar_alloc_range:
    LD A,9
ar_alloc_error:
    CALL ar_error
    XOR A
    RET

; HL×DE、16bitの積。CFは16bitに収まらない場合。BC/IXを保持。
ar_mul:
    PUSH BC
    LD B,H
    LD C,L
    LD HL,0
ar_mul_loop:
    LD A,D
    OR E
    JR Z,ar_mul_done
    SRL D
    RR E
    JR NC,ar_mul_shift
    ADD HL,BC
    JR C,ar_mul_done
ar_mul_shift:
    LD A,D
    OR E
    JR Z,ar_mul_done
    SLA C
    RL B
    JR NC,ar_mul_loop
    SCF
ar_mul_done:
    POP BC
    RET

ar_resolve:
    CALL ar_parse
    RET NZ
    CALL ar_default
    OR A
    RET Z
    CALL ar_elem
    RET
ar_elem:
    LD (MM_AR_REC),HL
    LD DE,13
    ADD HL,DE
    LD A,(MM_AR_NDIM)
    CP (HL)
    JP NZ,ar_range
    LD B,A
    INC HL
    LD A,(HL)
    LD (MM_AR_SIZE),A
    INC HL
    LD IX,MM_AR_ARGS
    LD DE,1
    LD (MM_AR_STRIDE),DE
    LD DE,0
    LD (MM_AR_OFFSET),DE
ar_elem_loop:
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    PUSH HL
    PUSH DE
    LD L,(IX+0)
    LD H,(IX+1)
    OR A
    SBC HL,DE
    JR NC,ar_elem_bad
    ADD HL,DE
    LD DE,(MM_AR_STRIDE)
    CALL ar_mul
    LD DE,(MM_AR_OFFSET)
    ADD HL,DE
    LD (MM_AR_OFFSET),HL
    POP DE
    LD HL,(MM_AR_STRIDE)
    CALL ar_mul
    LD (MM_AR_STRIDE),HL
    POP HL
    INC IX
    INC IX
    DJNZ ar_elem_loop
    PUSH HL
    LD HL,(MM_AR_OFFSET)
    LD A,(MM_AR_SIZE)
    LD E,A
    LD D,0
    CALL ar_mul
    POP DE
    ADD HL,DE
    XOR A
    LD (MM_ERROR_FLAG),A
    RET
ar_elem_bad:
    POP DE
    POP HL
ar_range:
    LD A,9
    CALL ar_error
    SCF
    RET
ar_read:
    CALL ar_resolve
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
    LD A,(MM_AR_SIZE)
    CP 3
    JR Z,ar_read_string
    LD C,A
    LD B,0
    CP 2
    LD A,0
    JR Z,ar_read_numeric
    LD A,C
    CP 4
    LD A,1
    JR Z,ar_read_numeric
    INC A
ar_read_numeric:
    LD (MM_CUR_TYPE),A
    LD DE,MM_CUR_DATA
    LDIR
    RET
ar_read_string:
    LD DE,MM_CUR_TYPE
    LD BC,3
    LDIR
    RET

; 死んだ枠はFREを消費せず、生きた配列の管理用8Bも利用者消費へ含めない。
ar_fre:
    LD HL,(MM_FREE_TOP)
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    ; 第20節の基準量X-(34586+n)から、生きた記号と文字列ページを差し引く。
    ; 本文の物理配置・空き枠・管理用8Bは利用者のFRE消費に含めない。
    LD DE,(MM_HEAP_START)
    ADD HL,DE
    LD DE,MM_AR_CAPACITY_BASE
    OR A
    SBC HL,DE
    EX DE,HL
    LD HL,(MM_HEAP_START)
ar_fre_loop:
    LD BC,(MM_HEAP_END)
    PUSH HL
    OR A
    SBC HL,BC
    POP HL
    JR Z,ar_fre_done
    PUSH DE
    PUSH HL
    LD BC,8
    ADD HL,BC
    LD A,(HL)
    POP HL
    PUSH AF
    CALL ar_record_size
    PUSH HL
    ADD HL,DE
    EX DE,HL
    POP HL
    POP AF
    POP BC
    BIT 7,A
    JR NZ,ar_fre_dead
    CP 2
    JR NZ,ar_fre_next
    PUSH DE
    LD DE,11
    ADD HL,DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD H,B
    LD L,C
    OR A
    SBC HL,DE
    LD B,H
    LD C,L
    POP DE
ar_fre_dead:
    ; BC=空き値-論理消費（死んだ枠なら空き値）、DE=次の枠。
    PUSH DE
    LD HL,(MM_HEAP_START)
    ; 元枠の物理長は次の枠から元枠を引く。元枠はMM_AR_RECへ記録。
    LD HL,(MM_AR_REC)
    EX DE,HL
    OR A
    SBC HL,DE
    ADD HL,BC
    LD B,H
    LD C,L
    POP DE
ar_fre_next:
    EX DE,HL
    LD D,B
    LD E,C
    JR ar_fre_loop

ar_fre_done:
    EX DE,HL
    RET

; HL=枠、DE=物理長。共通探索用。AF/BC保持。
ar_record_size:
    LD (MM_AR_REC),HL
    PUSH AF
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    AND 0x7F
    CP 1
    LD DE,42
    JR Z,ar_rs_done
    LD DE,298
    CP 2
    JR NZ,ar_rs_done
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
ar_rs_done:
    POP HL
    POP AF
    RET

ar_trim:
    LD HL,(MM_HEAP_START)
    LD BC,0
    LD B,H
    LD C,L
ar_trim_loop:
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    ADD HL,DE
    JR Z,ar_trim_done
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    POP HL
    CALL ar_record_size
    ADD HL,DE
    BIT 7,A
    JR NZ,ar_trim_loop
    LD B,H
    LD C,L
    JR ar_trim_loop
ar_trim_done:
    LD (MM_HEAP_END),BC
    RET

ar_erase:
    CALL ar_skip
    CALL ar_ident
    OR A
    JP Z,ar_syntax
    CALL ar_find
    OR A
    JR Z,ar_illegal
    PUSH HL
    LD DE,13
    ADD HL,DE
    LD A,(HL)
    ADD A,A
    ADD A,15
    LD E,A
    LD D,0
    POP HL
    PUSH HL
    PUSH HL
    LD BC,11
    ADD HL,BC
    LD C,(HL)
    INC HL
    LD B,(HL)
    LD HL,8
    ADD HL,BC
    OR A
    SBC HL,DE
    LD B,H
    LD C,L                 ; BC=要素領域バイト長
    POP HL
    ADD HL,DE
    CALL ar_size
    CP 3
    JR NZ,ar_erase_mark
ar_erase_string:
    PUSH BC
    PUSH HL
    LD A,(HL)
    OR A
    JR Z,ar_erase_string_next
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    CALL ar_pagefree
ar_erase_string_next:
    POP HL
    INC HL
    INC HL
    INC HL
    POP BC
    DEC BC
    DEC BC
    DEC BC
    LD A,B
    OR C
    JR NZ,ar_erase_string
ar_erase_mark:
    POP HL
    LD DE,8
    ADD HL,DE
    LD (HL),0x82
    CALL ar_trim
    CALL ar_skip
    CALL ar_peek
    CP ','
    RET NZ
    CALL ar_adv
    JP ar_erase
ar_illegal:
    LD A,5
    JR ar_error
ar_syntax:
    LD A,2
ar_error:
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
    RET

; READも同じ要素解決・型変換・文字列記述子を使う。
ar_read_stmt:
    CALL ar_skip
    CALL ar_ident
    OR A
    JP Z,ar_syntax
    LD (MM_RUN_ASSIGN_KIND),A
    LD HL,MM_IDENT_BUF
    LD DE,MM_RUN_ASSIGN_NAME
    LD BC,8
    LDIR
    CALL ar_skip
    CALL ar_peek
    CP '('
    LD HL,0
    JR NZ,ar_rs_target
    CALL ar_resolve
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
ar_rs_target:
    LD (MM_RUN_ARRAY_ASSIGN_ADDR),HL
    LD A,(MM_RUN_ASSIGN_KIND)
    CP 3
    LD A,0
    JR NZ,ar_rs_data
    INC A
ar_rs_data:
    CALL ar_data
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
    LD HL,MM_RUN_ASSIGN_NAME
    LD DE,MM_IDENT_BUF
    LD BC,8
    LDIR
    LD HL,(MM_RUN_ARRAY_ASSIGN_ADDR)
    LD A,H
    OR L
    JR Z,ar_rs_scalar
    LD A,(MM_RUN_ASSIGN_KIND)
    CP 3
    JR Z,ar_rs_string
    PUSH HL
    LD A,(MM_RUN_ASSIGN_KIND)
    CP 1
    CALL Z,ar_single
    CALL ar_size
    LD C,A
    LD B,0
    POP DE
    LD HL,MM_CUR_DATA
    LDIR
    JR ar_rs_next
ar_rs_string:
    CALL ar_sstore
    JR ar_rs_next
ar_rs_scalar:
    LD A,(MM_RUN_ASSIGN_KIND)
    CP 3
    JR Z,ar_rs_scalar_string
    CALL ar_vwrite
    JR ar_rs_next
ar_rs_scalar_string:
    CALL ar_swrite
ar_rs_next:
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
    CALL ar_skip
    CALL ar_peek
    CP ','
    RET NZ
    CALL ar_adv
    JP ar_read_stmt

AR_SKIP_ADDR EQU 0x1787
ar_skip:
    LD IX,AR_SKIP_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_PEEK_ADDR EQU 0x1787
ar_peek:
    LD IX,AR_PEEK_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_ADV_ADDR EQU 0x1787
ar_adv:
    LD IX,AR_ADV_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_IDENT_ADDR EQU 0x1787
ar_ident:
    LD IX,AR_IDENT_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_EXPR_ADDR EQU 0x1787
ar_expr:
    LD IX,AR_EXPR_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_INT_ADDR EQU 0x1787
ar_int:
    LD IX,AR_INT_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_FIND_ADDR EQU 0x1787
ar_find:
    LD IX,AR_FIND_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_SIZE_ADDR EQU 0x1787
ar_size:
    LD IX,AR_SIZE_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_PAGEFREE_ADDR EQU 0x1787
ar_pagefree:
    LD IX,AR_PAGEFREE_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_DATA_ADDR EQU 0x1787
ar_data:
    LD IX,AR_DATA_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_VWRITE_ADDR EQU 0x1787
ar_vwrite:
    LD IX,AR_VWRITE_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_SWRITE_ADDR EQU 0x1787
ar_swrite:
    LD IX,AR_SWRITE_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_SSTORE_ADDR EQU 0x1787
ar_sstore:
    LD IX,AR_SSTORE_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_SINGLE_ADDR EQU 0x1787
ar_single:
    LD IX,AR_SINGLE_ADDR
    JP BANK2_MAIN_CALL_ADDR

AR_PARSE_ADDR EQU 0x1787
ar_parse:
    LD IX,AR_PARSE_ADDR
    JP BANK2_MAIN_CALL_ADDR
