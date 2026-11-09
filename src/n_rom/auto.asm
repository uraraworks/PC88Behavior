; l4-program.md 10.2: AUTO の引数と既定値。
    ORG 0x2000
auto_stmt_n:
    LD HL,10
    LD (MM_AUTO_NUMBER),HL
    LD (MM_AUTO_STEP),HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR NZ,_auto_start_number
    LD HL,0
    LD (MM_AUTO_NUMBER),HL
    JR _auto_comma
_auto_start_number:
    OR A
    JR Z,_auto_ready
    CP ':'
    JR Z,_auto_ready
    CALL PARSE_LINENUM_CUR
    JP C,auto_n_syntax
    LD (MM_AUTO_NUMBER),HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR NZ,_auto_end
_auto_comma:
    CALL ADV_PTR
    CALL SKIP_SPACES
    CALL PARSE_LINENUM_CUR
    JP C,auto_n_syntax
    LD A,H
    OR L
    JP Z,auto_n_illegal
    LD (MM_AUTO_STEP),HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
_auto_end:
    OR A
    JR Z,_auto_ready
    CP ':'
    JP NZ,auto_n_syntax
_auto_ready:
    LD HL,(MM_AUTO_NUMBER)
    LD DE,65530
    OR A
    SBC HL,DE
    JR C,auto_ready_in_range
    LD A,(MM_AUTO_ACTIVE)
    AND 9
    LD (MM_AUTO_ACTIVE),A
    XOR A
    LD (MM_ERROR_FLAG),A
    RET
auto_ready_in_range:
    LD A,(MM_AUTO_ACTIVE)
    AND 9
    OR 2
    LD (MM_AUTO_ACTIVE),A
    XOR A
    LD (MM_ERROR_FLAG),A
    RET
auto_n_syntax:
    LD A,2
    JP ERR_SET_A
auto_n_illegal:
    LD A,5
    JP ERR_SET_A
