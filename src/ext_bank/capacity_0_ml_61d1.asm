; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x61D1
ml0_part_61d1:
; §4.24.2 DEF USR。DEF FNの既存入口へは不一致のとき戻す。
ML0_DEF_ENTRY:
    LD A,E
    CP 10
    JP NC,fn_syntax
    PUSH DE
    CALL fn_skip
    LD A,'='
    CALL ml0_expect
    CALL fn_bad
    JP NZ,ml0_def_fail
    CALL fn_is_string
    OR A
    JP NZ,ml0_def_type
    CALL fn_expr
    CALL fn_bad
    JP NZ,ml0_def_fail
    CALL ml0_address
    CALL fn_bad
; 関数途中の空隙接続。次は0x6254。
    JP ml0_part_6254
