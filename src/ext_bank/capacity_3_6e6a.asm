; c1: DATA_PARSE_NUMBER_LITERAL。自作mainから移動、規則/処理は維持。
    ORG 0x6E6A
DATA_PARSE_NUMBER_LITERAL:
    CALL PEEK_CHAR
    CP '-'
    JR NZ,_dpnl_noneg
    CALL ADV_PTR
    LD A,1
    LD (RUN_DATA_NEG),A
    JR _dpnl_afterneg
_dpnl_noneg:
    XOR A
    LD (RUN_DATA_NEG),A
_dpnl_afterneg:
    CALL LEX_NUMBER
    ; 第4.21節: 数字でないDATAの検査（hi→ERR 2）と、倍精度の読み先への'#'の補い。バンク0。
    CALL CAP_DATA_LITERAL_HELPER
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(LIT_HASDOT)
    OR A
    JR NZ,_dpnl_general
    LD A,(LIT_HASEXP)
    OR A
    JR NZ,_dpnl_general
    LD A,(LIT_HASSUFFIX)
    OR A
    JR NZ,_dpnl_general
    CALL LIT_TRY_INT16
    JR NC,_dpnl_general
    CALL VAL_SET_INT
    JR _dpnl_applyneg
_dpnl_general:
    CALL LIT_COPY_TO_FINBUF
    CALL MBF_FIN
    LD A,(MBF_STATUS)
    CP 3
    JR Z,_dpnl_double
    CP 1
    JR Z,_dpnl_ovfl
    CALL VAL_SET_SINGLE_FROM_RES
    JR _dpnl_applyneg
_dpnl_double:
    CALL MBF_DFIN
    LD A,(MBF_STATUS)
    OR A
    JR NZ,_dpnl_ovfl
    CALL VAL_SET_DOUBLE_FROM_DRES
    JR _dpnl_applyneg
_dpnl_ovfl:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET
_dpnl_applyneg:
    LD A,(RUN_DATA_NEG)
    OR A
    JR Z,_dpnl_done
    CALL VAL_NEG
_dpnl_done:
    XOR A
    LD (ERROR_FLAG),A
    JP ASSIGN_CONVERT_CUR       ; 第4.21節: 読み先の型へ変換（整数は丸め・範囲外ERR 6）
