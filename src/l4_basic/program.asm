; program.asm — M7段階5a: プログラムモード（行の入力・保存・LIST・NEW）。
;
; 根拠は docs/spec/l4-program.md（第1版）だけである。measurements/ も
; 公式ROMも参照していない。interp.asm（直接モードPRINT、変更点は
; BASIC_RUN_LINE/MATCH_STMT_KEYWORD/DIRECT_LINEの数箇所のみ）・
; keyboard.asm（LINE_FINISHの数行）・screen.asm（SCREEN_MAINに
; CALL PROGRAM_INIT を1行追加）と組み合わせて使う。
;
;   行番号つきの行はエコーのみでOk等が出ない       … l4-program.md 第1節
;   LISTの書式(行番号そのまま・命令語大文字化・     … l4-program.md 第2節
;   空白保持・?→PRINT展開時だけ空白挿入・:前後空白なし・
;   定数/文字列は打鍵どおり・大きい行番号もそのまま)
;   同一行番号は置換・行番号だけの行は削除・LISTは行番号順 … 第3節
;   トークン番号とは無関係（打鍵の再現でよい）        … 第4節
;
; 保存形式はゴールA（自由）。本実装は「行番号(2B)+本文長(1B)+本文(可変)」
; の可変長レコードを行番号昇順で並べた領域とし、公式の中間コード
; （トークン番号）は一切使わない（docs/notes/l4-token-design.md）。
; LISTは保存した本文を LIST_RENDER_TEXT で整形して出す。規則は
; docs/spec/l4-basic.md 第14節（l4-s5h、公式ROM723腕の測定）: 語・変数名の
; 英字は大文字、文字列の中・'以降・REM以降・DATAの:まで・数値定数は打鍵どおり、
; GO TOはGOTOに詰め、?はPRINTに展開する。最初の版（l4-program.md 第2節だけが
; 根拠）はPRINTと?しか知らず、ENDなどが小文字のまま残った。
;
; ---- 仕様書に無い判断（この段階で明示的に選んだもの） ----------------
;   - 行番号は行の先頭（桁0、前に空白なし）にある場合だけ行番号として
;     認識する。行頭に空白があるとその行は直接モードとして扱われ、多くは
;     Syntax errorになる（第5節4「行番号の前の空白」は未確定）。
;   - 行番号の上限は、実測で確認された65529までを妥当な範囲として受け付け、
;     それを超える数字列（桁数過多を含む）はこの行全体をSyntax errorとして
;     直接モード側の構文の誤りと同じ経路で扱う（第5節2「行番号の上限」は
;     未確定）。実装は BASIC_HANDLE_LINE で「行番号として解釈できない
;     digit-先頭行」を直接モードにフォールバックさせることで実現する
;     （結果としてDIRECT_LINEがMATCH_STMT_KEYWORDで不一致になりSyntax
;     errorになる）。
;   - 行番号だけの行（本文長0）は、既存の行があれば削除、無ければ何も
;     しない（第5節3「存在しない行番号だけを打った場合の反応」は未確定。
;     出力も一切起きない——行番号つきの行は常に無出力、という第1節の
;     規則をそのまま適用した）。
;   - `LIST` に範囲指定などの引数が続く場合はSyntax errorとする
;     （第5節5「LISTの範囲指定」は未確定。この版では引数無しのLISTだけを
;     実装する）。
;   - プログラム領域が溢れて新しい行が収まらない場合、その行は保存せず
;     何も表示しない（黙って無視する）。行番号つきの行は常に無出力という
;     第1節の規則を保つための選択であり、`Out of memory`
;     （errors.tsv 7番）を実際に出す挙動は測定されていない。
;   - 変数名等の大文字化は、最初の版では未確定として行わなかったが、l4-s5h
;     （docs/spec/l4-basic.md 第14節）で公式が大文字にすると測れたので行う。
;
; ---- RAM（メモリ配置、E969-E97Fは空き。E980から29バイトを使う） -----
STMT_KIND          EQU 0E980h  ; 1バイト。MATCH_STMT_KEYWORDが設定する
                                ; 文の種類(0=PRINT 1=LIST 2=NEW)
PROG_TMP16         EQU 0E981h  ; 2バイト（PARSE_LINENUMの作業領域）
PROG_DIGIT         EQU 0E983h  ; 2バイト（PARSE_LINENUMの作業領域）
PROG_CUR_LINENO    EQU 0E985h  ; 2バイト（保存/検索対象の行番号）
PROG_CUR_LNLEN     EQU 0E987h  ; 1バイト（行番号の桁数=LINE_BUF内での長さ）
PROG_CUR_TEXTLEN   EQU 0E988h  ; 1バイト（行番号より後ろの本文の長さ）
PROG_DEL_SRC       EQU 0E989h  ; 2バイト（PROGRAM_DELETE_ATの作業領域）
PROG_DEL_DST       EQU 0E98Bh  ; 2バイト
PROG_INS_AT        EQU 0E98Dh  ; 2バイト（PROGRAM_INSERT_ATの作業領域）
PROG_INS_SIZE      EQU 0E98Fh  ; 2バイト
PROG_TMP_SRC_LAST  EQU 0E991h  ; 2バイト
PROG_TMP_DST_LAST  EQU 0E993h  ; 2バイト
PROG_TMP_DST2      EQU 0E995h  ; 2バイト
PROG_REND_PTR      EQU 0E997h  ; 2バイト（LIST_RENDER_TEXTの走査位置）
PROG_REND_LEN      EQU 0E999h  ; 1バイト（LIST_RENDER_TEXTの残りバイト数）
PROG_REND_MODE     EQU 0E99Ah  ; 1バイト（LIST_RENDER_TEXTの状態。bit0=引用符の中
                                ; bit1=行末まで打鍵どおり bit2=DATAの中）
PROG_REND_INNAME   EQU 0E99Bh  ; 1バイト（名前の連なりの途中なら1）
PROG_REND_PREV     EQU 0E99Ch  ; 1バイト（直前に出した文字）

; プログラム本体（可変長レコード列、行番号昇順）。1レコード=
; [行番号2B LE][本文長1B][本文(本文長バイト)]。行番号=0xFFFFのレコードは
; 「以降レコード無し」を示す番兵（本文フィールドは持たない、2バイトのみ）。
PROGRAM_AREA       EQU 0EA00h
PROGRAM_AREA_SIZE  EQU 0400h   ; 1024バイト。E969-E97Fの空き・E980台の
                                ; 作業領域より十分離し、スタック(SP=F000、
                                ; make_ipl_rom.py)との間に512バイトの
                                ; 余裕を残す（仕様書に無い判断、報告参照）。

; ---------------------------------------------------------------------
; PROGRAM_INIT — 起動時に1回呼ぶ（screen.asm SCREEN_MAINから）。
;   プログラム領域を空（番兵のみ）にする。未初期化のまま読まない
;   （6dbd1dbの教訓どおり）。
; ---------------------------------------------------------------------
PROGRAM_INIT:
    CALL PROGRAM_CLEAR
    RET

; PROGRAM_CLEAR — プログラム領域を空にする（`NEW`本体）。
PROGRAM_CLEAR:
    LD HL,PROGRAM_AREA
    LD (HL),0FFh
    INC HL
    LD (HL),0FFh
    RET

; ---------------------------------------------------------------------
; BASIC_HANDLE_LINE — keyboard.asm LINE_FINISH から、改行直後（桁0）に
;   呼ばれる新しい入口。LINE_BUF/VAR_LINELENを見て、
;     - 空行、または先頭が数字でない行 … 従来の直接モード
;       (BASIC_RUN_DIRECT、旧BASIC_RUN_LINEの中身)を実行する
;     - 先頭が数字('0'-'9')の行 … 行番号つきの行として解釈を試みる。
;       解釈できれば保存するだけで実行しない（第1節：無出力）。
;       行番号として解釈できない場合（桁過多・65529超）は直接モードに
;       フォールバックする（Syntax errorになる、ヘッダコメント参照）。
;   出力: A=1のとき「無出力」（呼び出し元はOkを出さない）、
;         A=0のとき従来どおり（呼び出し元がOkの要否を判断する）。
; ---------------------------------------------------------------------
BASIC_HANDLE_LINE:
    LD A,(VAR_LINELEN)
    OR A
    JR Z,_bhl_direct
    LD HL,LINE_BUF
    LD A,(HL)
    CP '0'
    JR C,_bhl_direct
    CP '9'+1
    JR NC,_bhl_direct
    CALL PARSE_LINENUM
    JR C,_bhl_direct          ; 行番号として解釈できない -> 直接モードへ
    CALL PROGRAM_STORE_LINE
    LD A,1
    RET
