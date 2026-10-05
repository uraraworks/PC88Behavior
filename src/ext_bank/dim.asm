; DIM本体をmain末尾からバンク1へ移す。左辺・型・配列・誤りの経路は従来どおり。
; mainの呼び先は既存EXT_BANK_MAIN_CALLで窓を復元し、値とフラグを保つ。
; 第4.10節。カンマ区切りの複数配列・再DIMのERR 10も既存動作を維持。
; 0x7740までのON/WHILE本体と重ならない固定入口。
B1_DIM_MAX_ELEMS EQU 32 ; mainのARRAY_MAX_ELEMSと同じ既存の要素数上限。
    ORG 0x7750
B1_DIM_STMT:
_dim_one:
    CALL b1_dim_call_skip_spaces
    CALL b1_dim_call_lex_ident_consume
    OR A
    JR Z,_dim_syntax
    LD HL,MM_IDENT_BUF
    LD DE,MM_RUN_ARRAY_NAME
    LD BC,8
    LDIR
    CALL b1_dim_call_skip_spaces
    CALL b1_dim_call_peek_char
    CP '('
    JR NZ,_dim_syntax
    CALL b1_dim_call_adv_ptr
    CALL b1_dim_call_logic_or_expr
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
    CALL b1_dim_call_val_to_int16_cur
    JR C,_dim_ovfl
    LD A,D
    OR A
    JR NZ,_dim_ovfl
    LD A,E
    CP B1_DIM_MAX_ELEMS
    JR NC,_dim_ovfl
    INC A
    LD (MM_RUN_DIM_COUNT),A
    CALL b1_dim_call_skip_spaces
    CALL b1_dim_call_peek_char
    CP ')'
    JR NZ,_dim_syntax
    CALL b1_dim_call_adv_ptr
    LD HL,MM_RUN_ARRAY_NAME
    LD DE,MM_IDENT_BUF
    LD BC,8
    LDIR
    CALL b1_dim_call_array_find
    OR A
    JR NZ,_dim_dup
    LD A,(MM_RUN_DIM_COUNT)
    CALL b1_dim_call_array_alloc
    OR A
    JR Z,_dim_oom
    CALL b1_dim_call_skip_spaces
    CALL b1_dim_call_peek_char
    CP ','
    JR NZ,_dim_done
    CALL b1_dim_call_adv_ptr
    JR _dim_one
_dim_done:
    XOR A
    LD (MM_ERROR_FLAG),A
    RET
_dim_syntax:
    LD A,1
    LD (MM_ERROR_FLAG),A
    LD A,2
    LD (MM_ERROR_KIND),A
    RET
_dim_typeerr:
    LD A,1
    LD (MM_ERROR_FLAG),A
    LD A,13
    LD (MM_ERROR_KIND),A
    RET
_dim_ovfl:
    LD A,1
    LD (MM_ERROR_FLAG),A
    LD A,7
    LD (MM_ERROR_KIND),A
    RET
_dim_dup:
    LD A,1
    LD (MM_ERROR_FLAG),A
    LD A,10
    LD (MM_ERROR_KIND),A
    RET
_dim_oom:
    LD A,1
    LD (MM_ERROR_FLAG),A
    LD A,7
    LD (MM_ERROR_KIND),A
    RET

B1_DIM_SKIP_SPACES_ADDR EQU 0x1787
b1_dim_call_skip_spaces:
    LD IX,B1_DIM_SKIP_SPACES_ADDR
    JP BANK1_MAIN_CALL_ADDR
B1_DIM_LEX_IDENT_CONSUME_ADDR EQU 0x1787
b1_dim_call_lex_ident_consume:
    LD IX,B1_DIM_LEX_IDENT_CONSUME_ADDR
    JP BANK1_MAIN_CALL_ADDR
B1_DIM_PEEK_CHAR_ADDR EQU 0x1787
b1_dim_call_peek_char:
    LD IX,B1_DIM_PEEK_CHAR_ADDR
    JP BANK1_MAIN_CALL_ADDR
B1_DIM_ADV_PTR_ADDR EQU 0x1787
b1_dim_call_adv_ptr:
    LD IX,B1_DIM_ADV_PTR_ADDR
    JP BANK1_MAIN_CALL_ADDR
B1_DIM_LOGIC_OR_EXPR_ADDR EQU 0x1787
b1_dim_call_logic_or_expr:
    LD IX,B1_DIM_LOGIC_OR_EXPR_ADDR
    JP BANK1_MAIN_CALL_ADDR
B1_DIM_VAL_TO_INT16_CUR_ADDR EQU 0x1787
b1_dim_call_val_to_int16_cur:
    LD IX,B1_DIM_VAL_TO_INT16_CUR_ADDR
    JP BANK1_MAIN_CALL_ADDR
B1_DIM_ARRAY_FIND_ADDR EQU 0x1787
b1_dim_call_array_find:
    LD IX,B1_DIM_ARRAY_FIND_ADDR
    JP BANK1_MAIN_CALL_ADDR
B1_DIM_ARRAY_ALLOC_ADDR EQU 0x1787
b1_dim_call_array_alloc:
    LD IX,B1_DIM_ARRAY_ALLOC_ADDR
    JP BANK1_MAIN_CALL_ADDR
