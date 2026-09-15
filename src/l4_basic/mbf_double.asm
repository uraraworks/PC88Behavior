; mbf_double.asm — M7 段階4b-1: 倍精度 MBF(8B) 数値演算ルーチン
; （加算・減算・符号反転・比較・乗算・除算・整数/単精度との変換）。
;
; ----------------------------------------------------------------------------
; MIT License
;
; Copyright (c) Microsoft Corporation.
;
; Permission is hereby granted, free of charge, to any person obtaining a copy
; of this software and associated documentation files (the "Software"), to deal
; in the Software without restriction, including without limitation the rights
; to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
; copies of the Software, and to permit persons to whom the Software is
; furnished to do so, subject to the following conditions:
;
; The above copyright notice and this permission notice shall be included in all
; copies or substantial portions of the Software.
;
; THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
; IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
; FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
; AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
; LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
; OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
; SOFTWARE
; ----------------------------------------------------------------------------
;
; GW-BASIC edf82c2ebf6bfe099c2054e0ae125c3efe5769c4 の MATH1.ASM/MATH2.ASM の
; $FADDD/$FSUBD/$FMULD/$ROUND/DDIV のアルゴリズムをZ80で再表現したもの
; （8086命令の行単位の写経ではない）。加減算・乗算・除算はいずれも
; 「厳密値を求めて1回偶数丸め」と数学的に等価（mbf_single.asm の該当コメント、
; tools/l4_mbf_oracle_v2.py モジュールdocstring2-4番で確認済み）——単精度の
; $FMULS（粗い丸め）と違い、倍精度の$FMULDは正しい丸めなので、加減算・除算と
; 同じガード+スティッキー・偶数丸め方式をそのまま使う。
;
; このファイルは mbf_single.asm の直後に連結して1つのアセンブル単位として
; 使う前提（DA_*/DB_*・DBL_MUL・DBL_DIV・DBL_TO_SINGLE_CSD・SINGLE_TO_DOUBLE・
; MBF_UNPACK_A・MBF_STATUS 等、mbf_single.asm で定義済みのシンボルを呼ぶ）。
; RAM ワークエリアは mbf_single.asm が使う 0xC000-0xC169 と衝突しないよう
; 0xC200 以降に新規に確保した（仕様書に無い判断：単精度側の番地割り当てを
; そのまま踏襲しつつ、実際にインタプリタへ組み込む際の最終番地は次の担当
; 〔4b-2/4b-3〕が決める）。
;
; MBF倍精度8バイトの並び（tools/l4_mbf_oracle_v2.py mbf8_bytes/mbf8_from_bytes
; と同じ）: byte0=仮数下位8bit ... byte5=仮数第6バイト、
;           byte6=bit7:符号 bit6-0:仮数上位7bit(55bit仮数の最上位7bit、
;                 インプリシットビット=bit55は格納しない)
;           byte7=指数バイト(128げた上げ、0なら値0、単精度と同じ8bit・
;                 同じバイアスを共有する——SINGLE_TO_DOUBLE/DBL_TABLE_LOOKUP
;                 が単精度と同じexp_byteをそのまま倍精度でも使っている
;                 ことから明らか)。
; 値 = (-1)^符号 * (1.仮数55bit) * 2^(byte7-128-56+56) = mant56*2^(byte7-128-56)
; （mant56はインプリシットの先頭1を含めた56bit）
;
; オペランドは MBF_DOPA/MBF_DOPB（外部形式8バイト）に置いて呼ぶ。結果は
; MBF_DRES（8バイト）+ MBF_STATUS（mbf_single.asmと共有、0=正常 1=オーバー
; フロー 2=0除算）。比較は MBF_DOUT_CMP（1バイト、0/1/0xFF）。

; ---------------------------------------------------------------------
; RAM ワークエリア
; ---------------------------------------------------------------------
MBF_DOPA     EQU 0xC200   ; 被演算子A（またはNEG/CMP/DTOSの唯一の入力）8バイト
MBF_DOPB     EQU 0xC208   ; 被演算子B 8バイト
MBF_DRES     EQU 0xC210   ; 結果 8バイト
MBF_DOUT_CMP EQU 0xC218   ; MBF_DCMP の出力（0=等しい 1=A>B 0xFF=A<B）

; MBF_DADD/MBF_DSUBの位置合わせ用（BIG=勝者〈大きい方の指数〉、SML=敗者）。
; mbf_single.asm の BIG_*/SML_*（24bit仮数）と同じ設計を56bit仮数へ広げた
; だけ（仕様書に無い判断ではなく、同ファイル冒頭コメントの設計方針の踏襲）。
DBIG_SIGN EQU 0xC220
DBIG_EXP  EQU 0xC221
DBIG_M6   EQU 0xC222   ; MSB(bit7=暗黙の先頭1)
DBIG_M5   EQU 0xC223
DBIG_M4   EQU 0xC224
DBIG_M3   EQU 0xC225
DBIG_M2   EQU 0xC226
DBIG_M1   EQU 0xC227
DBIG_M0   EQU 0xC228   ; LSB
DBIG_MG   EQU 0xC229   ; ガードバイト

DSML_SIGN EQU 0xC22A
DSML_EXP  EQU 0xC22B
DSML_M6   EQU 0xC22C
DSML_M5   EQU 0xC22D
DSML_M4   EQU 0xC22E
DSML_M3   EQU 0xC22F
DSML_M2   EQU 0xC230
DSML_M1   EQU 0xC231
DSML_M0   EQU 0xC232
DSML_MG   EQU 0xC233

DWK_STICKY EQU 0xC234
DWK_BORROW EQU 0xC235
DWK_SHIFT  EQU 0xC236
DWK_TMP    EQU 0xC237

; MBF_DMUL専用（56bit×56bitの厳密112bit積。11byte〔32bit×56bit〕の
; DBL_MULを14byte〔56bit×56bit〕へ広げただけ）。
DPR13 EQU 0xC240   ; 積(112bit)のMSB側
DPR12 EQU 0xC241
DPR11 EQU 0xC242
DPR10 EQU 0xC243
DPR9  EQU 0xC244
DPR8  EQU 0xC245
DPR7  EQU 0xC246
DPR6  EQU 0xC247
DPR5  EQU 0xC248
DPR4  EQU 0xC249
DPR3  EQU 0xC24A
DPR2  EQU 0xC24B
DPR1  EQU 0xC24C
DPR0  EQU 0xC24D   ; LSB

DMC13 EQU 0xC24E   ; シフトしながら加算する被乗数(DBの56bitを14byteへ拡張)
DMC12 EQU 0xC24F
DMC11 EQU 0xC250
DMC10 EQU 0xC251
DMC9  EQU 0xC252
DMC8  EQU 0xC253
DMC7  EQU 0xC254
DMC6  EQU 0xC255
DMC5  EQU 0xC256
DMC4  EQU 0xC257
DMC3  EQU 0xC258
DMC2  EQU 0xC259
DMC1  EQU 0xC25A
DMC0  EQU 0xC25B

