;
; docs/spec/l4-program.md 4.22（l4-s9n）の観測から独立実装。本体はバンク0（deftype.asmの後ろへ連結）。
; WIDTH（l4-program.md 4.22.2〜4.22.4・5.6、l4-s9n・l4-s9o）・LOCATE・COLOR の本体も置く。
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
    ORG 0x7A60
    JP wb_color                ; MM_FN_AUX=値（run.asm COLOR_STMT）
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

; ---- COLOR の本体（第5.4節）。現在行の属性域20組を (位置0x80,値=引数) で塗り直す。
; 位置0x80は行の終端より後ろ（5.6.2の「区間の終端」が行の外）なので、桁数40でも同じ。
; 自作判断（未測定）: 5.6.2 の「印字した区間ごとの組」（終端桁／40桁は2×終端桁-1）は
; 作らない。効果は呼び出し時点の現在行だけ。
wb_color:
    LD HL,(MM_VAR_ROWBASE)
    LD DE,80
    ADD HL,DE
    LD A,(MM_FN_AUX)
    LD C,A
    LD B,20
wb_cl_loop:
    LD (HL),080h
    INC HL
    LD (HL),C
    INC HL
    DJNZ wb_cl_loop
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
    LD A,C                     ; コンマ欄の改行閾値T=(⌊W÷14⌋-1)×14（80桁56・40桁14）
    CP 80
    LD A,56
    JR Z,wb_wa_zt
    LD A,14
wb_wa_zt:
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
