; docs/spec/l4-graphics.md 第11節に基づくq2の前処理をbank3へ移設。
; PAINTごとに1度だけ呼ぶ描画前処理。bank3の空き。CF=確保不可。
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

    ORG 0x707D
PAINT_PREP_ENTRY:
    XOR A
    LD (PA_WIN_MODE),A
    LD (PA_WIN_COL),A
    LD (PA_WIN_Y0),A
    LD H,A
    LD L,A
    LD (PA_OFF),HL
    LD HL,80
    LD (PA_WIN_WIDTH),HL
    LD A,199
    LD (PA_WIN_Y1),A
    LD HL,16000
    LD (PA_BITMAP_SIZE),HL
    CALL pp_fit
    RET NC
    CALL pp_bounds               ; 空き不足のときだけ閉矩形を検証（まだ描かない）
    RET C
    CALL pp_fit
    RET C
    RET
pp_fit:                         ; 必要ヒープ=max(0,サイズ-3072)。CF=空き不足
    LD HL,(PA_BITMAP_SIZE)
    LD DE,3072
    OR A
    SBC HL,DE
    JR NC,pp_fitheap
    LD HL,0
pp_fitheap:
    LD (PA_BITMAP_HEAP),HL
    LD DE,(MM_HEAP_END)
    ADD HL,DE
    RET C
    EX DE,HL
    LD HL,(MM_FREE_TOP)
    OR A
    SBC HL,DE
    RET

; ---- 開始点から4方向の最初の境界（なければ画面端）を候補にする。
; 周囲の辺が全て境界/画面端であることを後から検証する。未検証のまま描かない。
pp_bounds:
    LD HL,(MM_GFX_LPX)
    LD (PA_RAY_X),HL
    LD A,(MM_GFX_LPY)
    LD (PA_RAY_Y),A
    LD HL,-1
    LD (PA_RAY_DX),HL
    CALL pp_rayh
    LD HL,(PA_RAY_X)
    LD (PA_WIN_X0),HL
    LD HL,(MM_GFX_LPX)
    LD (PA_RAY_X),HL
    LD HL,1
    LD (PA_RAY_DX),HL
    CALL pp_rayh
    LD HL,(PA_RAY_X)
    LD (PA_WIN_X1),HL
    LD HL,(MM_GFX_LPX)
    LD (PA_RAY_X),HL
    LD A,-1
    LD (PA_RAY_DY),A
    CALL pp_rayv
    LD A,(PA_RAY_Y)
    LD (PA_WIN_Y0),A
    LD A,(MM_GFX_LPY)
    LD (PA_RAY_Y),A
    LD A,1
    LD (PA_RAY_DY),A
    CALL pp_rayv
    LD A,(PA_RAY_Y)
    LD (PA_WIN_Y1),A
    ; 上下辺。画面端の外側は暗黙の壁なので端なら検証不要。
    LD A,(PA_WIN_Y0)
    OR A
    CALL NZ,pp_checkh
    JP NZ,pp_boundfail
    LD A,(PA_WIN_Y1)
    CP 199
    CALL NZ,pp_checkh
    JP NZ,pp_boundfail
    LD HL,(PA_WIN_X0)
    LD A,H
    OR L
    CALL NZ,pp_checkv
    JP NZ,pp_boundfail
    LD HL,(PA_WIN_X1)
    LD DE,639
    CALL pp_eqde
    CALL NZ,pp_checkv
    JP NZ,pp_boundfail
    LD HL,(PA_WIN_X0)
    CALL pp_div8
    LD A,L
    LD (PA_WIN_COL),A
    LD HL,(PA_WIN_X1)
    CALL pp_div8
    LD A,(PA_WIN_COL)
    LD C,A
    LD A,L
    SUB C
    INC A
    LD L,A
    LD H,0
    LD (PA_WIN_WIDTH),HL
    EX DE,HL
    LD A,(PA_WIN_Y0)
    LD C,A
    LD A,(PA_WIN_Y1)
    SUB C
    INC A
    CALL pp_mul
    LD (PA_BITMAP_SIZE),HL
    LD A,1
    LD (PA_WIN_MODE),A
    OR A
    RET
