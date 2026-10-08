;
; docs/spec/l4-program.md 4.22（l4-s9n）の観測から独立実装。本体はバンク0（deftype.asmの後ろへ連結）。
; WIDTH（l4-program.md 4.22.2〜4.22.4・5.6、l4-s9n・l4-s9o）・LOCATE・COLOR（5.4・5.6.2、l4-s9p）の本体も置く。
; ポート0x40は書き込み専用で読み戻せない（IN 0x40 は別の意味。l1-ipl.md のポート表）。
; そこで他のビット（b0〜b4）は、起動処理（l1-ipl.md 付録A）が最後に書く値 0x01 のまま保つ
; 定数にし、bit5（BEEP）だけを 0x21（鳴る）と 0x01（止める）で動かす。
; 未測定・自作判断: 他のビットは0x01を保つ（測定では窓内で動かなかったことだけが分かる）。
;   音の長さ（立ち上がりから立ち下がりまで）は約 0.1 秒（4MHz）の待ち。
;   BEL(CHR$(7))の出力は何も表示せずカーソルも動かさず、BEEP と同じ音だけ鳴らす。
;   誤りの音はメッセージの前。ERR 11（0除算）は鳴らさない（直接モードの print 1/0 の観測。
;   プログラム中・他の式の0除算は未測定でここと同じ扱い）。
;   BEEP n の n は 0〜255 の整数（範囲外は ERR 5、数値の溢れも ERR 5、文字列は ERR 13）。
;   引数の小数・3〜255 は未測定で、四捨五入した値が0以外なら鳴らし続ける。

WB_PORT EQU 040h
WB_OFF EQU 001h
WB_ON EQU 021h

; ---- mainからの固定入口（deftype.asmの後ろ）。引数はRAM（MM_FN_AUX）で渡す
    ORG 0x7A40
    JP wb_bell
    ORG 0x7A50
    JP wb_locate               ; MM_FN_AUX=桁x、MM_FN_AUX+1=行y（run.asm LOCATE_STMT）
    ORG 0x7A54
    JP wb_attr                 ; 印字したセルの色を属性域へ（screen.asm PRINT_CHAR）
    ORG 0x7A60
    JP wb_color_stmt           ; COLOR 文の全体（run.asm COLOR_STMT）
    ORG 0x7A70

; BEEP（文の種別41、第4.22.6節）。引数なし=鳴らして止める、BEEP n=nが0以外なら立てたまま・0なら下げる
wb_beep_stmt:
    CALL fn_skip
    CALL fn_peek
    OR A
    JR Z,wb_plain
    CP ':'
    JR Z,wb_plain
    CALL fn_is_string
    OR A
    JP NZ,fn_type
    CALL fn_expr
    CALL fn_bad
    RET NZ
    CALL fn_int
    OR A
    JP Z,fn_illegal
    LD A,D
    OR A
    JP NZ,fn_illegal
    LD A,E
    OR A
    LD A,WB_OFF
    JR Z,wb_write
    LD A,WB_ON
wb_write:
    OUT (WB_PORT),A
    JP fn_ok
wb_plain:
    CALL wb_bell
    JP fn_ok

; 引数なしのBEEPと誤り表示の音・BELの出力: bit5を立て、一定時間のあと下げる
wb_bell:
    LD A,WB_ON
    OUT (WB_PORT),A
    LD BC,04000h
wb_wait:
    DEC BC
    LD A,B
    OR C
    JR NZ,wb_wait
    LD A,WB_OFF
    OUT (WB_PORT),A
    RET

; ---- LOCATE の本体（第5.2節）。桁・行は現在のWIDTHの範囲へ丸める（範囲外は最大値。
; 4.22.5 は範囲外でも誤りにならないことだけを観測しているので、丸めは自作判断）。
; 行は最終の使用行(MM_SCR_MAXROW。ファンクションキー行を除く)まで。
wb_locate:
    LD A,(MM_SCR_COLS)
    LD B,A
    LD A,(MM_FN_AUX)
    CP B
    JR C,wb_lc_col
    LD A,B
    DEC A
wb_lc_col:
    LD (MM_VAR_COL),A
    LD A,(MM_SCR_MAXROW)
    LD B,A
    LD A,(MM_FN_AUX+1)
    CP B
    JR C,wb_lc_row
    LD A,B
wb_lc_row:
    LD (MM_VAR_ROW),A
    LD HL,MM_TEXT_BASE
    OR A
    JR Z,wb_lc_base
    LD B,A
    LD DE,120
