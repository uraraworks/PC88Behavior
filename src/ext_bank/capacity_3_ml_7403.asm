; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7403
ml3_part_7403:
ML3_ADDRESS_ENTRY:
    JP S9B_ADDRESS_CUR
ML3_USR_ENTRY:
    LD A,E
    CP 10
    JP NC,ml3_syntax
; E=番号。括弧と引数を先に検査し、未定義番号でも過多引数はERR 2。
; 番号は評価中CPUスタックに保持し、正常な引数のときだけ定義表を探す。
    PUSH DE
; 関数途中の空隙接続。次は0x7413。
    JP ml3_part_7413