pp_boundfail:
    SCF
    RET
pp_rayh:
    CALL pp_probe
    RET Z
    LD HL,(PA_RAY_X)
    LD DE,(PA_RAY_DX)
    ADD HL,DE
    BIT 7,H
    RET NZ                      ; 直前のx=0（画面端）
    LD DE,640
    CALL pp_eqde
    RET Z                       ; 直前のx=639
    LD (PA_RAY_X),HL
    JR pp_rayh
pp_rayv:
    CALL pp_probe
    RET Z
    LD A,(PA_RAY_DY)
    LD C,A
    LD A,(PA_RAY_Y)
    ADD A,C
    CP 200
    RET NC                      ; 直前のy=0または199
    LD (PA_RAY_Y),A
    JR pp_rayv
pp_checkh:                      ; A=y。戻りZ=辺が全て境界
    LD (PA_RAY_Y),A
    LD HL,(PA_WIN_X0)
    LD (PA_RAY_X),HL
pp_checkh1:
    CALL pp_probe
    RET NZ
    LD HL,(PA_RAY_X)
    LD DE,(PA_WIN_X1)
    CALL pp_eqde
    RET Z
    INC HL
    LD (PA_RAY_X),HL
    JR pp_checkh1
pp_checkv:                      ; HL=x。戻りZ=辺が全て境界
    LD (PA_RAY_X),HL
    LD A,(PA_WIN_Y0)
    LD (PA_RAY_Y),A
pp_checkv1:
    CALL pp_probe
    RET NZ
    LD A,(PA_WIN_Y1)
    LD C,A
    LD A,(PA_RAY_Y)
    CP C
    RET Z
    INC A
    LD (PA_RAY_Y),A
    JR pp_checkv1
pp_probe:                       ; (RAY_X,RAY_Y)が境界と完全一致ならZ。まだ描画していない
    LD A,(PA_RAY_Y)
    CALL pp_rowaddr
    PUSH HL
    LD HL,(PA_RAY_X)
    LD A,L
    AND 7
    LD B,A
    LD A,80h
    JR Z,pp_probemask
pp_probebit:
    RRCA
    DJNZ pp_probebit
pp_probemask:
    PUSH AF
    CALL pp_div8
    EX DE,HL
    POP AF
    POP HL
    ADD HL,DE
    PUSH AF
    CALL pp_rd3
    LD IX,PA_BC
    CALL pp_ne3
    POP BC
    AND B
    RET
pp_div8:
    SRL H
    RR L
    SRL H
    RR L
    SRL H
    RR L
    RET

pp_rowaddr:                     ; A=y → HL=その行の先頭（C000+y*80）。DE を壊す
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
pp_eqde:                        ; HL と DE が等しければ Z（どちらも保つ）
    OR A
    SBC HL,DE
    ADD HL,DE
    RET

pp_rd3:                         ; HL=番地 → B,C,D=プレーン0,1,2（白黒: アクティブページを3つに）
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
    JR Z,pp_rm0
    DEC A
    JR Z,pp_rm1
    LD B,D
    JR pp_rm0
pp_rm1:
    LD B,C
pp_rm0:
    LD C,B
    LD D,B
    RET

pp_ne3:                         ; B,C,D と (IX+0..2) が違うビットを A に（1=違う）。E を壊す
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

pp_mul:                         ; A(0..200)*DE(幅1..80)→HL
    LD HL,0
    LD B,8
pp_mulbit:
    SRL A
    JR NC,pp_mulnext
    ADD HL,DE
pp_mulnext:
    SLA E
    RL D
    DJNZ pp_mulbit
    RET
PAINT_PREP_END:
