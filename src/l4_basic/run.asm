; run.asm — M7段階5b: RUNとプログラムの実行(行番号順の実行・GOTO・END・
;   FOR〜NEXT・GOSUB〜RETURN・STOP・変数〔無印/%/$〕・実行中の誤り)。
;
; 根拠は docs/spec/l4-program.md 第3版(cd6bc19)第4節だけである。
; measurements/・docs/notes(測定結果・事前登録・予測表)・private/は
; 参照していない。program.asm(段階5a)・interp.asm(直接モードPRINT)・
; mbf_single.asm(単精度演算、参照のみ・編集しない)と組み合わせて使う。
;
;   行番号順の実行・GOTO・END・空プログラムのRUN              … 第4.1節
;   RUNへの行番号指定(その行から開始)                          … 第4.1節
;   FOR〜NEXT(既定STEP+1・開始が終了を超えていれば本体スキップ) … 第4.2節
;   ループ後の制御変数の値(終了値を1回超えたまま)               … 第4.2節
;   FORの入れ子・NEXTへの変数名                                … 第4.2a節
;   GOSUB〜RETURN・入れ子                                       … 第4.3節
;   変数への代入・参照                                          … 第4.4節
;   変数名は少なくとも3文字目まで区別                           … 第4.4a節
;   整数変数(%)への代入は半分を絶対値の大きい側へ丸める          … 第4.4b節
;   文字列変数の基本動作                                        … 第4.4d節
;   STOP(その行で停止・以降の行を実行しない)・実行中の誤り(出力1行) … 第4.5節
;
; 文言はl4-basic.md第7.1節のマニュアル一覧(errors.asm)から採る。
; 測定は「出力は1行」としか確認していないため、行番号を伴う形
; ("XX in 行番号")は第4.5節が触れている資料の記載を踏まえた
; **仕様書に無い判断**として実装する(下記「仕様書に無い判断」参照)。
;
; ---- 仕様書に無い判断(この段階で明示的に選んだもの) --------------------
;   - STOP・実行中の誤りの文言は、メッセージ本体(errors.asm、7.1節)の
;     後ろに" in "+行番号を付ける形で統一する(第4.5節が触れる資料の
;     「XX in 行番号」という形を採用)。STOPそのものはエラー一覧に無い
;     ため、独自に"Break"と名乗る(ROM由来ではない一般的なBASIC用語、
;     禁止事項1-2に抵触しない)。
;   - RUN・GOTO・GOSUBの行番号指定が存在しない行を指す場合は
;     Undefined line number(8)。RUNの行番号指定が完全一致しない場合の
;     扱い(直後の行から開始する等)は未確定のため、完全一致のみ受け付ける。
;   - 変数名は大文字小文字を区別しない(キーワードと同じFOLD_UPPERで畳む、
;     第6節1「未確定」への暫定選択)。有効文字数は7文字+接尾辞1文字の
;     計8文字までとし、それ以降は無視する(仕様書に無い上限、C3の
;     「少なくとも3文字目まで区別」は満たす)。
;   - 変数テーブルは最大40個、文字列変数の中身は最大31文字まで。
;     超えたらOut of memory(7)/String too long(15)。
;   - FORの入れ子は最大8重、GOSUBの入れ子も最大8重まで。超えたら
;     Out of memory(7)。
;   - `#`(倍精度)変数は、段階4b-3で倍精度が組み込まれるまでの暫定として、
;     代入・参照のいずれでもType mismatch(13)の誤りにする。
;   - FORのループ変数への初期値代入は、その変数が`%`接尾辞を持っていても
;     半分丸めの対象にしない(単純化。代入時の丸めは通常のASSIGN文だけの
;     規則として実装した)。
;   - NEXTに変数名を指定して見つかった場合、それより内側の(まだ閉じて
;     いない)FORフレームは暗黙に閉じる(標準的なBASICの挙動を採用)。
;   - FORの本体スキップ時に対応するNEXTを探す走査は、文字列リテラル内の
;     `:`や`FOR`/`NEXT`という文字列を特別扱いしない(簡略化。行内の全ての
;     `:`を文区切りとして扱い、字面が一致すれば統計対象にする)。
;   - RUNは呼ぶたびに変数テーブル・FORスタック・GOSUBスタックを
;     初期化する(繰り返し実行の再現性のための選択)。
;
; RAM配置(段階5b新規、0xD000台。既存: mbf_single/mbf_double=0xC000-
; 0xC2xx台、L3/L4作業域・program.asm=0xE800-0xE99A、PROGRAM_AREA=
; 0xEA00-0xEDFF、スタックSP=0xF000。いずれとも重ならない)。

RUN_STMT_KIND      EQU 0D000h  ; 1B (0=PRINT 1=GOTO 2=GOSUB 3=RETURN
                                 ; 4=FOR 5=NEXT 6=END 7=STOP 8=ASSIGN)
RUN_CUR_RECORD     EQU 0D001h  ; 2B 現在実行中のPROGRAM_AREAレコード先頭
RUN_CUR_LINENO     EQU 0D003h  ; 2B 現在の行番号(エラー表示用にキャッシュ)
RUN_CTRL           EQU 0D005h  ; 1B 0=通常続行 1=ジャンプ済み 2=停止
IDENT_BUF          EQU 0D006h  ; 8B 直近に読んだ識別子(畳み込み済み)
IDENT_LEN          EQU 0D00Eh  ; 1B 消費した文字数(接尾辞含む)
IDENT_KIND         EQU 0D00Fh  ; 1B 0=識別子でない 1=無印 2=% 3=$ 4=#
RUN_ASSIGN_KIND    EQU 0D010h  ; 1B
RUN_ASSIGN_NAME    EQU 0D011h  ; 8B
RUN_FOR_VARNAME    EQU 0D019h  ; 8B (FOR_STMT一時)
RUN_FOR_LIMIT_TYPE EQU 0D021h  ; 1B
RUN_FOR_LIMIT_DATA EQU 0D022h  ; 4B
RUN_FOR_STEP_TYPE  EQU 0D026h  ; 1B
RUN_FOR_STEP_DATA  EQU 0D027h  ; 4B
RUN_FOR_FRAME_PTR  EQU 0D02Bh  ; 2B
RUN_FOR_CMP_RESULT EQU 0D02Dh  ; 1B
RUN_FOR_SEARCH_IDX EQU 0D02Eh  ; 1B
RUN_TMP16          EQU 0D02Fh  ; 2B
RUN_STR_TMP_LEN    EQU 0D031h  ; 1B
RUN_STR_TMP_BUF    EQU 0D032h  ; 31B (文字列一時領域、STRMAXLEN=31)
RUN_SCAN_DEPTH     EQU 0D051h  ; 1B (FOR/NEXTスキャンの入れ子深さ)
RUN_GOSUB_SP       EQU 0D052h  ; 1B
RUN_FOR_SP         EQU 0D053h  ; 1B
RUN_TMP_E          EQU 0D054h  ; 1B (MBF_ROUND_TO_INT16作業領域)
RUN_TMP_SHIFT      EQU 0D055h
RUN_TMP_M2         EQU 0D056h
RUN_TMP_M1         EQU 0D057h
RUN_TMP_M0         EQU 0D058h
RUN_TMP_RBIT       EQU 0D059h
; 次の空き: 0xD05A

; ---- 変数テーブル ----
; レコード(42B): [NAME 8B][USED 1B][KIND 1B(0=数値 1=文字列)][VALUE 32B]
;   数値: VALUE[0]=type(0=整数16bit/1=単精度) VALUE[1..4]=data
;   文字列: VALUE[0]=len(0-31) VALUE[1..31]=chars
RUN_VARTAB          EQU 0D100h
RUN_VARTAB_REC_SIZE EQU 42
RUN_VARTAB_CAP      EQU 40
VARREC_USED         EQU 8
VARREC_KIND         EQU 9
VARREC_VALUE        EQU 10
RUN_VAR_FREE_PTR    EQU 0D0F0h  ; 2B (VAR_FINDが記録する最初の空きスロット)
; RUN_VARTAB終端 = D100+42*40 = D760

; ---- FORスタック ----
; フレーム(24B): [NAME 8B][LIMIT type1+data4][STEP type1+data4]
;                [RESUME record2+curptr2+lineend2]
RUN_FOR_STACK       EQU 0D800h
RUN_FOR_FRAME_SIZE  EQU 24
RUN_FOR_STACK_CAP   EQU 8
; 終端 = D800+192 = D8C0

