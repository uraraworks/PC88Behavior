; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x62E1
ml3_part_62e1:
; §4.24.1 CALL。文種別56。先頭は数値変数のみ、引数も実格納先を渡す。
ML3_STMT_ENTRY:
    LD A,(MM_RUN_STMT_KIND)
    CP 56
    JP NZ,T3_STMT_ENTRY
    CALL B3_SKIP_SPACES
    CALL B3_LEX_IDENT_CONSUME
    OR A
    JP Z,ml3_syntax
    CP 3
    JP Z,S9_TYPE
    CALL ml3_var_read
; 関数途中の空隙接続。次は0x63F0。
    JP ml3_part_63f0