_bhl_direct:
    CALL BASIC_RUN_DIRECT
    ; SAVEの成功フラグは通信完了判定用。直接モードは通常のOkへ戻る。
    XOR A
    LD (SAVE_DONE_FLAG),A
    RET

; ---------------------------------------------------------------------
; PARSE_LINENUM — LINE_BUF先頭の数字列を10進数として読む
;   （呼び出し元はLINE_BUF[0]が'0'-'9'であることを保証済み）。
;   出力: CF=0のとき成功、HL=値(0-65529)、B=消費した桁数(1以上)。
;         CF=1のとき失敗（桁数が無い、または65529を超える）。
;   破壊: AF,BC,DE,HL。
; ---------------------------------------------------------------------
PARSE_LINENUM:
    LD HL,0
    LD B,0                       ; B=消費した桁数
    LD A,(VAR_LINELEN)
    LD C,A                       ; C=行の長さ(上限)
    PUSH IX
    LD IX,LINE_BUF
_pln_loop:
    LD A,B
    CP C
    JR Z,_pln_finish
    LD A,(IX+0)
    CP '0'
    JR C,_pln_finish
    CP '9'+1
    JR NC,_pln_finish
    SUB '0'
    LD E,A
    LD D,0
    LD (PROG_DIGIT),DE           ; 桁の値(0-9)を保存
    LD (PROG_TMP16),HL           ; 元の値(倍率5の計算に使う)を保存
    ADD HL,HL                    ; *2
    JR C,_pln_ovfl
    ADD HL,HL                    ; *4
    JR C,_pln_ovfl
    LD DE,(PROG_TMP16)
    ADD HL,DE                    ; *5
    JR C,_pln_ovfl
    ADD HL,HL                    ; *10
    JR C,_pln_ovfl
    LD DE,(PROG_DIGIT)
    ADD HL,DE                    ; +桁の値
    JR C,_pln_ovfl
    INC IX
    INC B
    JR _pln_loop
_pln_finish:
    LD A,B
    OR A
    JR Z,_pln_ovfl                ; 桁が1つも読めなかった(呼び出し元の前提が
                                   ; 崩れている場合の保険)
    LD DE,65530
    CALL CP_HL_DE                 ; CF=1: HL<65530 (=HL<=65529、成功)
    JR NC,_pln_ovfl
    POP IX
    OR A                          ; CF=0
    RET
_pln_ovfl:
    POP IX
    SCF
    RET

; ---------------------------------------------------------------------
; PROGRAM_LOCATE — PROG_CUR_LINENOと同じ行番号のレコードを探す。
;   出力: HL=一致したレコードの先頭(A=1)、または挿入すべき位置
;         (行番号がPROG_CUR_LINENOより大きい最初のレコードの先頭、
;         無ければ番兵の位置。A=0)。
;   破壊: AF,BC,DE,HL。
; ---------------------------------------------------------------------
PROGRAM_LOCATE:
    LD HL,PROGRAM_AREA
_ploc_loop:
    LD E,(HL)
    INC HL
    LD D,(HL)
    DEC HL                        ; DE=このレコードの行番号、HLは先頭のまま
    LD A,D
    CP 0FFh
    JR NZ,_ploc_have
    LD A,E
    CP 0FFh
    JR Z,_ploc_notfound           ; 番兵(0xFFFF) -> ここが挿入位置
_ploc_have:
    LD A,(PROG_CUR_LINENO)
    CP E
    JR NZ,_ploc_cmp_hi
    LD A,(PROG_CUR_LINENO+1)
    CP D
    JR Z,_ploc_found