wb_lc_mul:
    ADD HL,DE
    DJNZ wb_lc_mul
wb_lc_base:
    LD (MM_VAR_ROWBASE),HL
    RET

; ---- COLOR（第5.4節）。書式: COLOR [n][,[第2引数][,[第3引数][,[第4引数]]]]。
; 受理範囲と誤り（l4-s9p の観測）: n は 0〜7（小数は四捨五入）、範囲外=ERR 5、文字列=ERR 13、
; 引数なし・「,」で終わる=ERR 22、第5引数=ERR 2。第1引数が省略（COLOR ,3）なら色は変えない。
; 誤りのときは色を変えない（文末まで確かめてから設定する）。
; 第5.4.4節（l4-s9q の観測）: 第2・第4引数は 0〜7、第3引数は 0 だけを受理し、他は ERR 5。
; 省略した引数は検査しない。受理された COLOR はポート 0x54 へ必ず2回書く（第2引数 b、省略時0）:
;   1回目 = 0x80 | (b bit0 なら 0x07) | (b bit1 なら 0x38)、2回目 = 0xC0 | (b bit2 なら 0x07)。
;   第3・第4引数はポートに出ない。誤りの COLOR は書かない（文末まで確かめてから書く）。
; 現在の色は MM_SCR_ZT の上位3bit。作業値は MM_FN_AUX（+0=第1引数、0xFFは省略。
;   +1=下位2bit が引数番号、bit2〜4 が第2引数 b）。
wb_color_stmt:
    LD A,0FFh
    LD (MM_FN_AUX),A
    XOR A
    LD (MM_FN_AUX+1),A
wb_c_arg:
    CALL fn_skip
    CALL fn_peek
    CP ','
    JR Z,wb_c_sep              ; この引数は省略されている
    OR A
    JP Z,wb_c_missing
    CP ':'
    JP Z,wb_c_missing
    CALL fn_is_string
    OR A
    JR Z,wb_c_num
    JP fn_type
wb_c_num:
    CALL wb_wn_num             ; A=1成功（DE=四捨五入した整数）、A=0失敗（誤りは設定済み）
    OR A
    RET Z
    LD A,D
    OR A
    JP NZ,wb_c_range
    LD A,(MM_FN_AUX+1)
    AND 3
    CP 2
    LD A,E
    JR NZ,wb_c_r7
    OR A
    JP NZ,wb_c_range           ; 第3引数は 0 だけ
    JR wb_c_sep
wb_c_r7:
    CP 8
    JP NC,wb_c_range
    LD C,A
    LD A,(MM_FN_AUX+1)
    AND 3
    JR Z,wb_c_first
    CP 1
    JR NZ,wb_c_sep             ; 第4引数は検査だけ
    LD A,C                     ; 第2引数 b を bit2〜4 へ
    ADD A,A
    ADD A,A
    LD HL,MM_FN_AUX+1
    OR (HL)
    LD (HL),A
    JR wb_c_sep
wb_c_first:
    LD A,C
    LD (MM_FN_AUX),A           ; 第1引数
wb_c_sep:
    CALL fn_skip
    CALL fn_peek
    CP ','
    JR NZ,wb_c_fin
    LD A,(MM_FN_AUX+1)
    AND 3
    CP 3
    JP NC,fn_syntax            ; 第5引数（値の検査は済んだあと）
    LD HL,MM_FN_AUX+1
    INC (HL)
    CALL fn_adv
    JR wb_c_arg
wb_c_fin:
    CALL wb_w_at_end
    JP NZ,fn_syntax
    LD A,(MM_FN_AUX+1)         ; ポート 0x54 へ2回（5.4.4）
    RRCA
    RRCA
    AND 7
    LD B,A
    LD A,080h
    BIT 0,B
    JR Z,wb_c_p1
    OR 007h
wb_c_p1:
    BIT 1,B
    JR Z,wb_c_p2
    OR 038h
wb_c_p2:
    OUT (054h),A
    LD A,0C0h
    BIT 2,B
    JR Z,wb_c_p3
    OR 007h
wb_c_p3:
    OUT (054h),A
    LD A,(MM_FN_AUX)
    CP 0FFh
    JP Z,fn_ok                 ; 第1引数なし: 色は変えない
    RRCA                       ; n(0〜7)を bit5〜7 へ
    RRCA
    RRCA
    AND 0E0h
    LD B,A
    LD A,(MM_SCR_ZT)
    AND 01Fh
    OR B
    LD (MM_SCR_ZT),A
    JP fn_ok
wb_c_missing:
    LD A,22
    JP fn_error
