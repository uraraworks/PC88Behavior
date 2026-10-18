; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7D63
ml3_part_7d63:
    JP s9b_address_slow_tail
ml3_address_fast:
    LD IX,CAP_ADDR_ML_ADDRESS_FAST
    JP B3_MAIN_CALL_ADDR
