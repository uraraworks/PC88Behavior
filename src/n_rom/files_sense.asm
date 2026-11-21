; FILES専用。N側からmain通信を呼び、応答を1バイト受け切る。
    ORG 0x4F00
    LD IX,FS_MAIN_SUB_SEND_LOGICAL_ONCE
    CALL MM_N_PROBE
    JR NC,fs_logical_ready
    ; 起動専用RECVに先頭だけ消費された場合は最初から送る。
    LD IX,FS_MAIN_SUB_SEND_LOGICAL_ONCE
    CALL MM_N_PROBE
    JR C,fs_ok
fs_logical_ready:
    LD A,014h
    LD IX,FS_MAIN_SUB_SEND
    CALL MM_N_PROBE
    JR C,fs_ok
    LD A,(MM_FILES_DRIVE)
    LD IX,FS_MAIN_SUB_SEND_CONT
    CALL MM_N_PROBE
    JR C,fs_ok
    LD IX,FS_MAIN_SUB_RECV
    CALL MM_N_PROBE
    JR C,fs_ok
    AND 8
    JR NZ,fs_ok
    LD A,33
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
    OR A
    RET
fs_ok:
    XOR A
    RET
