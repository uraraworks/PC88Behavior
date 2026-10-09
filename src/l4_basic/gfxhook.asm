; docs/spec/l4-graphics.md 第1版（l4-s9t）の観測から独立実装。バンク0の中継部。
; bank0.asm の後ろ・deffn.asm の前の空き（0x6A33〜0x6AFF）に置く（make_ext_rom_banks.py が連結順を決める）。
; グラフィック文の本体はバンク2（src/ext_bank/gfx.asm）。ここに置くのは次の3つだけ。
;   (1) 文の語の表 fn_words（deftype.asm から移した。PSET・PRESET・POINT・SCREEN を足した）。
;       文の種別は表の並びの番号+29（LET=1→30 ... CONSOLE=14→43、PSET=15→44、PRESET=45、POINT=46、SCREEN=47、LINE=48、CIRCLE=49）。
;   (2) 種別44以上の文をバンク2へ渡す中継（deftype.asm fn_stmt_dispatch から）。
;   (3) 式の中の POINT( を ts_try より先に見てバンク2の関数入口へ渡す。
; バンク0からバンク2を呼ぶには、窓外中継 EXT_BANK_MAIN_CALL でmainの EXT_BANK_CALL を呼ぶ
; （FN_BANK3_ADDR と同じ形。外側の窓状態は中継のスタックに残る）。
GFX_BANK EQU 2
GFX_STMT_ENTRY EQU 0x7300
GFX_POINT_ENTRY EQU 0x7310
CIRCLE_ENTRY EQU 0x7840
    ORG 0x6A40

; 文の語の表（照合順。DEFはDEFINT等より前でも、語の直後が英字なら一致しない）
fn_words:
    DB 3,"LET",5,"WHILE",4,"WEND",3,"DEF",4,"SWAP",5,"ERASE",6,"DEFINT",6,"DEFSNG",6,"DEFDBL",6,"DEFSTR",3,"RUN",4,"BEEP",5,"WIDTH",7,"CONSOLE"
    DB 4,"PSET",6,"PRESET",5,"POINT",6,"SCREEN",4,"LINE",6,"CIRCLE",0

gfx_stmt_fwd:
    LD HL,GFX_STMT_ENTRY
    LD A,(MM_RUN_STMT_KIND)
    CP 49                       ; 49=CIRCLE はバンク1（src/ext_bank/circle.asm）
    JR NZ,gfx_fwd
    LD HL,CIRCLE_ENTRY
    LD A,1
    JR gfx_fwd_go
gfx_fwd:
    LD A,GFX_BANK
gfx_fwd_go:
    LD IX,GFX_BANKCALL_ADDR
    JP FN_MAIN_CALL_ADDR
GFX_BANKCALL_ADDR EQU 0x1787

; FN_TRY_NUM（0x6B10）の入口。数値の項の先頭で呼ばれる。A=1で処理済み（CUR_TYPE/CUR_DATAに値、またはERROR_FLAG）。
; "POINT" の直後が '(' なら '(' を読み進めてバンク2の関数入口へ。そうでなければ位置を戻して従来の ts_try へ。
gfx_try_num:
    LD HL,(MM_CUR_PTR)
    PUSH HL
    LD HL,gfx_w_point
    CALL ts_kw
    OR A
    JR Z,gfx_tn_no
    CALL ts_peek
    CP '('
    JR NZ,gfx_tn_no
    CALL ts_adv
    POP HL
    LD HL,GFX_POINT_ENTRY
    CALL gfx_fwd
    LD A,1
    RET
gfx_tn_no:
    POP HL
    LD (MM_CUR_PTR),HL
    XOR A
    JP ts_try
gfx_w_point:
    DB "POINT",0
