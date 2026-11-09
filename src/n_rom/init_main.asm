N_RELAY_COPY:
    LD HL,MM_N_RELAY_SOURCE
    LD DE,N_ROM_CALL
    LD BC,31
    LDIR
    LD DE,MM_N_PROBE
    LD BC,15
    LDIR
    RET
; 最初のN側命令だけで検査。読み出し中のみ割込みを禁止する。
N_DETECT:
    LD A,(MM_N_ROM_PRESENT)
    OR A
    RET NZ                     ; 一度検出した結果はRUNを跨いで保持する。
    CALL N_RELAY_COPY
    DI
    LD A,(MM_SCR_P31)
    LD C,A
    LD HL,0x0038
    CALL MM_N_PROBE
    CP 0xFB
    JR NZ,n_detect_absent
    LD HL,0x0066
    CALL MM_N_PROBE
    CP 0xED
    JR NZ,n_detect_absent
    LD HL,0x7600
    CALL MM_N_PROBE
    CP 0xCD
    JR NZ,n_detect_absent
    LD A,1
    JR n_detect_done
n_detect_absent:
    LD A,2
n_detect_done:
    LD (MM_N_ROM_PRESENT),A
    EI
    RET
