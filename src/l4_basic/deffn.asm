; docs/spec/l4-program.md 4.19の観測から独立実装。本体はバンク0。
; mainへの呼出しはEXT_BANK_MAIN_CALL、再入時の窓状態は既存中継が保存。
; 未測定・自作判断: 最大6仮引数、ヒープ298Bの独立した呼出枠を使う。
; 実引数は全て評価・変換してから束縛。局所文字列も既存255B形式を使う。
; CPUスタックに96Bの余裕を残してERR 7。正確な再帰深さは規定しない。
; 未測定・自作判断: RND/INKEY$を含む本体も通常の式評価経路で一度評価する。
; 未測定・自作判断: 登録は編集/NEW/CLEAR/RUNで記号ヒープと共に消す。
; 未測定・自作判断: 本体の構文は呼出時に検査、無引数の括弧形はERR 2。
; 未測定・自作判断: #と%の変換は既存代入/CINT経路と共有する。
; 空き印付き枠を再利用し、末尾の空きだけ回収。他の番地は動かさない。
; bank3.asmのB3_FN_PAGE_FREE_ENTRY/B3_FN_PAGE_ALLOC_ENTRYの固定入口。
FN_PAGE_FREE_ENTRY EQU 0x61D0
FN_PAGE_ALLOC_ENTRY EQU 0x61D8
    ORG 0x6B00
    JP fn_match_stmt
    ORG 0x6B10
    XOR A
    JP ts_try
    ORG 0x6B20
    LD A,1
    JP fn_try
    ORG 0x6B30
    LD A,(MM_RUN_STMT_KIND)
    CP 33
    JP Z,fn_def
    CP 34
    JP Z,fn_swap
    JP fn_erase
    ORG 0x6B40
    JP fn_array_string_read
    ORG 0x6B50
    JP fn_array_string_assign
    ORG 0x6B60
    JP ts_print

; 既存の大小不問照合へ語をRAM経由で渡す。窓復元中にバンク文字列を読まない。
fn_match_stmt:
    LD HL,fn_words
    LD C,1
fn_match_loop:
    LD A,(HL)
    OR A
    RET Z
    LD B,A
    INC HL
    LD DE,MM_IDENT_BUF
    PUSH BC
    LD C,B
    LD B,0
    LDIR
    POP BC
    PUSH HL
    PUSH BC
    LD A,B
    LD (MM_RUN_KW_LEN),A
    LD HL,MM_IDENT_BUF
    LD (MM_RUN_KW_TEXT),HL
    CALL fn_match
    POP BC
    POP HL
    OR A
    JR NZ,fn_match_yes
    INC C
    JR fn_match_loop
fn_match_yes:
    LD A,C
    RET
fn_words:
    DB 3,"LET",5,"WHILE",4,"WEND",3,"DEF",4,"SWAP",5,"ERASE",0

; FNは予約語の接頭辞。空白も受理し、その後は通常の識別子規則を使う。
; 不一致は位置不変。名前にFNを含めないので7文字の区別も通常変数と同じ。
fn_prefix:
    LD HL,(MM_CUR_PTR)
    PUSH HL
    CALL fn_peek
    CALL fn_fold
    CP 'F'
    JR NZ,fn_prefix_no
    CALL fn_adv
    CALL fn_peek
    CALL fn_fold
    CP 'N'
    JR NZ,fn_prefix_no
    CALL fn_adv
    POP HL
    LD A,1
    RET
fn_prefix_no:
    POP HL
    LD (MM_CUR_PTR),HL
    XOR A
    RET

fn_def:
    LD HL,(MM_RUN_CUR_RECORD)
    LD A,(HL)
    INC HL
    OR (HL)
    LD A,12
    JP Z,fn_error
    CALL fn_skip
    CALL fn_prefix
    OR A
    JP Z,fn_syntax
    CALL fn_skip
    CALL fn_ident
    OR A
    JP Z,fn_syntax
    PUSH AF
    LD A,3
    CALL fn_heap_find
    OR A
    JR NZ,fn_def_have
    LD A,3
    CALL fn_heap_alloc
    OR A
    JR NZ,fn_def_new
    POP AF
    JP fn_memory
fn_def_new:
    PUSH HL
    EX DE,HL
    LD HL,MM_IDENT_BUF
    LD BC,8
    LDIR
    LD A,3
    LD (DE),A
    POP HL
fn_def_have:
    LD (MM_FN_WORK),HL
    LD DE,9
    ADD HL,DE
    LD (HL),0
    INC HL
    POP AF
    LD (HL),A
    CALL fn_skip
    CALL fn_peek
    CP '('
    JR NZ,fn_def_equal
    CALL fn_adv
