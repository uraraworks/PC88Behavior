; docs/spec/l4-graphics.md 第5版 第11節（l4-s9w の観測）から独立実装。PAINT 文のうち構文・検査・埋め値の準備。バンク2の line.asm の後ろへ連結。
; 塗りの本体（区間を単位にした反復走査の塗り）はバンク1の paint.asm。ここは引数を読み、検査し、作業域 PAINT_WORK を整えて本体を1回呼ぶ。
;
; 形: PAINT [STEP](x,y)[,領域色または文字列(タイル)[,境界色[,バックグラウンド(文字列)]]]。文の種別 50（gfx.asm の gx_stmt から）。
; 誤り番号（第11.1・11.3節）: 構文は ERR 2、欄の後ろが空なら ERR 22、色の範囲外・開始点が画面外・タイルが1行に満たないは ERR 5、
;   境界色が文字列は ERR 13、桁あふれは ERR 6。LP は gx_coord が座標を読み終えた時点で動かす。
; 自作判断（仕様で未測定のところ）:
;   - タイル塗りで境界色を省略したときの境界色は前景色（COLOR 第4引数。既定 7）。非タイルは領域色。
;   - バックグラウンド: 先頭の1行（3バイト。白黒は1バイト）を背景の行とし、タイルの行がそれと一致する行が3行連続したら ERR 5
;     （行数1のタイルで一致しても ERR 5）。1行に満たなければ ERR 5（tl-3）。数値のバックグラウンドは ERR 5。
;   - 第3コンマ（バックグラウンド）はタイルのときだけ。タイルでなければ ERR 2。ただし引数過多（余分なコンマ以降）は、
;     そこまでに読めた引数で塗ってから ERR 2 を返す（sx-b: 余分があっても領域が塗られている観測。LP は座標の組で動く）。

GP_ISSTR_ADDR EQU 0x1787
GP_STREXPR_ADDR EQU 0x1787
GP_EXTCALL_ADDR EQU 0x1787
PAINT_CORE_ENTRY EQU 0x7C8C
PA_BC EQU MM_PA_BC
PA_PF EQU MM_PA_PF
PA_TF EQU MM_PA_TF
PA_TL EQU MM_PA_TL
PA_NR EQU MM_PA_NR
PA_BDEF EQU MM_PA_BDEF
PA_PCOL EQU MM_PA_PCOL
PA_BCOL EQU MM_PA_BCOL
PA_BG EQU MM_PA_BG
PA_SL EQU MM_PA_SL
PA_Y EQU MM_PA_Y
PA_GR EQU MM_PA_GR
PA_SA EQU MM_PA_SA
PA_SQ EQU MM_PA_SQ
PA_DERR EQU MM_PA_DERR
PA_TILE EQU MM_PA_TILE

gx_paint:
    XOR A
    LD (PA_DERR),A
    LD (PA_TF),A
    LD (PA_BDEF),A
    LD (PA_BG),A
    LD (PA_SL),A
    LD A,(MM_GFX_FG)
    XOR 7
    LD (PA_PCOL),A
    CALL gx_coord               ; [STEP](x,y)。LP を更新
    CALL gx_bad
    RET NZ
gp_slot:                        ; 欄は ',' で始まる（0=領域色 1=境界色 2=バックグラウンド）
    CALL s2_skip
    CALL s2_peek
    CP ','
    JP NZ,gp_end
    CALL s2_adv
    LD A,(PA_SL)
    CP 3
    JR NC,gp_late
    CP 2
    JR C,gp_s0
    LD A,(PA_TF)                ; 第3コンマ: タイルでなければ引数過多
    OR A
    JR NZ,gp_s0
gp_late:                        ; 引数過多: 読めたところまでで塗ってから ERR 2（sx-b の観測。下記）
    LD A,1
    LD (PA_DERR),A
    JP gp_run
gp_s0:
    CALL s2_skip
    CALL s2_peek
    CP ','
    JR Z,gp_snext               ; 空の欄
    OR A
    JP Z,gx_err22
    CP ':'
    JP Z,gx_err22
    LD A,(PA_SL)
    OR A
    JR Z,gp_paint
    DEC A
    JR Z,gp_bord
    CALL gp_isstr               ; バックグラウンドは文字列
    OR A
    JP Z,gx_err5
    CALL gp_strexpr
    CALL gx_bad
    RET NZ
    LD A,1
    LD (PA_BG),A
    JR gp_snext
gp_bord:
    CALL gx_ca_val              ; 数値 0〜7（範囲外 ERR 5、文字列 ERR 13）
    RET NZ
    LD A,(MM_GFX_TC)
    LD (PA_BCOL),A
    LD A,1
    LD (PA_BDEF),A
    JR gp_snext
gp_paint:
    CALL gp_isstr
    OR A
    JR NZ,gp_tile
    CALL gx_ca_val
    RET NZ
    LD A,(MM_GFX_TC)
    LD (PA_PCOL),A
    JR gp_snext
gp_tile:
    CALL gp_strexpr
    CALL gx_bad
    RET NZ
    LD A,(MM_RUN_STR_TMP_LEN)
    LD (PA_TL),A
    LD C,A
    LD B,0
    LD A,1
    LD (PA_TF),A
    LD HL,MM_RUN_STR_TMP_BUF
    LD DE,PA_TILE
    LD A,C
    OR A
    JR Z,gp_snext
    LDIR
