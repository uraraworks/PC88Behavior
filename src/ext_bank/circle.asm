; docs/spec/l4-graphics.md 第4版 第10節（l4-s9v の観測）から独立実装。CIRCLE 文。バンク1の 0x7840 以降（dim.asm の後ろへ連結）。
;
; 形: CIRCLE [STEP](x,y),半径[,色[,開始角[,終了角[,比率]]]]。途中の引数は空にできる。文の種別 49（bank0 gfxhook.asm から入る）。
; 構成（容量と速さの釣り合い。バンク2の空きは約540Bで本体が入らないため、本体はバンク1に置いた）:
;   - 構文・式・単精度の計算（半径の符号、点数N、角→点数、比率→整数）はバンク1で、mainの常駐ルーチンを窓外中継で呼ぶ。
;   - 中点法の (a,b) の列と、8方向への展開・円弧の判定もバンク1。点は 8 組ずつ MM_CI_BUF に置き、
;     バンク2の共通部（gfx.asm の gx_ci_flush → gx_plotxy。範囲外は点ごとに切り捨て）へ**1組につき1回**だけ渡す。
;     点ごとにバンクを往復しない（往復は座標の読み取り1回、8点の受け渡しが (a,b) 1組につき1回、扇形の線が1本につき1回）。
;   - 扇形の線は gx_ci_line（バンク2）= LINE と同じ ln_seg（辺ごとに丸めるクリップを含む）。
; 手順は第10.2〜10.5節のとおり。中点法の和は最大で約 ±131070（半径 32767 のとき）になり16ビットを超えるため 24 ビット符号付きで持つ。
; 自作判断（仕様で未測定のところ）:
;   - 角の点数が 16 ビット符号付きに収まらないとき（半径が約 5790 を超える円弧）は 0xFFFF とする。
;   - 比率の a_ が 16 ビット符号付きに収まらないとき（比率が約 -128 未満）は 0x0100（真円）とする。
;   - 点の座標が 16 ビットを超える（中心 ± 半径が -32768〜32767 の外）点は、画面外として打たない（巻き込みで画面内に入れない）。
;   - 複数の誤りが同時にあるときは、引数を読む順（中心→半径→色→開始角→終了角→比率）に最初の誤りを返す。

; バンク2の入口（src/ext_bank/gfx.asm の 0x7330〜）
GFX_COORD_ENTRY EQU 0x7330
GFX_CIFLUSH_ENTRY EQU 0x7333
GFX_CILINE_ENTRY EQU 0x7336
CI_EXPR_ADDR EQU 0x1787
CI_ISNEG_ADDR EQU 0x1787
CI_TOINT_ADDR EQU 0x1787
CI_LOADA_ADDR EQU 0x1787
CI_MUL_ADDR EQU 0x1787
CI_DIV_ADDR EQU 0x1787
CI_I2S_ADDR EQU 0x1787
CI_ROUND_ADDR EQU 0x1787
CI_EXTCALL_ADDR EQU 0x1787

    ORG 0x7840
CI_ENTRY:
    LD A,2
    LD (MM_ERROR_KIND),A
    LD A,(MM_GFX_FG)
    XOR 7
    LD (MM_GFX_TC),A            ; 色の省略は前景
    LD HL,0
    LD (MM_CI_SC),HL            ; 開始＝0
    LD (MM_CI_PLOTF),HL         ; PLOTF と LFS
    LD (MM_CI_LFE),HL           ; LFE と SWAP
    LD (MM_CI_SLOT),HL          ; SLOT と TMP
    DEC HL
    LD (MM_CI_EC),HL            ; 終了＝0xFFFF
    LD HL,128
    LD (MM_CI_AA),HL            ; 比率の既定 0.5 → a_=128
    LD HL,GFX_COORD_ENTRY
    CALL ci_b2                  ; 中心（[STEP](x,y)）。LP を更新
    CALL ci_bad
    RET NZ
    CALL ci_peek
    CP ','
    JP NZ,ci_err2
    CALL _b1_call_adv_ptr
    ; ---- 半径。符号は丸める前に見る（負は ERR 5）。rnd(半径) が 32767 を超えると ERR 6
    CALL ci_expr
    RET NZ
    LD IX,CI_ISNEG_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    DEC A
    JP Z,ci_err5
    LD IX,CI_TOINT_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    OR A
    JP Z,ci_err6
    LD (MM_CI_R),DE
    ; N = rnd(f32(r × 0.7071068))
    LD (MM_MBF_IN_INT),DE
    CALL ci_i2s
    CALL ci_res2a
    LD HL,ci_k707
    CALL ci_mulk
    CALL ci_res2a
    CALL ci_round
    LD (MM_CI_N),DE
    ; f32(8N) = f32(N) の指数に 3 を足したもの（角→点数の掛け算に使う）
    LD (MM_MBF_IN_INT),DE
    CALL ci_i2s
    LD A,(MM_MBF_RES+3)
    OR A
    JR Z,ci_n8z
    ADD A,3
    LD (MM_MBF_RES+3),A
