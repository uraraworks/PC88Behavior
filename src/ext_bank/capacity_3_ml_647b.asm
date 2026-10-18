; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x647B
ml3_part_647b:
; 未使用引数の内容は未規定。HL/DEともRAM内を指すようにした。
    LD HL,(MM_CUR_PTR)
    PUSH HL
; 数値評価で再利用されない描画作業バッファ中央を使う。内容は未規定。
    LD HL,MM_PA_TILE+128
    PUSH HL
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP '('
    JP NZ,ml3_call_ready
    CALL B3_ADV_PTR
    CALL ml3_lvalue
    CALL S9_BAD
    JP NZ,ml3_call_fail
    POP DE
    POP AF
    PUSH HL
; 関数途中の空隙接続。次は0x64A3。
    JP ml3_part_64a3
