; docs/spec/l4-graphics.md 第2版 第9節（l4-s9u の観測）から独立実装。LINE 文。gfx.asm の後ろへ連結する（bank2）。
;
; 形: LINE [[STEP](x1,y1)]-[STEP](x2,y2) [,[色][,[B|BF][,スタイル]]]
; 座標の読み取り・LP の更新・色の検査・点を打つ・番地計算は gfx.asm の共通部を使う。作業値は memmap の LINE_WORK。
;
; 線の画素（第9.2節）: 始点＝Y の小さい端（等しければ第2点）、主軸＝差の大きい軸（等しければ Y）、和の初期値＝主軸の差÷2、
;   主軸を1歩ずつ進めて 和 += 副軸の差、和 >= 主軸の差 なら副軸を1歩進めて和から主軸の差を引く。画素数は主軸の差+1。
; クリップ（第9.3節）: 線を画面の長方形と交わらせて端点を求め（元の線との交点を四捨五入）、その2点で引き直す。
;   交点の式（自作判断）: 交点の他軸の値 = 元の第1点の値 + 四捨五入((辺 - 元の第1点の辺の軸の値) * (他軸の差) / (辺の軸の差))。
;   四捨五入は「厳密な有理数に 0.5 を足して床」（0.5 は +∞ 側）。32bit の積を16bitの商と余りで割り、余りの2倍と除数で丸めの向きを決める。
;   辺は 左(x<0)・右(x>=640)・上(y<0)・下(y>=200) の順に1回ずつ。同じ側に両端があれば何も描かず、最後に画面外が残っても何も描かない。
; ラインスタイル（第9.6節）: ビット15が最初の画素、16画素で繰り返し、1が描かれる（0は何もしない）。数え始めは「引く側の始点」（クリップ後）。
;   水平線で第2座標が画面外にあれば、第1座標側（クリップ後）から数える。
; B は4辺（上・右・下・左の順に各辺を線として引く）。BF は座標を画面の範囲へ切り詰めて、水平の帯をバイト単位で塗る。
;   画面外の BF は最寄りの画素へ切り詰められる（第9.4節の観測は左上だけ。他の外側は未検査で、同じ規則にした＝自作判断）。
; 水平の実線と BF の帯は、グラフィックVRAMの切替（OUT 0x5C〜0x5E）の窓の中で、端のバイトだけマスク付きで書き、間はバイトで埋める。
;   窓の中はスタックにもRAMにも触れず、DI〜EI で囲む（gfx.asm 冒頭と同じ約束）。

; ---------------------------------------------------------------- 文
gx_line:
    LD A,(MM_GFX_FG)
    XOR 7
    LD (MM_GFX_TC),A            ; 色の省略は前景（COLOR 第4引数）
    LD HL,65535
    LD (MM_LN_STYLE),HL
    XOR A
    LD (MM_LN_MODE),A
    CALL s2_skip
    CALL s2_peek
    CP '-'
    JR Z,gl_p1                  ; 始点省略は LP から
    CALL gx_coord
    CALL gx_bad
    RET NZ
gl_p1:
    LD HL,(MM_GFX_LPX)
    LD (MM_LN_BX1),HL
    LD HL,(MM_GFX_LPY)
    LD (MM_LN_BY1),HL
    LD A,'-'
    CALL gx_expect
    CALL gx_bad
    RET NZ
    CALL gx_coord               ; STEP の第2座標は第1点（いまの LP）からの相対
    CALL gx_bad
    RET NZ
    LD HL,(MM_GFX_LPX)
    LD (MM_LN_BX2),HL
    LD HL,(MM_GFX_LPY)
    LD (MM_LN_BY2),HL
    CALL s2_skip
    CALL s2_peek
    CP ','
    JR NZ,gl_end
    CALL s2_adv
    CALL s2_skip
    CALL s2_peek
    CP ','
    JR Z,gl_c2                  ; 色の省略
    AND 0DFh
    CP 'B'
    JR Z,gl_f                   ; ',b' は色の省略（箱の指定）
    CALL gx_ca_val              ; 色（範囲外は ERR 5、空は ERR 22）
    RET NZ
