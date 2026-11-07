; 既存INKEYキュー処理を主ROMへ移設。
; RUN開始時点の押下を既読とする。開始RETURNを混入させない。
IK_INIT:
    XOR A
    LD (MM_IK_HEAD),A
    LD (MM_IK_TAIL),A
    LD (MM_IK_COUNT),A
    LD (MM_IK_CHAR),A
    LD (MM_IK_TIMER),A
; l4-basic.md 26: コマンド確定のRETURNは既読にし、FIFOは保持する。
IK_SYNC_HELD:
    IN A,(040h)
    AND 020h
    LD (MM_IK_VRTC),A
    LD C,0
    LD HL,MM_IK_OLD
ik_init_port:
    IN A,(C)
    LD (HL),A
    INC HL
    INC C
    LD A,C
    CP 12
    JR NZ,ik_init_port
    RET



IK_TRY:
    LD HL,MM_IDENT_BUF              ; IDENT_BUF: 接尾辞はIDENT_KINDで判定済み
    LD DE,IK_NAME
    LD B,7
ik_match:
    LD A,(DE)
    CP (HL)
    JR NZ,ik_not_name
    INC HL
    INC DE
    DJNZ ik_match
    XOR A
    LD (MM_RUN_STR_TMP_LEN),A
    LD A,(MM_IK_COUNT)
    OR A
    JR Z,ik_read_done
    DEC A
    LD (MM_IK_COUNT),A
    LD A,(MM_IK_HEAD)
    LD E,A
    LD D,0
    LD HL,MM_IK_BUF
    ADD HL,DE
    LD A,(HL)
    LD (MM_RUN_STR_TMP_BUF),A
    LD A,(MM_IK_HEAD)
    INC A
    AND 31
    LD (MM_IK_HEAD),A
    LD A,1
    LD (MM_RUN_STR_TMP_LEN),A
ik_read_done:
    XOR A
    LD (ERROR_FLAG),A
    LD A,1
    RET
ik_not_name:
    XOR A
    RET
IK_NAME:
    DB "INKEY",0,0

