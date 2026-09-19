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
;   壊すレジスタ: A, F, BC, DE、および呼び出し先(バンク側ルーチン)が
;         使ったレジスタ(HLを含む——HLはこのルーチン自身は書き換え
;         ないが、呼び出し先が自由に使ってよい)。保存が要るなら
;         呼び出し元がPUSH/POPする(呼び出し規約としてCALLと同様)。
;   前提: 呼び出し先(バンク側ルーチン)は窓内で完結してRETで戻ること。
;         ただし、バンク側ルーチンが常駐部(窓の外、0x0000-0x5FFF)の
;         ルーチンを1回CALLして戻ってくること自体は、以下の条件下で
;         許可される(docs/spec/ext-rom-bank.md 第2節 制約3(a)〜(c)、
;         docs/notes/ext2-relay-to-resident-results.mdで測定済み):
;           (a) 呼び先が窓の外(0x0000-0x5FFF)にあること(窓の中の番地を
;               「常駐部の共有ルーチン」のつもりで呼ぶ設計は、実際には
;               その時点で有効なバンクの内容が実行されてしまうため使えない
;               ——q3_window_target_is_bank_local)。
;           (b) 呼び先の常駐ルーチンが実行中に0x71・0x32・EXT_BANK_CALLへ
;               一切触れないこと(触れる場合=常駐ルーチンが自ら別バンクへ
;               跨る呼び出しをする場合の挙動は未測定)。
;           (c) 常駐ルーチンは1回CALLされてRETで戻るだけの形に留めること
;               (バンクA→常駐部→バンクBのように、常駐ルーチンの中から
;               さらに別バンクへ跨る呼び出しは未測定)。
;         build_main_rom.pyのEXT_BANK_CALLABLE_RESIDENT_LABELSが、この
;         条件のうち(a)(機械的に検査できる部分)をビルド時に検査する
;         (check_ext_bank_callable_labels_below_window())。
;         バンク側から窓の中の他の番地(同じバンクの別ルーチン)を直接
;         CALLする設計は、引き続き測定していない(未確定)ため使わない。
;   定型: 呼び出し前に0x71・0x32の現在値を読んで保存し、対象ビット
;         (0x71のbit0・0x32の下位2bit)だけを書き換えてバンクを選び、
;         呼び出しから戻った後に保存しておいた値をそのまま書き戻す
;         (第2節 制約4。l1-ipl.md 第4節の「読んでから書き戻す」定型と
;         同じ形)。無関係なビット(PMODE等)は破壊しない。
;   再入不可(非reentrant): EXT_BANK_CALLの実行中(0x71/0x32を切り替えて
;         からポートを元に戻すまでの間)に、同じEXT_BANK_CALLを
;         もう一度呼ぶ設計は使わない。作業値(旧0x71・旧0x32・
;         バンク番号)をBC/DE(下記参照)に置いているため、再入すると
;         外側の呼び出しの作業値を内側の呼び出しが上書きし、外側が
;         窓を復元するときに壊れた値を書き戻してしまう。**この設計で
;         再入が起きうるのは、(a)バンク側ルーチンが自分自身から
;         EXT_BANK_CALLを呼ぶ、(b)割り込みハンドラ(VSYNC_HANDLER
;         以下)がEXT_BANK_CALLを呼ぶ、の2通りだが、いずれも現状の
;         コードには無い**（(a)は制約3で禁止済み、(b)はVSYNC_HANDLER
;         →L3_VSYNC_HOOK→KEY_READ等のどこもEXT_BANK_CALLを呼んで
;         いないことをgrep済み）。将来どちらかを行う設計に変える
;         場合は、下記のEXT_BANK_BUSYによる検出だけでは「壊れた値を
;         書き戻さない」ことまでは保証しない(検出して異常応答を
;         返すだけ)ため、別途の設計(呼び出しごとに独立した保存領域を
;         スタックに積む、等)が要る。
; ---------------------------------------------------------------
;
; ## レジスタ渡し vs RAM退避（経緯）
;
; 開発時、EXT_BANK_LOOP_TEST(割り込みを有効にしたまま連続呼び出し)で
; 実際にBC/DEの値が壊れる不具合を踏んだ。原因はEXT_BANK_CALL自身では
; なく、当時のVSYNCハンドラ(src/l1_ipl/make_ipl_rom.py
; sub_vsync_handler)がAF/BC/DE/HL/IX/IYを一切PUSH/POPしていなかった
; ことによる潜在不具合だった(割り込みを有効にしたまま呼び出しを
; またぐレジスタなら何でも壊れうる、ext_bank固有の話ではない)。
; 応急処置として作業値をRAM(EXT_BANK_SAVE_*)へ逃がしていたが、
; VSYNCハンドラ本体をPUSH/POPで包む修正(sub_vsync_handlerのコメント
; 参照)を入れたことで、このハンドラ経由の割り込みでレジスタが
; 壊れることは無くなったため、RAM退避は不要になり通常のレジスタ渡し
; (BC/DE)へ戻した。tools/vsync_regcheck_selftest.shが、VSYNCハンドラの
; レジスタ退避が外れると壊れる（陰性対照）・入っていれば壊れない
; ことを確認している。

