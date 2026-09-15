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
; M7段階2c追記: 既定の属性域のバイト値（第14節）とスクロール範囲の
; ファンクションキー行予約（第15節）を反映した。起動直後は白黒（第11節）
; なので、既定の属性値は白黒の並び(80,00)×20組を使う。カラーモードの
; 既定値(80,E8)×20組は、この段階ではCOLOR/CONSOLEを実装していない
; （白黒のみ）ため使わない。
;
; 仕様書に無いため、この版で明示的に選んだ既定（推測で埋めず、選択として
; 記録する。報告の「仕様書に無いこと」参照）:
;   - 最下行（ファンクションキー表示の行として予約する行、row0=19）に
;     何を出すかは第13節が「本測定の対象外」としているため、この実装は
;     空白＋既定属性のまま何も出さない選択をした（公式の文字は再現しない）。
;     初期化時に一度だけ埋め、以後スクロール・PRINTの対象にはしない。
;   - 属性域40バイトの各組の値バイトの各ビット意味は第3節・第16節-1で
;     未確定のため、既定並びの再現以上のことはしない
;     （COLOR等で個別のビットを操作する機能はまだ実装していない）。
;
; バナー文言は自作の名前・バージョンのみ（禁止事項6・
; docs/notes/banner-attribution-2026-08-16.md）。公式の製品名・
; 著作権表示は含まない。
;
; M7段階2b追記: カーソルの追従・キー入力・行入力は keyboard.asm にある。
; build_main_rom.py が、L1のVSYNCハンドラが毎フレーム出す固定カーソル位置
; (22,1)のOUTを keyboard.asm の L3_VSYNC_HOOK 呼び出しに置き換える
; （make_ipl_rom.py 自体は無変更）。

TEXT_BASE   EQU 0F3C8h   ; l3-main.md 第2節
STRIDE      EQU 120      ; l3-main.md 第1節（80桁+40属性）
COLS        EQU 80
ATTR_BYTES  EQU 40
ROWS        EQU 20       ; docs/spec/l1-ipl.md 第0節（起動時の実際の表示行数）
; 第15節（fkey_row_reserved）: ファンクションキー表示ありの既定では、
; スクロール・PRINTの対象範囲は表示行数-1。最下行(row0=ROWS-1=19)は
; ファンクションキー表示の行として予約し、スクロール対象から外す。
USABLE_ROWS EQU ROWS-1

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
    CALL KEY_INIT           ; keyboard.asm — KEY_OLDを初期化（M7段階2b）

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
; NEWLINE — 桁=0、行を1つ進める。最終「使用可能」行を超えたら SCROLL する
; （l3-main.md 第5節：VRAMの書き写し）。最下行(row0=ROWS-1)は第15節
; （fkey_row_reserved）によりファンクションキー表示用に予約し、
; カーソル・スクロールの対象から外す（対象はrow0=0〜USABLE_ROWS-1）。
; ---------------------------------------------------------------------
NEWLINE:
    XOR A
    LD (VAR_COL),A
    LD A,(VAR_ROW)
    INC A
    CP USABLE_ROWS
    JR C,_nl_no_scroll
    CALL SCROLL
    LD A,USABLE_ROWS-1
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
; 対象は使用可能な先頭行を除く USABLE_ROWS-1 行 =
; 120*(USABLE_ROWS-1) バイトの連続コピー（第15節: ファンクションキー
; 表示ありの既定では範囲は表示行数-1＝USABLE_ROWS）。
; 最終使用可能行（VAR_ROWBASEが指す、コピー前の最終使用可能行の
; アドレス＝コピー後は空くべき行と同じ番地）を空白＋既定属性で埋め直す。
; 最下行（ファンクションキー表示の予約行）はここでは一切触らない。
; ---------------------------------------------------------------------
SCROLL:
    LD HL,TEXT_BASE+STRIDE
    LD DE,TEXT_BASE
    LD BC,STRIDE*(USABLE_ROWS-1)
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

; 既定の属性域（40バイト＝2バイト1組×20組）。l3-main.md 第14節
; （nonzero_pattern）の白黒既定: (位置,値)=(0x80,0x00)×20組。
; 起動直後は白黒（第11節）なのでこの並びを使う。カラーの既定
; (0x80,0xE8)×20組はこの段階では使わない（COLOR/CONSOLE未実装）。
; 各組の値バイトの各ビット意味は第3節・第16節-1で未確定。
DEFAULT_ATTR:
    DB 080h,000h, 080h,000h, 080h,000h, 080h,000h, 080h,000h
    DB 080h,000h, 080h,000h, 080h,000h, 080h,000h, 080h,000h
    DB 080h,000h, 080h,000h, 080h,000h, 080h,000h, 080h,000h
    DB 080h,000h, 080h,000h, 080h,000h, 080h,000h, 080h,000h
    ; = ATTR_BYTES(40)バイト＝20組