ci_n8z:
    LD HL,MM_MBF_RES
    LD DE,MM_CI_N8F
    LD BC,4
    LDIR
    ; ---- 色・開始角・終了角・比率（途中を空にできる）
ci_slots:
    CALL ci_peek
    CP ','
    JR NZ,ci_parsed
    CALL _b1_call_adv_ptr
    CALL ci_peek
    CP ','
    JR Z,ci_slot_next           ; 空の欄
    OR A
    JP Z,ci_err22               ; コンマの後で文が終わる形
    CP ':'
    JP Z,ci_err22
    CALL ci_slot_value
    RET NZ
ci_slot_next:
    LD HL,MM_CI_SLOT
    INC (HL)
    LD A,(HL)
    CP 4
    JR C,ci_slots
    CALL ci_peek                ; 4つ（比率）の後にコンマが続くのは引数過多
    CP ','
    JP Z,ci_err2
ci_parsed:
    CALL ci_peek                ; 文の終わり（行末・':'・ELSE）
    OR A
    JR Z,ci_end_ok
    CP ':'
    JR Z,ci_end_ok
    AND 0DFh
    CP 'E'
    JP NZ,ci_err2
ci_end_ok:
    ; 開始＞終了なら入れ替えて外側を打つ（負の印も入れ替わる）
    LD HL,(MM_CI_EC)
    LD DE,(MM_CI_SC)
    OR A
    SBC HL,DE
    JR NC,ci_noswap
    LD HL,(MM_CI_EC)
    LD (MM_CI_SC),HL
    LD (MM_CI_EC),DE
    LD A,1
    LD (MM_CI_PLOTF),A
    LD HL,(MM_CI_LFS)
    LD A,H
    LD H,L
    LD L,A
    LD (MM_CI_LFS),HL
ci_noswap:
    ; ---- 中点法。X=2r, Y=0, 和=0。Y が偶数のとき (a,b)=((X+1)>>1,(Y+1)>>1) を8方向に展開し、Y>=X で終わる
    LD HL,(MM_CI_R)
    ADD HL,HL
    LD (MM_CI_X),HL
    LD HL,0
    LD (MM_CI_Y),HL
    LD (MM_CI_S),HL
    XOR A
    LD (MM_CI_S+2),A
ci_next:
    LD A,(MM_CI_Y)
    AND 1
    JR NZ,ci_step
    CALL ci_group
    LD HL,(MM_CI_Y)
    LD DE,(MM_CI_X)
    OR A
    SBC HL,DE
    JR NC,ci_ok                 ; Y >= X
ci_step:
    LD HL,(MM_CI_Y)             ; 和 += 2Y+1（17ビット）
    ADD HL,HL
    LD C,0
    RL C
    INC L
    LD DE,(MM_CI_S)
    ADD HL,DE
    LD (MM_CI_S),HL
    LD A,(MM_CI_S+2)
    ADC A,C
    LD (MM_CI_S+2),A
    BIT 7,A
    JR NZ,ci_ny                 ; 和 < 0
    LD HL,(MM_CI_X)             ; 和 >= 0: 和 -= 2X-1、X を1減らす
    ADD HL,HL
    LD C,0
    RL C
    LD DE,1
    OR A
    SBC HL,DE
    LD A,C
    SBC A,0
    LD C,A                      ; C:HL = 2X-1（符号付き24ビット）
    EX DE,HL
    LD HL,(MM_CI_S)
    OR A
    SBC HL,DE
    LD (MM_CI_S),HL
    LD A,(MM_CI_S+2)
    SBC A,C
    LD (MM_CI_S+2),A
    LD HL,(MM_CI_X)
    DEC HL
    LD (MM_CI_X),HL
