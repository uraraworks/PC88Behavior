; keyboard.asm — M7段階2b: キー入力(第8〜10節)と行入力。
;
; 根拠は docs/spec/l3-main.md（第8〜10節）と docs/spec/l1-ipl.md（第4b節、
; ポート00H-0BHの走査・「押されているビットが0」の規約）だけである。
; measurements/ も公式ROMも参照していない。
;
;   走査ポート00H-0BHの12個・押下ビット=0の規約   … l1-ipl.md 第4b節
;   D=10フレームの反映遅れ（実装側は不要。押下の立ち上がりを
;     見た瞬間に処理すればよく、ポーリング側の遅延を真似る理由が無い）
;                                                  … l3-main.md 第8節
;   0CH-0EHは走査しない（測定対象ROMの世代）        … l3-main.md 第8節
;   文字コード表（無修飾）                          … l3-main.md 第9節
;   修飾5種の効果・CAPS/カナは保持型               … l3-main.md 第10節
;   英字既定小文字・CAPS保持中大文字                … l3-main.md 第7節・第10節
;
; 表の実体（BASE_CODE_TAB等）は tools/gen_l3_key_table.py が
; docs/spec/l3-main.md 第9・10節から生成した key_table_gen.asm にある
; （手で打ち込んでいない）。
;
; 仕様書に無いため、この版で明示的に選んだ既定（推測で埋めず、選択として
; 記録する。報告の「仕様書に無いこと」参照）:
;   - SHIFT修飾は実コードが未確定（第15節-6）なので、SHIFT保持中は
;     押下を無視する（書かない扱い）。
;   - 複数の修飾を同時に押した場合の優先順位は仕様書に無い。この実装は
;     CTRL > GRPH > カナ > SHIFT(無視) > CAPS > 無修飾 の順で1つだけ適用する。
;   - RETURN（01H:7）は第9節の文字コード表に無い（未判定）ため、文字コード
;     としては生成しない。だがこの段階の目的（行入力の実装）のためRETURNの
;     押下そのものは検出し、「行を確定する」という専用の合図として特別扱い
;     する。コードそのものは仕様書に無い選択である。
;   - 1フレームに複数キーの押下エッジが同時に立った場合、ポート番号の
;     小さい方・ビット番号の小さい方を1つだけ処理する（仕様書に無い選択。
;     エミュレータでの打鍵注入は基本1フレーム1キーなので実運用に影響しない）。
;   - 内部行バッファ（LINE_BUF、80バイト）を超える入力は、画面には
;     エコーするが内部バッファには格納しない（BASICが無い現段階の最小実装。
;     RETURN時にオーバーフロー分はそのまま捨てる）。

KEY_PORT_N   EQU 12        ; l1-ipl.md 第4b節・l3-main.md 第8節：00H-0BHの12個
MOD_PORT     EQU 08h
GRPH_BIT     EQU 4
KANA_BIT     EQU 5
SHIFT_BIT    EQU 6
CTRL_BIT     EQU 7
CAPS_PORT    EQU 0Ah
CAPS_BIT     EQU 7
RETURN_PORT  EQU 01h
RETURN_BIT   EQU 7

; ---- RAM変数（screen.asmのVAR_ROW等と重ならない番地）----
KEY_OLD      EQU 0E810h    ; 直前スキャン12バイト（bit=1が「離されている」）
KEY_NEW      EQU 0E81Dh    ; 今回スキャン12バイト（一時領域）
VAR_LINELEN  EQU 0E82Ah    ; 行バッファに入っている文字数(0-80)
LINE_BUF     EQU 0E82Bh    ; 行バッファ本体（80バイト、null終端はしない）
LINE_BUF_CAP EQU 80

; ---------------------------------------------------------------------
; KEY_INIT — KEY_OLDを「全部離されている」(0xFF)で初期化する。
; ---------------------------------------------------------------------
KEY_INIT:
    LD HL,KEY_OLD
    LD B,KEY_PORT_N
    LD A,0FFh
_ki_loop:
    LD (HL),A
    INC HL
    DJNZ _ki_loop
    XOR A
    LD (VAR_LINELEN),A
    RET

; ---------------------------------------------------------------------
; KEY_READ — 1回ぶんのキースキャンをして、立ち上がりを1個だけ拾う。
;   戻り値: A = 0 (イベント無し) / 1 (通常の文字。Eに文字コード) /
;               2 (RETURNの押下)
; ---------------------------------------------------------------------
KEY_READ:
    ; 現在値をKEY_NEWへ読み込む(ポート0-11の昇順、l1-ipl.md第4b節の
    ; 走査対象と同じ12ポート。読む順序は本実装の選択で降順である必要は無い)
    LD C,0
    LD HL,KEY_NEW
_kr_scan:
    IN A,(C)
    LD (HL),A
    INC HL
    INC C
    LD A,C
    CP KEY_PORT_N
    JR NZ,_kr_scan

    ; 立ち上がり(旧=1・新=0)を探す。ポート昇順・ビット昇順で最初の1個。
    LD HL,KEY_OLD
    LD DE,KEY_NEW
    LD C,0                 ; C = ポート番号(0-11)
_kr_port_loop:
    LD A,(DE)
    CPL                    ; A = NOT(新値) … 押されているビットが1になる
    LD B,A
    LD A,(HL)
    AND B                  ; A = 旧値(離) AND 押されているビット = 立ち上がり
    OR A
    JR NZ,_kr_found_port
    INC HL
    INC DE
    INC C
    LD A,C
    CP KEY_PORT_N
    JR NZ,_kr_port_loop
    JR _kr_update_and_none

_kr_found_port:
    ; Aに立ち上がりビットのマスクが入っている。最下位の1ビットの番号を求める。
    LD B,0                  ; B = ビット番号
_kr_bit_loop:
    RRCA
    JR C,_kr_bit_found
    INC B
    JR _kr_bit_loop
_kr_bit_found:
    ; C=ポート番号、B=ビット番号。KEY_NEWの現在値からモディファイアを見る。
    PUSH BC
    CALL _kr_update_old      ; 先にKEY_OLD<-KEY_NEWを済ませる(以後の分岐でも必須)
    POP BC

    LD A,C
    CP RETURN_PORT
    JR NZ,_kr_not_return
    LD A,B
    CP RETURN_BIT
    JR NZ,_kr_not_return
    LD A,2                   ; RETURN
    RET
_kr_not_return:
    ; index = port*8 + bit
    LD A,C
    ADD A,A
    ADD A,A
    ADD A,A                  ; A = port*8
    ADD A,B
    LD E,A
    LD D,0                   ; DE = index

    LD A,(KEY_NEW+MOD_PORT)
    BIT CTRL_BIT,A
    JR NZ,_kr_try_grph
    LD HL,CTRL_CODE_TAB
    JR _kr_lookup
_kr_try_grph:
    LD A,(KEY_NEW+MOD_PORT)
    BIT GRPH_BIT,A
    JR NZ,_kr_try_kana
    LD HL,GRPH_CODE_TAB
    JR _kr_lookup
_kr_try_kana:
    LD A,(KEY_NEW+MOD_PORT)
    BIT KANA_BIT,A
    JR NZ,_kr_try_shift
    LD HL,KANA_CODE_TAB
    JR _kr_lookup
_kr_try_shift:
    LD A,(KEY_NEW+MOD_PORT)
    BIT SHIFT_BIT,A
    JR NZ,_kr_try_caps
    XOR A                     ; SHIFT保持中は無視（このファイル冒頭の注記）
    RET
_kr_try_caps:
    LD A,(KEY_NEW+CAPS_PORT)
    BIT CAPS_BIT,A
    JR NZ,_kr_use_base
    LD HL,CAPS_CODE_TAB
    JR _kr_lookup
_kr_use_base:
    LD HL,BASE_CODE_TAB
_kr_lookup:
    ADD HL,DE
    LD A,(HL)
    OR A
    JR Z,_kr_ignore
    LD E,A
    LD A,1
    RET
_kr_ignore:
    XOR A
    RET

_kr_update_and_none:
    CALL _kr_update_old
    XOR A
    RET

; KEY_NEW(12バイト) を KEY_OLD へコピーする。
_kr_update_old:
    LD HL,KEY_NEW
    LD DE,KEY_OLD
    LD BC,KEY_PORT_N
    LDIR
    RET

; ---------------------------------------------------------------------
; LINE_PUTCHAR — A=文字コード。カーソル位置へエコーしつつ行バッファへ積む。
; ---------------------------------------------------------------------
LINE_PUTCHAR:
    PUSH AF
    LD A,(VAR_LINELEN)
    CP LINE_BUF_CAP
    JR NC,_lp_skip_store     ; バッファ満杯: エコーだけ行い格納は捨てる(選択、冒頭注記)
    LD HL,LINE_BUF
    LD E,A
    LD D,0
    ADD HL,DE
    POP AF
    PUSH AF
    LD (HL),A
    LD A,(VAR_LINELEN)
    INC A
    LD (VAR_LINELEN),A
_lp_skip_store:
    POP AF
    CALL PRINT_CHAR
    RET

; ---------------------------------------------------------------------
; LINE_FINISH — RETUNRの押下。行を確定し、改行してOkを出す。
; ---------------------------------------------------------------------
LINE_FINISH:
    XOR A
    LD (VAR_LINELEN),A
    CALL NEWLINE
    LD HL,OK_TXT
    CALL PRINT_STR
    CALL NEWLINE
    RET

; ---------------------------------------------------------------------
; SET_CURSOR — CRTC LOAD CURSOR POSITION のパラメータ(X,Y)を、現在の
; カーソル位置(VAR_COL,VAR_ROW)から出す(l1-ipl.md 第5d節のコマンド書式。
; コマンドバイト自体はVSYNCハンドラ側で既に0x81を出しているので、
; ここではパラメータ2バイトだけを出す)。
; ---------------------------------------------------------------------
SET_CURSOR:
    LD A,(VAR_COL)
    OUT (50h),A
    LD A,(VAR_ROW)
    OUT (50h),A
    RET

; ---------------------------------------------------------------------
; L3_VSYNC_HOOK — VSYNCハンドラから毎フレーム1回呼ばれる
; (build_main_rom.pyがVSYNCハンドラの固定カーソル出力2個をこの呼び出しへ
; 置き換える)。キー入力→行入力の処理をしてから、カーソル位置を出す。
; ---------------------------------------------------------------------
L3_VSYNC_HOOK:
    CALL KEY_READ
    OR A
    JR Z,_hook_done
    CP 2
    JR Z,_hook_return
    LD A,E
    CALL LINE_PUTCHAR
    JR _hook_done
_hook_return:
    CALL LINE_FINISH
_hook_done:
    CALL SET_CURSOR
    RET