DWK_MULLOOP EQU 0xC25C
DWK_MULS    EQU 0xC25D   ; 2バイト、eA+eBの一時領域(0..510)

; =======================================================================
; DBL_UNPACK_A — MBF_DOPA(外部形式8byte)を DA_*（mbf_single.asmで定義済み、
; インプリシットビット込みの展開形式）へ展開する。AF,HL,B破壊。
; mbf_single.asm の MBF_UNPACK_A を56bit幅へ広げた形。
; =======================================================================
DBL_UNPACK_A:
    LD HL,MBF_DOPA+7
    LD A,(HL)
    LD (DA_EXP),A
    OR A
    JP Z,_dua_zero
    LD HL,MBF_DOPA+6
    LD A,(HL)
    LD B,A
    AND 0x80
    JP Z,_dua_pos
    LD A,1
    LD (DA_SIGN),A
    JP _dua_signdone
_dua_pos:
    XOR A
    LD (DA_SIGN),A
_dua_signdone:
    LD A,B
    AND 0x7F
    OR 0x80
    LD (DA_M6),A
    LD HL,MBF_DOPA+5
    LD A,(HL)
    LD (DA_M5),A
    LD HL,MBF_DOPA+4
    LD A,(HL)
    LD (DA_M4),A
    LD HL,MBF_DOPA+3
    LD A,(HL)
    LD (DA_M3),A
    LD HL,MBF_DOPA+2
    LD A,(HL)
    LD (DA_M2),A
    LD HL,MBF_DOPA+1
    LD A,(HL)
    LD (DA_M1),A
    LD HL,MBF_DOPA
    LD A,(HL)
    LD (DA_M0),A
    RET
_dua_zero:
    XOR A
    LD (DA_SIGN),A
    LD (DA_M6),A
    LD (DA_M5),A
    LD (DA_M4),A
    LD (DA_M3),A
    LD (DA_M2),A
    LD (DA_M1),A
    LD (DA_M0),A
    RET

; =======================================================================
; DBL_UNPACK_B — MBF_DOPB を DB_* へ展開する。AF,HL,B破壊。
; =======================================================================
DBL_UNPACK_B:
    LD HL,MBF_DOPB+7
    LD A,(HL)
    LD (DB_EXP),A
    OR A
    JP Z,_dub_zero
    LD HL,MBF_DOPB+6
    LD A,(HL)
    LD B,A
    AND 0x80
    JP Z,_dub_pos
    LD A,1
    LD (DB_SIGN),A
    JP _dub_signdone
_dub_pos:
    XOR A
    LD (DB_SIGN),A
_dub_signdone:
    LD A,B
    AND 0x7F
    OR 0x80
    LD (DB_M6),A
    LD HL,MBF_DOPB+5
    LD A,(HL)
    LD (DB_M5),A
    LD HL,MBF_DOPB+4
    LD A,(HL)
    LD (DB_M4),A
    LD HL,MBF_DOPB+3
    LD A,(HL)
    LD (DB_M3),A
    LD HL,MBF_DOPB+2
    LD A,(HL)
    LD (DB_M2),A
    LD HL,MBF_DOPB+1
    LD A,(HL)
    LD (DB_M1),A
    LD HL,MBF_DOPB
    LD A,(HL)
    LD (DB_M0),A
    RET
_dub_zero:
    XOR A
    LD (DB_SIGN),A
    LD (DB_M6),A
    LD (DB_M5),A
    LD (DB_M4),A
    LD (DB_M3),A
    LD (DB_M2),A
    LD (DB_M1),A
    LD (DB_M0),A
    RET

; =======================================================================
; DBL_PACK_RES — DA_SIGN/DA_EXP/DA_M6..M0（インプリシットビット込み）から
; MBF_DRES の8バイトを組み立てる。DBL_MUL/DBL_DIV/DBL_TO_SINGLE_CSD*と同じ
; 「結果はDAへ書き戻す」規約に合わせ、DA_*から直接パックする
; （mbf_single.asm MBF_PACK_RESの倍精度版）。AF,HL破壊。
; =======================================================================
DBL_PACK_RES:
    LD A,(DA_EXP)
    OR A
    JP NZ,_dpkr_nonzero
    XOR A
    LD HL,MBF_DRES
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    RET
_dpkr_nonzero:
    LD HL,MBF_DRES
    LD A,(DA_M0)
    LD (HL),A
    INC HL
    LD A,(DA_M1)
    LD (HL),A
    INC HL
    LD A,(DA_M2)
    LD (HL),A
    INC HL
    LD A,(DA_M3)
    LD (HL),A
    INC HL
    LD A,(DA_M4)
    LD (HL),A
    INC HL
    LD A,(DA_M5)
    LD (HL),A
    INC HL
    LD A,(DA_M6)
    AND 0x7F
    LD B,A
    LD A,(DA_SIGN)
    OR A
    JP Z,_dpkr_possign
    LD A,B
    OR 0x80
    JP _dpkr_setb6
_dpkr_possign:
    LD A,B
_dpkr_setb6:
    LD (HL),A
    INC HL
    LD A,(DA_EXP)
    LD (HL),A
    RET

; =======================================================================
; DBL_PACK_OVERFLOW — オーバーフロー時の残留値（$INFPD/$INFMD相当、
; 仮数全bit1・指数byte255）を RES_SIGN（mbf_single.asmと共有、呼び出し側が
; 事前に設定しておく）の符号で MBF_DRES に書き、MBF_STATUS=1にする。
; AF,HL破壊。
; =======================================================================
DBL_PACK_OVERFLOW:
    LD A,1
    LD (MBF_STATUS),A
    LD HL,MBF_DRES
    LD A,0xFF
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD A,(RES_SIGN)
    OR A
    JP Z,_dpko_pos
    LD A,0xFF
    JP _dpko_setb6
_dpko_pos:
    LD A,0x7F
_dpko_setb6:
    LD (HL),A
    INC HL
    LD A,0xFF
    LD (HL),A
    RET

; =======================================================================
; DBL_PACK_OVERFLOW_KEEPSTATUS — DBL_PACK_OVERFLOWと同じ残留値を書くが
; MBF_STATUSは変更しない（0除算=2を保つため。mbf_single.asm
; MBF_PACK_OVERFLOW_KEEPSTATUSの倍精度版）。AF,HL破壊。
; =======================================================================
DBL_PACK_OVERFLOW_KEEPSTATUS:
    LD HL,MBF_DRES
    LD A,0xFF
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD A,(RES_SIGN)
    OR A
    JP Z,_dpkok_pos
    LD A,0xFF
    JP _dpkok_setb6
_dpkok_pos:
    LD A,0x7F
_dpkok_setb6:
    LD (HL),A
    INC HL
    LD A,0xFF
    LD (HL),A
    RET