gl_c2:
    CALL s2_skip
    CALL s2_peek
    CP ','
    JR NZ,gl_end
    CALL s2_adv
    CALL s2_skip
    CALL s2_peek
gl_f:                           ; A=箱の指定の欄の先頭の文字（読み進めてはいない）
    OR A
    JP Z,gx_err22
    CP ':'
    JP Z,gx_err22
    CP ','
    JR Z,gl_s
    AND 0DFh
    CP 'B'
    JR NZ,gl_s
    CALL s2_adv
    LD A,1
    LD (MM_LN_MODE),A
    CALL s2_peek
    AND 0DFh
    CP 'F'
    JR NZ,gl_s
    CALL s2_adv
    LD A,2
    LD (MM_LN_MODE),A
gl_s:
    CALL s2_skip
    CALL s2_peek
    CP ','
    JR NZ,gl_end
    LD A,(MM_LN_MODE)
    CP 2
    JP Z,gx_err2                ; BF にスタイルは ERR 2
    CALL s2_adv
    CALL gx_parse_int
    CALL gx_bad
    RET NZ
    LD (MM_LN_STYLE),DE
gl_end:
    CALL gx_stmt_end            ; 構文が最後まで正しいときだけ描く
    RET NZ
    LD HL,(MM_LN_STYLE)
    LD (MM_LN_STY),HL           ; 線種の位相は文の頭で1回だけ置く（B の4辺をまたいで続く）
    LD A,(MM_LN_MODE)
    CP 2
    JP Z,ln_bf
    OR A
    JR NZ,ln_box
    LD HL,MM_LN_BX1
    LD DE,MM_LN_OX
    LD BC,8
    LDIR
    CALL ln_seg
    JP gx_ok

; B: 下・上・右・左の4辺を順に線として引く（角は2回描かれる）。線種の位相は4辺をまたいで続く（l4-s9u の sy-b・lp-c・sy-n の全画素に一致する並び。
; 水平の辺は第2座標側から数える）
ln_box:
    LD HL,ln_edge_tab
    LD B,4
ln_bx_e:
    PUSH BC
    PUSH HL
    LD DE,MM_LN_OX
    LD B,4
ln_bx_w:
    LD A,(HL)
    INC HL
    PUSH HL
    LD HL,MM_LN_BX1
    ADD A,L
    LD L,A
    LD A,(HL)
    LD (DE),A
    INC DE
    INC HL
    LD A,(HL)
    LD (DE),A
    INC DE
    POP HL
    DJNZ ln_bx_w
    CALL ln_seg
    POP HL
    LD DE,4
    ADD HL,DE
    POP BC
    DJNZ ln_bx_e
    JP gx_ok
ln_edge_tab:                    ; 各辺の (始点x, 始点y, 終点x, 終点y) の BX1 からのオフセット
    DB 0,6,4,6, 0,2,4,2, 4,2,4,6, 0,6,0,2

; BF: 座標を画面の範囲へ切り詰め、行ごとに水平の帯を塗る
ln_bf:
    LD HL,(MM_LN_BX1)
    LD DE,(MM_LN_BX2)
    LD BC,639
    CALL ln_clampsort
    LD (MM_LN_HX0),HL
    LD (MM_LN_HX1),DE
    LD HL,(MM_LN_BY1)
    LD DE,(MM_LN_BY2)
    LD BC,199
    CALL ln_clampsort
    LD (MM_LN_HY),HL
    LD (MM_LN_HYE),DE
    CALL gx_pt_begin            ; IX=色の行（行の塗りが使う）
    CALL ln_hprep               ; 先頭行の番地とマスク。以降の行は番地を +80 するだけ
ln_bf_l:
    CALL ln_hrow
    LD HL,(MM_LN_HY)
    LD DE,(MM_LN_HYE)
    OR A
    SBC HL,DE
    JP Z,gx_ok
    ADD HL,DE
    INC HL
    LD (MM_LN_HY),HL
    LD DE,80
    LD HL,(MM_LN_HA0)
    ADD HL,DE
    LD (MM_LN_HA0),HL
    LD HL,(MM_LN_HA1)
    ADD HL,DE
    LD (MM_LN_HA1),HL
    JR ln_bf_l

