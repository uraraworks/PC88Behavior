; docs/spec/l4-graphics.md 第5版 第11節（l4-s9w の観測）から独立実装。PAINT 文の塗りの本体。バンク1の circle.asm の後ろへ連結。
; 構文・検査・埋め値の準備はバンク2の paintp.asm（gx_paint）。ここは作業域 PAINT_WORK が整った状態で1回呼ばれる。
;
; 境界でない画素の4連結成分を区間単位で反復走査する。
; 訪問ビットはヒープ空きの12928Bと固定域3072B（画面絶対位置、1画素1bit）。
; 塗り色と元の色の一致や、タイルに含まれる境界色に探索が左右されない。
; 訪問済み画素の上下に接続する区間を探し、変化が無くなるまで走査する。
; 区間スタックは不要。CPUスタックは再帰せず深さは一定。
; 空き不足は描画前にERR 7。利用者ヒープと共有スタックは保護する。
; VRAM窓はDI〜EIで保護し、窓内ではRAMとCPUスタックに触れない。
; 自作判断: 作業域不足をERR 7とし、仕様11.5の公式の壁破壊異常は再現しない。

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
PAINT_CORE_ENTRY EQU 0x7C8C

    ORG 0x7C8C
pt_core:
    LD HL,(PA_SA)
    CALL pt_rd3
    LD IX,PA_BC
    CALL pt_ne3
    LD HL,PA_SQ
    AND (HL)
    JP Z,pt_exit                ; 境界上なら作業域を確保せず終了
    LD HL,(MM_HEAP_END)
    LD DE,-MM_PA_VIDEO_HEAP
    ADD HL,DE
    LD (PA_MAP),HL              ; VRAM番地から訪問ビットの番地への差
    LD HL,(MM_HEAP_END)
    LD DE,12928
    ADD HL,DE
    JP C,pt_nomem
    EX DE,HL
    LD HL,(MM_FREE_TOP)
    OR A
    SBC HL,DE
    JP C,pt_nomem
    LD HL,MM_PA_BITMAP_LOW
    LD BC,1024
    CALL pt_zero
    LD HL,MM_PA_BITMAP_TEMP
    LD BC,2048
    CALL pt_zero
    LD HL,(MM_HEAP_END)
    LD BC,12928
    CALL pt_zero
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
    CALL pt_rowaddr
    PUSH HL
    LD DE,80
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
    OR A
    JR Z,pt_above
    PUSH HL
    LD DE,-80
    ADD HL,DE
    CALL pt_map
    LD B,(HL)
    POP HL
pt_above:
    LD A,(PA_NY)
    CP 199
    JR Z,pt_below
    PUSH HL
    LD DE,80
    ADD HL,DE
    CALL pt_map
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
    CALL ci_err
pt_exit:
    XOR A
    LD (MM_VAL_SP),A            ; 再利用した式スタックの位置を空へ戻す
    CALL ci_bad                 ; 作業域が足りなかったなら ERR 7 が立っている
    RET NZ
    XOR A
    LD (MM_RUN_CTRL),A
    RET

; ---- 画面の番地
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

; ---- 区間を求めて塗り、枠を積む。A=行、HL=開始画素のバイト番地、B=そのビット。
;      CF=1: 開始画素が境界（何もしない）、または枠が足りない（ERR 7 を立ててある）
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
    CALL pt_rowaddr
    LD (PA_RB),HL
    LD DE,80
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


pt_zero:
    LD D,H
    LD E,L
    INC DE
    DEC BC
    LD (HL),0
    LDIR
    RET
pt_map:                         ; VRAM番地→訪問ビット（固定域2つと空きヒープ）
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

pt_scan_min:
    LD A,(MM_PA_YMIN)
    OR A
    RET Z
    DEC A
    RET
pt_scan_max:
    LD A,(MM_PA_YMAX)
    CP 199
    RET Z
    INC A
    RET
