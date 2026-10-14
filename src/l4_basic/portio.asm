; docs/spec/l4-program.md 4.23。未測定の正常OUTは検証だけで書き込まない。
; 自作判断: ポートは既存PEEK番地変換のaway丸めと下位8bit。
; WAITは整合した仮説の条件を実際にポーリングする。
    ORG 0x7BF0
T3_STMT_ENTRY:
    CALL S9_IS_STRING
    OR A
    JP NZ,S9_TYPE
    CALL S9B_EXPR
    CALL S9_BAD
    RET NZ
    CALL S9B_ADDRESS_CUR
    CALL S9_BAD
    RET NZ
    PUSH DE
    CALL S9_COMMA
    CALL S9_BAD
    JR NZ,t3_port_fail_one
    CALL S9_BYTE_ARG
    CALL S9_BAD
    JR NZ,t3_port_fail_one
    LD A,(MM_RUN_STMT_KIND)
    CP 54                       ; OUT（KEY=53の次）
    JR Z,t3_out_done
    PUSH DE                     ; WAITのマスク
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP ','
    LD DE,0
    JR NZ,t3_wait_tail
    CALL B3_ADV_PTR
    CALL S9_BYTE_ARG
    CALL S9_BAD
    JR NZ,t3_port_fail_two
t3_wait_tail:
    PUSH DE                     ; XOR値
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    OR A
    JR Z,t3_wait_ready
    CP ':'
    JR Z,t3_wait_ready
    POP DE
    LD A,2
    CALL S9_ERROR
    JR t3_port_fail_two
t3_wait_ready:
    POP DE
    POP HL
    POP BC
    LD D,E                      ; D=XOR、E=mask、C=port
    LD E,L
    LD B,0
t3_wait_loop:
    IN A,(C)
    XOR D
    AND E
    JR Z,t3_wait_loop
    JP S9_OK
t3_out_done:
    POP DE
    JP S9_OK
t3_port_fail_two:
    POP DE
t3_port_fail_one:
    POP DE
    RET
T3_PORTIO_END:
