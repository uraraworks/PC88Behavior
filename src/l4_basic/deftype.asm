;
; docs/spec/l4-program.md 4.21の観測から独立実装。本体はバンク0（deffn.asmの後ろへ連結）。
; DEFINT・DEFSNG・DEFDBL・DEFSTR。英字26文字の型表（MM_DEFTYPE_TAB）へ、単精度=0・
; 整数='%'・文字列='$'・倍精度='#' を書く。表を引くのはmainのLEX_IDENT_PEEKの1か所。
; 書式は「英字[-英字]{,英字[-英字]}」。範囲ごとに検査してから書き込み、失敗した範囲より
; 前は残す（4.21.2）。範囲を書いたあと、続きが','なら次の範囲、それ以外は文を返す
; （余りの文字はmainの文末検査がERR 2にする）。
; 未測定・自作判断: 範囲の英字は大文字小文字を区別しない。

; ---- mainからの固定入口（tabspc.asmの末尾0x77B8より後ろ。各16B間隔）
    ORG 0x77C0
    JP dt_convert
    ORG 0x77D0
    JP dt_convert_name
    ORG 0x77E0
    JP dt_intdiv
    ORG 0x77F0
    JP dt_modop
    ORG 0x7800
    JP dt_str_noident
    ORG 0x7810
    JP dt_data_fix

; 文の種別(33=DEF 34=SWAP 35=ERASE 36〜39=DEFINT/DEFSNG/DEFDBL/DEFSTR、第4.21節。40=RUN、41=BEEP・42=WIDTH 第4.22節)
fn_stmt_dispatch:
    LD A,(MM_RUN_STMT_KIND)
    CP 33
    JP Z,fn_def
    CP 34
    JP Z,fn_swap
    CP 35
    JP Z,fn_erase
    CP 40
    JP Z,dt_run
    CP 41
    JP Z,wb_beep_stmt
    CP 42
    JP Z,wb_width_stmt
    JP dt_stmt

; 文の語の表（照合順。DEFはDEFINT等より前でも、語の直後が英字なら一致しない）
fn_words:
    DB 3,"LET",5,"WHILE",4,"WEND",3,"DEF",4,"SWAP",5,"ERASE",6,"DEFINT",6,"DEFSNG",6,"DEFDBL",6,"DEFSTR",3,"RUN",4,"BEEP",5,"WIDTH",0

dt_stmt:
dt_next:
    CALL fn_skip
    CALL dt_letter
    JP C,fn_syntax
    LD (MM_FN_AUX),A
    LD (MM_FN_AUX+1),A
    CALL fn_skip
    CALL fn_peek
    CP '-'
    JR NZ,dt_write
    CALL fn_adv
    CALL fn_skip
    CALL dt_letter
    JP C,fn_syntax
    LD (MM_FN_AUX+1),A
    LD B,A
    LD A,(MM_FN_AUX)
    CP B
    JR Z,dt_write
    JP NC,fn_syntax            ; 逆順（c-a）は何も書かない
dt_write:
    LD A,(MM_RUN_STMT_KIND)
    SUB 36
    LD E,A
    LD D,0
    LD HL,dt_chars
    ADD HL,DE
    LD C,(HL)
    LD A,(MM_FN_AUX)
    SUB 'A'
    LD E,A
    LD HL,MM_DEFTYPE_TAB
    ADD HL,DE
    LD A,(MM_FN_AUX+1)
    SUB 'A'
    SUB E
    INC A
    LD B,A
dt_fill:
    LD (HL),C
    INC HL
    DJNZ dt_fill
    CALL fn_skip
    CALL fn_peek
    CP ','
    JP NZ,fn_ok
    CALL fn_adv
    JR dt_next

; 英字なら進めてA=大文字・CF=0、英字でなければCF=1（位置は動かさない）
dt_letter:
    CALL fn_peek
    CALL fn_fold
    CP 'A'
    JR C,dt_letter_no
    CP 'Z'+1
    JR NC,dt_letter_no
    PUSH AF
    CALL fn_adv
    POP AF
    OR A
    RET
dt_letter_no:
    SCF
    RET

dt_chars:
    DB '%',0,'#','$'

; ---- プログラム中の RUN [行番号]（40）。直接モードのRUNと同じ初期化をしてから、GOTOと同じ移り方
; （RUN_CTRL=1）で先頭行または指定行へ入る。4.21.6 の prog-run-line。
; 未測定・自作判断: 指定した行が無いときは初期化のあとERR 8。
dt_run:
    CALL fn_skip
    CALL fn_peek
    OR A
    JR Z,dt_run_all
    CP ':'
    JR Z,dt_run_all
    CALL dt_linenum
    JP C,fn_syntax
    PUSH HL
    CALL dt_reset
    POP HL
    CALL dt_find_line
    JR C,dt_run_undef
    JR dt_run_enter
dt_run_all:
    CALL dt_reset
    LD HL,MM_PROGRAM_AREA
dt_run_enter:
    CALL dt_enter
    LD A,1
    LD (MM_RUN_CTRL),A
    JP fn_ok
dt_run_undef:
    LD A,8
    JP fn_error

dt_linenum:
    LD IX,DT_LINENUM_ADDR
    JP FN_MAIN_CALL_ADDR
DT_LINENUM_ADDR EQU 0x1787
dt_find_line:
    LD IX,DT_FIND_ADDR
    JP FN_MAIN_CALL_ADDR