ci_ny:
    LD HL,(MM_CI_Y)
    INC HL
    LD (MM_CI_Y),HL
    JR ci_next
ci_ok:
    XOR A
    LD (MM_ERROR_FLAG),A
    LD (MM_RUN_CTRL),A
    RET

; ---- 1組 (a,b) を8方向へ。V=[a, b, sa, sb]。8点の c から打つか（1）・中心への線か（2）・何もしないか（0）を決める
ci_group:
    LD HL,MM_CI_X
    LD DE,MM_CI_V
    CALL ci_half
    LD HL,MM_CI_Y
    LD DE,MM_CI_V+2
    CALL ci_half
    LD HL,MM_CI_BUF+1           ; 8組の x の上位に範囲外の印 0x80
    LD DE,4
    LD B,8
    LD A,080h
ci_inv:
    LD (HL),A
    ADD HL,DE
    DJNZ ci_inv
    XOR A
    LD (MM_CI_SLOT),A           ; 打つ点があったか
    LD (MM_CI_I),A
    LD H,A
    LD L,A
    LD (MM_CI_BASE),HL
ci_oct:
    LD A,(MM_CI_I)              ; c = 基準 ± b（偶数番は +、奇数番は -。奇数番で基準に 2N を足す）
    RRA
    LD HL,(MM_CI_BASE)
    LD DE,(MM_CI_V+2)
    JR NC,ci_plus
    PUSH DE
    LD DE,(MM_CI_N)
    ADD HL,DE
    ADD HL,DE
    LD (MM_CI_BASE),HL
    POP DE
    OR A
    SBC HL,DE
    JR ci_c
ci_plus:
    ADD HL,DE
ci_c:
    EX DE,HL
    CALL ci_decide
    LD (MM_CI_TMP),A
    OR A
    JR Z,ci_onext
    LD A,(MM_CI_I)              ; 表の1バイト: bit0=主役が b、bit1=x を引く、bit2=y を引く
    LD E,A
    LD D,0
    LD HL,ci_otab
    ADD HL,DE
    LD C,(HL)
    LD A,(MM_CI_SWAP)
    ADD A,A
    ADD A,A
    LD B,A                      ; B=0（縮める軸が y）または 4（x）
    LD A,C
    AND 1
    ADD A,A
    ADD A,B                     ; dx の位置（V の添字×2）
    BIT 1,C
    JR Z,ci_sx
    OR 080h
ci_sx:
    LD HL,(MM_GFX_LPX)
    CALL ci_pos
    JP PE,ci_onext              ; 16ビットを超える座標は画面外
    PUSH HL
    LD A,C
    AND 1
    ADD A,A
    XOR 2
    LD E,A
    LD A,B
    XOR 4
    ADD A,E                     ; dy の位置
    BIT 2,C
    JR Z,ci_sy
    OR 080h
ci_sy:
    LD HL,(MM_GFX_LPY)
    CALL ci_pos
    EX DE,HL                    ; DE=y
    POP HL                      ; HL=x
    JP PE,ci_onext
    LD A,(MM_CI_TMP)
    CP 2
    JR Z,ci_line
    LD (MM_CI_SLOT),A           ; 打つ点がある
    PUSH DE
    PUSH HL
    LD A,(MM_CI_I)
    ADD A,A
    ADD A,A
    ADD A,MM_CI_BUF & 255
    LD L,A
    LD H,MM_CI_BUF >> 8
    POP DE
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    POP DE
    LD (HL),E
    INC HL
    LD (HL),D
    JR ci_onext
ci_line:                        ; この点から中心への線（LINE と同じ規則）
    LD (MM_LN_OX),HL
    LD (MM_LN_OX+2),DE
    LD HL,(MM_GFX_LPX)
    LD (MM_LN_OX+4),HL
    LD HL,(MM_GFX_LPY)
    LD (MM_LN_OX+6),HL
    LD HL,GFX_CILINE_ENTRY
    CALL ci_b2
ci_onext:
    LD HL,MM_CI_I
    INC (HL)
    LD A,(HL)
    CP 8
    JP C,ci_oct
    LD A,(MM_CI_SLOT)
    OR A
    RET Z
    LD HL,GFX_CIFLUSH_ENTRY
