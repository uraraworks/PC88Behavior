; src/ext_bank/relay.asm — 拡張ROMバンク(4th ROM)への中継ルーチン(土台)
;
; 根拠: docs/spec/ext-rom-bank.md 第1〜2節。ポート0x71のbit0(EXT_ROM_NOT)が
; 窓(0x6000-0x7FFF)の有効/無効を切り替える総スイッチ、0x32の下位2bit
; (EROMSL)がバンク0〜3を選ぶ(ビット定義そのものは docs/spec/l1-ipl.md
; 第5c節を参照)。
;
; このファイルは**必ず**組み合わせROM中で0x6000未満に来なければならない
; (第2節 制約1)。build_main_rom.py 側で「窓の外に置く」ようINCLUDE順序を
; 決め、check_ext_bank_relay_below_window() がビルド時に機械的に検査する。
;
; ---------------------------------------------------------------
; 呼び出し規約(docs/spec/ext-rom-bank.md 第2節 制約1・3・4 準拠)
; ---------------------------------------------------------------
;   入力: A  = バンク番号(0-3)
;         HL = 窓内(0x6000-0x7FFF)の呼び出し先番地
;   出力: バンク側ルーチンがAレジスタ等に置いた返り値をそのまま返す
;         (このルーチン自身は返り値を書き換えない)
;   壊すレジスタ: A, F, HL, および呼び出し先(バンク側ルーチン)が使った
;         レジスタ。BC・DEはこのルーチンの作業用に使うため保存しない
;         (呼び出し規約としてCALLと同様、保存が要るなら呼び出し元が
;         PUSH/POPする)。
;   前提: 呼び出し先(バンク側ルーチン)は窓内で完結してRETで戻ること。
;         バンク側からさらに別バンク・常駐部ルーチンを跨いで呼ぶ設計は
;         測定していない(第3節項3、未確定)ため使わない。
;   定型: 呼び出し前に0x71・0x32の現在値を読んで保存し、対象ビット
;         (0x71のbit0・0x32の下位2bit)だけを書き換えてバンクを選び、
;         呼び出しから戻った後に保存しておいた値をそのまま書き戻す
;         (第2節 制約4。l1-ipl.md 第4節の「読んでから書き戻す」定型と
;         同じ形)。無関係なビット(PMODE等)は破壊しない。
; ---------------------------------------------------------------

; ポート(l1-ipl.md 第5c節・ext-rom-bank.md 第1節)
EXT_PORT_BANKSEL EQU 0x32   ; bit1-0 = EROMSL(内蔵拡張ROMバンク選択0-3)
EXT_PORT_SWITCH  EQU 0x71   ; bit0   = EXT_ROM_NOT(0で拡張ROM有効/1でメインROM)

; 0x32書き戻し時に「バンク番号のビットだけ」を差し替えるためのマスク
EXT_BANKSEL_CLEAR_MASK EQU 0xFC   ; 下位2bitをクリア
EXT_SWITCH_ENABLE_MASK EQU 0xFE   ; bit0をクリア(拡張ROM有効化)

; 窓(バンクの内容が見える範囲)の先頭番地。バンク側の試験エントリは
; ここに置く(src/ext_bank/bank0.asm〜bank3.asm)。
EXT_BANK_WINDOW_BASE EQU 0x6000

; EXT_BANK_CALLの作業領域(RAM)。あえてBC/DEのようなレジスタではなく
; RAMに置く。理由: このリポジトリの既存VSYNCハンドラ
; (src/l1_ipl/make_ipl_rom.py sub_vsync_handler)はAF/BC/HL等を
; PUSH/POPせずに動く設計(定常状態のSTEADY_WAITは何もレジスタに
; 保持しないHALTループだけなので、それで成立している)。
; EXT_BANK_LOOP_TESTのように「割り込みを有効にしたまま」EXT_BANK_CALLを
; 連続で呼ぶ場面では、EXT_BANK_CALL自身がレジスタに退避した値の途中で
; VSYNC割り込みが入り、そのレジスタを壊されうる。**実際に最初の実装
; (BC/DEに退避)でこれを踏み、EXT_BANK_LOOP_TESTが常に失敗した**
; (tools/ext_bank_selftest.shで検出)。RAMへ退避すれば、割り込みが
; レジスタを壊しても次に読み直すまで値は保たれる。
EXT_BANK_SAVE_SWITCH  EQU 0E8C8h   ; 1バイト: 呼び出し前の0x71退避
EXT_BANK_SAVE_BANKSEL EQU 0E8C9h   ; 1バイト: 呼び出し前の0x32退避
EXT_BANK_SAVE_TARGET  EQU 0E8CAh   ; 2バイト: 呼び出し先番地(HL)の退避

; ---------------------------------------------------------------
; EXT_BANK_CALL — 拡張ROMバンクの窓内ルーチンを1回呼び出す中継
; ---------------------------------------------------------------
EXT_BANK_CALL:
    LD (EXT_BANK_SAVE_TARGET),HL  ; 呼び出し先番地をRAMへ退避
    LD D,A                        ; D = 要求バンク番号(0-3)。ここから
                                   ; OUT (EXT_PORT_BANKSEL) までの短い
                                   ; 区間だけレジスタに置く(RAM化は
                                   ; していない——既知の残余リスク、
                                   ; docs/spec/ext-rom-bank.md 第3節項1
                                   ; 「中継呼び出しの費用は未測定」とも
                                   ; 関係するトレードオフ)。
    IN A,(EXT_PORT_SWITCH)
    LD (EXT_BANK_SAVE_SWITCH),A
    IN A,(EXT_PORT_BANKSEL)
    LD (EXT_BANK_SAVE_BANKSEL),A
    AND EXT_BANKSEL_CLEAR_MASK
    OR D                          ; 対象ビット(下位2bit)だけバンク番号へ
    OUT (EXT_PORT_BANKSEL),A      ; まだ0x71が有効なので窓はまだ切り替わらない
    LD A,(EXT_BANK_SAVE_SWITCH)
    AND EXT_SWITCH_ENABLE_MASK
    OUT (EXT_PORT_SWITCH),A       ; ここで窓がバンク側に切り替わる
    LD HL,(EXT_BANK_SAVE_TARGET)  ; 窓切り替え直後、CALLの直前で読み直す
                                   ; (HLが割り込みで壊れていても戻せる)
    CALL EXT_BANK_JUMP_HL         ; HL先を1回CALLして戻ってくる(下記)
    PUSH AF                       ; バンク側ルーチンの返り値(A/F)を退避
                                   ; ——このあとの窓復元でAを使うため
                                   ; (実際にここでAを退避し忘れ、返り値が
                                   ; 常に0x32の旧値に化ける不具合を作った。
                                   ; tools/ext_bank_selftest.shで検出)
    LD A,(EXT_BANK_SAVE_SWITCH)
    OUT (EXT_PORT_SWITCH),A       ; まず0x71を元に戻す(窓をメインROM側へ)
    LD A,(EXT_BANK_SAVE_BANKSEL)
    OUT (EXT_PORT_BANKSEL),A      ; 0x32も元に戻す(PMODE等の無関係ビットも保持)
    POP AF                        ; 返り値(A/F)を復元してから戻る
    RET

; ---------------------------------------------------------------
; EXT_BANK_JUMP_HL — HLの指す番地を1回CALLするための小道具
;
; Z80に「CALL (HL)」相当の命令が無いため、次の技法を使う:
;   CALL EXT_BANK_JUMP_HL を実行すると、戻り先(EXT_BANK_CALL側の
;   次の命令)がスタックへ積まれる。ここで JP (HL) によりバンク側の
;   ルーチンへ飛ぶ。バンク側ルーチンが RET すると、スタックに積まれた
;   その戻り先へ戻る——結果としてHL先を1回CALLしたのと同じになる。
; ---------------------------------------------------------------
EXT_BANK_JUMP_HL:
    JP (HL)

