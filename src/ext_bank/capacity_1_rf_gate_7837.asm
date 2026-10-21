; l4-f2: main窓を復元する共有中継。
    ORG 0x7837
RF1_CALL_sq_number:
    LD IX,CAP_ADDR_RF_sq_number
    JP CAP_ADDR_MAIN_CALL
