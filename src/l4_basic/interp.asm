; interp.asm — M7段階3b: 直接モードの実行とPRINT文。
;
; 根拠は docs/spec/l4-basic.md（第1〜6.1節）と docs/spec/l3-main.md
; （画面出力・行入力、参照のみ）だけである。measurements/ も公式ROMも
; 参照していない。
;
;   直接モードの行の並び(相対+1に出力、+2にOk)         … l4-basic.md 第1節
;   整数の前後の空白(符号1桁+末尾空白1)                 … l4-basic.md 第2節
;   文字列の前後に空白なし                              … l4-basic.md 第3節
;   区切り記号(;は素通し、,は14列ゾーン、行末での改行抑止) … l4-basic.md 第4節
;   構文の誤り(出力の行1行、Okの位置は変わらない)         … l4-basic.md 第5節
;   誤りの形とメッセージの対応(Missing operand/Syntax error/Overflow) … l4-basic.md 第6.1.1節
;                                                            (errors.asm経由)
;   PRINTの語形とトークン                                … tokens.tsv
;                                                            (print_dispatch.asm経由)
;
; 仕様書に無いため、この版で明示的に選んだ既定（推測で埋めず、選択として
; 記録する。報告の「仕様書に無いこと」参照）:
;   - キーボードの無修飾の英字キーは既定で小文字を返す(l3-main.md 第7節)
;     ため、直接モードの行頭キーワード照合は大文字小文字を区別しない
;     (FOLD_UPPERで畳み込む)。文字列定数の中身は畳み込まない(打鍵した
;     とおりの文字を出す、第3節)。
;   - 行末の`;`・`,`がその直接モード行の最後の文であった場合(それに続く
;     文が無いまま行が終わった場合)、Okの前に改行を入れるかどうかは
;     l4-s3a/l4-s3b いずれの測定にも無い。この実装は「Okの前は必ず桁0から
;     始める」という統一規則を選び(LINE_FINISH側でVAR_COLを見て桁0で
;     なければ改行を追加する)、これによりOkが常に独立の行に出ることを
;     保証する。通常完了(PRINT_STMTが自身で改行する)ではこの追加改行は
;     効かない(桁は既に0のため)。
;   - 構文の誤りが式の途中で起きた場合、その文で既に出力済みの内容の
;     扱い(取り消すか残すか)はl4-s3aの実測(`print 1+`、式の途中で無出力の
;     まま丸ごと誤りになる腕)にしか無い。本実装は「値が確定してから
;     出力する」設計（式を評価し終えてからPRINT_NUMBER/文字列出力を呼ぶ）
;     のため、式の評価中に誤りが起きた項目自体は何も出力されない。
;     複数項目のうち前の項目が既に出力済みで後の項目で誤りが起きる場合の
;     扱いは実測が無いため、そのまま出力済み分を残す（取り消さない）。
;   - PRINT以外の語（未実装の命令）は、この段階では字句解析を試みず、
;     直ちに構文の誤りとして扱う（設計項目5）。
;
; RAM変数は lexer.asm 側にまとめて宣言してある(ERROR_FLAG, LINE_END,
; CUR_PTR, SUPPRESS_NL 等)。ここでは追加で以下を使う。
PUD_VALUE   EQU 0E89Ah   ; 2バイト
PUD_PLACE   EQU 0E89Ch   ; 2バイト
PUD_DIGIT   EQU 0E89Eh
PUD_STARTED EQU 0E89Fh
ERROR_KIND  EQU 0E8A0h   ; 誤りの形の番号(2/6/22、既定2)。errors.asm生成の
                         ; ERR_MSG_番号 を選ぶために BASIC_RUN_LINE が読む。
                         ; 判定方針は 第6.1.1節 対応、この段階の選択は
                         ; SELECT_ERROR_MSG の直前コメント参照。

; ゾーン幅(l4-basic.md 第4節zone_14)。故障注入(検査「ゾーンの幅を変えた
; 変種」)がこの1行だけを書き換える対象。
ZONE_WIDTH EQU 14