_ploc_cmp_hi:
    ; DE(このレコードの行番号) と PROG_CUR_LINENO を比較する。
    ; DE > 対象 なら、ここが挿入位置(まだ見つかっていない)。
    PUSH HL
    LD HL,(PROG_CUR_LINENO)
    CALL CP_HL_DE                 ; CF=1: 対象(HL) < DE
    POP HL
    JR C,_ploc_notfound            ; 対象より大きい行番号が先に出た -> 挿入位置
    ; 次のレコードへ
    PUSH HL
    INC HL
    INC HL
    LD A,(HL)                      ; 本文長
    POP HL
    LD C,A
    LD B,0
    INC BC
    INC BC
    INC BC                          ; BC=レコード全体のサイズ
    ADD HL,BC
    JR _ploc_loop
_ploc_found:
    XOR A
    LD A,1
    RET
_ploc_notfound:
    XOR A
    RET

; ---------------------------------------------------------------------
; PROGRAM_FIND_END — 番兵(0xFFFF)の位置を返す。
;   出力: HL=番兵の先頭。破壊: AF,BC,DE,HL。
; ---------------------------------------------------------------------
PROGRAM_FIND_END:
    LD HL,PROGRAM_AREA
_pfe_loop:
    LD E,(HL)
    INC HL
    LD D,(HL)
    DEC HL
    LD A,D
    CP 0FFh
    JR NZ,_pfe_next
    LD A,E
    CP 0FFh
    JR Z,_pfe_done
_pfe_next:
    PUSH HL
    INC HL
    INC HL
    LD A,(HL)
    POP HL
    LD C,A
    LD B,0
    INC BC
    INC BC
    INC BC
    ADD HL,BC
    JR _pfe_loop
_pfe_done:
    RET

; ---------------------------------------------------------------------
; PROGRAM_DELETE_AT — HL=削除するレコードの先頭。以降のレコード
;   (番兵含む)を前に詰める。破壊: AF,BC,DE,HL。
; ---------------------------------------------------------------------
PROGRAM_DELETE_AT:
    LD (PROG_DEL_DST),HL
    PUSH HL
    INC HL
    INC HL
    LD A,(HL)                      ; 本文長
    POP HL
    LD C,A
    LD B,0
    INC BC
    INC BC
    INC BC                          ; BC=削除するレコードのサイズ
    ADD HL,BC
    LD (PROG_DEL_SRC),HL            ; コピー元開始=削除対象の直後
    CALL PROGRAM_FIND_END
    INC HL
    INC HL                          ; HL=番兵の直後(=既存データの終端)
    LD DE,(PROG_DEL_SRC)
    OR A
    SBC HL,DE                       ; HL=コピーする長さ(番兵2バイトを含む)
    LD B,H
    LD C,L
    LD A,B
    OR C
    JR Z,_pda_done
    LD HL,(PROG_DEL_SRC)
    LD DE,(PROG_DEL_DST)
    LDIR
_pda_done:
    RET

; ---------------------------------------------------------------------
; PROGRAM_INSERT_AT — HL=挿入位置。PROG_CUR_LINENO・PROG_CUR_TEXTLEN・
;   (LINE_BUF+PROG_CUR_LNLEN)から新しいレコードを作り、既存データを
;   後ろにずらしてから書き込む。空き容量が足りなければ何もしない
;   （ヘッダコメント「仕様書に無い判断」参照）。破壊: AF,BC,DE,HL。
; ---------------------------------------------------------------------
PROGRAM_INSERT_AT:
    LD (PROG_INS_AT),HL
    LD A,(PROG_CUR_TEXTLEN)
    LD C,A
    LD B,0
    INC BC
    INC BC
    INC BC                          ; BC=新レコードのサイズ(本文長+3)
    LD (PROG_INS_SIZE),BC
    ; 空き容量確認: 使用量(番兵含まず) + 新レコード + 番兵2B <= 領域サイズ
    CALL PROGRAM_FIND_END
    LD DE,PROGRAM_AREA
    OR A
    SBC HL,DE                       ; HL=現在の使用バイト数(番兵含まず)
    LD DE,(PROG_INS_SIZE)
    ADD HL,DE
    LD DE,2
    ADD HL,DE
    LD DE,PROGRAM_AREA_SIZE
    CALL CP_HL_DE                   ; CF=1: 必要量 < 領域サイズ(収まる)
    JR NC,_pia_full
    ; 後ろにずらす: [挿入位置 .. 現データ終端(番兵含む)) を
    ; 新レコードサイズぶん後方へコピー(LDDR、末尾から)。
    ; 注意: PROGRAM_FIND_ENDはBCを破壊するため、長さ計算(BC)を保持した
    ; まま2回目を呼ぶと壊れる(過去に実際に踏んだ不具合、報告参照)。
    ; 1回の呼び出しの結果(現データ終端)をスタックに退避して使い回す。
    CALL PROGRAM_FIND_END
    INC HL
    INC HL                          ; HL=現データ終端(番兵の直後)
    LD DE,(PROG_INS_AT)
    PUSH HL                         ; 現データ終端を退避
    OR A
    SBC HL,DE                       ; HL=移動する長さ
    LD B,H
    LD C,L
    LD A,B
    OR C
    JR NZ,_pia_do_shift
    POP HL                          ; 使わない(スタック整合のためだけに回収)
    JR _pia_no_shift                ; 長さ0=末尾への追加、シフト不要
