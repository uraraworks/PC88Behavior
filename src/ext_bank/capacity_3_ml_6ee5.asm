; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6EE5
ml3_part_6ee5:
ml3_call_close:
    CALL S9_CLOSE
    CALL S9_BAD
    JP NZ,ml3_call_fail
ml3_call_ready:
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    OR A
    JP Z,ml3_call_valid
    CP ':'
    JP Z,ml3_call_valid
; 関数途中の空隙接続。次は0x6F03。
    JP ml3_part_6f03