; EXT_BANK_CALLの再入検出用フラグ(RAM)。上記「再入不可」参照。
EXT_BANK_BUSY              EQU 0E8C8h   ; 1=EXT_BANK_CALL実行中
EXT_BANK_REENTRY_DETECTED  EQU 0E8C9h   ; 1=再入を検出したことがある

; ---------------------------------------------------------------
; EXT_BANK_INIT — EXT_BANK_BUSYの初期化。
;
; RAM(main_ram)は起動時にゼロクリアされる保証が無い(vendor/
; quasi88-libretro/src/memory.c mem_alloc()はmallocでゼロ初期化しない、
; EXT_BANK_ST_LOOP_DONEで一度踏んだのと同じ話——下記EXT_BANK_SELFTEST
; 参照)。EXT_BANK_BUSYが起動直後にたまたま非ゼロだと、最初の
; EXT_BANK_CALLが「既に実行中」と誤検出して即座に異常応答を返し、
; 拡張ROMバンクが一切使えなくなる(自己検査ビルドで実際に踏んだ)。
; build_main_rom.pyがブート時に無条件(selftestフラグの有無と無関係)で
; 一度だけ呼び、常に0から始まるようにする。
; ---------------------------------------------------------------
EXT_BANK_INIT:
    XOR A
    LD (EXT_BANK_BUSY),A
    LD (EXT_BANK_REENTRY_DETECTED),A
    RET

; ポート(l1-ipl.md 第5c節・ext-rom-bank.md 第1節)
EXT_PORT_BANKSEL EQU 0x32   ; bit1-0 = EROMSL(内蔵拡張ROMバンク選択0-3)
EXT_PORT_SWITCH  EQU 0x71   ; bit0   = EXT_ROM_NOT(0で拡張ROM有効/1でメインROM)

; 0x32書き戻し時に「バンク番号のビットだけ」を差し替えるためのマスク
EXT_BANKSEL_CLEAR_MASK EQU 0xFC   ; 下位2bitをクリア
EXT_SWITCH_ENABLE_MASK EQU 0xFE   ; bit0をクリア(拡張ROM有効化)

; 窓(バンクの内容が見える範囲)の先頭番地。バンク側の試験エントリは
; ここに置く(src/ext_bank/bank0.asm〜bank3.asm)。
EXT_BANK_WINDOW_BASE EQU 0x6000

; ---------------------------------------------------------------
; EXT_BANK_CALL — 拡張ROMバンクの窓内ルーチンを1回呼び出す中継
;
; 作業値(バンク番号・旧0x71・旧0x32)は通常のレジスタ(D・E・C)へ置く
; (上記「レジスタ渡し vs RAM退避」参照。VSYNCハンドラのPUSH/POP修正
; 済みなので、割り込みを有効にしたまま実行中に割り込まれてもこれらの
; レジスタは保たれる)。
; ---------------------------------------------------------------
EXT_BANK_CALL:
    LD B,A                        ; B = 要求バンク番号(0-3)を一旦退避
                                   ; (EXT_BANK_BUSYチェックでAを使うため)
    LD A,(EXT_BANK_BUSY)
    OR A
    JR Z,_ebc_not_busy
    ; 再入を検出した。上記コメントのとおり、この実装は再入時に
    ; 「外側の呼び出しの作業値を壊さない」ことまでは保証できないため、
    ; ポートには一切触れずに異常を記録して抜ける(既存の窓の状態は
    ; そのまま——少なくとも新たな破壊は増やさない)。
    LD A,1
    LD (EXT_BANK_REENTRY_DETECTED),A
    XOR A
    RET
