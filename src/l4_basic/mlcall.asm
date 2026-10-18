; バンク内入口は固定断片の配置から定義。
ML0_DEF_ENTRY EQU 0x61D1
ML0_FN_ENTRY EQU 0x6AEE
ML0_VARPTR_ENTRY EQU 0x6AF1
ML0_LVALUE_ENTRY EQU 0x7A30
ML3_STMT_ENTRY EQU 0x62E1
ML3_ADDRESS_ENTRY EQU 0x7403
ML3_USR_ENTRY EQU 0x7406
ML3_SCRUB_ENTRY EQU 0x6D28
; §4.24。main途中の共通部。起動・待機からは呼ばない。
; 呼出先のAF/BC/DE/HL破壊を許す。SP/IX/IYの破壊は未測定。
ML_TRY:
    CALL PEEK_CHAR
    CALL FOLD_UPPER
    CP 'U'
    JP NZ,ML_OLD_RHS
    CALL ML_USR_NAME
    OR A
    JP Z,ML_OLD_RHS
    LD HL,ML3_USR_ENTRY
    CALL ML_BANK3
    LD A,1
    RET
ML_USR_NAME:
    CALL SKIP_SPACES
    CALL LEX_IDENT_PEEK
    LD HL,IDENT_BUF
    LD A,(HL)
    CP 'U'
    JP NZ,ML_NO
    INC HL
    LD A,(HL)
    CP 'S'
    JP NZ,ML_NO
    INC HL
    LD A,(HL)
    CP 'R'
    JP NZ,ML_NO
    INC HL
    LD A,(HL)
    LD E,0
    OR A
    JP Z,ML_USR_NAMED
    SUB '0'
    CP 10
    JP NC,ML_NO
    LD E,A
    INC HL
    LD A,(HL)
    OR A
    JP NZ,ML_USR_INVALID
ML_USR_NAMED:
    PUSH DE
    CALL LEX_IDENT_CONSUME
    POP DE
    LD A,1
    RET
ML_USR_INVALID:
    LD E,255
    JP ML_USR_NAMED
ML_NO:
    XOR A
    RET
ML_OLD_RHS:
    LD HL,0789Dh
    JP S9_BANK_CALL
ML_DEF:
    CALL ML_USR_NAME
    OR A
    LD HL,ML0_DEF_ENTRY
    JP NZ,ML_BANK0
    LD HL,ML0_FN_ENTRY
ML_BANK0:
    PUSH HL
    POP IX
    PUSH AF
    XOR A
    JP CAPACITY_BANK_CALL
ML_BANK3:
    PUSH HL
    POP IX
    PUSH AF
    LD A,3
    JP CAPACITY_BANK_CALL
ML_LVALUE:
    LD HL,ML0_LVALUE_ENTRY
    JP ML_BANK0
ML_TABLE:
; 非字句名の42Bレコード。初回DEFだけ確保、NEW/CLEAR/RUNは通常ヒープと同寿命。
; 10組×(番地2B+定義済1B)。番地0も未定義と区別する。
    PUSH DE
    PUSH BC
    LD HL,IDENT_BUF
    LD (HL),1
    INC HL
    LD B,7
    XOR A
ML_NAME_ZERO:
    LD (HL),A
    INC HL
    DJNZ ML_NAME_ZERO
    CALL VAR_FIND
    OR A
    JP NZ,ML_TABLE_FOUND
    POP BC
    PUSH BC
    LD A,C
    OR A
    JP Z,ML_TABLE_EXIT
    CALL VAR_ALLOC
ML_TABLE_FOUND:
    POP BC
    POP DE
    OR A
    RET Z
    LD A,E
    ADD A,A
    ADD A,E
    ADD A,11
    LD E,A
    LD D,0
    ADD HL,DE
    LD A,1
    RET
ML_TABLE_EXIT:
    POP BC
    POP DE
    RET
ML_ADDRESS:
    LD HL,ML3_ADDRESS_ENTRY
    JP ML_BANK3
ML_BAD:
    LD A,(ERROR_FLAG)
    OR A
    RET
ML_ERROR:
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_FLAG),A
    RET
