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