; ---- GOSUBスタック ----
; フレーム(6B): [record2][curptr2][lineend2]
RUN_GOSUB_STACK      EQU 0D900h
RUN_GOSUB_FRAME_SIZE EQU 6
RUN_GOSUB_STACK_CAP  EQU 8
; 終端 = D900+48 = D930

RUN_BREAK_TXT: DB "Break",0
RUN_INTXT: DB " in ",0

; =======================================================================
; LEX_IDENT_PEEK — CUR_PTR位置から識別子(英字1文字+英数字*、末尾に
;   任意で%/$/#を1つ)を読み取る(CUR_PTRは進めない)。
;   出力: A=IDENT_KIND(0=識別子でない/1=無印/2=%/3=$/4=#)、
;         IDENT_BUF(8B、英字は大文字化・7文字まで格納・8バイト目は
;         接尾辞または0)、IDENT_LEN(消費するはずの文字数、8文字超の
;         識別子でも実際の文字数を数える)。
;   破壊: AF,BC,DE,HL。
; =======================================================================
LEX_IDENT_PEEK:
    LD HL,IDENT_BUF
    LD B,8
    XOR A
_lip_clear:
    LD (HL),A
    INC HL
    DJNZ _lip_clear
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    OR A
    JP Z,_lip_none
    CALL PEEK_CHAR
    CALL FOLD_UPPER
    CP 'A'
    JP C,_lip_none
    CP 'Z'+1
    JP NC,_lip_none
    XOR A
    LD (RUN_TMP16),A       ; LI_COUNT(格納数、0-7)
    LD (RUN_TMP16+1),A     ; LI_TOTAL(総消費数)
_lip_alnum_loop:
    CALL AT_END
    JR Z,_lip_alnum_done
    CALL PEEK_CHAR
    CALL FOLD_UPPER
    CP 'A'
    JR C,_lip_check_digit
    CP 'Z'+1
    JR C,_lip_alnum_take
_lip_check_digit:
    CP '0'
    JR C,_lip_alnum_done
    CP '9'+1
    JR NC,_lip_alnum_done
_lip_alnum_take:
    LD A,(RUN_TMP16)
    CP 7
    JR NC,_lip_alnum_skip_store
    LD HL,IDENT_BUF
    LD D,0
    LD E,A
    ADD HL,DE
    CALL PEEK_CHAR
    CALL FOLD_UPPER
    LD (HL),A
    LD A,(RUN_TMP16)
    INC A
    LD (RUN_TMP16),A
_lip_alnum_skip_store:
    CALL ADV_PTR
    LD A,(RUN_TMP16+1)
    INC A
    LD (RUN_TMP16+1),A
    JR _lip_alnum_loop
_lip_alnum_done:
    CALL AT_END
    JR Z,_lip_have_kind_plain
    CALL PEEK_CHAR
    CP '%'
    JR Z,_lip_suffix_percent
    CP '$'
    JR Z,_lip_suffix_string
    CP '#'
    JR Z,_lip_suffix_double
    JR _lip_have_kind_plain
_lip_suffix_percent:
    LD A,'%'
    LD (IDENT_BUF+7),A
    CALL ADV_PTR
    LD A,(RUN_TMP16+1)
    INC A
    LD (RUN_TMP16+1),A
    LD A,2
    JR _lip_finish
_lip_suffix_string:
    LD A,'$'
    LD (IDENT_BUF+7),A
    CALL ADV_PTR
    LD A,(RUN_TMP16+1)
    INC A
    LD (RUN_TMP16+1),A
    LD A,3
    JR _lip_finish
_lip_suffix_double:
    LD A,'#'
    LD (IDENT_BUF+7),A
    CALL ADV_PTR
    LD A,(RUN_TMP16+1)
    INC A
    LD (RUN_TMP16+1),A
    LD A,4
    JR _lip_finish
_lip_have_kind_plain:
    LD A,1
_lip_finish:
    ; ここまでCUR_PTRを実際に進めてしまっている(ADV_PTR/PEEK_CHARの
    ; 組み合わせで判定を進めたため)。PEEKという名前だが実装上は
    ; いったんCUR_PTRを動かして最後に戻す設計にする。
    LD (IDENT_KIND),A
    LD A,(RUN_TMP16+1)
    LD (IDENT_LEN),A
    ; CUR_PTRを元の位置(IDENT_LEN分戻す)へ復元する
    LD HL,(CUR_PTR)
    LD A,(IDENT_LEN)
    LD E,A
    LD D,0
    OR A
    SBC HL,DE
    LD (CUR_PTR),HL
    LD A,(IDENT_KIND)
    RET
_lip_none:
    XOR A
    LD (IDENT_KIND),A
    LD (IDENT_LEN),A
    RET

; LEX_IDENT_CONSUME — LEX_IDENT_PEEKと同じ判定を行い、識別子があれば
;   CUR_PTRをIDENT_LENぶん進める(PEEKが直前に戻した分をここで進め直す)。
;   出力: A=IDENT_KIND。破壊: AF,BC,DE,HL。
LEX_IDENT_CONSUME:
    CALL LEX_IDENT_PEEK
    LD A,(IDENT_KIND)
    OR A
    RET Z
    LD HL,(CUR_PTR)
    LD A,(IDENT_LEN)
    LD E,A
    LD D,0
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,(IDENT_KIND)
    RET

; =======================================================================
; 変数テーブル
; =======================================================================

; VAR_FIND — IDENT_BUF(8B)と一致するUSEDレコードを探す。
;   出力: A=1見つかった(HL=レコード先頭)/0見つからない
;         (RUN_VAR_FREE_PTRに最初の空きスロット、無ければ0)。
;   破壊: AF,BC,DE,HL。
VAR_FIND:
    XOR A
    LD H,A
    LD L,A
    LD (RUN_VAR_FREE_PTR),HL
    LD HL,RUN_VARTAB
    LD B,RUN_VARTAB_CAP
_vf_loop:
    PUSH HL
    LD DE,VARREC_USED
    ADD HL,DE
    LD A,(HL)
    POP HL
    OR A
    JR NZ,_vf_check_match
    LD DE,(RUN_VAR_FREE_PTR)
    LD A,D
    OR E
    JR NZ,_vf_next
    LD (RUN_VAR_FREE_PTR),HL
    JR _vf_next
_vf_check_match:
    PUSH HL
    PUSH BC
    LD DE,IDENT_BUF
    LD B,8
_vf_cmp:
    LD A,(DE)
    CP (HL)
    JR NZ,_vf_cmp_fail
    INC HL
    INC DE
    DJNZ _vf_cmp
    POP BC
    POP HL
    LD A,1
    RET
_vf_cmp_fail:
    POP BC
    POP HL
_vf_next:
    LD DE,RUN_VARTAB_REC_SIZE
    ADD HL,DE
    DJNZ _vf_loop
    XOR A
    RET

; VAR_ALLOC — RUN_VAR_FREE_PTRのスロットにIDENT_BUFを初期登録する
;   (USED=1,KIND=0,VALUE全0)。出力: A=1成功(HL=スロット)/0満杯。
VAR_ALLOC:
    LD HL,(RUN_VAR_FREE_PTR)
    LD A,H
    OR L
    JR Z,_va_full
    PUSH HL
    LD DE,IDENT_BUF
    LD B,8
_va_copyname:
    LD A,(DE)
    LD (HL),A
    INC HL
    INC DE
    DJNZ _va_copyname
    LD (HL),1
    INC HL
    LD (HL),0
    INC HL
    LD B,32
    XOR A
_va_clearval:
    LD (HL),A
    INC HL
    DJNZ _va_clearval
    POP HL
    LD A,1
    RET
_va_full:
    XOR A
    RET

; VAR_GET_OR_CREATE — IDENT_BUFのスロットを確実に用意する。
;   出力: A=1成功(HL=スロット)/0満杯。
VAR_GET_OR_CREATE:
    CALL VAR_FIND
    OR A
    RET NZ
    CALL VAR_ALLOC
    RET

; VAR_READ_NUMERIC — IDENT_BUFの変数の値をCUR_TYPE/CUR_DATAへ読む
;   (無ければ0で自動生成)。失敗時ERROR_FLAG/ERROR_KIND=7を設定。
;   M7段階4b-3: CUR_DATAが4→8バイトへ広がったのに合わせ、VALUEの
;   データ部も8バイト読むようにした(VARREC_VALUEは32バイトの余裕が
;   あり、型1+データ8=9バイトはこれまでどおり収まる。レコードサイズ
;   自体は変えていない)。
VAR_READ_NUMERIC:
    CALL VAR_GET_OR_CREATE
    OR A
    JR Z,_vrn_oom
    PUSH HL
    LD DE,VARREC_VALUE
    ADD HL,DE
    LD A,(HL)
    LD (CUR_TYPE),A
    INC HL
    LD DE,CUR_DATA
    LD B,8
_vrn_copy:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vrn_copy
    POP HL
    XOR A
    LD (ERROR_FLAG),A
    RET
_vrn_oom:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET

; VAR_WRITE_NUMERIC — IDENT_BUFの変数へCUR_TYPE/CUR_DATAを書く。
;   M7段階4b-3: VAR_READ_NUMERICと対で8バイトのデータ部を書く。
VAR_WRITE_NUMERIC:
    CALL VAR_GET_OR_CREATE
    OR A
    JR Z,_vwn_oom
    PUSH HL
    LD DE,VARREC_KIND
    ADD HL,DE
    LD (HL),0
    INC HL
    LD A,(CUR_TYPE)
    LD (HL),A
    INC HL
    EX DE,HL
    LD HL,CUR_DATA
    LD B,8
_vwn_copy:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vwn_copy
    POP HL
    XOR A
    LD (ERROR_FLAG),A
    RET
_vwn_oom:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET

; VAR_READ_STRING — IDENT_BUFの変数の文字列をRUN_STR_TMP_LEN/BUFへ読む。
VAR_READ_STRING:
    CALL VAR_GET_OR_CREATE
    OR A
    JR Z,_vrs_oom
    PUSH HL
    LD DE,VARREC_VALUE
    ADD HL,DE
    LD A,(HL)
    LD (RUN_STR_TMP_LEN),A
    LD B,A
    INC HL
    LD DE,RUN_STR_TMP_BUF
_vrs_copy:
    LD A,B
    OR A
    JR Z,_vrs_done
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DEC B
    JR _vrs_copy
_vrs_done:
    POP HL
    XOR A
    LD (ERROR_FLAG),A
    RET
_vrs_oom:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET

; VAR_WRITE_STRING — IDENT_BUFの変数へRUN_STR_TMP_LEN/BUFを書く
;   (31文字超はString too long)。
VAR_WRITE_STRING:
    LD A,(RUN_STR_TMP_LEN)
    CP 32
    JR NC,_vws_toolong
    CALL VAR_GET_OR_CREATE
    OR A
    JR Z,_vws_oom
    PUSH HL
    LD DE,VARREC_KIND
    ADD HL,DE
    LD (HL),1
    INC HL
    LD A,(RUN_STR_TMP_LEN)
    LD (HL),A
    LD B,A
    INC HL
    LD DE,RUN_STR_TMP_BUF
_vws_copy:
    LD A,B
    OR A
    JR Z,_vws_done
    LD A,(DE)
    LD (HL),A
    INC HL
    INC DE
    DEC B
    JR _vws_copy
_vws_done:
    POP HL
    XOR A
    LD (ERROR_FLAG),A
    RET
_vws_oom:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET
_vws_toolong:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,15
    LD (ERROR_KIND),A
    RET

; PRINT_STRING_VAL — RUN_STR_TMP_LEN/BUFの内容をそのまま出力する。
PRINT_STRING_VAL:
    LD A,(RUN_STR_TMP_LEN)
    LD B,A
    LD C,0
_psv_loop:
    LD A,B
    OR A
    RET Z
    LD HL,RUN_STR_TMP_BUF
    LD D,0
    LD E,C
    ADD HL,DE
    LD A,(HL)
    CALL PRINT_CHAR
    INC C
    DEC B
    JR _psv_loop

; PARSE_STRING_RHS — 文字列を要求する文脈(PRINT/代入)でCUR_PTR位置を
;   解釈する。'"'なら文字列リテラル(閉じ`"`か行末まで、31文字超は
;   切り詰め・仕様書に無い判断)。識別子で$型ならその変数の値。
;   それ以外はSyntax error(識別子でない)かType mismatch($以外の識別子)。
;   出力: RUN_STR_TMP_LEN/BUF、ERROR_FLAG。
PARSE_STRING_RHS:
    CALL PEEK_CHAR
    CP '"'
    JR Z,_psr_literal
    CALL LEX_IDENT_CONSUME
    OR A
    JR Z,_psr_syntax
    CP 3
    JR Z,_psr_fromvar
    LD A,1
    LD (ERROR_FLAG),A
    LD A,13
    LD (ERROR_KIND),A
    RET
_psr_fromvar:
    CALL VAR_READ_STRING
    RET
_psr_literal:
    CALL ADV_PTR
    XOR A
    LD (RUN_STR_TMP_LEN),A
_psr_lit_loop:
    CALL PEEK_CHAR
    OR A
    JR Z,_psr_lit_done
    CP '"'
    JR Z,_psr_lit_close
    LD B,A
    LD A,(RUN_STR_TMP_LEN)
    CP 31
    JR NC,_psr_lit_skip_store
    LD HL,RUN_STR_TMP_BUF
    LD D,0
    LD E,A
    ADD HL,DE
    LD (HL),B
    LD A,(RUN_STR_TMP_LEN)
    INC A
    LD (RUN_STR_TMP_LEN),A
_psr_lit_skip_store:
    CALL ADV_PTR
    JR _psr_lit_loop
_psr_lit_close:
    CALL ADV_PTR
_psr_lit_done:
    XOR A
    LD (ERROR_FLAG),A
    RET
_psr_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET

; =======================================================================
; ASSIGN_STMT — RUN_ASSIGN_KIND/RUN_ASSIGN_NAMEに設定済みの変数へ、
;   CUR_PTR位置の'='直後の式を評価して代入する。
; =======================================================================
; M7段階4b-3: kind=4(#、倍精度)の代入を実装した(以前はType mismatchの
; 暫定扱い、_as_double_unsup)。docs/spec/l4-program.md 第4.4c節「単精度の
; 値を#変数へ代入すると単精度の値がそのまま倍精度になる(変換自体は正確)」
; の観測どおり、右辺の型を問わずVAL_PROMOTE_CUR_TO_DOUBLE(interp.asm)で
; 厳密に倍精度へ揃えてから書く。kind=2(%)側も、右辺が倍精度(CUR_TYPE=2)
; のときは先に単精度へ変換してから既存の丸め経路(MBF_ROUND_TO_INT16、
; 単精度専用)へ渡す(仕様書に無い判断: %への倍精度の丸めそのものは
; 測定されていないため、単精度を経由する二段丸めで代用する)。
ASSIGN_STMT:
    LD A,(RUN_ASSIGN_KIND)
    CP 3
    JP Z,_as_string
    CALL EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(RUN_ASSIGN_KIND)
    CP 4
    JR Z,_as_promote_double
    CP 2
    JR NZ,_as_store_plain
    LD A,(CUR_TYPE)
    CP 2
    JR NZ,_as_pct_have_type
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL MBF_DTOS
    CALL VAL_SET_SINGLE_FROM_RES
_as_pct_have_type:
    LD A,(CUR_TYPE)
    OR A
    JR Z,_as_store_plain
    CALL VAL_LOAD_CUR_TO_OPA
    CALL MBF_ROUND_TO_INT16
    OR A
    JR Z,_as_overflow
    EX DE,HL
    CALL VAL_SET_INT
    JR _as_store_plain
_as_promote_double:
    CALL VAL_PROMOTE_CUR_TO_DOUBLE
_as_store_plain:
    LD HL,RUN_ASSIGN_NAME
    LD DE,IDENT_BUF
    LD B,8
_as_copyname:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _as_copyname
    JP VAR_WRITE_NUMERIC
_as_overflow:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET
_as_string:
    CALL PARSE_STRING_RHS
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,RUN_ASSIGN_NAME
    LD DE,IDENT_BUF
    LD B,8
_as_copyname2:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _as_copyname2
    JP VAR_WRITE_STRING

; =======================================================================
; MBF_ROUND_TO_INT16 — MBF_OPA(単精度)を符号付き16bitへ、半分は絶対値の
;   大きい側へ丸めて変換する(l4-basic.md第5.3節・l4-program.md第4.4b節)。
;   出力: A=1成功,DE=結果 / A=0範囲外。破壊: AF,BC,DE,HL,UA_*等。
; =======================================================================
MBF_ROUND_TO_INT16:
    CALL MBF_UNPACK_A
    LD A,(UA_EXP)
    OR A
    JR NZ,_mri_nonzero
    LD DE,0
    LD A,1
    RET
; 訂正(実装時に踏んだ不具合): value = mantissa24 * 2^(E-24)
; (mantissa24は[2^23,2^24)、MBF_INT_TO_SINGLEの導出コメント
; 「exp=144-shifts」・「v*2^shifts*256=mant24」と同じ式を24bit側から
; 見た形)。よってvは[2^(E-1),2^E)に入り、シフト量は24-E
; （旧版は23-Eとしており1.5が3に丸まる不具合が出た）。E=-1(v∈
; [0.25,0.5))は0へ丸まるのが正しく、以前あった「E=-1は特別に1」という
; 分岐(_mri_half)は誤りだったため削除し、他の負のEと同じ
; (_mri_zero_small、0へ)扱いに統一した。
_mri_nonzero:
    LD A,(UA_EXP)
    SUB 128
    LD (RUN_TMP_E),A
    BIT 7,A
    JP NZ,_mri_zero_small
    CP 24
    JP NC,_mri_overflow
    LD B,A
    LD A,24
    SUB B
    LD (RUN_TMP_SHIFT),A
    LD A,(UA_M2)
    LD (RUN_TMP_M2),A
    LD A,(UA_M1)
    LD (RUN_TMP_M1),A
    LD A,(UA_M0)
    LD (RUN_TMP_M0),A
    LD A,(RUN_TMP_SHIFT)
    OR A
    JR Z,_mri_no_shift
    LD B,A
    XOR A
    LD (RUN_TMP_RBIT),A
_mri_shift_loop:
    LD A,(RUN_TMP_M2)
    SRL A
    LD (RUN_TMP_M2),A
    LD A,(RUN_TMP_M1)
    RR A
    LD (RUN_TMP_M1),A
    LD A,(RUN_TMP_M0)
    RR A
    LD (RUN_TMP_M0),A
    LD A,0
    JR NC,_mri_bit0
    LD A,1
_mri_bit0:
    LD (RUN_TMP_RBIT),A
    DJNZ _mri_shift_loop
_mri_no_shift:
    LD A,(RUN_TMP_RBIT)
    OR A
    JR Z,_mri_no_round
    LD A,(RUN_TMP_M0)
    INC A
    LD (RUN_TMP_M0),A
    OR A
    JR NZ,_mri_no_round
    LD A,(RUN_TMP_M1)
    INC A
    LD (RUN_TMP_M1),A
    OR A
    JR NZ,_mri_no_round
    LD A,(RUN_TMP_M2)
    INC A
    LD (RUN_TMP_M2),A
_mri_no_round:
    LD A,(RUN_TMP_M2)
    OR A
    JR NZ,_mri_overflow
    LD A,(RUN_TMP_M1)
    LD H,A
    LD A,(RUN_TMP_M0)
    LD L,A
    LD A,(UA_SIGN)
    OR A
    JR NZ,_mri_neg
    LD DE,32768
    CALL CP_HL_DE
    JR NC,_mri_overflow
    EX DE,HL
    LD A,1
    RET
_mri_neg:
    LD DE,32769
    CALL CP_HL_DE
    JR NC,_mri_overflow
    XOR A
    SUB L
    LD E,A
    LD A,0
    SBC A,H
    LD D,A
    LD A,1
    RET
_mri_zero_small:
    LD DE,0
    LD A,1
    RET
_mri_overflow:
    XOR A
    RET

; =======================================================================
; 数値比較・符号判定
; =======================================================================

; VAL_COMPARE_CUR_RHS — CUR_TYPE/CUR_DATAとRHS_TYPE/RHS_DATAを比較する
;   (両方を単精度へ揃えてMBF_CMPを使う)。出力: A=0等しい/1 CUR>RHS/
;   0xFF CUR<RHS。破壊: AF,HL,UA_*・UB_*等。
VAL_COMPARE_CUR_RHS:
    CALL VAL_LOAD_CUR_TO_OPA
    CALL VAL_LOAD_RHS_TO_OPB
    CALL MBF_CMP
    LD A,(MBF_OUT_CMP)
    RET

; VAL_IS_NEGATIVE — CUR_TYPE/CUR_DATAが負なら1、0以上なら0を返す
;   (RHSを0にしてVAL_COMPARE_CUR_RHSを使う。RHS_TYPE/DATAを破壊する)。
VAL_IS_NEGATIVE:
    XOR A
    LD (RHS_TYPE),A
    LD HL,0
    LD (RHS_DATA),HL
    LD (RHS_DATA+2),HL
    CALL VAL_COMPARE_CUR_RHS
    CP 0FFh
    JR Z,_vin_neg
    XOR A
    RET
_vin_neg:
    LD A,1
    RET

; =======================================================================
; プログラム位置の移動
; =======================================================================

; RUN_ENTER_RECORD — HL=レコード先頭。RUN_CUR_RECORD/RUN_CUR_LINENO/
;   CUR_PTR/LINE_ENDを設定する。破壊: AF,BC,HL。
RUN_ENTER_RECORD:
    LD (RUN_CUR_RECORD),HL
    LD A,(HL)
    LD (RUN_CUR_LINENO),A
    INC HL
    LD A,(HL)
    LD (RUN_CUR_LINENO+1),A
    INC HL
    LD A,(HL)
    LD C,A
    LD B,0
    INC HL
    LD (CUR_PTR),HL
    ADD HL,BC
    LD (LINE_END),HL
    RET

; RUN_ADVANCE_RECORD — RUN_CUR_RECORDの次のレコードへ進める。
;   出力: A=1成功(RUN_ENTER_RECORD相当を実施済み)/0番兵(プログラム終端)。
;   破壊: AF,BC,DE,HL。
RUN_ADVANCE_RECORD:
    LD HL,(RUN_CUR_RECORD)
    LD DE,2
    ADD HL,DE
    LD A,(HL)
    LD C,A
    LD B,0
    INC BC
    INC BC
    INC BC
    LD HL,(RUN_CUR_RECORD)
    ADD HL,BC
    LD A,(HL)
    LD B,A
    PUSH HL
    INC HL
    LD A,(HL)
    POP HL
    CP 0FFh
    JR NZ,_rar_have
    LD A,B
    CP 0FFh
    JR NZ,_rar_have
    XOR A
    RET
_rar_have:
    CALL RUN_ENTER_RECORD
    LD A,1
    RET

; RUN_FIND_LINE — HL=目的の行番号。program.asmのPROGRAM_LOCATEを使う。
;   出力: CF=0/HL=レコード先頭(見つかった) / CF=1(見つからない)。
;   破壊: AF,BC,DE,HL。
RUN_FIND_LINE:
    LD (PROG_CUR_LINENO),HL
    CALL PROGRAM_LOCATE
    OR A
    JR Z,_rfl_notfound
    OR A
    RET
_rfl_notfound:
    SCF
    RET

; PARSE_LINENUM_CUR — CUR_PTR位置の10進数字列を行番号として読む
;   (program.asm PARSE_LINENUMと同じ規則・上限65529、CUR_PTR基準版)。
;   出力: CF=0/HL=値、CUR_PTRを消費した分だけ進める。CF=1失敗
;   (桁が無い、または65529超、CUR_PTRは進めた分だけ残る)。
;   破壊: AF,BC,DE,HL。
PARSE_LINENUM_CUR:
    LD HL,0
    LD B,0
_plc_loop:
    CALL PEEK_CHAR
    CP '0'
    JR C,_plc_finish
    CP '9'+1
    JR NC,_plc_finish
    SUB '0'
    LD E,A
    LD D,0
    LD (PROG_DIGIT),DE
    LD (PROG_TMP16),HL
    ADD HL,HL
    JR C,_plc_ovfl
    ADD HL,HL
    JR C,_plc_ovfl
    LD DE,(PROG_TMP16)
    ADD HL,DE
    JR C,_plc_ovfl
    ADD HL,HL
    JR C,_plc_ovfl
    LD DE,(PROG_DIGIT)
    ADD HL,DE
    JR C,_plc_ovfl
    CALL ADV_PTR
    INC B
    JR _plc_loop
_plc_finish:
    LD A,B
    OR A
    JR Z,_plc_ovfl
    LD DE,65530
    CALL CP_HL_DE
    JR NC,_plc_ovfl
    OR A
    RET
_plc_ovfl:
    SCF
    RET

; =======================================================================
; FORスタック
; =======================================================================

; FOR_SLOT_ADDR — A=インデックス(0-7)。HL=RUN_FOR_STACK+インデックス*24。
;   破壊: HL,DE。
FOR_SLOT_ADDR:
    LD H,0
    LD L,A
    LD D,H
    LD E,L
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    PUSH HL
    ADD HL,HL
    POP DE
    ADD HL,DE
    LD DE,RUN_FOR_STACK
    ADD HL,DE
    RET

; RUN_FOR_PUSH — RUN_FOR_VARNAME/LIMIT/STEPと現在位置(RUN_CUR_RECORD/
;   CUR_PTR/LINE_END)をFORスタックへ積む。破壊: AF,BC,DE,HL。
RUN_FOR_PUSH:
    LD A,(RUN_FOR_SP)
    CP RUN_FOR_STACK_CAP
    JR NC,_rfp_oom
    CALL FOR_SLOT_ADDR
    PUSH HL
    LD DE,RUN_FOR_VARNAME
    LD B,8
_rfp_copyname:
    LD A,(DE)
    LD (HL),A
    INC HL
    INC DE
    DJNZ _rfp_copyname
    LD A,(RUN_FOR_LIMIT_TYPE)
    LD (HL),A
    INC HL
    LD A,(RUN_FOR_LIMIT_DATA)
    LD (HL),A
    INC HL
    LD A,(RUN_FOR_LIMIT_DATA+1)
    LD (HL),A
    INC HL
    LD A,(RUN_FOR_LIMIT_DATA+2)
    LD (HL),A
    INC HL
    LD A,(RUN_FOR_LIMIT_DATA+3)
    LD (HL),A
    INC HL
    LD A,(RUN_FOR_STEP_TYPE)
    LD (HL),A
    INC HL
    LD A,(RUN_FOR_STEP_DATA)
    LD (HL),A
    INC HL
    LD A,(RUN_FOR_STEP_DATA+1)
    LD (HL),A
    INC HL
    LD A,(RUN_FOR_STEP_DATA+2)
    LD (HL),A
    INC HL
    LD A,(RUN_FOR_STEP_DATA+3)
    LD (HL),A
    INC HL
    LD DE,(RUN_CUR_RECORD)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD DE,(CUR_PTR)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD DE,(LINE_END)
    LD (HL),E
    INC HL
    LD (HL),D
    POP HL
    LD A,(RUN_FOR_SP)
    INC A
    LD (RUN_FOR_SP),A
    XOR A
    LD (ERROR_FLAG),A
    RET
_rfp_oom:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET

; RUN_FOR_POP_DISCARD — FORスタックを1つ減らす(中身は使わない)。
RUN_FOR_POP_DISCARD:
    LD A,(RUN_FOR_SP)
    DEC A
    LD (RUN_FOR_SP),A
    RET

; RUN_FOR_FIND_BY_NAME — IDENT_BUFと同名のフレームをスタックの上から
;   探す。見つかったらRUN_FOR_SPをそのフレーム(含む)までに切り詰める
;   (内側の閉じていないループは暗黙に閉じる)。
;   出力: A=1見つかった/0見つからない(RUN_FOR_SP不変)。
RUN_FOR_FIND_BY_NAME:
    LD A,(RUN_FOR_SP)
    LD (RUN_FOR_SEARCH_IDX),A
_rffbn_loop:
    LD A,(RUN_FOR_SEARCH_IDX)
    OR A
    JR Z,_rffbn_notfound
    DEC A
    LD (RUN_FOR_SEARCH_IDX),A
    CALL FOR_SLOT_ADDR
    PUSH HL
    LD DE,IDENT_BUF
    LD B,8
_rffbn_cmp:
    LD A,(DE)
    CP (HL)
    JR NZ,_rffbn_mismatch
    INC HL
    INC DE
    DJNZ _rffbn_cmp
    POP HL
    LD A,(RUN_FOR_SEARCH_IDX)
    INC A
    LD (RUN_FOR_SP),A
    LD A,1
    RET
_rffbn_mismatch:
    POP HL
    JR _rffbn_loop
_rffbn_notfound:
    XOR A
    RET

; RUN_FOR_RESTORE_RESUME — RUN_FOR_FRAME_PTRのフレームの再開位置
;   (offset18:record2B/20:curptr2B/22:lineend2B)をRUN_CUR_RECORD/
;   CUR_PTR/LINE_ENDへ書き戻す。NEXTがループ本体へ戻るときに使う
;   (過去に実際に踏んだ不具合: ここが無いと変数の更新だけが起きて
;   実行位置がNEXT自身の直後のまま進み、ループが1周もしなかった)。
;   破壊: AF,DE,HL。
RUN_FOR_RESTORE_RESUME:
    LD HL,(RUN_FOR_FRAME_PTR)
    LD DE,18
    ADD HL,DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    PUSH DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    PUSH DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    PUSH DE
    POP HL
    LD (LINE_END),HL
    POP HL
    LD (CUR_PTR),HL
    POP HL
    LD (RUN_CUR_RECORD),HL
    LD A,(HL)
    LD (RUN_CUR_LINENO),A
    INC HL
    LD A,(HL)
    LD (RUN_CUR_LINENO+1),A
    RET

; RUN_FOR_TEST_BOUNDS — RUN_FOR_FRAME_PTRのフレームについて、現在の
;   変数値がSTEPの符号に応じてLIMITを越えているか判定する。
;   出力: A=1越えている(停止/スキップすべき)/0範囲内。
;   破壊: AF,BC,DE,HL,CUR_*,RHS_*等。
RUN_FOR_TEST_BOUNDS:
    LD HL,(RUN_FOR_FRAME_PTR)
    LD DE,IDENT_BUF
    LD B,8
_rftb_copyname:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _rftb_copyname
    CALL VAR_READ_NUMERIC
    LD HL,(RUN_FOR_FRAME_PTR)
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    LD (RHS_TYPE),A
    INC HL
    LD A,(HL)
    LD (RHS_DATA),A
    INC HL
    LD A,(HL)
    LD (RHS_DATA+1),A
    INC HL
    LD A,(HL)
    LD (RHS_DATA+2),A
    INC HL
    LD A,(HL)
    LD (RHS_DATA+3),A
    CALL VAL_COMPARE_CUR_RHS
    LD (RUN_FOR_CMP_RESULT),A
    LD HL,(RUN_FOR_FRAME_PTR)
    LD DE,13
    ADD HL,DE
    LD A,(HL)
    LD (CUR_TYPE),A
    INC HL
    LD A,(HL)
    LD (CUR_DATA),A
    INC HL
    LD A,(HL)
    LD (CUR_DATA+1),A
    INC HL
    LD A,(HL)
    LD (CUR_DATA+2),A
    INC HL
    LD A,(HL)
    LD (CUR_DATA+3),A
    CALL VAL_IS_NEGATIVE
    LD B,A
    LD A,(RUN_FOR_CMP_RESULT)
    LD C,A
    LD A,B
    OR A
    JR NZ,_rftb_step_neg
    LD A,C
    CP 1
    JR Z,_rftb_out
    JR _rftb_in
_rftb_step_neg:
    LD A,C
    CP 0FFh
    JR Z,_rftb_out
_rftb_in:
    XOR A
    RET
_rftb_out:
    LD A,1
    RET

; RUN_FOR_CHECK_SKIP — 直前にRUN_FOR_PUSHで積んだトップフレームが、
;   最初から範囲外(本体スキップ)かどうかを判定する。
;   出力: A=1スキップすべき/0本体へ入る。
RUN_FOR_CHECK_SKIP:
    LD A,(RUN_FOR_SP)
    DEC A
    CALL FOR_SLOT_ADDR
    LD (RUN_FOR_FRAME_PTR),HL
    CALL RUN_FOR_TEST_BOUNDS
    RET

; RUN_FOR_STEP_AND_TEST — トップフレームの変数へSTEPを加え、書き戻し、
;   範囲を判定する。出力: A=1継続(ループ本体へ戻る)/0終了(スタックは
;   ポップしない、呼び出し元がPOPする)。破壊多数。
RUN_FOR_STEP_AND_TEST:
    LD A,(RUN_FOR_SP)
    DEC A
    CALL FOR_SLOT_ADDR
    LD (RUN_FOR_FRAME_PTR),HL
    LD DE,IDENT_BUF
    LD B,8
_rfsat_copyname:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _rfsat_copyname
    CALL VAR_READ_NUMERIC
    LD HL,(RUN_FOR_FRAME_PTR)
    LD DE,13
    ADD HL,DE
    LD A,(HL)
    LD (RHS_TYPE),A
    INC HL
    LD A,(HL)
    LD (RHS_DATA),A
    INC HL
    LD A,(HL)
    LD (RHS_DATA+1),A
    INC HL
    LD A,(HL)
    LD (RHS_DATA+2),A
    INC HL
    LD A,(HL)
    LD (RHS_DATA+3),A
    CALL VAL_ADD
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,(RUN_FOR_FRAME_PTR)
    LD DE,IDENT_BUF
    LD B,8
_rfsat_copyname2:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _rfsat_copyname2
    CALL VAR_WRITE_NUMERIC
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL RUN_FOR_TEST_BOUNDS
    OR A
    JR Z,_rfsat_continue
    XOR A
    RET
_rfsat_continue:
    LD A,1
    RET

; RUN_SKIP_REST_OF_STATEMENT — CUR_PTRを':'か行末まで進める
;   (仕様書に無い判断: 文字列リテラル中の':'は特別扱いしない)。
RUN_SKIP_REST_OF_STATEMENT:
_rsros_loop:
    CALL AT_END
    RET Z
    CALL PEEK_CHAR
    CP ':'
    RET Z
    CALL ADV_PTR
    JR _rsros_loop

; RUN_SKIP_TO_MATCHING_NEXT — 現在位置から、入れ子を数えながら対応する
;   NEXTを探し、その直後(変数名があれば消費した位置)まで進める。
;   見つからなければFOR without NEXT(26)。破壊多数。
RUN_SKIP_TO_MATCHING_NEXT:
    XOR A
    LD (RUN_SCAN_DEPTH),A
_rstmn_stmt_loop:
    CALL SKIP_SPACES
    CALL AT_END
    JR Z,_rstmn_next_record
    CALL TRY_MATCH_FOR
    OR A
    JR Z,_rstmn_try_next_kw
    LD A,(RUN_SCAN_DEPTH)
    INC A
    LD (RUN_SCAN_DEPTH),A
    JR _rstmn_skip_rest_of_stmt
_rstmn_try_next_kw:
    CALL TRY_MATCH_NEXT
    OR A
    JR Z,_rstmn_skip_rest_of_stmt
    CALL SKIP_SPACES
    CALL LEX_IDENT_PEEK
    OR A
    JR Z,_rstmn_next_noname
    CALL LEX_IDENT_CONSUME
_rstmn_next_noname:
    LD A,(RUN_SCAN_DEPTH)
    OR A
    JR Z,_rstmn_found
    DEC A
    LD (RUN_SCAN_DEPTH),A
    JR _rstmn_after_stmt
_rstmn_skip_rest_of_stmt:
    CALL RUN_SKIP_REST_OF_STATEMENT
_rstmn_after_stmt:
    CALL AT_END
    JR Z,_rstmn_next_record
    CALL PEEK_CHAR
    CP ':'
    JR NZ,_rstmn_next_record
    CALL ADV_PTR
    JR _rstmn_stmt_loop
_rstmn_next_record:
    CALL RUN_ADVANCE_RECORD
    OR A
    JR Z,_rstmn_notfound
    JR _rstmn_stmt_loop
_rstmn_found:
    XOR A
    LD (ERROR_FLAG),A
    RET
_rstmn_notfound:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,26
    LD (ERROR_KIND),A
    RET

; =======================================================================
; GOSUBスタック
; =======================================================================

RUN_GOSUB_PUSH:
    LD A,(RUN_GOSUB_SP)
    CP RUN_GOSUB_STACK_CAP
    JR NC,_rgp_oom
    LD H,0
    LD L,A
    ADD HL,HL
    LD D,H
    LD E,L
    ADD HL,HL
    ADD HL,DE
    LD DE,RUN_GOSUB_STACK
    ADD HL,DE
    LD DE,(RUN_CUR_RECORD)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD DE,(CUR_PTR)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD DE,(LINE_END)
    LD (HL),E
    INC HL
    LD (HL),D
    LD A,(RUN_GOSUB_SP)
    INC A
    LD (RUN_GOSUB_SP),A
    XOR A
    LD (ERROR_FLAG),A
    RET
_rgp_oom:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET

; =======================================================================
; 文ハンドラ(RUN_EXECから呼ばれる)
; =======================================================================

GOTO_STMT:
    CALL SKIP_SPACES
    CALL PARSE_LINENUM_CUR
    JR C,_goto_syntax
    CALL RUN_FIND_LINE
    JR C,_goto_undef
    CALL RUN_ENTER_RECORD
    LD A,1
    LD (RUN_CTRL),A
    XOR A
    LD (ERROR_FLAG),A
    RET
_goto_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET
_goto_undef:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,8
    LD (ERROR_KIND),A
    RET

GOSUB_STMT:
    CALL SKIP_SPACES
    CALL PARSE_LINENUM_CUR
    JR C,_gosub_syntax
    LD (RUN_TMP16),HL
    CALL RUN_GOSUB_PUSH
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,(RUN_TMP16)
    CALL RUN_FIND_LINE
    JR C,_gosub_undef
    CALL RUN_ENTER_RECORD
    LD A,1
    LD (RUN_CTRL),A
    XOR A
    LD (ERROR_FLAG),A
    RET
_gosub_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET
_gosub_undef:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,8
    LD (ERROR_KIND),A
    RET

RETURN_STMT:
    LD A,(RUN_GOSUB_SP)
    OR A
    JR Z,_ret_nogosub
    DEC A
    LD (RUN_GOSUB_SP),A
    LD H,0
    LD L,A
    ADD HL,HL
    LD D,H
    LD E,L
    ADD HL,HL
    ADD HL,DE
    LD DE,RUN_GOSUB_STACK
    ADD HL,DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    PUSH DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    PUSH DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    PUSH DE
    POP HL
    LD (LINE_END),HL
    POP HL
    LD (CUR_PTR),HL
    POP HL
    LD (RUN_CUR_RECORD),HL
    LD A,(HL)
    LD (RUN_CUR_LINENO),A
    INC HL
    LD A,(HL)
    LD (RUN_CUR_LINENO+1),A
    LD A,1
    LD (RUN_CTRL),A
    XOR A
    LD (ERROR_FLAG),A
    RET
_ret_nogosub:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,3
    LD (ERROR_KIND),A
    RET

FOR_STMT:
    CALL SKIP_SPACES
    CALL LEX_IDENT_CONSUME
    OR A
    JP Z,_for_syntax
    CP 3
    JP Z,_for_typeerr
    CP 4
    JP Z,_for_typeerr
    LD HL,IDENT_BUF
    LD DE,RUN_FOR_VARNAME
    LD B,8
_for_copyname1:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _for_copyname1
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '='
    JP NZ,_for_syntax
    CALL ADV_PTR
    CALL EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,RUN_FOR_VARNAME
    LD DE,IDENT_BUF
    LD B,8
_for_copyname2:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _for_copyname2
    CALL VAR_WRITE_NUMERIC
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL SKIP_SPACES
    CALL TRY_MATCH_TO
    OR A
    JP Z,_for_syntax
    CALL EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(CUR_TYPE)
    LD (RUN_FOR_LIMIT_TYPE),A
    LD HL,(CUR_DATA)
    LD (RUN_FOR_LIMIT_DATA),HL
    LD HL,(CUR_DATA+2)
    LD (RUN_FOR_LIMIT_DATA+2),HL
    CALL SKIP_SPACES
    CALL TRY_MATCH_STEP
    OR A
    JR Z,_for_default_step
    CALL EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JR _for_have_step
_for_default_step:
    LD HL,1
    CALL VAL_SET_INT
_for_have_step:
    LD A,(CUR_TYPE)
    LD (RUN_FOR_STEP_TYPE),A
    LD HL,(CUR_DATA)
    LD (RUN_FOR_STEP_DATA),HL
    LD HL,(CUR_DATA+2)
    LD (RUN_FOR_STEP_DATA+2),HL
    CALL RUN_FOR_PUSH
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL RUN_FOR_CHECK_SKIP
    OR A
    JR Z,_for_enter_body
    CALL RUN_FOR_POP_DISCARD
    CALL RUN_SKIP_TO_MATCHING_NEXT
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,1
    LD (RUN_CTRL),A
    RET
_for_enter_body:
    XOR A
    LD (RUN_CTRL),A
    RET
_for_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET
_for_typeerr:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,13
    LD (ERROR_KIND),A
    RET

NEXT_STMT:
    CALL SKIP_SPACES
    CALL LEX_IDENT_PEEK
    OR A
    JR Z,_next_no_name
    CP 3
    JR Z,_next_typeerr
    CP 4
    JR Z,_next_typeerr
    CALL LEX_IDENT_CONSUME
    CALL RUN_FOR_FIND_BY_NAME
    OR A
    JR Z,_next_nofor
    JR _next_have_frame
_next_no_name:
    LD A,(RUN_FOR_SP)
    OR A
    JR Z,_next_nofor
_next_have_frame:
    CALL RUN_FOR_STEP_AND_TEST
    LD B,A                  ; 継続可否(1=継続/0=終了)を退避
                             ; (直後のERROR_FLAG確認でAを潰すため。
                             ; 過去に実際に踏んだ不具合、報告参照:
                             ; ここを退避せず2回目のOR Aが常にERROR_FLAG
                             ; の値〔0〕を見てしまい、毎回1周目で
                             ; ループを終了扱いにしていた)
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,B
    OR A
    JR Z,_next_done
    CALL RUN_FOR_RESTORE_RESUME
    LD A,1
    LD (RUN_CTRL),A
    RET
_next_done:
    CALL RUN_FOR_POP_DISCARD
    XOR A
    LD (RUN_CTRL),A
    RET
_next_nofor:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,1
    LD (ERROR_KIND),A
    RET
_next_typeerr:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,13
    LD (ERROR_KIND),A
    RET

END_STMT:
    XOR A
    LD (ERROR_FLAG),A
    LD A,2
    LD (RUN_CTRL),A
    RET

STOP_STMT:
    XOR A
    LD (ERROR_FLAG),A
    LD A,2
    LD (RUN_CTRL),A
    CALL RUN_EMIT_STOP
    RET

; =======================================================================
; エラー・停止の出力(RUNは常に1行、l4-program.md第4.5節)
; =======================================================================

RUN_EMIT_ERROR:
    CALL SELECT_ERROR_MSG
    CALL PRINT_STR
    LD HL,RUN_INTXT
    CALL PRINT_STR
    LD HL,(RUN_CUR_LINENO)
    CALL PRINT_UDEC
    CALL NEWLINE
    RET

RUN_EMIT_STOP:
    LD HL,RUN_BREAK_TXT
    CALL PRINT_STR
    LD HL,RUN_INTXT
    CALL PRINT_STR
    LD HL,(RUN_CUR_LINENO)
    CALL PRINT_UDEC
    CALL NEWLINE
    RET

; =======================================================================
; RUN_MATCH_STMT_KEYWORD / RUN_EXEC — プログラム実行の駆動部
; =======================================================================

RUN_MATCH_STMT_KEYWORD:
    XOR A
    LD (RUN_STMT_KIND),A
    CALL TRY_MATCH_PRINT
    OR A
    RET NZ
    CALL TRY_MATCH_GOTO
    OR A
    JR Z,_rmsk_try_gosub
    LD A,1
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_gosub:
    CALL TRY_MATCH_GOSUB
    OR A
    JR Z,_rmsk_try_return
    LD A,2
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_return:
    CALL TRY_MATCH_RETURN
    OR A
    JR Z,_rmsk_try_for
    LD A,3
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_for:
    CALL TRY_MATCH_FOR
    OR A
    JR Z,_rmsk_try_next
    LD A,4
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_next:
    CALL TRY_MATCH_NEXT
    OR A
    JR Z,_rmsk_try_end
    LD A,5
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_end:
    CALL TRY_MATCH_END
    OR A
    JR Z,_rmsk_try_stop
    LD A,6
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_stop:
    CALL TRY_MATCH_STOP
    OR A
    JR Z,_rmsk_try_assign
    LD A,7
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_assign:
    CALL LEX_IDENT_PEEK
    OR A
    RET Z
    LD (RUN_ASSIGN_KIND),A
    CALL LEX_IDENT_CONSUME
    LD HL,IDENT_BUF
    LD DE,RUN_ASSIGN_NAME
    LD B,8
_rmsk_copyname:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _rmsk_copyname
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '='
    JR NZ,_rmsk_assign_fail
    CALL ADV_PTR
    LD A,8
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_assign_fail:
    XOR A
    RET

RUN_EXEC:
_run_loop:
_run_stmt_loop:
    CALL SKIP_SPACES
    CALL AT_END
    JP Z,_run_line_end
    CALL RUN_MATCH_STMT_KEYWORD
    OR A
    JP Z,_run_syntax_error
    LD A,(RUN_STMT_KIND)
    CP 0
    JR Z,_run_do_print
    CP 1
    JR Z,_run_do_goto
    CP 2
    JR Z,_run_do_gosub
    CP 3
    JR Z,_run_do_return
    CP 4
    JR Z,_run_do_for
    CP 5
    JR Z,_run_do_next
    CP 6
    JR Z,_run_do_end
    CP 7
    JR Z,_run_do_stop
    CALL ASSIGN_STMT
    XOR A
    LD (RUN_CTRL),A
    JR _run_after_stmt
_run_do_print:
    CALL PRINT_STMT
    XOR A
    LD (RUN_CTRL),A
    JR _run_after_stmt
_run_do_goto:
    CALL GOTO_STMT
    JR _run_after_stmt
_run_do_gosub:
    CALL GOSUB_STMT
    JR _run_after_stmt
_run_do_return:
    CALL RETURN_STMT
    JR _run_after_stmt
_run_do_for:
    CALL FOR_STMT
    JR _run_after_stmt
_run_do_next:
    CALL NEXT_STMT
    JR _run_after_stmt
_run_do_end:
    CALL END_STMT
    JR _run_after_stmt
_run_do_stop:
    CALL STOP_STMT
_run_after_stmt:
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_run_error
    LD A,(RUN_CTRL)
    CP 2
    JR Z,_run_halted
    CP 1
    JR Z,_run_loop
    CALL SKIP_SPACES
    CALL AT_END
    JR Z,_run_line_end
    CALL PEEK_CHAR
    CP ':'
    JR NZ,_run_syntax_error
    CALL ADV_PTR
    JP _run_stmt_loop
_run_line_end:
    CALL RUN_ADVANCE_RECORD
    OR A
    JR Z,_run_normal_end
    JP _run_loop
_run_normal_end:
    RET
_run_halted:
    RET
_run_error:
    CALL RUN_EMIT_ERROR
    XOR A
    LD (ERROR_FLAG),A
    RET
_run_syntax_error:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    CALL RUN_EMIT_ERROR
    XOR A
    LD (ERROR_FLAG),A
    RET

; RUN_RESET_STATE — 変数テーブル・FOR/GOSUBスタックを初期化する
;   (ヘッダコメント「RUNは呼ぶたびに初期化する」参照)。
RUN_RESET_STATE:
    XOR A
    LD (RUN_FOR_SP),A
    LD (RUN_GOSUB_SP),A
    LD HL,RUN_VARTAB
    LD B,RUN_VARTAB_CAP
_rrs_loop:
    PUSH HL
    LD DE,VARREC_USED
    ADD HL,DE
    LD (HL),0
    POP HL
    LD DE,RUN_VARTAB_REC_SIZE
    ADD HL,DE
    DJNZ _rrs_loop
    RET

; RUN_STMT — 直接モードの"RUN"文(interp.asm MATCH_STMT_KEYWORDから
;   STMT_KIND=3で呼ばれる)。引数無しなら先頭行から、行番号指定があれば
;   その行から実行する(第4.1節)。
RUN_STMT:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,_run_stmt_no_arg
    CP ':'
    JR Z,_run_stmt_no_arg
    CALL PARSE_LINENUM_CUR
    JR C,_run_stmt_syntax
    LD (RUN_TMP16),HL
    CALL RUN_RESET_STATE
    LD HL,(RUN_TMP16)
    CALL RUN_FIND_LINE
    JR C,_run_stmt_undef
    JR _run_stmt_start
_run_stmt_no_arg:
    CALL RUN_RESET_STATE
    LD HL,PROGRAM_AREA
    LD A,(HL)
    LD B,A
    PUSH HL
    INC HL
    LD A,(HL)
    POP HL
    CP 0FFh
    JR NZ,_run_stmt_start
    LD A,B
    CP 0FFh
    JR NZ,_run_stmt_start
    XOR A
    LD (ERROR_FLAG),A
    RET
_run_stmt_start:
    CALL RUN_ENTER_RECORD
    JP RUN_EXEC
_run_stmt_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET
_run_stmt_undef:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,8
    LD (ERROR_KIND),A
    RET

; TRY_MATCH_GOTO — 固定語形"GOTO"を大文字小文字を区別せず照合する
;   (TRY_MATCH_PRINTと同じ構造・境界確認)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
TRY_MATCH_GOTO:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_GOTO_LEN
    JR C,_l4tmgoto_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_GOTO_TEXT
    LD B,STMT_GOTO_LEN
_l4tmgoto_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmgoto_fail
    INC HL
    INC DE
    DJNZ _l4tmgoto_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmgoto_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmgoto_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmgoto_boundary_ok2
    JR _l4tmgoto_fail
_l4tmgoto_boundary_ok:
    POP HL
_l4tmgoto_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_GOTO_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmgoto_fail:
    XOR A
    RET

STMT_GOTO_TEXT: DB "GOTO"
STMT_GOTO_LEN EQU 4


; TRY_MATCH_GOSUB — 固定語形"GOSUB"を大文字小文字を区別せず照合する
;   (TRY_MATCH_PRINTと同じ構造・境界確認)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
TRY_MATCH_GOSUB:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_GOSUB_LEN
    JR C,_l4tmgosub_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_GOSUB_TEXT
    LD B,STMT_GOSUB_LEN
_l4tmgosub_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmgosub_fail
    INC HL
    INC DE
    DJNZ _l4tmgosub_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmgosub_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmgosub_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmgosub_boundary_ok2
    JR _l4tmgosub_fail
_l4tmgosub_boundary_ok:
    POP HL
_l4tmgosub_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_GOSUB_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmgosub_fail:
    XOR A
    RET

STMT_GOSUB_TEXT: DB "GOSUB"
STMT_GOSUB_LEN EQU 5


; TRY_MATCH_RETURN — 固定語形"RETURN"を大文字小文字を区別せず照合する
;   (TRY_MATCH_PRINTと同じ構造・境界確認)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
TRY_MATCH_RETURN:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_RETURN_LEN
    JR C,_l4tmreturn_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_RETURN_TEXT
    LD B,STMT_RETURN_LEN
_l4tmreturn_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmreturn_fail
    INC HL
    INC DE
    DJNZ _l4tmreturn_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmreturn_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmreturn_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmreturn_boundary_ok2
    JR _l4tmreturn_fail
_l4tmreturn_boundary_ok:
    POP HL
_l4tmreturn_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_RETURN_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmreturn_fail:
    XOR A
    RET

STMT_RETURN_TEXT: DB "RETURN"
STMT_RETURN_LEN EQU 6


; TRY_MATCH_FOR — 固定語形"FOR"を大文字小文字を区別せず照合する
;   (TRY_MATCH_PRINTと同じ構造・境界確認)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
TRY_MATCH_FOR:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_FOR_LEN
    JR C,_l4tmfor_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_FOR_TEXT
    LD B,STMT_FOR_LEN
_l4tmfor_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmfor_fail
    INC HL
    INC DE
    DJNZ _l4tmfor_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmfor_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmfor_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmfor_boundary_ok2
    JR _l4tmfor_fail
_l4tmfor_boundary_ok:
    POP HL
_l4tmfor_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_FOR_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmfor_fail:
    XOR A
    RET

STMT_FOR_TEXT: DB "FOR"
STMT_FOR_LEN EQU 3


; TRY_MATCH_NEXT — 固定語形"NEXT"を大文字小文字を区別せず照合する
;   (TRY_MATCH_PRINTと同じ構造・境界確認)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
TRY_MATCH_NEXT:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_NEXT_LEN
    JR C,_l4tmnext_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_NEXT_TEXT
    LD B,STMT_NEXT_LEN
_l4tmnext_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmnext_fail
    INC HL
    INC DE
    DJNZ _l4tmnext_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmnext_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmnext_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmnext_boundary_ok2
    JR _l4tmnext_fail
_l4tmnext_boundary_ok:
    POP HL
_l4tmnext_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_NEXT_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmnext_fail:
    XOR A
    RET

STMT_NEXT_TEXT: DB "NEXT"
STMT_NEXT_LEN EQU 4


; TRY_MATCH_END — 固定語形"END"を大文字小文字を区別せず照合する
;   (TRY_MATCH_PRINTと同じ構造・境界確認)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
TRY_MATCH_END:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_END_LEN
    JR C,_l4tmend_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_END_TEXT
    LD B,STMT_END_LEN
_l4tmend_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmend_fail
    INC HL
    INC DE
    DJNZ _l4tmend_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmend_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmend_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmend_boundary_ok2
    JR _l4tmend_fail
_l4tmend_boundary_ok:
    POP HL
_l4tmend_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_END_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmend_fail:
    XOR A
    RET

STMT_END_TEXT: DB "END"
STMT_END_LEN EQU 3


; TRY_MATCH_STOP — 固定語形"STOP"を大文字小文字を区別せず照合する
;   (TRY_MATCH_PRINTと同じ構造・境界確認)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
TRY_MATCH_STOP:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_STOP_LEN
    JR C,_l4tmstop_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_STOP_TEXT
    LD B,STMT_STOP_LEN
_l4tmstop_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmstop_fail
    INC HL
    INC DE
    DJNZ _l4tmstop_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmstop_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmstop_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmstop_boundary_ok2
    JR _l4tmstop_fail
_l4tmstop_boundary_ok:
    POP HL
_l4tmstop_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_STOP_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmstop_fail:
    XOR A
    RET

STMT_STOP_TEXT: DB "STOP"
STMT_STOP_LEN EQU 4


; TRY_MATCH_RUN — 固定語形"RUN"を大文字小文字を区別せず照合する
;   (TRY_MATCH_PRINTと同じ構造・境界確認)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
TRY_MATCH_RUN:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_RUN_LEN
    JR C,_l4tmrun_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_RUN_TEXT
    LD B,STMT_RUN_LEN
_l4tmrun_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmrun_fail
    INC HL
    INC DE
    DJNZ _l4tmrun_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmrun_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmrun_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmrun_boundary_ok2
    JR _l4tmrun_fail
_l4tmrun_boundary_ok:
    POP HL
_l4tmrun_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_RUN_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmrun_fail:
    XOR A
    RET

STMT_RUN_TEXT: DB "RUN"
STMT_RUN_LEN EQU 3


; TRY_MATCH_TO — 固定語形"TO"を大文字小文字を区別せず照合する
;   (TRY_MATCH_PRINTと同じ構造・境界確認)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
TRY_MATCH_TO:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_TO_LEN
    JR C,_l4tmto_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_TO_TEXT
    LD B,STMT_TO_LEN
_l4tmto_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmto_fail
    INC HL
    INC DE
    DJNZ _l4tmto_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmto_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmto_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmto_boundary_ok2
    JR _l4tmto_fail
_l4tmto_boundary_ok:
    POP HL
_l4tmto_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_TO_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmto_fail:
    XOR A
    RET

STMT_TO_TEXT: DB "TO"
STMT_TO_LEN EQU 2


; TRY_MATCH_STEP — 固定語形"STEP"を大文字小文字を区別せず照合する
;   (TRY_MATCH_PRINTと同じ構造・境界確認)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
TRY_MATCH_STEP:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_STEP_LEN
    JR C,_l4tmstep_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_STEP_TEXT
    LD B,STMT_STEP_LEN
_l4tmstep_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmstep_fail
    INC HL
    INC DE
    DJNZ _l4tmstep_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmstep_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmstep_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmstep_boundary_ok2
    JR _l4tmstep_fail
_l4tmstep_boundary_ok:
    POP HL
_l4tmstep_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_STEP_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmstep_fail:
    XOR A
    RET

STMT_STEP_TEXT: DB "STEP"
STMT_STEP_LEN EQU 4

