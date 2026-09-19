; interp.asm — M7段階3b: 直接モードの実行とPRINT文。
; M7段階4a-2で単精度浮動小数点(src/l4_basic/mbf_single.asm)を組み込み、
; 整数と単精度の混在式・単精度のPRINT・範囲外/0除算の誤りを追加した。
;
; 根拠は docs/spec/l4-basic.md（第1〜7.1節）と docs/spec/l3-main.md
; （画面出力・行入力、参照のみ）だけである。measurements/ も公式ROMも
; 参照していない。
;
;   直接モードの行の並び(相対+1に出力、+2にOk)         … l4-basic.md 第1節
;   整数の前後の空白(符号1桁+末尾空白1)                 … l4-basic.md 第2節
;   文字列の前後に空白なし                              … l4-basic.md 第3節
;   区切り記号(;は素通し、,は14列ゾーン、行末での改行抑止) … l4-basic.md 第4節
;   浮動小数点の定数の型・昇格・書式・誤り               … l4-basic.md 第5節
;   構文の誤り(出力の行1行、Okの位置は変わらない)         … l4-basic.md 第6節
;   誤りの形とメッセージの対応(Missing operand/Syntax error/Overflow/
;   Division by zero)                                    … l4-basic.md 第7.1.1節
;                                                            (errors.asm経由)
;   PRINTの語形とトークン                                … tokens.tsv
;                                                            (print_dispatch.asm経由)
;
; 段階4a-2で明示的に選んだ実装方式(仕様書に無い判断。報告の
; 「仕様書に無いこと」参照。数値そのものの書式・昇格規則は仕様書
; 第5節の根拠つきだが、以下はそれを実現するための実装の内部構造の
; 選択であり、規則そのものではない):
;   - 値は「型(0=整数16bit/1=単精度MBF4バイト)+データ」の組
;     (CUR_TYPE/CUR_DATA)としてRAMに置き、EXPR/TERM/FACTORはこれを
;     介して値を受け渡す(旧HLレジスタの代わり)。二項演算では右辺を
;     RHS_TYPE/RHS_DATAへ写し、左辺をソフトウェアスタック(VAL_STACK)
;     へ退避してから計算する——元の「PUSH HL(左辺退避)→右辺を計算→
;     POP HL→合成」というZ80ハードウェアスタックを使ったパターンを、
;     型付きの5バイト組を退避する自前のスタックへそのまま置き換えた
;     形。VAL_PUSHは退避のみでCUR_TYPE/CUR_DATAを書き換えない
;     (Z80のPUSH HLがHLを破壊しないのと同じ性質)。
;   - 整数の加算・減算(EXPR)は、両辺が整数のときだけ16bit演算(ADC/SBC)
;     を試み、符号付きオーバーフロー(P/Vフラグ)が起きたら単精度へ
;     昇格して計算し直す(第5.2節)。乗算(TERM '*')・除算(TERM '/')は
;     昇格判定の実装を単純にするため、整数どうしでも常に単精度
;     (MBF_MUL/MBF_DIV)で計算する——第5.2節「7/2=3.5」は除算が常に
;     実数という規則そのものだが、乗算まで常に単精度にするのは規則
;     ではなく実装上の単純化である。整数どうしの乗算が実際に
;     32767以下に収まる場合(例: `2*(3+4)`)でも、単精度で計算した
;     結果をPRINTすると整数と同じ書式になる(MBF_FOUTは整数値を
;     整数と同じ桁で出す、第5.3節)ため、出力される文字列は既存の
;     整数専用経路と変わらない。この等価性はtools/l4_basic_selftest.sh
;     の既存の整数専用検査(case_expr等)がそのまま通ることで確認した。
;   - 数値定数の字句解析(LEX_NUMBER)は、小数点・E/D指数・!/#接尾辞の
;     どれも無い「純粋な数字列」だけを16bit整数として直接解釈しようと
;     試みる(LIT_TRY_INT16、-32768の単項マイナス経由の表現に必要な
;     0..32768の範囲を許す、値そのものは符号なしのまま)。それ以外
;     (小数点・指数・接尾辞がある、または純粋数字列でも32768を超える)
;     は全てMBF_FINへ渡し、単精度に変換する。MBF_FINがMBF_STATUS=3
;     (倍精度定数、mbf_single.asmヘッダの仕様書に無い判断どおり
;     段階4bまで未実装)を返した場合はSyntax errorとして扱う——
;     **これも仕様書に無い判断**であり、8桁以上・`#`・`D`/`d`指数の
;     定数を打った場合の実際の画面表示は本版では確認していない
;     (docs/spec/l4-basic.md 第5.1節は型の決まり方だけを扱い、
;     未実装時の挙動には触れていない)。
;   - 範囲外(単精度の表現範囲を超えるMBFオーバーフロー、MBF_STATUS=1)・
;     0除算(MBF_STATUS=2)は、l4-basic.md第5.6節の構造的事実
;     (出力が2行・Okが相対+3)だけに従う。文言は第7.1節のマニュアル
;     一覧(Overflow=6、Division by zero=11)を採る(第7.1節の開発者
;     判断を踏襲)。1行目に何を出すかは測定されていない
;     (禁止事項7、第10節5)ため、本実装は「空行にする」という
;     **仕様書に無い判断**を採った(ERROR_IS_RUNTIME=1のときBASIC_RUN_LINE
;     がメッセージの前にNEWLINEを1回追加するだけ)。
;
; 段階3b時点からの既存の仕様書に無い既定(変更なし、報告の
; 「仕様書に無いこと」参照):
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
;     出力する」設計（式を評価し終えてからPRINT_VALUE/文字列出力を呼ぶ）
;     のため、式の評価中に誤りが起きた項目自体は何も出力されない。
;     複数項目のうち前の項目が既に出力済みで後の項目で誤りが起きる場合の
;     扱いは実測が無いため、そのまま出力済み分を残す（取り消さない）。
;     段階4a-2の範囲外・0除算も同じ設計に従う(値が確定する直前に
;     誤りが確定するため、その項目自体は出力されない)。
;   - PRINT以外の語（未実装の命令）は、この段階では字句解析を試みず、
;     直ちに構文の誤りとして扱う（設計項目5）。
;
; RAM変数は lexer.asm 側にまとめて宣言してある(ERROR_FLAG, LINE_END,
; CUR_PTR, SUPPRESS_NL 等)。ここでは追加で以下を使う。
PUD_VALUE   EQU 0E89Ah   ; 2バイト
PUD_PLACE   EQU 0E89Ch   ; 2バイト
PUD_DIGIT   EQU 0E89Eh
PUD_STARTED EQU 0E89Fh
ERROR_KIND  EQU 0E8A0h   ; 誤りの形の番号(2/6/11/22、既定2)。errors.asm生成の
                         ; ERR_MSG_番号 を選ぶために BASIC_RUN_LINE が読む。
                         ; 判定方針は 第7.1.1節 対応、この段階の選択は
                         ; SELECT_ERROR_MSG の直前コメント参照。
ERROR_IS_RUNTIME EQU 0E8A1h  ; 1=範囲外/0除算(第5.6節、出力2行)、
                         ; 0=構文の誤り(出力1行)。BASIC_RUN_LINEが読む。

; ---- M7段階4a-2: 値の型付き表現(整数/単精度)。M7段階4b-3で倍精度
;   (CUR_TYPE=2)を追加。ヘッダコメント参照 ----
CUR_TYPE   EQU 0E8A2h        ; 0=整数16bit 1=単精度MBF 2=倍精度MBF
CUR_DATA   EQU 0E8A3h        ; 8バイト(整数は下位2バイト、単精度は下位4
                              ; バイトだけ意味を持つ。段階4b-3で4→8へ拡張)
RHS_TYPE   EQU 0E8ABh
RHS_DATA   EQU 0E8ACh        ; 8バイト(同上)

; 段階4b-3: VAL_STACK(32slot*9byte=288B)・LIT_*はここ(E8xx、program.asmの
; STMT_KIND=E980以降と隣接)に収まらなくなった(CUR_DATA/RHS_DATAを4→8Bへ
; 広げた上でVAL_STACKも5→9B/slotへ広げると計160B超過)ため、mbf_double.asm
; のワークエリア(0xC200-0xC2AB、172B)の直後・実行エンジン(run.asm、
; 0xD000-0xD059)より手前の空き番地(0xC2C0以降)へ再配置した。
; 仕様書に無い判断(RAM配置のみ、値の規則そのものではない)。
INTERP_EXT_RAM_BASE EQU 0C2C0h
VAL_STACK       EQU INTERP_EXT_RAM_BASE          ; 32slot*9byte(型1+データ8) = 288バイト
VAL_STACK_DEPTH EQU 32
VAL_SP          EQU INTERP_EXT_RAM_BASE+0120h    ; 1バイト(次に積む位置、0..32) = C3E0

; ---- 数値リテラルの生バイト列(MBF_FIN/MBF_DFINへ渡す前の字句、LEX_NUMBER) ----
LIT_BUF       EQU INTERP_EXT_RAM_BASE+0121h      ; 24バイト(FIN_BUFと同じ上限) = C3E1
LIT_LEN       EQU INTERP_EXT_RAM_BASE+0139h      ; C3F9
LIT_HASDOT    EQU INTERP_EXT_RAM_BASE+013Ah      ; C3FA
LIT_HASEXP    EQU INTERP_EXT_RAM_BASE+013Bh      ; C3FB
LIT_HASSUFFIX EQU INTERP_EXT_RAM_BASE+013Ch      ; C3FC

; ---- 段階4b-3: 整数どうしの乗算の範囲内判定(VAL_MUL_INT16)の作業領域 ----
MULI_SIGN  EQU INTERP_EXT_RAM_BASE+013Dh   ; C3FD 1バイト(結果の符号 0/1)
MULI_A     EQU INTERP_EXT_RAM_BASE+013Eh   ; C3FE 2バイト(|CUR|)
MULI_B     EQU INTERP_EXT_RAM_BASE+0140h   ; C400 2バイト(|RHS|)
MULI_COUNT EQU INTERP_EXT_RAM_BASE+0142h   ; C402 1バイト(シフト加算ループの残り回数)

; ゾーン幅(l4-basic.md 第4節zone_14)。故障注入(検査「ゾーンの幅を変えた
; 変種」)がこの1行だけを書き換える対象。
ZONE_WIDTH EQU 14

; ---------------------------------------------------------------------
; BASIC_RUN_DIRECT — 直接モードの行としての実行本体（旧BASIC_RUN_LINE。
;   M7段階5aで program.asm の BASIC_HANDLE_LINE が新しい入口になり、
;   行番号つきの行（プログラムモード、program.asm PROGRAM_STORE_LINE）
;   と直接モードの行（本ルーチン、PRINT/NEW/LISTを含む）を振り分ける
;   ようになった。keyboard.asm の LINE_FINISH は BASIC_HANDLE_LINE を
;   呼ぶ（program.asm 参照）。
;
;   LINE_BUF/VAR_LINELENを読み、直接モードの行として実行する。構文の
;   誤りがあれば、この中でメッセージを1行出して改行する。範囲外・
;   0除算(ERROR_IS_RUNTIME=1)のときはメッセージの前に空行を1つ追加し、
;   出力が2行になるようにする（l4-basic.md 第5.6節、文言・空行の中身
;   自体は仕様書に無い判断——ヘッダコメント参照）。「Ok」自体はここでは
;   出さない（呼び出し元LINE_FINISHの役目のまま）。
; ---------------------------------------------------------------------
BASIC_RUN_DIRECT:
    XOR A
    LD (ERROR_FLAG),A
    LD (ERROR_IS_RUNTIME),A
    LD A,2
    LD (ERROR_KIND),A    ; 既定はSyntax error(2)。誤りの検出箇所が
                          ; 該当すれば22(Missing operand)/6(Overflow)/
                          ; 11(Division by zero)に上書きする(第7.1.1節)。
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
    LD A,(ERROR_IS_RUNTIME)
    OR A
    JR Z,_l4brl_msg
    CALL NEWLINE          ; 範囲外・0除算の1行目(仕様書に無い判断、空行)
_l4brl_msg:
    CALL SELECT_ERROR_MSG
    CALL PRINT_STR
    CALL NEWLINE
    RET

