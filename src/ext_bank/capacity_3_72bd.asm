; c1: DATA_SCAN。自作mainから移動、規則/処理は維持。
    ORG 0x72BD
DATA_SCAN:
_ds_stmt_loop:
    CALL AT_END
    JR Z,_ds_next_record
    CALL SKIP_SPACES
    CALL AT_END
    JR Z,_ds_next_record
    CALL TRY_MATCH_DATA_KW
    OR A
    JR NZ,_ds_found
    CALL RUN_SKIP_REST_OF_STATEMENT
    CALL AT_END
    JR Z,_ds_next_record
    CALL PEEK_CHAR
    CP ':'
    JR NZ,_ds_next_record
    CALL ADV_PTR
    JR _ds_stmt_loop
_ds_next_record:
    CALL DATA_ADVANCE_RECORD
    OR A
    JR Z,_ds_exhausted
    JR _ds_stmt_loop
_ds_found:
    CALL SKIP_SPACES
    LD A,1
    RET
_ds_exhausted:
    XOR A
    RET