; ---------------------------------------------------------------
; 自己検査(陰性対照つき)。docs/spec/ext-rom-bank.md 第1節の観測に基づく
; 「常駐部から中継経由でバンクを呼んで正しい値が返る」
; 「窓の中から呼んでも戻れる」「割り込みを有効にしたまま多数回呼んでも
; 壊れない」を確かめる。
;
; ルーチン本体は常にROMへ含める(このリポジトリの既存の流儀
; ——例: src/l4_basic/lexer.asm の LEX_SELFTEST——に倣う)。だが**呼び出し
; そのもの**はbuild_main_rom.pyの--enable-ext-bank-selftestを立てた
; ビルドでだけ行う。理由も既存流儀と同じ: 起動時に無条件で呼ぶと
; L1適合検査(OUT列・フレーム内のI/O件数を数える検査)がブート時の
; サイクル数変化で壊れる(l4_selftest_callのコメント参照)。
; ---------------------------------------------------------------

; 結果格納領域(RAM)。既存の使用域(E800-E8B9、E980-E99B、EA00-)と
; 衝突しない空き(E8BA以降)を使う。
EXT_BANK_ST_VAL0      EQU 0E8C0h   ; バンク0を呼んだ返り値
EXT_BANK_ST_VAL1      EQU 0E8C1h   ; バンク1
EXT_BANK_ST_VAL2      EQU 0E8C2h   ; バンク2
EXT_BANK_ST_VAL3      EQU 0E8C3h   ; バンク3
EXT_BANK_ST_PASS      EQU 0E8C4h   ; 4バンク中、期待値と一致した本数(0-4)
EXT_BANK_ST_WINCALL   EQU 0E8C5h   ; 1=窓の中(run部)から呼んでも正しく戻れた
EXT_BANK_ST_LOOP_DONE EQU 0E8C6h   ; 1=多数回呼び出し試験を実行済み
EXT_BANK_ST_LOOP_OK   EQU 0E8C7h   ; 1=多数回呼び出し試験が全数一致
EXT_BANK_ST_LOOP_CNT  EQU 0E8CCh   ; 2バイト: 残り回数のカウンタ。DE等の
                                   ; レジスタに置くと、EXT_BANK_CALL自身の
                                   ; 作業(元はBC/DEを使っていた)やVSYNC
                                   ; ハンドラによる破壊を受けるため、
                                   ; EXT_BANK_SAVE_*と同じ理由でRAMに置く。

; 各バンクの試験エントリ(src/ext_bank/bank0.asm等)が返す期待値。
; 単純にバンク番号+0xB0(0x00やFILL=0x00・欠落時の0xFFと衝突しない値)。
EXT_BANK_EXPECT0 EQU 0xB0
EXT_BANK_EXPECT1 EQU 0xB1
EXT_BANK_EXPECT2 EQU 0xB2
EXT_BANK_EXPECT3 EQU 0xB3