; ---------------------------------------------------------------------
; SELECT_ERROR_MSG — ERROR_KIND(2/6/11/22)から、errors.asm生成の
;   ERR_MSG_番号 (l4-basic.md 第7.1節のマニュアル文言そのもの)を選ぶ。
;   出力: HL=メッセージ文字列アドレス。未知の値はERR_MSG_2にフォール
;   バックする(第7.1.1節の対応表に無い形は当面Syntax errorのまま、
;   設計項目「仕様書に無い形」参照)。
; ---------------------------------------------------------------------
; M7段階5b追記: 誤りの種類が増えた(Type mismatch・Undefined line number・
; NEXT without FOR・RETURN without GOSUB・FOR without NEXT・Out of
; memory・String too long、run.asm参照)ため、CP連鎖ではなく表引きに
; 変えた。表に無い番号はERR_MSG_2(Syntax error)へフォールバックする
; (第7.1.1節「対応表に無い形は当面Syntax error」を踏襲)。
SELECT_ERROR_MSG:
    LD A,(ERROR_KIND)
    LD B,A
    LD HL,ERRKIND_TABLE
_l4sem_loop:
    LD A,(HL)
    INC HL
    OR A
    JR Z,_l4sem_default
    CP B
    JR Z,_l4sem_match
    INC HL
    INC HL
    JR _l4sem_loop
_l4sem_match:
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
    RET
_l4sem_default:
    LD HL,ERR_MSG_2
    RET

ERRKIND_TABLE:
    DB 5
    DW ERR_MSG_5
    DB 6
    DW ERR_MSG_6
    DB 22
    DW ERR_MSG_22
    DB 11
    DW ERR_MSG_11
    DB 13
    DW ERR_MSG_13
    DB 8
    DW ERR_MSG_8
    DB 1
    DW ERR_MSG_1
    DB 3
    DW ERR_MSG_3
    DB 26
    DW ERR_MSG_26
    DB 7
    DW ERR_MSG_7
    DB 15
    DW ERR_MSG_15
    DB 9
    DW ERR_MSG_9
    DB 10
    DW ERR_MSG_10
    DB 4
    DW ERR_MSG_4
    DB 17
    DW ERR_MSG_17
    DB 0

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
    LD A,(STMT_KIND)
    CP 1
    JR Z,_l4dl_call_list
    CP 2
    JR Z,_l4dl_call_new
    CP 3
    JR Z,_l4dl_call_run
    CP 4
    JR Z,_l4dl_call_cont
    CP 5
    JR Z,_l4dl_call_cls
    CP 6
    JR Z,_l4dl_call_locate
    CP 7
    JR Z,_l4dl_call_color
    CALL PRINT_STMT
    JR _l4dl_after_stmt
_l4dl_call_list:
    CALL LIST_STMT
    JR _l4dl_after_stmt
_l4dl_call_new:
    CALL NEW_STMT
    JR _l4dl_after_stmt
_l4dl_call_run:
    CALL RUN_STMT
    JR _l4dl_after_stmt
_l4dl_call_cont:
    CALL CONT_STMT
    JR _l4dl_after_stmt
_l4dl_call_cls:
    CALL CLS_STMT
    JR _l4dl_after_stmt
_l4dl_call_locate:
    CALL LOCATE_STMT
    JR _l4dl_after_stmt
_l4dl_call_color:
    CALL COLOR_STMT
_l4dl_after_stmt:
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
;   M7段階5a追記: LIST・NEW（program.asm、l4-program.md 第0節「new・list
;   はいずれも行番号を伴わない直接モードのコマンドとして扱われる」）も
;   ここで認識する。STMT_KIND(program.asm)に一致した文の種類を残す
;   (0=PRINT 1=LIST 2=NEW)。DIRECT_LINEはこれを見て呼び分ける。
;   出力: A=1(認識してCUR_PTRを消費した)/0(未認識、CUR_PTR不変)
; ---------------------------------------------------------------------
MATCH_STMT_KEYWORD:
    XOR A
    LD (STMT_KIND),A
    CALL PEEK_CHAR
    CP '?'
    JR NZ,_l4msk_try_print
    CALL ADV_PTR
    LD A,1
    RET
_l4msk_try_print:
    CALL TRY_MATCH_PRINT
    OR A
    RET NZ
    CALL TRY_MATCH_LIST
    OR A
    JR Z,_l4msk_try_new
    LD A,1
    LD (STMT_KIND),A
    LD A,1
    RET
_l4msk_try_new:
    CALL TRY_MATCH_NEW
    OR A
    JR Z,_l4msk_try_run
    LD A,2
    LD (STMT_KIND),A
    LD A,1
    RET
_l4msk_try_run:
    ; M7段階5b追記: RUN(run.asmのTRY_MATCH_RUN、l4-program.md第4.1節
    ; 「new・listと同じく行番号を伴わない直接モードのコマンド」)。
    CALL TRY_MATCH_RUN
    OR A
    JR Z,_l4msk_try_cont
    LD A,3
    LD (STMT_KIND),A
    LD A,1
    RET
_l4msk_try_cont:
    ; M7段階5c追記: CONT(run.asmのTRY_MATCH_CONT、l4-program.md第4.11節。
    ; RUN・LIST・NEWと同じく行番号を伴わない直接モードのコマンド)。
    CALL TRY_MATCH_CONT
    OR A
    JR Z,_l4msk_try_cls
    LD A,4
    LD (STMT_KIND),A
    LD A,1
    RET
_l4msk_try_cls:
    ; M7段階5c-2a追記: CLS(run.asmのTRY_MATCH_CLS、第5.1節)。直接モードの
    ; コマンドとしても文としても使える(CLS_STMTが本体、run.asm)。
    CALL TRY_MATCH_CLS
    OR A
    JR Z,_l4msk_try_locate
    LD A,5
    LD (STMT_KIND),A
    LD A,1
    RET
_l4msk_try_locate:
    ; M7段階5c-2b追記: LOCATE(第5.2節)・COLOR(第5.4節)も、CLSと同じく
    ; 直接モードのコマンドとしても文としても使える。
    CALL TRY_MATCH_LOCATE
    OR A
    JR Z,_l4msk_try_color
    LD A,6
    LD (STMT_KIND),A
    LD A,1
    RET
_l4msk_try_color:
    CALL TRY_MATCH_COLOR
    OR A
    RET Z
    LD A,7
    LD (STMT_KIND),A
    LD A,1
    RET

STMT_LIST_TEXT: DB "LIST"
STMT_LIST_LEN EQU 4
STMT_NEW_TEXT: DB "NEW"
STMT_NEW_LEN EQU 3

; ---------------------------------------------------------------------
; TRY_MATCH_LIST / TRY_MATCH_NEW — TRY_MATCH_PRINTと全く同じ構造
;   （固定語形を大文字小文字を区別せず照合し、続く文字が英字でないこと
;   まで確認する）を"LIST"・"NEW"に対して行う。出力: A=1(一致、CUR_PTR
;   を消費)/0(不一致、CUR_PTR不変)。
; ---------------------------------------------------------------------
TRY_MATCH_LIST:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_LIST_LEN
    JR C,_l4tml_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_LIST_TEXT
    LD B,STMT_LIST_LEN
_l4tml_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tml_fail
    INC HL
    INC DE
    DJNZ _l4tml_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tml_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tml_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tml_boundary_ok2
    JR _l4tml_fail
_l4tml_boundary_ok:
    POP HL
_l4tml_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_LIST_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tml_fail:
    XOR A
    RET

