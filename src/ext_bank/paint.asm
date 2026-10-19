; docs/spec/l4-graphics.md 第11節から独立実装。PAINT本体（bank1の元の入口）。
; bank2 paintpから1回呼ばれ、描画前処理だけをbank3へ委譲する。
;
; 境界でない画素の4連結成分を区間単位で反復走査する。
; 訪問ビットは固定域3072Bと必要なヒープ空き（最大12928B）、1画素1bit。
; 塗り色と元の色の一致や、タイルに含まれる境界色に探索が左右されない。
; 訪問済み画素の上下に接続する区間を探し、変化が無くなるまで走査する。
; 区間スタックは不要。CPUスタックは再帰せず深さは一定。
; 空き不足時は閉矩形を描画前に検証し、その矩形だけの訪問ビットを使う。
; 矩形を保証できない・矩形分も足りない場合は描画前にERR 7。利用者ヒープと共有スタックは保護する。
; VRAM窓はDI〜EIで保護し、窓内ではRAMとCPUスタックに触れない。
; 自作判断: 作業域不足をERR 7とし、仕様11.5の公式の壁破壊異常は再現しない。

PA_EXTCALL_ADDR EQU 0x1787
PA_BC EQU MM_PA_BC
PA_PF EQU MM_PA_PF
PA_NR EQU MM_PA_NR
PA_Y EQU MM_PA_Y
PA_NY EQU MM_PA_NY
PA_RB EQU MM_PA_RB
PA_RE EQU MM_PA_RE
PA_XLA EQU MM_PA_XLA
PA_XLQ EQU MM_PA_XLQ
PA_XRA EQU MM_PA_XRA
PA_XRQ EQU MM_PA_XRQ
PA_CM EQU MM_PA_CM
PA_HM EQU MM_PA_HM
PA_E EQU MM_PA_E
PA_OFF EQU MM_PA_OFF
PA_BASE EQU MM_PA_BASE
PA_LIM EQU MM_PA_LIM
PA_SA EQU MM_PA_SA
PA_SQ EQU MM_PA_SQ
PA_TILE EQU MM_PA_TILE
PA_MAP EQU MM_PA_MAP
PA_WIN_X0 EQU MM_PA_WIN_X0
PA_WIN_X1 EQU MM_PA_WIN_X1
PA_WIN_Y0 EQU MM_PA_WIN_Y0
PA_WIN_Y1 EQU MM_PA_WIN_Y1
PA_WIN_COL EQU MM_PA_WIN_COL
PA_WIN_WIDTH EQU MM_PA_WIN_WIDTH
PA_WIN_MODE EQU MM_PA_WIN_MODE
PA_RAY_X EQU MM_PA_RAY_X
PA_RAY_Y EQU MM_PA_RAY_Y
PA_RAY_DX EQU MM_PA_RAY_DX
PA_RAY_DY EQU MM_PA_RAY_DY
PA_BITMAP_SIZE EQU MM_PA_BITMAP_SIZE
PA_BITMAP_HEAP EQU MM_PA_BITMAP_HEAP

; 先頭0x30Bは予約のまま。描画ループの補助も同じbank1内に置く。
    ORG 0x6030
pt_zero:
    LD D,H
    LD E,L
    INC DE
    DEC BC
    LD (HL),0
    LDIR
    RET
; ---- 行の実番地と訪問ビットの詰めた行との差。
; 通常モードは差0、幅80のまま。矩形のときだけ (y-y0)*幅 を計算する。
pt_rowsetup:
    PUSH AF
    CALL pt_rowaddr
    LD A,(PA_WIN_MODE)
    OR A
    JR NZ,pt_rowcompact
    POP AF
    RET
pt_rowcompact:
    POP AF
    PUSH HL
    LD C,A
    LD A,(PA_WIN_Y0)
    LD B,A
    LD A,C
    SUB B
    LD DE,(PA_WIN_WIDTH)
    CALL pt_mul
    LD DE,MM_GVRAM_BASE
    ADD HL,DE
    EX DE,HL
    POP HL
    LD A,(PA_WIN_COL)
    ADD A,L
    LD L,A
    JR NC,pt_rowcol
    INC H
pt_rowcol:
    PUSH HL
    EX DE,HL
    OR A
    SBC HL,DE
    LD (PA_OFF),HL
    POP HL
    RET
pt_mul:                         ; A(0..200)*DE(幅1..80)→HL
    LD HL,0
    LD B,8
pt_mulbit:
    SRL A
    JR NC,pt_mulnext
    ADD HL,DE
pt_mulnext:
    SLA E
    RL D
    DJNZ pt_mulbit
    RET