; =======================================================================
; MBF_DADD — MBF_DRES = MBF_DOPA + MBF_DOPB（倍精度）。MBF_STATUSを設定する。
; mbf_single.asm MBF_ADDの56bit仮数版。丸めはガード1byte+スティッキーの
; 偶数丸め（$FADDD/$ROUND相当。加減算は「厳密値を1回偶数丸め」と等価と
; 確認済みなので単精度と同じ方式でよい）。全レジスタ破壊可。
; =======================================================================
MBF_DADD:
    XOR A
    LD (MBF_STATUS),A
    LD (DWK_STICKY),A
    LD (DWK_BORROW),A
    CALL DBL_UNPACK_A
    CALL DBL_UNPACK_B

    LD A,(DA_EXP)
    OR A
    JP NZ,_dadd_a_nonzero
    ; A=0 -> 結果はB
    LD A,(DB_SIGN)
    LD (RES_SIGN),A
    LD A,(DB_EXP)
    LD (RES_EXP),A
    LD A,(DB_M6)
    LD (DBIG_M6),A
    LD A,(DB_M5)
    LD (DBIG_M5),A
    LD A,(DB_M4)
    LD (DBIG_M4),A
    LD A,(DB_M3)
    LD (DBIG_M3),A
    LD A,(DB_M2)
    LD (DBIG_M2),A
    LD A,(DB_M1)
    LD (DBIG_M1),A
    LD A,(DB_M0)
    LD (DBIG_M0),A
    JP _dadd_finish_from_big
_dadd_a_nonzero:
    LD A,(DB_EXP)
    OR A
    JP NZ,_dadd_both_nonzero
    ; B=0 -> 結果はA
    LD A,(DA_SIGN)
    LD (RES_SIGN),A
    LD A,(DA_EXP)
    LD (RES_EXP),A
    LD A,(DA_M6)
    LD (DBIG_M6),A
    LD A,(DA_M5)
    LD (DBIG_M5),A
    LD A,(DA_M4)
    LD (DBIG_M4),A
    LD A,(DA_M3)
    LD (DBIG_M3),A
    LD A,(DA_M2)
    LD (DBIG_M2),A
    LD A,(DA_M1)
    LD (DBIG_M1),A
    LD A,(DA_M0)
    LD (DBIG_M0),A
    JP _dadd_finish_from_big

_dadd_both_nonzero:
    ; どちらをBIGにするか決める（指数、等しければ仮数56bitの大小、MSBから）。
    LD A,(DA_EXP)
    LD B,A
    LD A,(DB_EXP)
    CP B
    JP C,_dadd_a_is_big
    JP NZ,_dadd_b_is_big
    LD A,(DA_M6)
    LD B,A
    LD A,(DB_M6)
    CP B
    JP C,_dadd_a_is_big
    JP NZ,_dadd_b_is_big
    LD A,(DA_M5)
    LD B,A
    LD A,(DB_M5)
    CP B
    JP C,_dadd_a_is_big
    JP NZ,_dadd_b_is_big
    LD A,(DA_M4)
    LD B,A
    LD A,(DB_M4)
    CP B
    JP C,_dadd_a_is_big
    JP NZ,_dadd_b_is_big
    LD A,(DA_M3)
    LD B,A
    LD A,(DB_M3)
    CP B
    JP C,_dadd_a_is_big
    JP NZ,_dadd_b_is_big
    LD A,(DA_M2)
    LD B,A
    LD A,(DB_M2)
    CP B
    JP C,_dadd_a_is_big
    JP NZ,_dadd_b_is_big
    LD A,(DA_M1)
    LD B,A
    LD A,(DB_M1)
    CP B
    JP C,_dadd_a_is_big
    JP NZ,_dadd_b_is_big
    LD A,(DA_M0)
    LD B,A
    LD A,(DB_M0)
    CP B
    JP C,_dadd_a_is_big
    ; ここに来るのは DB<=DA のとき（等しい場合を含む）。Aを大とする。
_dadd_a_is_big:
    LD A,(DA_SIGN)
    LD (DBIG_SIGN),A
    LD A,(DA_EXP)
    LD (DBIG_EXP),A
    LD A,(DA_M6)
    LD (DBIG_M6),A
    LD A,(DA_M5)
    LD (DBIG_M5),A
    LD A,(DA_M4)
    LD (DBIG_M4),A
    LD A,(DA_M3)
    LD (DBIG_M3),A
    LD A,(DA_M2)
    LD (DBIG_M2),A
    LD A,(DA_M1)
    LD (DBIG_M1),A
    LD A,(DA_M0)
    LD (DBIG_M0),A
    LD A,(DB_SIGN)
    LD (DSML_SIGN),A
    LD A,(DB_EXP)
    LD (DSML_EXP),A
    LD A,(DB_M6)
    LD (DSML_M6),A
    LD A,(DB_M5)
    LD (DSML_M5),A
    LD A,(DB_M4)
    LD (DSML_M4),A
    LD A,(DB_M3)
    LD (DSML_M3),A
    LD A,(DB_M2)
    LD (DSML_M2),A
    LD A,(DB_M1)
    LD (DSML_M1),A
    LD A,(DB_M0)
    LD (DSML_M0),A
    JP _dadd_have_bigsml
_dadd_b_is_big:
    LD A,(DB_SIGN)
    LD (DBIG_SIGN),A
    LD A,(DB_EXP)
    LD (DBIG_EXP),A
    LD A,(DB_M6)
    LD (DBIG_M6),A
    LD A,(DB_M5)
    LD (DBIG_M5),A
    LD A,(DB_M4)
    LD (DBIG_M4),A
    LD A,(DB_M3)
    LD (DBIG_M3),A
    LD A,(DB_M2)
    LD (DBIG_M2),A
    LD A,(DB_M1)
    LD (DBIG_M1),A
    LD A,(DB_M0)
    LD (DBIG_M0),A
    LD A,(DA_SIGN)
    LD (DSML_SIGN),A
    LD A,(DA_EXP)
    LD (DSML_EXP),A
    LD A,(DA_M6)
    LD (DSML_M6),A
    LD A,(DA_M5)
    LD (DSML_M5),A
    LD A,(DA_M4)
    LD (DSML_M4),A
    LD A,(DA_M3)
    LD (DSML_M3),A
    LD A,(DA_M2)
    LD (DSML_M2),A
    LD A,(DA_M1)
    LD (DSML_M1),A
    LD A,(DA_M0)
    LD (DSML_M0),A

_dadd_have_bigsml:
    XOR A
    LD (DBIG_MG),A
    LD (DSML_MG),A

    ; shift = DBIG_EXP - DSML_EXP
    LD A,(DBIG_EXP)
    LD B,A
    LD A,(DSML_EXP)
    LD C,A
    LD A,B
    SUB C
    LD (DWK_SHIFT),A
    OR A
    JP Z,_dadd_aligned

    CP 64
    JP C,_dadd_shift_loop_init
    ; 64以上は全部落ちる（仮数56bit+ガード8bit=64bitのシフトレジスタ幅を
    ; 超えたら全ビットが失われる。mbf_single.asm _add_の32(=24+8)と同じ
    ; 理屈——単精度は24bit仮数+8bitガード=32bit幅なので閾値32、倍精度は
    ; 56bit仮数+8bitガード=64bit幅なので閾値64。2026-09-15追記〔M7〕:
    ; 当初「56(仮数bit数)」を閾値にしていたが誤りで、故障注入用に組んだ
    ; sticky_loss_pairs_d〔ちょうどガードの外側1bitへ落ちる値〕の照合で
    ; shift=57のケースが「全部切り捨て」経路に落ち、ガードが常に0のまま
    ; 丸め切り捨てになる不一致(20/200件)として発覚した。修正後は
    ; 同テストが通る。仮数は常に非0なのでスティッキー確定で立つ）。
    XOR A
    LD (DSML_M6),A
    LD (DSML_M5),A
    LD (DSML_M4),A
    LD (DSML_M3),A
    LD (DSML_M2),A
    LD (DSML_M1),A
    LD (DSML_M0),A
    LD (DSML_MG),A
    LD A,1
    LD (DWK_STICKY),A
    JP _dadd_aligned

_dadd_shift_loop_init:
    LD B,A                     ; B=シフト回数(1..55)
_dadd_shift_loop:
    ; 64bit右シフト1回: (DSML_M6..M0,DSML_MG) を右へ、
    ; 落ちるbit(DSML_MGのbit0)をDWK_STICKYへOR。
    XOR A
    LD A,(DSML_M6)
    SRL A
    LD (DSML_M6),A
    LD A,(DSML_M5)
    RRA
    LD (DSML_M5),A
    LD A,(DSML_M4)
    RRA
    LD (DSML_M4),A
    LD A,(DSML_M3)
    RRA
    LD (DSML_M3),A
    LD A,(DSML_M2)
    RRA
    LD (DSML_M2),A
    LD A,(DSML_M1)
    RRA
    LD (DSML_M1),A
    LD A,(DSML_M0)
    RRA
    LD (DSML_M0),A
    LD A,(DSML_MG)
    RRA
    LD (DSML_MG),A
    JP NC,_dadd_shift_nostick
    LD A,1
    LD (DWK_STICKY),A
_dadd_shift_nostick:
    DJNZ _dadd_shift_loop

_dadd_aligned:
    LD A,(DBIG_SIGN)
    LD B,A
    LD A,(DSML_SIGN)
    CP B
    JP NZ,_dadd_diffsign

    ; 同符号: 64bit加算 (DBIG += DSML)、桁上げをキャリーへ
    LD A,(DBIG_MG)
    LD B,A
    LD A,(DSML_MG)
    ADD A,B
    LD (DBIG_MG),A
    LD A,(DBIG_M0)
    LD B,A
    LD A,(DSML_M0)
    ADC A,B
    LD (DBIG_M0),A
    LD A,(DBIG_M1)
    LD B,A
    LD A,(DSML_M1)
    ADC A,B
    LD (DBIG_M1),A
    LD A,(DBIG_M2)
    LD B,A
    LD A,(DSML_M2)
    ADC A,B
    LD (DBIG_M2),A
    LD A,(DBIG_M3)
    LD B,A
    LD A,(DSML_M3)
    ADC A,B
    LD (DBIG_M3),A
    LD A,(DBIG_M4)
    LD B,A
    LD A,(DSML_M4)
    ADC A,B
    LD (DBIG_M4),A
    LD A,(DBIG_M5)
    LD B,A
    LD A,(DSML_M5)
    ADC A,B
    LD (DBIG_M5),A
    LD A,(DBIG_M6)
    LD B,A
    LD A,(DSML_M6)
    ADC A,B
    LD (DBIG_M6),A
    JP NC,_dadd_same_nocarry
    ; 桁上げが出た: 64bit右シフト1（上からは桁上げの1が入る）。
    SCF
    LD A,(DBIG_M6)
    RR A
    LD (DBIG_M6),A
    LD A,(DBIG_M5)
    RR A
    LD (DBIG_M5),A
    LD A,(DBIG_M4)
    RR A
    LD (DBIG_M4),A
    LD A,(DBIG_M3)
    RR A
    LD (DBIG_M3),A
    LD A,(DBIG_M2)
    RR A
    LD (DBIG_M2),A
    LD A,(DBIG_M1)
    RR A
    LD (DBIG_M1),A
    LD A,(DBIG_M0)
    RR A
    LD (DBIG_M0),A
    LD A,(DBIG_MG)
    RR A
    LD (DBIG_MG),A
    JP NC,_dadd_same_carry_nostick
    LD A,1
    LD (DWK_STICKY),A
_dadd_same_carry_nostick:
    LD A,(DBIG_EXP)
    CP 0xFF
    JP NZ,_dadd_expinc_ok
    LD A,(DBIG_SIGN)
    LD (RES_SIGN),A
    JP DBL_PACK_OVERFLOW
_dadd_expinc_ok:
    INC A
    LD (DBIG_EXP),A
_dadd_same_nocarry:
    LD A,(DBIG_SIGN)
    LD (RES_SIGN),A
    LD A,(DBIG_EXP)
    LD (RES_EXP),A
    JP _dadd_round

_dadd_diffsign:
    ; 異符号: DBIG -= DSML（64bit減算、借りは出ない前提=DBIG>=DSML。
    ; mbf_single.asm _add_diffsignと同じ理屈で、桁借り時は2の補数として
    ; ガードバイトへ現れる）。
    LD A,1
    LD (DWK_BORROW),A
    LD A,(DBIG_MG)
    LD B,A
    LD A,(DSML_MG)
    LD C,A
    LD A,B
    SUB C
    LD (DBIG_MG),A
    LD A,(DBIG_M0)
    LD B,A
    LD A,(DSML_M0)
    LD C,A
    LD A,B
    SBC A,C
    LD (DBIG_M0),A
    LD A,(DBIG_M1)
    LD B,A
    LD A,(DSML_M1)
    LD C,A
    LD A,B
    SBC A,C
    LD (DBIG_M1),A
    LD A,(DBIG_M2)
    LD B,A
    LD A,(DSML_M2)
    LD C,A
    LD A,B
    SBC A,C
    LD (DBIG_M2),A
    LD A,(DBIG_M3)
    LD B,A
    LD A,(DSML_M3)
    LD C,A
    LD A,B
    SBC A,C
    LD (DBIG_M3),A
    LD A,(DBIG_M4)
    LD B,A
    LD A,(DSML_M4)
    LD C,A
    LD A,B
    SBC A,C
    LD (DBIG_M4),A
    LD A,(DBIG_M5)
    LD B,A
    LD A,(DSML_M5)
    LD C,A
    LD A,B
    SBC A,C
    LD (DBIG_M5),A
    LD A,(DBIG_M6)
    LD B,A
    LD A,(DSML_M6)
    LD C,A
    LD A,B
    SBC A,C
    LD (DBIG_M6),A

    LD A,(DBIG_SIGN)
    LD (RES_SIGN),A
    LD A,(DBIG_EXP)
    LD (RES_EXP),A

    ; 結果が完全に0か（8バイトとも0）
    LD A,(DBIG_M6)
    OR A
    JP NZ,_dadd_diff_norm
    LD A,(DBIG_M5)
    OR A
    JP NZ,_dadd_diff_norm
    LD A,(DBIG_M4)
    OR A
    JP NZ,_dadd_diff_norm
    LD A,(DBIG_M3)
    OR A
    JP NZ,_dadd_diff_norm
    LD A,(DBIG_M2)
    OR A
    JP NZ,_dadd_diff_norm
    LD A,(DBIG_M1)
    OR A
    JP NZ,_dadd_diff_norm
    LD A,(DBIG_M0)
    OR A
    JP NZ,_dadd_diff_norm
    LD A,(DBIG_MG)
    OR A
    JP NZ,_dadd_diff_norm
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    JP _dadd_finish_from_big