TRY_MATCH_NEW:
    LD HL,(LINE_END)
    LD DE,(CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP STMT_NEW_LEN
    JR C,_l4tmn_fail
    LD HL,(CUR_PTR)
    LD DE,STMT_NEW_TEXT
    LD B,STMT_NEW_LEN
_l4tmn_cmp:
    LD A,(HL)
    CALL FOLD_UPPER
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,_l4tmn_fail
    INC HL
    INC DE
    DJNZ _l4tmn_cmp
    LD DE,(LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    JR Z,_l4tmn_boundary_ok
    POP HL
    LD A,(HL)
    CALL FOLD_UPPER
    CP 'A'
    JR C,_l4tmn_boundary_ok2
    CP 'Z'+1
    JR NC,_l4tmn_boundary_ok2
    JR _l4tmn_fail
_l4tmn_boundary_ok:
    POP HL
_l4tmn_boundary_ok2:
    LD HL,(CUR_PTR)
    LD DE,STMT_NEW_LEN
    ADD HL,DE
    LD (CUR_PTR),HL
    LD A,1
    RET
_l4tmn_fail:
    XOR A
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
;   (l4-basic.md 第2〜5節の書式)。
; ---------------------------------------------------------------------
PRINT_STMT:
    XOR A
    LD (SUPPRESS_NL),A
_l4ps_loop:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JP Z,_l4ps_stmt_end
    CP ':'
    JP Z,_l4ps_stmt_end
    CP '"'
    JR Z,_l4ps_str_item
    ; M7段階5b追記: 文字列変数(run.asm、接尾辞'$')は数値式ではなく
    ; その文字列をそのまま出す。M7段階4b-3で倍精度('#'、kind=4)を
    ; 組み込んだため、Type mismatchにしていたのを取りやめ、他の数値
    ; (kind=0/1/2)と同じくEXPR(FACTORのVAR_READ_NUMERIC経由)へ流す。
    ; M7段階5c-2a追記: 文字列側はSTRING_EXPR(run.asm、'+'連結・
    ; MID$/LEFT$/RIGHT$/STR$の関数呼び出しに対応、第4.14節)へ統一した
    ; (以前は文字列変数を直接VAR_READ_STRING、リテラルを文字ごと
    ; PRINT_CHARする別経路だったが、連結・関数呼び出しに対応できなかった
    ; ため統合した)。
    CALL LEX_IDENT_PEEK
    CP 3
    JR Z,_l4ps_str_item
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL PRINT_VALUE
    JR _l4ps_after_item
_l4ps_str_item:
    CALL STRING_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL PRINT_STRING_VAL
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
; PEEK_CHAR / PEEK_CHAR2 / ADV_PTR / AT_END / SKIP_SPACES — 行バッファの
;   走査。
; ---------------------------------------------------------------------
; PEEK_CHAR/ADV_PTR は HL を破壊しない(呼び出し規約)。数値定数の字句解析
; (LEX_NUMBER)や式評価のループがこれらを多用するため、呼び出し元のHLを
; 保存しない実装は過去に不具合を出している(M7段階3b、当初HLを破壊する版で
; "PRINT1"が62768になる不具合を確認、PUSH/POPでHLを退避する形に修正した)。
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

; PEEK_CHAR2 — CUR_PTR+1位置の文字を覗く(CUR_PTRは進めない)。
;   数値定数が'.'で始まる場合(F2/S1等、l4-basic.md第5.3節)に、その直後が
;   数字かどうかをFACTORが確かめるために使う。
PEEK_CHAR2:
    PUSH HL
    LD HL,(CUR_PTR)
    INC HL
    LD DE,(LINE_END)
    OR A
    SBC HL,DE
    JR Z,_l4peek2_end
    LD HL,(CUR_PTR)
    INC HL
    LD A,(HL)
    POP HL
    RET
_l4peek2_end:
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
; EXPR / TERM / FACTOR — 整数・単精度混在の式(定数・単項-・+ - * /・
;   括弧)。結果は CUR_TYPE/CUR_DATA に残す(ヘッダコメント参照)。
;   エラー時はERROR_FLAG=1(CUR_TYPE/CUR_DATAの値は不定)。
; ---------------------------------------------------------------------
EXPR:
    CALL TERM
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
_l4expr_loop:
    CALL VAL_PUSH
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '+'
    JR Z,_l4expr_plus
    CP '-'
    JR Z,_l4expr_minus
    CALL VAL_POP_DISCARD
    RET
_l4expr_plus:
    CALL ADV_PTR
    CALL TERM
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_l4expr_err_pop
    CALL VAL_MOVE_CUR_TO_RHS
    CALL VAL_POP
    CALL VAL_ADD
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP _l4expr_loop
_l4expr_minus:
    CALL ADV_PTR
    CALL TERM
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_l4expr_err_pop
    CALL VAL_MOVE_CUR_TO_RHS
    CALL VAL_POP
    CALL VAL_SUB
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP _l4expr_loop
_l4expr_err_pop:
    CALL VAL_POP_DISCARD
    RET

; M7段階5c: べき乗'^'をFACTORとTERMの間の優先順位に挿入した
;   (POWER_FACTOR、run.asm。第4.12節D14の根拠のみ、優先順位そのものは
;   仕様書に無い判断・第8節15)。TERMの各被演算子はPOWER_FACTOR経由に
;   した(以前はFACTOR直呼び)。'\'(整数除算、0x5C)・MOD(run.asm
;   TRY_MATCH_MOD)も*/と同じ優先順位に追加した(仕様書に無い判断、
;   優先順位の細部は第8節15参照)。
TERM:
    CALL POWER_FACTOR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
_l4term_loop:
    CALL VAL_PUSH
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '*'
    JR Z,_l4term_mul
    CP '/'
    JR Z,_l4term_div
    CP 05Ch
    JR Z,_l4term_intdiv
    CALL TRY_MATCH_MOD
    OR A
    JR NZ,_l4term_mod
    CALL VAL_POP_DISCARD
    RET
_l4term_mul:
    CALL ADV_PTR
    CALL POWER_FACTOR
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_l4term_err_pop
    CALL VAL_MOVE_CUR_TO_RHS
    CALL VAL_POP
    CALL VAL_MUL
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP _l4term_loop
_l4term_div:
    CALL ADV_PTR
    CALL POWER_FACTOR
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_l4term_err_pop
    CALL VAL_MOVE_CUR_TO_RHS
    CALL VAL_POP
    CALL VAL_DIV
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP _l4term_loop
_l4term_intdiv:
    CALL ADV_PTR
    CALL POWER_FACTOR
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_l4term_err_pop
    CALL VAL_MOVE_CUR_TO_RHS
    CALL VAL_POP
    CALL VAL_INTDIV
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP _l4term_loop
_l4term_mod:
    ; TRY_MATCH_MODは一致時にCUR_PTRを既に消費済み(ADV_PTR不要)。
    CALL POWER_FACTOR
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_l4term_err_pop
    CALL VAL_MOVE_CUR_TO_RHS
    CALL VAL_POP
    CALL VAL_MODOP
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP _l4term_loop
_l4term_err_pop:
    CALL VAL_POP_DISCARD
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
    CALL VAL_NEG
    RET
_l4factor_try_paren:
    CP '('
    JR NZ,_l4factor_try_num
    CALL ADV_PTR
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ')'
    JR NZ,_l4factor_paren_err
    CALL ADV_PTR
    RET
_l4factor_paren_err:
    LD A,1
    LD (ERROR_FLAG),A
    RET
_l4factor_try_num:
    ; 数値定数の先頭判定: 数字、または'.'の直後が数字(F2/S1等、第5.3節)。
    CALL PEEK_CHAR
    CP '0'
    JR C,_l4factor_check_dot
    CP '9'+1
    JR C,_l4factor_is_number
_l4factor_check_dot:
    CALL PEEK_CHAR
    CP '.'
    JR NZ,_l4factor_try_ident
    CALL PEEK_CHAR2
    CP '0'
    JR C,_l4factor_try_ident
    CP '9'+1
    JR NC,_l4factor_try_ident
_l4factor_is_number:
    CALL LEX_NUMBER
    LD A,(LIT_HASDOT)
    OR A
    JR NZ,_l4factor_num_general
    LD A,(LIT_HASEXP)
    OR A
    JR NZ,_l4factor_num_general
    LD A,(LIT_HASSUFFIX)
    OR A
    JR NZ,_l4factor_num_general
    ; 純粋な数字列 -> まず16bit整数として解釈を試みる(LIT_TRY_INT16)。
    ; 収まらなければ(第5.2節の昇格対象)一般形と同じくMBF_FINへ回す。
    CALL LIT_TRY_INT16
    JR NC,_l4factor_num_general
    CALL VAL_SET_INT
    RET
_l4factor_num_general:
    CALL LIT_COPY_TO_FINBUF
    CALL MBF_FIN
    LD A,(MBF_STATUS)
    CP 3
    JR Z,_l4factor_num_double
    CP 1
    JR Z,_l4factor_num_ovfl
    CALL VAL_SET_SINGLE_FROM_RES
    RET
_l4factor_num_double:
    ; 倍精度定数(8桁以上・#・D/d指数、docs/spec/l4-basic.md 第5.1節)。
    ; M7段階4b-3: mbf_double.asm MBF_DFIN(推定DREP10A、第5.1.2節)へ渡す。
    ; MBF_FINは既にMBF_STATUS=3(倍精度と判定)を返しFIN_BUF/FIN_LENへ
    ; 生の数字列を残した状態のまま(mbf_double.asmヘッダコメント参照、
    ; MBF_DFIN自身が字句をFIN_BUFから読み直す)。
    CALL MBF_DFIN
    LD A,(MBF_STATUS)
    OR A
    JR NZ,_l4factor_num_dovfl
    CALL VAL_SET_DOUBLE_FROM_DRES
    RET
_l4factor_num_dovfl:
    ; 倍精度の表現範囲を超えるオーバーフロー(単精度と同じ第5.6節の扱い)。
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_IS_RUNTIME),A
    RET
_l4factor_num_ovfl:
    ; MBF自体のオーバーフロー(単精度の表現範囲を超える、第5.6節)。
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_IS_RUNTIME),A
    RET
; M7段階5b追記: 数値定数の形でなければ、変数名(run.asmのIDENT_BUF/
; VAR_READ_NUMERIC)として解釈を試みる。$接尾辞(文字列)は数値の文脈では
; Type mismatch(13、run.asmヘッダの仕様書に無い判断)。M7段階4b-3で
; #(倍精度、kind=4)はVAR_READ_NUMERIC(CUR_TYPE=2として読む)を通す
; ようにした。識別子ですらなければ(kind=0)従来どおり_l4factor_badへ落ちる。
; M7段階5c追記: 識別子の直後(空白を挟んでもよい、ASSIGN側の'='判定と
;   同じ規則)に'('があれば配列の読み出し(ARRAY_READ、run.asm、
;   第4.10節・6.5節)として扱う。
; M7段階5c-2a追記: 識別子が無印(kind=1)で、かつ`LEN`/`VAL`/`ASC`
;   (第4.14節、いずれも文字列を1個とり数値を返す)に一致し直後が'('なら
;   数値関数呼び出しとして扱う(FACTOR_TRY_NUM_FUNCS、下記)。一致しなければ
;   (関数名でない、または'('が続かない)従来どおり変数/配列として読む。
_l4factor_try_ident:
    CALL LEX_IDENT_CONSUME
    OR A
    JR Z,_l4factor_bad
    CP 3
    JR Z,_l4factor_ident_typeerr
    CP 1
    JR NZ,_l4factor_plain_ident
    CALL FACTOR_TRY_NUM_FUNCS
    OR A
    RET NZ
_l4factor_plain_ident:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '('
    JR Z,_l4factor_array_read
    CALL VAR_READ_NUMERIC
    RET
_l4factor_array_read:
    JP ARRAY_READ
_l4factor_ident_typeerr:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,13
    LD (ERROR_KIND),A
    RET
_l4factor_bad:
    LD A,1
    LD (ERROR_FLAG),A
    ; 被演算子を探した位置が行末、または続く文の区切り':'なら
    ; Missing operand(22、第7.1.1節)。それ以外(未知の語・記号)は
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

; =======================================================================
; M7段階5c-2a: LEN/VAL/ASC(数値を返す文字列関数、第4.14節)。
; =======================================================================
; JUMP_HL — HLの指す番地へ跳ぶ(間接CALL、CALL JUMP_HLの戻り先を
;   ハンドラのRETがそのまま使うトランポリン)。
JUMP_HL:
    JP (HL)

; FACTOR_TRY_NUM_FUNCS — IDENT_BUF(既にLEX_IDENT_CONSUME済み、kind=1)を
;   FTNF_TABLEの語と比較する。一致し直後が'('なら該当ハンドラを呼んで
;   A=1(CUR_TYPE/CUR_DATAに結果、ERROR_FLAG参照)で戻る。不一致、または
;   '('が続かなければA=0(CUR_PTRは識別子を消費した位置のまま、呼び出し元
;   はそのまま変数/配列として読み直す)。
FACTOR_TRY_NUM_FUNCS:
    LD HL,FTNF_TABLE
_ftnf_loop:
    LD A,(HL)
    OR A
    JR Z,_ftnf_none
    LD C,A
    INC HL
    PUSH HL
    LD DE,IDENT_BUF
    LD B,C
_ftnf_cmp:
    LD A,(DE)
    CP (HL)
    JR NZ,_ftnf_fail
    INC HL
    INC DE
    DJNZ _ftnf_cmp
    LD A,7
    SUB C
    LD B,A
    OR A
    JR Z,_ftnf_zero_ok
_ftnf_zero_check:
    LD A,(DE)
    OR A
    JR NZ,_ftnf_fail
    INC DE
    DJNZ _ftnf_zero_check
_ftnf_zero_ok:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '('
    JR NZ,_ftnf_fail
    LD E,(HL)
    INC HL
    LD D,(HL)
    POP HL
    CALL ADV_PTR
    EX DE,HL
    CALL JUMP_HL
    LD A,1
    RET
_ftnf_fail:
    POP HL
    LD B,0
    ADD HL,BC
    INC HL
    INC HL
    JR _ftnf_loop
_ftnf_none:
    XOR A
    RET

FTNF_TABLE:
    DB 3
    DB "LEN"
    DW FTNF_DO_LEN
    DB 3
    DB "VAL"
    DW FTNF_DO_VAL
    DB 3
    DB "ASC"
    DW FTNF_DO_ASC
    ; M7段階5c-2b: CINT・INT・FIX(第4.15節)・ABS・SGN(第4.16節)。
    DB 4
    DB "CINT"
    DW FTNF_DO_CINT
    DB 3
    DB "INT"
    DW FTNF_DO_INT
    DB 3
    DB "FIX"
    DW FTNF_DO_FIX
    DB 3
    DB "ABS"
    DW FTNF_DO_ABS
    DB 3
    DB "SGN"
    DW FTNF_DO_SGN
    ; 2026-09-20追記(l4-c7): CDBL(引数を型を問わず倍精度へ厳密に揃える)。
    ; tokens.asmには既にCDBLのトークン項目(0x93)があったが、この関数
    ; 名テーブル(FACTOR_TRY_NUM_FUNCS、IDENT_BUFの文字列と直接比較する
    ; 経路)には未登録で、l4-s7a/l4-s7b以来「print cdbl(<式>)」を
    ; 測定の直接プローブに使ってきたにもかかわらず自作ROM側では未実装
    ; のままだった(l4-c7自作側照合で発覚。公式ROMは1000000!のような
    ; 単純な値でも常にOverflow/0を返す既存のCDBL欠落経路とは無関係に
    ; 正しく倍精度化していたことをl4-c7の公式側期待値が示している)。
    ; 実装はrun.asm ASSIGN_STMTの#変数代入が既に使っている
    ; VAL_PROMOTE_CUR_TO_DOUBLE(整数はMBF_ITOD、単精度はMBF_STOD、
    ; 倍精度はそのまま——いずれも丸め不要の厳密変換)をそのまま呼ぶ。
    DB 4
    DB "CDBL"
    DW FTNF_DO_CDBL
    ; 2026-09-20追記: SQR(第4.16b節)。単精度へ強制してから拡張ROM
    ; バンク0(src/ext_bank/bank0.asm EXT_BANK0_SQR_ENTRY、オフセット
    ; 0x80固定)を中継(EXT_BANK_CALL、docs/spec/ext-rom-bank.md)経由で
    ; 呼ぶ。SIN/COS/TAN/ATN/EXP/LOGは未実装(第4.16a/b節参照、今回の
    ; 段階の対象外——PLAN.md「行き止まりを消さない」規律どおり、
    ; ここでは着手した範囲だけをコミットする)。
    DB 3
    DB "SQR"
    DW FTNF_DO_SQR
    ; 2026-09-20追記: SIN・COS・TAN(第4.16a節、`l4-s6b`〜`l4-s6g`で確定した
    ; 範囲縮約単精度化+away丸めの手順)。SQRと同じくVAL_LOAD_CUR_TO_OPAで
    ; 単精度へ強制してから拡張ROMバンク0(bank0.asm EXT_BANK0_SIN_ENTRY/
    ; COS_ENTRY/TAN_ENTRY、オフセット0x0200/0x0210/0x0220固定)を
    ; EXT_BANK_CALL経由で呼ぶ。ATN/EXP/LOGは未実装(第4.16b節、今回の
    ; 段階の対象外)。
    DB 3
    DB "SIN"
    DW FTNF_DO_SIN
    DB 3
    DB "COS"
    DW FTNF_DO_COS
    DB 3
    DB "TAN"
    DW FTNF_DO_TAN
    DB 0

; FTNF_STR_ARG — '('消費済みの位置から文字列式を1個読み、')'を確認する
;   (LEN/VAL/ASC共通の引数形)。出力: RUN_STR_TMP_LEN/BUF、ERROR_FLAG。
FTNF_STR_ARG:
    CALL STRING_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,')'
    JP EXPECT_CHAR

FTNF_DO_LEN:
    CALL FTNF_STR_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(RUN_STR_TMP_LEN)
    LD L,A
    LD H,0
    JP VAL_SET_INT

FTNF_DO_VAL:
    CALL FTNF_STR_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,RUN_STR_TMP_BUF
    LD A,(RUN_STR_TMP_LEN)
    LD B,A
    JP PARSE_NUM_FROM_MEM

FTNF_DO_ASC:
    CALL FTNF_STR_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(RUN_STR_TMP_LEN)
    OR A
    JR NZ,_ftnf_asc_ok
    ; 空文字列(仕様書に無い判断: 一般的なBASICの慣例どおりIllegal
    ; function callにする、第7.1節のマニュアル一覧に既にある番号)
    LD A,1
    LD (ERROR_FLAG),A
    LD A,5
    LD (ERROR_KIND),A
    RET
_ftnf_asc_ok:
    LD A,(RUN_STR_TMP_BUF)
    LD L,A
    LD H,0
    JP VAL_SET_INT

; ---------------------------------------------------------------------
; FTNF_NUM_ARG — '('消費済みの位置から数値式を1個読み(LOGIC_OR_EXPR、
;   run.asm)、')'を確認する(CINT等の数値引数、FTNF_STR_ARGの数値版)。
;   出力: CUR_TYPE/CUR_DATA、ERROR_FLAG。
; ---------------------------------------------------------------------
FTNF_NUM_ARG:
    CALL LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,')'
    JP EXPECT_CHAR

; ---------------------------------------------------------------------
; FTNF_DO_CINT — 第4.15節E13・E14。既存のCUR_TO_INT16(run.asm、
;   ASSIGN_STMTの%代入・MID$等の引数と同じ「半分は絶対値の大きい側」の
;   丸め、第4.4b節)をそのまま使う。範囲外はOverflow(6、第7.1節)。
; ---------------------------------------------------------------------
FTNF_DO_CINT:
    CALL FTNF_NUM_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL CUR_TO_INT16
    OR A
    JR NZ,_cint_ok
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    RET
_cint_ok:
    EX DE,HL
    JP VAL_SET_INT

; ---------------------------------------------------------------------
; FTNF_DO_FIX — 第4.15節E12(0方向への切り捨て)。整数はそのまま
;   (整数はFIX/INTいずれも自分自身)。単精度/倍精度は
;   VAL_LOAD_CUR_TO_OPA(倍精度は単精度へ丸めてから、STR$・ASSIGN%と
;   同じ「仕様書に無い判断」の簡略化、interp.asmヘッダ参照)で単精度化
;   してからTRUNC_TO_SINGLE(mbf_single.asm)へ渡す。
; ---------------------------------------------------------------------
FTNF_DO_FIX:
    CALL FTNF_NUM_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(CUR_TYPE)
    OR A
    RET Z
    CALL VAL_LOAD_CUR_TO_OPA
    CALL TRUNC_TO_SINGLE
    JP VAL_SET_SINGLE_FROM_RES

; ---------------------------------------------------------------------
; FTNF_DO_INT — 第4.15節E11(床関数)。FIXと同じTRUNC_TO_SINGLEを使い、
;   負かつ切り捨てたビットに1があった(TRUNC_HADFRAC)場合だけ
;   floor=trunc-1.0にする(絶対値方向で1大きくする、sign-magnitudeの
;   まま-1.0を引けば「より負」になり符号は保たれる)。
; ---------------------------------------------------------------------
FTNF_DO_INT:
    CALL FTNF_NUM_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,(CUR_TYPE)
    OR A
    RET Z
    CALL VAL_LOAD_CUR_TO_OPA
    CALL TRUNC_TO_SINGLE
    LD A,(TRUNC_HADFRAC)
    OR A
    JR Z,_int_settle
    LD A,(TRUNC_SIGN)
    OR A
    JR Z,_int_settle
    CALL FIN_COPY_RES_TO_OPA
    CALL FIN_SET_OPB_ONE
    CALL MBF_SUB
_int_settle:
    JP VAL_SET_SINGLE_FROM_RES

; ---------------------------------------------------------------------
; VAL_CUR_SIGN — CUR_TYPE/CUR_DATAが負(かつ非ゼロ)ならA=1、それ以外
;   (0または正)はA=0。ABS/SGN共通(第4.16節)。整数はCUR_DATA+1(上位
;   バイト)のbit7、単精度/倍精度はMBF形式の符号ビット(第3.7節の
;   バイト並び、単精度=CUR_DATA+2 bit7・倍精度=CUR_DATA+6 bit7)。
;   破壊: AF。
; ---------------------------------------------------------------------
VAL_CUR_SIGN:
    LD A,(CUR_TYPE)
    CP 2
    JR Z,_vcs_double
    OR A
    JR NZ,_vcs_single
    LD A,(CUR_DATA+1)
    JR _vcs_checkbit
_vcs_single:
    LD A,(CUR_DATA+2)
    JR _vcs_checkbit
_vcs_double:
    LD A,(CUR_DATA+6)
_vcs_checkbit:
    AND 080h
    RET Z
    LD A,1
    RET

; ---------------------------------------------------------------------
; VAL_CUR_IS_ZERO — CUR_TYPE/CUR_DATAが0ならA=1、それ以外はA=0。
;   整数はCUR_DATA(16bit)がゼロ、単精度/倍精度は指数バイトがゼロ
;   (MBF_UNPACK_Aと同じ「指数0=値0」規則、単精度=CUR_DATA+3・
;   倍精度=CUR_DATA+7)。破壊: AF,HL。
; ---------------------------------------------------------------------
VAL_CUR_IS_ZERO:
    LD A,(CUR_TYPE)
    CP 2
    JR Z,_vciz_double
    OR A
    JR NZ,_vciz_single
    LD HL,(CUR_DATA)
    LD A,H
    OR L
    JR Z,_vciz_zero
    XOR A
    RET
_vciz_single:
    LD A,(CUR_DATA+3)
    OR A
    JR Z,_vciz_zero
    XOR A
    RET
_vciz_double:
    LD A,(CUR_DATA+7)
    OR A
    JR Z,_vciz_zero
    XOR A
    RET
_vciz_zero:
    LD A,1
    RET

; ---------------------------------------------------------------------
; FTNF_DO_ABS — 第4.16節E15。負ならVAL_NEGで符号を反転するだけ
;   (MBF単精度/倍精度はsign-magnitude形式なので符号ビットの反転=絶対値化、
;   整数は2の補数、いずれもVAL_NEGが型ごとに正しく行う)。
; ---------------------------------------------------------------------
FTNF_DO_ABS:
    CALL FTNF_NUM_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL VAL_CUR_SIGN
    OR A
    RET Z
    JP VAL_NEG

; ---------------------------------------------------------------------
; FTNF_DO_SGN — 第4.16節E15。0ならCUR=0(整数)、負なら-1、それ以外は1。
; ---------------------------------------------------------------------
FTNF_DO_SGN:
    CALL FTNF_NUM_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL VAL_CUR_IS_ZERO
    OR A
    JR Z,_sgn_notzero
    LD HL,0
    JP VAL_SET_INT
_sgn_notzero:
    CALL VAL_CUR_SIGN
    OR A
    JR Z,_sgn_pos
    LD HL,0FFFFh
    JP VAL_SET_INT
_sgn_pos:
    LD HL,1
    JP VAL_SET_INT

; ---------------------------------------------------------------------
; FTNF_DO_CDBL — 2026-09-20追記(l4-c7)。CDBL(<数値式>)。型を問わず
;   倍精度へ厳密に揃える(整数・単精度・倍精度いずれも丸め不要の厳密
;   変換)。run.asm ASSIGN_STMTの#変数代入が既に使っている
;   VAL_PROMOTE_CUR_TO_DOUBLE(CUR_TYPE/CUR_DATAを見て変換しCUR_TYPE=2
;   で書き戻す)をそのまま呼ぶ。二重実装しない。
; ---------------------------------------------------------------------
FTNF_DO_CDBL:
    CALL FTNF_NUM_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JP VAL_PROMOTE_CUR_TO_DOUBLE

; ---------------------------------------------------------------------
; FTNF_DO_SQR — 2026-09-20追記。SQR(<数値式>)、第4.16b節。
;   VAL_LOAD_CUR_TO_OPA(ABS/SGNのVAL_CUR_SIGN/VAL_CUR_IS_ZERO同様、型を
;   問わずMBF_OPAへ単精度で強制ロードする——第4.16b節「単精度へ丸めて
;   計算し単精度で返す」既知の差、倍精度引数もここで単精度へ落ちる)。
;   0はそのまま0、負はIllegal function call(5、第7.1節・l4-s6a
;   SQR(-1))、それ以外は拡張ROMバンク0(src/ext_bank/bank0.asm
;   EXT_BANK0_SQR_ENTRY、オフセット0x80固定)をEXT_BANK_CALL
;   (src/ext_bank/relay.asm、docs/spec/ext-rom-bank.md)経由で呼ぶ。
; ---------------------------------------------------------------------
FTNF_DO_SQR:
    CALL FTNF_NUM_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL VAL_LOAD_CUR_TO_OPA
    LD A,(MBF_OPA+3)          ; 単精度指数バイト(0=値0、VAL_CUR_IS_ZEROと同じ規則)
    OR A
    JR Z,_sqr_zero
    LD A,(MBF_OPA+2)
    AND 0x80                  ; 単精度符号ビット(VAL_CUR_SIGNと同じ規則)
    JR NZ,_sqr_negative
    XOR A                     ; A=0(バンク0)
    LD HL,0x6080               ; EXT_BANK0_SQR_ENTRY(bank0.asm、オフセット0x80固定)
    CALL EXT_BANK_CALL
    JP VAL_SET_SINGLE_FROM_RES
_sqr_zero:
    XOR A
    LD (MBF_RES),A
    LD (MBF_RES+1),A
    LD (MBF_RES+2),A
    LD (MBF_RES+3),A
    JP VAL_SET_SINGLE_FROM_RES
_sqr_negative:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,5
    LD (ERROR_KIND),A
    RET

; ---------------------------------------------------------------------
; FTNF_DO_SIN/FTNF_DO_COS — 2026-09-20追記。SIN(<数値式>)・
;   COS(<数値式>)、第4.16a節。SQRと同じくVAL_LOAD_CUR_TO_OPAで型を
;   問わず単精度へ強制ロードしてから拡張ROMバンク0(bank0.asm
;   EXT_BANK0_SIN_ENTRY/COS_ENTRY、オフセット0x0200/0x0210固定)を
;   EXT_BANK_CALL経由で呼ぶ。sin/cosは有限入力に対し常に[-1,1]の範囲
;   (MBF_STATUS異常は理論上到達しないため、SQR/TANと異なりステータスは
;   確認しない——l4_mbf_oracle_v10_m9.py sin_impl/cos_implもエラーを
;   投げない)。
; ---------------------------------------------------------------------
FTNF_DO_SIN:
    CALL FTNF_NUM_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL VAL_LOAD_CUR_TO_OPA
    XOR A                        ; A=0(バンク0)
    LD HL,0x6200                 ; EXT_BANK0_SIN_ENTRY(bank0.asm、オフセット0x0200固定)
    CALL EXT_BANK_CALL
    JP VAL_SET_SINGLE_FROM_RES

FTNF_DO_COS:
    CALL FTNF_NUM_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL VAL_LOAD_CUR_TO_OPA
    XOR A                        ; A=0(バンク0)
    LD HL,0x6210                 ; EXT_BANK0_COS_ENTRY(bank0.asm、オフセット0x0210固定)
    CALL EXT_BANK_CALL
    JP VAL_SET_SINGLE_FROM_RES

; ---------------------------------------------------------------------
; FTNF_DO_TAN — 2026-09-20追記。TAN(<数値式>)、第4.16a節。SIN/COSと同じ
;   経路(拡張ROMバンク0 EXT_BANK0_TAN_ENTRY、オフセット0x0220固定)だが、
;   TANはsin/cosの除算(cos(x)=0付近)でMBF_STATUS=2(0除算)になりうる
;   ため、VAL_DIV(第2492行)と同じ「MBF_STATUS=2ならDivision by zero
;   (11、第7.1節)」の判定を行う。MBF_STATUS=1(オーバーフロー)は
;   l4_mbf_oracle_v10_m9.py tan_implの構造上到達しない経路のはずだが、
;   VAL_CHECK_MBF_STATUSと同じ安全側の扱い(Overflow、6)にしておく。
; ---------------------------------------------------------------------
FTNF_DO_TAN:
    CALL FTNF_NUM_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL VAL_LOAD_CUR_TO_OPA
    XOR A                        ; A=0(バンク0)
    LD HL,0x6220                 ; EXT_BANK0_TAN_ENTRY(bank0.asm、オフセット0x0220固定)
    CALL EXT_BANK_CALL
    JP VAL_CHECK_MBF_STATUS_TAN

; VAL_CHECK_MBF_STATUS_TAN — VAL_CHECK_MBF_STATUS(第2529行)と同型だが、
;   MBF_STATUS=2(0除算)をOverflowではなくDivision by zero(11)として
;   区別する(VAL_DIVの_vdiv_zero分岐と同じ判定)。
VAL_CHECK_MBF_STATUS_TAN:
    LD A,(MBF_STATUS)
    OR A
    JR Z,_vcmst_ok
    CP 2
    JR Z,_vcmst_divzero
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_IS_RUNTIME),A
    RET
_vcmst_divzero:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,11
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_IS_RUNTIME),A
    RET
_vcmst_ok:
    JP VAL_SET_SINGLE_FROM_RES

; ---------------------------------------------------------------------
; PARSE_NUM_FROM_MEM — HL=バッファ先頭、B=バイト数。数値として解釈し
;   CUR_TYPE/CUR_DATAへ書く(VAL関数・INPUT数値項目が共有、
;   run.asmのDATA_READ_ONEと同じ「CUR_PTR/LINE_ENDを一時的に差し替える」
;   手法)。先頭の空白・符号'-'/'+'を許可。数字が無ければ整数0にする
;   (仕様書に無い判断、VAL("abc")等は未測定)。ERROR_FLAGは変更しない
;   (常に成功扱い、範囲外はMBF_FIN/DFIN任せで丸まる)。
; ---------------------------------------------------------------------
PARSE_NUM_FROM_MEM:
    LD DE,(CUR_PTR)
    LD (PNFM_SAVE_PTR),DE
    LD DE,(LINE_END)
    LD (PNFM_SAVE_END),DE
    LD (CUR_PTR),HL
    LD D,0
    LD E,B
    ADD HL,DE
    LD (LINE_END),HL
    XOR A
    LD (PNFM_NEG),A
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '-'
    JR NZ,_pnfm_check_plus
    CALL ADV_PTR
    LD A,1
    LD (PNFM_NEG),A
    JR _pnfm_afterneg
_pnfm_check_plus:
    CP '+'
    JR NZ,_pnfm_afterneg
    CALL ADV_PTR
_pnfm_afterneg:
    CALL PEEK_CHAR
    CP '0'
    JR C,_pnfm_checkdot
    CP '9'+1
    JR C,_pnfm_isnum
_pnfm_checkdot:
    CP '.'
    JR NZ,_pnfm_zero
    CALL PEEK_CHAR2
    CP '0'
    JR C,_pnfm_zero
    CP '9'+1
    JR NC,_pnfm_zero
_pnfm_isnum:
    CALL LEX_NUMBER
    LD A,(LIT_HASDOT)
    OR A
    JR NZ,_pnfm_general
    LD A,(LIT_HASEXP)
    OR A
    JR NZ,_pnfm_general
    LD A,(LIT_HASSUFFIX)
    OR A
    JR NZ,_pnfm_general
    CALL LIT_TRY_INT16
    JR NC,_pnfm_general
    CALL VAL_SET_INT
    JR _pnfm_applysign
_pnfm_general:
    CALL LIT_COPY_TO_FINBUF
    CALL MBF_FIN
    LD A,(MBF_STATUS)
    CP 3
    JR Z,_pnfm_double
    CP 1
    JR Z,_pnfm_zero
    CALL VAL_SET_SINGLE_FROM_RES
    JR _pnfm_applysign
_pnfm_double:
    CALL MBF_DFIN
    LD A,(MBF_STATUS)
    OR A
    JR NZ,_pnfm_zero
    CALL VAL_SET_DOUBLE_FROM_DRES
    JR _pnfm_applysign
_pnfm_zero:
    LD HL,0
    CALL VAL_SET_INT
_pnfm_applysign:
    LD A,(PNFM_NEG)
    OR A
    JR Z,_pnfm_done
    CALL VAL_NEG
_pnfm_done:
    LD DE,(PNFM_SAVE_END)
    LD (LINE_END),DE
    LD DE,(PNFM_SAVE_PTR)
    LD (CUR_PTR),DE
    RET

; ---------------------------------------------------------------------
; STR$(第4.14節E8)。CUR_TYPE/CUR_DATAの値をRUN_STR_TMP_LEN/BUFへ書式化
;   する。PRINT_VALUEと同じ桁の作り方(PUD_PLACES流用)だが、末尾の空白
;   (PRINT時の項目区切り用、l4-basic.md第2節)は付けない(E8「先頭col0は
;   変化せず数字はcol1から」——先頭の符号1桁だけが残る)。倍精度は
;   単精度へ丸めてから同じ経路で書式化する(仕様書に無い判断:
;   ASSIGN_STMTの%代入と同じ考え方、STR$の倍精度書式は未測定のため)。
; ---------------------------------------------------------------------
STR_FROM_CUR:
    XOR A
    LD (RUN_STR_TMP_LEN),A
    LD A,(CUR_TYPE)
    CP 2
    JR NZ,_sfc_check_int
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL MBF_DTOS
    CALL VAL_SET_SINGLE_FROM_RES
_sfc_check_int:
    LD A,(CUR_TYPE)
    OR A
    JR NZ,_sfc_single
    LD HL,(CUR_DATA)
    BIT 7,H
    JR Z,_sfc_int_pos
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
    LD A,'-'
    CALL STR_APPEND_CHAR
    JR _sfc_int_digits
_sfc_int_pos:
    LD A,' '
    CALL STR_APPEND_CHAR
_sfc_int_digits:
    JP STR_APPEND_UDEC
_sfc_single:
    CALL VAL_LOAD_CUR_TO_OPA
    CALL MBF_FOUT
    LD A,(UA_EXP)
    OR A
    JR Z,_sfc_s_zero_sign
    LD A,(FOUT_SIGN)
    OR A
    JR NZ,_sfc_s_neg
_sfc_s_zero_sign:
    LD A,' '
    CALL STR_APPEND_CHAR
    JR _sfc_s_digits
_sfc_s_neg:
    LD A,'-'
    CALL STR_APPEND_CHAR
_sfc_s_digits:
    LD A,(FOUT_LEN)
    LD B,A
    LD C,0
_sfc_s_loop:
    LD A,B
    OR A
    RET Z
    PUSH BC
    LD HL,FOUT_BUF
    LD D,0
    LD E,C
    ADD HL,DE
    LD A,(HL)
    CALL STR_APPEND_CHAR
    POP BC
    INC C
    DEC B
    JR _sfc_s_loop

; STR_APPEND_CHAR — A=文字。RUN_STR_TMP_BUF[RUN_STR_TMP_LEN]へ追記し
;   1増やす(31文字超は捨てる、既存のString too long上限と同じ考え方)。
STR_APPEND_CHAR:
    PUSH BC
    LD B,A
    LD A,(RUN_STR_TMP_LEN)
    CP 31
    JR NC,_sac_full
    PUSH HL
    PUSH DE
    LD HL,RUN_STR_TMP_BUF
    LD E,A
    LD D,0
    ADD HL,DE
    LD (HL),B
    POP DE
    POP HL
    LD A,(RUN_STR_TMP_LEN)
    INC A
    LD (RUN_STR_TMP_LEN),A
_sac_full:
    POP BC
    RET

; STR_APPEND_UDEC — HL=符号なし16bit値。RUN_STR_TMP_LEN/BUFへ10進の桁を
;   前ゼロ抑制つきで追記する(PRINT_UDECと同じ算法、出力先を画面でなく
;   文字列バッファへ変えただけ)。
STR_APPEND_UDEC:
    LD (PUD_VALUE),HL
    XOR A
    LD (PUD_STARTED),A
    LD IX,PUD_PLACES
    LD B,5
_sau_place_loop:
    LD L,(IX+0)
    LD H,(IX+1)
    LD (PUD_PLACE),HL
    XOR A
    LD (PUD_DIGIT),A
_sau_sub_loop:
    LD HL,(PUD_VALUE)
    LD DE,(PUD_PLACE)
    OR A
    SBC HL,DE
    JR C,_sau_sub_done
    LD (PUD_VALUE),HL
    LD A,(PUD_DIGIT)
    INC A
    LD (PUD_DIGIT),A
    JP _sau_sub_loop
_sau_sub_done:
    LD A,B
    CP 1
    JR NZ,_sau_not_last
    LD A,(PUD_DIGIT)
    ADD A,'0'
    CALL STR_APPEND_CHAR
    JR _sau_advance
_sau_not_last:
    LD A,(PUD_DIGIT)
    OR A
    JR NZ,_sau_show
    LD A,(PUD_STARTED)
    OR A
    JR Z,_sau_advance
_sau_show:
    LD A,1
    LD (PUD_STARTED),A
    LD A,(PUD_DIGIT)
    ADD A,'0'
    CALL STR_APPEND_CHAR
_sau_advance:
    LD DE,2
    ADD IX,DE
    DJNZ _sau_place_loop
    RET