; ---------------------------------------------------------------------
; BASIC_RUN_LINE — keyboard.asm の LINE_FINISH から、RETURN確定直後
;   （改行済み、桁0の出力行の先頭）に呼ばれる。LINE_BUF/VAR_LINELENを
;   読み、直接モードの行として実行する。構文の誤りがあれば、この中で
;   メッセージを1行出して改行する。「Ok」自体はここでは出さない
;   （呼び出し元LINE_FINISHの役目のまま）。
; ---------------------------------------------------------------------
BASIC_RUN_LINE:
    XOR A
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A    ; 既定はSyntax error(2)。誤りの検出箇所が
                          ; 該当すれば22(Missing operand)/6(Overflow)に
                          ; 上書きする(第6.1.1節)。
    LD HL,LINE_BUF
    LD A,(VAR_LINELEN)
    LD E,A
    LD D,0
    ADD HL,DE
    LD (LINE_END),HL
    LD HL,LINE_BUF
    LD (CUR_PTR),HL
    CALL DIRECT_LINE
    LD A,(ERROR_FLAG)
    OR A
    RET Z
    CALL SELECT_ERROR_MSG
    CALL PRINT_STR
    CALL NEWLINE
    RET

; ---------------------------------------------------------------------
; SELECT_ERROR_MSG — ERROR_KIND(2/6/22)から、errors.asm生成の
;   ERR_MSG_番号 (l4-basic.md 第6.1節のマニュアル文言そのもの)を選ぶ。
;   出力: HL=メッセージ文字列アドレス。未知の値はERR_MSG_2にフォール
;   バックする(第6.1.1節の対応表に無い形は当面Syntax errorのまま、
;   設計項目「仕様書に無い形」参照)。
; ---------------------------------------------------------------------
SELECT_ERROR_MSG:
    LD A,(ERROR_KIND)
    CP 6
    JR Z,_l4sem_overflow
    CP 22
    JR Z,_l4sem_missing
    LD HL,ERR_MSG_2
    RET
_l4sem_overflow:
    LD HL,ERR_MSG_6
    RET
_l4sem_missing:
    LD HL,ERR_MSG_22
    RET

; ---------------------------------------------------------------------
; DIRECT_LINE — ':'区切りの文を先頭から順に実行する。
; ---------------------------------------------------------------------
DIRECT_LINE:
_l4dl_loop:
    CALL SKIP_SPACES
    CALL AT_END
    RET Z
    CALL MATCH_STMT_KEYWORD
    OR A
    JR NZ,_l4dl_have_stmt
    LD A,1
    LD (ERROR_FLAG),A
    RET
_l4dl_have_stmt:
    CALL PRINT_STMT
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL SKIP_SPACES
    CALL AT_END
    RET Z
    CALL PEEK_CHAR
    CP ':'
    JR NZ,_l4dl_bad_trailing
    CALL ADV_PTR
    JP _l4dl_loop
_l4dl_bad_trailing:
    LD A,1
    LD (ERROR_FLAG),A
    RET

; ---------------------------------------------------------------------
; MATCH_STMT_KEYWORD — 現在位置の文キーワードを見る。
;   '?' は PRINT の代替表記として扱う(l4-token-design.md 追記)。
;   出力: A=1(認識してCUR_PTRを消費した)/0(未認識、CUR_PTR不変)
; ---------------------------------------------------------------------
MATCH_STMT_KEYWORD:
    CALL PEEK_CHAR
    CP '?'
    JR NZ,_l4msk_try_print
    CALL ADV_PTR
    LD A,1
    RET
_l4msk_try_print:
    CALL TRY_MATCH_PRINT
    RET

; ---------------------------------------------------------------------
; TRY_MATCH_PRINT — print_dispatch.asm の TOK_PRINT_TEXT(=PRINT語形)を
;   大文字小文字を区別せず照合する。一致直後の文字が英字なら不一致扱い
;   (PRINTEDのような別の識別子の一部との混同を避ける、仕様書に無い選択)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
; ---------------------------------------------------------------------
TRY_MATCH_PRINT:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP TOK_PRINT_LEN
    JR C,_l4tmp_fail
    LD HL,(CUR_PTR)
    LD DE,TOK_PRINT_TEXT
    LD B,TOK_PRINT_LEN
_l4tmp_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmp_fail
    INC HL
    INC DE
    DJNZ _l4tmp_cmp
    ; HL は一致した5文字の直後。境界確認(続く文字が英字でないこと)。
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmp_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmp_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmp_boundary_ok2
    JR _l4tmp_fail
_l4tmp_boundary_ok:
    POP HL
_l4tmp_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,TOK_PRINT_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmp_fail:
    XOR A
    RET

; ---------------------------------------------------------------------
; PRINT_STMT — 現在位置から印字リストを解釈・出力する
;   (l4-basic.md 第2〜4節の書式)。
; ---------------------------------------------------------------------
PRINT_STMT:
    XOR A
    LD (SUPPRESS_NL),A
_l4ps_loop:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,_l4ps_stmt_end
    CP ':'
    JR Z,_l4ps_stmt_end
    CP '"'
    JR Z,_l4ps_string_item
    CALL EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL PRINT_NUMBER
    JR _l4ps_after_item
_l4ps_string_item:
    CALL ADV_PTR
_l4ps_str_loop:
    CALL PEEK_CHAR
    OR A
    JR Z,_l4ps_str_done
    CP '"'
    JR Z,_l4ps_str_close
    CALL PRINT_CHAR
    CALL ADV_PTR
    JR _l4ps_str_loop
_l4ps_str_close:
    CALL ADV_PTR
_l4ps_str_done:
_l4ps_after_item:
    XOR A
    LD (SUPPRESS_NL),A
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ';'
    JR Z,_l4ps_semi
    CP ','
    JR Z,_l4ps_comma
    JR _l4ps_stmt_end
_l4ps_semi:
    CALL ADV_PTR
    LD A,1
    LD (SUPPRESS_NL),A
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,_l4ps_stmt_end
    CP ':'
    JR Z,_l4ps_stmt_end
    XOR A
    LD (SUPPRESS_NL),A
    JP _l4ps_loop
_l4ps_comma:
    CALL ADV_PTR
    LD A,1
    LD (SUPPRESS_NL),A
    CALL ZONE_PAD
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,_l4ps_stmt_end
    CP ':'
    JR Z,_l4ps_stmt_end
    XOR A
    LD (SUPPRESS_NL),A
    JP _l4ps_loop
_l4ps_stmt_end:
    LD A,(SUPPRESS_NL)
    OR A
    RET NZ
    CALL NEWLINE
    RET

; ---------------------------------------------------------------------
; ZONE_PAD — 現在桁を次のZONE_WIDTH刻みの境界まで空白で埋める
;   (l4-basic.md 第4節zone_14。既に境界上でも必ず1ゾーン以上進む)。
; ---------------------------------------------------------------------
ZONE_PAD:
    LD A,(VAR_COL)
    LD B,A
    LD C,0
_l4zp_find:
    LD A,C
    ADD A,ZONE_WIDTH
    LD C,A
    CP B
    JR Z,_l4zp_find
    JR C,_l4zp_find
    LD A,C
    SUB B
    LD B,A
    OR A
    RET Z
_l4zp_pad_loop:
    LD A,' '
    CALL PRINT_CHAR
    DJNZ _l4zp_pad_loop
    RET

; ---------------------------------------------------------------------
; PEEK_CHAR / ADV_PTR / AT_END / SKIP_SPACES — 行バッファの走査。
; ---------------------------------------------------------------------
; PEEK_CHAR/ADV_PTR は HL を破壊しない(呼び出し規約)。FACTOR の数値解析
; ループがHLを桁の積算値として保持したままこれらを呼ぶため
; (M7段階3b、当初HLを破壊する版で"PRINT1"が62768になる不具合を確認、
; PUSH/POPでHLを退避する形に修正した)。
PEEK_CHAR:
    PUSH HL
    LD HL,(CUR_PTR)
    LD DE,(LINE_END)
    OR A
    SBC HL,DE
    JR Z,_l4peek_end
    LD HL,(CUR_PTR)
    LD A,(HL)
    POP HL
    RET
_l4peek_end:
    XOR A
    POP HL
    RET

ADV_PTR:
    PUSH HL
    LD HL,(CUR_PTR)
    INC HL
    LD (CUR_PTR),HL
    POP HL
    RET

AT_END:
    LD HL,(CUR_PTR)
    LD DE,(LINE_END)
    OR A
    SBC HL,DE
    RET

SKIP_SPACES:
_l4skip_loop:
    CALL PEEK_CHAR
    CP ' '
    RET NZ
    CALL ADV_PTR
    JR _l4skip_loop

; FOLD_UPPER: Aの英小文字をAND大文字化する。他の文字はそのまま。
FOLD_UPPER:
    CP 'a'
    RET C
    CP 'z'+1
    RET NC
    SUB 32
    RET

; ---------------------------------------------------------------------
; EXPR / TERM / FACTOR — 整数式(定数・単項-・+ - *・括弧)。
;   戻り値はHL。エラー時はERROR_FLAG=1(HLの値は不定)。
; ---------------------------------------------------------------------
EXPR:
    CALL TERM
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
_l4expr_loop:
    PUSH HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '+'
    JR Z,_l4expr_plus
    CP '-'
    JR Z,_l4expr_minus
    POP HL
    RET
_l4expr_plus:
    CALL ADV_PTR
    CALL TERM
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_l4expr_err_pop
    EX DE,HL
    POP HL
    OR A            ; CF=0にしてからADCで加算(ADD HL,DEはP/Vを更新しない
                     ; ため、符号付きオーバーフロー判定にADC HL,DEを使う。
                     ; CF=0なのでADDと同じ結果になる)。
    ADC HL,DE
    JP PE,_l4expr_overflow  ; PE=P/Vフラグ1=符号付きオーバーフロー
    JP _l4expr_loop
_l4expr_minus:
    CALL ADV_PTR
    CALL TERM
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_l4expr_err_pop
    EX DE,HL
    POP HL
    OR A
    SBC HL,DE
    JP PE,_l4expr_overflow
    JP _l4expr_loop
_l4expr_err_pop:
    POP HL
    RET
_l4expr_overflow:
    ; 式の計算結果が−32768〜32767を超えた(l4-basic.md 第6.1.1節、資ー14)。
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET

TERM:
    CALL FACTOR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
_l4term_loop:
    PUSH HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '*'
    JR NZ,_l4term_done
    CALL ADV_PTR
    CALL FACTOR
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_l4term_err_pop
    EX DE,HL
    POP HL
    LD B,H
    LD C,L
    CALL MUL16
    JP _l4term_loop
_l4term_done:
    POP HL
    RET
_l4term_err_pop:
    POP HL
    RET

FACTOR:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '-'
    JR NZ,_l4factor_try_paren
    CALL ADV_PTR
    CALL FACTOR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
    RET
_l4factor_try_paren:
    CP '('
    JR NZ,_l4factor_try_num
    CALL ADV_PTR
    CALL EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    PUSH HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ')'
    JR NZ,_l4factor_paren_err
    CALL ADV_PTR
    POP HL
    RET
_l4factor_paren_err:
    POP HL
    LD A,1
    LD (ERROR_FLAG),A
    RET
_l4factor_try_num:
    CP '0'
    JR C,_l4factor_bad
    CP '9'+1
    JR NC,_l4factor_bad
    LD HL,0
_l4factor_num_loop:
    CALL PEEK_CHAR
    CP '0'
    JR C,_l4factor_num_done
    CP '9'+1
    JR NC,_l4factor_num_done
    ; 定数オーバーフロー(第6.1.1節、資ー14)の事前チェック: 現在値が
    ; 3277以上なら、どんな桁が続いても*10した結果は32768を超える
    ; (16bitレジスタの折り返しに入る前に検出する。仕様書に無いため
    ; この段階で選んだ実装上のガード、報告のとおり)。
    LD C,A                  ; 今回の桁の文字を退避
    LD DE,3277
    CALL CP_HL_DE
    JR NC,_l4factor_overflow  ; HL>=3277
    LD A,C
    SUB '0'
    LD E,A
    LD D,0                    ; DE = 今回の桁(0-9)
    PUSH DE
    ADD HL,HL
    PUSH HL
    ADD HL,HL
    ADD HL,HL
    POP DE
    ADD HL,DE                 ; HL = 旧HL*10
    POP DE
    ADD HL,DE                 ; HL = 旧HL*10 + 桁
    LD DE,32769
    CALL CP_HL_DE
    JR NC,_l4factor_overflow  ; HL>=32769 → 32768を超えた
    CALL ADV_PTR
    JR _l4factor_num_loop
_l4factor_num_done:
    RET
_l4factor_overflow:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET
_l4factor_bad:
    LD A,1
    LD (ERROR_FLAG),A
    ; 被演算子を探した位置が行末、または続く文の区切り':'なら
    ; Missing operand(22、第6.1.1節、資ー13)。それ以外(未知の語・記号)は
    ; 既定のSyntax error(2)のまま。
    CALL AT_END
    JR Z,_l4factor_bad_missing
    CALL PEEK_CHAR
    CP ':'
    JR NZ,_l4factor_bad_ret
