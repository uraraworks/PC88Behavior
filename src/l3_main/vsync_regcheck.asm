; src/l3_main/vsync_regcheck.asm — VSYNCハンドラのレジスタ非退避の
; 潜在不具合を検出する最小の自己検査(陰性対照)。ext_bank固有の話ではない。
;
; 背景: src/l1_ipl/make_ipl_rom.py sub_vsync_handler()は、以前は
; AF/BC/DE/HL/IX/IYを一切PUSH/POPせずに動いていた。通常は誰も
; STEADY_WAIT(定常状態、EI済み)の外でこれらのレジスタへ長寿命の値を
; 置いて次のVSYNCをまたいで読む、という書き方をしていなかったため
; 症状が出なかっただけで、実際にそういうコードを書いた瞬間に壊れる
; 潜在不具合だった(src/ext_bank/relay.asm EXT_BANK_LOOP_TESTの初版
; 〈BC/DEへ中継ルーチンの退避値を置いた〉で実際に踏んだ)。
;
; 検査方法: STEADY_WAIT(IM2/I/EI設定済み)から1回だけ呼ぶ。
; A/BC/DE/HL/IX/IYへ既知の目印値を積み、HALTで実際に1回VSYNC割り込みを
; 受理させてから、レジスタが変わっていないことを確認する。
; VSYNC_HANDLER自身がPUSH/POPで包まれていれば(修正後)、このハンドラ
; (と、そこから呼ばれるL3_VSYNC_HOOK以下・KEYSCAN)がどれだけレジスタを
; 使っても、戻ってきたときは呼び出し元(=この検査)のレジスタがそのまま
; 残っているはずである。修正前はここが不一致(RESULT=0)になる
; (tools/vsync_regcheck_selftest.shの陰性対照が示す)。

VSYNC_REGCHECK_DONE    EQU 0E8D0h   ; 1=検査実行済み
VSYNC_REGCHECK_RESULT  EQU 0E8D1h   ; 1=全レジスタ一致(OK)・0=不一致
VSYNC_REGCHECK_SAVE_A  EQU 0E8D2h   ; 1バイト
VSYNC_REGCHECK_SAVE_BC EQU 0E8D3h   ; 2バイト
VSYNC_REGCHECK_SAVE_DE EQU 0E8D5h   ; 2バイト
VSYNC_REGCHECK_SAVE_HL EQU 0E8D7h   ; 2バイト
VSYNC_REGCHECK_SAVE_IX EQU 0E8D9h   ; 2バイト
VSYNC_REGCHECK_SAVE_IY EQU 0E8DBh   ; 2バイト

VSYNC_REGCHECK:
    LD A,(VSYNC_REGCHECK_DONE)
    OR A
    RET NZ
    LD A,1
    LD (VSYNC_REGCHECK_DONE),A

    LD A,0x5A
    LD BC,0x1122
    LD DE,0x3344
    LD HL,0x5566
    LD IX,0x7788
    LD IY,0x99AA
    HALT                            ; 次のVSYNCを1回受理させる

    ; 直後、すべてをRAMへ書き出す(比較に使うA/HLを温存するため先に退避)。
    ; ここでのAは、割り込みハンドラが本当にAを保存/復帰していれば
    ; まだ0x5Aのはず。
    LD (VSYNC_REGCHECK_SAVE_A),A
    LD (VSYNC_REGCHECK_SAVE_BC),BC
    LD (VSYNC_REGCHECK_SAVE_DE),DE
    LD (VSYNC_REGCHECK_SAVE_HL),HL
    LD (VSYNC_REGCHECK_SAVE_IX),IX
    LD (VSYNC_REGCHECK_SAVE_IY),IY

    LD A,1
    LD (VSYNC_REGCHECK_RESULT),A

    LD A,(VSYNC_REGCHECK_SAVE_A)
    CP 0x5A
    JR NZ,_vrc_fail

    LD HL,(VSYNC_REGCHECK_SAVE_BC)
    LD A,H
    CP 0x11
    JR NZ,_vrc_fail
    LD A,L
    CP 0x22
    JR NZ,_vrc_fail

    LD HL,(VSYNC_REGCHECK_SAVE_DE)
    LD A,H
    CP 0x33
    JR NZ,_vrc_fail
    LD A,L
    CP 0x44
    JR NZ,_vrc_fail

    LD HL,(VSYNC_REGCHECK_SAVE_HL)
    LD A,H
    CP 0x55
    JR NZ,_vrc_fail
    LD A,L
    CP 0x66
    JR NZ,_vrc_fail

    LD HL,(VSYNC_REGCHECK_SAVE_IX)
    LD A,H
    CP 0x77
    JR NZ,_vrc_fail
    LD A,L
    CP 0x88
    JR NZ,_vrc_fail

    LD HL,(VSYNC_REGCHECK_SAVE_IY)
    LD A,H
    CP 0x99
    JR NZ,_vrc_fail
    LD A,L
    CP 0xAA
    JR NZ,_vrc_fail

    RET
_vrc_fail:
    XOR A
    LD (VSYNC_REGCHECK_RESULT),A
    RET
