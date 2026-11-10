; ファイル文専用。ROM表示切替中だけ割込みを禁止する。
    ORG 0 ; ビルド時にMM_N_ROM_CALLへ置換する
n_complex_call:
    CALL n_complex_toggle
    CALL n_complex_jump_hl
    JP n_complex_toggle
n_complex_toggle:
    DI
    PUSH AF
    PUSH BC
    LD A,(MM_N_ACTIVE)
    XOR 4
    LD (MM_N_ACTIVE),A
    LD B,A
    LD A,(MM_SCR_P31)
    OR B
    OUT (0x31),A
    POP BC
    POP AF
    EI
    RET
n_complex_call_end:
    ORG 0 ; ビルド時にMM_N_PROBEへ置換する
n_complex_callback:
    CALL n_complex_toggle
    CALL n_complex_jump_ix
    JP n_complex_toggle
n_complex_jump_ix:
    JP (IX)
    DB 0
n_complex_jump_hl:
    JP (HL)
n_complex_callback_end:
