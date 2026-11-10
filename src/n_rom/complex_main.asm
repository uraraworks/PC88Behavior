; ファイル文だけ双方向中継を使い、終了時に通常中継を復元する。
; PRESENTのbit7は中継配置中を示す。他のN呼出しは下位bitで有無を判定する。
; main→N→main→Nと入れ子になる場合は二重配置せず現在の中継を使う。
N_COMPLEX_CALL:
    PUSH AF
    PUSH HL
    LD A,(MM_N_ROM_PRESENT)
    BIT 7,A
    JR NZ,_n_complex_nested
    CALL N_DETECT
    LD A,(MM_N_ROM_PRESENT)
    CP 1
    JR NZ,_n_complex_absent
    DI
    LD HL,MM_N_RELAY_SOURCE+46
    LD DE,MM_N_ROM_CALL
    LD BC,31
    LDIR
    LD DE,MM_N_PROBE
    LD BC,15
    LDIR
    LD HL,MM_N_ROM_PRESENT
    SET 7,(HL)
    EI
    POP HL
    POP AF
    CALL MM_N_ROM_CALL
    PUSH AF
    PUSH BC
    PUSH DE
    PUSH HL
    DI
    CALL N_RELAY_COPY
    LD HL,MM_N_ROM_PRESENT
    RES 7,(HL)
    EI
    POP HL
    POP DE
    POP BC
    POP AF
    RET
_n_complex_nested:
    POP HL
    POP AF
    JP MM_N_ROM_CALL
_n_complex_absent:
    POP HL
    POP AF
    LD A,5
    JP ERR_SET_A
