; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7D13
ml3_part_7d13:
    LD L,E
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,DE
    LD DE,MM_INTERP_EXT_RAM_BASE
    ADD HL,DE
; 関数途中の空隙接続。次は0x7D23。
    JP ml3_part_7d23
