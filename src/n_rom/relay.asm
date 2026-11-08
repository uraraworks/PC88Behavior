; 固定RAM中継。呼出元は割込み許可状態、HL=呼出先。AFは入力に使わない。
; DIは写しと表示切替を同期する数命令の間だけ。N側実行中はEI。
    ORG 0 ; ビルド時にMM_N_ROM_CALLへ置換する
n_call:
    DI
    LD A,4
    LD (MM_N_ACTIVE),A
    LD A,(MM_SCR_P31)
    OR 4
    OUT (0x31),A
    EI
    CALL n_jump_hl
    PUSH AF
    DI
    LD A,(MM_SCR_P31)
    OUT (0x31),A
    XOR A
    LD (MM_N_ACTIVE),A
    EI
    POP AF
    RET
n_call_end:
    ORG 0 ; ビルド時にMM_N_PROBEへ置換する
; 初回検出専用。HL=検査番地、C=31hの写し。割込み禁止状態で呼ぶ。
n_probe:
    LD A,C
    OR 4
    OUT (0x31),A
    LD A,(HL)
    LD B,A
    LD A,C
    OUT (0x31),A
    LD A,B
    RET
n_jump_hl:
    JP (HL)
n_probe_end:
