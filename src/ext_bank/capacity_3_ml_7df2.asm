; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7DF2
ml3_part_7df2:
ml3_usr_pop:
    POP BC
    RET
ml3_syntax:
    LD A,2
    JP S9_ERROR
ml3_var_read:
    LD IX,CAP_ADDR_VAR_READ_NUMERIC
    JP B3_MAIN_CALL_ADDR
ml3_lvalue:
    LD IX,CAP_ADDR_ML_LVALUE
    JP B3_MAIN_CALL_ADDR
ml3_table:
    LD IX,CAP_ADDR_ML_TABLE
; 関数途中の空隙接続。次は0x7EBF。
    JP ml3_part_7ebf
