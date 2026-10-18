; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6B33
ml0_part_6b33:
    LD HL,MM_RUN_STR_TMP_BUF
    JP ml0_varptr_close
ml0_varptr_name:
; 存在検査より先に変数の構文を検査し、未定義名を含む式もERR 2にする。
    LD HL,(MM_CUR_PTR)
    PUSH HL
; 関数途中の空隙接続。次は0x6B43。
    JP ml0_part_6b43
