; src/ext_bank/wincall_probe.asm — 「窓の中から呼んでも戻れる」自己検査用プローブ
;
; docs/spec/ext-rom-bank.md 第1節 q3_interrupt_during_window_ok は、割り込み
; ハンドラが窓の外にあれば安全という観測だったが、それとは別に「窓の中
; (常駐部のrun.asm相当、拡張ROMバンクが無効な間は普通にメインROMとして
; 読める番地)にあるコードがEXT_BANK_CALLを呼んでも問題なく戻ってくる
; こと」も自己検査で確かめておきたい(呼び出し元は窓の中でも、戻り先は
; Z80の物理スタックに積まれるため窓の切り替えとは無関係——という設計上の
; 前提を実機/エミュレータ上のコードで裏づける)。
;
; このファイル自体は「バンク側(窓の中に切り替えて見えるコード)」では
; なく、拡張ROMバンクが無効な通常状態でメインROM側として窓の番地に
; 置かれる常駐コードである。ext-rom-bank.md 第2節 制約3(バンク側コードが
; 窓の外を直接CALLしない)には該当しない——ここでCALLしているのは逆で、
; 「窓の中の常駐コード」が「窓の外の中継ルーチン」を呼ぶ側であり、
; 制約1・4が要求する形そのもの。
;
; build_main_rom.py は通常ビルドでこのファイルをrun.asmの直後に
; INCLUDEする。run.asmの一部が既に0x6000を越える番地に配置されている
; (現状のレイアウトの実測)ため、このファイルも自然に窓の中に来る。
EXT_BANK_WINCALL_PROBE:
    LD A,1
    LD HL,EXT_BANK_WINDOW_BASE
    CALL EXT_BANK_CALL
    CP EXT_BANK_EXPECT1
    JR NZ,_ebwp_fail
    LD A,1
    RET
_ebwp_fail:
    XOR A
    RET