; ---------------------------------------------------------------------
; LEX_NUMBER — CUR_PTRが数値定数の先頭(数字または'.'+数字)を指している
;   前提で、数値定数の文字列をそのままLIT_BUF/LIT_LENへコピーし、
;   CUR_PTRを直後まで進める(l4-basic.md 第5.1節の構文: 整数部→小数点→
;   小数部→[E/e/D/d[+/-]指数]→[!/#])。フラグ LIT_HASDOT/LIT_HASEXP/
;   LIT_HASSUFFIX で、後続の分岐(FACTORの純粋整数判定)に使う情報を返す。
;   24バイトを超える分は捨てる(仕様書に無い判断、極端に長い定数は対象外)。
; ---------------------------------------------------------------------
LEX_NUMBER:
    XOR A
    LD (LIT_LEN),A
    LD (LIT_HASDOT),A
    LD (LIT_HASEXP),A
    LD (LIT_HASSUFFIX),A
_ln_intpart:
    CALL PEEK_CHAR
    CP '0'
    JR C,_ln_after_intpart
    CP '9'+1
    JR NC,_ln_after_intpart
    CALL LEX_NUMBER_APPEND
    CALL ADV_PTR
    JR _ln_intpart
_ln_after_intpart:
    CALL PEEK_CHAR
    CP '.'
    JR NZ,_ln_after_dot
    LD A,1
    LD (LIT_HASDOT),A
    CALL PEEK_CHAR
    CALL LEX_NUMBER_APPEND
    CALL ADV_PTR
_ln_fracpart:
    CALL PEEK_CHAR
    CP '0'
    JR C,_ln_after_dot
    CP '9'+1
    JR NC,_ln_after_dot
    CALL LEX_NUMBER_APPEND
    CALL ADV_PTR
    JR _ln_fracpart
_ln_after_dot:
_ln_check_exp:
    CALL PEEK_CHAR
    CALL FOLD_UPPER
    CP 'E'
    JR Z,_ln_have_exp
    CP 'D'
    JR Z,_ln_have_exp
    JR _ln_after_exp
_ln_have_exp:
    LD A,1
    LD (LIT_HASEXP),A
    CALL PEEK_CHAR
    CALL LEX_NUMBER_APPEND
    CALL ADV_PTR
    CALL PEEK_CHAR
    CP '+'
    JR Z,_ln_exp_sign
    CP '-'
    JR NZ,_ln_exp_digits
_ln_exp_sign:
    CALL PEEK_CHAR
    CALL LEX_NUMBER_APPEND
    CALL ADV_PTR
_ln_exp_digits:
    CALL PEEK_CHAR
    CP '0'
    JR C,_ln_after_exp
    CP '9'+1
    JR NC,_ln_after_exp
    CALL LEX_NUMBER_APPEND
    CALL ADV_PTR
    JR _ln_exp_digits
_ln_after_exp:
    CALL PEEK_CHAR
    CP '#'
    JR Z,_ln_suffix
    CP '!'
    JR NZ,_ln_done
_ln_suffix:
    LD A,1
    LD (LIT_HASSUFFIX),A
    CALL PEEK_CHAR
    CALL LEX_NUMBER_APPEND
    CALL ADV_PTR
_ln_done:
    RET

; LEX_NUMBER_APPEND — A=文字。LIT_BUF[LIT_LEN]へ書きLIT_LENを進める
;   (24バイトで打ち切り)。破壊: AF,HL,DE。
LEX_NUMBER_APPEND:
    PUSH AF
    LD A,(LIT_LEN)
    CP 24
    JR NC,_lna_full
    LD H,0
    LD L,A
    LD DE,LIT_BUF
    ADD HL,DE
    EX DE,HL
    POP AF
    LD (DE),A
    PUSH AF
    LD A,(LIT_LEN)
    INC A
    LD (LIT_LEN),A
_lna_full:
    POP AF
    RET

; ---------------------------------------------------------------------
; LIT_TRY_INT16 — LIT_BUF(数字のみ、LIT_LEN桁)を16bit整数として解釈
;   できるか試みる。元のFACTOR整数リテラル解析(M7段階3b)と同じ
;   3277/32769の事前・事後チェックを、LIT_BUFを読む形に書き直しただけ
;   (アルゴリズムは変更していない)。
;   出力: CF=1のときHL=値(0..32768、0..32767が実際に打鍵できる整数、
;   32768は単項マイナス([-32768])経由でのみ意味を持つ)。
;   CF=0のとき範囲外(呼び出し元はMBF_FINへ回す、l4-basic.md 第5.2節)。
;   破壊: AF,HL,DE,IX。
; ---------------------------------------------------------------------
LIT_TRY_INT16:
    LD A,(LIT_LEN)
    OR A
    JR Z,_ti16_fail
    LD HL,0
    LD IX,LIT_BUF
    LD B,A
_ti16_loop:
    LD DE,3277
    CALL CP_HL_DE
    JR NC,_ti16_fail          ; HL>=3277
    LD A,(IX+0)
    SUB '0'
    LD E,A
    LD D,0
    PUSH DE
    ADD HL,HL
    PUSH HL
    ADD HL,HL
    ADD HL,HL
    POP DE
    ADD HL,DE
    POP DE
    ADD HL,DE
    LD DE,32769
    CALL CP_HL_DE
    JR NC,_ti16_fail          ; HL>=32769
    INC IX
    DJNZ _ti16_loop
    SCF
    RET
_ti16_fail:
    OR A
    RET

; LIT_COPY_TO_FINBUF — LIT_BUF[0..LIT_LEN)をFIN_BUF/FIN_LENへコピーする
;   (mbf_single.asmのMBF_FIN入力形式)。破壊: AF,B,HL,DE。
LIT_COPY_TO_FINBUF:
    LD A,(LIT_LEN)
    LD (FIN_LEN),A
    OR A
    RET Z
    LD B,A
    LD HL,LIT_BUF
    LD DE,FIN_BUF
_lctf_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _lctf_loop
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
; VAL_* — CUR_TYPE/CUR_DATA・RHS_TYPE/RHS_DATA・VAL_STACKを操作する
;   値の型付き表現の基本ルーチン群(ヘッダコメント参照)。
; ---------------------------------------------------------------------

; VAL_SET_INT — HL(0..65535として書くが実運用0..32768)をCUR_TYPE=0の
;   整数値として設定する。破壊: AF,HL。
VAL_SET_INT:
    LD (CUR_DATA),HL
    XOR A
    LD (CUR_TYPE),A
    LD (CUR_DATA+2),A
    LD (CUR_DATA+3),A
    LD (CUR_DATA+4),A
    LD (CUR_DATA+5),A
    LD (CUR_DATA+6),A
    LD (CUR_DATA+7),A
    RET

; VAL_SET_SINGLE_FROM_RES — MBF_RES(4バイト)をCUR_TYPE=1の単精度値として
;   設定する。破壊: AF。
VAL_SET_SINGLE_FROM_RES:
    LD A,1
    LD (CUR_TYPE),A
    LD A,(MBF_RES)
    LD (CUR_DATA),A
    LD A,(MBF_RES+1)
    LD (CUR_DATA+1),A
    LD A,(MBF_RES+2)
    LD (CUR_DATA+2),A
    LD A,(MBF_RES+3)
    LD (CUR_DATA+3),A
    XOR A
    LD (CUR_DATA+4),A
    LD (CUR_DATA+5),A
    LD (CUR_DATA+6),A
    LD (CUR_DATA+7),A
    RET

; VAL_SET_DOUBLE_FROM_DRES — M7段階4b-3: MBF_DRES(8バイト)をCUR_TYPE=2の
;   倍精度値として設定する。破壊: AF,HL。
VAL_SET_DOUBLE_FROM_DRES:
    LD A,2
    LD (CUR_TYPE),A
    LD HL,MBF_DRES
    LD DE,CUR_DATA
    LD B,8
_vsdfd_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vsdfd_loop
    RET

; VAL_PROMOTE_CUR_TO_DOUBLE — M7段階4b-3新設。CUR_TYPE/CUR_DATAの値を、
;   型を問わず倍精度(CUR_TYPE=2)へ厳密に揃える(整数はMBF_ITOD、単精度
;   はMBF_STOD、倍精度なら何もしない)。run.asm ASSIGN_STMTの#変数への
;   代入(l4-program.md 第4.4c節「単精度の値を#変数へ代入すると単精度の
;   値がそのまま倍精度になる、変換自体は正確」)が使う。破壊: AF,HL,DE,B。
VAL_PROMOTE_CUR_TO_DOUBLE:
    LD A,(CUR_TYPE)
    CP 2
    RET Z
    CALL VAL_LOAD_CUR_TO_OPA_D
    LD HL,MBF_DOPA
    LD DE,MBF_DRES
    LD B,8
_vpctd_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vpctd_loop
    CALL VAL_SET_DOUBLE_FROM_DRES
    RET

; VAL_STACK_ADDR — A=インデックス(0..VAL_STACK_DEPTH-1)。
;   HL=VAL_STACK+インデックス*9(1組=型1+データ8バイト、段階4b-3で
;   5バイトから拡張)を返す。破壊: DE。
VAL_STACK_ADDR:
    LD E,A
    LD D,0
    LD H,D
    LD L,E
    ADD HL,HL   ; *2
    ADD HL,HL   ; *4
    ADD HL,HL   ; *8
    ADD HL,DE   ; *9
    LD DE,VAL_STACK
    ADD HL,DE
    RET

; VAL_PUSH — CUR_TYPE/CUR_DATA(9バイト、段階4b-3で5→9に拡張)をVAL_STACK
;   へ退避しVAL_SPを進める(Z80のPUSH HLと同じくCUR_TYPE/CUR_DATA自体は
;   書き換えない)。破壊: AF,HL,DE,B。
VAL_PUSH:
    LD A,(VAL_SP)
    CALL VAL_STACK_ADDR
    EX DE,HL
    LD A,(CUR_TYPE)
    LD (DE),A
    INC DE
    LD HL,CUR_DATA
    LD B,8
_vpush_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vpush_loop
    LD A,(VAL_SP)
    INC A
    LD (VAL_SP),A
    RET

; VAL_POP — VAL_SPを1つ戻し、その位置の9バイトをCUR_TYPE/CUR_DATAへ
;   書き戻す(Z80のPOP HLに相当)。破壊: AF,HL,DE,B。
VAL_POP:
    LD A,(VAL_SP)
    DEC A
    LD (VAL_SP),A
    CALL VAL_STACK_ADDR
    LD A,(HL)
    LD (CUR_TYPE),A
    INC HL
    LD DE,CUR_DATA
    LD B,8
_vpop_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vpop_loop
    RET

; VAL_POP_DISCARD — VAL_SPを1つ戻すだけ(中身は読まない)。誤り処理での
;   スタック帳尻合わせに使う(Z80の"POP HL; RET"パターンの対応物)。
;   破壊: AF。
VAL_POP_DISCARD:
    LD A,(VAL_SP)
    DEC A
    LD (VAL_SP),A
    RET

; VAL_MOVE_CUR_TO_RHS — CUR_TYPE/CUR_DATA(9バイト)をRHS_TYPE/RHS_DATAへ
;   複写する。破壊: AF,HL,DE,B。
VAL_MOVE_CUR_TO_RHS:
    LD A,(CUR_TYPE)
    LD (RHS_TYPE),A
    LD HL,CUR_DATA
    LD DE,RHS_DATA
    LD B,8
_vmctr_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vmctr_loop
    RET

; VAL_LOAD_CUR_TO_OPA — CUR_TYPE/CUR_DATAの値をMBF_OPAへ用意する
;   (整数は MBF_INT_TO_SINGLE で厳密に単精度化してから複写、単精度は
;   そのまま複写)。
;   M7段階4b-3追記: CUR_TYPE=2(倍精度)は MBF_DTOS で単精度へ丸めてから
;   渡す。**仕様書に無い判断**——この入口(VAL_LOAD_CUR_TO_OPA)は元々
;   「整数/単精度」だけを前提にした消費者(IFの比較VAL_COMPARE_CUR_RHS・
;   %代入の丸めMBF_ROUND_TO_INT16、いずれも本段階の範囲外)が既に
;   呼んでいるため、倍精度をそのまま4バイトとして読ませるとバイト列を
;   誤読して暴走する。真の倍精度比較・丸めは本段階の範囲外のまま
;   (精度が落ちるだけで、誤動作は防ぐ)。倍精度どうしの演算・PRINTは
;   これを経由せずVAL_LOAD_CUR_TO_OPA_Dを使う。破壊: AF,HL。
VAL_LOAD_CUR_TO_OPA:
    LD A,(CUR_TYPE)
    CP 2
    JR Z,_vlca_double
    OR A
    JR NZ,_vlca_single
    LD HL,(CUR_DATA)
    LD (MBF_IN_INT),HL
    CALL MBF_INT_TO_SINGLE
    CALL FIN_COPY_RES_TO_OPA
    RET
_vlca_single:
    LD A,(CUR_DATA)
    LD (MBF_OPA),A
    LD A,(CUR_DATA+1)
    LD (MBF_OPA+1),A
    LD A,(CUR_DATA+2)
    LD (MBF_OPA+2),A
    LD A,(CUR_DATA+3)
    LD (MBF_OPA+3),A
    RET
_vlca_double:
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL MBF_DTOS
    LD A,(MBF_RES)
    LD (MBF_OPA),A
    LD A,(MBF_RES+1)
    LD (MBF_OPA+1),A
    LD A,(MBF_RES+2)
    LD (MBF_OPA+2),A
    LD A,(MBF_RES+3)
    LD (MBF_OPA+3),A
    RET

; VAL_LOAD_RHS_TO_OPB — RHS_TYPE/RHS_DATAの値をMBF_OPBへ用意する
;   (VAL_LOAD_CUR_TO_OPAと対の実装、倍精度の扱いも同じ「仕様書に無い
;   判断」に従う)。MBF_INT_TO_SINGLE/MBF_DTOSはMBF_OPA/OPBを一切
;   読み書きしないため、先にOPAを設定していても壊れない
;   =ヘッダ確認済み、mbf_single.asm MBF_INT_TO_SINGLE参照)。
;   破壊: AF,HL。
VAL_LOAD_RHS_TO_OPB:
    LD A,(RHS_TYPE)
    CP 2
    JR Z,_vlrb_double
    OR A
    JR NZ,_vlrb_single
    LD HL,(RHS_DATA)
    LD (MBF_IN_INT),HL
    CALL MBF_INT_TO_SINGLE
    LD A,(MBF_RES)
    LD (MBF_OPB),A
    LD A,(MBF_RES+1)
    LD (MBF_OPB+1),A
    LD A,(MBF_RES+2)
    LD (MBF_OPB+2),A
    LD A,(MBF_RES+3)
    LD (MBF_OPB+3),A
    RET
_vlrb_single:
    LD A,(RHS_DATA)
    LD (MBF_OPB),A
    LD A,(RHS_DATA+1)
    LD (MBF_OPB+1),A
    LD A,(RHS_DATA+2)
    LD (MBF_OPB+2),A
    LD A,(RHS_DATA+3)
    LD (MBF_OPB+3),A
    RET
_vlrb_double:
    ; RHS_DATA(8バイト、必ず倍精度の生表現)をMBF_DOPAへ複写してMBF_DTOS
    ; を呼ぶ(DTOSの入力はMBF_DOPA固定)。この時点でCUR側の単精度化は
    ; VAL_LOAD_CUR_TO_OPAが既に完了しMBF_OPAへ結果を出し終えているため、
    ; MBF_DOPAを再利用しても壊れない。破壊: AF,HL,DE,B。
    LD HL,RHS_DATA
    LD DE,MBF_DOPA
    LD B,8
_vlrb_dcopy:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vlrb_dcopy
    CALL MBF_DTOS
    LD A,(MBF_RES)
    LD (MBF_OPB),A
    LD A,(MBF_RES+1)
    LD (MBF_OPB+1),A
    LD A,(MBF_RES+2)
    LD (MBF_OPB+2),A
    LD A,(MBF_RES+3)
    LD (MBF_OPB+3),A
    RET

; ---------------------------------------------------------------------
; VAL_LOAD_CUR_TO_OPA_D / VAL_LOAD_RHS_TO_OPB_D — M7段階4b-3新設。
;   CUR_TYPE/CUR_DATA・RHS_TYPE/RHS_DATAの値を、型を問わず**倍精度**へ
;   厳密に揃えてMBF_DOPA/MBF_DOPBへ用意する(整数はMBF_ITOD、単精度は
;   MBF_STOD、倍精度はそのまま複写。整数＜単精度＜倍精度の昇格順)。
;   倍精度どうしの演算(VAL_ADD等の昇格後)・PRINT_VALUEの倍精度分岐が使う。
;   破壊: AF,HL,DE,B。
; ---------------------------------------------------------------------
VAL_LOAD_CUR_TO_OPA_D:
    LD A,(CUR_TYPE)
    CP 2
    JR Z,_vlcad_double
    OR A
    JR NZ,_vlcad_single
    LD HL,(CUR_DATA)
    LD (MBF_IN_INT),HL
    CALL MBF_ITOD
    JR _vlcad_copy_dres
_vlcad_single:
    LD A,(CUR_DATA)
    LD (MBF_OPA),A
    LD A,(CUR_DATA+1)
    LD (MBF_OPA+1),A
    LD A,(CUR_DATA+2)
    LD (MBF_OPA+2),A
    LD A,(CUR_DATA+3)
    LD (MBF_OPA+3),A
    CALL MBF_STOD
_vlcad_copy_dres:
    LD HL,MBF_DRES
    LD DE,MBF_DOPA
    LD B,8
_vlcad_copy_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vlcad_copy_loop
    RET
_vlcad_double:
    LD HL,CUR_DATA
    LD DE,MBF_DOPA
    LD B,8
_vlcad_direct_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vlcad_direct_loop
    RET

VAL_LOAD_RHS_TO_OPB_D:
    LD A,(RHS_TYPE)
    CP 2
    JR Z,_vlrbd_double
    OR A
    JR NZ,_vlrbd_single
    LD HL,(RHS_DATA)
    LD (MBF_IN_INT),HL
    CALL MBF_ITOD
    JR _vlrbd_copy_dres
_vlrbd_single:
    LD A,(RHS_DATA)
    LD (MBF_OPA),A
    LD A,(RHS_DATA+1)
    LD (MBF_OPA+1),A
    LD A,(RHS_DATA+2)
    LD (MBF_OPA+2),A
    LD A,(RHS_DATA+3)
    LD (MBF_OPA+3),A
    CALL MBF_STOD
_vlrbd_copy_dres:
    LD HL,MBF_DRES
    LD DE,MBF_DOPB
    LD B,8
_vlrbd_copy_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vlrbd_copy_loop
    RET
_vlrbd_double:
    LD HL,RHS_DATA
    LD DE,MBF_DOPB
    LD B,8
_vlrbd_direct_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _vlrbd_direct_loop
    RET

; ---------------------------------------------------------------------
; VAL_NEG — CUR_TYPE/CUR_DATA = -CUR_TYPE/CUR_DATA。整数はそのまま
;   2の補数(既存の単項マイナスと同じ、-32768のオーバーフロー検出は
;   従来どおり対象外=段階3bからの既存の仕様書に無い既定を維持)、
;   単精度はMBF_NEG(符号ビット反転、ゼロは変えない)。
;   M7段階4b-3追記: 倍精度はMBF_DNEG(符号ビット反転、ゼロは変えない、
;   単精度と同型)。
; ---------------------------------------------------------------------
VAL_NEG:
    LD A,(CUR_TYPE)
    CP 2
    JR Z,_vneg_double
    OR A
    JR NZ,_vneg_single
    LD HL,(CUR_DATA)
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
    LD (CUR_DATA),HL
    RET
_vneg_single:
    CALL VAL_LOAD_CUR_TO_OPA
    CALL MBF_NEG
    CALL VAL_SET_SINGLE_FROM_RES
    RET
_vneg_double:
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL MBF_DNEG
    CALL VAL_SET_DOUBLE_FROM_DRES
    RET

; ---------------------------------------------------------------------
; VAL_ADD/VAL_SUB/VAL_MUL/VAL_DIV — CUR = CUR (op) RHS。
;   l4-basic.md 第5.2節: 整数どうしの16bit加減算がオーバーフローしたら
;   単精度へ昇格する。除算は常に単精度以上で計算する(ファイル冒頭
;   コメント「仕様書に無い判断」参照)。
;   M7段階4b-3: 型の昇格順は 整数 ＜ 単精度 ＜ 倍精度（混在時は高い方へ
;   揃える、docs/spec/l4-basic.md 第5節冒頭「型の昇格」）。CUR_TYPE・
;   RHS_TYPEのどちらかが2(倍精度)なら常に倍精度で計算する(下記
;   `_vXXX_dbl`)。段階4a-2の宿題(このコメント旧版が明記していた
;   「整数どうしの乗算も単精度で計算する簡略化」)は本段階で解消し、
;   整数どうしの乗算は16bit同士の符号付き乗算を試み、-32768..32767に
;   収まれば整数のまま、溢れれば単精度へ昇格する(VAL_MUL_INT16)。
;   MBF演算がMBF_STATUS!=0を返した場合(表現範囲のオーバーフロー・
;   0除算)はERROR_FLAG/ERROR_KIND/ERROR_IS_RUNTIMEを設定して戻る
;   (第5.6節、第7.1.1節)。
; ---------------------------------------------------------------------
VAL_ADD:
    LD A,(CUR_TYPE)
    CP 2
    JR Z,_vadd_dbl
    LD A,(RHS_TYPE)
    CP 2
    JR Z,_vadd_dbl
    LD A,(CUR_TYPE)
    OR A
    JR NZ,_vadd_mbf
    LD A,(RHS_TYPE)
    OR A
    JR NZ,_vadd_mbf
    LD HL,(CUR_DATA)
    LD DE,(RHS_DATA)
    OR A
    ADC HL,DE
    JP PE,_vadd_mbf      ; 符号付きオーバーフロー -> 昇格
    CALL VAL_SET_INT
    RET
_vadd_mbf:
    CALL VAL_LOAD_CUR_TO_OPA
    CALL VAL_LOAD_RHS_TO_OPB
    CALL MBF_ADD
    JP VAL_CHECK_MBF_STATUS
_vadd_dbl:
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL VAL_LOAD_RHS_TO_OPB_D
    CALL MBF_DADD
    JP VAL_CHECK_MBF_DSTATUS

VAL_SUB:
    LD A,(CUR_TYPE)
    CP 2
    JR Z,_vsub_dbl
    LD A,(RHS_TYPE)
    CP 2
    JR Z,_vsub_dbl
    LD A,(CUR_TYPE)
    OR A
    JR NZ,_vsub_mbf
    LD A,(RHS_TYPE)
    OR A
    JR NZ,_vsub_mbf
    LD HL,(CUR_DATA)
    LD DE,(RHS_DATA)
    OR A
    SBC HL,DE
    JP PE,_vsub_mbf      ; 符号付きオーバーフロー -> 昇格
    CALL VAL_SET_INT
    RET
_vsub_mbf:
    CALL VAL_LOAD_CUR_TO_OPA
    CALL VAL_LOAD_RHS_TO_OPB
    CALL MBF_SUB
    JP VAL_CHECK_MBF_STATUS
_vsub_dbl:
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL VAL_LOAD_RHS_TO_OPB_D
    CALL MBF_DSUB
    JP VAL_CHECK_MBF_DSTATUS

; VAL_MUL — 整数どうしは16bit符号付き乗算(VAL_MUL_INT16)を試み、範囲内
;   (-32768..32767)なら整数のまま、溢れれば単精度へ昇格する(段階4a-2の
;   宿題の解消、上のヘッダコメント参照)。どちらかが倍精度なら倍精度で、
;   それ以外(整数×単精度・単精度どうし)は単精度(MBF_MUL)で計算する。
VAL_MUL:
    LD A,(CUR_TYPE)
    CP 2
    JR Z,_vmul_dbl
    LD A,(RHS_TYPE)
    CP 2
    JR Z,_vmul_dbl
    LD A,(CUR_TYPE)
    OR A
    JR NZ,_vmul_single
    LD A,(RHS_TYPE)
    OR A
    JR NZ,_vmul_single
    CALL VAL_MUL_INT16
    JR C,_vmul_single    ; 範囲外(-32768..32767に収まらない) -> 単精度へ
    RET
_vmul_single:
    CALL VAL_LOAD_CUR_TO_OPA
    CALL VAL_LOAD_RHS_TO_OPB
    CALL MBF_MUL
    JP VAL_CHECK_MBF_STATUS
_vmul_dbl:
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL VAL_LOAD_RHS_TO_OPB_D
    CALL MBF_DMUL
    JP VAL_CHECK_MBF_DSTATUS

; VAL_MUL_INT16 — CUR_DATA・RHS_DATAの下位16bit(符号付き)を掛け、
;   -32768..32767に収まればCUR_TYPE/CUR_DATAへ整数として書いて戻る
;   (CF=0)。収まらなければCUR_TYPE/CUR_DATAは変更せずCF=1で戻る
;   (呼び出し元が単精度経路へフォールバックする)。
;   仕様書に無い判断: 32bit積の計算そのものは10進の丸めを一切伴わない
;   厳密な整数演算であり、範囲判定だけがこのルーチンの役目
;   (l4-basic.md 第5.2節「範囲外は単精度へ昇格」)。
;   破壊: AF,HL,DE,BC,IX。
VAL_MUL_INT16:
    XOR A
    LD (MULI_SIGN),A
    LD HL,(CUR_DATA)
    BIT 7,H
    JR Z,_vmi_a_pos
    LD A,1
    LD (MULI_SIGN),A
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
_vmi_a_pos:
    LD (MULI_A),HL
    LD HL,(RHS_DATA)
    BIT 7,H
    JR Z,_vmi_b_pos
    LD A,(MULI_SIGN)
    XOR 1
    LD (MULI_SIGN),A
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
_vmi_b_pos:
    LD (MULI_B),HL
    ; 符号なし16x16→32bit乗算(MSB-firstのシフト加算)。
    ; BC:HL = 32bit積の累算器(BC=上位16bit、HL=下位16bit)、
    ; DE = 乗数(MULI_A、1bitずつ左シフトしながらMSBから取り出す)。
    ; ループ回数(16)はB(累算器の上位バイトと兼用できないため)ではなく
    ; MULI_COUNT(RAM)に持つ。
    LD BC,0
    LD HL,0
    LD DE,(MULI_A)
    LD A,16
    LD (MULI_COUNT),A
_vmi_loop:
    ; 累算器(BC:HL)を1bit左シフト
    SLA L
    RL H
    RL C
    RL B
    ; 乗数(DE)の最上位ビットを1bit取り出す(左シフト、CFへ)
    SLA E
    RL D
    JR NC,_vmi_noadd
    ; 累算器(BC:HL) += MULI_B(16bit、上位16bitへは桁上げだけ伝播)
    PUSH DE
    LD DE,(MULI_B)
    ADD HL,DE
    JR NC,_vmi_nocarry
    INC BC
_vmi_nocarry:
    POP DE
_vmi_noadd:
    LD A,(MULI_COUNT)
    DEC A
    LD (MULI_COUNT),A
    JR NZ,_vmi_loop
    ; BC:HL = |CUR|*|RHS| (32bit符号なし)。BC!=0なら16bitに収まらない
    ; ので即オーバーフロー。
    LD A,B
    OR C
    JR NZ,_vmi_overflow
    LD A,(MULI_SIGN)
    OR A
    JR NZ,_vmi_applyneg
    ; 正(0を含む): 0..32767だけ整数として表現できる
    ; (32768は単項マイナス経由でしか打鍵できない値のため、正の積としては
    ; 範囲外扱いにする)。
    LD DE,32768
    OR A
    SBC HL,DE
    JR NC,_vmi_overflow
    ADD HL,DE            ; HLを積の値に戻す
    CALL VAL_SET_INT
    OR A
    RET
_vmi_applyneg:
    ; 負: 0..32768が表現できる(-32768..0)。
    LD DE,32769
    OR A
    SBC HL,DE
    JR NC,_vmi_overflow
    ADD HL,DE             ; HLを積の絶対値に戻す
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
    CALL VAL_SET_INT
    OR A
    RET
_vmi_overflow:
    SCF
    RET

; VAL_DIV — '/'は整数どうしでも常に実数になる(l4-basic.md 第5.2節
;   「7/2=3.5」)。どちらかが倍精度なら倍精度(MBF_DDIV)、それ以外は
;   単精度(MBF_DIV)で計算する。MBF_STATUS=2(0除算)は
;   Division by zero(11、第7.1節)として扱う。
VAL_DIV:
    LD A,(CUR_TYPE)
    CP 2
    JR Z,_vdiv_dbl
    LD A,(RHS_TYPE)
    CP 2
    JR Z,_vdiv_dbl
    CALL VAL_LOAD_CUR_TO_OPA
    CALL VAL_LOAD_RHS_TO_OPB
    CALL MBF_DIV
    LD A,(MBF_STATUS)
    CP 2
    JR Z,_vdiv_zero
    JP VAL_CHECK_MBF_STATUS
_vdiv_dbl:
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL VAL_LOAD_RHS_TO_OPB_D
    CALL MBF_DDIV
    LD A,(MBF_STATUS)
    CP 2
    JR Z,_vdiv_zero
    JP VAL_CHECK_MBF_DSTATUS
_vdiv_zero:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,11
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_IS_RUNTIME),A
    RET