; HL=a, DE=b を 0〜BC に切り詰め、HL=小さい方・DE=大きい方
ln_clampsort:
    CALL ln_clamp
    EX DE,HL
    CALL ln_clamp
    OR A
    PUSH HL
    SBC HL,DE
    POP HL
    RET C
    EX DE,HL
    RET
ln_clamp:
    BIT 7,H
    JR Z,ln_cp_p
    LD HL,0
    RET
ln_cp_p:
    PUSH HL
    OR A
    SBC HL,BC
    POP HL
    RET C
    LD H,B
    LD L,C
    RET

; ---------------------------------------------------------------- 1本の線（OX=元の2点）
ln_seg:
    LD HL,MM_LN_OX
    LD DE,MM_LN_C0X
    LD BC,8
    LDIR
    LD HL,(MM_LN_OX+4)          ; X の差も Y の差も 65535 の線は何も描かない（第9.3節。自作は「両軸とも 65535」を最小の実装とした）
    LD DE,(MM_LN_OX)
    CALL ln_subabs
    INC HL
    LD A,H
    OR L
    JR NZ,ln_sg_ok
    LD HL,(MM_LN_OX+6)
    LD DE,(MM_LN_OX+2)
    CALL ln_subabs
    INC HL
    LD A,H
    OR L
    RET Z
ln_sg_ok:
    CALL ln_ocs
    LD A,(MM_LN_F0)
    LD HL,MM_LN_F1
    OR (HL)
    JR Z,ln_seg_in
    CALL ln_clipall
    RET C
ln_seg_in:
    LD HL,(MM_LN_C0Y)           ; 始点＝Y の小さい端。等しければ第2点。ただし水平線で第2点が切られていたら第1点
    LD DE,(MM_LN_C1Y)
    OR A
    SBC HL,DE
    JR C,ln_s_c0
    JR NZ,ln_s_c1
    LD HL,(MM_LN_OX+4)
    LD DE,(MM_LN_C1X)
    OR A
    SBC HL,DE
    JR Z,ln_s_c1
ln_s_c0:
    LD HL,(MM_LN_C0X)
    LD (MM_LN_X),HL
    LD HL,(MM_LN_C0Y)
    LD (MM_LN_Y),HL
    LD HL,(MM_LN_C1X)
    LD DE,(MM_LN_C1Y)
    JR ln_s_go
ln_s_c1:
    LD HL,(MM_LN_C1X)
    LD (MM_LN_X),HL
    LD HL,(MM_LN_C1Y)
    LD (MM_LN_Y),HL
    LD HL,(MM_LN_C0X)
    LD DE,(MM_LN_C0Y)
ln_s_go:                        ; HL,DE=終点 x,y。X,Y=始点
    LD BC,(MM_LN_X)
    OR A
    SBC HL,BC                   ; 終点x - 始点x
    LD BC,1
    BIT 7,H
    JR Z,ln_dxp
    LD BC,65535
    XOR A
    SUB L
    LD L,A
    SBC A,A
    SUB H
    LD H,A
ln_dxp:
    LD (MM_LN_XS),BC            ; x の向き（+1/-1）。HL=dx
    EX DE,HL                    ; DE=dx, HL=終点y
    PUSH DE
    LD DE,(MM_LN_Y)
    OR A
    SBC HL,DE                   ; dy（始点が上なので 0 以上）
    POP DE
    LD A,H
    OR L
    JR NZ,ln_gen
    LD BC,(MM_LN_STYLE)         ; 水平の実線は帯で塗る
    INC BC
    LD A,B
    OR C
    JR NZ,ln_gen
    LD HL,(MM_LN_X)
    LD A,(MM_LN_XS+1)
    OR A
    JR Z,ln_hp
    LD (MM_LN_HX1),HL
    OR A
    SBC HL,DE
    LD (MM_LN_HX0),HL
    JR ln_hgo