ci_b2:                          ; HL=バンク2の入口
    LD A,2
    LD IX,CI_EXTCALL_ADDR
    JP BANK1_MAIN_CALL_ADDR

ci_otab:
    DB 4,5,7,6,2,3,1,0

; c の判定（第10.5節 3）。DE=c → A=0（何もしない）・1（打つ）・2（中心への線）
ci_decide:
    LD A,(MM_CI_PLOTF)
    LD HL,(MM_CI_SC)
    OR A
    SBC HL,DE
    JR Z,cd_sc
    RET NC                      ; sc > c: plotf なら打つ
    LD HL,(MM_CI_EC)
    OR A
    SBC HL,DE
    JR Z,cd_ec
    RET C                       ; c > ec: plotf なら打つ
    XOR 1                       ; ec > c: plotf でなければ打つ
    RET
cd_sc:
    LD A,(MM_CI_LFS)
    INC A
    RET
cd_ec:
    LD A,(MM_CI_LFE)
    INC A
    RET

; A=V の位置（bit7=引く）、HL=基準 → HL=基準±V。符号付き16ビットの溢れは PE。BC を壊さない
ci_pos:
    PUSH HL
    LD E,A
    RES 7,E
    LD D,0
    LD HL,MM_CI_V
    ADD HL,DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    POP HL
    OR A
    JP M,ci_psub
    ADC HL,DE
    RET
ci_psub:
    SBC HL,DE
    RET

; (HL)=元の値(X か Y) → V[k]=(v+1)>>1、V[k+2個先]=scale(V[k])。DE=&V[k]
ci_half:
    LD C,(HL)
    INC HL
    LD B,(HL)
    INC BC
    SRL B
    RR C
    LD A,C
    LD (DE),A
    INC DE
    LD A,B
    LD (DE),A
    INC DE
    INC DE
    INC DE
    PUSH DE
    CALL ci_scale
    EX DE,HL
    POP HL
    LD (HL),E
    INC HL
    LD (HL),D
    RET

; BC=v → HL=scale(v, a_)（第10.3節）。lo=0: hi≠0 なら素通し・0 なら 0。それ以外は (v×lo+128)>>8
ci_scale:
    LD A,(MM_CI_AA)
    OR A
    JR NZ,cs_mul
    LD A,(MM_CI_AA+1)
    OR A
    LD H,B
    LD L,C
    RET NZ
    LD HL,0
    RET
cs_mul:                         ; (vh×lo) + ((vl×lo+128)>>8)
    LD E,A
    LD D,0
    LD A,C
    CALL ci_mul8
    LD A,L
    ADD A,128
    LD A,H
    ADC A,0
    LD L,A
    LD H,0
    LD A,B
    OR A
    RET Z
    PUSH HL
    CALL ci_mul8
    POP DE
    ADD HL,DE
    RET
ci_mul8:                        ; A×DE(<=255) → HL。DE・BC は保つ
    PUSH BC
    LD HL,0
    LD B,8
cm_l:
    ADD HL,HL
    RLA
    JR NC,cm_n
    ADD HL,DE
cm_n:
    DJNZ cm_l
    POP BC
    RET

; ---- 引数の読み取り
ci_slot_value:                  ; SLOT=0 色 / 1 開始角 / 2 終了角 / 3 比率。NZ=誤り
    LD A,(MM_CI_SLOT)
    OR A
    JR NZ,cv_angle
                                ; 色: 0〜7（範囲外 ERR 5、1e10 は ERR 6）
    CALL _b1_call_parse_int_arg
    CALL ci_bad
    RET NZ
    LD A,D
    OR A
    JP NZ,ci_err5
    LD A,E
    CP 8
    JP NC,ci_err5
    LD (MM_GFX_TC),A
    XOR A
    RET
cv_angle:
    CP 3
    JR Z,cv_ratio
    CALL ci_angle               ; DE=点数、TMP=負の印
    RET NZ
    LD A,(MM_CI_SLOT)
    DEC A
    LD HL,MM_CI_SC
    LD BC,MM_CI_LFS
    JR Z,cv_store
    LD HL,MM_CI_EC
    LD BC,MM_CI_LFE
cv_store:
    LD (HL),E
    INC HL
    LD (HL),D
    LD A,(MM_CI_TMP)
    LD (BC),A
    XOR A
    RET