pt_rowaddr:                     ; A=y → HL=その行の先頭（C000+y*80）。DE を壊す
    LD H,0
    LD L,A
    LD D,H
    LD E,A
    ADD HL,HL
    ADD HL,HL
    ADD HL,DE
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    LD DE,MM_GVRAM_BASE
    ADD HL,DE
    RET
pt_eqde:                        ; HL と DE が等しければ Z（どちらも保つ）
    OR A
    SBC HL,DE
    ADD HL,DE
    RET
pt_scan_min:
    LD A,(PA_WIN_Y0)
    LD E,A
    LD A,(MM_PA_YMIN)
    CP E
    RET Z
    DEC A
    RET
pt_scan_max:
    LD A,(PA_WIN_Y1)
    LD E,A
    LD A,(MM_PA_YMAX)
    CP E
    RET Z
    INC A
    RET


PAINT_LOCAL_HELPERS_END:
    ORG 0x7C8C
PAINT_CORE_ENTRY:
pt_core:
    LD HL,(PA_SA)
    CALL pt_rd3
    LD IX,PA_BC
    CALL pt_ne3
    LD HL,PA_SQ
    AND (HL)
    JP Z,pt_exit                ; 境界上なら作業域を確保せず終了
    LD HL,0x707D               ; bank3の描画前処理を1回だけ呼ぶ
    LD A,3
    LD IX,PA_EXTCALL_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    JP C,pt_nomem
pt_space:
    LD HL,(MM_HEAP_END)
    LD DE,-MM_PA_VIDEO_HEAP
    ADD HL,DE
    LD (PA_MAP),HL
    LD HL,MM_PA_BITMAP_LOW
    LD BC,1024
    CALL pt_zero
    LD HL,MM_PA_BITMAP_TEMP
    LD BC,2048
    CALL pt_zero
    LD BC,(PA_BITMAP_HEAP)
    LD A,B
    OR C
    JR Z,pt_seed
    LD HL,(MM_HEAP_END)
    CALL pt_zero
pt_seed:
    LD HL,(PA_SA)               ; 開始画素のバイト番地とビット
    LD A,(PA_SQ)
    LD B,A
    LD A,(PA_Y)
    LD (MM_PA_YMIN),A
    LD (MM_PA_YMAX),A
    CALL pt_expand              ; 開始点の区間（開始点が境界なら何もしない）
    JP C,pt_exit
    XOR A
    LD (MM_PA_DIR),A
pt_sweep:
    XOR A
    LD (MM_PA_CHANGED),A
    LD A,(MM_PA_DIR)
    XOR 1
    LD (MM_PA_DIR),A
    JR Z,pt_start_forward
    CALL pt_scan_max
    JR pt_row
pt_start_forward:
    CALL pt_scan_min
pt_row:
    LD (PA_NY),A
    CALL pt_rowsetup
    PUSH HL
    LD DE,(PA_WIN_WIDTH)
    ADD HL,DE
    LD (MM_PA_SCAN_END),HL
    POP HL
pt_scan:
    LD (MM_PA_SCAN),HL
    PUSH HL
    CALL pt_map
    LD A,(HL)
    CPL
    OR A
    JR NZ,pt_unseen
    POP HL
    JR pt_advance
pt_unseen:
    LD C,A
    POP HL
    PUSH HL
    LD B,0
    LD A,(PA_NY)
    LD E,A
    LD A,(PA_WIN_Y0)
    CP E
    JR Z,pt_above
    PUSH HL
    LD DE,(PA_OFF)
    ADD HL,DE
    LD DE,(PA_WIN_WIDTH)
    OR A
    SBC HL,DE
    CALL pt_mapv
    LD B,(HL)
    POP HL
pt_above:
    LD A,(PA_NY)
    LD E,A
    LD A,(PA_WIN_Y1)
    CP E
    JR Z,pt_below
    PUSH HL
    LD DE,(PA_OFF)
    ADD HL,DE
    LD DE,(PA_WIN_WIDTH)
    ADD HL,DE
    CALL pt_mapv
    LD A,(HL)
    OR B
    LD B,A
    POP HL
pt_below:
    LD A,B
    AND C
    POP HL
    OR A
    JR Z,pt_advance
    LD C,A
    CALL pt_getm
    AND C
    JR Z,pt_advance
    LD C,A
    LD B,80h
pt_bit:
    LD A,C
    AND B
    JR NZ,pt_hit
    SRL B
    JR pt_bit
pt_hit:
    LD A,(PA_NY)
    CALL pt_expand
    LD HL,(MM_PA_SCAN)
    JR pt_scan