; ---------------------------------------------------------------
; EXT_BANK_SELFTEST — 割り込み無しで行える範囲の自己検査(常駐部から
; バンク0-3を呼ぶ・窓の中から呼んでも戻れる)。ブート途中(IM2/EIの
; 前)から呼ばれる前提なので、ここではEIしない(呼び出し元の
; build_main_rom.pyのコメント参照。IM2ベクタページがIへ積まれる前に
; EIすると、その瞬間にVSYNC割り込みが入った場合にベクタ引きが
; 外れて暴走する——未確定の危険を避け、割り込みを使う試験は
; EXT_BANK_LOOP_TESTへ分離しIM2/EI設定後の定常状態から呼ぶ)。
; ---------------------------------------------------------------
EXT_BANK_SELFTEST:
    XOR A
    LD (EXT_BANK_ST_PASS),A
    LD (EXT_BANK_ST_WINCALL),A
    ; EXT_BANK_ST_LOOP_DONE/LOOP_OKもここで明示的に0初期化する。
    ; RAM(main_ram)は起動時にゼロクリアされる保証が無く(vendor/
    ; quasi88-libretro/src/memory.c mem_alloc()はmallocでゼロ初期化しない)、
    ; EXT_BANK_LOOP_TESTの「実行済みフラグ」がたまたま非ゼロの不定値
    ; だった場合、STEADY_WAIT到達後の初回呼び出しが即RETし、多数回呼び出し
    ; 試験が永久に走らない不具合を実際に踏んだ(tools/ext_bank_selftest.sh
    ; で検出)。EXT_BANK_SELFTESTはSTEADY_WAITより必ず先に走る(build_main_rom.py
    ; の挿入順)ため、ここで0にしておけば確実にEXT_BANK_LOOP_TESTが
    ; 初回実行される。
    LD (EXT_BANK_ST_LOOP_DONE),A
    LD (EXT_BANK_ST_LOOP_OK),A

    LD A,0
    LD HL,EXT_BANK_WINDOW_BASE
    CALL EXT_BANK_CALL
    LD (EXT_BANK_ST_VAL0),A

    LD A,1
    LD HL,EXT_BANK_WINDOW_BASE
    CALL EXT_BANK_CALL
    LD (EXT_BANK_ST_VAL1),A

    LD A,2
    LD HL,EXT_BANK_WINDOW_BASE
    CALL EXT_BANK_CALL
    LD (EXT_BANK_ST_VAL2),A

    LD A,3
    LD HL,EXT_BANK_WINDOW_BASE
    CALL EXT_BANK_CALL
    LD (EXT_BANK_ST_VAL3),A

    LD B,0
    LD A,(EXT_BANK_ST_VAL0)
    CP EXT_BANK_EXPECT0
    JR NZ,_ebst_v0ng
    INC B
_ebst_v0ng:
    LD A,(EXT_BANK_ST_VAL1)
    CP EXT_BANK_EXPECT1
    JR NZ,_ebst_v1ng
    INC B
_ebst_v1ng:
    LD A,(EXT_BANK_ST_VAL2)
    CP EXT_BANK_EXPECT2
    JR NZ,_ebst_v2ng
    INC B
_ebst_v2ng:
    LD A,(EXT_BANK_ST_VAL3)
    CP EXT_BANK_EXPECT3
    JR NZ,_ebst_v3ng
    INC B
_ebst_v3ng:
    LD A,B
    LD (EXT_BANK_ST_PASS),A

    ; 窓の中(run部)に置いたプローブ(src/ext_bank/wincall_probe.asm)を
    ; 経由して、窓の中のコードからEXT_BANK_CALLを呼んでも戻れることを
    ; 確かめる。
    CALL EXT_BANK_WINCALL_PROBE
    LD (EXT_BANK_ST_WINCALL),A
    RET

; ---------------------------------------------------------------
; EXT_BANK_LOOP_TEST — 割り込みを有効にしたまま多数回(200回)
; EXT_BANK_CALLを呼んでも壊れないことを確かめる。
;
; IM2/I/EI設定済みの定常状態(STEADY_WAIT)からだけ呼ぶ前提
; (build_main_rom.pyがSTEADY_WAIT直後に注入する)。一度実行したら
; EXT_BANK_ST_LOOP_DONEで以後は素通りする(STEADY_WAITは毎フレーム
; 通るループのため)。
; ---------------------------------------------------------------
EXT_BANK_LOOP_TEST:
    LD A,(EXT_BANK_ST_LOOP_DONE)
    OR A
    RET NZ

    LD HL,200
    LD (EXT_BANK_ST_LOOP_CNT),HL
_ebst_loop:
    LD A,0
    LD HL,EXT_BANK_WINDOW_BASE
    CALL EXT_BANK_CALL
    CP EXT_BANK_EXPECT0
    JR NZ,_ebst_loop_fail
    LD HL,(EXT_BANK_ST_LOOP_CNT)
    DEC HL
    LD (EXT_BANK_ST_LOOP_CNT),HL
    LD A,H
    OR L
    JR NZ,_ebst_loop

    LD A,1
    LD (EXT_BANK_ST_LOOP_DONE),A
    LD (EXT_BANK_ST_LOOP_OK),A
    RET
_ebst_loop_fail:
    LD A,1
    LD (EXT_BANK_ST_LOOP_DONE),A
    XOR A
    LD (EXT_BANK_ST_LOOP_OK),A
    RET
