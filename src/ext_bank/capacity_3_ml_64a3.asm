; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x64A3
ml3_part_64a3:
    PUSH DE
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP ','
    JP NZ,ml3_call_close
    CALL B3_ADV_PTR
    CALL ml3_lvalue
    CALL S9_BAD
    JP NZ,ml3_call_fail
    POP DE
    PUSH HL
; 関数途中の空隙接続。次は0x6EE5。
    JP ml3_part_6ee5