pt_advance:
    INC HL
    LD DE,(MM_PA_SCAN_END)
    CALL pt_eqde
    JR NZ,pt_scan
    LD A,(MM_PA_DIR)
    OR A
    LD A,(PA_NY)
    JR Z,pt_forward
    LD C,A
    CALL pt_scan_min
    CP C
    JR Z,pt_swept
    LD A,C
    DEC A
    JP pt_row
pt_forward:
    LD C,A
    CALL pt_scan_max
    CP C
    JR Z,pt_swept
    LD A,C
    INC A
    JP pt_row
pt_swept:
    LD A,(MM_PA_CHANGED)
    OR A
    JP NZ,pt_sweep
    JR pt_exit
pt_nomem:
    LD A,7
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
pt_exit:
    XOR A
    LD (MM_VAL_SP),A            ; 再利用した式スタックの位置を空へ戻す
    LD A,(MM_ERROR_FLAG)
    OR A                        ; 作業域が足りなかったなら ERR 7 が立っている
    RET NZ
    XOR A
    LD (MM_RUN_CTRL),A
    RET

; ---- 画面の番地
pt_islast:                      ; HL が PA_E と等しければ Z
    LD A,(PA_E)
    CP L
    RET NZ
    LD A,(PA_E+1)
    CP H
    RET

; ---- VRAM のバイトの読み書き（窓の中はスタックにもRAMにも触れない）
pt_rd3:                         ; HL=番地 → B,C,D=プレーン0,1,2（白黒: アクティブページを3つに）
    DI
    OUT (05Ch),A
    LD B,(HL)
    OUT (05Dh),A
    LD C,(HL)
    OUT (05Eh),A
    LD D,(HL)
    OUT (05Fh),A
    EI
    LD A,(MM_GFX_MONO)
    OR A
    RET Z
    LD A,(MM_GFX_APAGE)
    OR A
    JR Z,pt_rm0
    DEC A
    JR Z,pt_rm1
    LD B,D
    JR pt_rm0
pt_rm1:
    LD B,C
pt_rm0:
    LD C,B
    LD D,B
    RET
pt_wr3:                         ; HL=番地, B=マスク, C=埋め値0, E=埋め値1, D=埋め値2（白黒は C だけ）。マスクの位置だけ埋め値に替える
    LD A,(MM_GFX_MONO)
    OR A
    JR NZ,pt_wr_mono
    DI
    OUT (05Ch),A
    LD A,(HL)
    XOR C
    AND B
    XOR (HL)
    LD (HL),A
    OUT (05Dh),A
    LD A,(HL)
    XOR E
    AND B
    XOR (HL)
    LD (HL),A
    OUT (05Eh),A
    LD A,(HL)
    XOR D
    AND B
    XOR (HL)
    LD (HL),A
    OUT (05Fh),A
    EI
    RET
pt_wr_mono:
    LD E,C
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
    OUT (05Fh),A
    EI
    LD C,E
    RET
pt_ne3:                         ; B,C,D と (IX+0..2) が違うビットを A に（1=違う）。E を壊す
    LD A,B
    XOR (IX+0)
    LD E,A
    LD A,C
    XOR (IX+1)
    OR E
    LD E,A
    LD A,D
    XOR (IX+2)
    OR E
    RET
pt_getm:                        ; 境界でも訪問済みでもないビット。HL・BCを保つ
    PUSH BC
    CALL pt_rd3
    LD IX,PA_BC
    CALL pt_ne3
    PUSH HL
    PUSH AF
    CALL pt_map
    POP AF
    LD E,A
    LD A,(HL)
    CPL
    AND E
    POP HL
    POP BC
    RET

; ---- タイルの行を埋め値(PA_PF)へ（A=y を保つ）
pt_setrow:
    LD C,A
    LD A,(PA_NR)
    OR A
    LD A,C
    RET Z                       ; 非タイル
    LD A,(PA_NR)
    LD B,A
    LD A,C
pt_sr1:
    SUB B
    JR NC,pt_sr1
    ADD A,B                     ; A=y mod n
    LD E,A
    LD D,0
    LD HL,PA_TILE
    ADD HL,DE
    LD A,(MM_GFX_MONO)
    OR A
    JR Z,pt_sr_col
    LD A,(HL)
    LD (PA_PF),A
    LD (PA_PF+1),A
    LD (PA_PF+2),A
    LD A,C
    RET
pt_sr_col:
    ADD HL,DE
    ADD HL,DE                   ; タイル + 3*(y mod n)
    LD DE,PA_PF
    LDI
    LDI
    LDI
    LD A,C
    RET