fn_def_param:
    CALL fn_skip
    CALL fn_ident
    OR A
    JP Z,fn_syntax
    LD HL,(MM_FN_WORK)
    LD DE,9
    ADD HL,DE
    LD A,(HL)
    CP 6
    JP NC,fn_memory
    INC (HL)
    LD L,A
    LD H,0
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    LD DE,15
    ADD HL,DE
    LD DE,(MM_FN_WORK)
    ADD HL,DE
    EX DE,HL
    LD HL,MM_IDENT_BUF
    LD BC,8
    LDIR
    CALL fn_skip
    CALL fn_peek
    CP ','
    JR NZ,fn_def_close
    CALL fn_adv
    JR fn_def_param
fn_def_close:
    CP ')'
    JP NZ,fn_syntax
    CALL fn_adv
fn_def_equal:
    CALL fn_skip
    CALL fn_peek
    CP '='
    JP NZ,fn_syntax
    CALL fn_adv
    CALL fn_skip
    LD HL,(MM_CUR_PTR)
    LD (MM_FN_AUX),HL
    ; 本体の末尾は引用符外のコロンか行末。登録時は評価しない。
    LD C,0
fn_def_scan:
    CALL fn_peek
    OR A
    JR Z,fn_def_end
    CP '"'
    JR NZ,fn_def_colon
    LD A,C
    XOR 1
    LD C,A
    JR fn_def_next
fn_def_colon:
    CP ':'
    JR NZ,fn_def_next
    LD A,C
    OR A
    JR Z,fn_def_end
fn_def_next:
    CALL fn_adv
    JR fn_def_scan
fn_def_end:
    LD HL,(MM_FN_WORK)
    LD DE,11
    ADD HL,DE
    LD DE,(MM_FN_AUX)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD DE,(MM_CUR_PTR)
    LD (HL),E
    INC HL
    LD (HL),D
    JP fn_ok

; A=要求文脈(0=数値、1=文字列)。呼出枠が親を指すため入れ子でも独立。
fn_try:
    PUSH AF
    CALL fn_prefix
    OR A
    JR NZ,fn_try_name
    POP AF
    XOR A
    RET
fn_try_name:
    CALL fn_skip
    CALL fn_ident
    OR A
    JR NZ,fn_try_find
    POP AF
    CALL fn_syntax
    JP fn_handled
fn_try_find:
    LD A,3
    CALL fn_heap_find
    OR A
    JR NZ,fn_try_defined
    POP AF
    LD A,18
    CALL fn_error
    JP fn_handled
fn_try_defined:
    PUSH HL
    LD DE,10
    ADD HL,DE
    LD A,(HL)
    CP 3
    LD A,0
    JR NZ,fn_try_type
    INC A
fn_try_type:
    LD B,A
    POP HL
    POP AF
    CP B
    JR Z,fn_try_room
    CALL fn_type
    JP fn_handled
fn_try_room:
    PUSH HL
    LD HL,0
    ADD HL,SP
    LD DE,MM_FN_CPU_BOTTOM+96
    OR A
    SBC HL,DE
    POP HL
    JR NC,fn_try_frame
    CALL fn_memory
    JP fn_handled
fn_try_frame:
    PUSH HL
    LD A,4
    CALL fn_heap_alloc
    OR A
    JR NZ,fn_frame_allocated
    POP HL
    CALL fn_memory
    JP fn_handled
fn_frame_allocated:
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD (HL),4
    INC HL
    LD DE,(MM_FN_FRAME)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    ; DE=定義はスタックから取得
    POP BC
    POP DE
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD DE,(MM_CUR_PTR)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD DE,(MM_LINE_END)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    ; 残りの枠はゼロ初期化。実引数の失敗時も確保済みのものだけ回収。
    PUSH BC
    LD BC,281
fn_frame_clear:
    LD (HL),0
    INC HL
    DEC BC
    LD A,B
    OR C
    JR NZ,fn_frame_clear
    POP HL
    LD (MM_FN_FRAME),HL
    LD DE,241
    ADD HL,DE
    EX DE,HL
    LD HL,MM_RUN_ARRAY_NAME
    LD BC,8
    LDIR
    LD HL,MM_RUN_ARRAY_IDX
    LD BC,2
    LDIR
    CALL fn_skip
    CALL fn_def_count
    OR A
    JP Z,fn_call_zero
    CALL fn_peek
    CP '('
    JP NZ,fn_call_syntax
    CALL fn_adv
fn_actual:
    ; 仮引数の名前から型を取り、実引数をその型へ変換。
    CALL fn_param_name
    CALL fn_name_kind
    PUSH AF
    CALL fn_skip
    CALL fn_peek
    CP ')'
    JR NZ,fn_actual_present
    POP AF
    JP fn_call_syntax
