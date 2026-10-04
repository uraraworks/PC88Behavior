; 第22節の式因子。LN_*は入力時と実行時で同時に使わないため共用する。
; 接尾辞や不正英字は消費せず、後続の式評価に構文検査を任せる。
    ORG 0x7E10
FACTOR_RADIX_ENTRY:
    ; 実行行はNUL終端を保証しない。残り本文を上限内で複写する。
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD B,H
    LD C,L
    EX DE,HL
    LD DE,LN_INPUT
    LDIR
    XOR A
    LD (DE),A
    LD HL,LN_INPUT
    LD (LN_SRC),HL
    CALL LN_RADIX_VALUE
    LD HL,(LN_SRC)
    LD DE,LN_INPUT
    OR A
    SBC HL,DE
    LD DE,(CUR_PTR)
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,(LN_ERR)
    OR A
    JR NZ,_b3_radix_error
    LD HL,(LN_VALUE)
    LD (MM_CUR_DATA),HL             ; CUR_DATA: 符号付き16bit整数
    XOR A
    LD (MM_CUR_TYPE),A              ; CUR_TYPE=整数
    RET
_b3_radix_error:
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_FLAG),A
    LD (MM_ERROR_IS_RUNTIME),A              ; ERROR_IS_RUNTIME
    RET

; 入力拒否もON ERRORへ通知する。捕捉なしでは従来の入力時表示を保つ。
; mainへの中継はBUSYを退避するので、ハンドラからバンク3を再び使える。
HEXCONST_INPUT_ERROR:
    LD A,(MM_RUN_ERROR_ACTIVE)              ; RUN_ERROR_ACTIVE
    OR A
    JP NZ,LN_MESSAGE
    LD HL,(MM_RUN_ERROR_HANDLER_LINE)             ; RUN_ERROR_HANDLER_LINE
    LD A,H
    OR L
    JP Z,LN_MESSAGE
    LD HL,LN_LINE_BUF
    LD (CUR_PTR),HL
    LD (MM_STMT_START),HL             ; RESUME用の入力文頭
    LD A,(LN_LINE_LEN)
    LD E,A
    LD D,0
    ADD HL,DE
    LD (LINE_END),HL
    LD HL,HEXCONST_DIRECT_RECORD_ADDR
    LD (RUN_CUR_RECORD),HL
    XOR A
    LD (MM_RUN_CUR_LINENO),A              ; RUN_CUR_LINENO=直接モード
    LD (MM_RUN_CUR_LINENO+1),A
    LD (RUN_CTRL),A
    LD A,1
    LD (ERROR_FLAG),A
    LD IX,HEXCONST_INPUT_ERROR_ADDR
    CALL B3_MAIN_CALL_ADDR
    XOR A
    LD (ERROR_FLAG),A
    RET
HEXCONST_DIRECT_RECORD_ADDR EQU 0x1787
HEXCONST_INPUT_ERROR_ADDR EQU 0x1787

; ABSの負数経路。-32768の絶対値だけは整数に収まらないため単精度へ。
    ORG 0x7EA0
HEXCONST_ABS_NEGATIVE:
    LD A,(S9_CUR_TYPE)
    OR A
    JR NZ,_hex_abs_negate
    LD HL,(S9_CUR_DATA)
    LD A,H
    CP 080h
    JR NZ,_hex_abs_negate
    LD A,L
    OR A
    JR NZ,_hex_abs_negate
    CALL S9_LOAD_OPA
    CALL S9_SET_SINGLE
_hex_abs_negate:
    LD IX,HEXCONST_NEG_ADDR
    JP B3_MAIN_CALL_ADDR
HEXCONST_NEG_ADDR EQU 0x1787