ln_hp:
    LD (MM_LN_HX0),HL
    ADD HL,DE
    LD (MM_LN_HX1),HL
ln_hgo:
    LD HL,(MM_LN_Y)
    LD (MM_LN_HY),HL
    JP ln_hspan
ln_gen:                         ; DE=dx, HL=dy
    PUSH HL
    OR A
    SBC HL,DE
    POP HL
    JR C,ln_xmaj
    LD (MM_LN_M),HL             ; Y 主軸（dy >= dx）
    LD (MM_LN_S),DE
    LD A,1
    JR ln_gset
ln_xmaj:
    LD (MM_LN_M),DE
    LD (MM_LN_S),HL
    XOR A
ln_gset:
    LD (MM_LN_YMAJ),A
    LD HL,(MM_LN_M)
    LD (MM_LN_CNT),HL
    SRL H
    RR L
    LD (MM_LN_SUM),HL           ; 和の初期値 = 主軸の差 ÷ 2（切り捨て）
    CALL gx_pt_begin
    LD HL,(MM_LN_STY)
    INC HL
    LD A,H
    OR L
    JR NZ,ln_loop               ; 線種のある線は点ごとの汎用ループ（下）
    LD HL,(MM_LN_X)
    LD DE,(MM_LN_Y)
    CALL gx_addr
    JR C,ln_loop                ; （起きないはず。起きても汎用ループが同じ画素を描く）
    JR ln_fast
ln_loop:
    CALL ln_pix
    LD HL,(MM_LN_CNT)
    LD A,H
    OR L
    RET Z
    DEC HL
    LD (MM_LN_CNT),HL
    LD A,(MM_LN_YMAJ)
    OR A
    JR Z,ln_lx
    LD HL,(MM_LN_Y)             ; Y 主軸: y を進め、副軸 x は和で決める
    INC HL
    LD (MM_LN_Y),HL
    CALL ln_sum
    JR NC,ln_loop
    CALL ln_stepx
    JR ln_loop
ln_lx:
    CALL ln_stepx               ; X 主軸: x を進め、副軸 y は和で決める
    CALL ln_sum
    JR NC,ln_loop
    LD HL,(MM_LN_Y)
    INC HL
    LD (MM_LN_Y),HL
    JR ln_loop
ln_stepx:
    LD HL,(MM_LN_X)
    LD DE,(MM_LN_XS)
    ADD HL,DE
    LD (MM_LN_X),HL
    RET
ln_sum:                         ; 和 += 副軸の差。和 >= 主軸の差なら和 -= 主軸の差 で CF=1（副軸を進める）
    LD HL,(MM_LN_SUM)
    LD DE,(MM_LN_S)
    ADD HL,DE
    LD DE,(MM_LN_M)
    OR A
    SBC HL,DE
    JR C,ln_sum_n
    LD (MM_LN_SUM),HL
    SCF
    RET
ln_sum_n:
    ADD HL,DE
    LD (MM_LN_SUM),HL
    OR A
    RET
ln_pix:                         ; スタイルを1つ回し、ビットが立っていれば (X,Y) を打つ
    LD HL,(MM_LN_STY)
    ADD HL,HL
    JR NC,ln_pix_n
    INC HL
    LD (MM_LN_STY),HL
    LD HL,(MM_LN_X)
    LD DE,(MM_LN_Y)
    JP gx_plotxy
ln_pix_n:
    LD (MM_LN_STY),HL
    RET