_ebc_not_busy:
    LD A,1
    LD (EXT_BANK_BUSY),A
    LD D,B                        ; D = 要求バンク番号(0-3)
    IN A,(EXT_PORT_SWITCH)
    LD E,A                        ; E = 旧0x71(あとで書き戻す)
    IN A,(EXT_PORT_BANKSEL)
    LD C,A                        ; C = 旧0x32(あとで書き戻す)
    AND EXT_BANKSEL_CLEAR_MASK
    OR D                          ; 対象ビット(下位2bit)だけバンク番号へ
    OUT (EXT_PORT_BANKSEL),A      ; まだ0x71が有効なので窓はまだ切り替わらない
    LD A,E
    AND EXT_SWITCH_ENABLE_MASK
    OUT (EXT_PORT_SWITCH),A       ; ここで窓がバンク側に切り替わる
    CALL EXT_BANK_JUMP_HL         ; HL先を1回CALLして戻ってくる(下記)
    PUSH AF                       ; バンク側ルーチンの返り値(A/F)を退避
                                   ; ——このあとの窓復元でAを使うため
                                   ; (開発時、ここでAを退避し忘れ、
                                   ; 返り値が常に0x32の旧値に化ける
                                   ; 不具合を作ったことがある。
                                   ; tools/ext_bank_selftest.shで検出)
    LD A,E
    OUT (EXT_PORT_SWITCH),A       ; まず0x71を元に戻す(窓をメインROM側へ)
    LD A,C
    OUT (EXT_PORT_BANKSEL),A      ; 0x32も元に戻す(PMODE等の無関係ビットも保持)
    XOR A
    LD (EXT_BANK_BUSY),A          ; 再入検出フラグを下ろす(POP AFの前、
                                   ; Aは次のPOP AFで上書きされるので
                                   ; ここで自由に使ってよい)
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
EXT_BANK_ST_LOOP_CNT  EQU 0E8CCh   ; 2バイト: 残り回数のカウンタ。
                                   ; EXT_BANK_CALLがB/C/D/Eを作業用に
                                   ; 使う(上記「壊すレジスタ」参照)ため、
                                   ; BC/DEに置くと呼ぶたびに潰れる。
                                   ; RAMに置けば影響されない。

; 各バンクの試験エントリ(src/ext_bank/bank0.asm等)が返す期待値。
; 単純にバンク番号+0xB0(0x00やFILL=0x00・欠落時の0xFFと衝突しない値)。
EXT_BANK_EXPECT0 EQU 0xB0
EXT_BANK_EXPECT1 EQU 0xB1
EXT_BANK_EXPECT2 EQU 0xB2
EXT_BANK_EXPECT3 EQU 0xB3

; バンク0の絶対番地試験(src/ext_bank/bank0.asm EXT_BANK0_ABS_TEST_ENTRY)
; のオフセットと期待値。0x6000起点でORGされていれば、絶対番地の
; CALL/JP/LD A,(nn)がすべて正しい窓内番地を指し、テーブルの値0xC5を
; 正しく読める。ORGがずれていれば別の番地へ飛ぶ/別のデータを読み、
; 一致しない(ビルド次第では暴走もありうる——RETに辿り着かない場合、
; ここのCALLは戻ってこず、以降の自己検査も止まる。これ自体が
; 「壊れている」ことの検出になる)。
EXT_BANK0_ABS_ENTRY_OFFSET EQU 0x10
EXT_BANK0_ABS_EXPECT       EQU 0xC5
EXT_BANK_ST_ABS_VAL EQU 0E8CFh   ; 1バイト: 絶対番地試験の生の返り値
EXT_BANK_ST_ABS_OK  EQU 0E8CEh   ; 1バイト: 1=期待値0xC5と一致

; バンク0の「常駐の単精度演算(MBF_ADD)を呼んで正しい結果を返す」試験
; (src/ext_bank/bank0.asm EXT_BANK0_MBF_TEST_ENTRY、docs/spec/
; ext-rom-bank.md 第2節 制約3)。offset 0x30固定。
EXT_BANK0_MBF_ENTRY_OFFSET EQU 0x30
EXT_BANK_ST_MBF_OK  EQU 0E8D0h   ; 1バイト: 1=MBF_ADD(1.0+2.0)が3.0と一致

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
    LD (EXT_BANK_ST_ABS_OK),A
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

    ; バンク0の絶対番地試験(src/ext_bank/bank0.asm
    ; EXT_BANK0_ABS_TEST_ENTRY)。ORGが正しければ期待値0xC5が返る。
    LD A,0
    LD HL,EXT_BANK_WINDOW_BASE+EXT_BANK0_ABS_ENTRY_OFFSET
    CALL EXT_BANK_CALL
    LD (EXT_BANK_ST_ABS_VAL),A
    CP EXT_BANK0_ABS_EXPECT
    JR NZ,_ebst_absng
    LD A,1
    LD (EXT_BANK_ST_ABS_OK),A
_ebst_absng:

    ; バンク0の試験ルーチンが常駐のMBF_ADD(単精度加算)を呼んで
    ; 1.0+2.0=3.0を正しく返すことの自己検査(docs/spec/ext-rom-bank.md
    ; 第2節 制約3)。
    XOR A
    LD (EXT_BANK_ST_MBF_OK),A
    LD A,0
    LD HL,EXT_BANK_WINDOW_BASE+EXT_BANK0_MBF_ENTRY_OFFSET
    CALL EXT_BANK_CALL
    LD (EXT_BANK_ST_MBF_OK),A
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