fn_actual_present:
    POP AF
    CP 3
    JR Z,fn_actual_string
    PUSH AF
    CALL fn_is_string
    OR A
    JR Z,fn_actual_num_expr
    POP AF
    JP fn_call_type
fn_actual_num_expr:
    CALL fn_expr
    POP BC
    CALL fn_bad
    JP NZ,fn_call_cleanup
    LD A,B
    CALL fn_convert
    CALL fn_bad
    JP NZ,fn_call_cleanup
    CALL fn_local_alloc
    CALL fn_bad
    JP NZ,fn_call_cleanup
    CALL fn_var_write
    JP fn_actual_stored
fn_actual_string:
    CALL fn_is_string
    OR A
    JP Z,fn_call_type
    CALL fn_string
    CALL fn_bad
    JP NZ,fn_call_cleanup
    CALL fn_local_alloc
    CALL fn_bad
    JP NZ,fn_call_cleanup
    CALL fn_str_write
fn_actual_stored:
    CALL fn_bad
    JP NZ,fn_call_cleanup
    CALL fn_index_ptr
    INC (HL)
    LD A,(HL)
    PUSH AF
    CALL fn_def_count
    LD B,A
    POP AF
    CP B
    JR Z,fn_actual_close
    CALL fn_skip
    CALL fn_peek
    CP ','
    JP NZ,fn_call_syntax
    CALL fn_adv
    JP fn_actual
fn_actual_close:
    CALL fn_skip
    CALL fn_peek
    CP ')'
    JP NZ,fn_call_syntax
    CALL fn_adv
    JR fn_bind_start
fn_call_zero:
    CALL fn_peek
    CP '('
    JP Z,fn_call_syntax
fn_bind_start:
    LD HL,(MM_CUR_PTR)
    EX DE,HL
    LD HL,(MM_FN_FRAME)
    LD BC,13
    ADD HL,BC
    LD (HL),E
    INC HL
    LD (HL),D
    CALL fn_index_ptr
    LD (HL),0
fn_bind_loop:
    CALL fn_index_ptr
    LD A,(HL)
    PUSH AF
    CALL fn_def_count
    LD B,A
    POP AF
    CP B
    JP Z,fn_body
    CALL fn_param_name
    CALL fn_var_get
    OR A
    JP Z,fn_call_memory
    ; 変数アドレスを保存し、旧33Bを独立した枠に退避。
    PUSH HL
    CALL fn_bind_slot
    POP DE
    LD (HL),E
    INC HL
    LD (HL),D
    EX DE,HL
    LD BC,9
    ADD HL,BC
    PUSH HL
    CALL fn_saved_slot
    EX DE,HL
    POP HL
    LD BC,33
    LDIR
    CALL fn_local_slot
    CALL fn_read_ptr
    LD DE,9
    ADD HL,DE
    PUSH HL
    CALL fn_bind_slot
    CALL fn_read_ptr
    LD DE,9
    ADD HL,DE
    EX DE,HL
    POP HL
    PUSH HL
    LD BC,33
    LDIR
    POP HL
    LD (HL),0                 ; 所有権は束縛先へ。局所枠はページを解放しない。
    CALL fn_index_ptr
    INC (HL)
    LD A,(HL)
    DEC HL
    LD (HL),A                 ; +17=束縛済み数
    JP fn_bind_loop
fn_body:
    CALL fn_def_ptr
    LD DE,11
    ADD HL,DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    LD (MM_CUR_PTR),DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD (MM_LINE_END),DE
    CALL fn_def_type
    CP 3
    JR Z,fn_body_string
    CALL fn_expr
    CALL fn_bad
    JR NZ,fn_call_cleanup
    CALL fn_def_type
    CALL fn_convert
    JR fn_body_end
fn_body_string:
    CALL fn_is_string
    OR A
    JR Z,fn_call_type
    CALL fn_string
fn_body_end:
    CALL fn_bad
    JR NZ,fn_call_cleanup
    CALL fn_skip
    CALL fn_peek
    OR A
    JR NZ,fn_call_syntax
    JR fn_call_cleanup
fn_call_syntax:
    CALL fn_syntax
    JR fn_call_cleanup
fn_call_type:
    CALL fn_type
    JR fn_call_cleanup
fn_call_memory:
    CALL fn_memory
fn_call_cleanup:
    ; 解放/復元はERRORと返り値を変更しない。全ての誤り経路をここへ集める。
    CALL fn_index_ptr
    LD (HL),0
fn_restore_loop:
    CALL fn_index_ptr
    LD A,(HL)
    LD B,A
    DEC HL
    LD A,(HL)
    CP B
    JR Z,fn_locals_cleanup
    CALL fn_bind_slot
    CALL fn_read_ptr
    LD DE,9
    ADD HL,DE
    PUSH HL
    CALL fn_release_string
    CALL fn_saved_slot
    POP DE
    LD BC,33
    LDIR
    CALL fn_index_ptr
    INC (HL)
    JR fn_restore_loop
fn_locals_cleanup:
    CALL fn_index_ptr
    LD (HL),0
fn_locals_loop:
    CALL fn_local_slot
    CALL fn_read_ptr
    LD A,H
    OR L
    JR Z,fn_local_next
    PUSH HL
    LD DE,9
    ADD HL,DE
    CALL fn_release_string
    POP HL
    LD DE,8
    ADD HL,DE
    LD (HL),081h
fn_local_next:
    CALL fn_index_ptr
    INC (HL)
    LD A,(HL)
    CP 6
    JR C,fn_locals_loop
    LD HL,(MM_FN_FRAME)
    LD DE,241
    ADD HL,DE
    LD DE,MM_RUN_ARRAY_NAME
    LD BC,8
    LDIR
    LD DE,MM_RUN_ARRAY_IDX
    LD BC,2
    LDIR
    LD HL,(MM_FN_FRAME)
    LD DE,8
    ADD HL,DE
    LD (HL),084h
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    INC HL
    INC HL
    LD A,(HL)
    LD (MM_CUR_PTR),A
    INC HL
    LD A,(HL)
    LD (MM_CUR_PTR+1),A
    INC HL
    LD A,(HL)
    LD (MM_LINE_END),A
    INC HL
    LD A,(HL)
    LD (MM_LINE_END+1),A
    LD (MM_FN_FRAME),DE
    CALL fn_trim
fn_handled:
    LD A,1
    RET

; フレームのスロット計算。値をCPUスタックへ積まない。
fn_def_ptr:
    LD HL,(MM_FN_FRAME)
    LD DE,11
    ADD HL,DE
fn_read_ptr:
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
    RET
fn_def_count:
    CALL fn_def_ptr
    LD DE,9
    ADD HL,DE
    LD A,(HL)
    RET
fn_def_type:
    CALL fn_def_ptr
    LD DE,10
    ADD HL,DE
    LD A,(HL)
    RET
fn_index_ptr:
    LD HL,(MM_FN_FRAME)
    LD DE,18
    ADD HL,DE
    RET
fn_param_name:
    CALL fn_index_ptr
    LD A,(HL)
    LD L,A
    LD H,0
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    LD DE,15
    ADD HL,DE
    PUSH HL
    CALL fn_def_ptr
    POP DE
    ADD HL,DE
    LD DE,MM_IDENT_BUF
    LD BC,8
    LDIR
    RET
fn_local_slot:
    LD BC,19
    JR fn_ptr_slot
fn_bind_slot:
    LD BC,31
fn_ptr_slot:
    CALL fn_index_ptr
    LD L,(HL)
    LD H,0
    ADD HL,HL
    ADD HL,BC
    LD DE,(MM_FN_FRAME)
    ADD HL,DE
    RET
fn_saved_slot:
    CALL fn_index_ptr
    LD L,(HL)
    LD H,0
    LD E,L
    LD D,H
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,DE
    LD DE,43
    ADD HL,DE
    LD DE,(MM_FN_FRAME)
    ADD HL,DE
    RET
fn_local_alloc:
    CALL fn_var_alloc
    OR A
    JP Z,fn_memory
    PUSH HL
    ; 非字句名(先頭0と自分の番地)。通常のVAR_WRITE経路をそのまま使う。
    LD B,8
    XOR A
fn_hidden_name:
    LD (HL),A
    INC HL
    DJNZ fn_hidden_name
    POP DE
    PUSH DE
    LD H,D
    LD L,E
    INC HL
    LD (HL),E
    INC HL
    LD (HL),D
    POP HL
    PUSH HL
    LD DE,MM_IDENT_BUF
    LD BC,8
    LDIR
    CALL fn_local_slot
    POP DE
    LD (HL),E
    INC HL
    LD (HL),D
    JP fn_ok
fn_name_kind:
    LD A,(MM_IDENT_BUF+7)
    CP '%'
    LD A,2
    RET Z
    LD A,(MM_IDENT_BUF+7)
    CP '$'
    LD A,3
    RET Z
    LD A,(MM_IDENT_BUF+7)
    CP '#'
    LD A,4
    RET Z
    LD A,1
    RET