; ---------------------------------------------------------------- 実線の速い走査（線種なし）
; 線の画素は汎用ループ（上）と同じ。違いは画素ごとに (x,y) から番地を求め直さず、番地 HL とビットマスク B を進めること。
;   x を1歩: B を回し、回りきったら HL を ±1。y を1歩: HL += 80。クリップ後の線は画面の長方形の中に収まるので範囲検査は要らない。
;   和の判定: t = 和 - 主軸の差（負）で持ち、t += 副軸の差 のキャリー ⇔ 和+副軸の差 >= 主軸の差。キャリーで t += -主軸の差。
;   レジスタ: HL=番地 B=マスク DE=副軸の差 IX=色の行 IY=t、裏レジスタ BC'=-主軸の差 HL'=残りの歩数（割り込みハンドラは裏レジスタを使わない）。
;   窓（DI〜EI）は gx_pt の中だけ。入口 HL=始点の番地 B=マスク
ln_fast:
    LD DE,(MM_LN_S)             ; DE=副軸の差（ループの間ずっと）
    EXX
    LD HL,(MM_LN_M)
    XOR A
    SUB L
    LD C,A
    SBC A,A
    SUB H
    LD B,A                      ; BC'=-主軸の差
    LD D,H
    LD E,L
    SRL D
    RR E                        ; DE'=主軸の差 ÷ 2
    LD IY,0
    ADD IY,DE
    ADD IY,BC                   ; t = (主軸の差 ÷ 2) - 主軸の差
    LD HL,(MM_LN_CNT)           ; HL'=残りの歩数
    EXX
    LD A,(MM_LN_YMAJ)
    OR A
    JR Z,ln_fx
    LD A,(MM_LN_XS+1)
    OR A
    JR NZ,ln_fy_m
ln_fy_p:                        ; Y 主軸・x が増える
    CALL gx_pt
    EXX
    LD A,H
    OR L
    JR Z,ln_f_end
    DEC HL
    EXX
    LD A,L
    ADD A,80
    LD L,A
    JR NC,ln_fyp_a
    INC H
ln_fyp_a:
    ADD IY,DE
    JR NC,ln_fy_p
    EXX
    ADD IY,BC
    EXX
    RRC B
    JR NC,ln_fy_p
    INC HL
    JR ln_fy_p
ln_fy_m:                        ; Y 主軸・x が減る
    CALL gx_pt
    EXX
    LD A,H
    OR L
    JR Z,ln_f_end
    DEC HL
    EXX
    LD A,L
    ADD A,80
    LD L,A
    JR NC,ln_fym_a
    INC H
ln_fym_a:
    ADD IY,DE
    JR NC,ln_fy_m
    EXX
    ADD IY,BC
    EXX
    RLC B
    JR NC,ln_fy_m
    DEC HL
    JR ln_fy_m
ln_f_end:
    EXX
    RET
ln_fx:                          ; X 主軸
    LD A,(MM_LN_XS+1)
    OR A
    JR NZ,ln_fx_m
ln_fx_p:                        ; x が増える
    CALL gx_pt
    EXX
    LD A,H
    OR L
    JR Z,ln_f_end
    DEC HL
    EXX
    RRC B
    JR NC,ln_fxp_a
    INC HL
ln_fxp_a:
    ADD IY,DE
    JR NC,ln_fx_p
    EXX
    ADD IY,BC
    EXX
    LD A,L
    ADD A,80
    LD L,A
    JR NC,ln_fx_p
    INC H
    JR ln_fx_p
ln_fx_m:                        ; x が減る
    CALL gx_pt
    EXX
    LD A,H
    OR L
    JR Z,ln_f_end
    DEC HL
    EXX
    RLC B
    JR NC,ln_fxm_a
    DEC HL
ln_fxm_a:
    ADD IY,DE
    JR NC,ln_fx_m
    EXX
    ADD IY,BC
    EXX
    LD A,L
    ADD A,80
    LD L,A
    JR NC,ln_fx_m
    INC H
    JR ln_fx_m

; ---------------------------------------------------------------- クリップ
; IX=端点 → A=はみ出しの印（bit0 x<0, bit1 x>=640, bit2 y<0, bit3 y>=200）
ln_oc:
    LD L,(IX+0)
    LD H,(IX+1)
    LD DE,640
    CALL ln_oc1
    LD B,A
    LD L,(IX+2)
    LD H,(IX+3)
    LD DE,200
    CALL ln_oc1
    ADD A,A
    ADD A,A
    OR B
    RET
ln_oc1:                         ; HL=値, DE=上限 → A=1 負 / 2 上限以上 / 0 範囲内
    BIT 7,H
    JR Z,ln_oc1a
    LD A,1
    RET