_dadd_diff_norm:
    ; 左正規化: DBIG_M6のbit7が1になるまで64bit左シフト、指数-1。
_dadd_norm_loop:
    LD A,(DBIG_M6)
    BIT 7,A
    JP NZ,_dadd_round
    LD A,(RES_EXP)
    CP 1
    JP NZ,_dadd_norm_dec
    ; これ以上下げられない(アンダーフロー) -> 結果0
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    JP _dadd_finish_from_big
_dadd_norm_dec:
    DEC A
    LD (RES_EXP),A
    XOR A
    LD A,(DBIG_MG)
    SLA A
    LD (DBIG_MG),A
    LD A,(DBIG_M0)
    RLA
    LD (DBIG_M0),A
    LD A,(DBIG_M1)
    RLA
    LD (DBIG_M1),A
    LD A,(DBIG_M2)
    RLA
    LD (DBIG_M2),A
    LD A,(DBIG_M3)
    RLA
    LD (DBIG_M3),A
    LD A,(DBIG_M4)
    RLA
    LD (DBIG_M4),A
    LD A,(DBIG_M5)
    RLA
    LD (DBIG_M5),A
    LD A,(DBIG_M6)
    RLA
    LD (DBIG_M6),A
    JP _dadd_norm_loop

_dadd_round:
    ; guard = DBIG_MG。判定はmbf_single.asm _add_roundと全く同じ理屈
    ; （幅が24bit->56bitへ広がるだけで丸め理論は不変）。
    LD A,(DBIG_MG)
    LD B,A
    BIT 7,B
    JP Z,_dadd_round_down
    LD A,B
    AND 0x7F
    JP NZ,_dadd_round_up
    LD A,(DWK_STICKY)
    OR A
    JP Z,_dadd_round_tie
    LD A,(DWK_BORROW)
    OR A
    JP NZ,_dadd_round_down
    JP _dadd_round_up
_dadd_round_tie:
    LD A,(DBIG_M0)
    BIT 0,A
    JP Z,_dadd_round_down
_dadd_round_up:
    LD A,(DBIG_M0)
    INC A
    LD (DBIG_M0),A
    JP NZ,_dadd_round_down
    LD A,(DBIG_M1)
    INC A
    LD (DBIG_M1),A
    JP NZ,_dadd_round_down
    LD A,(DBIG_M2)
    INC A
    LD (DBIG_M2),A
    JP NZ,_dadd_round_down
    LD A,(DBIG_M3)
    INC A
    LD (DBIG_M3),A
    JP NZ,_dadd_round_down
    LD A,(DBIG_M4)
    INC A
    LD (DBIG_M4),A
    JP NZ,_dadd_round_down
    LD A,(DBIG_M5)
    INC A
    LD (DBIG_M5),A
    JP NZ,_dadd_round_down
    LD A,(DBIG_M6)
    INC A
    LD (DBIG_M6),A
    JP NZ,_dadd_round_down
    ; 56bit全部繰り上がり -> 0x80:00:00:00:00:00:00へ、指数+1
    LD A,0x80
    LD (DBIG_M6),A
    XOR A
    LD (DBIG_M5),A
    LD (DBIG_M4),A
    LD (DBIG_M3),A
    LD (DBIG_M2),A
    LD (DBIG_M1),A
    LD (DBIG_M0),A
    LD A,(RES_EXP)
    CP 0xFF
    JP NZ,_dadd_round_expinc_ok
    JP DBL_PACK_OVERFLOW
_dadd_round_expinc_ok:
    INC A
    LD (RES_EXP),A
_dadd_round_down:
    JP _dadd_finish_from_big

; DBIG_M6..M0（丸め済み仮数）と RES_SIGN/RES_EXP（最終符号・指数）から
; DA_*へ書き戻し、DBL_PACK_RESでMBF_DRESへ詰める。
_dadd_finish_from_big:
    LD A,(RES_SIGN)
    LD (DA_SIGN),A
    LD A,(RES_EXP)
    LD (DA_EXP),A
    LD A,(DBIG_M6)
    LD (DA_M6),A
    LD A,(DBIG_M5)
    LD (DA_M5),A
    LD A,(DBIG_M4)
    LD (DA_M4),A
    LD A,(DBIG_M3)
    LD (DA_M3),A
    LD A,(DBIG_M2)
    LD (DA_M2),A
    LD A,(DBIG_M1)
    LD (DA_M1),A
    LD A,(DBIG_M0)
    LD (DA_M0),A
    JP DBL_PACK_RES

; =======================================================================
; MBF_DSUB — MBF_DRES = MBF_DOPA - MBF_DOPB（倍精度）。MBF_DOPB の符号
; バイト（オフセット+6、bit7）をその場で反転してから MBF_DADD へ入る
; （mbf_single.asm MBF_SUBと同じ形。ゼロはbyte7=0で判定するため、
; 符号ビット反転は0の判定に影響しない）。
; =======================================================================
MBF_DSUB:
    LD A,(MBF_DOPB+6)
    XOR 0x80
    LD (MBF_DOPB+6),A
    JP MBF_DADD

; =======================================================================
; MBF_DNEG — MBF_DRES = -MBF_DOPA。ゼロはゼロのまま（符号は変えない）。
; mbf_single.asm MBF_NEGの8byte版。
; =======================================================================
MBF_DNEG:
    LD A,(MBF_DOPA+7)
    LD (MBF_DRES+7),A
    LD B,A
    LD A,(MBF_DOPA)
    LD (MBF_DRES),A
    LD A,(MBF_DOPA+1)
    LD (MBF_DRES+1),A
    LD A,(MBF_DOPA+2)
    LD (MBF_DRES+2),A
    LD A,(MBF_DOPA+3)
    LD (MBF_DRES+3),A
    LD A,(MBF_DOPA+4)
    LD (MBF_DRES+4),A
    LD A,(MBF_DOPA+5)
    LD (MBF_DRES+5),A
    LD A,(MBF_DOPA+6)
    LD C,A
    LD A,B
    OR A
    JP Z,_dneg_iszero
    LD A,C
    XOR 0x80
    LD (MBF_DRES+6),A
    XOR A
    LD (MBF_STATUS),A
    RET