wb_c_range:
    JP fn_illegal

; ---- 印字したセルの色を属性域の組へ反映する（PRINT_CHAR から。第5.6.2節）。
; 行の属性域は 20組×(位置,値)。組 k は区間 [組k-1の終端, 組kの終端) の値（先頭の区間は桁0から）。
; 位置は終端桁（80桁）／2×終端桁-1（40桁）。位置0x80は「ここから先すべて」（尾）。組19は常に尾。
; VAR_COL のセル（PRINT_CHAR が書いたばかり）を現在の色 v にする:
;  1. 色0で組が無い行は何もしない（COLOR 0 だけの行は全組 (0x80,0)）。
;  2. セルが入る区間 i（終端 > 桁 の最初の組）の値 w が v に等しければ変更なし。
;     ただし値0の尾は「まだ書いていない」ので、その先頭に有限の区間を作る（別の色の後の値0の区間）。
;  3. 区間 i を [始点,桁)=w・[桁,桁+1)=v・[桁+1,終端)=w に割る（空の区間は作らない）。
;     組を右へずらして挿入し、組19が尾でなくなったら (0x80,v) にする（20区間以上: 20組目は最後の区間の値）。
;  4. 隣り合う有限の組で値が同じものは1つにまとめる（上書きで区間が組み直される）。
; 破壊: AF,BC,DE,HL。
wb_attr:
    CALL wa_getv
    LD E,A                     ; E = v
    LD HL,(MM_VAR_ROWBASE)
    LD BC,80
    ADD HL,BC                  ; HL = 組0
    LD A,E
    OR A
    JR NZ,wa_start
    BIT 7,(HL)
    RET NZ
wa_start:
    LD A,(MM_VAR_COL)
    LD C,A                     ; C = 桁
    LD D,0                     ; D = 区間の始点
    LD B,0                     ; B = 組の番号
wa_find:
    CALL wa_dec
    CP C
    JR Z,wa_next
    JR NC,wa_found
wa_next:
    LD D,A
    INC HL
    INC HL
    INC B
    LD A,B
    CP 19
    JR C,wa_find
wa_found:
    INC HL
    LD A,(HL)                  ; A = w
    DEC HL
    CP E
    JR NZ,wa_split
    OR A
    RET NZ                     ; w = v ≠ 0
    BIT 7,(HL)
    RET Z                      ; 有限の区間で w = v = 0
wa_split:
    PUSH AF                    ; w
    CALL wa_dec                ; A = 終端
    SUB C
    CP 1
    JR Z,wa_noc                ; 終端 = 桁+1: 後ろの w の区間は無い
    LD A,C
    INC A
    CALL wa_enc
    CALL wa_ins                ; [桁,桁+1)=v を組 i に挿入（元の組は組 i+1 になる）
    JR wa_a
wa_noc:
    INC HL
    LD (HL),E                  ; 組 i の値だけを v にする（位置はそのまま）
    DEC HL
wa_a:
    POP AF
    LD E,A                     ; E = w
    LD A,C
    CP D
    JR Z,wa_norm               ; 始点 = 桁: [始点,桁) は空
    CALL wa_enc
    CALL wa_ins                ; [始点,桁)=w
wa_norm:
    LD A,19
    SUB B
    ADD A,A
    LD E,A
    LD D,0
    ADD HL,DE                  ; HL = 組19
    LD A,(HL)
    CP 080h
    JR Z,wa_compact
    LD (HL),080h               ; 20区間以上: 20組目は (0x80, 最後の区間の値)
    INC HL
    CALL wa_getv
    LD (HL),A
wa_compact:
    LD HL,(MM_VAR_ROWBASE)
    LD DE,80
    ADD HL,DE
    LD B,18
wc_loop:
    LD A,(HL)
    CP 080h
    RET Z
    INC HL
    LD D,(HL)                  ; D = 組kの値
    INC HL
    LD A,(HL)
    CP 080h
    RET Z                      ; 次が尾: まとめない
    INC HL
    LD A,(HL)                  ; 組k+1の値
    DEC HL                     ; HL = 組k+1
    CP D
    JR NZ,wc_next
    PUSH HL                    ; 同じ値: 組kを消す（組k+1以降を1組左へ。組19は (0x80,0)）
    LD A,B
    INC A
    ADD A,A
    LD C,A
    LD B,0
    LD D,H
    LD E,L
    DEC DE
    DEC DE
    LDIR
    DEC HL
    LD (HL),0
    DEC HL
    LD (HL),080h
    POP HL
    JR wa_compact