gp_snext:
    LD HL,PA_SL
    INC (HL)
    JP gp_slot
gp_end:
    CALL gx_stmt_end            ; 構文が最後まで正しいときだけ進む
    JR Z,gp_run
    LD A,(PA_SL)
    CP 1
    RET NZ
    LD A,(PA_TF)
    OR A
    RET NZ
    JP gx_err5                 ; 数値の領域色の後の余分な語（7 7）はERR 5
gp_run:
    ; ---- 開始点は画面内か（範囲外は ERR 5）。HL=バイトの番地、B=その画素のビット
    LD HL,(MM_GFX_LPX)
    LD DE,(MM_GFX_LPY)
    CALL gx_addr
    JP C,gx_err5
    LD (PA_SA),HL
    LD A,B
    LD (PA_SQ),A
    LD A,(MM_GFX_LPY)
    LD (PA_Y),A
    ; ---- タイル: 1行の桁数 C（白黒1・カラー3）、行数 n。足りなければ ERR 5。背景の行と連続一致なら ERR 5
    XOR A
    LD (PA_NR),A
    LD A,(PA_TF)
    OR A
    JR Z,gp_fills
    LD C,3
    LD A,(MM_GFX_MONO)
    OR A
    JR Z,gp_c3
    LD C,1
gp_c3:
    LD A,(PA_TL)
    LD B,0
gp_div:
    SUB C
    JR C,gp_dd
    INC B
    JR gp_div
gp_dd:
    LD A,B
    OR A
    JP Z,gx_err5
    LD (PA_NR),A
    LD HL,0                     ; 背景の行 PA_GR[0..2]（無い・1行に満たないときは 0）
    LD (PA_GR),HL
    LD (PA_GR+2),HL
    LD A,(PA_BG)
    OR A
    JR Z,gp_bgdone
    LD A,(MM_RUN_STR_TMP_LEN)
    CP C
    JP C,gx_err5                ; 1行に満たないバックグラウンドは ERR 5（tl-3 の観測）
    PUSH BC
    LD B,0
    LD HL,MM_RUN_STR_TMP_BUF
    LD DE,PA_GR
    LDIR
    POP BC
gp_bgdone:
    LD A,(PA_NR)
    LD B,A                      ; B=残り行数
    LD D,3                      ; D=ERR 5 になる連続一致数（行数1なら1）
    DEC A
    JR NZ,gp_d3
    LD D,1
gp_d3:
    LD HL,PA_TILE
    LD E,0                      ; E=連続一致数
gp_cmp:
    PUSH HL
    PUSH BC
    LD IX,PA_GR
gp_cmp1:
    LD A,(IX+0)
    CP (HL)
    JR NZ,gp_cmpno
    INC HL
    INC IX
    DEC C
    JR NZ,gp_cmp1
    POP BC
    POP HL
    INC E
    LD A,E
    CP D
    JP NC,gx_err5
    JR gp_cmpnext
gp_cmpno:
    POP BC
    POP HL
    LD E,0
gp_cmpnext:
    LD A,B                      ; 次の行へ（HL += C）
    LD B,0
    ADD HL,BC
    LD B,A
    DEC B
    JR NZ,gp_cmp
gp_fills:
    ; ---- 境界色（省略: 非タイルは領域色、タイルは前景）と領域色の埋め値
    LD A,(PA_BDEF)
    OR A
    LD A,(PA_BCOL)
    JR NZ,gp_bset
    LD A,(PA_PCOL)
    LD B,A
    LD A,(PA_TF)
    OR A
    LD A,B
    JR Z,gp_bset
    LD A,(MM_GFX_FG)
    XOR 7
gp_bset:
    LD HL,PA_BC
    CALL gp_fill
    LD A,(PA_PCOL)
    LD HL,PA_PF
    CALL gp_fill
    LD HL,PAINT_CORE_ENTRY      ; 塗りの本体（バンク1）を1回だけ呼ぶ
    LD A,1
    LD IX,GP_EXTCALL_ADDR
    CALL BANK2_MAIN_CALL_ADDR
    CALL gx_bad
    RET NZ
    LD A,(PA_DERR)
    OR A
    RET Z
    JP gx_err2
gp_fill:                        ; A=色(0〜7)、HL=3バイトの埋め値の置き場（プレーン0〜2。ビットが1なら FF）。白黒は 0 以外を 7 にする
    LD C,A
    LD A,(MM_GFX_MONO)
    OR A
    LD A,C
    JR Z,gp_f0
    ADD A,0FFh
    SBC A,A
    AND 7
gp_f0:
    LD B,3
gp_f1:
    RRA
    LD C,A
    SBC A,A
    LD (HL),A
    INC HL
    LD A,C
    DJNZ gp_f1
    RET
gp_isstr:
    LD IX,GP_ISSTR_ADDR
    JP BANK2_MAIN_CALL_ADDR
gp_strexpr:
    LD IX,GP_STREXPR_ADDR
    JP BANK2_MAIN_CALL_ADDR