_dneg_iszero:
    LD A,C
    LD (MBF_DRES+6),A
    XOR A
    LD (MBF_STATUS),A
    RET

; =======================================================================
; MBF_DCMP — MBF_DOUT_CMP = sign(MBF_DOPA - MBF_DOPB) (0/1/0xFF)。
; MBF_DRES・MBF_STATUS は変更しない。mbf_single.asm MBF_CMPの56bit版。
; =======================================================================
MBF_DCMP:
    CALL DBL_UNPACK_A
    CALL DBL_UNPACK_B

    LD A,(DA_EXP)
    OR A
    JP NZ,_dcmp_a_nonzero
    LD A,(DB_EXP)
    OR A
    JP Z,_dcmp_eq
    LD A,(DB_SIGN)
    OR A
    JP Z,_dcmp_lt
    JP _dcmp_gt
_dcmp_a_nonzero:
    LD A,(DB_EXP)
    OR A
    JP NZ,_dcmp_both_nonzero
    LD A,(DA_SIGN)
    OR A
    JP Z,_dcmp_gt
    JP _dcmp_lt

_dcmp_both_nonzero:
    LD A,(DA_SIGN)
    LD B,A
    LD A,(DB_SIGN)
    CP B
    JP Z,_dcmp_samesign
    LD A,(DA_SIGN)
    OR A
    JP Z,_dcmp_gt
    JP _dcmp_lt

_dcmp_samesign:
    LD A,(DA_EXP)
    LD B,A
    LD A,(DB_EXP)
    CP B
    JP C,_dcmp_mag_a_gt
    JP NZ,_dcmp_mag_b_gt
    LD A,(DA_M6)
    LD B,A
    LD A,(DB_M6)
    CP B
    JP C,_dcmp_mag_a_gt
    JP NZ,_dcmp_mag_b_gt
    LD A,(DA_M5)
    LD B,A
    LD A,(DB_M5)
    CP B
    JP C,_dcmp_mag_a_gt
    JP NZ,_dcmp_mag_b_gt
    LD A,(DA_M4)
    LD B,A
    LD A,(DB_M4)
    CP B
    JP C,_dcmp_mag_a_gt
    JP NZ,_dcmp_mag_b_gt
    LD A,(DA_M3)
    LD B,A
    LD A,(DB_M3)
    CP B
    JP C,_dcmp_mag_a_gt
    JP NZ,_dcmp_mag_b_gt
    LD A,(DA_M2)
    LD B,A
    LD A,(DB_M2)
    CP B
    JP C,_dcmp_mag_a_gt
    JP NZ,_dcmp_mag_b_gt
    LD A,(DA_M1)
    LD B,A
    LD A,(DB_M1)
    CP B
    JP C,_dcmp_mag_a_gt
    JP NZ,_dcmp_mag_b_gt
    LD A,(DA_M0)
    LD B,A
    LD A,(DB_M0)
    CP B
    JP C,_dcmp_mag_a_gt
    JP NZ,_dcmp_mag_b_gt
    JP _dcmp_eq
_dcmp_mag_a_gt:
    LD A,(DA_SIGN)
    OR A
    JP Z,_dcmp_gt
    JP _dcmp_lt
_dcmp_mag_b_gt:
    LD A,(DA_SIGN)
    OR A
    JP Z,_dcmp_lt
    JP _dcmp_gt

_dcmp_eq:
    XOR A
    LD (MBF_DOUT_CMP),A
    RET
_dcmp_gt:
    LD A,1
    LD (MBF_DOUT_CMP),A
    RET
_dcmp_lt:
    LD A,0xFF
    LD (MBF_DOUT_CMP),A
    RET

; =======================================================================
; MBF_DMUL — MBF_DRES = MBF_DOPA * MBF_DOPB（倍精度）。MBF_STATUSを設定する。
;
; $FMULD (MATH2.ASM 308-407) の再現。単精度の$FMULSと違い、倍精度の
; $FMULDは厳密56bit×56bit積からガード+スティッキーで正しく丸める
; （mbf_single.asm DBL_MULのヘッダコメント参照——DBL_MULは32bit(DAが単精度/
; 整数からの変換由来で有効32bitしかない)×56bitの制限版だが、丸め方式は
; ここと同じ「厳密積全体からguard+sticky、偶数丸め」）。
;
; 仕様書に無い判断: このルーチンはDBL_MULと違い、DA・DBともに一般の56bit
; （MBF_DADD等の演算結果を再度掛け合わせる場合を含む）を許すため、
; 32bit×56bit(11byte積)ではなく56bit×56bit(14byte積)のshift-add乗算に
; 拡張した。乗数側(DA)を下位ビットから試し、その都度被乗数(DB)を14byteへ
; ゼロ拡張してから1bitずつ左シフトする構成はDBL_MULと同型（乗数を下位
; ビットから試す向きはDBL_MULのコメントにある通り、上位から試すと重みが
; 逆転して壊れる——同じ理由でこの向きを踏襲した）。
; =======================================================================
MBF_DMUL:
    CALL DBL_UNPACK_A
    CALL DBL_UNPACK_B
    XOR A
    LD (MBF_STATUS),A
    LD A,(DA_EXP)
    OR A
    JP Z,_dmulc_zero
    LD A,(DB_EXP)
    OR A
    JP Z,_dmulc_zero

    XOR A
    LD (DPR13),A
    LD (DPR12),A
    LD (DPR11),A
    LD (DPR10),A
    LD (DPR9),A
    LD (DPR8),A
    LD (DPR7),A
    LD (DPR6),A
    LD (DPR5),A
    LD (DPR4),A
    LD (DPR3),A
    LD (DPR2),A
    LD (DPR1),A
    LD (DPR0),A
    LD A,(DB_M0)
    LD (DMC0),A
    LD A,(DB_M1)
    LD (DMC1),A
    LD A,(DB_M2)
    LD (DMC2),A
    LD A,(DB_M3)
    LD (DMC3),A
    LD A,(DB_M4)
    LD (DMC4),A
    LD A,(DB_M5)
    LD (DMC5),A
    LD A,(DB_M6)
    LD (DMC6),A
    XOR A
    LD (DMC7),A
    LD (DMC8),A
    LD (DMC9),A
    LD (DMC10),A
    LD (DMC11),A
    LD (DMC12),A
    LD (DMC13),A

    LD A,56
    LD (DWK_MULLOOP),A