fn_convert:
    CP 4
    JP Z,fn_promote
    CP 2
    RET NZ
    CALL fn_int
    OR A
    JP Z,fn_overflow
    EX DE,HL
    JP fn_set_int
fn_is_string:
    CALL fn_skip
    CALL fn_peek
    CP '"'
    JR Z,fn_is_string_yes
    CALL fn_ident_peek
    CP 3
    JR Z,fn_is_string_yes
    ; fn a$の空白形も文字列として判定する（呼出位置は保持）。
    LD HL,(MM_CUR_PTR)
    PUSH HL
    CALL fn_prefix
    OR A
    JR Z,fn_is_string_no
    CALL fn_skip
    CALL fn_ident_peek
    CP 3
    JR Z,fn_is_string_space
fn_is_string_no:
    POP HL
    LD (MM_CUR_PTR),HL
    XOR A
    RET
fn_is_string_space:
    POP HL
    LD (MM_CUR_PTR),HL
fn_is_string_yes:
    LD A,1
    RET

; +9の種別2だけ長文字列ページを所有する。短い文字列はレコード内。
fn_release_string:
    LD A,(HL)
    CP 2
    RET NZ
    INC HL
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD (MM_FN_WORK),DE
    LD HL,FN_PAGE_FREE_ENTRY
    JP fn_bank3

; SWAPの左辺解決。A=0は新設可、A=1は存在必須。
; 未測定・自作判断: 第2が存在しない配列の場合もERR 5で新設しない。
; 数値要素9B、単純変数は種別+値の33Bを交換。文字列要素は別途9B形式。
fn_lvalue:
    PUSH AF
    CALL fn_skip
    CALL fn_ident
    OR A
    JR NZ,fn_lvalue_name
    POP AF
    JP fn_syntax
fn_lvalue_name:
    LD HL,MM_IDENT_BUF
    LD B,4
fn_lvalue_save_name:
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    PUSH DE
    DJNZ fn_lvalue_save_name
    CALL fn_skip
    CALL fn_peek
    CP '('
    JR NZ,fn_lvalue_scalar
    CALL fn_adv
    CALL fn_expr
    CALL fn_bad
    JP NZ,fn_lvalue_pop_error
    CALL fn_to_int
    JR C,fn_lvalue_pop_overflow
    LD (MM_RUN_ARRAY_IDX),DE
    CALL fn_skip
    CALL fn_peek
    CP ')'
    JR NZ,fn_lvalue_pop_syntax
    CALL fn_adv
    CALL fn_lvalue_restore_name
    POP AF
    PUSH AF
    CALL fn_array_find
    OR A
    JR NZ,fn_lvalue_array_found
    POP AF
    OR A
    JP NZ,fn_illegal
    CALL fn_array_get
    OR A
    JP Z,fn_memory
    JR fn_lvalue_array_addr
fn_lvalue_array_found:
    POP AF
fn_lvalue_array_addr:
    CALL fn_array_elem
    JP C,fn_range
    PUSH HL
    CALL fn_name_kind
    POP HL
    LD B,9
    LD C,1                    ; C=配列
    JP fn_lvalue_done
fn_lvalue_scalar:
    CALL fn_lvalue_restore_name
    POP AF
    OR A
    JR Z,fn_lvalue_scalar_create
    CALL fn_var_find
    OR A
    JP Z,fn_illegal
    JR fn_lvalue_scalar_addr
fn_lvalue_scalar_create:
    CALL fn_var_get
    OR A
    JP Z,fn_memory
fn_lvalue_scalar_addr:
    LD DE,9
    ADD HL,DE
    PUSH HL
    CALL fn_name_kind
    POP HL
    LD B,33
    LD C,0                    ; C=単純変数
fn_lvalue_done:
    LD D,A
    XOR A
    LD (MM_ERROR_FLAG),A
    LD A,D
    RET
; 名前の4wordはこのルーチンの戻り番地より下にある。
fn_lvalue_restore_name:
    POP IX
    LD HL,MM_IDENT_BUF+7
    LD B,4
fn_lvalue_restore_loop:
    POP DE
    LD (HL),D
    DEC HL
    LD (HL),E
    DEC HL
    DJNZ fn_lvalue_restore_loop
    JP (IX)
fn_lvalue_pop_overflow:
    CALL fn_overflow
    JR fn_lvalue_pop_error
fn_lvalue_pop_syntax:
    CALL fn_syntax
fn_lvalue_pop_error:
    CALL fn_lvalue_restore_name
    POP AF
    RET
