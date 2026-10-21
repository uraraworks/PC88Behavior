; l4-f2: main窓を復元する共有中継。
    ORG 0x7343
RF1_CALL_sq_buffer:
    LD IX,CAP_ADDR_RF_sq_buffer
    JP CAP_ADDR_MAIN_CALL
