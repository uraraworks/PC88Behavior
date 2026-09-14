; screen.asm — M7段階2a: テキストVRAMへの1文字出力・改行・スクロール・
; 自作バナー・Ok表示。
;
; 根拠は docs/spec/l3-main.md だけである。measurements/ も公式ROMも
; 参照していない。
;
;   TEXT_BASE / STRIDE / COLS       … l3-main.md 第1〜2節（行=120バイト、
;                                       addr = 0xF3C8 + row0*120 + col0）
;   ATTR_BYTES                      … l3-main.md 第1節・第3節（40バイト
;                                       ＝2バイト1組×20組）
;   スクロールが「VRAMの書き写し」であること … l3-main.md 第5節
;
; 仕様書に無いため、この版で明示的に選んだ既定（推測で埋めず、選択として
; 記録する。報告の「仕様書に無いこと」参照）:
;   - 属性域40バイトの「既定の並び」の具体的なバイト値
;     （各組の値バイトのビット意味は第3節・第8節で未確定のため、
;     20組すべて (位置=0,値=0) とする＝DEFAULT_ATTR）。
;   - スクロール対象行数。ファンクションキー表示行の予約はせず、
;     20行フル画面を対象にする（第5節「推定」節・第8節8番は未確定のため、
;     ファンクションキー行を実装しない選択をした）。
;     これにより1回のスクロールで書き写すのは 120 × 19 = 2280 バイト
;     （spec本文の2160/2760はファンクションキー行を予約した公式BASICの
;     実測値であり、この実装はその構成を採らないため一致しない）。
;
; バナー文言は自作の名前・バージョンのみ（禁止事項6・
; docs/notes/banner-attribution-2026-08-16.md）。公式の製品名・
; 著作権表示は含まない。

TEXT_BASE   EQU 0F3C8h   ; l3-main.md 第2節
STRIDE      EQU 120      ; l3-main.md 第1節（80桁+40属性）
COLS        EQU 80
ATTR_BYTES  EQU 40
ROWS        EQU 20       ; docs/spec/l1-ipl.md 第0節（起動時の実際の表示行数）

; ---- RAM変数（0000-7FFFはROM＝L1のROM/RAMモード設定のため書けない。
;      8000-FFFF側の、VRAM(F3C8-)ともスタック(F000から下方)とも
;      重ならない番地を選ぶ）----
VAR_ROW     EQU 0E800h   ; 現在の行 (0-19)
VAR_COL     EQU 0E801h   ; 現在の桁 (0-79)
VAR_ROWBASE EQU 0E802h   ; 現在行のVRAM先頭番地（2バイト）

; ---------------------------------------------------------------------
; SCREEN_MAIN — 画面初期化 → 自作バナー → (試験用の埋め草) → Ok
; ---------------------------------------------------------------------
SCREEN_MAIN:
    XOR A
    LD (VAR_ROW),A
    LD (VAR_COL),A
    LD HL,TEXT_BASE
    LD (VAR_ROWBASE),HL
    CALL CLEAR_SCREEN

    LD HL,BANNER_TXT
    CALL PRINT_STR
    CALL NEWLINE

    LD A,EXTRA_LINES
    OR A
    JR Z,_sm_no_extra
    LD B,EXTRA_LINES
_sm_extra_loop:
    PUSH BC
    LD HL,FILLER_TXT
    CALL PRINT_STR
    CALL NEWLINE
    POP BC
    DJNZ _sm_extra_loop
_sm_no_extra:

    LD HL,OK_TXT
    CALL PRINT_STR
    CALL NEWLINE
    RET

; ---------------------------------------------------------------------
; CLEAR_SCREEN — 全20行を空白＋既定の属性で埋める
; ---------------------------------------------------------------------
CLEAR_SCREEN:
    LD B,ROWS
    LD HL,TEXT_BASE
_cs_row_loop:
    PUSH BC
    PUSH HL
    LD B,COLS
    LD A,020h