fn_swap:
    XOR A
    CALL fn_lvalue
    CALL fn_bad_keep
    RET NZ
    PUSH HL
    LD A,B
    LD (MM_FN_AUX),A
    CALL fn_name_kind
    PUSH BC
    PUSH AF
    CALL fn_skip
    CALL fn_peek
    CP ','
    JR NZ,fn_swap_pop_syntax
    CALL fn_adv
    LD A,1
    CALL fn_lvalue
    CALL fn_bad_keep
    JR NZ,fn_swap_pop_error
    LD D,A
    POP AF
    CP D
    JR NZ,fn_swap_pop_type
    POP DE                    ; D=第1サイズ、E=配列印
    ; 数値なら単純変数のkindを飛ばし、全て9B形式で交換。
    CP 3
    JR Z,fn_swap_strings
    LD A,C
    OR A
    JR NZ,fn_swap_num_second
    INC HL
fn_swap_num_second:
    POP DE
    JR fn_swap_numeric_fix
fn_swap_strings:
    LD A,D
    CP B
    JR NZ,fn_swap_mixed_string
    POP DE
    JR fn_swap_bytes
fn_swap_mixed_string:
    LD A,D
    POP DE
    CP 33
    JR Z,fn_swap_mixed_first_scalar
    ; HL=第2の単純変数、DE=第1の配列
    JP fn_swap_string_mixed
fn_swap_mixed_first_scalar:
    EX DE,HL
    JP fn_swap_string_mixed
fn_swap_numeric_fix:
    ; 第1のサイズをMM_FN_AUXへ保存する版は下の共通入口で設定する。
    LD A,(MM_FN_AUX)
    CP 33
    JR NZ,fn_swap_numeric_bytes
    INC DE
fn_swap_numeric_bytes:
    LD B,9
fn_swap_bytes:
    LD A,(DE)
    LD C,(HL)
    LD (HL),A
    LD A,C
    LD (DE),A
    INC HL
    INC DE
    DJNZ fn_swap_bytes
    JP fn_ok
fn_swap_pop_syntax:
    CALL fn_syntax
fn_swap_pop_error:
    POP AF
    POP BC
    POP HL
    RET
fn_swap_pop_type:
    POP BC
    POP HL
    JP fn_type

; 未測定・自作判断: 文字列配列と単純文字列の交換はページの所有権を移す。
; HL=単純変数のkind、DE=配列の長さ。新設ページの失敗時は交換しない。
fn_swap_string_mixed:
    PUSH HL
    PUSH DE
    LD A,(HL)
    CP 2
    JR Z,fn_swap_string_long
    INC HL
    LD A,(HL)
    OR A
    JR Z,fn_swap_string_empty
    PUSH HL
    CALL fn_new_page
    POP HL
    OR A
    JR Z,fn_swap_string_oom
    LD C,(HL)
    LD B,0
    INC HL
    LD DE,(MM_FN_WORK)
    LDIR
    JR fn_swap_string_page_ready
fn_swap_string_long:
    INC HL
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD (MM_FN_WORK),DE
    JR fn_swap_string_page_ready
fn_swap_string_empty:
    LD DE,0
    LD (MM_FN_WORK),DE
fn_swap_string_page_ready:
    POP DE
    POP HL
    PUSH HL
    PUSH DE
    ; 配列の記述子をCUR_TYPE/DATAへ退避（文なので式の返り値はない）。
    EX DE,HL
    LD DE,MM_CUR_TYPE
    LD BC,9
    LDIR
    POP DE
    POP HL
    INC HL
    LD A,(HL)                  ; 旧単純文字列の長さ
    LD (DE),A
    INC DE
    PUSH HL
    LD HL,(MM_FN_WORK)
    LD A,L
    LD (DE),A
    INC DE
    LD A,H
    LD (DE),A
    POP HL
    ; 旧配列のページを単純変数へ。空文字列はinlineに戻す。
    LD A,(MM_CUR_TYPE)
    LD (HL),A
    DEC HL
    LD (HL),1
    OR A
    JP Z,fn_ok
    LD (HL),2
    INC HL
    INC HL
    LD DE,(MM_CUR_DATA)
    LD (HL),E
    INC HL
    LD (HL),D
    JP fn_ok
fn_swap_string_oom:
    POP DE
    POP HL
    JP fn_memory

fn_erase:
fn_erase_one:
    CALL fn_skip
    CALL fn_ident
    OR A
    JP Z,fn_syntax
    CALL fn_array_find
    OR A
    JP Z,fn_illegal
    PUSH HL
    LD DE,7
    ADD HL,DE
    LD A,(HL)
    CP '$'
    JR NZ,fn_erase_mark
    INC HL
    INC HL
    LD B,(HL)
    INC HL
