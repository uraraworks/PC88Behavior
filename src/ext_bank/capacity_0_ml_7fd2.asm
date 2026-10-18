; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7FD2
ml0_part_7fd2:
    JP Z,ml0_lvalue_string
    LD A,C
    OR A
    RET NZ
    INC HL
    INC HL
    RET
ml0_lvalue_string:
    LD A,C
    OR A
    RET NZ
    LD A,(HL)
    CP 2
    INC HL
    RET Z
; 短い文字列も既存ページを所有するkind=2に昇格。通常の読取/解放を共用し、
; 再代入は既存規則で短形式に戻せる（以前のVARPTRの寿命は未規定）。
    PUSH HL
    LD HL,FN_PAGE_ALLOC_ENTRY
    CALL fn_bank3
    POP HL
    OR A
    JP Z,fn_memory
    DEC HL
    LD (HL),2
    INC HL
    PUSH HL
    LD B,(HL)
    INC HL
    LD DE,(MM_FN_WORK)
    PUSH HL
    PUSH DE
; 関数途中の空隙接続。次は0x6204。
    JP ml0_part_6204
