;
; docs/spec/l4-program.md 4.22（l4-s9n）の観測から独立実装。本体はバンク0（deftype.asmの後ろへ連結）。
; このファイルは BEEP と誤り表示の音だけ（WIDTH は測定の続きの後に実装する）。
; ポート0x40は書き込み専用で読み戻せない（IN 0x40 は別の意味。l1-ipl.md のポート表）。
; そこで他のビット（b0〜b4）は、起動処理（l1-ipl.md 付録A）が最後に書く値 0x01 のまま保つ
; 定数にし、bit5（BEEP）だけを 0x21（鳴る）と 0x01（止める）で動かす。
; 未測定・自作判断: 他のビットは0x01を保つ（測定では窓内で動かなかったことだけが分かる）。
;   音の長さ（立ち上がりから立ち下がりまで）は約 0.1 秒（4MHz）の待ち。
;   BEL(CHR$(7))の出力は何も表示せずカーソルも動かさず、BEEP と同じ音だけ鳴らす。
;   誤りの音はメッセージの前。ERR 11（0除算）は鳴らさない（直接モードの print 1/0 の観測。
;   プログラム中・他の式の0除算は未測定でここと同じ扱い）。
;   BEEP n の n は 0〜255 の整数（範囲外は ERR 5、数値の溢れも ERR 5、文字列は ERR 13）。
;   引数の小数・3〜255 は未測定で、四捨五入した値が0以外なら鳴らし続ける。

WB_PORT EQU 040h
WB_OFF EQU 001h
WB_ON EQU 021h

; ---- mainからの固定入口（deftype.asmの後ろ）
    ORG 0x7A40
    JP wb_bell

; BEEP（文の種別41、第4.22.6節）。引数なし=鳴らして止める、BEEP n=nが0以外なら立てたまま・0なら下げる
wb_beep_stmt:
    CALL fn_skip
    CALL fn_peek
    OR A
    JR Z,wb_plain
    CP ':'
    JR Z,wb_plain
    CALL fn_is_string
    OR A
    JP NZ,fn_type
    CALL fn_expr
    CALL fn_bad
    RET NZ
    CALL fn_int
    OR A
    JP Z,fn_illegal
    LD A,D
    OR A
    JP NZ,fn_illegal
    LD A,E
    OR A
    LD A,WB_OFF
    JR Z,wb_write
    LD A,WB_ON
wb_write:
    OUT (WB_PORT),A
    JP fn_ok
wb_plain:
    CALL wb_bell
    JP fn_ok

; 引数なしのBEEPと誤り表示の音・BELの出力: bit5を立て、一定時間のあと下げる
wb_bell:
    LD A,WB_ON
    OUT (WB_PORT),A
    LD BC,04000h
wb_wait:
    DEC BC
    LD A,B
    OR C
    JR NZ,wb_wait
    LD A,WB_OFF
    OUT (WB_PORT),A
    RET
