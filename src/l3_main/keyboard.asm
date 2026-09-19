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
; M7段階2c追記: SHIFTは第10節SHIFT列（`e915172`実測）が埋まったため、
; SHIFT_CODE_TAB（key_table_gen.asm、生成器で作成）で通常のキーと同様に
; 引く。無視する選択はやめた。
;
; 仕様書に無いため、この版で明示的に選んだ既定（推測で埋めず、選択として
; 記録する。報告の「仕様書に無いこと」参照）:
;   - 複数の修飾を同時に押した場合の優先順位は仕様書に無い。この実装は
;     CTRL > GRPH > カナ > SHIFT > CAPS > 無修飾 の順で1つだけ適用する。
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
;
; M7段階3b追記2 — SPACE(09H:6)の扱い。l3-main.md 第3.1版第9節末尾の
; 追記により、打った行のエコーでSPACEを押すとカーソルが1桁進むという
; 観測が加わった（段階3bまでの本実装はSPACEを「書かない」＝無視する
; 選択で、この前進を実装していなかった）。ただし同節は「0x20を書いて
; 進むのか、書かずに進むだけなのかは区別できない」とも明記している。
;   - **この実装は「0x20を書いて進む」を選ぶ**（選択、仕様書に無い）。
;     理由: 通常の文字キーと同じ LINE_PUTCHAR(エコー+行バッファ格納)を
;     そのまま再利用でき、実装が単純になる。加えて interp.asm の
;     SKIP_SPACES（l4_basic側、直接モードのPRINT解析）は既に行バッファ
;     中の 0x20 をスキップする設計になっており、SPACEが行バッファへ
;     0x20 を積む前提と自然に噛み合う。
;   - **行バッファにも0x20を1文字として積む**（LINE_PUTCHARをそのまま
;     通すため）。`PRINT 1` のように打った場合、行バッファは
;     "PRINT 1"（0x20を含む8バイト）になり、DIRECT_LINE/PRINT_STMTの
;     SKIP_SPACESがこの0x20を読み飛ばして"1"を数値として解釈する
;     （BASICの字句解析が空白を意味の無い区切りとして扱うことと整合）。
;   - SPACEと修飾(SHIFT等)の組は、l3-main.md 第9節・第10節のどちらの
;     表にも 09:6 の行が無い（無修飾コード表(第9節)にも修飾表(第10節)
;     にも含まれない）。この実装は指示どおり「表に無ければ無視」を
;     採り、修飾キーの状態に関わらず常にこの既定の0x20前進を行う
;     （後述のとおりモディファイア判定より前で分岐し、通常のコード表
;     参照には進まない）。

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
SPACE_PORT   EQU 09h    ; l3-main.md 第9節末尾の追記（M7段階3b追記2）
SPACE_BIT    EQU 6

; ---- 第16節: スクリーンエディタ（編集キー）4種8条件。いずれもMOD_PORT
; (08h)・CAPS_PORT(0Ah)と同じポートのビットを使う(l3-main.md第16節見出し
; の port:bit 表記のとおり)。専用の名前は付けず、既存のポート定数を使い
; 回す（RETURN/SPACEと同じやり方）。
HOME_BIT     EQU 0        ; MOD_PORT bit0: HOME/CLR (無修飾=clear/SHIFT=home)
UP_BIT       EQU 1        ; MOD_PORT bit1: ↑ (row_move)
RIGHT_BIT    EQU 2        ; MOD_PORT bit2: → (no_change/wrap_to_next_line)
INSDEL_BIT   EQU 3        ; MOD_PORT bit3: INS/DEL (無修飾=del_left/SHIFT=ins_mode_only)
DOWN_BIT     EQU 1        ; CAPS_PORT bit1: ↓ (row_move)
LEFT_BIT     EQU 2        ; CAPS_PORT bit2: ← (no_change/wrap_prev_line_end)

