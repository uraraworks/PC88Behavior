; l4-program.md 9.1: 行番号を解析し存在を確認する。
    ORG 0x7FF4
delete_parse:
    LD IX,CAP_DELETE_PARSE_FIND
    JP CAP_ADDR_MAIN_CALL
