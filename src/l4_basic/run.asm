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
; M7段階5c: IF〜THEN〜ELSE・比較・AND/OR/NOT・配列・CONT・^ \ MOD・
;   READ/DATA/RESTORE・REM・1行複数文の残りを実装する。RAM配置は
;   GOSUBスタック終端(0xD930)〜配列テーブル(0xD980以降)の空き番地
;   (既存: mbf_single/mbf_double=0xC0xx台、式の作業域=0xC2C0-0xC405、
;   実行エンジン=0xD000-0xD059、変数表=0xD100-0xD75F、FOR=0xD800-
;   0xD8BF、GOSUB=0xD900-0xD92F、L3/L4作業域・PROGRAM_AREA=0xE800台、
;   スタックSP=0xF000。いずれとも重ならない)。
; =======================================================================
RUN_KW_TEXT             EQU 0D930h ; 2B 汎用キーワード照合(下記)のスクラッチ
RUN_KW_LEN              EQU 0D932h ; 1B
LOGIC_TMP_RIGHT         EQU 0D933h ; 2B AND/OR演算中の右辺int16退避
RUN_CMP_OP              EQU 0D935h ; 1B 比較演算子種別(0=,1<>,2<,3>,4<=,5>=)
RUN_CMP_RAW             EQU 0D936h ; 1B VAL_COMPARE_CUR_RHSの生の結果
RUN_DATA_WANT_KIND      EQU 0D937h ; 1B DATA_READ_ONEの要求型(0数値/1文字列)
RUN_DATA_REC            EQU 0D938h ; 2B DATA走査中のレコード先頭(0=未着手)
RUN_DATA_PTR            EQU 0D93Ah ; 2B DATA走査/読み取りの再開位置
RUN_DATA_END            EQU 0D93Ch ; 2B 同レコードのLINE_END
RUN_DATA_STATE          EQU 0D93Eh ; 1B 0=次を探す必要/1=読み取り位置あり/2=尽きた
RUN_DATA_MAIN_SAVE_PTR  EQU 0D93Fh ; 2B DATA処理中の本線CUR_PTR退避
RUN_DATA_MAIN_SAVE_END  EQU 0D941h ; 2B 同LINE_END
RUN_DATA_NEG            EQU 0D943h ; 1B DATA数値リテラルの'-'
RUN_CONT_REC            EQU 0D944h ; 2B CONT再開レコード(0=無効、第4.11節)
RUN_CONT_PTR            EQU 0D946h ; 2B
RUN_CONT_END            EQU 0D948h ; 2B
RUN_ARITH_L             EQU 0D94Ah ; 2B \・MODの左辺int16
RUN_ARITH_R             EQU 0D94Ch ; 2B \・MODの右辺int16
SDIV_SIGNQ              EQU 0D94Eh ; 1B SDIV16の商の符号
SDIV_SIGNR              EQU 0D94Fh ; 1B SDIV16の剰余の符号
RUN_POW_EXP             EQU 0D950h ; 2B ^の指数(int16、符号付き)
RUN_POW_NEG             EQU 0D952h ; 1B 指数が負か
RUN_POW_COUNT           EQU 0D953h ; 2B 指数の絶対値(乗算回数)
RUN_POW_BASE            EQU 0D955h ; 9B ^の底(型1+データ8)を退避
RUN_VAL_SAVE9           EQU 0D95Eh ; 9B 配列代入の右辺退避(型1+データ8)
RUN_ARRAY_IDX           EQU 0D967h ; 2B 配列の添字(int16)
RUN_ARRAY_FREE_PTR      EQU 0D969h ; 2B ARRAY_FINDが記録する空きスロット
RUN_ARRAY_NAME          EQU 0D96Bh ; 8B 配列名(IDENT_BUFの退避)
RUN_DIM_COUNT           EQU 0D973h ; 1B DIMの要素数(添字上限+1)
RUN_IF_TRUE             EQU 0D974h ; 1B IF条件の真偽

; ---- 配列テーブル(第4.10節・6.5節) ----
; レコード(298B): [NAME 8B][USED 1B][COUNT 1B][DATA(32要素*9B=288B)]
;   要素は変数と同じ「型1+データ8」(VARREC_VALUEと同形式)。
;   宣言なし配列は既定COUNT=11(添字0-10、D9-D11の観測から10が上限と
;   推定、仕様書に無い判断・第8節11)。最大4配列・1配列最大32要素
;   (いずれも仕様書に無い上限)。
RUN_ARRAY_TAB       EQU 0D980h
ARRAY_REC_SIZE      EQU 298
ARRAY_CAP           EQU 4
ARRAYREC_USED       EQU 8
ARRAYREC_COUNT      EQU 9
ARRAYREC_DATA       EQU 10
ARRAY_MAX_ELEMS     EQU 32
; 終端 = D980+4*298(4A8h) = DE28h(既存領域と重ならない)

; ---- M7段階5c-2a: INPUT・文字列関数の作業領域 ----
; 配列テーブル終端(0xDE28)〜画面/L3L4共通域(VAR_ROW、0xE800)の間は空き
; (約2000B)。仕様書に無い判断(RAM配置のみ、値の規則そのものではない)。
RUN_STR_ARG1_LEN    EQU 0DE28h ; 1B MID$/LEFT$/RIGHT$の元文字列を、数値
RUN_STR_ARG1_BUF    EQU 0DE29h ; 31B 引数の評価(入れ子のLEN/VAL/ASC等が
                                ;     RUN_STR_TMP_LEN/BUFを上書きしうる)
                                ;     より前に退避しておく場所
RUN_STR_ACC_LEN     EQU 0DE48h ; 1B STRING_EXPRの'+'連結、左辺の蓄積
RUN_STR_ACC_BUF     EQU 0DE49h ; 31B
RUN_ARG1            EQU 0DE68h ; 2B MID$の第2引数(開始位置)の退避
PNFM_SAVE_PTR        EQU 0DE6Ah ; 2B PARSE_NUM_FROM_MEMのCUR_PTR退避
PNFM_SAVE_END        EQU 0DE6Ch ; 2B 同LINE_END退避
PNFM_NEG             EQU 0DE6Eh ; 1B 同'-'符号
RUN_INPUT_COUNT      EQU 0DE6Fh ; 1B INPUTの変数個数(0-4、仕様書に無い上限)
RUN_INPUT_VARS       EQU 0DE70h ; 4*(kind1B+name8B)=36B
RUN_INPUT_RAW_LEN    EQU 0DE94h ; 1B INPUT_READLINEが読み取った生の行の長さ
RUN_INPUT_RAW_BUF    EQU 0DE95h ; 40B(仕様書に無い上限、keyboard.asmの
                                ; LINE_BUF80Bより短くした簡略化)
; 終端 = DE95+40 = DEBDh(まだ0xE800より十分手前)

; ---- M7段階5c-2b: 配列代入(ARRAY_ASSIGN_STMT)の左辺アドレス退避 ----
RUN_ARRAY_ASSIGN_ADDR EQU 0DEBDh ; 2B 左辺の配列要素アドレス(右辺式の
                                 ; 評価より前に確定させ、ここへ退避する。
                                 ; 右辺式が同じ配列を読む場合(a(1)=a(2)等)
                                 ; ARRAY_READがRUN_ARRAY_IDX/RUN_ARRAY_NAME
                                 ; を上書きするため、右辺評価後までこれらを
                                 ; 当てにできない(不具合、下記ARRAY_ASSIGN_STMT
                                 ; 参照)
; 終端 = DEBD+2 = DEBFh(まだ0xE800より十分手前)

; ---- M7段階5c-2b: LOCATE文の第1引数(桁)の一時退避 ----
RUN_LOCATE_COL        EQU 0DEBFh ; 1B LOCATE文の第1引数(桁)を、第2引数
                                 ; (行)を評価する間退避しておく(第5.2節)。
                                 ; 終端 = DEBF+1 = DEC0h

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
; M7段階5c-2a追記: 識別子が$型(kind=3)のとき、MID$/LEFT$/RIGHT$/STR$
;   (第4.14節、関数名自体に'$'を含む)に一致し直後が'('なら関数呼び出し
;   として扱う(PSR_TRY_FUNCS、下記)。一致しなければ従来どおりその
;   変数の値を読む。
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
    CALL PSR_TRY_FUNCS
    OR A
    RET NZ
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
; STRING_EXPR — 文字列の式を1個読む(PARSE_STRING_RHSの"項"を'+'で
;   繰り返し連結する、第4.14節E10)。出力: RUN_STR_TMP_LEN/BUF、
;   ERROR_FLAG。
; =======================================================================
STRING_EXPR:
    CALL PARSE_STRING_RHS
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
_se_loop:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '+'
    JR NZ,_se_done
    CALL ADV_PTR
    LD A,(RUN_STR_TMP_LEN)
    LD (RUN_STR_ACC_LEN),A
    LD HL,RUN_STR_TMP_BUF
    LD DE,RUN_STR_ACC_BUF
    LD B,A
    CALL STR_COPY_BN
    CALL PARSE_STRING_RHS
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL STR_CONCAT
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JR _se_loop
_se_done:
    XOR A
    LD (ERROR_FLAG),A
    RET

; STR_COPY_BN — HL=コピー元、DE=コピー先、B=個数(0-255)。BCへ拡張して
;   LDIRするだけの小さな共有ラッパ(ROM節約)。
STR_COPY_BN:
    LD C,B
    LD B,0
    LDIR
    RET

; STR_CONCAT — RUN_STR_ACC(左)++RUN_STR_TMP(右、現在値)をRUN_STR_TMPへ
;   書き直す。合計32文字以上はString too long(15、第4.4d節・errors.asm)。
; 注意: STR_COPY_BN(LDIR経由)はBCを0まで使い切るため、右辺長をCに
;   持たせたままでは1回目の複写で潰れる。RUN_TMP16の下位=左辺長・
;   上位=右辺長として退避し、Cレジスタに頼らないようにする。
STR_CONCAT:
    LD A,(RUN_STR_ACC_LEN)
    LD (RUN_TMP16),A
    LD B,A
    LD A,(RUN_STR_TMP_LEN)
    LD (RUN_TMP16+1),A
    LD C,A
    ADD A,B
    CP 32
    JR NC,_sc_toolong
    ; 右辺(RUN_STR_TMP_BUF、Cバイト)を ACC_BUF+acc_len(RUN_TMP16) へ複写
    LD A,(RUN_TMP16)
    LD D,0
    LD E,A
    LD HL,RUN_STR_ACC_BUF
    ADD HL,DE               ; HL = 結合先頭(ACC_BUF+acc_len)
    EX DE,HL                 ; DE = 結合先頭(コピー先)
    LD HL,RUN_STR_TMP_BUF     ; HL = 右辺(コピー元)
    LD B,C
    CALL STR_COPY_BN
    ; ACC_BUF(合計 acc_len+右辺長 バイト)を RUN_STR_TMP_BUF へ複写し直す
    LD A,(RUN_TMP16)
    LD B,A
    LD A,(RUN_TMP16+1)
    ADD A,B
    LD (RUN_STR_TMP_LEN),A
    LD B,A
    LD HL,RUN_STR_ACC_BUF
    LD DE,RUN_STR_TMP_BUF
    CALL STR_COPY_BN
    XOR A
    LD (ERROR_FLAG),A
    RET
_sc_toolong:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,15
    LD (ERROR_KIND),A
    RET

; EXPECT_CHAR — A=期待する1文字。SKIP_SPACESしてから照合し、一致すれば
;   ADV_PTRする(TRY_MATCH系と同じ「空白を挟んでよい」規則)。不一致は
;   Syntax error(2)。
EXPECT_CHAR:
    PUSH BC
    LD B,A
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP B
    JR NZ,_ec_fail
    CALL ADV_PTR
    POP BC
    XOR A
    LD (ERROR_FLAG),A
    RET
_ec_fail:
    POP BC
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET

; CUR_TO_INT16 — CUR_TYPE/CUR_DATAを符号付き16bit整数へ変換しDEへ返す
;   (ASSIGN_STMTの%代入(第4.4b節)と同じ丸め規則の共有)。
;   出力: A=1成功/0範囲外、DE=結果。
CUR_TO_INT16:
    LD A,(CUR_TYPE)
    CP 2
    JR NZ,_cti_have_type
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL MBF_DTOS
    CALL VAL_SET_SINGLE_FROM_RES
_cti_have_type:
    LD A,(CUR_TYPE)
    OR A
    JR NZ,_cti_round
    LD DE,(CUR_DATA)
    LD A,1
    RET
_cti_round:
    CALL VAL_LOAD_CUR_TO_OPA
    JP MBF_ROUND_TO_INT16

; PARSE_INT_ARG — 数値の式を1個読み、CUR_TO_INT16で16bit整数(DE)へ
;   変換する(MID$/LEFT$/RIGHT$の引数、第4.14節)。範囲外はOverflow(6)。
PARSE_INT_ARG:
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL CUR_TO_INT16
    OR A
    JR NZ,_pia_ok
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET
_pia_ok:
    XOR A
    LD (ERROR_FLAG),A
    RET

; =======================================================================
; PSR_TRY_FUNCS — IDENT_BUF(既にLEX_IDENT_CONSUME済み、kind=3=$型)を
;   PSR_FUNC_TABLEの語(接尾辞'$'を含めた完全な語形)と比較する。一致し
;   直後が'('なら該当ハンドラを呼び、A=1(RUN_STR_TMP_LEN/BUFに結果、
;   ERROR_FLAG参照)で戻る。不一致、または'('が続かなければA=0
;   (呼び出し元はそのまま文字列変数として読み直す)。
;   FACTOR_TRY_NUM_FUNCS(interp.asm)と全く同じ表引きの形(ROM節約の
;   ためJUMP_HLトランポリンも共有する)。
; =======================================================================
PSR_TRY_FUNCS:
    LD HL,PSR_FUNC_TABLE
_ptf_loop:
    LD A,(HL)
    OR A
    JR Z,_ptf_none
    LD C,A
    INC HL
    PUSH HL
    LD DE,IDENT_BUF
    LD B,C
_ptf_cmp:
    LD A,(DE)
    CP (HL)
    JR NZ,_ptf_fail
    INC HL
    INC DE
    DJNZ _ptf_cmp
    LD A,7
    SUB C
    LD B,A
    OR A
    JR Z,_ptf_zero_ok
_ptf_zero_check:
    LD A,(DE)
    OR A
    JR NZ,_ptf_fail
    INC DE
    DJNZ _ptf_zero_check
_ptf_zero_ok:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '('
    JR NZ,_ptf_fail
    LD E,(HL)
    INC HL
    LD D,(HL)
    POP HL
    CALL ADV_PTR
    EX DE,HL
    CALL JUMP_HL
    LD A,1
    RET
_ptf_fail:
    POP HL
    LD B,0
    ADD HL,BC
    INC HL
    INC HL
    JR _ptf_loop
_ptf_none:
    XOR A
    RET

PSR_FUNC_TABLE:
    DB 3
    DB "MID"
    DW PSR_DO_MID
    DB 4
    DB "LEFT"
    DW PSR_DO_LEFT
    DB 5
    DB "RIGHT"
    DW PSR_DO_RIGHT
    DB 3
    DB "STR"
    DW PSR_DO_STR
    DB 0

; PSR_DO_MID — MID$(str,start,len)。'('消費済みから始まる。
PSR_DO_MID:
    CALL STRING_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(RUN_STR_TMP_LEN)
    LD (RUN_STR_ARG1_LEN),A
    LD HL,RUN_STR_TMP_BUF
    LD DE,RUN_STR_ARG1_BUF
    LD B,A
    CALL STR_COPY_BN
    LD A,','
    CALL EXPECT_CHAR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL PARSE_INT_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD (RUN_ARG1),DE
    LD A,','
    CALL EXPECT_CHAR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL PARSE_INT_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    PUSH DE
    LD A,')'
    CALL EXPECT_CHAR
    POP DE
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP MID_COMPUTE

; MID_COMPUTE — RUN_STR_ARG1(元文字列)・RUN_ARG1(開始、1始まり)・
;   DE(長さ)からRUN_STR_TMP_LEN/BUFへ結果を作る。開始・長さは下位1
;   バイトだけを使う(仕様書に無い簡略化、8bit範囲=0-255文字を想定)。
;   開始が範囲外(0または元文字列長超え)は空文字列。長さは残り文字数で
;   打ち切る(仕様書に無い判断、一般的なBASICのMID$と同じ振る舞い)。
MID_COMPUTE:
    LD (RUN_TMP16),DE
    LD A,(RUN_ARG1)
    OR A
    JR NZ,_mc_start_nz
    LD A,1
_mc_start_nz:
    LD B,A
    LD A,(RUN_STR_ARG1_LEN)
    LD C,A
    LD A,B
    CP C
    JR Z,_mc_have_start
    JR C,_mc_have_start
    XOR A
    LD (RUN_STR_TMP_LEN),A
    XOR A
    LD (ERROR_FLAG),A
    RET
_mc_have_start:
    LD A,C
    SUB B
    INC A
    LD D,A
    LD A,(RUN_TMP16)
    LD E,A
    LD A,D
    CP E
    JR C,_mc_use_avail
    LD A,E
    JR _mc_have_copylen
_mc_use_avail:
    LD A,D
_mc_have_copylen:
    LD (RUN_STR_TMP_LEN),A
    OR A
    JR NZ,_mc_copy
    XOR A
    LD (ERROR_FLAG),A
    RET
_mc_copy:
    LD C,A
    LD HL,RUN_STR_ARG1_BUF
    LD D,0
    LD A,B
    DEC A
    LD E,A
    ADD HL,DE
    LD DE,RUN_STR_TMP_BUF
    LD B,C
    CALL STR_COPY_BN
    XOR A
    LD (ERROR_FLAG),A
    RET

; PSR_DO_LEFT — LEFT$(str,n)。先頭からmin(n,元の長さ)文字。
PSR_DO_LEFT:
    CALL STRING_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(RUN_STR_TMP_LEN)
    LD (RUN_STR_ARG1_LEN),A
    LD HL,RUN_STR_TMP_BUF
    LD DE,RUN_STR_ARG1_BUF
    LD B,A
    CALL STR_COPY_BN
    LD A,','
    CALL EXPECT_CHAR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL PARSE_INT_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    PUSH DE
    LD A,')'
    CALL EXPECT_CHAR
    POP DE
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,E
    LD B,A
    LD A,(RUN_STR_ARG1_LEN)
    LD C,A
    CP B
    JR NC,_pl_have_n
    LD B,A
_pl_have_n:
    LD A,B
    LD (RUN_STR_TMP_LEN),A
    XOR A
    LD (ERROR_FLAG),A
    LD A,B
    OR A
    RET Z
    LD B,A
    LD HL,RUN_STR_ARG1_BUF
    LD DE,RUN_STR_TMP_BUF
    JP STR_COPY_BN

; PSR_DO_RIGHT — RIGHT$(str,n)。末尾からmin(n,元の長さ)文字。
PSR_DO_RIGHT:
    CALL STRING_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(RUN_STR_TMP_LEN)
    LD (RUN_STR_ARG1_LEN),A
    LD HL,RUN_STR_TMP_BUF
    LD DE,RUN_STR_ARG1_BUF
    LD B,A
    CALL STR_COPY_BN
    LD A,','
    CALL EXPECT_CHAR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL PARSE_INT_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    PUSH DE
    LD A,')'
    CALL EXPECT_CHAR
    POP DE
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,E
    LD B,A
    LD A,(RUN_STR_ARG1_LEN)
    LD C,A
    CP B
    JR NC,_pr_have_n
    LD B,A
_pr_have_n:
    LD A,B
    LD (RUN_STR_TMP_LEN),A
    XOR A
    LD (ERROR_FLAG),A
    LD A,B
    OR A
    RET Z
    LD A,C
    SUB B
    LD HL,RUN_STR_ARG1_BUF
    LD D,0
    LD E,A
    ADD HL,DE
    LD DE,RUN_STR_TMP_BUF
    LD A,(RUN_STR_TMP_LEN)
    LD B,A
    JP STR_COPY_BN

; PSR_DO_STR — STR$(数値式)。'('消費済みから始まる。
PSR_DO_STR:
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,')'
    CALL EXPECT_CHAR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP STR_FROM_CUR

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
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP ASSIGN_NUMERIC_FROM_CUR

; ASSIGN_NUMERIC_FROM_CUR — M7段階5c-2a追記: ASSIGN_STMTの「式を評価
;   し終えた直後」からの再入口。RUN_ASSIGN_KIND/NAMEが指す変数へ
;   CUR_TYPE/CUR_DATAの値を(kindに応じた型変換をしてから)書く部分だけを
;   切り出し、INPUT_STMT(第4.13節、数値項目)から共有する
;   (仕様書に無い判断: 実装上の再利用、代入そのものの規則はASSIGN_STMTと
;   完全に同じにする)。
ASSIGN_NUMERIC_FROM_CUR:
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
    CALL STRING_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP ASSIGN_STRING_FROM_TMP

; ASSIGN_STRING_FROM_TMP — M7段階5c-2a追記: 文字列側の再入口
;   (RUN_STR_TMP_LEN/BUFが用意済みの状態から)。INPUT_STMTの文字列項目が
;   共有する。
ASSIGN_STRING_FROM_TMP:
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
    CALL LOGIC_OR_EXPR
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
    CALL LOGIC_OR_EXPR
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
    CALL LOGIC_OR_EXPR
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

; M7段階5c: CONT(第4.11節)のために、STOPで止まった位置(RUN_CUR_RECORD/
;   CUR_PTR/LINE_END、STOP自身の直後で以降の':'続き・次の行を指す)を
;   RUN_CONT_*へ保存する。
STOP_STMT:
    LD HL,(RUN_CUR_RECORD)
    LD (RUN_CONT_REC),HL
    LD HL,(CUR_PTR)
    LD (RUN_CONT_PTR),HL
    LD HL,(LINE_END)
    LD (RUN_CONT_END),HL
    XOR A
    LD (ERROR_FLAG),A
    LD A,2
    LD (RUN_CTRL),A
    CALL RUN_EMIT_STOP
    RET

; =======================================================================
; M7段階5c-2a: CLS(第5.1節)。直接モードのコマンドとしても(interp.asm
;   DIRECT_LINE経由)、プログラム中の文としても(RUN_EXEC_ONE_STMT経由)
;   同じ本体を使う。引数は取らない。
; =======================================================================
CLS_STMT:
    CALL CLS_SCREEN
    XOR A
    LD (ERROR_FLAG),A
    LD (RUN_CTRL),A
    RET

; =======================================================================
; M7段階5c-2b: LOCATE(第5.2節「第1引数が桁(x)、第2引数が行(y)」)。
;   本体はl3_main/screen.asmのLOCATE_SET_CURSORへ委ねる(範囲外の丸め等は
;   そちら参照)。CLSと同じく直接モード・プログラム中の文の両方から使う。
; =======================================================================
LOCATE_STMT:
    CALL PARSE_INT_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,E
    LD (RUN_LOCATE_COL),A
    LD A,','
    CALL EXPECT_CHAR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL PARSE_INT_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(RUN_LOCATE_COL)
    LD C,A
    LD A,E
    LD B,A
    CALL LOCATE_SET_CURSOR
    XOR A
    LD (ERROR_FLAG),A
    LD (RUN_CTRL),A
    RET

; =======================================================================
; M7段階5c-2b: COLOR(第5.4節「引数の値が属性域の値バイトにそのまま
;   入る」)。本体はl3_main/screen.asmのCOLOR_APPLYへ委ねる。
; =======================================================================
COLOR_STMT:
    CALL PARSE_INT_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,E
    CALL COLOR_APPLY
    XOR A
    LD (ERROR_FLAG),A
    LD (RUN_CTRL),A
    RET

; =======================================================================
; M7段階5c-2a: INPUT(第4.13節)。プロンプトを出し、打った1行を','で
;   区切って変数へ入れる。プロンプトの記号("? ")は仕様書が記録していない
;   ため仕様書に無い判断(禁止事項7、一般的なBASICの慣例を採用)。
;   最大4変数(仕様書に無い上限、配列の最大個数と揃えた)。値が足りない
;   変数は数値なら0、文字列なら空文字のまま(仕様書に無い判断、
;   ?Redo from startはマニュアル自身がエラーメッセージでないと明記する
;   特殊メッセージのため今回の範囲では実装しない)。
; =======================================================================
INPUT_STMT:
    XOR A
    LD (RUN_INPUT_COUNT),A
_input_parse_loop:
    CALL SKIP_SPACES
    CALL LEX_IDENT_CONSUME
    OR A
    JP Z,_input_syntax
    LD B,A
    LD A,(RUN_INPUT_COUNT)
    CP 4
    JP NC,_input_syntax
    LD HL,RUN_INPUT_VARS
    LD D,0
    LD E,A
    ; エントリ9B毎: HL += count*9
    PUSH AF
    LD A,E
    ADD A,A
    ADD A,A
    ADD A,A
    ADD A,E
    LD E,A
    ADD HL,DE
    POP AF
    LD (HL),B
    INC HL
    PUSH HL
    LD HL,IDENT_BUF
    EX DE,HL
    POP HL
    LD B,8
_input_copyname:
    LD A,(DE)
    LD (HL),A
    INC HL
    INC DE
    DJNZ _input_copyname
    LD A,(RUN_INPUT_COUNT)
    INC A
    LD (RUN_INPUT_COUNT),A
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR NZ,_input_parse_done
    CALL ADV_PTR
    JR _input_parse_loop
_input_parse_done:
    LD A,(RUN_INPUT_COUNT)
    OR A
    JP Z,_input_syntax
    ; プロンプトを出す(仕様書に無い判断、"? "を選んだ。ヘッダコメント参照)
    LD A,'?'
    CALL PRINT_CHAR
    LD A,' '
    CALL PRINT_CHAR
    CALL INPUT_READLINE
    ; 生の行(RUN_INPUT_RAW_LEN/BUF)を','で区切り、変数の個数ぶんだけ
    ; 順に代入する。CUR_PTR/LINE_ENDを生の行バッファへ一時的に差し替え、
    ; 既存の字句解析(PARSE_NUM_FROM_MEM相当の手順・PARSE_STRING_RHS等)を
    ; そのまま再利用する(DATA_READ_ONEと同じ手法)。
    LD HL,(CUR_PTR)
    LD (RUN_DATA_MAIN_SAVE_PTR),HL
    LD HL,(LINE_END)
    LD (RUN_DATA_MAIN_SAVE_END),HL
    LD HL,RUN_INPUT_RAW_BUF
    LD (CUR_PTR),HL
    LD A,(RUN_INPUT_RAW_LEN)
    LD D,0
    LD E,A
    ADD HL,DE
    LD (LINE_END),HL
    XOR A
    LD (RUN_TMP_E),A          ; 変数インデックス(0..count-1)、1バイト間借り
_input_field_loop:
    LD A,(RUN_TMP_E)
    LD HL,RUN_INPUT_VARS
    LD B,A
    ADD A,A
    ADD A,A
    ADD A,A
    ADD A,B
    LD D,0
    LD E,A
    ADD HL,DE                 ; HL=このエントリの[kind][name8]
    LD A,(HL)
    LD C,A                     ; C=kind
    INC HL
    LD DE,RUN_ASSIGN_NAME
    PUSH HL
    LD B,8
_input_copy_assign_name:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _input_copy_assign_name
    POP HL
    LD A,C
    LD (RUN_ASSIGN_KIND),A
    CP 3
    JR Z,_input_field_string
    ; 数値項目: 現在位置(','または行末まで)をPARSE_NUM_FROM_MEM相当で
    ; 読む。まずDATA_PARSE_RAW_TOKENと同じ生トークン切り出しを使い、
    ; RUN_STR_TMP_LEN/BUFへ集めてからPARSE_NUM_FROM_MEMへ渡す
    ; (','・行末で区切る点はDATA_PARSE_RAW_TOKENと同じ形を流用する)。
    CALL DATA_PARSE_RAW_TOKEN
    LD HL,RUN_STR_TMP_BUF
    LD A,(RUN_STR_TMP_LEN)
    LD B,A
    CALL PARSE_NUM_FROM_MEM
    CALL ASSIGN_NUMERIC_FROM_CUR
    JR _input_field_after
_input_field_string:
    ; 文字列項目: ','または行末までの生の文字をそのまま代入する
    ; (引用符は要らない、DATA_PARSE_RAW_TOKENと同じ簡略化)。
    CALL DATA_PARSE_RAW_TOKEN
    CALL ASSIGN_STRING_FROM_TMP
_input_field_after:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR NZ,_input_field_done
    CALL ADV_PTR
_input_field_done:
    LD A,(RUN_TMP_E)
    INC A
    LD (RUN_TMP_E),A
    LD B,A
    LD A,(RUN_INPUT_COUNT)
    CP B
    JP NZ,_input_field_loop
    LD HL,(RUN_DATA_MAIN_SAVE_END)
    LD (LINE_END),HL
    LD HL,(RUN_DATA_MAIN_SAVE_PTR)
    LD (CUR_PTR),HL
    CALL NEWLINE
    XOR A
    LD (ERROR_FLAG),A
    LD (RUN_CTRL),A
    RET
_input_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET

; INPUT_READLINE — キーボードを直接ポーリングし(keyboard.asmのKEY_READ、
;   VSYNC割り込み経由ではなく本ルーチンが自分で繰り返し呼ぶ)、RETURNまで
;   の1行をRUN_INPUT_RAW_LEN/BUFへ集めながらエコーする(仕様書に無い判断:
;   INPUTの打鍵はBackspace等の編集を扱わない最小実装、l3-main.mdの
;   LINE_PUTCHAR/LINE_BUFとは別の領域を使い、実行中の"run"行の入力状態
;   〔LINE_BUF/VAR_LINELEN、keyboard.asm〕と衝突しないようにする)。
INPUT_READLINE:
    XOR A
    LD (RUN_INPUT_RAW_LEN),A
_irl_loop:
    CALL KEY_READ
    OR A
    JR Z,_irl_loop
    CP 2
    JR Z,_irl_done
    ; A=1(通常文字)、E=文字コード
    PUSH DE
    LD A,(RUN_INPUT_RAW_LEN)
    CP 40
    JR NC,_irl_skip_store
    LD HL,RUN_INPUT_RAW_BUF
    LD D,0
    LD E,A
    ADD HL,DE
    POP DE
    LD (HL),E
    LD A,(RUN_INPUT_RAW_LEN)
    INC A
    LD (RUN_INPUT_RAW_LEN),A
    LD A,E
    CALL PRINT_CHAR
    JR _irl_loop
_irl_skip_store:
    POP DE
    LD A,E
    CALL PRINT_CHAR
    JR _irl_loop
_irl_done:
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
    JR Z,_rmsk_try_if
    LD A,7
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
; M7段階5c追記: IF/DIM/READ/RESTORE/REM('含む)を、代入へ落ちる前に
;   照合する(第4.7節・4.10節・6.1〜6.2節・6.7節)。
_rmsk_try_if:
    CALL TRY_MATCH_IF
    OR A
    JR Z,_rmsk_try_dim
    LD A,9
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_dim:
    CALL TRY_MATCH_DIM
    OR A
    JR Z,_rmsk_try_read
    LD A,10
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_read:
    CALL TRY_MATCH_READ
    OR A
    JR Z,_rmsk_try_restore
    LD A,11
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_restore:
    CALL TRY_MATCH_RESTORE
    OR A
    JR Z,_rmsk_try_rem
    LD A,12
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_rem:
    CALL TRY_MATCH_REM_ANY
    OR A
    JR Z,_rmsk_try_cls
    LD A,13
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
; M7段階5c-2a追記: CLS(第5.1節)・INPUT(第4.13節)も、代入へ落ちる前に照合する。
_rmsk_try_cls:
    CALL TRY_MATCH_CLS
    OR A
    JR Z,_rmsk_try_input
    LD A,15
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_input:
    CALL TRY_MATCH_INPUT
    OR A
    JR Z,_rmsk_try_locate
    LD A,16
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
; M7段階5c-2b追記: LOCATE(第5.2節)・COLOR(第5.4節)も、代入へ落ちる前に照合する。
_rmsk_try_locate:
    CALL TRY_MATCH_LOCATE
    OR A
    JR Z,_rmsk_try_color
    LD A,17
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_try_color:
    CALL TRY_MATCH_COLOR
    OR A
    JR Z,_rmsk_try_assign
    LD A,18
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
    CP '('
    JR Z,_rmsk_array_assign
    CP '='
    JR NZ,_rmsk_assign_fail
    CALL ADV_PTR
    LD A,8
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_array_assign:
    ; CUR_PTRは'('の直前に残す(ARRAY_ASSIGN_STMTが'('から再解析する)。
    LD A,14
    LD (RUN_STMT_KIND),A
    LD A,1
    RET
_rmsk_assign_fail:
    XOR A
    RET

; RUN_EXEC_ONE_STMT — CUR_PTR位置の文を1つだけ照合・実行する
;   (RUN_MATCH_STMT_KEYWORDの結果で分岐)。呼び出し前にSKIP_SPACESは
;   呼び出し元の責任。誤り時もここではメッセージを出さない(呼び出し元の
;   RUN_EXECが1行1回だけRUN_EMIT_ERRORする、第4.5節)。
;   M7段階5c: 従来RUN_EXEC内に直書きしていたswitchをここへ切り出し、
;   IF文(THEN/ELSEの単文実行、IF_STMT参照)から再利用できるようにした。
;   出力: ERROR_FLAG/ERROR_KIND・RUN_CTRL(呼び出し元が確認する)。
RUN_EXEC_ONE_STMT:
    CALL RUN_MATCH_STMT_KEYWORD
    OR A
    JP Z,_reos_unmatched
    LD A,(RUN_STMT_KIND)
    CP 0
    JR Z,_reos_print
    CP 1
    JR Z,_reos_goto
    CP 2
    JR Z,_reos_gosub
    CP 3
    JR Z,_reos_return
    CP 4
    JR Z,_reos_for
    CP 5
    JR Z,_reos_next
    CP 6
    JR Z,_reos_end
    CP 7
    JR Z,_reos_stop
    CP 9
    JR Z,_reos_if
    CP 10
    JR Z,_reos_dim
    CP 11
    JR Z,_reos_read
    CP 12
    JR Z,_reos_restore
    CP 13
    JR Z,_reos_rem
    CP 14
    JR Z,_reos_arrassign
    CP 15
    JR Z,_reos_cls
    CP 16
    JR Z,_reos_input
    CP 17
    JR Z,_reos_locate
    CP 18
    JR Z,_reos_color
    CALL ASSIGN_STMT
    XOR A
    LD (RUN_CTRL),A
    RET
_reos_print:
    CALL PRINT_STMT
    XOR A
    LD (RUN_CTRL),A
    RET
_reos_goto:
    JP GOTO_STMT
_reos_gosub:
    JP GOSUB_STMT
_reos_return:
    JP RETURN_STMT
_reos_for:
    JP FOR_STMT
_reos_next:
    JP NEXT_STMT
_reos_end:
    JP END_STMT
_reos_stop:
    JP STOP_STMT
_reos_if:
    JP IF_STMT
_reos_dim:
    JP DIM_STMT
_reos_read:
    JP READ_STMT
_reos_restore:
    JP RESTORE_STMT
_reos_rem:
    JP REM_STMT
_reos_arrassign:
    JP ARRAY_ASSIGN_STMT
_reos_cls:
    JP CLS_STMT
_reos_input:
    JP INPUT_STMT
_reos_locate:
    JP LOCATE_STMT
_reos_color:
    JP COLOR_STMT
_reos_unmatched:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET

RUN_EXEC:
_run_loop:
_run_stmt_loop:
    CALL SKIP_SPACES
    CALL AT_END
    JP Z,_run_line_end
    CALL RUN_EXEC_ONE_STMT
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
    JR NZ,_run_trailing_syntax
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
_run_trailing_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
_run_error:
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
    ; M7段階5c: 配列テーブル・DATA読み取り位置・CONT再開位置も
    ; RUNのたびに初期化する(RUN_VARTABと同じ「呼ぶたびに初期化する」
    ; 方針、ヘッダコメント参照)。
    LD HL,RUN_ARRAY_TAB
    LD B,ARRAY_CAP
_rrs_arr_loop:
    PUSH HL
    LD DE,ARRAYREC_USED
    ADD HL,DE
    LD (HL),0
    POP HL
    LD DE,ARRAY_REC_SIZE
    ADD HL,DE
    DJNZ _rrs_arr_loop
    XOR A
    LD (RUN_DATA_STATE),A
    LD HL,0
    LD (RUN_DATA_REC),HL
    LD (RUN_CONT_REC),HL
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

; =======================================================================
; TRY_MATCH_KEYWORD_GENERIC — 汎用の固定語形照合(TRY_MATCH_GOTO等と同じ
;   境界規則)。(RUN_KW_TEXT)=語形の先頭番地・(RUN_KW_LEN)=長さを呼び出し
;   前に設定して使う。段階5c以降の新規キーワードはこれで済ませ、
;   個別展開によるROM肥大を避ける(仕様書に無い判断、実装上の選択)。
;   出力: A=1(一致、CUR_PTRを消費)/0(不一致、CUR_PTR不変)
; =======================================================================
TRY_MATCH_KEYWORD_GENERIC:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    LD HL,RUN_KW_LEN
    CP (HL)
    JR C,_kwg_fail
    LD HL,(CUR_PTR)
    LD DE,(RUN_KW_TEXT)
    LD A,(RUN_KW_LEN)
    LD B,A
_kwg_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_kwg_fail
    INC HL
    INC DE
    DJNZ _kwg_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_kwg_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_kwg_boundary_ok2
    CP 'Z'+1
    JR NC,_kwg_boundary_ok2
    JR _kwg_fail
_kwg_boundary_ok:
    POP HL
_kwg_boundary_ok2:
    LD HL,(CUR_PTR)
    LD A,(RUN_KW_LEN)
    LD E,A
    LD D,0
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_kwg_fail:
    XOR A
    RET

TRY_MATCH_THEN:
    LD HL,STMT_THEN_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_THEN_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_THEN_TEXT: DB "THEN"
STMT_THEN_LEN EQU 4

TRY_MATCH_ELSE:
    LD HL,STMT_ELSE_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_ELSE_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_ELSE_TEXT: DB "ELSE"
STMT_ELSE_LEN EQU 4

TRY_MATCH_AND:
    LD HL,STMT_AND_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_AND_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_AND_TEXT: DB "AND"
STMT_AND_LEN EQU 3

TRY_MATCH_OR:
    LD HL,STMT_OR_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_OR_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_OR_TEXT: DB "OR"
STMT_OR_LEN EQU 2

TRY_MATCH_NOT:
    LD HL,STMT_NOT_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_NOT_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_NOT_TEXT: DB "NOT"
STMT_NOT_LEN EQU 3

TRY_MATCH_MOD:
    LD HL,STMT_MOD_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_MOD_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_MOD_TEXT: DB "MOD"
STMT_MOD_LEN EQU 3

TRY_MATCH_RESTORE:
    LD HL,STMT_RESTORE_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_RESTORE_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_RESTORE_TEXT: DB "RESTORE"
STMT_RESTORE_LEN EQU 7

TRY_MATCH_DIM:
    LD HL,STMT_DIM_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_DIM_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_DIM_TEXT: DB "DIM"
STMT_DIM_LEN EQU 3

TRY_MATCH_READ:
    LD HL,STMT_READ_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_READ_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_READ_TEXT: DB "READ"
STMT_READ_LEN EQU 4

TRY_MATCH_IF:
    LD HL,STMT_IF_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_IF_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_IF_TEXT: DB "IF"
STMT_IF_LEN EQU 2

TRY_MATCH_CONT:
    LD HL,STMT_CONT_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_CONT_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC

; M7段階5c-2a: CLS(第5.1節)・INPUT(第4.13節)。CLSは直接モードの
;   コマンド(interp.asm MATCH_STMT_KEYWORD)としてもプログラム中の文
;   (RUN_MATCH_STMT_KEYWORD)としても使えるため、両方から呼ぶ。
STMT_CLS_TEXT: DB "CLS"
STMT_CLS_LEN EQU 3
TRY_MATCH_CLS:
    LD HL,STMT_CLS_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_CLS_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC

TRY_MATCH_INPUT:
    LD HL,STMT_INPUT_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_INPUT_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_INPUT_TEXT: DB "INPUT"
STMT_INPUT_LEN EQU 5
STMT_CONT_TEXT: DB "CONT"
STMT_CONT_LEN EQU 4

; M7段階5c-2b: LOCATE(第5.2節)・COLOR(第5.4節)。CLS/INPUTと同じく
;   直接モードのコマンドとしても文としても使う。
TRY_MATCH_LOCATE:
    LD HL,STMT_LOCATE_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_LOCATE_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_LOCATE_TEXT: DB "LOCATE"
STMT_LOCATE_LEN EQU 6

TRY_MATCH_COLOR:
    LD HL,STMT_COLOR_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_COLOR_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_COLOR_TEXT: DB "COLOR"
STMT_COLOR_LEN EQU 5

; TRY_MATCH_REM_ANY — "REM"またはシングルクォート"'"(6.7節)。
TRY_MATCH_REM_ANY:
    CALL PEEK_CHAR
    CP 027h
    JR NZ,_tmra_word
    CALL ADV_PTR
    LD A,1
    RET
_tmra_word:
    LD HL,STMT_REM_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_REM_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_REM_TEXT: DB "REM"
STMT_REM_LEN EQU 3

TRY_MATCH_DATA_KW:
    LD HL,STMT_DATA_TEXT
    LD (RUN_KW_TEXT),HL
    LD A,STMT_DATA_LEN
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
STMT_DATA_TEXT: DB "DATA"
STMT_DATA_LEN EQU 4

; =======================================================================
; 数値→int16変換(AND/OR/NOT・\・MOD・配列添字・^の指数で共通に使う)。
;   仕様書に無い判断: 単精度・倍精度からの変換はMBF_ROUND_TO_INT16と
;   同じ「半分は絶対値の大きい側」丸めを流用する(第4.4b節・l4-basic.md
;   第5.3節と同じ規則の使い回し、第8節17参照)。
; =======================================================================
; VAL_TO_INT16_CUR — CUR_TYPE/CUR_DATA -> DE(int16)。CUR_TYPE/DATAを
;   破壊する(倍精度は単精度へ変換してから丸めるため)。CF=1は範囲外。
VAL_TO_INT16_CUR:
    LD A,(CUR_TYPE)
    OR A
    JR NZ,_v2i_not_plain
    LD DE,(CUR_DATA)
    OR A
    RET
_v2i_not_plain:
    CP 2
    JR NZ,_v2i_single
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL MBF_DTOS
    CALL VAL_SET_SINGLE_FROM_RES
_v2i_single:
    CALL VAL_LOAD_CUR_TO_OPA
    CALL MBF_ROUND_TO_INT16
    OR A
    JR Z,_v2i_ovfl
    OR A
    RET
_v2i_ovfl:
    SCF
    RET

; VAL_TO_INT16_RHS — RHS_TYPE/RHS_DATAをCUR_TYPE/DATAへ複写してから
;   VAL_TO_INT16_CURを呼ぶ(CURを破壊する。呼び出し元は必要ならCURを
;   先に退避すること)。出力・破壊はVAL_TO_INT16_CURと同じ。
VAL_TO_INT16_RHS:
    LD HL,RHS_TYPE
    LD DE,CUR_TYPE
    LD BC,9
    LDIR
    JP VAL_TO_INT16_CUR

; =======================================================================
; 符号付き16bit除算(\・MOD、第4.12節)。
; =======================================================================
; UDIV16 — HL=被除数(符号なし) DE=除数(符号なし) -> HL=商 DE=余り。
UDIV16:
    LD B,H
    LD C,L
    LD HL,0
    LD A,16
_ud16_loop:
    SLA C
    RL B
    ADC HL,HL
    OR A
    SBC HL,DE
    JR NC,_ud16_noadd
    ADD HL,DE
    JR _ud16_next
_ud16_noadd:
    SET 0,C
_ud16_next:
    DEC A
    JR NZ,_ud16_loop
    PUSH HL
    LD H,B
    LD L,C
    POP DE
    RET

NEG16_HL:
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
    RET

NEG16_DE:
    XOR A
    SUB E
    LD E,A
    LD A,0
    SBC A,D
    LD D,A
    RET

; SDIV16 — HL=被除数(符号付き) DE=除数(符号付き) -> HL=商(0方向切り捨て)
;   DE=余り(被除数と同じ符号、負の数の商・余りの符号は仕様書に無い判断
;   ・第8節17)。呼び出し元が0除算を事前に弾くこと。
SDIV16:
    XOR A
    LD (SDIV_SIGNQ),A
    LD (SDIV_SIGNR),A
    BIT 7,H
    JR Z,_sdiv_hpos
    CALL NEG16_HL
    LD A,1
    LD (SDIV_SIGNQ),A
    LD (SDIV_SIGNR),A
_sdiv_hpos:
    BIT 7,D
    JR Z,_sdiv_dpos
    CALL NEG16_DE
    LD A,(SDIV_SIGNQ)
    XOR 1
    LD (SDIV_SIGNQ),A
_sdiv_dpos:
    CALL UDIV16
    LD A,(SDIV_SIGNQ)
    OR A
    JR Z,_sdiv_qpos
    CALL NEG16_HL
_sdiv_qpos:
    LD A,(SDIV_SIGNR)
    OR A
    JR Z,_sdiv_rpos
    CALL NEG16_DE
_sdiv_rpos:
    RET

; VAL_INTDIV — CUR = trunc(CUR \ RHS)(第4.12節)。
VAL_INTDIV:
    CALL VAL_TO_INT16_CUR
    JR C,_vid_ovfl
    LD (RUN_ARITH_L),DE
    CALL VAL_TO_INT16_RHS
    JR C,_vid_ovfl
    LD (RUN_ARITH_R),DE
    LD A,D
    OR E
    JR Z,_vid_divzero
    LD HL,(RUN_ARITH_L)
    LD DE,(RUN_ARITH_R)
    CALL SDIV16
    CALL VAL_SET_INT
    XOR A
    LD (ERROR_FLAG),A
    RET
_vid_divzero:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,11
    LD (ERROR_KIND),A
    RET
_vid_ovfl:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET

; VAL_MODOP — CUR = CUR MOD RHS(剰余、第4.12節)。
VAL_MODOP:
    CALL VAL_TO_INT16_CUR
    JR C,_vmo_ovfl
    LD (RUN_ARITH_L),DE
    CALL VAL_TO_INT16_RHS
    JR C,_vmo_ovfl
    LD (RUN_ARITH_R),DE
    LD A,D
    OR E
    JR Z,_vmo_divzero
    LD HL,(RUN_ARITH_L)
    LD DE,(RUN_ARITH_R)
    CALL SDIV16
    EX DE,HL
    CALL VAL_SET_INT
    XOR A
    LD (ERROR_FLAG),A
    RET
_vmo_divzero:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,11
    LD (ERROR_KIND),A
    RET
_vmo_ovfl:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET

; =======================================================================
; べき乗 '^'(第4.12節)。FACTORとTERMの間に挿入する優先順位
;   (仕様書に無い判断、第8節15)。非負整数の指数は繰り返し乗算、負の
;   指数は絶対値で計算した後に逆数(1/x)を取る。
; =======================================================================
POWER_FACTOR:
    CALL FACTOR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
_pow_loop:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '^'
    RET NZ
    CALL ADV_PTR
    CALL VAL_PUSH
    CALL FACTOR
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_pow_err
    CALL VAL_TO_INT16_CUR
    JR C,_pow_ovfl_early
    PUSH DE
    CALL VAL_POP
    POP DE
    LD (RUN_POW_EXP),DE
    CALL POWER_COMPUTE
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JR _pow_loop
_pow_err:
    CALL VAL_POP_DISCARD
    RET
_pow_ovfl_early:
    CALL VAL_POP_DISCARD
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET

; POWER_COMPUTE — CUR_TYPE/DATA(底)とRUN_POW_EXP(指数)から
;   CUR_TYPE/DATA(結果)を計算する。
POWER_COMPUTE:
    LD HL,(RUN_POW_EXP)
    XOR A
    LD (RUN_POW_NEG),A
    BIT 7,H
    JR Z,_powc_have_abs
    CALL NEG16_HL
    LD A,1
    LD (RUN_POW_NEG),A
_powc_have_abs:
    LD (RUN_POW_COUNT),HL
    LD HL,CUR_TYPE
    LD DE,RUN_POW_BASE
    LD BC,9
    LDIR
    LD HL,1
    CALL VAL_SET_INT
    LD HL,(RUN_POW_COUNT)
    LD A,H
    OR L
    JR Z,_powc_done
_powc_loop:
    LD HL,RUN_POW_BASE
    LD DE,RHS_TYPE
    LD BC,9
    LDIR
    CALL VAL_MUL
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,(RUN_POW_COUNT)
    DEC HL
    LD (RUN_POW_COUNT),HL
    LD A,H
    OR L
    JR NZ,_powc_loop
_powc_done:
    LD A,(RUN_POW_NEG)
    OR A
    RET Z
    LD HL,CUR_TYPE
    LD DE,RHS_TYPE
    LD BC,9
    LDIR
    LD HL,1
    CALL VAL_SET_INT
    CALL VAL_DIV
    RET

; =======================================================================
; 比較・論理演算(第4.7〜4.9節)。優先順位(仕様書に無い判断、第8節15):
;   OR(最弱) > AND > NOT > 比較(= <> < > <= >=) > EXPR(+ -) > TERM
;   (* / \ MOD) > POWER_FACTOR(^) > FACTOR。PRINT/ASSIGN/FOR/配列添字/
;   カッコの中は、いずれもLOGIC_OR_EXPR(最上位)から入る。
; =======================================================================
LOGIC_OR_EXPR:
    CALL LOGIC_AND_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
_loe_loop:
    CALL SKIP_SPACES
    CALL TRY_MATCH_OR
    OR A
    RET Z
    CALL VAL_PUSH
    CALL LOGIC_AND_EXPR
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_loe_err
    CALL VAL_TO_INT16_CUR
    JR C,_loe_ovfl
    LD (LOGIC_TMP_RIGHT),DE
    CALL VAL_POP
    CALL VAL_TO_INT16_CUR
    JR C,_loe_ovfl
    LD HL,(LOGIC_TMP_RIGHT)
    LD A,L
    OR E
    LD L,A
    LD A,H
    OR D
    LD H,A
    CALL VAL_SET_INT
    XOR A
    LD (ERROR_FLAG),A
    JR _loe_loop
_loe_err:
    CALL VAL_POP_DISCARD
    RET
_loe_ovfl:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET

LOGIC_AND_EXPR:
    CALL NOT_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
_lae_loop:
    CALL SKIP_SPACES
    CALL TRY_MATCH_AND
    OR A
    RET Z
    CALL VAL_PUSH
    CALL NOT_EXPR
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_lae_err
    CALL VAL_TO_INT16_CUR
    JR C,_lae_ovfl
    LD (LOGIC_TMP_RIGHT),DE
    CALL VAL_POP
    CALL VAL_TO_INT16_CUR
    JR C,_lae_ovfl
    LD HL,(LOGIC_TMP_RIGHT)
    LD A,L
    AND E
    LD L,A
    LD A,H
    AND D
    LD H,A
    CALL VAL_SET_INT
    XOR A
    LD (ERROR_FLAG),A
    JR _lae_loop
_lae_err:
    CALL VAL_POP_DISCARD
    RET
_lae_ovfl:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET

NOT_EXPR:
    CALL SKIP_SPACES
    CALL TRY_MATCH_NOT
    OR A
    JR NZ,_ne_have_not
    JP COMPARE_EXPR
_ne_have_not:
    CALL NOT_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL VAL_TO_INT16_CUR
    JR C,_ne_ovfl
    LD A,D
    CPL
    LD D,A
    LD A,E
    CPL
    LD E,A
    LD H,D
    LD L,E
    CALL VAL_SET_INT
    XOR A
    LD (ERROR_FLAG),A
    RET
_ne_ovfl:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET

; COMPARE_EXPR — EXPR(+ -のみ)を左右に、= <> < > <= >= の1回だけの
;   比較(連鎖はしない、仕様書に無い判断・第8節15)。真=-1・偽=0
;   (第4.8節)。
COMPARE_EXPR:
    CALL EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '='
    JR Z,_ce_eq
    CP '<'
    JR Z,_ce_lt_family
    CP '>'
    JR Z,_ce_gt_family
    RET
_ce_eq:
    CALL ADV_PTR
    XOR A
    LD (RUN_CMP_OP),A
    JR _ce_rhs
_ce_lt_family:
    CALL ADV_PTR
    CALL PEEK_CHAR
    CP '>'
    JR Z,_ce_ne
    CP '='
    JR Z,_ce_le
    LD A,2
    LD (RUN_CMP_OP),A
    JR _ce_rhs
_ce_ne:
    CALL ADV_PTR
    LD A,1
    LD (RUN_CMP_OP),A
    JR _ce_rhs
_ce_le:
    CALL ADV_PTR
    LD A,4
    LD (RUN_CMP_OP),A
    JR _ce_rhs
_ce_gt_family:
    CALL ADV_PTR
    CALL PEEK_CHAR
    CP '='
    JR Z,_ce_ge
    LD A,3
    LD (RUN_CMP_OP),A
    JR _ce_rhs
_ce_ge:
    CALL ADV_PTR
    LD A,5
    LD (RUN_CMP_OP),A
_ce_rhs:
    CALL VAL_PUSH
    CALL EXPR
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_ce_err
    CALL VAL_MOVE_CUR_TO_RHS
    CALL VAL_POP
    CALL VAL_COMPARE_CUR_RHS
    LD (RUN_CMP_RAW),A
    JP CMP_EVAL_RESULT
_ce_err:
    CALL VAL_POP_DISCARD
    RET

CMP_EVAL_RESULT:
    LD A,(RUN_CMP_RAW)
    LD B,A
    LD A,(RUN_CMP_OP)
    OR A
    JR Z,_cer_eq
    CP 1
    JR Z,_cer_ne
    CP 2
    JR Z,_cer_lt
    CP 3
    JR Z,_cer_gt
    CP 4
    JR Z,_cer_le
    JR _cer_ge
_cer_eq:
    LD A,B
    OR A
    JR Z,_cer_true
    JR _cer_false
_cer_ne:
    LD A,B
    OR A
    JR NZ,_cer_true
    JR _cer_false
_cer_lt:
    LD A,B
    CP 0FFh
    JR Z,_cer_true
    JR _cer_false
_cer_gt:
    LD A,B
    CP 1
    JR Z,_cer_true
    JR _cer_false
_cer_le:
    LD A,B
    OR A
    JR Z,_cer_true
    CP 0FFh
    JR Z,_cer_true
    JR _cer_false
_cer_ge:
    LD A,B
    OR A
    JR Z,_cer_true
    CP 1
    JR Z,_cer_true
    JR _cer_false
_cer_true:
    LD HL,0FFFFh
    CALL VAL_SET_INT
    XOR A
    LD (ERROR_FLAG),A
    RET
_cer_false:
    LD HL,0
    CALL VAL_SET_INT
    XOR A
    LD (ERROR_FLAG),A
    RET

; IF_TEST_NONZERO — CUR_TYPE/DATAが0以外ならA=1、0ならA=0(第4.7節
;   「0以外の数値は真」)。CUR/RHSを破壊する。
IF_TEST_NONZERO:
    XOR A
    LD (RHS_TYPE),A
    LD HL,0
    LD (RHS_DATA),HL
    LD (RHS_DATA+2),HL
    CALL VAL_COMPARE_CUR_RHS
    OR A
    JR Z,_itn_zero
    LD A,1
    RET
_itn_zero:
    XOR A
    RET

; =======================================================================
; IF_STMT — 第4.7節・6.4節・6.8節。THENの後は行番号(GOTO相当)か1文。
;   ELSEがあれば偽のとき1文だけ実行する。真のとき、同じ行の':'続きは
;   RUN_EXECの通常ループがそのまま実行する(6.8節rest_runs_when_true、
;   ここではELSE節だけを読み飛ばす)。偽のときは、ELSEが見つかるまで
;   (見つかればその1文を実行して)、無ければ行の残り全てを飛ばす
;   (6.8節rest_skipped_when_false)。
; =======================================================================
IF_STMT:
    CALL SKIP_SPACES
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL IF_TEST_NONZERO
    LD (RUN_IF_TRUE),A
    CALL SKIP_SPACES
    CALL TRY_MATCH_THEN
    OR A
    JP Z,_if_syntax
    CALL SKIP_SPACES
    LD A,(RUN_IF_TRUE)
    OR A
    JR Z,_if_false
_if_true:
    CALL PEEK_CHAR
    CP '0'
    JR C,_if_true_stmt
    CP '9'+1
    JR NC,_if_true_stmt
    CALL PARSE_LINENUM_CUR
    JP C,_if_syntax
    CALL RUN_FIND_LINE
    JR C,_if_undef
    CALL RUN_ENTER_RECORD
    LD A,1
    LD (RUN_CTRL),A
    XOR A
    LD (ERROR_FLAG),A
    RET
_if_true_stmt:
    CALL RUN_EXEC_ONE_STMT
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(RUN_CTRL)
    OR A
    RET NZ
    CALL SKIP_SPACES
    CALL TRY_MATCH_ELSE
    OR A
    JR Z,_if_true_stmt_done
    LD HL,(LINE_END)
    LD (CUR_PTR),HL
_if_true_stmt_done:
    RET
; 偽: THENの対象を実行せず読み飛ばす。ELSEは':'を挟むとは限らず
;   (例: "THEN print 1 ELSE print 2"は空白区切り)、1文字ずつ進めながら
;   TRY_MATCH_ELSEを試す(仕様書に無い判断、単純さ優先で低速だが
;   1行の長さは小さい)。見つからなければ行末まで丸ごと飛ばす
;   (6.8節rest_skipped_when_false)。
_if_false:
_if_false_check:
    CALL AT_END
    JR Z,_if_false_done
    CALL TRY_MATCH_ELSE
    OR A
    JR NZ,_if_false_run_else
    CALL ADV_PTR
    JR _if_false_check
_if_false_run_else:
    CALL SKIP_SPACES
    CALL RUN_EXEC_ONE_STMT
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(RUN_CTRL)
    OR A
    RET NZ
    LD HL,(LINE_END)
    LD (CUR_PTR),HL
_if_false_done:
    XOR A
    LD (ERROR_FLAG),A
    LD (RUN_CTRL),A
    RET
_if_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET
_if_undef:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,8
    LD (ERROR_KIND),A
    RET

; REM_STMT — 第6.7節。CUR_PTRを行末まで進める(':'も含め注釈として
;   無視する、仕様書に無い判断・第8節31)。
REM_STMT:
    LD HL,(LINE_END)
    LD (CUR_PTR),HL
    XOR A
    LD (ERROR_FLAG),A
    LD (RUN_CTRL),A
    RET

; =======================================================================
; 配列(第4.10節・6.5節)
; =======================================================================
ARRAY_FIND:
    XOR A
    LD H,A
    LD L,A
    LD (RUN_ARRAY_FREE_PTR),HL
    LD HL,RUN_ARRAY_TAB
    LD B,ARRAY_CAP
_af_loop:
    PUSH HL
    LD DE,ARRAYREC_USED
    ADD HL,DE
    LD A,(HL)
    POP HL
    OR A
    JR NZ,_af_check_match
    LD DE,(RUN_ARRAY_FREE_PTR)
    LD A,D
    OR E
    JR NZ,_af_next
    LD (RUN_ARRAY_FREE_PTR),HL
    JR _af_next
_af_check_match:
    PUSH HL
    PUSH BC
    LD DE,IDENT_BUF
    LD B,8
_af_cmp:
    LD A,(DE)
    CP (HL)
    JR NZ,_af_cmp_fail
    INC HL
    INC DE
    DJNZ _af_cmp
    POP BC
    POP HL
    LD A,1
    RET
_af_cmp_fail:
    POP BC
    POP HL
_af_next:
    LD DE,ARRAY_REC_SIZE
    ADD HL,DE
    DJNZ _af_loop
    XOR A
    RET

; ARRAY_ALLOC — A=要素数(COUNT)。IDENT_BUFの名前で空きスロットへ
;   初期登録する(USED=1,COUNT=A,DATA全0)。出力: A=1成功(HL=スロット)/
;   0満杯。
ARRAY_ALLOC:
    LD (RUN_DIM_COUNT),A
    LD HL,(RUN_ARRAY_FREE_PTR)
    LD A,H
    OR L
    JR Z,_aa_full
    PUSH HL
    LD DE,IDENT_BUF
    LD B,8
_aa_copyname:
    LD A,(DE)
    LD (HL),A
    INC HL
    INC DE
    DJNZ _aa_copyname
    LD (HL),1
    INC HL
    LD A,(RUN_DIM_COUNT)
    LD (HL),A
    INC HL
    LD BC,ARRAY_MAX_ELEMS*9
_aa_clear:
    LD (HL),0
    INC HL
    DEC BC
    LD A,B
    OR C
    JR NZ,_aa_clear
    POP HL
    LD A,1
    RET
_aa_full:
    XOR A
    RET

; ARRAY_GET_OR_CREATE_DEFAULT — IDENT_BUFの配列を確実に用意する
;   (無ければCOUNT=11で新規作成、第4.10節の推定上限)。
;   出力: A=1成功(HL=スロット)/0満杯。
ARRAY_GET_OR_CREATE_DEFAULT:
    CALL ARRAY_FIND
    OR A
    RET NZ
    LD A,11
    CALL ARRAY_ALLOC
    RET

; ARRAY_ELEM_ADDR — HL=配列レコード先頭(呼び出し前提)。RUN_ARRAY_IDXの
;   添字から要素アドレスを求める。出力: HL'=要素アドレス(CF=0)/
;   CF=1(範囲外、第9節Subscript out of range)。
ARRAY_ELEM_ADDR:
    PUSH HL
    LD DE,ARRAYREC_COUNT
    ADD HL,DE
    LD A,(HL)
    POP HL
    LD B,A
    LD DE,(RUN_ARRAY_IDX)
    LD A,D
    OR A
    JR NZ,_aea_range
    LD A,E
    CP B
    JR NC,_aea_range
    PUSH HL
    LD H,0
    LD L,E
    LD D,H
    LD E,L
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,DE
    LD DE,ARRAYREC_DATA
    ADD HL,DE
    POP DE
    ADD HL,DE
    OR A
    RET
_aea_range:
    SCF
    RET

; ARRAY_READ — FACTORから、識別子(IDENT_BUF)の直後に'('を見た時点で
;   呼ばれる(CUR_PTRは'('の位置)。出力: CUR_TYPE/CUR_DATA(読み出した
;   値)、ERROR_FLAG/KIND。
ARRAY_READ:
    LD HL,IDENT_BUF
    LD DE,RUN_ARRAY_NAME
    LD BC,8
    LDIR
    CALL ADV_PTR
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL VAL_TO_INT16_CUR
    JR C,_ar_ovfl
    LD (RUN_ARRAY_IDX),DE
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ')'
    JR NZ,_ar_syntax
    CALL ADV_PTR
    LD HL,RUN_ARRAY_NAME
    LD DE,IDENT_BUF
    LD BC,8
    LDIR
    CALL ARRAY_GET_OR_CREATE_DEFAULT
    OR A
    JR Z,_ar_oom
    CALL ARRAY_ELEM_ADDR
    JR C,_ar_range
    LD DE,CUR_TYPE
    LD BC,9
    LDIR
    XOR A
    LD (ERROR_FLAG),A
    RET
_ar_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET
_ar_ovfl:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET
_ar_oom:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET
_ar_range:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,9
    LD (ERROR_KIND),A
    RET

; ARRAY_ASSIGN_STMT — RUN_STMT_KIND=14。RUN_ASSIGN_NAME/KINDは
;   RUN_MATCH_STMT_KEYWORDが設定済み、CUR_PTRは'('の位置。
;
;   M7段階5c-2b修正: 従来は'='の右辺式(LOGIC_OR_EXPR)を評価してから
;   左辺の配列要素アドレスを求めていたが、右辺式が同じ配列を読む形
;   (例: `a(1)=a(2)`)だと、右辺のARRAY_READがRUN_ARRAY_IDX/
;   RUN_ARRAY_NAME(左辺の添字・配列名の退避場所と同じグローバル領域)
;   を上書きしてしまい、左辺の添字が右辺の添字に化けて誤った要素へ
;   書き込む不具合があった(tests/programs/p03_bubble_sort.bas の
;   `t=a(j):a(j)=a(j+1):a(j+1)=t` で顕在化。実測: `a(j)=a(j+1)`単体で
;   左辺が変化しなかった)。対策として、右辺式を評価する**前**に左辺の
;   配列要素アドレスを確定させ、RUN_ARRAY_IDX/RUN_ARRAY_NAMEに依存しない
;   RUN_ARRAY_ASSIGN_ADDRへ退避してから右辺を評価し、右辺の値(CUR_TYPE)
;   をその退避アドレスへ直接書き込む(仕様書に無い判断: 実装上のバグ修正、
;   代入そのものの規則はASSIGN_STMTと同じ)。
ARRAY_ASSIGN_STMT:
    LD A,(RUN_ASSIGN_KIND)
    CP 3
    JR Z,_aas_typeerr
    LD HL,RUN_ASSIGN_NAME
    LD DE,RUN_ARRAY_NAME
    LD BC,8
    LDIR
    CALL ADV_PTR
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL VAL_TO_INT16_CUR
    JR C,_aas_ovfl
    LD (RUN_ARRAY_IDX),DE
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ')'
    JR NZ,_aas_syntax
    CALL ADV_PTR
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '='
    JR NZ,_aas_syntax
    CALL ADV_PTR
    LD HL,RUN_ARRAY_NAME
    LD DE,IDENT_BUF
    LD BC,8
    LDIR
    CALL ARRAY_GET_OR_CREATE_DEFAULT
    OR A
    JR Z,_aas_oom
    CALL ARRAY_ELEM_ADDR
    JR C,_aas_range
    LD (RUN_ARRAY_ASSIGN_ADDR),HL
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,CUR_TYPE
    LD DE,(RUN_ARRAY_ASSIGN_ADDR)
    LD BC,9
    LDIR
    XOR A
    LD (ERROR_FLAG),A
    RET
_aas_typeerr:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,13
    LD (ERROR_KIND),A
    RET
_aas_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET
_aas_ovfl:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET
_aas_oom:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET
_aas_range:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,9
    LD (ERROR_KIND),A
    RET

; DIM_STMT — 第4.10節。カンマ区切りで複数配列を宣言できる
;   (仕様書に無い判断、追加的な拡張)。同名の再DIMはDuplicate
;   Definition(10、仕様書に無い判断)。
DIM_STMT:
_dim_one:
    CALL SKIP_SPACES
    CALL LEX_IDENT_CONSUME
    OR A
    JR Z,_dim_syntax
    CP 3
    JR Z,_dim_typeerr
    LD HL,IDENT_BUF
    LD DE,RUN_ARRAY_NAME
    LD BC,8
    LDIR
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '('
    JR NZ,_dim_syntax
    CALL ADV_PTR
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL VAL_TO_INT16_CUR
    JR C,_dim_ovfl
    LD A,D
    OR A
    JR NZ,_dim_ovfl
    LD A,E
    CP ARRAY_MAX_ELEMS
    JR NC,_dim_ovfl
    INC A
    LD (RUN_DIM_COUNT),A
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ')'
    JR NZ,_dim_syntax
    CALL ADV_PTR
    LD HL,RUN_ARRAY_NAME
    LD DE,IDENT_BUF
    LD BC,8
    LDIR
    CALL ARRAY_FIND
    OR A
    JR NZ,_dim_dup
    LD A,(RUN_DIM_COUNT)
    CALL ARRAY_ALLOC
    OR A
    JR Z,_dim_oom
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR NZ,_dim_done
    CALL ADV_PTR
    JR _dim_one
_dim_done:
    XOR A
    LD (ERROR_FLAG),A
    RET
_dim_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET
_dim_typeerr:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,13
    LD (ERROR_KIND),A
    RET
_dim_ovfl:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET
_dim_dup:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,10
    LD (ERROR_KIND),A
    RET
_dim_oom:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET

; =======================================================================
; READ/DATA/RESTORE(第6.1〜6.3節)。DATA_READ_ONEは、実行中のCUR_PTR/
;   LINE_ENDを一時的にDATA走査位置へ差し替えて既存の字句解析
;   (PEEK_CHAR/ADV_PTR/SKIP_SPACES/AT_END/LEX_NUMBER等)をそのまま
;   再利用し、終わったら呼び出し元のCUR_PTR/LINE_ENDへ戻す
;   (RUN_DATA_MAIN_SAVE_*)。RUN_CUR_RECORD(本線の実行位置)とは別に
;   RUN_DATA_REC(DATAの走査位置)を持つ。
; =======================================================================
DATA_ENTER_RECORD:
    LD (RUN_DATA_REC),HL
    INC HL
    INC HL
    LD A,(HL)
    LD C,A
    LD B,0
    INC HL
    LD (CUR_PTR),HL
    ADD HL,BC
    LD (LINE_END),HL
    RET

DATA_ADVANCE_RECORD:
    LD HL,(RUN_DATA_REC)
    LD DE,2
    ADD HL,DE
    LD A,(HL)
    LD C,A
    LD B,0
    INC BC
    INC BC
    INC BC
    LD HL,(RUN_DATA_REC)
    ADD HL,BC
    LD A,(HL)
    LD B,A
    PUSH HL
    INC HL
    LD A,(HL)
    POP HL
    CP 0FFh
    JR NZ,_dar_have
    LD A,B
    CP 0FFh
    JR NZ,_dar_have
    XOR A
    RET
_dar_have:
    CALL DATA_ENTER_RECORD
    LD A,1
    RET

; DATA_SCAN — CUR_PTR/LINE_END/RUN_DATA_RECが指す位置から、文区切りを
;   数えながら次の"DATA"文を探す。見つかれば最初の値の直前まで
;   (空白を読み飛ばして)CUR_PTRを進める。出力: A=1見つかった/0尽きた。
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

; DATA_PARSE_NUMBER_LITERAL — FACTORの数値定数解釈(_l4factor_is_number
;   相当)を、DATA用にCUR_PTR位置へ直接適用する。先頭の'-'も許す
;   (仕様書に無い判断、DATAの負数リテラルは未測定)。
DATA_PARSE_NUMBER_LITERAL:
    CALL PEEK_CHAR
    CP '-'
    JR NZ,_dpnl_noneg
    CALL ADV_PTR
    LD A,1
    LD (RUN_DATA_NEG),A
    JR _dpnl_afterneg
_dpnl_noneg:
    XOR A
    LD (RUN_DATA_NEG),A
_dpnl_afterneg:
    CALL LEX_NUMBER
    LD A,(LIT_HASDOT)
    OR A
    JR NZ,_dpnl_general
    LD A,(LIT_HASEXP)
    OR A
    JR NZ,_dpnl_general
    LD A,(LIT_HASSUFFIX)
    OR A
    JR NZ,_dpnl_general
    CALL LIT_TRY_INT16
    JR NC,_dpnl_general
    CALL VAL_SET_INT
    JR _dpnl_applyneg
_dpnl_general:
    CALL LIT_COPY_TO_FINBUF
    CALL MBF_FIN
    LD A,(MBF_STATUS)
    CP 3
    JR Z,_dpnl_double
    CP 1
    JR Z,_dpnl_ovfl
    CALL VAL_SET_SINGLE_FROM_RES
    JR _dpnl_applyneg
_dpnl_double:
    CALL MBF_DFIN
    LD A,(MBF_STATUS)
    OR A
    JR NZ,_dpnl_ovfl
    CALL VAL_SET_DOUBLE_FROM_DRES
    JR _dpnl_applyneg
_dpnl_ovfl:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET
_dpnl_applyneg:
    LD A,(RUN_DATA_NEG)
    OR A
    JR Z,_dpnl_done
    CALL VAL_NEG
_dpnl_done:
    XOR A
    LD (ERROR_FLAG),A
    RET

; DATA_PARSE_RAW_TOKEN — ','/':'/行末までの生の文字をRUN_STR_TMP_LEN/
;   BUFへ読む(31文字超は切り詰め、引用符の特別扱いはしない・第8節29)。
DATA_PARSE_RAW_TOKEN:
    XOR A
    LD (RUN_STR_TMP_LEN),A
_dprt_loop:
    CALL AT_END
    JR Z,_dprt_done
    CALL PEEK_CHAR
    CP ','
    JR Z,_dprt_done
    CP ':'
    JR Z,_dprt_done
    LD B,A
    LD A,(RUN_STR_TMP_LEN)
    CP 31
    JR NC,_dprt_skip
    LD HL,RUN_STR_TMP_BUF
    LD D,0
    LD E,A
    ADD HL,DE
    LD (HL),B
    LD A,(RUN_STR_TMP_LEN)
    INC A
    LD (RUN_STR_TMP_LEN),A
_dprt_skip:
    CALL ADV_PTR
    JR _dprt_loop
_dprt_done:
    XOR A
    LD (ERROR_FLAG),A
    RET

; DATA_READ_ONE — A(in)=0数値/1文字列。出力: 数値ならCUR_TYPE/DATA、
;   文字列ならRUN_STR_TMP_LEN/BUF。DATA切れはOut of DATA(4、第6.3節)。
DATA_READ_ONE:
    LD (RUN_DATA_WANT_KIND),A
    LD HL,(CUR_PTR)
    LD (RUN_DATA_MAIN_SAVE_PTR),HL
    LD HL,(LINE_END)
    LD (RUN_DATA_MAIN_SAVE_END),HL
    LD A,(RUN_DATA_STATE)
    CP 2
    JP Z,_dro_exhausted
    CP 1
    JR Z,_dro_have_pos
    LD HL,(RUN_DATA_REC)
    LD A,H
    OR L
    JR NZ,_dro_resume_scan
    LD HL,PROGRAM_AREA
    LD A,(HL)
    LD B,A
    PUSH HL
    INC HL
    LD A,(HL)
    POP HL
    CP 0FFh
    JR NZ,_dro_enter_first
    LD A,B
    CP 0FFh
    JR NZ,_dro_enter_first
    JR _dro_exhausted
_dro_enter_first:
    CALL DATA_ENTER_RECORD
    JR _dro_do_scan
_dro_resume_scan:
    LD HL,(RUN_DATA_PTR)
    LD (CUR_PTR),HL
    LD HL,(RUN_DATA_END)
    LD (LINE_END),HL
_dro_do_scan:
    CALL DATA_SCAN
    OR A
    JR Z,_dro_exhausted
    JR _dro_have_value_pos
_dro_have_pos:
    LD HL,(RUN_DATA_PTR)
    LD (CUR_PTR),HL
    LD HL,(RUN_DATA_END)
    LD (LINE_END),HL
_dro_have_value_pos:
    CALL SKIP_SPACES
    LD A,(RUN_DATA_WANT_KIND)
    OR A
    JR NZ,_dro_parse_string
    CALL DATA_PARSE_NUMBER_LITERAL
    JR _dro_parsed
_dro_parse_string:
    CALL DATA_PARSE_RAW_TOKEN
_dro_parsed:
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_dro_fail_restore
    CALL SKIP_SPACES
    CALL AT_END
    JR Z,_dro_clause_ends
    CALL PEEK_CHAR
    CP ','
    JR Z,_dro_more
    JR _dro_clause_ends
_dro_more:
    CALL ADV_PTR
    LD A,1
    LD (RUN_DATA_STATE),A
    JR _dro_save
_dro_clause_ends:
    XOR A
    LD (RUN_DATA_STATE),A
_dro_save:
    LD HL,(CUR_PTR)
    LD (RUN_DATA_PTR),HL
    LD HL,(LINE_END)
    LD (RUN_DATA_END),HL
    LD HL,(RUN_DATA_MAIN_SAVE_PTR)
    LD (CUR_PTR),HL
    LD HL,(RUN_DATA_MAIN_SAVE_END)
    LD (LINE_END),HL
    XOR A
    LD (ERROR_FLAG),A
    RET
_dro_exhausted:
    LD A,2
    LD (RUN_DATA_STATE),A
    LD HL,(RUN_DATA_MAIN_SAVE_PTR)
    LD (CUR_PTR),HL
    LD HL,(RUN_DATA_MAIN_SAVE_END)
    LD (LINE_END),HL
    LD A,1
    LD (ERROR_FLAG),A
    LD A,4
    LD (ERROR_KIND),A
    RET
_dro_fail_restore:
    LD HL,(RUN_DATA_MAIN_SAVE_PTR)
    LD (CUR_PTR),HL
    LD HL,(RUN_DATA_MAIN_SAVE_END)
    LD (LINE_END),HL
    RET

; READ_STMT — 第6.1節。カンマ区切りで複数変数へ同時READできる
;   (%・#の丸めは適用せずそのまま代入する、仕様書に無い判断)。
READ_STMT:
_read_one:
    CALL SKIP_SPACES
    CALL LEX_IDENT_CONSUME
    OR A
    JR Z,_read_syntax
    CP 3
    JR Z,_read_string_target
    LD HL,IDENT_BUF
    LD DE,RUN_ASSIGN_NAME
    LD BC,8
    LDIR
    XOR A
    CALL DATA_READ_ONE
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,RUN_ASSIGN_NAME
    LD DE,IDENT_BUF
    LD BC,8
    LDIR
    CALL VAR_WRITE_NUMERIC
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JR _read_next
_read_string_target:
    LD HL,IDENT_BUF
    LD DE,RUN_ASSIGN_NAME
    LD BC,8
    LDIR
    LD A,1
    CALL DATA_READ_ONE
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,RUN_ASSIGN_NAME
    LD DE,IDENT_BUF
    LD BC,8
    LDIR
    CALL VAR_WRITE_STRING
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
_read_next:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR NZ,_read_done
    CALL ADV_PTR
    JR _read_one
_read_done:
    XOR A
    LD (ERROR_FLAG),A
    RET
_read_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET

; AEL_ROM_LAYOUT_PAD — 2026-09-20追記(ATN/EXP/LOG、第4.16b節)。
;   ATN/EXP/LOGの追加でN88.ROM全体の総バイト数が伸び、QUASI88の機種判定
;   予約番地0x79D7(build_main_rom.py ROM_VERSION_RESERVED_ADDR、同ファイル
;   のコメント参照)に実命令の1バイトが偶然かかるようになった
;   (docs/PLAN.mdの方針どおりレイアウトをここで分ける——同予約番地の
;   コメントが指示する「この番地の手前でレイアウトを分けること」の
;   実施)。RESTORE_STMTの直前(予約番地のすぐ手前)に置くことで、他の
;   モジュール(L1 IPL・ext_bank等)の故障注入・selftestフラグ
;   (run_all_selftests.shが使うもの、いずれもRESTORE_STMTより前方の
;   モジュールにしか触れない)によるバイト数の増減があっても、この
;   埋め草との相対位置がほぼ保たれる(interp.asm側の離れた位置に置くと、
;   予約番地に自然に来る0バイトが孤立点で、フラグの組み合わせごとに
;   再調整が要ることが実測で分かった)。340バイトという量自体は、
;   --inject-ext-bank-window-fault(この埋め草より手前のモジュールの
;   内容を差し替えるため、他のフラグより相対位置のずれが大きい
;   ——実測で最大約290バイト)を含む全フラグの組み合わせで
;   AEL_ROM_LAYOUT_PADのバイト範囲が予約番地0x79D7を覆うように実測で
;   決めた値(build_main_rom.pyの --enable-l4-selftest・
;   --enable-ext-bank-selftest・--inject-ext-bank-bcde-fault・
;   --inject-address-fault・--inject-l4-sign-space-fault・
;   --inject-l3-space-fault・--enable-vsync-regcheck・
;   --inject-vsync-no-save-fault・--inject-key-repeat-fault・
;   --inject-editkey-home-clr-fault・--inject-l4-missing-operand-fault・
;   --inject-cursor-fault・--inject-key-table-fault・--inject-shift-fault・
;   --inject-default-attr-fault・--inject-scroll-range-fault・
;   --inject-l4-zone-width-fault・--inject-l4-token-fault・
;   --inject-ext-bank-no-org-fault・--inject-ext-bank-mbf-addr-fault・
;   --inject-ext-bank-window-fault を1つずつ単独で当てて実測、
;   --inject-ext-bank-window-faultは意図どおりcheck_ext_bank_relay_
;   below_windowで落ちる〔ROM_VERSION検査より後段〕ことも確認済み)。
;   機能的な意味は無く、純粋にレイアウト調整用。
AEL_ROM_LAYOUT_PAD:
    DS 340

; RESTORE_STMT — 第6.2節。行番号指定(第8節28)は本段階では対応せず、
;   引数があれば構文の誤り扱い(仕様書に無い判断、安全側に倒す)。
RESTORE_STMT:
    CALL SKIP_SPACES
    CALL AT_END
    JR Z,_restore_ok
    CALL PEEK_CHAR
    CP ':'
    JR Z,_restore_ok
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET
_restore_ok:
    XOR A
    LD (RUN_DATA_STATE),A
    LD HL,0
    LD (RUN_DATA_REC),HL
    XOR A
    LD (ERROR_FLAG),A
    RET

; =======================================================================
; CONT(第4.11節) — 直接モードのコマンド(interp.asm DIRECT_LINEから
;   STMT_KIND=4で呼ばれる、RUNと同じ位置づけ)。STOP_STMTが保存した
;   RUN_CONT_*から再開し、RUN_EXECの通常の継続処理(_run_after_stmt、
;   ERROR_FLAG=0・RUN_CTRL=0で開始)へそのまま合流する。
; =======================================================================
CONT_STMT:
    LD HL,(RUN_CONT_REC)
    LD A,H
    OR L
    JR NZ,_cont_have
    LD A,1
    LD (ERROR_FLAG),A
    LD A,17
    LD (ERROR_KIND),A
    RET
_cont_have:
    LD (RUN_CUR_RECORD),HL
    LD HL,(RUN_CONT_PTR)
    LD (CUR_PTR),HL
    LD HL,(RUN_CONT_END)
    LD (LINE_END),HL
    LD HL,0
    LD (RUN_CONT_REC),HL
    XOR A
    LD (RUN_CTRL),A
    LD (ERROR_FLAG),A
    JP _run_after_stmt

