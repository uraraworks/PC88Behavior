; docs/spec/l4-basic.md 第18節(l4-s9b)。本体は拡張バンク3。
; 利用者番地へのアクセスをそのまま行う。作業域の保護・移設はしない。
; CLEARの上限・共有スタックは第20節と段Fの自作配置判断に従う。
    ORG 0x7D00
    JP S9B_PEEK
    ORG 0x7D10
    JP S9B_POKE
    ORG 0x7D20
    JP S9B_CLEAR
    ORG 0x7D30
    JP S9D_FRE
    ORG 0x7D40
    JP S9D_GOSUB_PUSH
    ORG 0x7D50
    JP S9D_FOR_SLOT
    ORG 0x7D60
    JP S9D_GOSUB_SLOT
    ORG 0x7D70
    JP S9D_FOR_ROOM

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
    LD A,(MM_MBF_OPA+3)
    CP 144
    JR NZ,s9b_address_round
    LD A,(MM_MBF_OPA+2)
    BIT 7,A
    JR NZ,s9b_address_round
    XOR A
    LD (MM_MBF_OPB),A
    LD (MM_MBF_OPB+1),A
    LD (MM_MBF_OPB+2),A
    LD A,145
    LD (MM_MBF_OPB+3),A
    CALL S9_MBF_SUB
    CALL S9_SET_SINGLE
s9b_address_round:
    CALL S9_TO_INT
    OR A
    JP Z,S9_OVERFLOW
    JP S9_OK