; ---- RAM変数（screen.asmのVAR_ROW等と重ならない番地）----
KEY_OLD      EQU 0E810h    ; 直前スキャン12バイト（bit=1が「離されている」）
KEY_NEW      EQU 0E81Dh    ; 今回スキャン12バイト（一時領域）
VAR_LINELEN  EQU 0E82Ah    ; 行バッファに入っている文字数(0-80)
LINE_BUF     EQU 0E82Bh    ; 行バッファ本体（80バイト、null終端はしない）
LINE_BUF_CAP EQU 80
VAR_INSMODE  EQU 0E87Bh    ; 1バイト。第16節ins_mode_only: 1=挿入モード中。
                            ; 抜ける条件は未測定(第18節項8)。この実装は
                            ; RETURNで行を確定した時点で解除する(選択)。

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
    LD (VAR_INSMODE),A
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
    JP _kr_update_and_none

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
    LD A,C
    CP SPACE_PORT
    JR NZ,_kr_not_space
    LD A,B
    CP SPACE_BIT
    JR NZ,_kr_not_space
    ; SPACE(09H:6) — 冒頭注記(M7段階3b追記2)のとおり、修飾の有無に
    ; 関わらず常に0x20を書いて1桁進める(通常の文字と同じLINE_PUTCHAR
    ; 経路をそのまま使うため、A=1・E=0x20をそのまま返す)。
    LD E,020h
    LD A,1
    RET
_kr_not_space:
    ; 第16節: MOD_PORT(08h)の下位4ビット=HOME/CLR・↑・→・INS/DEL。
    ; 修飾(SHIFT)の有無に関わらずここで拾う(矢印は無修飾しか測定していない
    ; ため常にこの経路。HOME/CLR・INS/DELはSHIFTの有無で分岐する)。
    ; いずれも文字コードを生成せず、この場でカーソル/画面を直接操作して
    ; A=0(イベント無し扱い)で返す — L3_VSYNC_HOOK側の変更を要さないため。
    LD A,C
    CP MOD_PORT
    JR NZ,_kr_try_down_left
    LD A,B
    CP HOME_BIT
    JR Z,_kr_home_or_clr
    LD A,B
    CP UP_BIT
    JR Z,_kr_do_up
    LD A,B
    CP RIGHT_BIT
    JR Z,_kr_do_right
    LD A,B
    CP INSDEL_BIT
    JR Z,_kr_ins_or_del
    JR _kr_not_edit
_kr_try_down_left:
    LD A,C
    CP CAPS_PORT
    JR NZ,_kr_not_edit
    LD A,B
    CP DOWN_BIT
    JR Z,_kr_do_down
    LD A,B
    CP LEFT_BIT
    JR Z,_kr_do_left
    JR _kr_not_edit
_kr_do_up:
    CALL KEY_CURSOR_UP
    XOR A
    RET
_kr_do_down:
    CALL KEY_CURSOR_DOWN
    XOR A
    RET
_kr_do_left:
    CALL KEY_CURSOR_LEFT
    XOR A
    RET
_kr_do_right:
    CALL KEY_CURSOR_RIGHT
    XOR A
    RET
_kr_home_or_clr:
    LD A,(KEY_NEW+MOD_PORT)
    BIT SHIFT_BIT,A
    JR NZ,_kr_do_clr          ; SHIFT無し(bit=1=離): 無修飾=clear
    CALL KEY_HOME               ; SHIFT有り(bit=0=押下): home
    XOR A
    RET
_kr_do_clr:
    CALL CLS_SCREEN
    XOR A
    RET
_kr_ins_or_del:
    LD A,(KEY_NEW+MOD_PORT)
    BIT SHIFT_BIT,A
    JR NZ,_kr_do_del           ; SHIFT無し: 無修飾=del_left
    CALL KEY_ENTER_INSERT       ; SHIFT有り: ins_mode_only
    XOR A
    RET
_kr_do_del:
    CALL KEY_DEL_LEFT
    XOR A
    RET