ln_oc1a:
    OR A
    SBC HL,DE
    LD A,0
    RET C
    LD A,2
    RET

; 4辺を 左(x>=0)・右(x<=639)・上(y>=0)・下(y<=199) の順に1辺ずつ切る。各段で、はみ出している端点を「いまの線」とその辺の直線の
; 交点（四捨五入して整数）に置き換え、次の辺へ進む（第3版の cp-8 の根拠）。両端がその辺の外なら棄却（CF=1）。
ln_clipall:
    XOR A
    LD (MM_LN_K),A
ln_ca_l:
    CALL ln_ocs
    LD A,(MM_LN_K)
    LD B,A
    INC B
    LD A,1
ln_ca_m:
    DEC B
    JR Z,ln_ca_mm
    ADD A,A
    JR ln_ca_m
ln_ca_mm:
    LD D,A                      ; この辺の印
    LD A,(MM_LN_F0)
    AND D
    LD E,A
    LD A,(MM_LN_F1)
    AND D
    JR Z,ln_ca_one
    LD A,E
    OR A
    JR NZ,ln_ca_rej
ln_ca_one:
    LD HL,(MM_LN_C0Y)           ; いまの線を転置した記録 (y0,x0,y1,x1)（上下の辺用）
    LD (MM_LN_OT),HL
    LD HL,(MM_LN_C0X)
    LD (MM_LN_OT+2),HL
    LD HL,(MM_LN_C1Y)
    LD (MM_LN_OT+4),HL
    LD HL,(MM_LN_C1X)
    LD (MM_LN_OT+6),HL
    LD A,E
    OR A
    JR Z,ln_ca_p1
    LD IX,MM_LN_C0X
    CALL ln_move
    JR ln_ca_n
ln_ca_p1:
    LD A,(MM_LN_F1)
    AND D
    JR Z,ln_ca_n
    LD IX,MM_LN_C1X
    CALL ln_move
ln_ca_n:
    LD A,(MM_LN_K)
    INC A
    LD (MM_LN_K),A
    CP 4
    JR NZ,ln_ca_l
    CALL ln_ocs                 ; 丸めで辺の外に残ったら棄却
    LD A,(MM_LN_F0)
    LD HL,MM_LN_F1
    OR (HL)
    RET Z
ln_ca_rej:
    SCF
    RET
ln_move:                        ; IX=端点。MM_LN_K の辺との交点へ置き換える
    LD A,(MM_LN_K)
    ADD A,A
    LD E,A
    LD D,0
    LD HL,ln_edge_e
    ADD HL,DE
    LD E,(HL)
    INC HL
    LD D,(HL)                   ; DE=辺の値（0/639/0/199）
    LD HL,MM_LN_C0X
    LD A,(MM_LN_K)
    BIT 1,A
    JR Z,ln_mv_a
    LD HL,MM_LN_OT
ln_mv_a:
    PUSH DE
    CALL ln_interp
    POP DE
    LD A,(MM_LN_K)
    BIT 1,A
    JR NZ,ln_mv_y
    LD (IX+0),E
    LD (IX+1),D
    LD (IX+2),L
    LD (IX+3),H
    RET
ln_mv_y:
    LD (IX+0),L
    LD (IX+1),H
    LD (IX+2),E
    LD (IX+3),D
    RET
ln_ocs:                         ; 両端の印を MM_LN_F0・F1 へ
    LD IX,MM_LN_C0X
    CALL ln_oc
    LD (MM_LN_F0),A
    LD IX,MM_LN_C1X
    CALL ln_oc
    LD (MM_LN_F1),A
    RET
ln_edge_e:
    DW 0,639,0,199

