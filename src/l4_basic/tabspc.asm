; docs/spec/l4-program.md 4.20の観測から独立実装。本体はバンク0（deffn.asmの後ろへ連結）。
; TAB(・SPC(（PRINTの項目）、POS・CSNG・CSRLIN（数値の関数）、XOR・EQV・IMP（論理）、
; 倍精度を含む数値比較（4.20.3）。mainに置くのは入口の中継だけ。
; 式の字句はバンクからRAMを直接読む（窓の復元中にバンクの文字列を読まないため）。
; 未測定・自作判断: POSの引数は式として評価するだけで値は使わない。
;   TABの前後の判定は「桁は0〜79、80セルを出した直後は次行の桁0」で数える（4.20.2）。
;   CSRLINは行番号（0始まり）。4.20に記述は無いが、測定器具が行の増分の観測に使う。
;   XOR・EQV・IMPの左右の文字列はVAL_TO_INT16_CUR経由で既存のAND/ORと同じ誤りになる。
;   TAB(・SPC(の直前の語が'('のとき（HEX$(TAB(…など）はPRINTの項目として扱わない。
;   数値比較は整数どうしだけ窓内で完結し、それ以外は既存の単精度比較、
;   どちらかが倍精度なら倍精度の比較（MBF_DCMP）へ回す。
; 入口（main中継の固定番地）。deffn.asmの末尾（0x743B）より後ろ。
    ORG 0x7450
    JP ts_logic
    ORG 0x7460
    JP ts_compare

; ---- RAMを直接読む字句の補助（A,HL,DEを壊す。BCは保つ） ----
ts_peek:
    LD HL,(MM_CUR_PTR)
    LD DE,(MM_LINE_END)
    OR A
    SBC HL,DE
    JR NC,ts_peek_end
    ADD HL,DE
    LD A,(HL)
    RET
ts_peek_end:
    XOR A
    RET

ts_adv:
    LD HL,(MM_CUR_PTR)
    INC HL
    LD (MM_CUR_PTR),HL
    RET

ts_skip:
    CALL ts_peek
    CP ' '
    RET NZ
    CALL ts_adv
    JR ts_skip

; HL=大文字のNUL終端語。現在位置が大小不問で一致し、直後が英字でなければ
; A=1でCUR_PTRを語の後ろへ進める。不一致はA=0でCUR_PTR不変。BCを保つ。
ts_kw:
    PUSH BC
    LD DE,(MM_CUR_PTR)
ts_kw_loop:
    LD A,(HL)
    OR A
    JR Z,ts_kw_tail
    LD B,A
    PUSH HL
    LD HL,(MM_LINE_END)
    OR A
    SBC HL,DE
    POP HL
    JR C,ts_kw_fail
    JR Z,ts_kw_fail
    LD A,(DE)
    CP 'a'
    JR C,ts_kw_cmp
    CP 'z'+1
    JR NC,ts_kw_cmp
    SUB 32
ts_kw_cmp:
    CP B
    JR NZ,ts_kw_fail
    INC HL
    INC DE
    JR ts_kw_loop
ts_kw_tail:
    LD HL,(MM_LINE_END)
    OR A
    SBC HL,DE
    JR C,ts_kw_ok
    JR Z,ts_kw_ok
    LD A,(DE)
    CP 'a'
    JR C,ts_kw_up
    CP 'z'+1
    JR NC,ts_kw_up
    SUB 32
ts_kw_up:
    CP 'A'
    JR C,ts_kw_ok
    CP 'Z'+1
    JR NC,ts_kw_ok
ts_kw_fail:
    POP BC
    XOR A
    RET
ts_kw_ok:
    LD (MM_CUR_PTR),DE
    POP BC
    LD A,1
    RET

; ---- mainの呼び先 ----
ts_valpush:
    LD IX,TS_VPUSH_ADDR
    JP FN_MAIN_CALL_ADDR
TS_VPUSH_ADDR EQU 0x1787
ts_valpop:
    LD IX,TS_VPOP_ADDR
    JP FN_MAIN_CALL_ADDR
TS_VPOP_ADDR EQU 0x1787
ts_valdiscard:
    LD IX,TS_VDISCARD_ADDR
    JP FN_MAIN_CALL_ADDR
TS_VDISCARD_ADDR EQU 0x1787
ts_or_level:
    LD IX,TS_ORLEVEL_ADDR
    JP FN_MAIN_CALL_ADDR
TS_ORLEVEL_ADDR EQU 0x1787
ts_putc:
    LD IX,TS_PUTC_ADDR
    JP FN_MAIN_CALL_ADDR
TS_PUTC_ADDR EQU 0x1787
ts_newline:
    LD IX,TS_NEWLINE_ADDR
    JP FN_MAIN_CALL_ADDR
TS_NEWLINE_ADDR EQU 0x1787
ts_load_opa:
    LD IX,TS_LOADOPA_ADDR
    JP FN_MAIN_CALL_ADDR
TS_LOADOPA_ADDR EQU 0x1787
ts_load_opb:
    LD IX,TS_LOADOPB_ADDR
    JP FN_MAIN_CALL_ADDR
TS_LOADOPB_ADDR EQU 0x1787
ts_mbf_cmp:
    LD IX,TS_MBFCMP_ADDR
    JP FN_MAIN_CALL_ADDR
TS_MBFCMP_ADDR EQU 0x1787
ts_load_opa_d:
    LD IX,TS_LOADOPA_D_ADDR
    JP FN_MAIN_CALL_ADDR
TS_LOADOPA_D_ADDR EQU 0x1787
ts_load_opb_d:
    LD IX,TS_LOADOPB_D_ADDR
    JP FN_MAIN_CALL_ADDR
TS_LOADOPB_D_ADDR EQU 0x1787
ts_dcmp:
    LD IX,TS_DCMP_ADDR
    JP FN_MAIN_CALL_ADDR
TS_DCMP_ADDR EQU 0x1787
ts_zone:
    LD IX,TS_ZONE_ADDR
    JP FN_MAIN_CALL_ADDR
TS_ZONE_ADDR EQU 0x1787

; ===================== XOR・EQV・IMP =====================
; mainのLOGIC_OR_EXPRが、OR段の値を作ったあと次の語がX/E/Iで始まるときだけ入る。
; CUR_TYPE/CUR_DATA=OR段の値。優先順位はOR>XOR>EQV>IMP（弱くなる順）。
; B=1:XOR 2:EQV 3:IMP。各段の右辺は一段強い段（0はmainのOR段）。
ts_logic:
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
    CALL ts_peek
    AND 0DFh
    CP 'X'
    JR Z,ts_logic_go
    CP 'E'
    JR Z,ts_logic_go
    CP 'I'
    RET NZ
ts_logic_go:
    LD B,1
ts_logic_next:
    PUSH BC
    CALL ts_lg_loop
    POP BC
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
    INC B
    LD A,B
    CP 4
    JR C,ts_logic_next
    RET

; B=段(1〜3)の右辺。段0はmainのOR段。誤りはERROR_FLAGで返す。
ts_lg_level:
    LD A,B
    OR A
    JP Z,ts_or_level
    PUSH BC
    DEC B
    CALL ts_lg_level
    POP BC
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
; B=段。CUR=左辺。同じ段の演算子が続く限り左結合で畳む。
ts_lg_loop:
    CALL ts_skip
    LD A,B
    DEC A
    ADD A,A
    ADD A,A
    LD E,A
    LD D,0
    LD HL,ts_ops
    ADD HL,DE
    CALL ts_kw
    OR A
    RET Z
    PUSH BC
    CALL ts_valpush
    POP BC
    RET C
    PUSH BC
    DEC B
    CALL ts_lg_level
    POP BC
    LD A,(MM_ERROR_FLAG)
    OR A
    JR NZ,ts_lg_err
    PUSH BC
    CALL fn_to_int
    POP BC
    JR C,ts_lg_ovfl_pop
    PUSH DE
    PUSH BC
    CALL ts_valpop
    CALL fn_to_int
    POP BC
    POP HL
    JR C,ts_lg_ovfl
    LD A,B
    CP 2
    JR C,ts_lg_xor
    JR Z,ts_lg_eqv
    LD A,D
    CPL
    OR H
    LD H,A
    LD A,E
    CPL
    OR L
    LD L,A
    JR ts_lg_set
ts_lg_eqv:
    LD A,D
    XOR H
    CPL
    LD H,A
    LD A,E
    XOR L
    CPL
    LD L,A
    JR ts_lg_set
ts_lg_xor:
    LD A,D
    XOR H
    LD H,A
    LD A,E
    XOR L
    LD L,A
ts_lg_set:
    PUSH BC
    CALL fn_set_int
    POP BC
    XOR A
    LD (MM_ERROR_FLAG),A
    JR ts_lg_loop
ts_lg_err:
    PUSH BC
    CALL ts_valdiscard
    POP BC
    RET
ts_lg_ovfl_pop:
    PUSH BC
    CALL ts_valdiscard
    POP BC
ts_lg_ovfl:
    JP fn_overflow

ts_ops:
    DB "XOR",0,"EQV",0,"IMP",0

; ===================== PRINTのTAB(・SPC( =====================
; FN_IS_STRING（main、PRINT項目の先頭。バンク0の0x6B60）から。
; A=0数値の項目、1文字列の項目（従来のfn_is_string）。2=TAB/SPCを出して区切りまで
; 読み進めた（呼び元はループの先頭から続ける。誤りはERROR_FLAGに置き、CUR_PTRを
; 行末へ進めてA=2で返す）。TAB/SPCで終わる文に改行は付けない（SUPPRESS_NLを立てる）。
ts_print:
    CALL ts_skip
    LD HL,(MM_CUR_PTR)
    PUSH HL
ts_print_prev:
    DEC HL
    LD A,(HL)
    CP ' '
    JR Z,ts_print_prev
    CP '('
    JR Z,ts_print_none
    LD HL,ts_w_tab
    CALL ts_kw
    LD C,0
    OR A
    JR NZ,ts_print_hit
    LD HL,ts_w_spc
    CALL ts_kw
    LD C,1
    OR A
    JR NZ,ts_print_hit
ts_print_none:
    POP HL
    JP fn_is_string
ts_print_hit:
    CALL ts_peek
    CP '('
    JR NZ,ts_print_back
    PUSH BC
    CALL ts_adv
    CALL ts_arg
    POP BC
    LD A,(MM_ERROR_FLAG)
    OR A
    JR NZ,ts_print_err
    PUSH BC
    CALL fn_int
    POP BC
    OR A
    JR NZ,ts_print_range_ok
    CALL fn_overflow
    JR ts_print_err
ts_print_range_ok:
    CALL ts_mod80
    LD B,A
    LD A,C
    OR A
    JR NZ,ts_print_spc
    LD A,(MM_VAR_COL)
    CP B
    JR Z,ts_print_done
    JR C,ts_print_pad
    PUSH BC
    CALL ts_newline
    POP BC
    XOR A
ts_print_pad:
    LD C,A
    LD A,B
    SUB C
    LD B,A
ts_print_spc:
    CALL ts_spaces
ts_print_done:
    POP HL
    LD A,1
    LD (MM_SUPPRESS_NL),A
    CALL ts_skip
    CALL ts_peek
    CP ';'
    JR NZ,ts_print_comma
    CALL ts_adv
    JR ts_print_ret
ts_print_comma:
    CP ','
    JR NZ,ts_print_ret
    CALL ts_adv
    CALL ts_zone
ts_print_ret:
    LD A,2
    RET
ts_print_back:
    POP HL
    LD (MM_CUR_PTR),HL
    JP fn_is_string
ts_print_err:
    POP HL
    LD HL,(MM_LINE_END)
    LD (MM_CUR_PTR),HL
    LD A,1
    LD (MM_SUPPRESS_NL),A
    LD A,2
    RET

ts_w_tab:
    DB "TAB",0
ts_w_spc:
    DB "SPC",0

; DE=符号付き16bit。0以下は0、正なら80で割った余り。A=結果。
ts_mod80:
    BIT 7,D
    JR NZ,ts_mod80_zero
    LD H,D
    LD L,E
    LD DE,80
ts_mod80_loop:
    OR A
    SBC HL,DE
    JR NC,ts_mod80_loop
    ADD HL,DE
    LD A,L
    RET
ts_mod80_zero:
    XOR A
    RET

; B個の空白をPRINT_CHARで出す（折り返しは既存どおり）。
ts_spaces:
    LD A,B
    OR A
    RET Z
ts_spaces_loop:
    PUSH BC
    LD A,' '
    CALL ts_putc
    POP BC
    DJNZ ts_spaces_loop
    RET

; '('消費済みの位置から式を1個読み、')'を確認する。誤りはERROR_FLAG。
ts_arg:
    CALL fn_expr
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
    CALL ts_skip
    CALL ts_peek
    CP ')'
    JP NZ,fn_syntax
    JP ts_adv

; ===================== 式の中の TAB(・SPC(・POS・CSNG・CSRLIN =====================
; FN_TRY_NUM（バンク0の0x6B10）から。数値の項の先頭で呼ばれる。A=1で処理済み
; （CUR_TYPE/CUR_DATAに値、またはERROR_FLAG）。A=0は何もせず従来のFN判定へ。
ts_try:
    LD HL,(MM_CUR_PTR)
    PUSH HL
    LD HL,ts_names
ts_try_next:
    LD A,(HL)
    OR A
    JR Z,ts_try_none
    LD C,A
    INC HL
    PUSH HL
    PUSH BC
    CALL ts_kw
    POP BC
    POP HL
    OR A
    JR NZ,ts_try_hit
ts_try_skip:
    LD A,(HL)
    INC HL
    OR A
    JR NZ,ts_try_skip
    JR ts_try_next
ts_try_none:
    POP HL
    XOR A
    JP fn_try
ts_try_hit:
    LD A,C
    CP 5
    JR Z,ts_csrlin
    CALL ts_peek
    CP '('
    JR NZ,ts_try_back
    CALL ts_adv
    LD A,C
    CP 3
    JR NC,ts_try_syntax
    PUSH BC
    CALL ts_arg
    POP BC
    LD A,(MM_ERROR_FLAG)
    OR A
    JR NZ,ts_try_done
    LD A,C
    CP 2
    JR Z,ts_pos
; CSNG: 整数・倍精度を単精度へ（倍精度は既存のMBF_DTOS＝半端は絶対値の大きい側）。
    LD A,(MM_CUR_TYPE)
    CP 1
    JR Z,ts_try_done
    CALL ts_load_opa
    LD HL,MM_MBF_OPA
    LD DE,MM_CUR_DATA
    LD BC,4
    LDIR
    XOR A
    LD B,4
ts_csng_zero:
    LD (DE),A
    INC DE
    DJNZ ts_csng_zero
    LD A,1
    LD (MM_CUR_TYPE),A
    JR ts_try_done
ts_pos:
    LD A,(MM_VAR_COL)
    JR ts_try_int
ts_csrlin:
    LD A,(MM_VAR_ROW)
ts_try_int:
    LD L,A
    LD H,0
    CALL fn_set_int
ts_try_done:
    POP HL
    LD A,1
    RET
ts_try_syntax:
    CALL fn_syntax
    JR ts_try_done
ts_try_back:
    POP HL
    LD (MM_CUR_PTR),HL
    XOR A
    JP fn_try

ts_names:
    DB 1,"CSNG",0
    DB 2,"POS",0
    DB 3,"TAB",0
    DB 4,"SPC",0
    DB 5,"CSRLIN",0
    DB 0

; ===================== 数値の比較（VAL_COMPARE_CUR_RHSの本体） =====================
; 入口はmainのVAL_COMPARE_CUR_RHS。出力: A=0等しい/1 CUR>RHS/0xFF CUR<RHS。
; 整数どうしは窓内で符号付き比較。どちらかが倍精度なら両方を倍精度へ揃えてMBF_DCMP、
; それ以外は従来どおり単精度へ揃えてMBF_CMP（4.20.3: csng(1/3#)>1/3# は真）。
TS_DOUT_CMP EQU MM_MBF_DOUBLE_RAM_BASE+0x18
ts_compare:
    LD A,(MM_CUR_TYPE)
    LD B,A
    LD A,(MM_RHS_TYPE)
    LD C,A
    OR B
    JR Z,ts_cmp_int
    LD A,B
    OR C
    AND 2
    JR NZ,ts_cmp_double
    CALL ts_load_opa
    CALL ts_load_opb
    CALL ts_mbf_cmp
    LD A,(MM_MBF_OUT_CMP)
    RET
ts_cmp_double:
    CALL ts_load_opa_d
    CALL ts_load_opb_d
    CALL ts_dcmp
    LD A,(TS_DOUT_CMP)
    RET
ts_cmp_int:
    LD HL,(MM_CUR_DATA)
    LD DE,(MM_RHS_DATA)
    OR A
    SBC HL,DE
    JR Z,ts_cmp_eq
    JP PO,ts_cmp_nov
    JP P,ts_cmp_lt
    JR ts_cmp_gt
ts_cmp_nov:
    JP M,ts_cmp_lt
ts_cmp_gt:
    LD A,1
    RET
ts_cmp_lt:
    LD A,0FFh
    RET
ts_cmp_eq:
    XOR A
    RET