_pia_do_shift:
    ; 移動元最終バイト = 現データ終端-1、移動先最終バイト = それ+新サイズ
    POP HL                           ; HL=現データ終端(退避したもの)
    DEC HL                           ; HL=現データ終端-1(=移動元の最終バイト)
    LD (PROG_TMP_SRC_LAST),HL
    LD DE,(PROG_INS_SIZE)
    ADD HL,DE
    LD (PROG_TMP_DST_LAST),HL
    LD HL,(PROG_TMP_SRC_LAST)
    LD DE,(PROG_TMP_DST_LAST)
    LDDR
_pia_no_shift:
    ; ヘッダを書く
    LD HL,(PROG_INS_AT)
    LD DE,(PROG_CUR_LINENO)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD A,(PROG_CUR_TEXTLEN)
    LD (HL),A
    INC HL
    LD (PROG_TMP_DST2),HL           ; 本文の書き込み先
    LD A,(PROG_CUR_TEXTLEN)
    OR A
    JR Z,_pia_full                  ; 本文長0なら書くものが無い(削除扱いの
                                     ; 呼び出しは行われない設計だが保険)
    LD HL,LINE_BUF
    LD A,(PROG_CUR_LNLEN)
    LD E,A
    LD D,0
    ADD HL,DE                       ; HL=LINE_BUF+行番号の桁数(=本文の先頭)
    LD DE,(PROG_TMP_DST2)
    LD A,(PROG_CUR_TEXTLEN)
    LD C,A
    LD B,0
    LDIR
_pia_full:
    RET

; ---------------------------------------------------------------------
; PROGRAM_STORE_LINE — 行番号つきの行を保存する（BASIC_HANDLE_LINEから、
;   PARSE_LINENUMが成功した直後に呼ばれる。HL=行番号、B=桁数が入力）。
;   本文長0(行番号だけ) -> 既存があれば削除、無ければ何もしない。
;   本文長>0 -> 既存があれば削除してから挿入(=置換)、無ければ挿入。
;   いずれも画面には一切出力しない（第1節）。破壊: AF,BC,DE,HL,IX。
; ---------------------------------------------------------------------
PROGRAM_STORE_LINE:
    LD (PROG_CUR_LINENO),HL
    LD A,B
    LD (PROG_CUR_LNLEN),A
    LD A,(VAR_LINELEN)
    SUB B
    LD (PROG_CUR_TEXTLEN),A
    OR A
    JR NZ,_psl_have_text
    ; 本文長0 -> 削除のみ
    CALL PROGRAM_LOCATE
    OR A
    RET Z                          ; 見つからなければ何もしない
    JP PROGRAM_DELETE_AT
_psl_have_text:
    CALL PROGRAM_LOCATE
    OR A
    JR Z,_psl_insert
    CALL PROGRAM_DELETE_AT
_psl_insert:
    CALL PROGRAM_LOCATE            ; 削除後(または初めから無い場合)の
                                    ; 挿入位置を求め直す
    JP PROGRAM_INSERT_AT

; ---------------------------------------------------------------------
; NEW_STMT / LIST_STMT — 直接モードの文（DIRECT_LINEから、
;   MATCH_STMT_KEYWORDがSTMT_KIND=2/1を返した直後に呼ばれる）。
;   どちらも引数を取らない(l4-program.md 第5節5「範囲指定」は未確定の
;   ため、この版では引数付きはSyntax errorにする)。
; ---------------------------------------------------------------------
NEW_STMT:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,_l4new_ok
    CP ':'
    JR Z,_l4new_ok
    LD A,1
    LD (ERROR_FLAG),A
    RET
_l4new_ok:
    JP PROGRAM_CLEAR

LIST_STMT:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,_l4list_ok
    CP ':'
    JR Z,_l4list_ok
    LD A,1
    LD (ERROR_FLAG),A
    RET
_l4list_ok:
    JP LIST_RENDER_ALL

; ---------------------------------------------------------------------
; LIST_RENDER_ALL — 保存済みの全行を、行番号順に
;   「行番号(前ゼロなし) + 変換済み本文」の形で1行ずつ出す（第2節）。
;   破壊: AF,BC,DE,HL。
; ---------------------------------------------------------------------
LIST_RENDER_ALL:
    LD HL,PROGRAM_AREA
_lra_loop:
    LD E,(HL)
    INC HL
    LD D,(HL)
    DEC HL
    LD A,D
    CP 0FFh
    JR NZ,_lra_have
    LD A,E
    CP 0FFh
    JR Z,_lra_done
_lra_have:
    PUSH HL
    EX DE,HL
    CALL PRINT_UDEC                 ; 行番号(前ゼロ抑制、既存ルーチン流用)
    POP HL
    PUSH HL
    INC HL
    INC HL
    LD A,(HL)                       ; 本文長
    INC HL                          ; HL=本文の先頭
    LD C,A                          ; C=本文の残り長さ
    PUSH HL                         ; PRINT_CHARはHLを作業用に破壊する
                                     ; (screen.asmヘッダ注記)ので退避する
    LD A,' '
    CALL PRINT_CHAR                 ; 行番号の直後は常にちょうど空白1個
                                     ; (仕様書に無い判断。A1/A3/A9(空白1個
                                     ; 打鍵->そのまま)とA2(空白0個打鍵->
                                     ; 1個)を両立させるには、本文先頭の
                                     ; 空白を「区切り」として吸収し常に
                                     ; 1個へ正規化するしかない。第2.1節
                                     ; 「行番号の直後は…打鍵どおりの間隔」
                                     ; はこの正規化後の間隔を指すと解釈
                                     ; した。本文中の2文字目以降の空白
                                     ; (A3の命令語後の空白2個等)は正規化
                                     ; せずそのまま保持する——下のループが
                                     ; 「本文先頭から続く空白だけ」を
                                     ; 読み捨てる設計だからである)
    POP HL                           ; PRINT_CHAR呼び出し前に退避した
                                      ; 本文先頭ポインタを戻す
_lra_skip_lead_sp:
    LD A,C
    OR A
    JR Z,_lra_render
    LD A,(HL)
    CP ' '
    JR NZ,_lra_render
    INC HL
    DEC C
    JR _lra_skip_lead_sp
_lra_render:
    LD A,C
    CALL LIST_RENDER_TEXT
    CALL NEWLINE
    POP HL
    PUSH HL
    INC HL
    INC HL
    LD A,(HL)
    POP HL
    LD C,A
    LD B,0
    INC BC
    INC BC
    INC BC
    ADD HL,BC
    JR _lra_loop
_lra_done:
    RET

; ---------------------------------------------------------------------
; LIST_RENDER_TEXT — HL=本文先頭、A=本文の長さ。小文字で打った語を LIST で
;   大文字にして出す（l4-basic.md「プログラム行の LIST 表示」節。根拠は
;   docs/notes/l4-s5h-round3-results.md「採る規則」。公式ROMの測定723腕）。
;   規則:
;     - 二重引用符の中（閉じが無ければ行末まで）は打鍵どおり
;     - `'` 以降は打鍵どおり
;     - 「名前の連なり」（英字で始まり英数字と . が続く並び）がちょうど
;       REM なら REM にして以降は行末まで打鍵どおり（位置は問わない）、
;       ちょうど DATA なら DATA にして `:`（引用符の外）まで打鍵どおり、
;       `GO TO` / `GO SUB`（空白ちょうど1個、語の直後が名前の文字でない）は
;       GOTO / GOSUB に詰める
;     - `?` は文字列の外ならどこでも PRINT に展開。直後が英数字・.・& なら
;       後ろに空白1個、直前の出力が英数字・. なら前にも空白1個
;     - それ以外の英字はすべて大文字。語の前後に空白は足さない。数字・記号・
;       空白は打鍵どおり
;   数字で始まる並びは数値で、その直後から新しい連なりが始まる。
;   実装しないもの（公式は数値定数を読み直して書き直す等）は
;   docs/notes/l4-s5h-round3-results.md の末尾に列挙してある。
;   状態: PROG_REND_MODE(bit0=引用符の中 bit1=行末まで打鍵どおり
;   bit2=DATA の中)、PROG_REND_INNAME(名前の連なりの途中)、
;   PROG_REND_PREV(直前に出した文字)。
;   破壊: AF,BC,DE,HL。
; ---------------------------------------------------------------------
LIST_RENDER_TEXT:
    LD (PROG_REND_PTR),HL
    LD (PROG_REND_LEN),A
    XOR A
    LD (PROG_REND_MODE),A
    LD (PROG_REND_INNAME),A
    LD (PROG_REND_PREV),A
_lrt_loop:
    LD A,(PROG_REND_LEN)
    OR A
    RET Z
    LD HL,(PROG_REND_PTR)
    LD A,(PROG_REND_MODE)
    LD D,A
    LD A,(HL)
    BIT 1,D
    JR NZ,_lrt_put                  ; 行末まで打鍵どおり
    CP '"'
    JR NZ,_lrt_notq
    LD A,D
    XOR 1
    LD (PROG_REND_MODE),A           ; 引用符の開閉
    XOR A
    LD (PROG_REND_INNAME),A
    LD A,'"'
    JR _lrt_put
_lrt_notq:
    BIT 0,D
    JR NZ,_lrt_put                  ; 引用符の中
    BIT 2,D
    JR Z,_lrt_normal
    CP ':'
    JR NZ,_lrt_put                  ; DATA の中
    LD A,D
    AND 0FBh
    LD (PROG_REND_MODE),A           ; DATA は ':' で終わる
    LD A,':'
    JR _lrt_put
_lrt_put:                           ; A=出す文字。出して1文字進む
    CALL LRT_EMIT
    CALL LRT_ADV1
    JR _lrt_loop
_lrt_normal:
    CP 27h                          ; '
    JR NZ,_lrt_n1
    LD HL,PROG_REND_MODE
    SET 1,(HL)
    LD A,27h
    JR _lrt_put
_lrt_n1:
    CP '?'
    JR Z,_lrt_question
    LD D,A                          ; D=打った文字
    CALL FOLD_UPPER
    CP 'A'
    JR C,_lrt_nonletter
    CP 'Z'+1
    JR NC,_lrt_nonletter
    LD B,A                          ; B=大文字にした英字（以下 PRINT_CHAR を呼ぶまで保つ）
    LD A,(PROG_REND_INNAME)
    OR A
    LD A,B
    JR NZ,_lrt_put                  ; 名前の途中
    ; 名前の連なりの先頭: REM / DATA / GO TO / GO SUB か調べる
    LD HL,LRT_KW
_lrt_kwloop:
    LD A,(HL)
    CP 0FFh
    JR Z,_lrt_namestart
    PUSH AF                         ; 方式ビット
    INC HL
    PUSH HL
    LD DE,(PROG_REND_PTR)
    LD A,(PROG_REND_LEN)
    LD C,A
    CALL LRT_MATCH
    POP HL                          ; 語の先頭（PUSH/POPはフラグを変えない）
    JR Z,_lrt_kwhit
    POP AF
_lrt_kwskip:
    LD A,(HL)
    INC HL
    OR A
    JR NZ,_lrt_kwskip
    JR _lrt_kwloop
_lrt_kwhit:
    LD (PROG_REND_PTR),DE           ; 語の直後へ進める
    LD A,C
    LD (PROG_REND_LEN),A
    CALL LRT_PUTS                   ; 語（大文字）を出す
    POP AF
    LD HL,PROG_REND_MODE
    OR (HL)
    LD (HL),A
    JP _lrt_loop