fn_erase_strings:
    PUSH BC
    PUSH HL
    LD A,(HL)
    OR A
    JR Z,fn_erase_string_next
    INC HL                    ; +0=長さ,+1/+2=ページ
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD (MM_FN_WORK),DE
    LD HL,FN_PAGE_FREE_ENTRY
    CALL fn_bank3
fn_erase_string_next:
    POP HL
    LD DE,9
    ADD HL,DE
    POP BC
    DJNZ fn_erase_strings
fn_erase_mark:
    POP HL
    LD DE,8
    ADD HL,DE
    LD (HL),082h
    CALL fn_trim
    CALL fn_skip
    CALL fn_peek
    CP ','
    JP NZ,fn_ok
    CALL fn_adv
    JP fn_erase_one

fn_trim:
    LD HL,(MM_HEAP_START)
    LD B,H
    LD C,L                    ; BC=最後の生きた枠の終わり
fn_trim_loop:
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    ADD HL,DE
    JR Z,fn_trim_end
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    POP HL
    LD D,A
    AND 07Fh
    CP 1
    LD DE,42
    JR Z,fn_trim_size
    LD DE,298
fn_trim_size:
    PUSH HL
    ADD HL,DE
    EX DE,HL
    POP HL
    PUSH DE
    LD DE,8
    ADD HL,DE
    BIT 7,(HL)
    POP HL
    JR NZ,fn_trim_loop
    LD B,H
    LD C,L
    JR fn_trim_loop
fn_trim_end:
    LD (MM_HEAP_END),BC
    RET
 ; 文字列配列: +0=長さ,+1/+2=ページ番地。空文字列はページを持たない。
; 未測定・自作判断: 非空の文字列要素は長さにかかわらず256Bページ。
fn_array_string_read:
    CALL fn_skip
    CALL fn_peek
    CP '('
    JP NZ,fn_str_read
    CALL fn_array_read
    CALL fn_bad
    RET NZ
    LD A,(MM_CUR_TYPE)
    LD (MM_RUN_STR_TMP_LEN),A
    OR A
    JP Z,fn_ok
    LD C,A
    LD B,0
    LD HL,(MM_CUR_DATA)
    LD DE,MM_RUN_STR_TMP_BUF
    LDIR
    JP fn_ok
fn_array_string_assign:
    CALL fn_is_string
    OR A
    JP Z,fn_type
    CALL fn_string
    CALL fn_bad
    RET NZ
    LD HL,(MM_RUN_ARRAY_ASSIGN_ADDR)
    CALL fn_release_array_string
    LD A,(MM_RUN_STR_TMP_LEN)
    OR A
    JR Z,fn_array_store_empty
    CALL fn_new_page
    OR A
    JP Z,fn_memory
    LD DE,(MM_FN_WORK)
    PUSH DE
    LD HL,MM_RUN_STR_TMP_BUF
    LD A,(MM_RUN_STR_TMP_LEN)
    LD C,A
    LD B,0
    LDIR
    POP DE
    LD HL,(MM_RUN_ARRAY_ASSIGN_ADDR)
    LD A,(MM_RUN_STR_TMP_LEN)
    LD (HL),A
    INC HL
    LD (HL),E
    INC HL
    LD (HL),D
    JP fn_ok
fn_array_store_empty:
    LD HL,(MM_RUN_ARRAY_ASSIGN_ADDR)
    LD B,9
fn_array_empty_loop:
    LD (HL),0
    INC HL
    DJNZ fn_array_empty_loop
    JP fn_ok
fn_release_array_string:
    LD A,(HL)
    OR A
    RET Z
    LD (HL),0
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD (MM_FN_WORK),DE
    LD HL,FN_PAGE_FREE_ENTRY
    JP fn_bank3
fn_new_page:
    LD HL,FN_PAGE_ALLOC_ENTRY
    JP fn_bank3

fn_ok:
    XOR A
    LD (MM_ERROR_FLAG),A
    RET
fn_syntax:
    LD A,2
    JR fn_error
fn_illegal:
    LD A,5
    JR fn_error
fn_overflow:
    LD A,6
    JR fn_error
fn_memory:
    LD A,7
    JR fn_error
fn_range:
    LD A,9
    JR fn_error
fn_type:
    LD A,13
fn_error:
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
    RET
fn_bad_keep:
    PUSH AF
    CALL fn_bad
    JR NZ,fn_bad_keep_error
    POP AF
    CP A
    RET
fn_bad_keep_error:
    POP AF
    OR 1
    RET
fn_bad:
    LD A,(MM_ERROR_FLAG)
    OR A
    RET
fn_skip:
    LD IX,FN_SKIP_ADDR
    JP FN_MAIN_CALL_ADDR
