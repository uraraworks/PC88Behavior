; docs/spec/l4-basic.md 第18節(l4-s9b)。本体は拡張バンク3。
; 利用者番地へのアクセスをそのまま行う。作業域の保護・移設はしない。
; CLEARの第2引数は受理のみ。メモリ上限への反映は別段で決める。
    ORG 0x7D00
    JP S9B_PEEK
    ORG 0x7D10
    JP S9B_POKE
    ORG 0x7D20
    JP S9B_CLEAR

S9B_PEEK:
    CALL S9_IS_STRING
    OR A
    JP NZ,S9_TYPE
    CALL S9_NUM_ARG
    CALL S9_BAD
    RET NZ
    CALL S9B_ADDRESS_CUR
    CALL S9_BAD
    RET NZ
    EX DE,HL
    LD L,(HL)
    LD H,0
    JP S9_SET_INT
S9B_POKE:
    CALL S9_IS_STRING
    OR A
    JP NZ,S9_TYPE
    CALL S9B_EXPR
    CALL S9_BAD
    RET NZ
    CALL S9B_ADDRESS_CUR
    CALL S9_BAD
    RET NZ
    PUSH DE                    ; 値の評価から書込先を守る
    CALL S9_COMMA
    CALL S9_BAD
    JR NZ,s9b_poke_fail
    CALL S9_BYTE_ARG
    CALL S9_BAD
    JR NZ,s9b_poke_fail
    POP HL
    LD (HL),E
    JP S9_OK
s9b_poke_fail:
    POP DE
    RET

; 正の[32768,65536)だけ先に65536を減算し、away丸め。
; HEX$/OCT$と同じ単精度経由（未測定の倍精度境界は同じ自作判断）。
S9B_ADDRESS_CUR:
    LD A,(S9_CUR_TYPE)
    OR A
    JR Z,s9b_address_round
    CALL S9_LOAD_OPA
    LD A,(0C003h)
    CP 144
    JR NZ,s9b_address_round
    LD A,(0C002h)
    BIT 7,A
    JR NZ,s9b_address_round
    XOR A
    LD (0C004h),A
    LD (0C005h),A
    LD (0C006h),A
    LD A,145
    LD (0C007h),A
    CALL S9_MBF_SUB
    CALL S9_SET_SINGLE
s9b_address_round:
    CALL S9_TO_INT
    OR A
    JP Z,S9_OVERFLOW
    JP S9_OK

; CLEAR、CLEAR n、CLEAR ,n、CLEAR n,n の数値引数を受理する。
; 引数値は保存しない。既存の変数・配列・実行状態の初期化を共有し、
; プログラムと乱数状態は保持する。未測定のCLEAR誤り条件は決めない。
S9B_CLEAR:
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    OR A
    JR Z,s9b_clear_apply
    CP ':'
    JR Z,s9b_clear_apply
    CP ','
    JR Z,s9b_clear_second
    CALL S9_IS_STRING
    OR A
    JP NZ,S9_TYPE
    CALL S9B_EXPR
    CALL S9_BAD
    RET NZ
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP ','
    JR NZ,s9b_clear_apply
s9b_clear_second:
    CALL B3_ADV_PTR
    CALL S9_IS_STRING
    OR A
    JP NZ,S9_TYPE
    CALL S9B_EXPR
    CALL S9_BAD
    RET NZ
s9b_clear_apply:
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    OR A
    JR Z,s9b_clear_ok
    CP ':'
    JR Z,s9b_clear_ok
    LD A,2
    JP S9_ERROR
s9b_clear_ok:
    CALL S9B_CLEAR_STATE
    JP S9_OK

S9B_EXPR_ADDR EQU 0x1787
S9B_EXPR:
    LD IX,S9B_EXPR_ADDR
    JP B3_MAIN_CALL_ADDR
S9B_CLEAR_ADDR EQU 0x1787
S9B_CLEAR_STATE:
    LD IX,S9B_CLEAR_ADDR
    JP B3_MAIN_CALL_ADDR