; HL=記録 (a1,b1,a2,b2)、DE=A0 → HL = b1 + 四捨五入((A0-a1)*(b2-b1)/(a2-a1))
ln_interp:
    PUSH DE
    LD DE,MM_LN_TA1
    LD BC,8
    LDIR
    POP HL
    LD DE,(MM_LN_TA1)
    CALL ln_subabs
    PUSH HL                     ; |A0-a1|
    SBC A,A
    LD (MM_LN_SG),A
    LD HL,(MM_LN_TA2)
    LD DE,(MM_LN_TA1)
    CALL ln_subabs
    PUSH HL                     ; |a2-a1|
    SBC A,A
    LD HL,MM_LN_SG
    XOR (HL)
    LD (HL),A
    LD HL,(MM_LN_TB2)
    LD DE,(MM_LN_TB1)
    CALL ln_subabs
    PUSH HL                     ; |b2-b1|
    SBC A,A
    LD HL,MM_LN_SG
    XOR (HL)
    LD (HL),A                   ; 結果の符号（0xFF=負）
    POP DE                      ; |b2-b1|
    POP BC                      ; |a2-a1|
    POP HL                      ; |A0-a1|
    PUSH BC
    LD B,H
    LD C,L
    LD HL,0                     ; DEHL = BC * DE（32bit）
    LD A,16
ln_mu:
    ADD HL,HL
    RL E
    RL D
    JR NC,ln_mu_n
    ADD HL,BC
    JR NC,ln_mu_n
    INC DE
ln_mu_n:
    DEC A
    JR NZ,ln_mu
    EX DE,HL                    ; HL=上位, DE=下位
    POP BC                      ; 除数 |a2-a1|
    LD A,16
ln_dv:                          ; (HL:DE) / BC → 商 DE, 余り HL（上位 < 除数）
    SLA E
    RL D
    ADC HL,HL
    JR C,ln_dv_s
    SBC HL,BC
    JR NC,ln_dv_q
    ADD HL,BC
    JR ln_dv_n
ln_dv_s:
    OR A
    SBC HL,BC
ln_dv_q:
    INC E
ln_dv_n:
    DEC A
    JR NZ,ln_dv
    LD A,(MM_LN_SG)
    ADD HL,HL
    JR C,ln_ip_up
    OR A
    JR Z,ln_ip_c
    SCF                         ; 負: 2*余り > 除数 のときだけ繰り上げ（0.5 は +∞ 側へ）
ln_ip_c:
    SBC HL,BC
    JR C,ln_ip_nr
ln_ip_up:
    INC DE
ln_ip_nr:
    LD A,(MM_LN_SG)
    OR A
    JR Z,ln_ip_p
    XOR A
    SUB E
    LD E,A
    SBC A,A
    SUB D
    LD D,A
ln_ip_p:
    LD HL,(MM_LN_TB1)
    ADD HL,DE
    RET

; HL=a, DE=b（符号付き16bit） → HL=|a-b|（0〜65535）、CF=1 なら a<b
ln_subabs:
    OR A
    SBC HL,DE
    JP PE,ln_sa_ov
    JP P,ln_sa_pos
    JR ln_sa_neg
ln_sa_ov:
    JP M,ln_sa_pos
ln_sa_neg:
    XOR A
    SUB L
    LD L,A
    SBC A,A
    SUB H
    LD H,A
    SCF
    RET
ln_sa_pos:
    OR A
    RET

; ---------------------------------------------------------------- 水平の帯（バイト単位）
; MM_LN_HX0..HX1 (0〜639, HX0<=HX1) の y=MM_LN_HY を MM_GFX_TC で塗る。カラーは3プレーン、白黒はアクティブページ。
; 1行1プレーンを1つの窓（DI〜EI）で塗る: 端のバイトはマスク付き、間は PUSH DE の並びへ飛び込んで2バイトずつ書く
; （スタックポインタをグラフィックVRAMの右端に置く。窓の中は割り込みが来ない）。
ln_hspan:
    CALL gx_pt_begin
    CALL ln_hprep
    JP ln_hrow