_dmulc_loop:
    ; DA_M6:M5:M4:M3:M2:M1:M0 (56bit,M6=MSB) を右へ1、落ちたbit0をCFへ
    LD A,(DA_M6)
    SRL A
    LD (DA_M6),A
    LD A,(DA_M5)
    RRA
    LD (DA_M5),A
    LD A,(DA_M4)
    RRA
    LD (DA_M4),A
    LD A,(DA_M3)
    RRA
    LD (DA_M3),A
    LD A,(DA_M2)
    RRA
    LD (DA_M2),A
    LD A,(DA_M1)
    RRA
    LD (DA_M1),A
    LD A,(DA_M0)
    RRA
    LD (DA_M0),A
    JP NC,_dmulc_noadd
    ; DPR(14byte) += DMC(14byte) LSBから
    LD A,(DPR0)
    LD B,A
    LD A,(DMC0)
    ADD A,B
    LD (DPR0),A
    LD A,(DPR1)
    LD B,A
    LD A,(DMC1)
    ADC A,B
    LD (DPR1),A
    LD A,(DPR2)
    LD B,A
    LD A,(DMC2)
    ADC A,B
    LD (DPR2),A
    LD A,(DPR3)
    LD B,A
    LD A,(DMC3)
    ADC A,B
    LD (DPR3),A
    LD A,(DPR4)
    LD B,A
    LD A,(DMC4)
    ADC A,B
    LD (DPR4),A
    LD A,(DPR5)
    LD B,A
    LD A,(DMC5)
    ADC A,B
    LD (DPR5),A
    LD A,(DPR6)
    LD B,A
    LD A,(DMC6)
    ADC A,B
    LD (DPR6),A
    LD A,(DPR7)
    LD B,A
    LD A,(DMC7)
    ADC A,B
    LD (DPR7),A
    LD A,(DPR8)
    LD B,A
    LD A,(DMC8)
    ADC A,B
    LD (DPR8),A
    LD A,(DPR9)
    LD B,A
    LD A,(DMC9)
    ADC A,B
    LD (DPR9),A
    LD A,(DPR10)
    LD B,A
    LD A,(DMC10)
    ADC A,B
    LD (DPR10),A
    LD A,(DPR11)
    LD B,A
    LD A,(DMC11)
    ADC A,B
    LD (DPR11),A
    LD A,(DPR12)
    LD B,A
    LD A,(DMC12)
    ADC A,B
    LD (DPR12),A
    LD A,(DPR13)
    LD B,A
    LD A,(DMC13)
    ADC A,B
    LD (DPR13),A
_dmulc_noadd:
    ; DMC(14byte)を左へ1 LSBから
    XOR A
    LD A,(DMC0)
    SLA A
    LD (DMC0),A
    LD A,(DMC1)
    RLA
    LD (DMC1),A
    LD A,(DMC2)
    RLA
    LD (DMC2),A
    LD A,(DMC3)
    RLA
    LD (DMC3),A
    LD A,(DMC4)
    RLA
    LD (DMC4),A
    LD A,(DMC5)
    RLA
    LD (DMC5),A
    LD A,(DMC6)
    RLA
    LD (DMC6),A
    LD A,(DMC7)
    RLA
    LD (DMC7),A
    LD A,(DMC8)
    RLA
    LD (DMC8),A
    LD A,(DMC9)
    RLA
    LD (DMC9),A
    LD A,(DMC10)
    RLA
    LD (DMC10),A
    LD A,(DMC11)
    RLA
    LD (DMC11),A
    LD A,(DMC12)
    RLA
    LD (DMC12),A
    LD A,(DMC13)
    RLA
    LD (DMC13),A
    LD A,(DWK_MULLOOP)
    DEC A
    LD (DWK_MULLOOP),A
    JP NZ,_dmulc_loop

    ; 指数: S=eA+eB (0..510)、single/DBL_MULと同じ判定式
    LD A,(DA_SIGN)
    LD B,A
    LD A,(DB_SIGN)
    XOR B
    LD (RES_SIGN),A
    LD A,(DA_EXP)
    LD H,0
    LD L,A
    LD A,(DB_EXP)
    LD D,0
    LD E,A
    ADD HL,DE
    LD (DWK_MULS),HL
    LD DE,385
    OR A
    SBC HL,DE
    JP NC,_dmulc_overflow
    LD HL,(DWK_MULS)
    LD DE,129
    OR A
    SBC HL,DE
    JP C,_dmulc_zero
    LD A,L
    LD (RES_EXP),A

    ; 正規化: DPR13のbit7が立っていればそのまま(exp_adj=1)、
    ; 立っていなければ1bit左シフト(exp_adj=0)。
    LD A,(DPR13)
    BIT 7,A
    JP NZ,_dmulc_asis
    XOR A
    LD A,(DPR0)
    SLA A
    LD (DPR0),A
    LD A,(DPR1)
    RLA
    LD (DPR1),A
    LD A,(DPR2)
    RLA
    LD (DPR2),A
    LD A,(DPR3)
    RLA
    LD (DPR3),A
    LD A,(DPR4)
    RLA
    LD (DPR4),A
    LD A,(DPR5)
    RLA
    LD (DPR5),A
    LD A,(DPR6)
    RLA
    LD (DPR6),A
    LD A,(DPR7)
    RLA
    LD (DPR7),A
    LD A,(DPR8)
    RLA
    LD (DPR8),A
    LD A,(DPR9)
    RLA
    LD (DPR9),A
    LD A,(DPR10)
    RLA
    LD (DPR10),A
    LD A,(DPR11)
    RLA
    LD (DPR11),A
    LD A,(DPR12)
    RLA
    LD (DPR12),A
    LD A,(DPR13)
    RLA
    LD (DPR13),A
    JP _dmulc_have_m
_dmulc_asis:
    LD A,(RES_EXP)
    INC A
    LD (RES_EXP),A
    JP NZ,_dmulc_have_m
    JP DBL_PACK_OVERFLOW
_dmulc_have_m:
    ; candidate = DPR13:DPR12:DPR11:DPR10:DPR9:DPR8:DPR7 (56bit)
    ; guard = DPR6, sticky = DPR5|DPR4|DPR3|DPR2|DPR1|DPR0|(DPR6&0x7F)
    LD A,(DPR6)
    LD B,A
    BIT 7,B
    JP Z,_dmulc_round_down
    LD A,B
    AND 0x7F
    LD C,A
    LD A,(DPR5)
    OR C
    LD C,A
    LD A,(DPR4)
    OR C
    LD C,A
    LD A,(DPR3)
    OR C
    LD C,A
    LD A,(DPR2)
    OR C
    LD C,A
    LD A,(DPR1)
    OR C
    LD C,A
    LD A,(DPR0)
    OR C
    JP NZ,_dmulc_round_up
    LD A,(DPR7)
    BIT 0,A
    JP Z,_dmulc_round_down