; VAL_CHECK_MBF_STATUS — 単精度MBF演算直後の共通後処理。MBF_STATUS=0
;   ならMBF_RESをCUR_TYPE/CUR_DATAへ設定して戻る。MBF_STATUS!=0(0除算は
;   呼び出し元で先に処理済みなので、ここに来るのはオーバーフロー=1の
;   はず)ならOverflow(6、第7.1節)としてERROR_FLAG等を設定する。
VAL_CHECK_MBF_STATUS:
    LD A,(MBF_STATUS)
    OR A
    JR NZ,_vcms_overflow
    CALL VAL_SET_SINGLE_FROM_RES
    RET
_vcms_overflow:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_IS_RUNTIME),A
    RET

; VAL_CHECK_MBF_DSTATUS — M7段階4b-3新設。倍精度MBF演算直後の共通後処理
;   (VAL_CHECK_MBF_STATUSの倍精度版)。MBF_STATUS=0ならMBF_DRESを
;   CUR_TYPE/CUR_DATAへ設定して戻る。MBF_STATUS!=0(0除算は呼び出し元で
;   先に処理済み)ならOverflow(6、第7.1節)。
VAL_CHECK_MBF_DSTATUS:
    LD A,(MBF_STATUS)
    OR A
    JR NZ,_vcmds_overflow
    CALL VAL_SET_DOUBLE_FROM_DRES
    RET
