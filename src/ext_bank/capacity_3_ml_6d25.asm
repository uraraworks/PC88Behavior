; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6D25
ml3_part_6d25:
    JP t3_rhs_args

; USRへ渡した値の所有権は呼出枠へ移す。評価済みの一時値を無効化する。
; 利用者の変数・配列・文字列、使用中の式評価スタックは変更しない。
ML3_SCRUB_ENTRY:
    LD HL,MM_CUR_DATA
    LD B,8
; 関数途中の空隙接続。次は0x72F4。
    JP ml3_part_72f4