; ---- 未訪問区間を求めて塗り、訪問ビットを立てる。A=行、HL=開始画素のバイト番地、B=そのビット。
;      CF=1: 開始画素が境界または訪問済み（何もしない）
pt_expand:
    LD (PA_Y),A
    LD C,A
    LD A,(MM_PA_YMIN)
    CP C
    JR C,pt_keepmin
    LD A,C
    LD (MM_PA_YMIN),A
pt_keepmin:
    LD A,(MM_PA_YMAX)
    CP C
    JR NC,pt_keepmax
    LD A,C
    LD (MM_PA_YMAX),A
pt_keepmax:
    LD A,C
    PUSH HL
    PUSH BC
    CALL pt_rowsetup
    LD (PA_RB),HL
    LD DE,(PA_WIN_WIDTH)
    ADD HL,DE
    LD (PA_RE),HL
    POP BC
    POP HL
    CALL pt_getm
    LD C,A
    AND B
    SCF
    RET Z                       ; 境界
    PUSH HL
    PUSH BC
    ; ---- 右へ。(HL,B)=最後の境界でない画素
pt_sr:
    LD A,B
    RRCA
    JR C,pt_srn
    AND C
    JR Z,pt_sre
    LD B,A
    JR pt_sr
pt_srn:                         ; 次の画素は次のバイトの先頭
    INC HL
    LD DE,(PA_RE)
    CALL pt_eqde
    JR Z,pt_sred                ; 画面の右端は壁
    CALL pt_getm
    LD C,A
    LD B,80h
    AND B
    JR Z,pt_sred                ; 先頭の画素が境界
    LD A,C
    INC A
    JR NZ,pt_sr
    LD B,1                      ; 8画素とも境界でない: 最後の画素へ
    JR pt_sr
pt_sred:
    DEC HL
    LD B,1
pt_sre:
    LD (PA_XRA),HL
    LD A,B
    LD (PA_XRQ),A
    POP BC
    POP HL
    ; ---- 左へ。(HL,B)=最初の境界でない画素
pt_sl:
    LD A,B
    RLCA
    JR C,pt_slp
    AND C
    JR Z,pt_sle
    LD B,A
    JR pt_sl
pt_slp:                         ; 次の画素は前のバイトの末尾
    LD DE,(PA_RB)
    CALL pt_eqde
    JR Z,pt_sle                 ; 画面の左端は壁
    DEC HL
    CALL pt_getm
    LD C,A
    LD B,1
    AND B
    JR Z,pt_slb                 ; 末尾の画素が境界
    LD A,C
    INC A
    JR NZ,pt_sl
    LD B,80h                    ; 8画素とも境界でない: 先頭の画素へ
    JR pt_sl
pt_slb:
    INC HL
    LD B,80h
pt_sle:
    LD (PA_XLA),HL
    LD A,B
    LD (PA_XLQ),A
    ; ---- 塗る
    LD A,(PA_Y)
    CALL pt_setrow
    LD A,(PA_XLQ)
    ADD A,A
    DEC A
    LD (PA_CM),A                ; 左端のバイトのマスク（左端の画素から右）
    LD A,(PA_XRQ)
    NEG
    LD (PA_HM),A                ; 右端のバイトのマスク（左から右端の画素まで）
    LD HL,(PA_XRA)
    LD (PA_E),HL
    LD HL,(PA_XLA)
    LD A,(PA_PF)
    LD C,A
    LD DE,(PA_PF+1)             ; E=埋め値1, D=埋め値2
pt_pl:
    LD A,(PA_CM)
    LD B,A
    LD A,0FFh
    LD (PA_CM),A
    CALL pt_islast
    JR NZ,pt_pm
    LD A,(PA_HM)
    AND B
    LD B,A
pt_pm:
    PUSH HL
    CALL pt_map
    LD A,(HL)
    OR B
    LD (HL),A
    POP HL
    LD DE,(PA_PF+1)
    CALL pt_wr3
    CALL pt_islast
    INC HL
    JR NZ,pt_pl
    LD A,1
    LD (MM_PA_CHANGED),A
    OR A
    RET


pt_map:                         ; 実VRAM番地→矩形内の仮想番地→訪問ビット
    LD DE,(PA_OFF)
    ADD HL,DE
pt_mapv:                        ; 仮想C000〜FE7F→固定域2つと空きヒープ
    LD A,H
    CP 0C4h
    LD DE,MM_PA_BITMAP_LOW-MM_GVRAM_BASE
    JR C,pt_mapped
    CP 0CCh
    LD DE,MM_PA_BITMAP_TEMP-MM_PA_VIDEO_SECOND
    JR C,pt_mapped
    LD DE,(PA_MAP)
pt_mapped:
    ADD HL,DE
    RET

PAINT_CORE_END:
