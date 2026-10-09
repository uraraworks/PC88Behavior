; docs/spec/l4-graphics.md 第1版（l4-s9t の観測）から独立実装。本体はバンク2（bank2.asm の後ろへ連結）。
; 容量計画と共通部の入口は docs/design/graphics-capacity.md。
;
; 置くもの: PSET・PRESET・POINT（文と関数）・SCREEN・CLS の引数。後続の LINE・CIRCLE・PAINT・GET@/PUT@ は
;   同じ共通部（gx_coord 座標の読み取り、gx_plot 点を打つ、gx_getpix 点を読む、gx_color_arg 色の引数）を
;   同じバンクの中から CALL する。
;
; グラフィックVRAMの書き方（自作判断。l4-graphics.md 第2節は「同じ画素が立つことが本質」としている）:
;   公式の書き方（OUT 0x34/0x35。ビットの意味は未測定）は使わず、ポート 0x5C〜0x5E でプレーンを選んで
;   C000〜 を読み書きし、0x5F でメインRAMへ戻す（l1-ipl.md 第5c節: GVRAM0=青・1=赤・2=緑）。
;   選択中は C000〜FFFF がグラフィックVRAMに替わる。CPUスタックも BASIC のRAMも C000〜FFFF にあるので、
;   選択中は「スタックとRAMに触れない」（レジスタだけで完結する）。割り込み（VSYNCハンドラ）がスタックへ
;   積むと壊れるので、選択の前に DI、メインRAMへ戻したあとに EI する。BASIC は定常状態で常に割り込みを
;   許可しており、グラフィックの文を割り込み禁止のまま呼ぶ経路は無い（未条件の EI でよい）。
;   長い塗りつぶし（cls 2・3）は 128 バイトごとに EI で割り込みを通す。
;
; 座標: 範囲外（x>=640・y>=200・負）は何も描かない。LP は座標の組を読み終えた時点で更新する。
; 色: 0〜7（範囲外は ERR 5）。前景は MM_GFX_FG（xor 7 で持つ）、背景は MM_GFX_BG（COLOR の第4・第2引数。widthbeep.asm）。

GX_STEP_KIND EQU 1

    ORG 0x7300
GFX_STMT_ENTRY:
    JP gx_stmt                  ; 文の種別 44=PSET 45=PRESET 46=POINT 47=SCREEN（bank0 gfxhook.asm から）
    ORG 0x7310
GFX_POINT_ENTRY:
    JP gx_point_fn              ; 式の中の POINT( ... の '(' の後ろから（bank0 gfxhook.asm から）
    ORG 0x7320
GFX_CLS_ENTRY:
    JP gx_cls                   ; CLS 文の全体（main run.asm CLS_STMT から）

    ORG 0x7340
; ---- mainの呼び先（窓外中継。IX=呼び先。BANK2_MAIN_CALL_ADDR は bank2.asm）
gx_expect:                      ; A=期待する1文字（空白を挟んでよい）。不一致は ERR 2
    LD IX,GX_EXPECT_ADDR
    JP BANK2_MAIN_CALL_ADDR
GX_EXPECT_ADDR EQU 0x1787
gx_parse_int:                   ; 数値の式を1個読んで DE=整数（四捨五入）。文字列は ERR 13、範囲外は ERR 6
    LD IX,GX_PARSE_INT_ADDR
    JP BANK2_MAIN_CALL_ADDR
GX_PARSE_INT_ADDR EQU 0x1787
gx_set_int:                     ; HL=整数 を式の値（CUR）にする
    LD IX,GX_SET_INT_ADDR
    JP BANK2_MAIN_CALL_ADDR
GX_SET_INT_ADDR EQU 0x1787
gx_text_cls:                    ; テキスト画面の消去（CONSOLEの窓）
    LD IX,GX_TEXT_CLS_ADDR
    JP BANK2_MAIN_CALL_ADDR
GX_TEXT_CLS_ADDR EQU 0x1787

; ---- 終わり方
gx_ok:
    XOR A
    LD (MM_ERROR_FLAG),A
    LD (MM_RUN_CTRL),A
    RET
gx_err2:
    LD A,2
    JR gx_err
gx_err5:
    LD A,5
    JR gx_err
gx_err6:
    LD A,6
    JR gx_err
gx_err22:
    LD A,22
gx_err:
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
    RET
gx_bad:                         ; NZ=誤り
    LD A,(MM_ERROR_FLAG)
    OR A
    RET
gx_at_end:                      ; Z=文の終わり（行末か ':'）
    CALL s2_skip
    CALL s2_peek
    OR A
    RET Z
    CP ':'
    RET
gx_stmt_end:                    ; Z=ここで文が終わってよい（行末・':'・ELSE）。そうでなければ ERR 2 で NZ
    CALL gx_at_end
    RET Z
    AND 0DFh
    CP 'E'
    RET Z
    CALL gx_err2
    OR A
    RET

; ---- 文の入口
gx_stmt:
    LD A,2
    LD (MM_ERROR_KIND),A
    LD A,(MM_RUN_STMT_KIND)
    CP 44
    JR Z,gx_pset
    CP 45
    JR Z,gx_preset
    CP 46
    JR Z,gx_point_stmt
    CP 47
    JP NZ,gx_line               ; 48=LINE（line.asm）
    JP gx_screen

; PSET [STEP](x,y)[,色]。色の省略は前景（COLOR 第4引数。既定7）
gx_pset:
    LD A,(MM_GFX_FG)
    XOR 7
    JR gx_draw
; PRESET [STEP](x,y)[,色]。色の省略は背景（COLOR 第2引数）
gx_preset:
    LD A,(MM_GFX_BG)
gx_draw:
    LD (MM_GFX_TC),A
    CALL gx_coord
    CALL gx_bad
    RET NZ
    CALL gx_color_arg           ; ',' があれば色を MM_GFX_TC へ
    RET NZ
    CALL gx_stmt_end            ; 構文が最後まで正しいときだけ描く
    RET NZ
    LD HL,(MM_GFX_LPX)
    LD DE,(MM_GFX_LPY)
    LD A,(MM_GFX_TC)
    CALL gx_plot
    JP gx_ok

; POINT [STEP](x,y) — 文は LP を動かすだけ
gx_point_stmt:
    CALL gx_coord
    CALL gx_bad
    RET NZ
    JP gx_ok

; 座標のあとの ',色' を読む。',' が無ければ何もしない。返り値 NZ=誤り
; 色は 0〜7（それ以外は ERR 5。', ' だけで色が空なら式の読み取りが ERR 22 か ERR 2）
gx_color_arg:
    CALL s2_skip
    CALL s2_peek
    CP ','
    JR Z,gx_ca_have
    XOR A                       ; Z
    RET
gx_ca_have:
    CALL s2_adv
gx_ca_val:                      ; ',' は読み済み（LINE からも入る）
    CALL gx_parse_int
    CALL gx_bad
    RET NZ
    LD A,D
    OR A
    JR NZ,gx_ca_range
    LD A,E
    CP 8
    JR NC,gx_ca_range
    LD (MM_GFX_TC),A
    XOR A                       ; Z
    RET
gx_ca_range:
    CALL gx_err5
    OR A                        ; NZ
    RET

; 座標 [STEP](x,y) を読んで LP を更新する。誤りは ERROR_FLAG（LP は動かさない）。
; LP の更新は ')' まで読み終えた時点（l4-graphics.md 第4節）。STEP は LP からの相対。
gx_coord:
    CALL s2_skip
    LD IX,gx_step_tab
    CALL k2_match_word
    LD (MM_GFX_STEP),A
    LD A,'('
    CALL gx_expect
    CALL gx_bad
    RET NZ
    CALL gx_parse_int
    CALL gx_bad
    RET NZ
    PUSH DE                     ; x はCPUスタックで持つ（y の式の中の POINT( が MM_GFX_TX/TY を使うため）
    LD A,','
    CALL gx_expect
    CALL gx_bad
    JR NZ,gx_c_drop
    CALL gx_parse_int
    CALL gx_bad
    JR NZ,gx_c_drop
    LD (MM_GFX_TY),DE
    LD A,')'
    CALL gx_expect
    CALL gx_bad
    JR NZ,gx_c_drop
    POP HL
    LD (MM_GFX_TX),HL
    LD A,(MM_GFX_STEP)
    OR A
    JR Z,gx_c_store
    LD HL,(MM_GFX_LPX)
    LD DE,(MM_GFX_TX)
    OR A
    ADC HL,DE
    JP PE,gx_err6               ; 符号付き16bitを超える相対座標は ERR 6（自作判断）
    LD (MM_GFX_TX),HL
    LD HL,(MM_GFX_LPY)
    LD DE,(MM_GFX_TY)
    OR A
    ADC HL,DE
    JP PE,gx_err6
    LD (MM_GFX_TY),HL
gx_c_store:
    LD HL,(MM_GFX_TX)
    LD (MM_GFX_LPX),HL
    LD HL,(MM_GFX_TY)
    LD (MM_GFX_LPY),HL
    RET
gx_c_drop:
    POP DE
    RET
gx_step_tab:
    DB 4,GX_STEP_KIND,"STEP",0

; ---- 画面の番地と点
; HL=x, DE=y（符号付き16bit）→ CF=1 なら範囲外（x>=640・y>=200・負）。
; CF=0 なら HL=グラフィックVRAMの番地（プレーンの先頭 + y*80 + x/8）、B=ビットマスク（x%8==0 が bit7）。A,C,DE を壊す。
; （速さ: y*80 は (y*5)<<4 の加算、x/8 はシフト、マスクは表。高速化の前は y*80 と x%8 を毎回ループで求めていた）
gx_addr:
    LD A,H
    CP 2
    JR C,gx_a_xok               ; x の上位が 0/1 なら 0〜511（負は 0x80 以上なので入らない）
    JR NZ,gx_a_out
    LD A,L
    CP 080h
    JR NC,gx_a_out              ; 512〜639 だけ通す
gx_a_xok:
    LD A,D
    OR A
    JR NZ,gx_a_out
    LD A,E
    CP 200
    JR NC,gx_a_out
    LD B,H
    LD C,L                      ; BC=x
    LD H,D
    LD L,E                      ; HL=y（D=0）
    ADD HL,HL
    ADD HL,HL                   ; y*4
    ADD HL,DE                   ; y*5
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL                   ; y*80
    LD A,C
    AND 7
    LD E,A                      ; E=x%8
    SRL B
    RR C
    SRL B
    RR C
    SRL B
    RR C                        ; x/8
    ADD HL,BC
    LD BC,MM_GVRAM_BASE
    ADD HL,BC
    LD BC,gx_masktab
    LD A,C
    ADD A,E
    LD C,A
    JR NC,gx_a_mt
    INC B
gx_a_mt:
    LD A,(BC)
    LD B,A
    OR A                        ; CF=0
    RET
gx_a_out:
    SCF
    RET
gx_masktab:
    DB 080h,040h,020h,010h,008h,004h,002h,001h
; 色ごとの3プレーン分の埋め値（プレーン0=青・1=赤・2=緑。色のbit p が 1 なら 0FFh）
gx_filltab:
    DB 000h,000h,000h, 0FFh,000h,000h, 000h,0FFh,000h, 0FFh,0FFh,000h
    DB 000h,000h,0FFh, 0FFh,000h,0FFh, 000h,0FFh,0FFh, 0FFh,0FFh,0FFh

; ---- 点列を描く入口（LINE の線・CIRCLE・PAINT が使う）
; 使い方: MM_GFX_TC に色を置き、gx_pt_begin を1回呼ぶ（IX が色の行を指す）。そのあとは
;   gx_pt（HL=番地, B=マスク。番地とマスクは呼び手が進める）か gx_plotxy（HL=x, DE=y。範囲外は何もしない）を何度でも呼んでよい。
;   その間 IX を壊さないこと。グラフィックVRAMの切替（OUT 5C〜5E → 5F）は点ごとに DI〜EI の窓の中で、窓の中はスタックにもRAMにも触れない。
gx_pt_begin:                    ; A,BC,IX,F を壊す
    LD A,(MM_GFX_TC)
    LD C,A
    ADD A,A
    ADD A,C                     ; 色*3
    LD C,A
    LD B,0
    LD IX,gx_filltab
    ADD IX,BC
    RET
; 点を打つ（カラーは色の行で3プレーン、白黒はアクティブページ）。A,F 以外は壊さない
gx_pt:
    LD A,(MM_GFX_MONO)
    OR A
    JR NZ,gx_pt_mono
    DI                          ; ここから EI まで、スタックとRAMに触れない
    OUT (05Ch),A                ; プレーン選択（5C=青 5D=赤 5E=緑。値は何でもよい）
    LD A,(HL)
    XOR (IX+0)
    AND B
    XOR (HL)                    ; (HL) のマスク位置だけ埋め値に替わる
    LD (HL),A
    OUT (05Dh),A
    LD A,(HL)
    XOR (IX+1)
    AND B
    XOR (HL)
    LD (HL),A
    OUT (05Eh),A
    LD A,(HL)
    XOR (IX+2)
    AND B
    XOR (HL)
    LD (HL),A
    OUT (05Fh),A                ; 5F=メインRAMへ戻す
    EI
    RET
gx_pt_mono:                     ; 白黒: アクティブページのプレーンだけ、色が0以外なら立て、0なら消す
    PUSH DE
    PUSH BC
    LD A,(MM_GFX_TC)
    ADD A,0FFh
    SBC A,A
    LD E,A                      ; 埋め値
    LD A,(MM_GFX_APAGE)
    ADD A,05Ch
    LD C,A
    DI
    OUT (C),A
    LD A,(HL)
    XOR E
    AND B
    XOR (HL)
    LD (HL),A
    LD C,05Fh
    OUT (C),A
    EI
    POP BC
    POP DE
    RET
; HL=x, DE=y に打つ（範囲外は何もしない）。gx_pt_begin のあとで使う
gx_plotxy:
    CALL gx_addr
    RET C
    JP gx_pt

; 点を打つ。HL=x, DE=y, A=色(0〜7)。範囲外は何もしない。
; カラー: 3プレーンそれぞれ、色のbitが1なら点を立て、0なら消す。白黒(screen 1): アクティブページのプレーンだけ、色が0以外なら立て、0なら消す。
gx_plot:
    LD (MM_GFX_TC),A
    CALL gx_pt_begin
    JR gx_plotxy

; 点を読む。HL=x, DE=y → A=色(0〜7)、範囲外は 0FFh（-1）。白黒はアクティブページの1/0
gx_getpix:
    CALL gx_addr
    JR C,gx_gp_out
    LD A,(MM_GFX_MONO)
    OR A
    JR NZ,gx_gp_mono
    LD C,05Ch
    LD D,0
    DI
gx_gp_loop:
    OUT (C),A
    LD A,(HL)
    AND B
    ADD A,0FFh                  ; 0以外ならキャリー
    RR D
    INC C
    LD A,C
    CP 05Fh
    JR NZ,gx_gp_loop
    OUT (C),A
    EI
    LD A,D                      ; D=bit7:緑 bit6:赤 bit5:青
    RLCA
    RLCA
    RLCA
    RET
gx_gp_mono:
    LD A,(MM_GFX_APAGE)
    ADD A,05Ch
    LD C,A
    DI
    OUT (C),A
    LD A,(HL)
    AND B
    LD D,A
    LD C,05Fh
    OUT (C),A
    EI
    LD A,D
    OR A
    RET Z
    LD A,1
    RET
gx_gp_out:
    LD A,0FFh
    RET

; 3プレーン全体（各16000バイト）を背景色 A(0〜7) で塗る。プレーン p は A の bit p が 1 なら 0FFh、0 なら 0。
; 128バイトごとに割り込みを通す（DI の間だけスタックとRAMに触れない）。
gx_clear_gfx:
    LD E,A
    LD C,05Ch
gx_cg_plane:
    SRL E
    SBC A,A
    LD D,A
    LD HL,MM_GVRAM_BASE
gx_cg_chunk:
    DI
    OUT (C),A
    LD A,D
    LD B,128
gx_cg_fill:
    LD (HL),A
    INC HL
    DJNZ gx_cg_fill
    OUT (05Fh),A
    EI
    LD A,H
    CP MM_GVRAM_END_HI
    JR C,gx_cg_chunk
    LD A,L
    CP MM_GVRAM_END_LO
    JR C,gx_cg_chunk
    INC C
    LD A,C
    CP 05Fh
    JR NZ,gx_cg_plane
    RET

; ---- 式の中の POINT( ... 。'(' は読み済み。POINT(n) は n=0,2 が LP の X、1,3 が LP の Y（4以上・負は ERR 5）。
; POINT(x,y) は点の色（描いていない範囲内は背景色、範囲外は -1）。LP は動かさない。
gx_point_fn:
    LD A,2
    LD (MM_ERROR_KIND),A
    CALL gx_parse_int
    CALL gx_bad
    RET NZ
    PUSH DE                     ; 最初の値はCPUスタックで持つ（入れ子の POINT( が MM_GFX_TX/TY を使うため）
    CALL s2_skip
    CALL s2_peek
    CP ','
    JR Z,gx_pf_xy
    LD A,')'
    CALL gx_expect
    CALL gx_bad
    JR NZ,gx_pf_drop
    POP HL
    LD A,H
    OR A
    JP NZ,gx_err5
    LD A,L
    CP 4
    JP NC,gx_err5
    AND 1
    LD HL,(MM_GFX_LPX)
    JP Z,gx_set_int
    LD HL,(MM_GFX_LPY)
    JP gx_set_int
gx_pf_xy:
    CALL s2_adv
    CALL gx_parse_int
    CALL gx_bad
    JR NZ,gx_pf_drop
    LD (MM_GFX_TY),DE
    LD A,')'
    CALL gx_expect
    CALL gx_bad
    JR NZ,gx_pf_drop
    POP HL
    LD DE,(MM_GFX_TY)
    CALL gx_getpix
    LD L,A
    LD H,0
    CP 0FFh
    JP NZ,gx_set_int
    DEC H
    JP gx_set_int
gx_pf_drop:
    POP DE
    RET

; ---- CLS [n]。n=省略か1: テキストを消す。2: グラフィックを背景色で塗る(LPを(0,0)へ)。3: 両方。0: 何もしない。
; 4以上・負は ERR 5。小数は四捨五入（1.5→2）。文字列は ERR 13。
gx_cls:
    LD A,2
    LD (MM_ERROR_KIND),A
    XOR A
    LD (MM_ERROR_FLAG),A
    LD (MM_RUN_CTRL),A
    CALL gx_at_end
    LD E,1                      ; 省略は1（gx_at_end が DE を壊すのでその後に置く。LD は Z を変えない）
    JR Z,gx_cls_go
    CALL gx_parse_int
    CALL gx_bad
    RET NZ
    LD A,D
    OR A
    JP NZ,gx_err5
    LD A,E
    CP 4
    JP NC,gx_err5
gx_cls_go:
    LD A,E
    LD (MM_GFX_TC),A
    BIT 1,A
    JR Z,gx_cls_text
    LD A,(MM_GFX_BG)
    CALL gx_clear_gfx
    LD HL,0
    LD (MM_GFX_LPX),HL
    LD (MM_GFX_LPY),HL
gx_cls_text:
    LD A,(MM_GFX_TC)
    AND 1
    JP Z,gx_ok
    CALL gx_text_cls
    JP gx_ok

; ---- SCREEN [モード][,画面スイッチ][,アクティブページ][,ディスプレイページ]
; 範囲は 0〜2・0〜3・0〜2・0〜7（外れは ERR 5）、引数なしは ERR 22、5個以上は ERR 2。
; 全引数を確かめてから反映する（誤りのときは何も変えない）。
;   モード: 0=640x200カラー（0x31 の bit0・bit4 を立てる） 1=白黒（bit0 を立て bit4 を落とす） 2=640x400（bit0・bit4 を落とし 0x53←0xF8）
;   モードを書いた文は LP を (0,0) へ戻す（省略した `screen ,1` は戻さない）。
;   画面スイッチ: 0,1=グラフィック表示（0x31 の bit3 を立てる） 2,3=非表示（落とす）。
;   アクティブページ: 白黒のとき書き込むプレーン。ディスプレイページ d: OUT 0x53 ← 0F0h|((7-d)<<1)。
; 0x31 の値は垂直同期のたびに MM_SCR_P31 から出される（WIDTH と共用）。ここでも即座に出す。
gx_screen:
    XOR A
    LD (MM_GFX_SM),A
    LD (MM_GFX_SI),A
    CALL gx_at_end
    JP Z,gx_err22
gx_sc_loop:
    CALL s2_skip
    CALL s2_peek
    CP ','
    JR Z,gx_sc_next
    OR A
    JR Z,gx_sc_next
    CP ':'
    JR Z,gx_sc_next
    CALL gx_parse_int
    CALL gx_bad
    RET NZ
    LD A,(MM_GFX_SI)
    LD C,A
    LD B,0
    LD A,D
    OR A
    JP NZ,gx_err5
    LD HL,gx_sc_max
    ADD HL,BC
    LD A,(HL)
    CP E
    JP C,gx_err5
    LD HL,MM_GFX_S0
    ADD HL,BC
    LD (HL),E
    LD HL,gx_sc_bit
    ADD HL,BC
    LD A,(MM_GFX_SM)
    OR (HL)
    LD (MM_GFX_SM),A
gx_sc_next:
    CALL s2_skip
    CALL s2_peek
    CP ','
    JR NZ,gx_sc_done
    CALL s2_adv
    LD A,(MM_GFX_SI)
    INC A
    LD (MM_GFX_SI),A
    CP 4
    JP NC,gx_err2
    JR gx_sc_loop
gx_sc_done:
    CALL gx_stmt_end
    RET NZ
    LD A,(MM_SCR_P31)
    LD C,A                      ; C=0x31 に出す値
    LD A,(MM_GFX_SM)
    BIT 0,A
    JR Z,gx_sa_nomode
    LD HL,0
    LD (MM_GFX_LPX),HL
    LD (MM_GFX_LPY),HL
    XOR A
    LD (MM_GFX_MONO),A
    LD A,(MM_GFX_S0)
    OR A
    JR Z,gx_sa_m0
    CP 1
    JR Z,gx_sa_m1
    LD A,C                      ; モード2
    AND 0EEh
    LD C,A
    LD A,0F8h
    OUT (053h),A
    JR gx_sa_nomode
gx_sa_m0:
    LD A,C
    OR 011h
    LD C,A
    JR gx_sa_nomode
gx_sa_m1:
    LD A,C
    OR 001h
    AND 0EFh
    LD C,A
    LD A,1
    LD (MM_GFX_MONO),A
    XOR A
    LD (MM_GFX_APAGE),A
gx_sa_nomode:
    LD A,(MM_GFX_SM)
    BIT 2,A
    JR Z,gx_sa_nopage
    LD A,(MM_GFX_S2)
    LD (MM_GFX_APAGE),A
gx_sa_nopage:
    LD A,(MM_GFX_SM)
    BIT 1,A
    JR Z,gx_sa_nosw
    LD A,C
    OR 008h
    LD C,A
    LD A,(MM_GFX_S1)
    CP 2
    JR C,gx_sa_nosw
    LD A,C
    AND 0F7h
    LD C,A
gx_sa_nosw:
    LD A,C
    LD (MM_SCR_P31),A
    OUT (031h),A
    LD A,(MM_GFX_SM)
    BIT 3,A
    JP Z,gx_ok
    LD A,(MM_GFX_S3)
    LD B,A
    LD A,7
    SUB B
    ADD A,A
    OR 0F0h
    OUT (053h),A
    JP gx_ok
gx_sc_max:
    DB 2,3,2,7
gx_sc_bit:
    DB 1,2,4,8