_vcmds_overflow:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,6
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_IS_RUNTIME),A
    RET

; ---------------------------------------------------------------------
; PRINT_VALUE — CUR_TYPE/CUR_DATAの値を出力する。整数(CUR_TYPE=0)は
;   既存のPRINT_NUMBER(l4-basic.md 第2節)をそのまま使う。単精度
;   (CUR_TYPE=1)は、MBF_FOUTが返す数字列に、整数と同じ前置1桁
;   (正/0は空白、負は'-')・後置空白1を付けて出す(第5.3節「整数と同じ
;   規則がそのまま浮動小数点にも適用される」)。ゼロ値はMBF_FOUTが
;   FOUT_SIGNを設定しない(内部でUA_EXP=0の早期RETを通るため)ので、
;   UA_EXPで先にゼロ判定してから符号を決める(仕様書に無い判断:
;   整数のゼロと同じく常に空白側=正として扱う、第2節sign_space_before)。
;   M7段階4b-3追記: 倍精度(CUR_TYPE=2)は、MBF_DFOUT/DFOUT_BUF/DFOUT_LEN
;   に同じ設計を広げただけ(DA_EXP・DFOUT_SIGNがMBF_DFOUT呼び出し後も
;   UA_EXP・FOUT_SIGNと同じ形で残る、mbf_double.asm MBF_DFOUT本体で確認
;   済み)。
; ---------------------------------------------------------------------
PRINT_VALUE:
    LD A,(CUR_TYPE)
    CP 2
    JR Z,_l4pv_double
    OR A
    JR NZ,_l4pv_single
    LD HL,(CUR_DATA)
    ; M7段階5c-2b追記: 印字前にフィールド幅(符号1+桁数+末尾空白1)を
    ; 求め、行に収まらなければ折り返す(PRINT_FIELD_WRAP_CHECK、第5.3節)。
    BIT 7,H
    JR Z,_l4pvi_wrap_pos
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
_l4pvi_wrap_pos:
    CALL DEC_DIGIT_COUNT
    ADD A,2
    CALL PRINT_FIELD_WRAP_CHECK
    LD HL,(CUR_DATA)
    JP PRINT_NUMBER
_l4pv_single:
    CALL VAL_LOAD_CUR_TO_OPA
    CALL MBF_FOUT
    LD A,(FOUT_LEN)
    ADD A,2
    CALL PRINT_FIELD_WRAP_CHECK
    LD A,(UA_EXP)
    OR A
    JR Z,_l4pv_zero_sign
    LD A,(FOUT_SIGN)
    OR A
    JR NZ,_l4pv_neg
_l4pv_zero_sign:
    LD A,' '
    CALL PRINT_CHAR
    JR _l4pv_digits
_l4pv_neg:
    LD A,'-'
    CALL PRINT_CHAR
_l4pv_digits:
    LD A,(FOUT_LEN)
    LD B,A
    LD C,0
_l4pv_loop:
    LD A,B
    OR A
    JR Z,_l4pv_done
    LD HL,FOUT_BUF
    LD D,0
    LD E,C
    ADD HL,DE
    LD A,(HL)
    CALL PRINT_CHAR
    INC C
    DEC B
    JR _l4pv_loop
_l4pv_done:
    LD A,' '
    CALL PRINT_CHAR
    RET
_l4pv_double:
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL MBF_DFOUT
    LD A,(DFOUT_LEN)
    ADD A,2
    CALL PRINT_FIELD_WRAP_CHECK
    LD A,(DA_EXP)
    OR A
    JR Z,_l4pvd_zero_sign
    LD A,(DFOUT_SIGN)
    OR A
    JR NZ,_l4pvd_neg
_l4pvd_zero_sign:
    LD A,' '
    CALL PRINT_CHAR
    JR _l4pvd_digits
_l4pvd_neg:
    LD A,'-'
    CALL PRINT_CHAR
_l4pvd_digits:
    LD A,(DFOUT_LEN)
    LD B,A
    LD C,0
_l4pvd_loop:
    LD A,B
    OR A
    JR Z,_l4pvd_done
    LD HL,DFOUT_BUF
    LD D,0
    LD E,C
    ADD HL,DE
    LD A,(HL)
    CALL PRINT_CHAR
    INC C
    DEC B
    JR _l4pvd_loop
_l4pvd_done:
    LD A,' '
    CALL PRINT_CHAR
    RET

; ---------------------------------------------------------------------
; PRINT_NUMBER — HL=16bit値(2の補数)。符号1桁(正/0は空白、負は'-')＋
;   数字＋末尾空白1を出力する(l4-basic.md 第2節)。M7段階3bのまま変更なし
;   (PRINT_VALUEが整数(CUR_TYPE=0)のときにHLへ値を積んでテイルコールする)。
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

; ---------------------------------------------------------------------
; DEC_DIGIT_COUNT — HL=0-65535(実運用0-32768)。PRINT_UDECと同じ前ゼロ
;   抑制規則(値0は1桁)で、印字せずに桁数だけをAへ返す(PUD_VALUE等の
;   スクラッチをPRINT_UDECと共用。呼び出しの入れ子はしない前提)。
;   M7段階5c-2b追記: 折り返し判定(PRINT_FIELD_WRAP_CHECK)が、実際に
;   印字する前に符号込みの幅を知るために使う。
; ---------------------------------------------------------------------
DEC_DIGIT_COUNT:
    LD (PUD_VALUE),HL
    XOR A
    LD (PUD_STARTED),A
    LD IX,PUD_PLACES
    LD B,5
    LD C,0
_l4ddc_place_loop:
    LD L,(IX+0)
    LD H,(IX+1)
    LD (PUD_PLACE),HL
    XOR A
    LD (PUD_DIGIT),A
_l4ddc_sub_loop:
    LD HL,(PUD_VALUE)
    LD DE,(PUD_PLACE)
    OR A
    SBC HL,DE
    JR C,_l4ddc_sub_done
    LD (PUD_VALUE),HL
    LD A,(PUD_DIGIT)
    INC A
    LD (PUD_DIGIT),A
    JP _l4ddc_sub_loop
_l4ddc_sub_done:
    LD A,B
    CP 1
    JR NZ,_l4ddc_not_last
    INC C
    JR _l4ddc_advance
_l4ddc_not_last:
    LD A,(PUD_DIGIT)
    OR A
    JR NZ,_l4ddc_show
    LD A,(PUD_STARTED)
    OR A
    JR Z,_l4ddc_advance
_l4ddc_show:
    LD A,1
    LD (PUD_STARTED),A
    INC C
_l4ddc_advance:
    LD DE,2
    ADD IX,DE
    DJNZ _l4ddc_place_loop
    LD A,C
    RET

; ---------------------------------------------------------------------
; PRINT_FIELD_WRAP_CHECK — A=これから印字するフィールドの全幅(符号1+
;   数字+末尾空白1)。現在桁(VAR_COL)から書くとその行(COLS=80桁)へ
;   収まらない場合、印字前にNEWLINEを呼んで次の行の先頭へ送る。
;
;   根拠: docs/spec/l4-program.md 第5.3節(l4-s5f、`locate 78,5:print 12`
;   の観測)。行の右端に近い桁で数値PRINTを行うと、その行には変化が
;   一切現れず、値全体が次の行へまとまって現れた——PRINT_CHARの1文字
;   ごとの折り返し(COLSを超えたらNEWLINE、screen.asm)とは別に、L4の
;   数値PRINTはフィールド全体を割らずに丸ごと次行へ送る規則を持つ、
;   という観測に基づく実装(厳密な桁の判定式そのものは同節が「未確定」
;   としているため、収まるかどうかの単純な比較のみを実装する)。
; ---------------------------------------------------------------------
PRINT_FIELD_WRAP_CHECK:
    PUSH BC
    LD B,A
    LD A,(VAR_COL)
    ADD A,B
    CP 81
    JR C,_l4pfwc_fit
    CALL NEWLINE
_l4pfwc_fit:
    POP BC
    RET
