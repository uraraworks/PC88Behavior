; l4-f2: main窓を復元する共有中継。
    ORG 0x7323
RF1_CALL_rf_end:
    LD IX,CAP_ADDR_RF_rf_end
    JP CAP_ADDR_MAIN_CALL