FN_SKIP_ADDR EQU 0x1787

fn_peek:
    LD IX,FN_PEEK_ADDR
    JP FN_MAIN_CALL_ADDR
FN_PEEK_ADDR EQU 0x1787

fn_adv:
    LD IX,FN_ADV_ADDR
    JP FN_MAIN_CALL_ADDR
FN_ADV_ADDR EQU 0x1787

fn_ident:
    LD IX,FN_IDENT_ADDR
    JP FN_MAIN_CALL_ADDR
FN_IDENT_ADDR EQU 0x1787

fn_ident_peek:
    LD IX,FN_IDENT_PEEK_ADDR
    JP FN_MAIN_CALL_ADDR
FN_IDENT_PEEK_ADDR EQU 0x1787

fn_fold:
    LD IX,FN_FOLD_ADDR
    JP FN_MAIN_CALL_ADDR
FN_FOLD_ADDR EQU 0x1787

fn_match:
    LD IX,FN_MATCH_ADDR
    JP FN_MAIN_CALL_ADDR
FN_MATCH_ADDR EQU 0x1787

fn_expr:
    LD IX,FN_EXPR_ADDR
    JP FN_MAIN_CALL_ADDR
FN_EXPR_ADDR EQU 0x1787

fn_string:
    LD IX,FN_STRING_ADDR
    JP FN_MAIN_CALL_ADDR
FN_STRING_ADDR EQU 0x1787

fn_int:
    LD IX,FN_INT_ADDR
    JP FN_MAIN_CALL_ADDR
FN_INT_ADDR EQU 0x1787

fn_set_int:
    LD IX,FN_SET_INT_ADDR
    JP FN_MAIN_CALL_ADDR
FN_SET_INT_ADDR EQU 0x1787

fn_promote:
    LD IX,FN_PROMOTE_ADDR
    JP FN_MAIN_CALL_ADDR
FN_PROMOTE_ADDR EQU 0x1787

fn_var_find:
    LD IX,FN_VAR_FIND_ADDR
    JP FN_MAIN_CALL_ADDR
FN_VAR_FIND_ADDR EQU 0x1787

fn_var_alloc:
    LD IX,FN_VAR_ALLOC_ADDR
    JP FN_MAIN_CALL_ADDR
FN_VAR_ALLOC_ADDR EQU 0x1787

fn_var_get:
    LD IX,FN_VAR_GET_ADDR
    JP FN_MAIN_CALL_ADDR
FN_VAR_GET_ADDR EQU 0x1787

fn_var_write:
    LD IX,FN_VAR_WRITE_ADDR
    JP FN_MAIN_CALL_ADDR
FN_VAR_WRITE_ADDR EQU 0x1787

fn_str_write:
    LD IX,FN_STR_WRITE_ADDR
    JP FN_MAIN_CALL_ADDR
FN_STR_WRITE_ADDR EQU 0x1787

fn_array_find:
    LD IX,FN_ARRAY_FIND_ADDR
    JP FN_MAIN_CALL_ADDR
FN_ARRAY_FIND_ADDR EQU 0x1787

fn_array_get:
    LD IX,FN_ARRAY_GET_ADDR
    JP FN_MAIN_CALL_ADDR
FN_ARRAY_GET_ADDR EQU 0x1787

fn_array_elem:
    LD IX,FN_ARRAY_ELEM_ADDR
    JP FN_MAIN_CALL_ADDR
FN_ARRAY_ELEM_ADDR EQU 0x1787

fn_heap_find:
    LD IX,FN_HEAP_FIND_ADDR
    JP FN_MAIN_CALL_ADDR
FN_HEAP_FIND_ADDR EQU 0x1787

fn_heap_alloc:
    LD IX,FN_HEAP_ALLOC_ADDR
    JP FN_MAIN_CALL_ADDR
FN_HEAP_ALLOC_ADDR EQU 0x1787

fn_bank3:
    LD IX,FN_BANK3_ADDR
    JP FN_MAIN_CALL_ADDR
FN_BANK3_ADDR EQU 0x1787

fn_to_int:
    LD IX,FN_TO_INT_ADDR
    JP FN_MAIN_CALL_ADDR
FN_TO_INT_ADDR EQU 0x1787

FN_MAIN_CALL_ADDR EQU 0x1787
fn_str_read:
    LD IX,FN_STR_READ_ADDR
    JP FN_MAIN_CALL_ADDR
FN_STR_READ_ADDR EQU 0x1787
fn_array_read:
    LD IX,FN_ARRAY_READ_ADDR
    JP FN_MAIN_CALL_ADDR
FN_ARRAY_READ_ADDR EQU 0x1787