; HX0,HX1,HY から 左端の番地 HA0・左端のマスク HLM・右端の番地 HA1・右端のマスク HRM・間隔 HNB を作る
ln_hprep:
    LD HL,(MM_LN_HX0)
    LD DE,(MM_LN_HY)
    CALL gx_addr
    LD (MM_LN_HA0),HL
    LD A,B                      ; 左端のバイトのマスク = (左端の位置のビット*2)-1
    ADD A,A
    DEC A
    LD (MM_LN_HLM),A
    LD HL,(MM_LN_HX1)
    LD DE,(MM_LN_HY)
    CALL gx_addr
    LD (MM_LN_HA1),HL
    LD A,B                      ; 右端のバイトのマスク = -(右端の位置のビット)
    NEG
    LD (MM_LN_HRM),A
    LD DE,(MM_LN_HA0)
    OR A
    SBC HL,DE
    LD A,L
    LD (MM_LN_HNB),A            ; 右端のバイトと左端のバイトの間隔
    RET
; 準備済みの1行を塗る（IX=色の行）。間のバイトが2個以上あるときの飛び先 IY と奇数の印 HFV を作る
ln_hrow:
    LD A,(MM_LN_HNB)
    OR A
    JR Z,ln_hr_go
    DEC A                       ; 間のバイト数 n = 間隔-1
    LD B,A
    AND 1
    LD (MM_LN_HFV),A            ; 奇数なら左端の次の1バイトを別に書く
    LD A,B
    SRL A                       ; 2バイトずつの書き込みの回数 k
    LD E,A
    LD D,0
    LD HL,ln_pend
    OR A
    SBC HL,DE
    PUSH HL
    POP IY                      ; ln_pend から k 個さかのぼった PUSH DE へ飛ぶ
ln_hr_go:
    LD A,(MM_GFX_MONO)
    OR A
    JR NZ,ln_hr_mono
    LD E,(IX+0)
    LD C,05Ch
    CALL ln_hplane
    LD E,(IX+1)
    LD C,05Dh
    CALL ln_hplane
    LD E,(IX+2)
    LD C,05Eh
    JR ln_hplane
ln_hr_mono:
    LD A,(MM_GFX_TC)
    ADD A,0FFh
    SBC A,A
    LD E,A
    LD A,(MM_GFX_APAGE)
    ADD A,05Ch
    LD C,A
; C=プレーンのポート, E=埋める値(00/FF)。1行1プレーンを塗る
ln_hplane:
    LD A,(MM_LN_HNB)
    OR A
    JR Z,ln_hp_one
    LD (MM_LN_TA2),SP           ; 窓の中でSPを書き換えるので退避（窓の外のRAMに置く）
    LD A,(MM_LN_HFV)
    LD B,A
    LD A,E
    EXX
    LD E,A                      ; E'=埋める値
    LD HL,(MM_LN_HA1)
    LD A,(MM_LN_HRM)
    LD D,A                      ; D'=右端のマスク
    EXX
    LD HL,(MM_LN_HA0)
    LD A,(MM_LN_HLM)
    LD D,A                      ; D=左端のマスク
    DI                          ; ここから EI まで、スタックにもRAMにも触れない
    OUT (C),A
    LD A,(HL)
    XOR E
    AND D
    XOR (HL)
    LD (HL),A                   ; 左端
    BIT 0,B
    JR Z,ln_hp_ev
    INC HL
    LD (HL),E                   ; 間のバイトが奇数個のとき、左端の次の1バイト
ln_hp_ev:
    EXX
    LD A,(HL)
    XOR E
    AND D
    XOR (HL)
    LD (HL),A                   ; 右端
    LD SP,HL                    ; 右端の番地から下へ2バイトずつ
    LD D,E
    JP (IY)
ln_pushes:
    DS 40,0D5h                  ; PUSH DE × 40（1行の間のバイトは最大78＝39組）
ln_pend:
    EXX
    OUT (05Fh),A                ; メインRAMへ戻す
    LD SP,(MM_LN_TA2)
    EI
    RET
ln_hp_one:                      ; 1バイトだけ（左端と右端が同じバイト）
    LD A,(MM_LN_HLM)
    LD D,A
    LD A,(MM_LN_HRM)
    AND D
    LD D,A
    LD HL,(MM_LN_HA0)
    DI
    OUT (C),A
    LD A,(HL)
    XOR E
    AND D
    XOR (HL)
    LD (HL),A
    OUT (05Fh),A
    EI
    RET