; 角（ラジアン）→ 点数 rnd(f32(f32(|v|)×f32(0.15915494)) × f32(8N))。積が 1 を超えたら ERR 5。負なら TMP=1
ci_angle:
    CALL ci_expr
    RET NZ
    CALL ci_loada
    LD A,(MM_MBF_OPA+2)
    LD C,A
    AND 07Fh
    LD (MM_MBF_OPA+2),A
    LD A,C
    AND 080h
    RLCA
    LD (MM_CI_TMP),A
    LD HL,ci_k2pi
    CALL ci_mulk
    LD HL,MM_MBF_RES
    CALL ci_gt1
    JP NC,ci_err5
    CALL ci_res2a
    LD HL,MM_CI_N8F
    LD DE,MM_MBF_OPB
    LD BC,4
    LDIR
    CALL ci_mul
    CALL ci_res2a
    CALL ci_round
    XOR A
    RET

; 比率 → a_ と向き。ratio<=1（負を含む）: a_=rnd(f32(ratio)×256)。ratio>1: a_=rnd(f32(1÷f32(ratio))×256)、SWAP=1
cv_ratio:
    CALL ci_expr
    RET NZ
    CALL ci_loada
    LD HL,MM_MBF_OPA
    CALL ci_gt1
    JR C,cr_le1
    LD A,1
    LD (MM_CI_SWAP),A
    LD HL,MM_MBF_OPA
    LD DE,MM_MBF_OPB
    LD BC,4
    LDIR
    LD HL,ci_one
    LD DE,MM_MBF_OPA
    LD C,4
    LDIR
    LD IX,CI_DIV_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    CALL ci_res2a
cr_le1:
    LD A,(MM_MBF_OPA+3)         ; ×256 は指数に 8 を足す
    OR A
    JR Z,cr_r
    ADD A,8
    JR C,cr_big
    LD (MM_MBF_OPA+3),A
cr_r:
    CALL ci_round
    OR A
    JR NZ,cr_st
cr_big:
    LD DE,0100h
cr_st:
    LD (MM_CI_AA),DE
    XOR A
    RET

; (HL)=MBF 単精度 → CF=1 なら 1.0 以下（負を含む）、NC なら 1.0 より大きい
ci_gt1:
    LD A,(HL)
    INC HL
    OR (HL)
    INC HL
    LD C,(HL)
    INC HL
    LD B,(HL)
    LD H,A
    LD A,C
    ADD A,A
    RET C
    OR H
    LD H,A
    LD A,B
    CP 081h
    RET C
    RET NZ
    LD A,H
    OR A
    RET NZ
    SCF
    RET

; ---- mainの常駐ルーチン（窓外中継）と小物
ci_bad:
    LD A,(MM_ERROR_FLAG)
    OR A
    RET
ci_peek:
    CALL _b1_call_skip_spaces
    JP _b1_call_peek_char
ci_expr:
    LD IX,CI_EXPR_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    JR ci_bad
ci_loada:
    LD IX,CI_LOADA_ADDR
    JP BANK1_MAIN_CALL_ADDR
ci_mul:
    LD IX,CI_MUL_ADDR
    JP BANK1_MAIN_CALL_ADDR
ci_i2s:
    LD IX,CI_I2S_ADDR
    JP BANK1_MAIN_CALL_ADDR
ci_round:                       ; OPA → DE（A=1 成功）。収まらないときは DE=0xFFFF
    LD IX,CI_ROUND_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    OR A
    RET NZ
    LD DE,65535
    RET
ci_res2a:
    LD HL,MM_MBF_RES
    LD DE,MM_MBF_OPA
    LD BC,4
    LDIR
    RET
ci_mulk:                        ; OPB=(HL) の定数、OPA×OPB → RES
    LD DE,MM_MBF_OPB
    LD BC,4
    LDIR
    JR ci_mul
ci_k2pi:
    DB 083h,0F9h,022h,07Eh      ; f32(0.15915494)
ci_k707:
    DB 0F4h,004h,035h,080h      ; f32(0.7071068)
ci_one:
    DB 000h,000h,000h,081h      ; 1.0

; ---- 誤り
ci_err2:
    LD A,2
    JR ci_err
ci_err5:
    LD A,5
    JR ci_err
ci_err6:
    LD A,6
    JR ci_err
ci_err22:
    LD A,22
ci_err:
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
    OR A
    RET