_kr_not_edit:
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
    LD HL,SHIFT_CODE_TAB
    JR _kr_lookup
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
;   第16節ins_mode_only追記: VAR_INSMODE=1のときはPRINT_CHAR(上書き)の
;   代わりにINSERT_PUTCHAR(カーソルから列79までを右へ押し出してから書く)
;   を使う。行バッファへの格納は変更しない(LINE_BUFはRETURN時に
;   LINE_READ_FROM_SCREENが画面から丸ごと作り直すため、ここでの格納内容
;   自体はもう直接モードの実行には使われないが、既存の経路を壊さない
;   ため残す)。
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
    LD C,A
    LD A,(VAR_INSMODE)
    OR A
    LD A,C
    JR Z,_lp_overwrite
    CALL INSERT_PUTCHAR
    RET
_lp_overwrite:
    CALL PRINT_CHAR
    RET

; ---------------------------------------------------------------------
; LINE_FINISH — RETUNRの押下。行を確定し、改行してOkを出す。
;
; M7段階3b追記: 改行の直後（出力行の先頭、桁0）で BASIC_RUN_LINE
; （l4_basic/interp.asm）を呼び、直接モードのPRINTを実行する。
; Okの前に必ず桁0から始めるという統一規則(interp.asmの冒頭コメント参照、
; 仕様書に無い選択)により、BASIC_RUN_LINE実行後にVAR_COLを見て桁0でなければ
; 改行を1つ足す(通常完了・構文の誤りのいずれも既に桁0のため実際には
; 効かない。行末の区切りで改行が抑止されたまま行が終わる未測定の場合に
; だけ効く安全策)。
;
; M7段階5a追記: BASIC_RUN_LINE の代わりに program.asm の
; BASIC_HANDLE_LINE を呼ぶ。行番号つきの行（プログラムモード）は
; l4-program.md 第1節のとおり無出力（Ok も出ない）なので、
; BASIC_HANDLE_LINE が A=1 を返したときはOk表示を丸ごと飛ばす。
;
; 第16・17節追記: RETURNを押した時点でカーソルがある行のVRAM内容を
; LINE_READ_FROM_SCREENでLINE_BUF/VAR_LINELENへ複製してから実行する
; (whole_line・reads_whole_row、第17節)。NEWLINEを呼ぶ前(=カーソルが
; まだその行にある間)に行う必要がある。挿入モード(VAR_INSMODE)は
; ここで解除する(抜ける条件は未測定、第18節項8の選択)。
; ---------------------------------------------------------------------
LINE_FINISH:
    CALL LINE_READ_FROM_SCREEN
    XOR A
    LD (VAR_INSMODE),A
    CALL NEWLINE
    CALL BASIC_HANDLE_LINE
    PUSH AF
    XOR A
    LD (VAR_LINELEN),A
    POP AF
    OR A
    JR NZ,_lf_done            ; 行番号つきの行: 無出力のまま終わる(第1節)
    LD A,(VAR_COL)
    OR A
    JR Z,_lf_ok
    CALL NEWLINE
_lf_ok:
    LD HL,OK_TXT
    CALL PRINT_STR
    CALL NEWLINE
_lf_done:
    RET

; ---------------------------------------------------------------------
; LINE_READ_FROM_SCREEN — 第17節（whole_line・reads_whole_row）。
;   現在のカーソル行(VAR_ROWBASEが指す80桁)をそのままLINE_BUFへ複製する。
;   カーソルの列位置には依存しない(第17節「カーソル位置に依存する候補は
;   採用されず、常に行全体が読まれる」)。上書きされずに残った行末の
;   古い文字(空白でないもの)もそのまま複製されるため、reads_whole_rowの
;   結果はそのまま保たれる。
;
;   末尾が空白(0x20)の並びだけはVAR_LINELENから除く(仕様書に無い選択)。
;   直接モードの構文解析(DIRECT_LINEのSKIP_SPACES+AT_END)は行末の空白を
;   もともと無視するため実行結果は変わらない。これを省くと、まっさらな
;   行(残りが既定の空白で埋まっている行)を打っただけでも本文長が常に
;   COLS(80)になり、program.asm PROGRAM_STORE_LINEが「行番号より後ろ
;   全部」を本文として保存してしまい、LIST時に大量の末尾空白が付いて
;   1行が画面上2行にまたがる(自動折り返し)という別の不具合を生むため。
; ---------------------------------------------------------------------
LINE_READ_FROM_SCREEN:
    LD HL,(VAR_ROWBASE)
    LD DE,LINE_BUF
    LD BC,COLS
    LDIR
    LD HL,LINE_BUF+COLS-1
    LD B,COLS