_dmulc_round_up:
    LD A,(DPR7)
    INC A
    LD (DPR7),A
    JP NZ,_dmulc_round_down
    LD A,(DPR8)
    INC A
    LD (DPR8),A
    JP NZ,_dmulc_round_down
    LD A,(DPR9)
    INC A
    LD (DPR9),A
    JP NZ,_dmulc_round_down
    LD A,(DPR10)
    INC A
    LD (DPR10),A
    JP NZ,_dmulc_round_down
    LD A,(DPR11)
    INC A
    LD (DPR11),A
    JP NZ,_dmulc_round_down
    LD A,(DPR12)
    INC A
    LD (DPR12),A
    JP NZ,_dmulc_round_down
    LD A,(DPR13)
    INC A
    LD (DPR13),A
    JP NZ,_dmulc_round_down
    LD A,0x80
    LD (DPR13),A
    XOR A
    LD (DPR12),A
    LD (DPR11),A
    LD (DPR10),A
    LD (DPR9),A
    LD (DPR8),A
    LD (DPR7),A
    LD A,(RES_EXP)
    INC A
    LD (RES_EXP),A
    JP Z,_dmulc_overflow2
_dmulc_round_down:
    LD A,(DPR13)
    LD (DA_M6),A
    LD A,(DPR12)
    LD (DA_M5),A
    LD A,(DPR11)
    LD (DA_M4),A
    LD A,(DPR10)
    LD (DA_M3),A
    LD A,(DPR9)
    LD (DA_M2),A
    LD A,(DPR8)
    LD (DA_M1),A
    LD A,(DPR7)
    LD (DA_M0),A
    LD A,(RES_SIGN)
    LD (DA_SIGN),A
    LD A,(RES_EXP)
    LD (DA_EXP),A
    JP DBL_PACK_RES
_dmulc_zero:
    XOR A
    LD (DA_SIGN),A
    LD (DA_EXP),A
    LD (DA_M6),A
    LD (DA_M5),A
    LD (DA_M4),A
    LD (DA_M3),A
    LD (DA_M2),A
    LD (DA_M1),A
    LD (DA_M0),A
    JP DBL_PACK_RES
_dmulc_overflow2:
_dmulc_overflow:
    JP DBL_PACK_OVERFLOW

; =======================================================================
; MBF_DDIV — MBF_DRES = MBF_DOPA / MBF_DOPB（倍精度）。MBF_STATUSを設定する
; (0=正常 1=オーバーフロー 2=0除算)。
;
; 除算の本体は mbf_single.asm の DBL_DIV（56bit÷56bit、復元法63回、
; ガード+スティッキー偶数丸め——単精度MBF_DIVの31回版と同型を56bit幅へ
; 広げたもの）をそのまま呼ぶ。DBL_DIV自体は元々FOUTの10進スケーリング
; （除数=DBL_TABLEの10のべき、常に正）専用に書かれたものだが、内部は
; 符号もXORで一般に扱っており、0除算のチェックだけが無い
; （呼び出し元〔FOUT〕が常に非0の除数しか渡さないため）。このラッパで
; 0除数のケースを先に弾き、オーバーフロー時の残留値パックだけ補う
; （DBL_MUL/DBL_DIVはオーバーフロー時にMBF_STATUS=1を設定するだけで
; MBF_DRES/DA_*を書かない——mbf_single.asm MBF_DIVのように、ここでは
; 呼び出し側でRES_SIGN経由のDBL_PACK_OVERFLOWへ振り分ける）。
; =======================================================================
MBF_DDIV:
    CALL DBL_UNPACK_A
    CALL DBL_UNPACK_B
    XOR A
    LD (MBF_STATUS),A
    LD A,(DB_EXP)
    OR A
    JP NZ,_dddiv_b_nonzero
    ; 0除算
    LD A,(DA_EXP)
    OR A
    JP Z,_dddiv_zerobyzero_sign
    LD A,(DA_SIGN)
    LD (RES_SIGN),A
    JP _dddiv_zerodivide_pack
_dddiv_zerobyzero_sign:
    XOR A
    LD (RES_SIGN),A
_dddiv_zerodivide_pack:
    LD A,2
    LD (MBF_STATUS),A
    JP DBL_PACK_OVERFLOW_KEEPSTATUS
_dddiv_b_nonzero:
    CALL DBL_DIV
    LD A,(MBF_STATUS)
    CP 1
    JP Z,DBL_PACK_OVERFLOW
    JP DBL_PACK_RES

; =======================================================================
; MBF_ITOD — MBF_IN_INT（符号付き16bit、mbf_single.asmと共有）を倍精度MBF
; へ変換し MBF_DRES へ書く。0はゼロ、それ以外は正規化して詰める。
; mbf_single.asm MBF_INT_TO_SINGLEと全く同じ正規化（exp=144-shifts）を
; 使う——SINGLE_TO_DOUBLEのコメントの通り、単精度と倍精度は同じ指数バイト
; 表現を共有するため、16bit整数は仮数56bitの上位16bit(M6,M5)へ置き、
; 下位40bitを0にするだけで厳密に表現できる（丸め不要）。
; =======================================================================
MBF_ITOD:
    XOR A
    LD (MBF_STATUS),A
    LD HL,(MBF_IN_INT)
    LD A,H
    OR L
    JP NZ,_i2d_nonzero
    XOR A
    LD (DA_SIGN),A
    LD (DA_EXP),A
    LD (DA_M6),A
    LD (DA_M5),A
    LD (DA_M4),A
    LD (DA_M3),A
    LD (DA_M2),A
    LD (DA_M1),A
    LD (DA_M0),A
    JP DBL_PACK_RES
_i2d_nonzero:
    LD A,H
    BIT 7,A
    JP Z,_i2d_pos
    LD A,1
    LD (DA_SIGN),A
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
    JP _i2d_haveabs
_i2d_pos:
    XOR A
    LD (DA_SIGN),A
_i2d_haveabs:
    LD B,144
_i2d_norm:
    BIT 7,H
    JP NZ,_i2d_normed
    SLA L
    RL H
    DEC B
    JP _i2d_norm
_i2d_normed:
    LD A,B
    LD (DA_EXP),A
    LD A,H
    LD (DA_M6),A
    LD A,L
    LD (DA_M5),A
    XOR A
    LD (DA_M4),A
    LD (DA_M3),A
    LD (DA_M2),A
    LD (DA_M1),A
    LD (DA_M0),A
    JP DBL_PACK_RES

; =======================================================================
; MBF_STOD — MBF_OPA（単精度、mbf_single.asmと共有の外部形式4byte）を
; 倍精度へ厳密変換し MBF_DRES へ書く（丸め不要。mbf_single.asm
; SINGLE_TO_DOUBLEをそのまま使う）。
; =======================================================================
MBF_STOD:
    XOR A
    LD (MBF_STATUS),A
    CALL MBF_UNPACK_A
    CALL SINGLE_TO_DOUBLE
    JP DBL_PACK_RES

; =======================================================================
; MBF_DTOS — MBF_DOPA（倍精度）を単精度へ切り詰め MBF_RES（mbf_single.asm
; と共有の外部形式4byte）へ書く。$CSD丸め（mbf_single.asm
; DBL_TO_SINGLE_CSDをそのまま使う）。
; =======================================================================
MBF_DTOS:
    XOR A
    LD (MBF_STATUS),A
    CALL DBL_UNPACK_A
    JP DBL_TO_SINGLE_CSD
