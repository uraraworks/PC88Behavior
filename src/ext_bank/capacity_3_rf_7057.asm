; l4-f2: ランダム機能本体。既存の入口・断片を動かさず空隙へ配置。
    ORG 0x7057
RF3_rf_make_copy:
    LD DE,MM_RUN_STR_TMP_BUF
    LDIR
    POP AF
    LD (MM_RUN_STR_TMP_LEN),A
    LD L,A
    LD H,0
    LD DE,MM_RUN_STR_TMP_BUF-1
    ADD HL,DE
    LD A,(HL)
    OR A
    RET NZ
    ; 指数0が数値0。未測定の仮数は自作の非零印を選ぶ。
    LD A,1
    LD (MM_RUN_STR_TMP_BUF),A
    RET
RF3_rf_make_overflow:
    LD A,6
    CALL S9_ERROR
RF3_rf_make_bad:
    POP AF
    RET
