; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7D53
ml3_part_7d53:

ml3_address_dispatch:
    CALL ml3_address_fast
    OR A
    JP NZ,S9_OK
    LD A,(MM_CUR_TYPE)
; 関数途中の空隙接続。次は0x7D63。
    JP ml3_part_7d63