DT_FIND_ADDR EQU 0x1787
dt_enter:
    LD IX,DT_ENTER_ADDR
    JP FN_MAIN_CALL_ADDR
DT_ENTER_ADDR EQU 0x1787
dt_reset:
    LD IX,DT_RESET_ADDR
    JP FN_MAIN_CALL_ADDR
DT_RESET_ADDR EQU 0x1787

; ---- 代入の型変換（mainのASSIGN_CONVERT_CUR）。CUR_TYPE/CUR_DATAをMM_RUN_ASSIGN_KINDの型へ。
; 1=単精度（倍精度なら単精度へ丸める。整数・単精度はそのまま）、2=整数（CINTの丸め、範囲外ERR 6）、
; 4=倍精度（広げる）。3（文字列）と0は何もしない。誤りはERROR_FLAGで返す。
dt_convert:
    LD A,(MM_RUN_ASSIGN_KIND)
    CP 1
    JP NZ,fn_convert
    LD A,(MM_CUR_TYPE)
    CP 2
    RET NZ
    CALL ts_load_opa           ; 倍精度のCURを単精度へ（既存のMBF_DTOS、CSNGと同じ）
    LD HL,MM_MBF_OPA
    LD DE,MM_CUR_DATA
    LD BC,4
    LDIR
    XOR A
    LD B,4
dt_conv_zero:
    LD (DE),A
    INC DE
    DJNZ dt_conv_zero
    LD A,1
    LD (MM_CUR_TYPE),A
    RET

; 変数名（MM_IDENT_BUFの[7]）の型へ。整数('%')なら整数、それ以外は何もしない。
; （FORの制御変数の初期値・上限・刻み、NEXTの加算結果。単精度の制御変数は従来どおり）
dt_convert_name:
    LD A,(MM_IDENT_BUF+7)
    CP '%'
    LD A,2
    JR Z,dt_cn_set
    XOR A
dt_cn_set:
    LD (MM_RUN_ASSIGN_KIND),A
    JR dt_convert

; ---- 整数除算 \ と MOD（mainのVAL_INTDIV・VAL_MODOPの本体。第4.12節の処理のままmainから移した）
; 両辺を16bit整数へ丸め（範囲外ERR 6）、除数0はERR 11。結果は整数。
dt_intdiv:
    XOR A
    JR dt_idm
dt_modop:
    LD A,1
dt_idm:
    PUSH AF
    CALL fn_to_int
    JR C,dt_idm_ovfl
    LD (MM_RUN_ARITH_L),DE
    CALL dt_to_int_rhs
    JR C,dt_idm_ovfl
    LD (MM_RUN_ARITH_R),DE
    LD A,D
    OR E
    JR Z,dt_idm_div0
    LD HL,(MM_RUN_ARITH_L)
    LD DE,(MM_RUN_ARITH_R)
    CALL dt_sdiv16
    POP AF
    OR A
    JR Z,dt_idm_set
    EX DE,HL                   ; MODは剰余（DE）
dt_idm_set:
    CALL fn_set_int
    JP fn_ok
dt_idm_div0:
    POP AF
    LD A,11
    JP fn_error
dt_idm_ovfl:
    POP AF
    JP fn_overflow
dt_to_int_rhs:
    LD IX,DT_TOINT_RHS_ADDR
    JP FN_MAIN_CALL_ADDR
DT_TOINT_RHS_ADDR EQU 0x1787
dt_sdiv16:
    LD IX,DT_SDIV_ADDR
    JP FN_MAIN_CALL_ADDR
DT_SDIV_ADDR EQU 0x1787

; ---- 文字列を要求する文脈で式が識別子でないとき（mainのPARSE_STRING_RHS）。
; 数値で始まる（数字・'.'・'-'）ならType mismatch(13)、それ以外はSyntax error(2)。
dt_str_noident:
    CALL fn_peek
    CP '-'
    JP Z,fn_type
    CP '.'
    JP Z,fn_type
    CP '0'
    JP C,fn_syntax
    CP '9'+1
    JP C,fn_type
    JP fn_syntax

; ---- DATAの数値項目（mainのDATA_PARSE_NUMBER_LITERAL、LEX_NUMBERの直後）。
; 字句が空で次が','':'行末以外（数字でないDATA）→Syntax error(2)。倍精度の読み先（MM_RUN_ASSIGN_KIND=4）
; には'#'を補い、倍精度の精度で読む（接尾辞があれば補わない）。誤りはERROR_FLAGで返す。
dt_data_fix:
    LD A,(MM_LIT_LEN)
    OR A
    JR NZ,dt_data_have
    CALL fn_peek
    OR A
    JP Z,fn_ok
    CP ','
    JP Z,fn_ok
    CP ':'
    JP Z,fn_ok
    JP fn_syntax
dt_data_have:
    LD A,(MM_RUN_ASSIGN_KIND)
    CP 4
    JP NZ,fn_ok
    LD A,(MM_LIT_HASSUFFIX)
    OR A
    JP NZ,fn_ok
    LD A,(MM_LIT_LEN)
    CP 24
    JP NC,fn_ok
    LD E,A
    LD D,0
    LD HL,MM_LIT_BUF
    ADD HL,DE
    LD (HL),'#'
    INC A
    LD (MM_LIT_LEN),A
    JP fn_ok