ML_SYNTAX:
    LD A,2
    JP ML_ERROR
ML_ILLEGAL:
    LD A,5
    JP ML_ERROR
ML_OK:
    XOR A
    LD (ERROR_FLAG),A
    RET
ML_CALL_USER:
; BC=入口、HL/DE=実引数。構文位置をCPUスタックで保護する。
    CALL ML_TARGET_CHECK
    CALL ML_BAD
    RET NZ
    LD IX,(CUR_PTR)
    PUSH IX
    LD IX,(LINE_END)
    PUSH IX
    CALL ML_JUMP_BC
    POP HL
    LD (LINE_END),HL
    POP HL
    LD (CUR_PTR),HL
    JP ML_OK
ML_JUMP_BC:
    PUSH BC
    LD BC,0
    RET
ML_INVOKE:
; A=内部型(0/1/2/3)。P=SPの8B作業域、HL=P+4（倍精度だけPから）。
; 数値枠はRETまで有効。文字列記述子は専用RAMに保持し、返値を評価バッファへ複写する。
    PUSH AF
    CALL ML_TARGET_CHECK
    CALL ML_BAD
    JP NZ,ML_TARGET_FAILED
    POP AF
    PUSH AF
    LD HL,(CUR_PTR)
    PUSH HL
    LD HL,(LINE_END)
    PUSH HL
    LD HL,(CUR_DATA+6)
    PUSH HL
    LD HL,(CUR_DATA+4)
    PUSH HL
    LD HL,(CUR_DATA+2)
    PUSH HL
    LD HL,(CUR_DATA)
    PUSH HL
    LD HL,0
    ADD HL,SP
    CP 2
    JP Z,ML_FRAME_READY
    CP 3
    JP Z,ML_FRAME_STRING
    PUSH BC
    PUSH AF
    PUSH HL
    LD D,H
    LD E,L
    INC DE
    INC DE
    INC DE
    INC DE
    LD BC,4
    LDIR
    POP HL
; 単精度位置へ移した後は元の下半分を無効にし、作業値を二重に残さない。
    LD (HL),0
    INC HL
    LD (HL),0
    INC HL
    LD (HL),0
    INC HL
    LD (HL),0
    DEC HL
    DEC HL
    DEC HL
    POP AF
    POP BC
    JP ML_FRAME_READY
ML_FRAME_STRING:
; 文字列記述子はRET後も残す。数値のスタック枠とは寿命を分ける。
    LD HL,MM_USR_STRING_DESC
    LD A,(RUN_STR_TMP_LEN)
    LD (HL),A
    INC HL
    LD (HL),RUN_STR_TMP_BUF & 255
    INC HL
    LD (HL),RUN_STR_TMP_BUF >> 8
    DEC HL
    DEC HL
    LD HL,0
    ADD HL,SP
    LD A,3
ML_FRAME_READY:
    CALL ML_SCRUB
    LD D,H
    LD E,L
    INC HL
    INC HL
    INC HL
    INC HL
    CP 3
    JP NZ,ML_FRAME_NUMERIC
    LD DE,MM_USR_STRING_DESC
    JP ML_FRAME_CALL
ML_FRAME_NUMERIC:
    PUSH HL
    LD HL,ML_TYPES
    LD E,A
    LD D,0
    ADD HL,DE
    LD A,(HL)
    POP HL
ML_FRAME_CALL:
    CALL ML_JUMP_BC
    LD HL,13
    ADD HL,SP
    LD A,(HL)
    LD (CUR_TYPE),A
    LD HL,0
    ADD HL,SP
    CP 3
    JP Z,ML_RETURN_STRING
    CP 2
    JP Z,ML_RETURN_NUM
    INC HL
    INC HL
    INC HL
    INC HL
ML_RETURN_NUM:
    LD DE,CUR_DATA
    LD BC,4
    CP 2
    JP NZ,ML_RETURN_COPY
    LD C,8
ML_RETURN_COPY:
    LDIR
    JP ML_FRAME_FREE
ML_RETURN_STRING:
    LD HL,MM_USR_STRING_DESC
    LD A,(HL)
    LD (RUN_STR_TMP_LEN),A
    LD B,A
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
    LD DE,RUN_STR_TMP_BUF
    CALL STR_COPY_BN