_lrfs_trim:
    LD A,B
    OR A
    JR Z,_lrfs_done
    LD A,(HL)
    CP 020h
    JR NZ,_lrfs_done
    DEC HL
    DEC B
    JR _lrfs_trim
_lrfs_done:
    LD A,B
    LD (VAR_LINELEN),A
    RET

; ---------------------------------------------------------------------
; INSERT_PUTCHAR — A=文字コード。第16節ins_mode_only:
;   カーソル位置から列79までの内容を1つ右へ押し出し(列79の元の内容は
;   失われる)、カーソル位置にAを書き、カーソルを1つ右へ進める。
;   列79で押されたときは押し出す先が無いため上書きのみ行い、カーソルは
;   進めない(挿入モードで列79まで詰まった行への挿入の挙動は未測定、
;   仕様未確定・第18節項8。この実装は最小の安全策として「これ以上は
;   崩さない」を選ぶ)。破壊: AF,BC,DE,HL。
; ---------------------------------------------------------------------
INSERT_PUTCHAR:
    PUSH AF
    LD A,(VAR_COL)
    LD C,A
    CP COLS-1
    JR NC,_ip_no_shift
    LD A,COLS-1
    SUB C
    LD B,A                    ; B = 押し出す回数 = (COLS-1)-col
    LD HL,(VAR_ROWBASE)
    LD DE,COLS-1
    ADD HL,DE                 ; HL = dst = ROWBASE+(COLS-1)
_ip_shift_loop:
    LD D,H
    LD E,L
    DEC DE                    ; DE = src = dst-1
    LD A,(DE)
    LD (HL),A
    LD H,D
    LD L,E                    ; 次の周のdst = 今回のsrc
    DJNZ _ip_shift_loop
_ip_no_shift:
    LD HL,(VAR_ROWBASE)
    LD E,C
    LD D,0
    ADD HL,DE                 ; HL = ROWBASE+col = 書き込み位置
    POP AF
    LD (HL),A
    LD A,C
    CP COLS-1
    JR NC,_ip_no_advance       ; 既に列79なら進めない(選択、上記コメント参照)
    INC A
    LD (VAR_COL),A
_ip_no_advance:
    RET

; ---------------------------------------------------------------------
; 第16節: スクリーンエディタ（編集キー）の実体。いずれもKEY_READから直接
; 呼ばれ、カーソル(VAR_ROW/VAR_COL/VAR_ROWBASE)または画面(VRAM)だけを
; 操作する。文字コードは生成しない。
; ---------------------------------------------------------------------

; KEY_CURSOR_UP — ↑(row_move)。同じ列のまま1行上へ。行0では無反応
; (真の境界での挙動は本節の測定対象外。仕様書に無い、安全側の選択)。
KEY_CURSOR_UP:
    LD A,(VAR_ROW)
    OR A
    RET Z
    DEC A
    LD (VAR_ROW),A
    LD HL,(VAR_ROWBASE)
    LD DE,STRIDE
    OR A
    SBC HL,DE
    LD (VAR_ROWBASE),HL
    RET

; KEY_CURSOR_DOWN — ↓(row_move)。同じ列のまま1行下へ。最終使用可能行
; (USABLE_ROWS-1、ファンクションキー予約行の手前)では無反応
; (仕様書に無い、安全側の選択。LOCATE_SET_CURSORの範囲丸めと同じ境界)。
KEY_CURSOR_DOWN:
    LD A,(VAR_ROW)
    CP USABLE_ROWS-1
    RET NC
    INC A
    LD (VAR_ROW),A
    LD HL,(VAR_ROWBASE)
    LD DE,STRIDE
    ADD HL,DE
    LD (VAR_ROWBASE),HL
    RET