_lrt_namestart:
    LD A,1
    LD (PROG_REND_INNAME),A
    LD A,B
    JR _lrt_put
_lrt_nonletter:
    LD A,D
    CALL LRT_NAMECH                 ; 英字ではないので、CF=1 は数字か .
    LD A,D
    JR C,_lrt_put                   ; 数字と . は連なりの状態を変えない
    XOR A
    LD (PROG_REND_INNAME),A
    LD A,D
    JR _lrt_put
_lrt_question:
    LD A,(PROG_REND_PREV)
    CALL LRT_NAMECH
    JR NC,_lrt_q1
    LD A,' '
    CALL LRT_EMIT
_lrt_q1:
    LD HL,LRT_W_PRINT
    CALL LRT_PUTS
    XOR A
    LD (PROG_REND_INNAME),A
    LD A,(PROG_REND_LEN)
    CP 2
    JR C,_lrt_q3
    LD HL,(PROG_REND_PTR)
    INC HL
    LD A,(HL)
    CP '&'
    JR Z,_lrt_q2
    CALL LRT_NAMECH
    JR NC,_lrt_q3
_lrt_q2:
    LD A,' '
    CALL LRT_EMIT
_lrt_q3:
    CALL LRT_ADV1
    JP _lrt_loop

; LRT_ADV1 — 1文字進む。
LRT_ADV1:
    LD HL,(PROG_REND_PTR)
    INC HL
    LD (PROG_REND_PTR),HL
    LD HL,PROG_REND_LEN
    DEC (HL)
    RET

; LRT_EMIT — A を出して PROG_REND_PREV に残す。破壊: AF,DE,HL（PRINT_CHAR 準拠）。
LRT_EMIT:
    LD (PROG_REND_PREV),A
    JP PRINT_CHAR

; LRT_PUTS — HL=0終端の語。空白は出さない（"GO TO" -> GOTO）。
LRT_PUTS:
    LD A,(HL)
    OR A
    RET Z
    INC HL
    CP ' '
    JR Z,LRT_PUTS
    PUSH HL
    CALL LRT_EMIT
    POP HL
    JR LRT_PUTS

; LRT_MATCH — HL=0終端の語（大文字、空白は1個ちょうどに一致）、DE=本文、
;   C=本文の残り。語が大文字小文字を区別せず一致し、直後が本文の終端か名前の
;   文字でないときだけ一致。出力: Z=一致（DE,C が語の直後へ進む）／NZ=不一致。
LRT_MATCH:
    LD A,(HL)
    OR A
    JR Z,_lm_end
    LD A,C
    OR A
    JR Z,_lm_fail
    LD A,(DE)
    CALL FOLD_UPPER
    CP (HL)
    JR NZ,_lm_fail
    INC HL
    INC DE
    DEC C
    JR LRT_MATCH
_lm_end:
    LD A,C
    OR A
    RET Z
    LD A,(DE)
    CALL LRT_NAMECH
    JR C,_lm_fail
    XOR A
    RET
_lm_fail:
    OR 1
    RET

; LRT_NAMECH — A が名前の文字（英字・数字・.）なら CF=1。破壊: A。
LRT_NAMECH:
    CP '.'
    JR Z,_ln_yes
    CP '0'
    JR C,_ln_fold
    CP '9'+1
    JR C,_ln_yes
_ln_fold:
    CALL FOLD_UPPER
    CP 'A'
    JR C,_ln_no
    CP 'Z'+1
    RET
_ln_no:
    OR A
    RET
_ln_yes:
    SCF
    RET

; 名前の連なりが語そのものか調べる表。1項目 = 方式ビット(1バイト) + 0終端の語。
; 方式ビットは LIST_RENDER_TEXT の PROG_REND_MODE へ足す（2=行末まで、4=DATA）。
LRT_KW:
    DB 2, "REM", 0
    DB 4, "DATA", 0
    DB 0, "GO TO", 0
    DB 0, "GO SUB", 0
    DB 0FFh
LRT_W_PRINT:
    DB "PRINT", 0
