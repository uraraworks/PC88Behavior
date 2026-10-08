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

TEXT_BASE   EQU MM_TEXT_BASE   ; l3-main.md 第2節
STRIDE      EQU 120      ; l3-main.md 第1節（80桁+40属性）
COLS        EQU 80       ; 起動時の桁数。行の文字域のバイト数（桁数40でも80バイト。l4-program.md 5.6.1）
ATTR_BYTES  EQU 40
ROWS        EQU 20       ; docs/spec/l1-ipl.md 第0節（起動時の実際の表示行数）
; 第15節（fkey_row_reserved）: ファンクションキー表示ありの既定では、
; スクロール・PRINTの対象範囲は表示行数-1。最下行(row0=ROWS-1=19)は
; ファンクションキー表示の行として予約し、スクロール対象から外す。
; WIDTH（l4-program.md 4.22・5.6）で桁数・行数が変わる。現在値は下のRAM変数。
USABLE_ROWS EQU ROWS-1
SCR_COLS    EQU MM_SCR_COLS     ; 現在の桁数（40か80）
SCR_MAXROW  EQU MM_SCR_MAXROW   ; 現在の最終の使用行（行0始まり。行数-2。起動時18、25行で23）
SCR_P31     EQU MM_SCR_P31      ; 垂直同期のたびにポート0x31へ出す値（20行0x19・25行0x39。l4-program.md 5.6.5）
SCR_MODE    EQU MM_SCR_MODE     ; bit0=カラーモード（console ,,,1。l4-program.md 5.4.5・5.4.6）、bit5=INPUT待ちで見た垂直帰線の位相（RUN_CURSOR_INPUT）
SCR_ZT      EQU MM_SCR_ZT       ; bit0-4=コンマ欄の改行閾値T÷2（80桁28・40桁7。l4-program.md 4.22.4）、bit5-7=現在の COLOR 値（5.4。0〜7）

; ---- RAM変数（0000-7FFFはROM＝L1のROM/RAMモード設定のため書けない。
;      8000-FFFF側の、VRAM(F3C8-)ともスタック(F000から下方)とも
;      重ならない番地を選ぶ）----
VAR_ROW     EQU MM_VAR_ROW   ; 現在の行 (0-19)
VAR_COL     EQU MM_VAR_COL   ; 現在の桁 (0-79)
VAR_ROWBASE EQU MM_VAR_ROWBASE   ; 現在行のVRAM先頭番地（2バイト）

; ---------------------------------------------------------------------
; SCREEN_MAIN — 画面初期化 → 自作バナー → (試験用の埋め草) → Ok
; ---------------------------------------------------------------------
SCREEN_MAIN:
    XOR A
    LD (SAVE_CAPTURE_ACTIVE),A
    LD (SAVE_DONE_FLAG),A
    LD (VAR_ROW),A
    LD (VAR_COL),A
    LD (SCR_MODE),A             ; 起動直後は白黒モード（l4-program.md 5.4.5）
    LD HL,TEXT_BASE
    LD (VAR_ROWBASE),HL
    LD HL,((ROWS-2)<<8)|COLS    ; 起動時の桁数80・最終使用行18（WIDTHの状態）
    LD (SCR_COLS),HL
    LD HL,(28<<8)|019h          ; ポート0x31の値0x19（20行）・コンマ欄閾値56÷2・COLOR 値0
    LD (SCR_P31),HL
    CALL CLEAR_SCREEN
    CALL KEY_INIT           ; keyboard.asm — KEY_OLDを初期化（M7段階2b）
    CALL PROGRAM_INIT       ; l4_basic/program.asm — プログラム領域を
                             ; 空にする（M7段階5a、未初期化のまま読まない）

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
; CLEAR_SCREEN — 起動時の全20行を空白＋既定の属性で埋める
; ---------------------------------------------------------------------
CLEAR_SCREEN:
    LD B,ROWS
    LD HL,TEXT_BASE
    JP CLEAR_N_ROWS

