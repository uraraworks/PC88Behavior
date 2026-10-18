; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6B43
ml0_part_6b43:
    CALL fn_ident
    OR A
    JP Z,ml0_varptr_bad
    CALL fn_skip
; 関数途中の空隙接続。次は0x743F。
    JP ml0_part_743f
