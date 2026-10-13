; LINE 実線の X 主軸。クリップ・端点順・和の初期値は line.asm と共通。
; C に現在のバイトの画素を OR し、行またはバイトが変わる前に gx_pt へ渡す。
; レジスタは ln_fast と同じ、表 C だけを蓄積マスクに使う。新規RAMなし。
; gx_pt は3プレーンを1バイトずつ処理し、DI 区間と窓内のスタック禁止を維持。
    ORG 0x6F00
ln_fx:
    LD C,B
    LD A,(MM_LN_XS+1)
    OR A
    JR NZ,ln_fx_m
ln_fx_p:
    EXX
    LD A,H
    OR L
    JR Z,ln_fx_end
    DEC HL
    EXX
    ADD IY,DE
    JR NC,ln_fxp_x
    EXX
    ADD IY,BC
    EXX
    CALL ln_fx_flush            ; 次の行へ進む前に現在のバイトを確定
    LD A,L
    ADD A,80
    LD L,A
    JR NC,ln_fxp_y
    INC H
ln_fxp_y:
    RRC B
    JR NC,ln_fxp_new
    INC HL
ln_fxp_new:
    LD C,B
    JR ln_fx_p
ln_fxp_x:
    RRC B
    JR NC,ln_fxp_or
    CALL ln_fx_flush            ; B は既に次のバイトの先頭。描画マスクは C
    INC HL
    LD C,B
    JR ln_fx_p
ln_fxp_or:
    LD A,C
    OR B
    LD C,A
    JR ln_fx_p
ln_fx_m:
    EXX
    LD A,H
    OR L
    JR Z,ln_fx_end
    DEC HL
    EXX
    ADD IY,DE
    JR NC,ln_fxm_x
    EXX
    ADD IY,BC
    EXX
    CALL ln_fx_flush
    LD A,L
    ADD A,80
    LD L,A
    JR NC,ln_fxm_y
    INC H
ln_fxm_y:
    RLC B
    JR NC,ln_fxm_new
    DEC HL
ln_fxm_new:
    LD C,B
    JR ln_fx_m
ln_fxm_x:
    RLC B
    JR NC,ln_fxm_or
    CALL ln_fx_flush
    DEC HL
    LD C,B
    JR ln_fx_m
ln_fxm_or:
    LD A,C
    OR B
    LD C,A
    JR ln_fx_m
ln_fx_end:
    EXX
    ; 最終画素も確定。スタック操作は gx_pt が RAM に戻す前後だけ。
ln_fx_flush:
    PUSH BC
    LD B,C
    CALL gx_pt
    POP BC
    RET