_l4factor_bad_missing:
    LD A,22
    LD (ERROR_KIND),A
_l4factor_bad_ret:
    RET

; ---------------------------------------------------------------------
; CP_HL_DE — HLとDEを符号なしで比較する(HL,DEとも変更しない)。
;   フラグ: HL<DEならC、HL>=DEならNC(SBCの結果をそのまま使う)。
; ---------------------------------------------------------------------
CP_HL_DE:
    PUSH HL
    OR A
    SBC HL,DE
    POP HL
    RET

; ---------------------------------------------------------------------
; MUL16 — HL = BC * DE (16x16→16、下位16bitのみ。オーバーフローは
;   この段階の対象外、l4-basic.md 第9節2)。AF破壊。BC,DEは破壊してよい。
; ---------------------------------------------------------------------
MUL16:
    LD HL,0
_l4mul16_loop:
    LD A,E
    OR D
    JR Z,_l4mul16_done
    BIT 0,E
    JR Z,_l4mul16_noadd
    ADD HL,BC
_l4mul16_noadd:
    SLA C
    RL B
    SRL D
    RR E
    JR _l4mul16_loop
_l4mul16_done:
    RET

; ---------------------------------------------------------------------
; PRINT_NUMBER — HL=16bit値(2の補数)。符号1桁(正/0は空白、負は'-')＋
;   数字＋末尾空白1を出力する(l4-basic.md 第2節)。
; ---------------------------------------------------------------------
; 注意: screen.asmのPRINT_CHARはHLをVRAMアドレス計算の作業用に使い、
; 呼び出し元のHLを保存しない(l3-main.md側の既存実装、変更しない)。
; そのため符号の1文字を出す前に、印字する値(HL)を退避してから呼ぶ
; (M7段階3b、当初この退避が無くPRINT_CHARの副作用でHLが破壊され
; "PRINT1"が62768と出る不具合を確認、PUSH/POPで退避する形に修正した)。
PRINT_NUMBER:
    BIT 7,H
    JR Z,_l4pn_pos
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
    PUSH HL
    LD A,'-'
    CALL PRINT_CHAR
    POP HL
    JR _l4pn_digits
_l4pn_pos:
    PUSH HL
    LD A,' '
    CALL PRINT_CHAR
    POP HL
_l4pn_digits:
    CALL PRINT_UDEC
    LD A,' '
    CALL PRINT_CHAR
    RET

; ---------------------------------------------------------------------
; PRINT_UDEC — HL(0-65535、実運用0-32768)を10進で出力する。前ゼロは
;   抑制するが、値0のときは"0"を1文字出す。
; ---------------------------------------------------------------------
PUD_PLACES:
    DW 10000
    DW 1000
    DW 100
    DW 10
    DW 1

PRINT_UDEC:
    LD (PUD_VALUE),HL
    XOR A
    LD (PUD_STARTED),A
    LD IX,PUD_PLACES
    LD B,5
_l4pud_place_loop:
    LD L,(IX+0)
    LD H,(IX+1)
    LD (PUD_PLACE),HL
    XOR A
    LD (PUD_DIGIT),A
_l4pud_sub_loop:
    LD HL,(PUD_VALUE)
    LD DE,(PUD_PLACE)
    OR A
    SBC HL,DE
    JR C,_l4pud_sub_done
    LD (PUD_VALUE),HL
    LD A,(PUD_DIGIT)
    INC A
    LD (PUD_DIGIT),A
    JP _l4pud_sub_loop
_l4pud_sub_done:
    LD A,B
    CP 1
    JR NZ,_l4pud_not_last
    LD A,(PUD_DIGIT)
    ADD A,'0'
    CALL PRINT_CHAR
    JR _l4pud_advance
_l4pud_not_last:
    LD A,(PUD_DIGIT)
    OR A
    JR NZ,_l4pud_show
    LD A,(PUD_STARTED)
    OR A
    JR Z,_l4pud_advance
_l4pud_show:
    LD A,1
    LD (PUD_STARTED),A
    LD A,(PUD_DIGIT)
    ADD A,'0'
    CALL PRINT_CHAR
_l4pud_advance:
    LD DE,2
    ADD IX,DE
    DJNZ _l4pud_place_loop
    RET