; KEY_CURSOR_LEFT — ←。行の途中はno_change(1列左へ)。列0の真の境界では
; 前の行の列79へ回り込む(wrap_prev_line_end、内容の有無によらず常に
; 起こる)。行0・列0(画面左上)では、それより上に行が無いため無反応
; (この組み合わせは本節の測定対象外。仕様書に無い、安全側の選択)。
KEY_CURSOR_LEFT:
    LD A,(VAR_COL)
    OR A
    JR Z,_kcl_boundary
    DEC A
    LD (VAR_COL),A
    RET
_kcl_boundary:
    LD A,(VAR_ROW)
    OR A
    RET Z
    DEC A
    LD (VAR_ROW),A
    LD A,COLS-1
    LD (VAR_COL),A
    LD HL,(VAR_ROWBASE)
    LD DE,STRIDE
    OR A
    SBC HL,DE
    LD (VAR_ROWBASE),HL
    RET

; KEY_CURSOR_RIGHT — →。行の途中はno_change(1列右へ)。列79の境界では
; 次の行の列0へ進む(長押しでのwrap_to_next_line、境界での停止は観測
; されなかった。単発押下の挙動は未測定だが同じ動きを採る、仕様未確定・
; 第18節項8)。最終使用可能行の列79では、それより下に行が無いため無反応
; (この組み合わせは本節の測定対象外。仕様書に無い、安全側の選択)。
KEY_CURSOR_RIGHT:
    LD A,(VAR_COL)
    CP COLS-1
    JR Z,_kcr_boundary
    INC A
    LD (VAR_COL),A
    RET
_kcr_boundary:
    LD A,(VAR_ROW)
    CP USABLE_ROWS-1
    RET Z
    INC A
    LD (VAR_ROW),A
    XOR A
    LD (VAR_COL),A
    LD HL,(VAR_ROWBASE)
    LD DE,STRIDE
    ADD HL,DE
    LD (VAR_ROWBASE),HL
    RET

; KEY_DEL_LEFT — INS/DEL無修飾(del_left)。カーソルの左の文字を1つ除き、
; 後続の文字(同じ行、列79まで)を左へ1つ詰める。列79は空白で埋める。
; 真の境界(列0)では常に無反応(boundary_no_op。前の行の内容の有無に
; よらない)。破壊: AF,BC,DE,HL。
KEY_DEL_LEFT:
    LD A,(VAR_COL)
    OR A
    RET Z
    DEC A
    LD (VAR_COL),A
    LD C,A                     ; C = 削除位置(新カーソル位置)
    LD B,0
    LD HL,(VAR_ROWBASE)
    ADD HL,BC
    PUSH HL                    ; dstをスタックへ退避
    INC HL                     ; HL = src = ROWBASE+col+1
    LD B,COLS-1
    LD A,B
    SUB C
    LD B,A                     ; B = (COLS-1)-col = コピーするバイト数
    POP DE                     ; DE = dst
    LD A,B
    OR A
    JR Z,_kdl_lastonly
_kdl_loop:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _kdl_loop
_kdl_lastonly:
    LD A,020h
    LD (DE),A                  ; 最終列(79)を空白で埋める
    RET

; KEY_ENTER_INSERT — INS/DEL+SHIFT(ins_mode_only)。押した時点では行内容
; は変化させず、挿入モードに入るだけ。
KEY_ENTER_INSERT:
    LD A,1
    LD (VAR_INSMODE),A
    RET

; KEY_HOME — HOME/CLR+SHIFT(home)。画面内容は変えず、カーソルだけを
; 画面左上(行0・列0)へ移す。
KEY_HOME:
    XOR A
    LD (VAR_ROW),A
    LD (VAR_COL),A
    LD HL,TEXT_BASE
    LD (VAR_ROWBASE),HL
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
