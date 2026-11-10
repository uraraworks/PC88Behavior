; l4-program.md 第12節: 可変ポート出力も共有の写しを更新する。
    ORG 0x704B
t3_record_port:
    LD IX,CAP_ADDR_RECORD_OUT
    CALL B3_MAIN_CALL_ADDR
    JP S9_OK
