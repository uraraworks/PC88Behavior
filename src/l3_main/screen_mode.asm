; WIDTH/CONSOLE の既存画面設定をmain予約前へ移設し、7071と共用する。
; MM_FN_AUX=桁・行、MM_SCR_MODE=カラー等。D=0はBASIC、D=1は7071。
; バンク0からはEXT_BANK_MAIN_CALL経由で呼ぶ（表もmain側に置く）。
; 根拠: l4-program.md 5.6.5、main-rom-entry.md 第6版 1.6。
; 行数ごとの表: ポート0x31の値・DMAC転送長（下位,上位）・CRTC RESETの5パラメータ（5.6.5の手順1・6・7）
wb_w_tab20:
    DB 019h,05Fh,089h,0CEh,093h,073h,038h,013h
wb_w_tab25:
    DB 039h,0B7h,08Bh,0CEh,098h,06Fh,058h,013h

SCREEN_MODE_APPLY:
    LD A,(MM_FN_AUX)
    LD (MM_SCR_COLS),A
    LD C,A
    LD A,(MM_FN_AUX+1)
    LD B,A
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
    LD A,D
    OR A
    LD A,(HL)
    JR Z,wb_wa_31
    AND 0E7h                   ; 7071: カラー80x25からbit3・4を落とす
wb_wa_31:                      ; 1: OUT 0x31（20行0x19／25行0x39）。垂直同期ごとに同じ値を出す
    LD (MM_SCR_P31),A
    OUT (0x31),A
    INC HL
    LD A,C                     ; 2: OUT 0x30（80桁0x23／40桁0x22。差はbit0だけ）
    CP 80
    LD A,023h
    JR Z,wb_wa_30
    LD A,022h
wb_wa_30:
    LD B,A                     ; カラーモードは bit1=0（console ,,,1 の 0x21 と同じ形。自作判断: width 後の値は未測定）
    LD A,(MM_SCR_MODE)
    RRCA
    LD A,B
    JR NC,wb_wa_30o
    AND 0FDh
wb_wa_30o:
    LD B,A
    LD A,D
    OR A
    LD A,B
    JR Z,wb_wa_30store
    AND 3
    LD B,A
    LD A,(0xE6C0)
    AND 0FCh
    OR B
wb_wa_30store:
    LD (MM_SCR_P30),A          ; l4-program.md 第12節。
    OUT (0x30),A
    LD A,D
    OR A
    JR Z,wb_wa_reset
    LD A,(0xE6C1)
    OR 8                       ; 起動時CRTC設定の同期ビットを立てる
    OUT (0x40),A
wb_wa_reset:
    XOR A                      ; 3: CRTC RESET
    OUT (0x51),A
    LD A,0A0h                  ; 4: DMAC
    OUT (0x68),A
    LD A,D
    OR A
    LD A,0C8h                  ; 5: BASICではDMAアドレス F3C8
    JR Z,wb_wa_dma_low
    LD A,(0xE6C4)
wb_wa_dma_low:
    OUT (0x64),A
    LD A,D
    OR A
    LD A,0F3h
    JR Z,wb_wa_dma_high
    LD A,(0xE6C5)
wb_wa_dma_high:
    OUT (0x64),A
    LD A,(HL)                  ; 6: 転送長（下位・上位）
    OUT (0x65),A
    INC HL
    LD A,(HL)
    OUT (0x65),A
    INC HL
    LD B,4                     ; 7: CRTC RESETの5パラメータ（5つ目はカラーモードで bit6 を足す）
wb_wa_crtc:
    LD A,(HL)
    OUT (0x50),A
    INC HL
    DJNZ wb_wa_crtc
    LD A,(MM_SCR_MODE)
    RRCA
    LD A,(HL)
    JR NC,wb_wa_p5
    OR 040h
wb_wa_p5:
    OUT (0x50),A
    LD A,043h                  ; 8
    OUT (0x51),A
    LD A,0E4h                  ; 9
    OUT (0x68),A
    LD A,020h                  ; 10
    OUT (0x51),A
    LD A,D
    OR A
    RET Z
    LD A,(0xE6C1)
    AND 0F7h                   ; 同期ビットを戻し、それ以外はRAM値を保つ
    OUT (0x40),A
    RET
