; GET/PUTの既存図形振分けからmainの分類へ。
    ORG 0x6077
rf_gput_stmt:
    LD IX,CAP_ADDR_RF_TRY_TRANSFER
    JP BANK2_MAIN_CALL_ADDR