; ---------------------------------------------------------------------
; CLEAR_N_ROWS — HL=先頭VRAM番地、B=消す行数。空白＋既定の属性で埋める
;   (CLEAR_SCREENの本体を切り出した共通部、M7段階5c-2a追記)。
;   WIDTH（l4-program.md 5.6.4）の3000バイト全体の消去（B=25）もここを使う。
; ---------------------------------------------------------------------
CLEAR_N_ROWS:
_cn_loop:
    PUSH BC
    CALL CLEAR_ROW
    POP BC
    DJNZ _cn_loop
    RET

; ---------------------------------------------------------------------
; CLEAR_ROW — HL=行の先頭。文字域80バイトを空白、属性域を既定の20組
;   (位置0x80,値0x00。l3-main.md 第14節・l4-program.md 5.6.2)にして、
;   HLは次の行の先頭（120バイト先）になる。破壊: AF,BC,HL。
;   既定の属性は40バイトの表でなく同じ値の繰り返しとして書く（mainの空き節約）。
; ---------------------------------------------------------------------
CLEAR_ROW:
    LD B,COLS
    LD A,020h
_cr_txt:
    LD (HL),A
    INC HL
    DJNZ _cr_txt
    LD A,(SCR_MODE)             ; 既定の属性値: 白黒 0x00、カラー 0xE8（l3-main.md 第14節）
    AND 1
    JR Z,_cr_mono
    LD A,0E8h
_cr_mono:
    LD C,A
    LD B,ATTR_BYTES/2
_cr_attr:
    LD (HL),080h
    INC HL
    LD (HL),C
    INC HL
    DJNZ _cr_attr
    RET

; ---------------------------------------------------------------------
; CLS_SCREEN — M7段階5c-2a: `CLS`文の本体(docs/spec/l4-program.md
;   第5.1節)。ファンクションキー表示行（最下行、予約行）を除く
;   現在の使用行数(SCR_MAXROW+1)行だけを空白＋既定の属性で埋め、
;   カーソルを絶対行0・桁0へ戻す(第5.1節F1「消した後に残るのはOk相当の行と
;   ファンクションキー表示の行だけ」——予約行を対象外にする構造はスクロール
;   対象と同じNEWLINE/SCROLLの規約(第15節)をそのまま流用)。
; ---------------------------------------------------------------------
; (build_main_rom.pyの故障注入FAULT_OLD/NEWは、SCREEN_MAINの
;  "LD HL,TEXT_BASE"直後に"LD (VAR_ROWBASE),HL"が続く2行を対象に一意に
;  検索するため、ここでは同じ並びを作らないよう命令の順序をずらす
;  〔仕様書に無い判断、実装上の都合のみ〕。)
CLS_SCREEN:
    LD A,(SCR_MAXROW)
    INC A
    LD B,A
    LD HL,TEXT_BASE
    CALL CLEAR_N_ROWS
    LD HL,TEXT_BASE
    XOR A
    LD (VAR_ROW),A
    LD (VAR_COL),A
    LD (VAR_ROWBASE),HL
    RET

; LOCATE（第5.2節）の本体と COLOR（第5.4節）の本体は拡張ROMバンク0
; （src/l4_basic/widthbeep.asm の wb_locate・wb_color）へ移した。
; 呼び出しは run.asm の LOCATE_STMT・COLOR_STMT。

; ---------------------------------------------------------------------
; CELL_PTR — A=桁(0始まり)。HL=現在行のその桁の文字のVRAM番地
;   (80桁は ROWBASE+桁、40桁は ROWBASE+2×桁。l4-program.md 5.6.1)。
;   破壊: AF,DE,HL。BCは保つ。
; ---------------------------------------------------------------------
CELL_PTR:
    LD HL,(VAR_ROWBASE)
    LD E,A
    LD D,0
    ADD HL,DE
    LD A,(SCR_COLS)
    CP COLS
    RET Z
    ADD HL,DE
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
    LD A,(SAVE_CAPTURE_ACTIVE)
    OR A
    JR Z,_pc_no_capture
    POP AF
    JP SAVE_CAPTURE_CHAR
_pc_no_capture:
    POP AF
    CP 7                        ; 第4.22節: BEL(CHR$(7))は表示せず BEEP と同じ音だけ鳴らす
    JR Z,_pc_bell
    PUSH AF
    LD A,(VAR_COL)
    CALL CELL_PTR
    POP AF
    LD (HL),A
    LD A,(SCR_MODE)             ; カラーモードは既定の値が 0xE8 で、色0も組を書くので常に呼ぶ（5.4.5）
    AND 1
    JR NZ,_pc_attr
    LD A,(SCR_ZT)               ; l4-program.md 5.4・5.6.2: 印字したセルの色を属性域の組へ反映する。
    AND 0E0h                    ; 白黒の色0で行に組が無い（組0の位置が0x80）ときは何も書かないので呼ばない
    JR NZ,_pc_attr
    LD HL,(VAR_ROWBASE)
    LD DE,COLS
    ADD HL,DE
    BIT 7,(HL)
    JR NZ,_pc_adv
_pc_attr:
    PUSH BC
    LD HL,07A54h                ; バンク0 wb_attr（widthbeep.asm）
    XOR A
    CALL EXT_BANK_CALL
    POP BC
_pc_adv:
    LD A,(VAR_COL)
    INC A
    LD (VAR_COL),A
    LD E,A
    LD A,(SCR_COLS)
    CP E                        ; 桁が現在の桁数に達したら自動折り返し
    RET NZ
    JP NEWLINE
_pc_bell:
    PUSH BC                     ; 呼び出し元(文字列の出力ループ)がBCを使う
    CALL BEEP_BELL
    POP BC
    RET

; ---------------------------------------------------------------------
; NEWLINE — 桁=0、行を1つ進める。最終「使用可能」行を超えたら SCROLL する
; （l3-main.md 第5節：VRAMの書き写し）。最下行(row0=ROWS-1)は第15節
; （fkey_row_reserved）によりファンクションキー表示用に予約し、
; カーソル・スクロールの対象から外す（対象はrow0=0〜USABLE_ROWS-1）。
; ---------------------------------------------------------------------
NEWLINE:
    LD A,(SAVE_CAPTURE_ACTIVE)
    OR A
    JP NZ,SAVE_CAPTURE_NEWLINE
    XOR A
    LD (VAR_COL),A
    LD A,(SCR_MAXROW)
    INC A                       ; 使用行数
    LD E,A
    LD A,(VAR_ROW)
    INC A
    CP E
    JR C,_nl_no_scroll
    CALL SCROLL
    LD A,(SCR_MAXROW)
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
    LD A,(SCR_MAXROW)           ; 書き写す行数 = 使用行数-1 = 最終使用行
    LD B,A
    LD HL,0
    LD DE,STRIDE
_sc_mul:
    ADD HL,DE
    DJNZ _sc_mul
    LD B,H
    LD C,L                      ; BC = STRIDE*(使用行数-1)
    LD HL,TEXT_BASE+STRIDE
    LD DE,TEXT_BASE
    LDIR
    LD HL,(VAR_ROWBASE)
    JP CLEAR_ROW

; ---------------------------------------------------------------------
; データ
; ---------------------------------------------------------------------
BANNER_TXT:
    DB "PC88Behavior v0.1",0
FILLER_TXT:
    DB "----FILLER----",0
OK_TXT:
    DB "Ok",0

; 既定の属性域（40バイト＝2バイト1組×20組、(位置0x80,値0x00)×20組。l3-main.md 第14節
; nonzero_pattern）は CLEAR_ROW が同じ値の繰り返しとして書く（旧DEFAULT_ATTR表は廃止）。
; 起動直後は白黒（第11節）。カラーの既定(0x80,0xE8)×20組は SCR_MODE のbit0が立っているとき CLEAR_ROW が書く。