wc_next:
    DJNZ wc_loop
    RET

; 現在の色（MM_SCR_ZT の上位3bit）→ A
wa_getv:
    LD A,(MM_SCR_ZT)
    RLCA
    RLCA
    RLCA
    AND 7
    RET

; (HL)=位置バイト → A=終端桁（論理）。0x80は255。BC,DE,HL保存。
wa_dec:
    LD A,(HL)
    CP 080h
    JR NZ,wa_d1
    LD A,0FFh
    RET
wa_d1:
    PUSH BC
    LD B,A
    LD A,(MM_SCR_COLS)
    CP 80
    LD A,B
    POP BC
    RET Z
    INC A                      ; 40桁: 位置 = 2×終端桁-1
    SRL A
    RET

; A=終端桁（論理）→ A=位置バイト（80桁はそのまま、40桁は 2×終端桁-1）。BC,DE,HL保存。
wa_enc:
    PUSH BC
    LD B,A
    LD A,(MM_SCR_COLS)
    CP 80
    LD A,B
    POP BC
    RET Z
    ADD A,A
    DEC A
    RET

; 組 i（HL、番号B）に (A, E) を挿入する。組 i〜18 を1組右へずらす（組19の元の内容は捨てる）。BC,DE,HL保存。
wa_ins:
    PUSH BC
    PUSH DE
    PUSH HL
    PUSH AF
    LD A,19
    SUB B
    JR Z,wi_w
    ADD A,A
    LD C,A
    LD B,0
    ADD HL,BC
    LD D,H
    LD E,L
    INC DE
    DEC HL
    LDDR
wi_w:
    POP AF
    POP HL
    POP DE
    LD (HL),A
    INC HL
    LD (HL),E
    DEC HL
    POP BC
    RET

; ---- WIDTH（文の種別42。l4-program.md 4.22.2〜4.22.4・5.6）
; 書式: WIDTH 桁[,行] ／ WIDTH LPRINT 数。桁は40か80、行は20か25（式・小数は四捨五入）。
; 誤りは何も変えない（引数を全部読み、文末まで確かめてから適用する）:
;   引数なし・「桁,」の行の欠け=ERR 22、桁の省略（WIDTH ,20）・文字列・余分な引数=ERR 2、
;   範囲外（桁40/80以外・行20/25以外）=ERR 5。
; 受理されたら（現在と同じ指定でも）5.6.5の順にポート・CRTC・DMACへ書き、3000バイト全体を
; 消してカーソルを先頭へ戻す。WIDTH LPRINT は装置幅の指定で画面に触れない（受理するだけ）。
; 未測定・自作判断: LPRINTの幅の範囲は見ない。ファンクションキー行は自作ROMでは何も出さない。
; 作業値は MM_FN_AUX（+0=桁、+1=行）。
wb_width_stmt:
    CALL ts_skip
    CALL ts_peek
    OR A
    JR Z,wb_w_missing
    CP ':'
    JR Z,wb_w_missing
    CP ','
    JP Z,fn_syntax
    LD HL,wb_w_lprint
    CALL ts_kw
    OR A
    JR NZ,wb_w_lp
    CALL wb_w_num
    OR A
    RET Z
    LD A,D
    OR A
    JR NZ,wb_w_range
    LD A,E
    CP 40
    JR Z,wb_w_cols
    CP 80
    JR NZ,wb_w_range
wb_w_cols:
    LD (MM_FN_AUX),A
    LD A,(MM_SCR_MAXROW)       ; 行の省略は現在の行数のまま
    ADD A,2
    LD (MM_FN_AUX+1),A
    CALL ts_skip
    CALL ts_peek
    CP ','
    JR NZ,wb_w_end
    CALL ts_adv
    CALL ts_skip
    CALL ts_peek
    OR A
    JR Z,wb_w_missing
    CP ':'
    JR Z,wb_w_missing
    CALL wb_w_num
    OR A
    RET Z
    LD A,D
    OR A
    JR NZ,wb_w_range
    LD A,E
    CP 20
    JR Z,wb_w_rows
    CP 25
    JR NZ,wb_w_range
wb_w_rows:
    LD (MM_FN_AUX+1),A
wb_w_end:
    CALL wb_w_at_end
    JP NZ,fn_syntax
    JR wb_w_apply
wb_w_missing:
    LD A,22
    JP fn_error
wb_w_range:
    JP fn_illegal
wb_w_lp:
    CALL ts_skip
    CALL ts_peek
    OR A
    JR Z,wb_w_missing
    CP ':'
    JR Z,wb_w_missing
    CALL wb_w_num
    OR A
    RET Z
    CALL wb_w_at_end
    JP NZ,fn_syntax
    JP fn_ok

; 数値の式を1つ読む。A=1成功（DE=四捨五入した整数）、A=0失敗（誤りは設定済み）。文字列はERR 2、整数の範囲外はERR 5。
wb_w_num:
    CALL fn_is_string
    OR A
    JR Z,wb_wn_num
    CALL fn_syntax
    XOR A
    RET
wb_wn_num:
    CALL fn_expr
    CALL fn_bad
    JR Z,wb_wn_conv
    XOR A
    RET
wb_wn_conv:
    CALL fn_int
    OR A
    RET NZ
    CALL fn_illegal
    XOR A
    RET

; 文末（行末・':'・ELSE）ならZ。CUR_PTRは動かさない。
wb_w_at_end:
    CALL ts_skip
    CALL ts_peek
    OR A
    RET Z
    CP ':'
    RET Z
    LD HL,(MM_CUR_PTR)
    PUSH HL
    LD HL,wb_w_else
    CALL ts_kw
    POP HL
    LD (MM_CUR_PTR),HL
    DEC A
    RET

wb_w_lprint:
    DB "LPRINT",0
wb_w_else:
    DB "ELSE",0

; 行数ごとの表: ポート0x31の値・DMAC転送長（下位,上位）・CRTC RESETの5パラメータ（5.6.5の手順1・6・7）
wb_w_tab20:
    DB 019h,05Fh,089h,0CEh,093h,073h,038h,013h
wb_w_tab25:
    DB 039h,0B7h,08Bh,0CEh,098h,06Fh,058h,013h

wb_w_apply:
    LD A,(MM_FN_AUX)
    LD (MM_SCR_COLS),A
    LD C,A
    LD A,(MM_FN_AUX+1)
    LD B,A
    SUB 2
    LD (MM_SCR_MAXROW),A
    LD HL,wb_w_tab20
    LD A,B
    CP 25
    JR NZ,wb_wa_tab
    LD HL,wb_w_tab25
wb_wa_tab:
    LD A,(MM_SCR_ZT)           ; 上位3bit（現在の COLOR 値）は保つ
    AND 0E0h
    LD B,A
    LD A,C                     ; コンマ欄の改行閾値T=(⌊W÷14⌋-1)×14（80桁56・40桁14）の半分を下位5bitへ
    CP 80
    LD A,28
    JR Z,wb_wa_zt
    LD A,7
wb_wa_zt:
    OR B
    LD (MM_SCR_ZT),A
    LD A,(HL)                  ; 1: OUT 0x31（20行0x19／25行0x39）。垂直同期ごとに同じ値を出す
    LD (MM_SCR_P31),A
    OUT (0x31),A
    INC HL
    LD A,C                     ; 2: OUT 0x30（80桁0x23／40桁0x22。差はbit0だけ）
    CP 80
    LD A,023h
    JR Z,wb_wa_30
    LD A,022h
wb_wa_30:
    OUT (0x30),A
    XOR A                      ; 3: CRTC RESET
    OUT (0x51),A
    LD A,0A0h                  ; 4: DMAC
    OUT (0x68),A
    LD A,0C8h                  ; 5: DMAアドレス F3C8
    OUT (0x64),A
    LD A,0F3h
    OUT (0x64),A
    LD A,(HL)                  ; 6: 転送長（下位・上位）
    OUT (0x65),A
    INC HL
    LD A,(HL)
    OUT (0x65),A
    INC HL
    LD B,5                     ; 7: CRTC RESETの5パラメータ
wb_wa_crtc:
    LD A,(HL)
    OUT (0x50),A
    INC HL
    DJNZ wb_wa_crtc
    LD A,043h                  ; 8
    OUT (0x51),A
    LD A,0E4h                  ; 9
    OUT (0x68),A
    LD A,020h                  ; 10
    OUT (0x51),A
    LD IX,WB_CLEAR_ADDR        ; 3000バイト全体（25行）を消す（mainのCLEAR_N_ROWS）
    LD HL,MM_TEXT_BASE
    LD B,25
    CALL FN_MAIN_CALL_ADDR
    XOR A                      ; カーソルを先頭（行0桁0）へ
    LD (MM_VAR_ROW),A
    LD (MM_VAR_COL),A
    LD HL,MM_TEXT_BASE
    LD (MM_VAR_ROWBASE),HL
    JP fn_ok

WB_CLEAR_ADDR EQU 0x1787
