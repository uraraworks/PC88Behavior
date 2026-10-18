; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6AEE
ml0_part_6aee:
ML0_FN_ENTRY:
    JP fn_def
ML0_VARPTR_ENTRY:
; '('は予約語の入口で消費済み。#は未測定につき固定の負番地を返す。
    CALL fn_skip
    CALL fn_peek
    CP '#'
    JP NZ,ml0_varptr_name
; 関数途中の空隙接続。次は0x6B03。
    JP ml0_part_6b03