_cs_txt_loop:
    LD (HL),A
    INC HL
    DJNZ _cs_txt_loop
    LD DE,DEFAULT_ATTR
    LD B,ATTR_BYTES
_cs_attr_loop:
    LD A,(DE)
    LD (HL),A
    INC HL
    INC DE
    DJNZ _cs_attr_loop
    POP HL
    LD DE,STRIDE
    ADD HL,DE
    POP BC
    DJNZ _cs_row_loop
    RET

; ---------------------------------------------------------------------
; PRINT_STR — HL=0終端文字列の先頭。1文字ずつ PRINT_CHAR へ渡す
; ---------------------------------------------------------------------
PRINT_STR:
_ps_loop:
    LD A,(HL)
    OR A
    RET Z
    PUSH HL
    CALL PRINT_CHAR
    POP HL
    INC HL
    JR _ps_loop

; ---------------------------------------------------------------------
; PRINT_CHAR — A=文字コード。現在のカーソル位置に書き、桁を進める。
; 桁が COLS を超えたら NEWLINE を呼ぶ（自動折り返し）。
; ---------------------------------------------------------------------
PRINT_CHAR:
    PUSH AF
    LD HL,(VAR_ROWBASE)
    LD A,(VAR_COL)
    LD E,A
    LD D,0
    ADD HL,DE
    POP AF
    LD (HL),A
    LD A,(VAR_COL)
    INC A
    LD (VAR_COL),A
    CP COLS
    RET C
    CALL NEWLINE
    RET

; ---------------------------------------------------------------------
; NEWLINE — 桁=0、行を1つ進める。最終行を超えたら SCROLL する
; （l3-main.md 第5節：VRAMの書き写し）。
; ---------------------------------------------------------------------
NEWLINE:
    XOR A
    LD (VAR_COL),A
    LD A,(VAR_ROW)
    INC A
    CP ROWS
    JR C,_nl_no_scroll
    CALL SCROLL
    LD A,ROWS-1
    LD (VAR_ROW),A
    RET
_nl_no_scroll:
    LD (VAR_ROW),A
    LD HL,(VAR_ROWBASE)
    LD DE,STRIDE
    ADD HL,DE
    LD (VAR_ROWBASE),HL
    RET

; ---------------------------------------------------------------------
; SCROLL — VRAMを1行ぶん書き写す（l3-main.md 第5節）。
; 対象は先頭行を除く ROWS-1 行 = 120*(ROWS-1) バイトの連続コピー。
; 最終行（VAR_ROWBASEが指す、コピー前の最終行のアドレス＝コピー後は
; 空くべき行と同じ番地）を空白＋既定属性で埋め直す。
; ---------------------------------------------------------------------
SCROLL:
    LD HL,TEXT_BASE+STRIDE
    LD DE,TEXT_BASE
    LD BC,STRIDE*(ROWS-1)
    LDIR
    LD HL,(VAR_ROWBASE)
    LD B,COLS
    LD A,020h
_sc_txt_loop:
    LD (HL),A
    INC HL
    DJNZ _sc_txt_loop
    LD DE,DEFAULT_ATTR
    LD B,ATTR_BYTES
_sc_attr_loop:
    LD A,(DE)
    LD (HL),A
    INC HL
    INC DE
    DJNZ _sc_attr_loop
    RET

; ---------------------------------------------------------------------
; データ
; ---------------------------------------------------------------------
BANNER_TXT:
    DB "PC88Behavior v0.1",0
FILLER_TXT:
    DB "----FILLER----",0
OK_TXT:
    DB "Ok",0

; 既定の属性域（40バイト＝2バイト1組×20組）。値バイトのビット意味は
; l3-main.md 第3節・第8節で未確定のため、全組を(位置=0,値=0)とする
; （このファイル冒頭の注記を参照）。
DEFAULT_ATTR:
    DS 40,0   ; = ATTR_BYTES。DS の件数はpass1で評価するためEQUを使えない