ML_FRAME_FREE:
    POP HL
    POP HL
    POP HL
    POP HL
    POP HL
    LD (LINE_END),HL
    POP HL
    LD (CUR_PTR),HL
    POP AF
    JP ML_OK
ML_TYPES:
    DB 2,4,8

ML_VARPTR:
    LD HL,ML0_VARPTR_ENTRY
    JP ML_BANK0

ML_TARGET_FAILED:
    POP AF
    RET
ML_TARGET_CHECK:
; 未測定の0/FFFF番地は暴走させずERR 5。定義済みフラグとは独立に検査する。
    LD A,B
    OR C
    JP Z,ML_ILLEGAL
    LD A,B
    AND C
    CP 255
    JP Z,ML_ILLEGAL
    JP ML_OK

ML_SCRUB:
; 呼出枠への移動後、一時コピーだけを無効化する。使用中の評価枠は残す。
    PUSH AF
    PUSH BC
    PUSH DE
    PUSH HL
    LD HL,ML3_SCRUB_ENTRY
    CALL ML_BANK3
    CALL ML_CLEAR_CPU
    POP HL
    POP DE
    POP BC
    POP AF
    RET

; 関数名は第2文字も英字（FN接頭辞を含む）。一文字変数・配列の
; 読出しで予約語表の二つのバンクへ毎回入らない。値の解釈は変更しない。
ML_FUNC_CANDIDATE:
    CALL SKIP_SPACES
; PEEで始まる名前は常駐PEEKか通常変数。追加予約語/FNの候補ではない。
    LD HL,(CUR_PTR)
    LD A,(HL)
    AND 0DFh
    CP 'P'
    JP NZ,ML_FUNC_SECOND
    INC HL
    LD A,(HL)
    AND 0DFh
    CP 'E'
    JP NZ,ML_FUNC_SECOND
    INC HL
    LD A,(HL)
    AND 0DFh
    CP 'E'
    JP Z,ML_NO
ML_FUNC_SECOND:
    CALL PEEK_CHAR2
    CALL FOLD_UPPER
    CP 'A'
    JP C,ML_NO
    CP 'Z'+1
    JP NC,ML_NO
    LD A,1
    OR A
    RET
ML_TRY_NUM:
    CALL ML_FUNC_CANDIDATE
    RET Z
    CALL T3_RHS
    OR A
    RET NZ
    LD HL,06B10h
    XOR A
    JP EXT_BANK_CALL
ML_TRY_STR:
    CALL ML_FUNC_CANDIDATE
    RET Z
    CALL T3_RHS
    OR A
    RET NZ
    LD HL,06B20h
    XOR A
    JP EXT_BANK_CALL

; 単精度の正の16bit整数番地はMBFの末尾2Bから厳密に得られる。
; 小数・倍精度・他の指数は既存のaway丸めへ戻す。PEEK/POKEの意味は保つ。
ML_ADDRESS_FAST:
    LD A,(CUR_TYPE)
    CP 1
    JP NZ,ML_NO
    LD A,(CUR_DATA+3)
    CP 144
    JP NZ,ML_NO
    LD A,(CUR_DATA+2)
    BIT 7,A
    JP NZ,ML_NO
    OR 128
    LD D,A
    LD A,(CUR_DATA)
    OR A
    JP NZ,ML_NO
    LD A,(CUR_DATA+1)
    LD E,A
    LD A,1
    RET

ML_CLEAR_CPU:
; 戻り番地より下の未使用CPUスタックを消す。消去中は新たにCALLしない。
    LD HL,0
    ADD HL,SP
    EX DE,HL
    LD HL,MM_FN_CPU_BOTTOM
    OR A
    SBC HL,DE
    RET NC
    LD HL,MM_FN_CPU_BOTTOM
ML_CPU_ZERO:
    LD A,H
    CP D
    JP NZ,ML_CPU_STORE
    LD A,L
    CP E
    RET Z
ML_CPU_STORE:
    LD (HL),0
    INC HL
    JP ML_CPU_ZERO
