; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7A2C
ml0_part_7a2c:
    RET NZ
    JP fn_set_int
ML0_LVALUE_ENTRY:
; fn_lvalueの数値は+9の種別を指すので値領域+11へ進む。
; 文字列配列はもともと3B記述子。単純文字列はアドレス要求時に長形式へ移す。
    LD A,1
    CALL fn_lvalue
    CALL fn_bad_keep
    RET NZ
    CP 3
; 関数途中の空隙接続。次は0x7FD2。
    JP ml0_part_7fd2
