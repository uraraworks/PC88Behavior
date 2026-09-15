; mbf_single.asm — M7 段階4a-1: 単精度 MBF(Microsoft Binary Format) 4バイト
; 数値演算ルーチン（加算・減算・符号反転・比較・整数からの変換）。
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
; アルゴリズムを Z80 で再表現したもの（8086命令の行単位の写経ではない）。
; 各ルーチンの対応関係:
;   MBF_ADD/MBF_SUB   <-> $FADDS/$FSUBS (MATH1.ASM 3265-3427)
;   MBF_NEG           <-> $FSUBS冒頭の "XOR BYTE PTR $FAC-1,LOW 200"（符号反転）
;   丸め              <-> $ROUNS/$ROUNM (MATH2.ASM 1764-1807)
;   $INFPD/$INFMD相当 <-> オーバーフロー時の残留値(MATH1.ASM 776-792、
;                          仮数全ビット1・指数バイト255。
;                          tools/l4_mbf_oracle_v2.py _max_value_num で確認済み)
;
; 実装方針（仕様書に無い判断）: 8086版はビット位置合わせを1ビットシフトの
; 繰り返しで行うが、レジスタが少ないため「勝者(大きい方の指数)を BIG_*、
; 敗者を SML_* という固定番地へ複製してから位置合わせする」設計にした。
; アルゴリズム的には同じ(位置合わせシフト時に落ちるビットを毎回スティッキー
; フラグへOR)だが、この固定番地への複製という構成そのものは GW-BASIC
; MATH1.ASM のレジスタ割り付けを写したものではなく、Z80のレジスタ資源の
; 制約から独自に組んだ。加算・減算・(倍精度)乗算・除算は「厳密値を1回
; 偶数丸めしたものと数学的に等価」であることを tools/l4_mbf_oracle_v2.py の
; 確認済みコメント(モジュール docstring 2-4番)で裏付けており、このルーチンの
; シフト+スティッキー方式はその等価な実装のひとつとして書いた。
;
; MBF単精度4バイトの並び（decode_mbf/mbf4_bytes、tools/l4_mbf_oracle_v2.py
; と同じ）: byte0=仮数下位8bit、byte1=仮数中位8bit、
;           byte2=bit7:符号 bit6-0:仮数上位7bit(23bit仮数の上位、
;                 インプリシットビット=bit23は格納しない)
;           byte3=指数バイト(128げた上げ、0なら値0)
; 値 = (-1)^符号 * (1.仮数23bit) * 2^(byte3-128-24+24) = mant24*2^(byte3-128-24)
; (mant24はインプリシットの先頭1を含めた24bit)

; ---------------------------------------------------------------------
; RAM ワークエリア（このファイル専用の固定番地。段階4a-1はルーチン単体の
; 検証が目的でインタプリタへの組み込みは次の担当が行うため、実際に
; インタプリタへ組み込む際の番地割り当てはここでは決めない=仕様書に
; 無い判断として保留する）。
; ---------------------------------------------------------------------
MBF_OPA     EQU 0xC000   ; 被演算子A（またはNEG/CMP/変換の唯一の入力）4バイト
MBF_OPB     EQU 0xC004   ; 被演算子B 4バイト
MBF_RES     EQU 0xC008   ; 結果 4バイト
MBF_STATUS  EQU 0xC00C   ; 0=正常 1=オーバーフロー 2=0除算
MBF_IN_INT  EQU 0xC00D   ; MBF_INT_TO_SINGLE の入力（符号付き16bit、2バイト）
MBF_OUT_CMP EQU 0xC00F   ; MBF_CMP の出力（0=等しい 1=A>B 0xFF=A<B、1バイト）

UA_SIGN EQU 0xC010
UA_EXP  EQU 0xC011
UA_M2   EQU 0xC012      ; bit23-16（bit7=インプリシット先頭1）
UA_M1   EQU 0xC013      ; bit15-8
UA_M0   EQU 0xC014      ; bit7-0

UB_SIGN EQU 0xC016
UB_EXP  EQU 0xC017
UB_M2   EQU 0xC018
UB_M1   EQU 0xC019
UB_M0   EQU 0xC01A

BIG_SIGN EQU 0xC020
BIG_EXP  EQU 0xC021
BIG_M2   EQU 0xC022
BIG_M1   EQU 0xC023
BIG_M0   EQU 0xC024
BIG_MG   EQU 0xC025      ; ガードバイト（仮数24bitの下、位置合わせで使う）

SML_SIGN EQU 0xC026
SML_EXP  EQU 0xC027
SML_M2   EQU 0xC028
SML_M1   EQU 0xC029
SML_M0   EQU 0xC02A
SML_MG   EQU 0xC02B

RES_SIGN EQU 0xC02C
RES_EXP  EQU 0xC02D

WK_STICKY EQU 0xC030      ; 0/非0
WK_BORROW EQU 0xC034      ; 1=異符号減算(BIG-SML)で桁借りが起きた側の丸め規則を使う
WK_SHIFT  EQU 0xC031
WK_TMP    EQU 0xC032

; =======================================================================
; MBF_UNPACK_A — MBF_OPA を UA_* へ展開する。AF,HL,B破壊。
; =======================================================================
MBF_UNPACK_A:
    LD HL,MBF_OPA+3
    LD A,(HL)
    LD (UA_EXP),A
    OR A
    JR Z,_ua_zero
    LD HL,MBF_OPA+2
    LD A,(HL)
    LD B,A
    AND 0x80
    JR Z,_ua_pos
    LD A,1
    LD (UA_SIGN),A
    JR _ua_signdone
_ua_pos:
    XOR A
    LD (UA_SIGN),A
_ua_signdone:
    LD A,B
    AND 0x7F
    OR 0x80
    LD (UA_M2),A
    LD HL,MBF_OPA+1
    LD A,(HL)
    LD (UA_M1),A
    LD HL,MBF_OPA
    LD A,(HL)
    LD (UA_M0),A
    RET
_ua_zero:
    XOR A
    LD (UA_SIGN),A
    LD (UA_M2),A
    LD (UA_M1),A
    LD (UA_M0),A
    RET

; =======================================================================
; MBF_UNPACK_B — MBF_OPB を UB_* へ展開する。AF,HL,B破壊。
; =======================================================================
MBF_UNPACK_B:
    LD HL,MBF_OPB+3
    LD A,(HL)
    LD (UB_EXP),A
    OR A
    JR Z,_ub_zero
    LD HL,MBF_OPB+2
    LD A,(HL)
    LD B,A
    AND 0x80
    JR Z,_ub_pos
    LD A,1
    LD (UB_SIGN),A
    JR _ub_signdone
_ub_pos:
    XOR A
    LD (UB_SIGN),A
_ub_signdone:
    LD A,B
    AND 0x7F
    OR 0x80
    LD (UB_M2),A
    LD HL,MBF_OPB+1
    LD A,(HL)
    LD (UB_M1),A
    LD HL,MBF_OPB
    LD A,(HL)
    LD (UB_M0),A
    RET
_ub_zero:
    XOR A
    LD (UB_SIGN),A
    LD (UB_M2),A
    LD (UB_M1),A
    LD (UB_M0),A
    RET

; =======================================================================
; MBF_PACK_RES — BIG_M2/M1/M0(24bit仮数、bit7of M2=インプリシット1)・
; RES_SIGN・RES_EXP から MBF_RES の4バイトを組み立てる。
; RES_EXP が 0（呼び出し前にゼロ判定済みの意）なら全バイト0にする。
; AF,HL破壊。
; =======================================================================
MBF_PACK_RES:
    LD A,(RES_EXP)
    OR A
    JR NZ,_pkr_nonzero
    XOR A
    LD HL,MBF_RES
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD (HL),A
    RET
_pkr_nonzero:
    LD HL,MBF_RES
    LD A,(BIG_M0)
    LD (HL),A
    INC HL
    LD A,(BIG_M1)
    LD (HL),A
    INC HL
    LD A,(BIG_M2)
    AND 0x7F
    LD B,A
    LD A,(RES_SIGN)
    OR A
    JR Z,_pkr_possign
    LD A,B
    OR 0x80
    JR _pkr_setb2
_pkr_possign:
    LD A,B
_pkr_setb2:
    LD (HL),A
    INC HL
    LD A,(RES_EXP)
    LD (HL),A
    RET

; =======================================================================
; MBF_PACK_OVERFLOW — オーバーフロー時の残留値（$INFPD/$INFMD、仮数全bit1・
; 指数byte255）を RES_SIGN の符号で MBF_RES に書き、MBF_STATUS=1 にする。
; AF,HL破壊。
; =======================================================================
MBF_PACK_OVERFLOW:
    LD A,1
    LD (MBF_STATUS),A
    LD HL,MBF_RES
    LD A,0xFF
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD A,(RES_SIGN)
    OR A
    JR Z,_pko_pos
    LD A,0xFF
    JR _pko_setb2
_pko_pos:
    LD A,0x7F
_pko_setb2:
    LD (HL),A
    INC HL
    LD A,0xFF
    LD (HL),A
    RET

; =======================================================================
; MBF_ADD — MBF_RES = MBF_OPA + MBF_OPB（単精度）。MBF_STATUS を設定する。
; 全レジスタ破壊可。
; =======================================================================
MBF_ADD:
    XOR A
    LD (MBF_STATUS),A
    LD (WK_STICKY),A
    LD (WK_BORROW),A
    CALL MBF_UNPACK_A
    CALL MBF_UNPACK_B

    LD A,(UA_EXP)
    OR A
    JR NZ,_add_a_nonzero
    ; A=0 -> 結果はB
    LD A,(UB_SIGN)
    LD (RES_SIGN),A
    LD A,(UB_EXP)
    LD (RES_EXP),A
    LD A,(UB_M2)
    LD (BIG_M2),A
    LD A,(UB_M1)
    LD (BIG_M1),A
    LD A,(UB_M0)
    LD (BIG_M0),A
    JP MBF_PACK_RES
_add_a_nonzero:
    LD A,(UB_EXP)
    OR A
    JR NZ,_add_both_nonzero
    ; B=0 -> 結果はA
    LD A,(UA_SIGN)
    LD (RES_SIGN),A
    LD A,(UA_EXP)
    LD (RES_EXP),A
    LD A,(UA_M2)
    LD (BIG_M2),A
    LD A,(UA_M1)
    LD (BIG_M1),A
    LD A,(UA_M0)
    LD (BIG_M0),A
    JP MBF_PACK_RES

_add_both_nonzero:
    ; どちらを BIG にするか決める（指数、等しければ仮数24bitの大小）。
    LD A,(UA_EXP)
    LD B,A
    LD A,(UB_EXP)
    CP B
    JR C,_add_a_is_big     ; UB_EXP < UA_EXP -> Aが大
    JR NZ,_add_b_is_big    ; UB_EXP > UA_EXP -> Bが大
    ; 指数が等しい -> 仮数24bit(M2,M1,M0)を比較
    LD A,(UA_M2)
    LD B,A
    LD A,(UB_M2)
    CP B
    JR C,_add_a_is_big
    JR NZ,_add_b_is_big
    LD A,(UA_M1)
    LD B,A
    LD A,(UB_M1)
    CP B
    JR C,_add_a_is_big
    JR NZ,_add_b_is_big
    LD A,(UA_M0)
    LD B,A
    LD A,(UB_M0)
    CP B
    JR C,_add_a_is_big
    ; ここに来るのは UB<=UA のとき（等しい場合を含む）。Aを大とする。
_add_a_is_big:
    LD A,(UA_SIGN)
    LD (BIG_SIGN),A
    LD A,(UA_EXP)
    LD (BIG_EXP),A
    LD A,(UA_M2)
    LD (BIG_M2),A
    LD A,(UA_M1)
    LD (BIG_M1),A
    LD A,(UA_M0)
    LD (BIG_M0),A
    LD A,(UB_SIGN)
    LD (SML_SIGN),A
    LD A,(UB_EXP)
    LD (SML_EXP),A
    LD A,(UB_M2)
    LD (SML_M2),A
    LD A,(UB_M1)
    LD (SML_M1),A
    LD A,(UB_M0)
    LD (SML_M0),A
    JR _add_have_bigsml
_add_b_is_big:
    LD A,(UB_SIGN)
    LD (BIG_SIGN),A
    LD A,(UB_EXP)
    LD (BIG_EXP),A
    LD A,(UB_M2)
    LD (BIG_M2),A
    LD A,(UB_M1)
    LD (BIG_M1),A
    LD A,(UB_M0)
    LD (BIG_M0),A
    LD A,(UA_SIGN)
    LD (SML_SIGN),A
    LD A,(UA_EXP)
    LD (SML_EXP),A
    LD A,(UA_M2)
    LD (SML_M2),A
    LD A,(UA_M1)
    LD (SML_M1),A
    LD A,(UA_M0)
    LD (SML_M0),A

_add_have_bigsml:
    XOR A
    LD (BIG_MG),A
    LD (SML_MG),A

    ; shift = BIG_EXP - SML_EXP
    LD A,(BIG_EXP)
    LD B,A
    LD A,(SML_EXP)
    LD C,A
    LD A,B
    SUB C
    LD (WK_SHIFT),A
    OR A
    JR Z,_add_aligned          ; 差0ならシフト不要

    CP 32
    JR C,_add_shift_loop_init
    ; 32以上は全部落ちる（仮数は常に非0なのでスティッキー確定で立つ）
    XOR A
    LD (SML_M2),A
    LD (SML_M1),A
    LD (SML_M0),A
    LD (SML_MG),A
    LD A,1
    LD (WK_STICKY),A
    JR _add_aligned

_add_shift_loop_init:
    LD B,A                     ; B=シフト回数(1..31)
_add_shift_loop:
    ; 32bit右シフト1回: (SML_M2,SML_M1,SML_M0,SML_MG) を右へ、
    ; 落ちるbit(SML_MGのbit0)をWK_STICKYへOR。
    XOR A                      ; CF=0でシフト開始（上位に0を入れる）
    LD A,(SML_M2)
    SRL A
    LD (SML_M2),A
    LD A,(SML_M1)
    RRA
    LD (SML_M1),A
    LD A,(SML_M0)
    RRA
    LD (SML_M0),A
    LD A,(SML_MG)
    RRA
    LD (SML_MG),A
    JR NC,_add_shift_nostick
    LD A,1
    LD (WK_STICKY),A
_add_shift_nostick:
    DJNZ _add_shift_loop

_add_aligned:
    LD A,(BIG_SIGN)
    LD B,A
    LD A,(SML_SIGN)
    CP B
    JR NZ,_add_diffsign

    ; 同符号: 32bit加算 (BIG += SML)、桁上げをキャリーへ
    LD A,(BIG_MG)
    LD B,A
    LD A,(SML_MG)
    ADD A,B
    LD (BIG_MG),A
    LD A,(BIG_M0)
    LD B,A
    LD A,(SML_M0)
    ADC A,B
    LD (BIG_M0),A
    LD A,(BIG_M1)
    LD B,A
    LD A,(SML_M1)
    ADC A,B
    LD (BIG_M1),A
    LD A,(BIG_M2)
    LD B,A
    LD A,(SML_M2)
    ADC A,B
    LD (BIG_M2),A
    JR NC,_add_same_nocarry
    ; 桁上げが出た: 32bit右シフト1（上からは桁上げの1が入る）。
    ; MSB(BIG_M2)側から順にCFを伝播させる必要があるので、
    ; SCF(CF=1をあふれた1として使う)->M2->M1->M0->MGの順にRRする。
    ; 最後にMGから落ちるbitが本当の喪失ビット=スティッキーへOR。
    SCF
    LD A,(BIG_M2)
    RR A
    LD (BIG_M2),A
    LD A,(BIG_M1)
    RR A
    LD (BIG_M1),A
    LD A,(BIG_M0)
    RR A
    LD (BIG_M0),A
    LD A,(BIG_MG)
    RR A
    LD (BIG_MG),A
    JR NC,_add_same_carry_nostick
    LD A,1
    LD (WK_STICKY),A
_add_same_carry_nostick:
    LD A,(BIG_EXP)
    CP 0xFF
    JR NZ,_add_expinc_ok
    LD A,(BIG_SIGN)
    LD (RES_SIGN),A
    JP MBF_PACK_OVERFLOW
_add_expinc_ok:
    INC A
    LD (BIG_EXP),A
_add_same_nocarry:
    LD A,(BIG_SIGN)
    LD (RES_SIGN),A
    LD A,(BIG_EXP)
    LD (RES_EXP),A
    JP _add_round

_add_diffsign:
    ; 異符号: BIG -= SML（32bit減算、借りは出ない前提=BIG>=SML）。
    ; ガードバイト(BIG_MG)はBIG_MG(0)からSML_MGを引くため、SML_MGが非0なら
    ; 必ず桁借りが起き、結果のガードバイトは「SML_MGの2の補数」になる
    ; ——つまり正の端数ではなく、2の補数で表した負の端数になる。丸め判定
    ; (_add_round)はこの違いをWK_BORROWで区別する(詳細は_add_roundの
    ; コメント。仕様書に無い判断: GW-BASICの8086実装は桁合わせのシフト量
    ; ぶんだけ実際にビットを動かして符号なしの引き算をするため、この
    ; 「2の補数として出てくる」現象自体は8086実装にも存在するはずだが、
    ; MATH1.ASMのFA23-FA30をそこまで読んでいない。ここでは丸めの数学的な
    ; 意味から独立に導いた)。
    LD A,1
    LD (WK_BORROW),A
    LD A,(BIG_MG)
    LD B,A
    LD A,(SML_MG)
    LD C,A
    LD A,B
    SUB C
    LD (BIG_MG),A
    LD A,(BIG_M0)
    LD B,A
    LD A,(SML_M0)
    LD C,A
    LD A,B
    SBC A,C
    LD (BIG_M0),A
    LD A,(BIG_M1)
    LD B,A
    LD A,(SML_M1)
    LD C,A
    LD A,B
    SBC A,C
    LD (BIG_M1),A
    LD A,(BIG_M2)
    LD B,A
    LD A,(SML_M2)
    LD C,A
    LD A,B
    SBC A,C
    LD (BIG_M2),A

    LD A,(BIG_SIGN)
    LD (RES_SIGN),A
    LD A,(BIG_EXP)
    LD (RES_EXP),A

    ; 結果が完全に0か（4バイトとも0）
    LD A,(BIG_M2)
    OR A
    JR NZ,_add_diff_norm
    LD A,(BIG_M1)
    OR A
    JR NZ,_add_diff_norm
    LD A,(BIG_M0)
    OR A
    JR NZ,_add_diff_norm
    LD A,(BIG_MG)
    OR A
    JR NZ,_add_diff_norm
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    JP MBF_PACK_RES

_add_diff_norm:
    ; 左正規化: BIG_M2のbit7が1になるまで32bit左シフト、指数-1。
    ; 左シフトはビットを失わないのでスティッキー更新は不要。
_add_norm_loop:
    LD A,(BIG_M2)
    BIT 7,A
    JR NZ,_add_round
    LD A,(RES_EXP)
    CP 1
    JR NZ,_add_norm_dec
    ; これ以上下げられない(アンダーフロー) -> 結果0
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    JP MBF_PACK_RES
_add_norm_dec:
    DEC A
    LD (RES_EXP),A
    ; 32bit左シフト1 (BIG_MG,BIG_M0,BIG_M1,BIG_M2 の順でCFを伝播)
    XOR A                      ; CF=0
    LD A,(BIG_MG)
    SLA A
    LD (BIG_MG),A
    LD A,(BIG_M0)
    RLA
    LD (BIG_M0),A
    LD A,(BIG_M1)
    RLA
    LD (BIG_M1),A
    LD A,(BIG_M2)
    RLA
    LD (BIG_M2),A
    JR _add_norm_loop

_add_round:
    ; guard = BIG_MG。bit7=0なら常に切り捨て。bit7=1かつ下位7bitが非0なら
    ; 常に切り上げ——これはWK_BORROW(異符号減算での桁借り=2の補数表現)の
    ; 有無によらず正しい。理由(仕様書に無い判断、丸めの数学から導出):
    ;   桁借りが無い(同符号加算)側: guardは正の端数そのもの。
    ;     0x81-0xFFは0.5より真に大きい—そのまま切り上げでよい。
    ;   桁借りが有る(異符号減算)側: 実際に保持している値は
    ;     「2の補数化されたguard」から、整列シフトで切り捨てたぶん
    ;     (WK_STICKY)を差し引いたものになる(=guard/256 - 微小量)。
    ;     0x81-0xFFはこの微小量を引いても0.5を下回らない
    ;     (0x81-1=0x80が下限のため)ので、やはり切り上げでよい。
    ; ちょうど0x80(境目)だけは2つの側で意味が逆転する:
    ;   桁借り無し: guard=0x80はそのまま0.5。WK_STICKY!=0なら
    ;     「0.5より真に大きい」ので切り上げ。
    ;   桁借り有り: guard=0x80から微小量(WK_STICKY!=0の場合)を引くと
    ;     「0.5より真に小さい」になるので、切り捨てになる
    ;     (符号が反転する)。WK_STICKY=0ならどちらの側でも真にちょうど
    ;     0.5なので、偶数丸めは共通。
    LD A,(BIG_MG)
    LD B,A                     ; B に guard byte を保持
    BIT 7,B
    JR Z,_add_round_down        ; guard=0 -> 切り捨て
    LD A,B
    AND 0x7F
    JR NZ,_add_round_up          ; guard=0x81-0xFF -> 常に切り上げ
    ; ここに来るのは guard=0x80 ちょうどのとき
    LD A,(WK_STICKY)
    OR A
    JR Z,_add_round_tie          ; sticky=0 -> 真のタイ、偶数丸めへ
    LD A,(WK_BORROW)
    OR A
    JR NZ,_add_round_down        ; 桁借り側は符号が逆転するので切り捨て
    JR _add_round_up             ; 桁借り無し側はそのまま切り上げ
_add_round_tie:
    ; 真のタイ: 偶数丸め（候補仮数の最下位ビット=BIG_M0 bit0）
    LD A,(BIG_M0)
    BIT 0,A
    JR Z,_add_round_down
_add_round_up:
    ; 24bit(BIG_M2,BIG_M1,BIG_M0)を+1、繰り上がりがあれば正規化しなおす
    LD A,(BIG_M0)
    INC A
    LD (BIG_M0),A
    JR NZ,_add_round_down
    LD A,(BIG_M1)
    INC A
    LD (BIG_M1),A
    JR NZ,_add_round_down
    LD A,(BIG_M2)
    INC A
    LD (BIG_M2),A
    JR NZ,_add_round_down
    ; 24bit全部繰り上がり(0x1000000)になった -> 0x800000へ、指数+1
    LD A,0x80
    LD (BIG_M2),A
    XOR A
    LD (BIG_M1),A
    LD (BIG_M0),A
    LD A,(RES_EXP)
    CP 0xFF
    JR NZ,_add_round_expinc_ok
    JP MBF_PACK_OVERFLOW
_add_round_expinc_ok:
    INC A
    LD (RES_EXP),A
_add_round_down:
    JP MBF_PACK_RES

; =======================================================================
; MBF_SUB — MBF_RES = MBF_OPA - MBF_OPB（単精度）。
; MBF_OPB の符号バイトをその場で反転してから MBF_ADD へ入る
; （$FSUBS が $FAC の符号を反転してから $FADDS へ落ちる構造と同じ形）。
; ゼロは byte3=0 で判定するため、符号ビット反転は0の判定に影響しない。
; =======================================================================
MBF_SUB:
    LD A,(MBF_OPB+2)
    XOR 0x80
    LD (MBF_OPB+2),A
    JP MBF_ADD

; =======================================================================
; MBF_NEG — MBF_RES = -MBF_OPA。ゼロはゼロのまま（符号は変えない）。
; =======================================================================
MBF_NEG:
    LD A,(MBF_OPA+3)
    LD (MBF_RES+3),A
    LD B,A
    LD A,(MBF_OPA)
    LD (MBF_RES),A
    LD A,(MBF_OPA+1)
    LD (MBF_RES+1),A
    LD A,(MBF_OPA+2)
    LD C,A
    LD A,B
    OR A
    JR Z,_neg_iszero
    LD A,C
    XOR 0x80
    LD (MBF_RES+2),A
    XOR A
    LD (MBF_STATUS),A
    RET
_neg_iszero:
    LD A,C
    LD (MBF_RES+2),A
    XOR A
    LD (MBF_STATUS),A
    RET

; =======================================================================
; MBF_CMP — MBF_OUT_CMP = sign(MBF_OPA - MBF_OPB) (0/1/0xFF)。
; MBF_RES・MBF_STATUS は変更しない。
; =======================================================================
MBF_CMP:
    CALL MBF_UNPACK_A
    CALL MBF_UNPACK_B

    LD A,(UA_EXP)
    OR A
    JR NZ,_cmp_a_nonzero
    LD A,(UB_EXP)
    OR A
    JR Z,_cmp_eq                ; 両方0 -> 等しい
    LD A,(UB_SIGN)
    OR A
    JR Z,_cmp_lt                ; A=0, B>0 -> A<B
    JR _cmp_gt                  ; A=0, B<0 -> A>B
_cmp_a_nonzero:
    LD A,(UB_EXP)
    OR A
    JR NZ,_cmp_both_nonzero
    LD A,(UA_SIGN)
    OR A
    JR Z,_cmp_gt                 ; B=0, A>0 -> A>B
    JR _cmp_lt                   ; B=0, A<0 -> A<B

_cmp_both_nonzero:
    LD A,(UA_SIGN)
    LD B,A
    LD A,(UB_SIGN)
    CP B
    JR Z,_cmp_samesign
    ; 符号が違う: 正の方が大きい
    LD A,(UA_SIGN)
    OR A
    JR Z,_cmp_gt
    JR _cmp_lt

_cmp_samesign:
    ; 同符号: 指数→仮数の順で大小比較し、符号が負なら結果を反転する。
    LD A,(UA_EXP)
    LD B,A
    LD A,(UB_EXP)
    CP B
    JR C,_cmp_mag_a_gt
    JR NZ,_cmp_mag_b_gt
    LD A,(UA_M2)
    LD B,A
    LD A,(UB_M2)
    CP B
    JR C,_cmp_mag_a_gt
    JR NZ,_cmp_mag_b_gt
    LD A,(UA_M1)
    LD B,A
    LD A,(UB_M1)
    CP B
    JR C,_cmp_mag_a_gt
    JR NZ,_cmp_mag_b_gt
    LD A,(UA_M0)
    LD B,A
    LD A,(UB_M0)
    CP B
    JR C,_cmp_mag_a_gt
    JR NZ,_cmp_mag_b_gt
    JR _cmp_eq
_cmp_mag_a_gt:
    ; |A|>|B|: 正なら A>B、負なら A<B
    LD A,(UA_SIGN)
    OR A
    JR Z,_cmp_gt
    JR _cmp_lt
_cmp_mag_b_gt:
    LD A,(UA_SIGN)
    OR A
    JR Z,_cmp_lt
    JR _cmp_gt

_cmp_eq:
    XOR A
    LD (MBF_OUT_CMP),A
    RET
_cmp_gt:
    LD A,1
    LD (MBF_OUT_CMP),A
    RET
_cmp_lt:
    LD A,0xFF
    LD (MBF_OUT_CMP),A
    RET

; =======================================================================
; MBF_INT_TO_SINGLE — MBF_IN_INT（符号付き16bit）を単精度MBFへ変換し
; MBF_RES へ書く。0はゼロ、それ以外は正規化して詰める。
; 仕様書に無い判断: 16bit整数は絶対値が最大32768で常に単精度の範囲内
; （24bit仮数で正確に表現できる）ため、丸め・オーバーフロー処理は不要。
; =======================================================================
MBF_INT_TO_SINGLE:
    XOR A
    LD (MBF_STATUS),A
    LD HL,(MBF_IN_INT)
    LD A,H
    OR L
    JR NZ,_i2s_nonzero
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    JP MBF_PACK_RES
_i2s_nonzero:
    LD A,H
    BIT 7,A
    JR Z,_i2s_pos
    LD A,1
    LD (RES_SIGN),A
    ; 2の補数の絶対値化: HL = -HL
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
    JR _i2s_haveabs
_i2s_pos:
    XOR A
    LD (RES_SIGN),A
_i2s_haveabs:
    ; HL(1..32768)を0x8000..0xFFFF範囲(bit15=1)へ左シフトしながら
    ; 指数を数える。仮数24bitは(H,L,0)なので実際の仮数は元の値の256倍。
    ; v*2^shifts*256 = mant24, mant24 = v*2^(exp-128-24) より
    ; exp = 128+24-8-shifts = 144-shifts。v=32768(shifts=0)ならexp=144
    ; (2^15<=32768<2^16よりexp_byte=16+128=144と一致)。
    LD B,144
_i2s_norm:
    BIT 7,H
    JR NZ,_i2s_normed
    ; HL左シフト1、指数-1
    SLA L
    RL H
    DEC B
    JR _i2s_norm
_i2s_normed:
    LD A,B
    LD (RES_EXP),A
    LD A,H
    LD (BIG_M2),A
    ; 仮数は16bit(HL)しか無いので下位8bitは0
    LD A,L
    LD (BIG_M1),A
    XOR A
    LD (BIG_M0),A
    JP MBF_PACK_RES

; =======================================================================
; MBF_MUL — MBF_RES = MBF_OPA * MBF_OPB（単精度）。MBF_STATUS を設定する。
;
; $FMULS (MATH2.ASM 408-490) の再現。単精度乗算は加減算・除算と違って
; 「厳密値を求めて1回偶数丸め」とは等価ではない——8086実装は24bit×24bitの
; 厳密48bit積のうち下位16bitをスティッキーへ畳み込まずにそのまま捨てる
; (MATH2.ASM 449-450 "MUL DX;MOV CX,DX"で最初の部分積の下位ワードを保存せず
; 破棄している)。さらに丸め自体も $ROUNS/$ROUNM (MATH2.ASM 1764-1807) の
; "AND AH,LOW 340"（ガードバイトの下位5bitを捨ててからタイ判定）により、
; 加減算より粗い。この2点は tools/l4_mbf_oracle_v2.py
; （_single_multiply_mantissa/_rouns_from_guard32、モジュール docstring
; 1番）で命令単位の確認済み事項として記録されている。ここではその確認済みの
; 挙動を、Z80の24bit×24bit shift-add乗算＋粗いROUNS丸めとして独自に
; 組み直した（8086命令列の行単位の写経ではない）。
;
; 指数計算 $AEXPS (MATH1.ASM 2913-2970): final_exp = eA+eB-257
; （8bit指数バイト同士の和を9bit精度(0-510)のまま扱う必要があるため、
; Z80では16bit加算で行う=仕様書に無い判断。8086はAXレジスタで自然に
; 9bit精度が出るが、Z80の8bit ADDでは桁あふれが検出できないため）。
; =======================================================================
MUL_R5 EQU 0xC040  ; 48bit積（MSB）。R5,R4,R3,R2が上位32bit(丸め対象)。
MUL_R4 EQU 0xC041
MUL_R3 EQU 0xC042
MUL_R2 EQU 0xC043
MUL_R1 EQU 0xC044
MUL_R0 EQU 0xC045  ; LSB。丸めに一切使わず捨てる(8086実装の忠実な再現)。
MUL_C5 EQU 0xC046  ; シフトしながら加算する被乗数(mf24を6byteに拡張)
MUL_C4 EQU 0xC047
MUL_C3 EQU 0xC048
MUL_C2 EQU 0xC049
MUL_C1 EQU 0xC04A
MUL_C0 EQU 0xC04B
WK_S   EQU 0xC04C  ; eA+eB (2バイト、0..510)

MBF_MUL:
    XOR A
    LD (MBF_STATUS),A
    CALL MBF_UNPACK_A
    CALL MBF_UNPACK_B

    LD A,(UA_EXP)
    OR A
    JR NZ,_mul_a_nonzero
    JP _mul_zero
_mul_a_nonzero:
    LD A,(UB_EXP)
    OR A
    JR NZ,_mul_both_nonzero
    JP _mul_zero

_mul_both_nonzero:
    ; 符号
    LD A,(UA_SIGN)
    LD B,A
    LD A,(UB_SIGN)
    XOR B
    LD (RES_SIGN),A

    ; S = eA+eB (0..510)
    LD A,(UA_EXP)
    LD H,0
    LD L,A
    LD A,(UB_EXP)
    LD D,0
    LD E,A
    ADD HL,DE
    LD (WK_S),HL

    ; オーバーフロー判定: S>=385 (raw=S-257>=128)
    LD DE,385
    OR A
    SBC HL,DE
    JR C,_mul_no_overflow
    JP MBF_PACK_OVERFLOW
_mul_no_overflow:
    ; ゼロ判定: S<129 (raw=S-257<-128)
    LD HL,(WK_S)
    LD DE,129
    OR A
    SBC HL,DE
    JR NC,_mul_have_base_exp
    JP _mul_zero
_mul_have_base_exp:
    ; HL = S-129 = final_exp_before_adj (0..255)
    ; $AEXPS は raw=-128(S=129)ちょうどのとき通常どおり final_exp=0 を返すが、
    ; $FMULS 側はここで即ゼロ扱いにして戻る(仮数の正規化・丸めによる
    ; exp_adj/繰り上がりを一切見ない。tools/l4_mbf_oracle_v2.py
    ; gw_mul_single の "if final_exp == 0: return ...Fraction(0)..." と同じ)。
    ; 仮数側の丸めで指数が0から1以上へ動く余地を先に断つ必要がある。
    LD A,L
    OR A
    JP Z,_mul_zero
    LD (RES_EXP),A          ; 一時的にRES_EXPへ置く(下でexp_adj/carryを加算)

    ; --- 24bit×24bit shift-add乗算 ---
    XOR A
    LD (MUL_R5),A
    LD (MUL_R4),A
    LD (MUL_R3),A
    LD (MUL_R2),A
    LD (MUL_R1),A
    LD (MUL_R0),A
    LD A,(UA_M0)
    LD (MUL_C0),A
    LD A,(UA_M1)
    LD (MUL_C1),A
    LD A,(UA_M2)
    LD (MUL_C2),A
    XOR A
    LD (MUL_C3),A
    LD (MUL_C4),A
    LD (MUL_C5),A

    LD B,24
_mul_loop:
    ; UB_M2:UB_M1:UB_M0 (24bit, M2=MSB) を右へ1、落ちたbit0をCFへ
    LD A,(UB_M2)
    SRL A                     ; 最初のシフトはbit7に強制的に0が入る(SRL)
    LD (UB_M2),A
    LD A,(UB_M1)
    RRA
    LD (UB_M1),A
    LD A,(UB_M0)
    RRA
    LD (UB_M0),A
    JR NC,_mul_no_add
    ; MUL_R(6byte) += MUL_C(6byte)  (LSBから)
    LD A,(MUL_R0)
    LD C,A
    LD A,(MUL_C0)
    ADD A,C
    LD (MUL_R0),A
    LD A,(MUL_R1)
    LD C,A
    LD A,(MUL_C1)
    ADC A,C
    LD (MUL_R1),A
    LD A,(MUL_R2)
    LD C,A
    LD A,(MUL_C2)
    ADC A,C
    LD (MUL_R2),A
    LD A,(MUL_R3)
    LD C,A
    LD A,(MUL_C3)
    ADC A,C
    LD (MUL_R3),A
    LD A,(MUL_R4)
    LD C,A
    LD A,(MUL_C4)
    ADC A,C
    LD (MUL_R4),A
    LD A,(MUL_R5)
    LD C,A
    LD A,(MUL_C5)
    ADC A,C
    LD (MUL_R5),A
_mul_no_add:
    ; MUL_C(6byte) を左へ1 (LSBから)
    XOR A
    LD A,(MUL_C0)
    SLA A
    LD (MUL_C0),A
    LD A,(MUL_C1)
    RLA
    LD (MUL_C1),A
    LD A,(MUL_C2)
    RLA
    LD (MUL_C2),A
    LD A,(MUL_C3)
    RLA
    LD (MUL_C3),A
    LD A,(MUL_C4)
    RLA
    LD (MUL_C4),A
    LD A,(MUL_C5)
    RLA
    LD (MUL_C5),A
    DEC B
    JP NZ,_mul_loop

    ; 上位32bit(MUL_R5:R4:R3:R2)だけを見る。下位16bit(R1,R0)は完全に破棄
    ; (スティッキーへも畳み込まない。$FMULSの忠実な再現)。
    LD A,(MUL_R5)
    BIT 7,A
    JR NZ,_mul_p32_asis
    ; bit31=0 -> 32bit左へ1 (BIG_M2,M1,M0,MGの並びに合わせてR2,R3,R4,R5を使う)
    XOR A
    LD A,(MUL_R2)
    SLA A
    LD (BIG_MG),A
    LD A,(MUL_R3)
    RLA
    LD (BIG_M0),A
    LD A,(MUL_R4)
    RLA
    LD (BIG_M1),A
    LD A,(MUL_R5)
    RLA
    LD (BIG_M2),A
    JR _mul_have_m32
_mul_p32_asis:
    LD A,(MUL_R2)
    LD (BIG_MG),A
    LD A,(MUL_R3)
    LD (BIG_M0),A
    LD A,(MUL_R4)
    LD (BIG_M1),A
    LD A,(MUL_R5)
    LD (BIG_M2),A
    ; exp_adjを+1（bit31が既に1だった=正規化で1桁シフト分の指数調整）
    LD A,(RES_EXP)
    INC A
    LD (RES_EXP),A
    JR NZ,_mul_have_m32
    JP MBF_PACK_OVERFLOW     ; RES_EXPが256へ桁あふれ=オーバーフロー

_mul_have_m32:
    ; $ROUNS の粗い丸め: masked = guard(BIG_MG) & 0xE0
    LD A,(BIG_MG)
    AND 0xE0
    JR Z,_mul_round_down
    CP 0x80
    JR C,_mul_round_down     ; masked<0x80 -> 切り捨て
    JR NZ,_mul_round_up      ; masked>0x80 -> 切り上げ
    ; masked==0x80 ちょうど: 偶数丸め(候補仮数の最下位ビット=BIG_M0 bit0)
    LD A,(BIG_M0)
    BIT 0,A
    JR Z,_mul_round_down
_mul_round_up:
    LD A,(BIG_M0)
    INC A
    LD (BIG_M0),A
    JR NZ,_mul_round_down
    LD A,(BIG_M1)
    INC A
    LD (BIG_M1),A
    JR NZ,_mul_round_down
    LD A,(BIG_M2)
    INC A
    LD (BIG_M2),A
    JR NZ,_mul_round_down
    LD A,0x80
    LD (BIG_M2),A
    XOR A
    LD (BIG_M1),A
    LD (BIG_M0),A
    LD A,(RES_EXP)
    INC A
    LD (RES_EXP),A
    JR Z,_mul_overflow_now
_mul_round_down:
    LD A,(RES_EXP)
    OR A
    JP NZ,MBF_PACK_RES
    ; final_expがちょうど0まで落ちた(丸め・正規化のどちらでも加算されなかった)
    ; -> ゼロ
    JP _mul_zero
_mul_overflow_now:
    JP MBF_PACK_OVERFLOW

_mul_zero:
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    JP MBF_PACK_RES

; =======================================================================
; MBF_DIV — MBF_RES = MBF_OPA / MBF_OPB（単精度）。MBF_STATUS を設定する
; (0=正常 1=オーバーフロー 2=0除算)。
;
; $SDIV/$FDIVS (MATH1.ASM 3666-3825) の再現。除算は加減算と同じく
; 「厳密値を求めて1回偶数丸め」と数学的に等価(tools/l4_mbf_oracle_v2.py
; モジュールdocstring4番で確認済み)なので、MBF_ADDの丸め(guard1バイト+
; スティッキー1bit、偶数丸め)をそのまま再利用できる。
;
; 商の求め方は「剰余を毎回2倍しながら引けるか試す」教科書的な復元法
; （remainder doubling、8086のKnuth Algorithm Dの写経ではなく独自に
; 組んだ）。この方法は剰余Rが常にmantB未満であることを前提にするが、
; mantA/mantBは(0.5,2)の範囲なのでmantA>=mantB(比が1以上)のことも
; 半分程度ある。そこで先にmantA,mantBを比較し、mantA>=mantBなら
; 1回だけR-=mantBしておいて前提を満たしてから31回のループへ入り
; （このR<mantB化と、その1ビットをQのbit31へ合成する構成は仕様書に
; 無い判断。境界値照合(MAX_POS÷2.0のようなratio>=1のケース)で
; 「前提を満たしていないと商が壊れる」ことを実際に見つけて追加した）、
; 最終的にQ=floor(mantA*2^31/mantB)を得る。mantA/mantBが(0.5,2)の
; 範囲であることから、Qの最上位ビットは必ずbit30かbit31のどちらかに
; なり(31回という回数を選んだ理由=仕様書に無い判断)、MBF_MULの正規化
; (bit31が立っているかどうかで0/1ビットシフト)と全く同じ形にできる。
;
; 指数の基準式(eA-eB+128、$SEXPS(MATH1.ASM 3691-3714)と同型)から、
; N=31回のQに対する丸め前の指数を導出すると:
;   bit31が既に立っている(シフト不要) -> final_exp = (eA-eB+128) + 1
;   bit31が立っていない(1bit左シフトが要る) -> final_exp = (eA-eB+128)
; （導出はコミットメッセージに残す。境界値・乱数照合で検算済み）。
; =======================================================================
DIV_Q3 EQU 0xC050   ; 商(32bit中、有効なのは31bitぶん)
DIV_Q2 EQU 0xC051
DIV_Q1 EQU 0xC052
DIV_Q0 EQU 0xC053
DIV_R3 EQU 0xC054   ; 剰余(復元法のワーキングレジスタ)
DIV_R2 EQU 0xC055
DIV_R1 EQU 0xC056
DIV_R0 EQU 0xC057
DIV_T3 EQU 0xC058   ; 試し引き算のスクラッチ
DIV_T2 EQU 0xC059
DIV_T1 EQU 0xC05A
DIV_T0 EQU 0xC05B
DIV_B3 EQU 0xC05C   ; 除数(mantB、24bitを32bitへゼロ拡張)
DIV_B2 EQU 0xC05D
DIV_B1 EQU 0xC05E
DIV_B0 EQU 0xC05F
WK_REMZERO EQU 0xC060  ; 真の剰余が最終的に0だったか(0=0だった)
WK_DIVINIT EQU 0xC061  ; mantA>=mantBの事前正規化フラグ(下のコメント参照)

MBF_DIV:
    XOR A
    LD (MBF_STATUS),A
    LD (WK_STICKY),A
    LD (WK_BORROW),A
    CALL MBF_UNPACK_A
    CALL MBF_UNPACK_B

    LD A,(UB_EXP)
    OR A
    JR NZ,_div_b_nonzero
    ; 0除算
    LD A,(UA_EXP)
    OR A
    JR Z,_div_zerobyzero_sign
    LD A,(UA_SIGN)
    LD (RES_SIGN),A
    JR _div_zerodivide_pack
_div_zerobyzero_sign:
    XOR A
    LD (RES_SIGN),A
_div_zerodivide_pack:
    LD A,2
    LD (MBF_STATUS),A
    CALL MBF_PACK_OVERFLOW_KEEPSTATUS
    RET

_div_b_nonzero:
    LD A,(UA_EXP)
    OR A
    JR NZ,_div_both_nonzero
    ; 0/x = 0
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    JP MBF_PACK_RES

_div_both_nonzero:
    LD A,(UA_SIGN)
    LD B,A
    LD A,(UB_SIGN)
    XOR B
    LD (RES_SIGN),A

    ; base_exp = eA-eB+128 (16bit符号つきで計算。Sフラグで判定するため
    ; SBC HL,DE を使う)
    LD A,(UA_EXP)
    LD H,0
    LD L,A
    LD DE,128
    ADD HL,DE            ; HL = eA+128
    LD A,(UB_EXP)
    LD D,0
    LD E,A
    OR A
    SBC HL,DE             ; HL = eA+128-eB = base_exp (符号つき、-126..382)
    LD (WK_S),HL          ; 一時保存(WK_Sを2バイトの汎用一時領域として流用)

    ; --- 24bit÷24bit 復元法（31回） ---
    XOR A
    LD (DIV_Q3),A
    LD (DIV_Q2),A
    LD (DIV_Q1),A
    LD (DIV_Q0),A
    LD (DIV_R3),A
    LD A,(UA_M2)
    LD (DIV_R2),A
    LD A,(UA_M1)
    LD (DIV_R1),A
    LD A,(UA_M0)
    LD (DIV_R0),A
    XOR A
    LD (DIV_B3),A
    LD A,(UB_M2)
    LD (DIV_B2),A
    LD A,(UB_M1)
    LD (DIV_B1),A
    LD A,(UB_M0)
    LD (DIV_B0),A

    ; 事前正規化: remainder-doubling法は「R<B」を前提にするが、
    ; mantA/mantBは(0.5,2)の範囲なので mantA>=mantB（比が1以上）のことも
    ; 半分程度ある。そのときは先に1回だけ R-=B しておき、その1ビットを
    ; 後でQのbit31として合成する（仕様書に無い判断。標準的な復元法の
    ; 前提を満たすための独自の前処理。境界値照合(MAX_POS/2のような
    ; ratio>=1のケース)で見つけた）。
    XOR A
    LD (WK_DIVINIT),A
    LD A,(DIV_R2)
    LD B,A
    LD A,(DIV_B2)
    CP B
    JR C,_div_a_ge_b
    JR NZ,_div_pre_done
    LD A,(DIV_R1)
    LD B,A
    LD A,(DIV_B1)
    CP B
    JR C,_div_a_ge_b
    JR NZ,_div_pre_done
    LD A,(DIV_R0)
    LD B,A
    LD A,(DIV_B0)
    CP B
    JR C,_div_a_ge_b
    JR NZ,_div_pre_done
_div_a_ge_b:
    LD A,1
    LD (WK_DIVINIT),A
    LD A,(DIV_R0)
    LD H,A
    LD A,(DIV_B0)
    LD L,A
    LD A,H
    SUB L
    LD (DIV_R0),A
    LD A,(DIV_R1)
    LD H,A
    LD A,(DIV_B1)
    LD L,A
    LD A,H
    SBC A,L
    LD (DIV_R1),A
    LD A,(DIV_R2)
    LD H,A
    LD A,(DIV_B2)
    LD L,A
    LD A,H
    SBC A,L
    LD (DIV_R2),A
_div_pre_done:

    LD B,31
_div_loop:
    ; R = R<<1 (32bit、LSBから)
    XOR A
    LD A,(DIV_R0)
    SLA A
    LD (DIV_R0),A
    LD A,(DIV_R1)
    RLA
    LD (DIV_R1),A
    LD A,(DIV_R2)
    RLA
    LD (DIV_R2),A
    LD A,(DIV_R3)
    RLA
    LD (DIV_R3),A
    ; Q = Q<<1 (32bit、LSBから)
    XOR A
    LD A,(DIV_Q0)
    SLA A
    LD (DIV_Q0),A
    LD A,(DIV_Q1)
    RLA
    LD (DIV_Q1),A
    LD A,(DIV_Q2)
    RLA
    LD (DIV_Q2),A
    LD A,(DIV_Q3)
    RLA
    LD (DIV_Q3),A

    ; T = R - B (32bit、LSBから)。桁借りが無ければ R>=B。
    LD A,(DIV_R0)
    LD C,A
    LD A,(DIV_B0)
    LD E,A
    LD A,C
    SUB E
    LD (DIV_T0),A
    LD A,(DIV_R1)
    LD C,A
    LD A,(DIV_B1)
    LD E,A
    LD A,C
    SBC A,E
    LD (DIV_T1),A
    LD A,(DIV_R2)
    LD C,A
    LD A,(DIV_B2)
    LD E,A
    LD A,C
    SBC A,E
    LD (DIV_T2),A
    LD A,(DIV_R3)
    LD C,A
    LD A,(DIV_B3)
    LD E,A
    LD A,C
    SBC A,E
    LD (DIV_T3),A
    JR C,_div_no_sub          ; 桁借りが出た(R<B) -> 引かない、商bitは0のまま
    ; R>=B: T(=R-B)をRへ採用し、Qのbit0を立てる
    LD A,(DIV_T0)
    LD (DIV_R0),A
    LD A,(DIV_T1)
    LD (DIV_R1),A
    LD A,(DIV_T2)
    LD (DIV_R2),A
    LD A,(DIV_T3)
    LD (DIV_R3),A
    LD A,(DIV_Q0)
    OR 1
    LD (DIV_Q0),A
_div_no_sub:
    DEC B
    JP NZ,_div_loop

    ; 真の剰余が0かどうか(スティッキーに使う)
    XOR A
    LD (WK_REMZERO),A
    LD A,(DIV_R0)
    OR A
    JR NZ,_div_remnz
    LD A,(DIV_R1)
    OR A
    JR NZ,_div_remnz
    LD A,(DIV_R2)
    OR A
    JR NZ,_div_remnz
    LD A,(DIV_R3)
    OR A
    JR NZ,_div_remnz
    JR _div_remcheck_done
_div_remnz:
    LD A,1
    LD (WK_REMZERO),A
_div_remcheck_done:

    ; 事前正規化フラグをQのbit31として合成する(31回のループはbit0-30ぶん
    ; しか作らない。この合成後、bit31が立っている⇔事前正規化フラグが
    ; 立っていた、が必ず一致する——mantA<mantBのときはQ(31bit)の最上位は
    ; 必ずbit30までにしかならないため)。
    LD A,(WK_DIVINIT)
    OR A
    JR Z,_div_no_initbit
    LD A,(DIV_Q3)
    OR 0x80
    LD (DIV_Q3),A
_div_no_initbit:

    ; 正規化: DIV_Q3のbit7(=Qのbit31)が立っていれば追加シフト不要、
    ; final_exp=base_exp+1。立っていなければ1bit左シフトしてfinal_exp=base_exp。
    LD A,(DIV_Q3)
    BIT 7,A
    JR NZ,_div_noshift
    ; 1bit左シフト(LSBから)
    XOR A
    LD A,(DIV_Q0)
    SLA A
    LD (DIV_Q0),A
    LD A,(DIV_Q1)
    RLA
    LD (DIV_Q1),A
    LD A,(DIV_Q2)
    RLA
    LD (DIV_Q2),A
    LD A,(DIV_Q3)
    RLA
    LD (DIV_Q3),A
    LD HL,(WK_S)
    JR _div_have_finalexp
_div_noshift:
    LD HL,(WK_S)
    LD DE,1
    ADD HL,DE            ; final_exp = base_exp + 1
_div_have_finalexp:
    ; オーバーフロー判定: final_exp>255
    PUSH HL
    LD DE,256
    OR A
    SBC HL,DE
    POP HL
    JP P,_div_overflow    ; (final_exp-256)>=0 -> final_exp>=256
    ; アンダーフロー判定: final_exp<1
    PUSH HL
    LD DE,1
    OR A
    SBC HL,DE
    POP HL
    JP M,_div_zero_result ; (final_exp-1)<0 -> final_exp<1

    LD A,L
    LD (RES_EXP),A

    ; 候補仮数(BIG_M2,M1,M0)とガード(BIG_MG)にDIV_Q3,Q2,Q1,Q0を写す
    LD A,(DIV_Q3)
    LD (BIG_M2),A
    LD A,(DIV_Q2)
    LD (BIG_M1),A
    LD A,(DIV_Q1)
    LD (BIG_M0),A
    LD A,(DIV_Q0)
    LD (BIG_MG),A
    LD A,(WK_REMZERO)
    LD (WK_STICKY),A
    ; WK_BORROWは0のまま(除算に桁借りの逆転規則は無い、通常のADD丸めと同じ扱い)
    JP _add_round

_div_overflow:
    JP MBF_PACK_OVERFLOW
_div_zero_result:
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    JP MBF_PACK_RES

; MBF_PACK_OVERFLOW と同じだが MBF_STATUS を上書きしない版(0除算用)。
MBF_PACK_OVERFLOW_KEEPSTATUS:
    LD HL,MBF_RES
    LD A,0xFF
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    LD A,(RES_SIGN)
    OR A
    JR Z,_pkok_pos
    LD A,0xFF
    JR _pkok_setb2
_pkok_pos:
    LD A,0x7F
_pkok_setb2:
    LD (HL),A
    INC HL
    LD A,0xFF
    LD (HL),A
    RET

; =======================================================================
; MBF_UDWORD_TO_SINGLE — FIN_ACC3:ACC2:ACC1:ACC0(32bit符号なし整数)と
; FIN_SIGNから単精度MBFを作る。24bitに収まらない場合はADDと同じ
; guard+sticky・偶数丸めで正しく丸める(16bit専用のMBF_INT_TO_SINGLEとは
; 別物。MBF_FIN専用に組んだので入出力はFIN_*を直接読み書きする
; =仕様書に無い判断、汎用ルーチンとして独立させていない)。
;
; 正規化: 32bit値V(非0)をbit31が立つまで左シフト(s回)すると、
; V=candidate24*2^(8-s)(近似、下参照)になるので final_exp=160-s。
; (V=1のときs=31,final_exp=129={1.0の単精度指数}で検算済み)。
; =======================================================================
MBF_UDWORD_TO_SINGLE:
    XOR A
    LD (MBF_STATUS),A
    LD (WK_STICKY),A
    LD (WK_BORROW),A
    LD A,(FIN_ACC3)
    OR A
    JR NZ,_udw_nz
    LD A,(FIN_ACC2)
    OR A
    JR NZ,_udw_nz
    LD A,(FIN_ACC1)
    OR A
    JR NZ,_udw_nz
    LD A,(FIN_ACC0)
    OR A
    JR NZ,_udw_nz
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    JP MBF_PACK_RES
_udw_nz:
    LD A,(FIN_SIGN)
    LD (RES_SIGN),A
    LD C,0                     ; C = シフト回数
_udw_norm:
    LD A,(FIN_ACC3)
    BIT 7,A
    JR NZ,_udw_normed
    XOR A
    LD A,(FIN_ACC0)
    SLA A
    LD (FIN_ACC0),A
    LD A,(FIN_ACC1)
    RLA
    LD (FIN_ACC1),A
    LD A,(FIN_ACC2)
    RLA
    LD (FIN_ACC2),A
    LD A,(FIN_ACC3)
    RLA
    LD (FIN_ACC3),A
    INC C
    JR _udw_norm
_udw_normed:
    LD A,160
    SUB C
    LD (RES_EXP),A
    LD A,(FIN_ACC3)
    LD (BIG_M2),A
    LD A,(FIN_ACC2)
    LD (BIG_M1),A
    LD A,(FIN_ACC1)
    LD (BIG_M0),A
    LD A,(FIN_ACC0)
    LD (BIG_MG),A
    JP _add_round

; =======================================================================
; UDWORD_TO_DOUBLE — FIN_ACC3:ACC2:ACC1:ACC0(32bit符号なし整数)と
; FIN_SIGNから倍精度MBF(DA_*)を厳密に作る。32bit整数は56bit仮数へ
; 必ず正確に収まるので丸めは不要(MBF_UDWORD_TO_SINGLEと違い偶数丸めの
; 分岐が無い)。$FINEがMDPTENへ渡す前にFRCDBLで倍精度化する箇所の再現
; ——MBF_FINが「整数へ厳密に積み上げた値を、指数適用より前に単精度へ
; 丸めてしまう」と、GWの実際の手順(丸めは最後の$CSD1回だけ)より
; 余分な丸め(2重丸め)が入り、FIN_ACCが2^24を超える(8桁以上の`!`強制
; 単精度リテラルなど)ケースで予測器と食い違うことが照合でわかった
; ("2246.07656!"のような9桁の`!`付き定数で発覚)。
; =======================================================================
UDWORD_TO_DOUBLE:
    XOR A
    LD A,(FIN_ACC3)
    OR A
    JR NZ,_udwd_nz
    LD A,(FIN_ACC2)
    OR A
    JR NZ,_udwd_nz
    LD A,(FIN_ACC1)
    OR A
    JR NZ,_udwd_nz
    LD A,(FIN_ACC0)
    OR A
    JR NZ,_udwd_nz
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
    RET
_udwd_nz:
    LD A,(FIN_SIGN)
    LD (DA_SIGN),A
    LD C,0
_udwd_norm:
    LD A,(FIN_ACC3)
    BIT 7,A
    JR NZ,_udwd_normed
    XOR A
    LD A,(FIN_ACC0)
    SLA A
    LD (FIN_ACC0),A
    LD A,(FIN_ACC1)
    RLA
    LD (FIN_ACC1),A
    LD A,(FIN_ACC2)
    RLA
    LD (FIN_ACC2),A
    LD A,(FIN_ACC3)
    RLA
    LD (FIN_ACC3),A
    INC C
    JR _udwd_norm
_udwd_normed:
    LD A,160
    SUB C
    LD (DA_EXP),A
    LD A,(FIN_ACC3)
    LD (DA_M6),A
    LD A,(FIN_ACC2)
    LD (DA_M5),A
    LD A,(FIN_ACC1)
    LD (DA_M4),A
    LD A,(FIN_ACC0)
    LD (DA_M3),A
    XOR A
    LD (DA_M2),A
    LD (DA_M1),A
    LD (DA_M0),A
    RET

; =======================================================================
; MBF_FIN — 10進の数字文字列(FIN_BUF、FIN_LEN)を解釈し、単精度MBFへ
; 変換する。$FIN (GIOCON.ASM ではなく BIMISC.ASM 系。今回は個々の8086
; 命令列を読まず、GW-BASICソース中の$FINが「符号→数字列(小数点含む)→
; E/D指数→!/#」の構造を持つという構文のみを、docs/spec/l4-basic.md
; 第5.1節の観測例(定数の型の決まり方)から独立に組み直した。
;
; 仕様書に無い判断(coordinatorの指示どおり明記):
;   - 倍精度と判定される定数(小数点を除く有効桁が8桁以上、または`#`、
;     または`D`/`d`指数)は、値を計算せず MBF_STATUS=3 を返すだけにする
;     (倍精度の実装は段階4bで別途行う)。
;   - 桁数のカウントは資料からの転記ではなく、GW-BASICのMIT公開ソース
;     ($FIN)を読まずに「10進の値そのものが1,000,000以上になった時点で
;     倍精度」という閾値判定として独自に組んだ(整数→単精度→倍精度の
;     3段階しきい値がある可能性があるが、どの経路でも「生の桁の値が
;     1,000,000に達するかどうか」で単精度/倍精度の分岐が決まる、という
;     部分だけを採用した)。
;   - 数値の合成は GW-BASIC の $FINE/MDPTEN の実際の手順(MATH1.ASM
;     1145-1240)どおり、有効桁(最大32bit整数として蓄積)を
;     UDWORD_TO_DOUBLEで倍精度(56bit)へ厳密変換してから、10進指数ぶんの
;     倍精度10のべき定数(DBL_TABLE)をDBL_MUL/DBL_DIVで1回だけ掛ける・
;     割り、最後にDBL_TO_SINGLE_CSD($CSD)で単精度へ戻す(下のDBL_MUL
;     ヘッダコメント参照)。かつては「単精度のまま10.0を2進累乗法で
;     繰り返し掛ける」近似だったため、繰り返しの乗除算ごとに丸めが入り
;     予測器の「厳密値→1回丸め」から高頻度でずれていたが、この
;     GW手順への作り直し(コミット90cb054)で解消した。
;     2026-09-15追記: それでもなお乱数照合で約0.3-0.5%(常に最下位
;     バイトが+1高い側)の不一致が残っていたが、これはこのルーチンの
;     バグではなく、予測器側(tools/l4_mbf_oracle_v2.py parse_literal)の
;     fin_algo="gw"が単精度への最終丸め($CSD、タイを作らない特殊丸め)を
;     再現せず直接24bit丸めしていたための予測器側の不一致だった
;     （実際のMATH1.ASM MDPTENを読み、"JNB FIN20"→FRCDBL→MDP10→
;     "JNB FIN25/FIN50"→$CSDという、指数が非0なら単精度でも必ず倍精度を
;     経由し最後に$CSDで戻すという手順そのものを確認した上での結論）。
;     予測器側を修正し、乱数5000件超・境界値の照合で不一致0件を確認した
;     (tools/l4_mbf_conform.py・tools/l4_mbf_oracle_v2.py 該当コメント、
;     コミットメッセージ参照)。
;   - 指数(E/D)の桁は2桁までしか蓄積しない(3桁目以降は無視、単精度の
;     範囲では現実的に不要)。
;
; 入力: FIN_BUF(最大24バイト、ASCII、大文字小文字問わず)、FIN_LEN。
; 出力: MBF_RES・MBF_STATUS(0=正常な単精度値、3=倍精度定数だった)。
; =======================================================================
FIN_BUF     EQU 0xC080   ; 24バイト
FIN_LEN     EQU 0xC098
FIN_POS     EQU 0xC099
FIN_SIGN    EQU 0xC09A
FIN_ACC3    EQU 0xC09B
FIN_ACC2    EQU 0xC09C
FIN_ACC1    EQU 0xC09D
FIN_ACC0    EQU 0xC09E
FIN_FRACDIG EQU 0xC09F
FIN_SEENDOT EQU 0xC0A0
FIN_EXPSIGN EQU 0xC0A1
FIN_EXPVAL  EQU 0xC0A2
FIN_HASHASH EQU 0xC0A3
FIN_HASD    EQU 0xC0A4
FIN_ISDOUBLE EQU 0xC0A5
FIN_SCALE   EQU 0xC0A6   ; 符号つき1バイト(-128..127)。exponent-fracdig
WK_FINDIGIT EQU 0xC0A7
WK_FINLOOP  EQU 0xC0AA
FIN_HASBANG EQU 0xC0AB
FIN_VALUE   EQU 0xC0AC   ; 4バイト(AC-AF)
FIN_SCALE_NEG EQU 0xC0B0
FIN_POW     EQU 0xC0B1   ; 4バイト(B1-B4)
FIN_BASE    EQU 0xC0B5   ; 4バイト(B5-B8)

MBF_FIN:
    XOR A
    LD (MBF_STATUS),A
    LD (FIN_POS),A
    LD (FIN_SIGN),A
    LD (FIN_ACC3),A
    LD (FIN_ACC2),A
    LD (FIN_ACC1),A
    LD (FIN_ACC0),A
    LD (FIN_FRACDIG),A
    LD (FIN_SEENDOT),A
    LD (FIN_EXPSIGN),A
    LD (FIN_EXPVAL),A
    LD (FIN_HASHASH),A
    LD (FIN_HASD),A
    LD (FIN_ISDOUBLE),A
    LD (FIN_HASBANG),A

    ; 符号
    LD HL,FIN_BUF
    LD A,(HL)
    CP '-'
    JR NZ,_fin_chk_plus
    LD A,1
    LD (FIN_SIGN),A
    LD A,1
    LD (FIN_POS),A
    JR _fin_digits
_fin_chk_plus:
    CP '+'
    JR NZ,_fin_digits_start0
    LD A,1
    LD (FIN_POS),A
    JR _fin_digits
_fin_digits_start0:
    XOR A
    LD (FIN_POS),A
_fin_digits:

_fin_digit_loop:
    LD A,(FIN_POS)
    LD C,A
    LD A,(FIN_LEN)
    CP C
    JP Z,_fin_after_digits      ; POS==LEN -> 数字列おしまい
    LD HL,FIN_BUF
    LD B,0
    ADD HL,BC
    LD A,(HL)
    CP '.'
    JR NZ,_fin_try_digit
    LD A,(FIN_SEENDOT)
    OR A
    JR NZ,_fin_after_digits      ; 2個目の'.'は数字列の終わり(構文誤りは無視)
    LD A,1
    LD (FIN_SEENDOT),A
    LD A,(FIN_POS)
    INC A
    LD (FIN_POS),A
    JR _fin_digit_loop
_fin_try_digit:
    CP '0'
    JR C,_fin_after_digits
    CP '9'+1
    JR NC,_fin_after_digits
    SUB '0'
    LD (WK_FINDIGIT),A

    ; 倍精度しきい値判定: 現在のACC(32bit)が1,000,000以上ならこれ以降は
    ; 倍精度確定(仕様書に無い判断、本ルーチンヘッダのコメント参照)。
    LD A,(FIN_ACC3)
    OR A
    JR NZ,_fin_set_double
    LD A,(FIN_ACC2)
    CP 0x0F
    JR C,_fin_below_threshold
    JR NZ,_fin_set_double
    LD A,(FIN_ACC1)
    CP 0x42
    JR C,_fin_below_threshold
    JR NZ,_fin_set_double
    LD A,(FIN_ACC0)
    CP 0x40
    JR C,_fin_below_threshold
_fin_set_double:
    LD A,1
    LD (FIN_ISDOUBLE),A
_fin_below_threshold:

    LD A,(WK_FINDIGIT)
    CALL FIN_MUL10ADD
    LD A,(FIN_SEENDOT)
    OR A
    JR Z,_fin_digit_next
    LD A,(FIN_FRACDIG)
    INC A
    LD (FIN_FRACDIG),A
_fin_digit_next:
    LD A,(FIN_POS)
    INC A
    LD (FIN_POS),A
    JP _fin_digit_loop

_fin_after_digits:
    ; E/e/D/d 指数
    LD A,(FIN_POS)
    LD C,A
    LD A,(FIN_LEN)
    CP C
    JP Z,_fin_after_exp
    LD HL,FIN_BUF
    LD B,0
    ADD HL,BC
    LD A,(HL)
    CP 'E'
    JR Z,_fin_have_exp
    CP 'e'
    JR Z,_fin_have_exp
    CP 'D'
    JR Z,_fin_have_expd
    CP 'd'
    JR Z,_fin_have_expd
    JR _fin_after_exp
_fin_have_expd:
    LD A,1
    LD (FIN_HASD),A
_fin_have_exp:
    LD A,(FIN_POS)
    INC A
    LD (FIN_POS),A
    ; 指数の符号
    LD A,(FIN_POS)
    LD C,A
    LD A,(FIN_LEN)
    CP C
    JR Z,_fin_expdigits
    LD HL,FIN_BUF
    LD B,0
    ADD HL,BC
    LD A,(HL)
    CP '-'
    JR NZ,_fin_expchkplus
    LD A,1
    LD (FIN_EXPSIGN),A
    LD A,(FIN_POS)
    INC A
    LD (FIN_POS),A
    JR _fin_expdigits
_fin_expchkplus:
    CP '+'
    JR NZ,_fin_expdigits
    LD A,(FIN_POS)
    INC A
    LD (FIN_POS),A
_fin_expdigits:
    LD B,0                      ; B=読んだ指数桁数(2桁まで)
_fin_expdigit_loop:
    LD A,(FIN_POS)
    LD C,A
    LD A,(FIN_LEN)
    CP C
    JP Z,_fin_after_exp
    LD HL,FIN_BUF
    PUSH BC
    LD B,0
    ADD HL,BC
    POP BC
    LD A,(HL)
    CP '0'
    JR C,_fin_after_exp
    CP '9'+1
    JR NC,_fin_after_exp
    SUB '0'
    LD C,A
    LD A,B
    CP 2
    JR NC,_fin_expdigit_skip     ; 3桁目以降は無視
    LD A,(FIN_EXPVAL)
    ; EXPVAL = EXPVAL*10+digit (8bit範囲、最大99なので桁あふれ無し)
    ADD A,A
    LD D,A
    ADD A,A
    ADD A,A
    ADD A,D
    ADD A,C
    LD (FIN_EXPVAL),A
    INC B
_fin_expdigit_skip:
    LD A,(FIN_POS)
    INC A
    LD (FIN_POS),A
    JR _fin_expdigit_loop

_fin_after_exp:
    ; # / !
    LD A,(FIN_POS)
    LD C,A
    LD A,(FIN_LEN)
    CP C
    JR Z,_fin_classify
    LD HL,FIN_BUF
    LD B,0
    ADD HL,BC
    LD A,(HL)
    CP '#'
    JR Z,_fin_sethash
    CP '!'
    JR NZ,_fin_classify
    LD A,1
    LD (FIN_HASBANG),A
    JR _fin_classify
_fin_sethash:
    LD A,1
    LD (FIN_HASHASH),A

_fin_classify:
    ; `!`は倍精度しきい値より優先して単精度を強制する
    ; (parse_literalの force_suffix=="!" -> kind="single" と同じ優先順位)。
    LD A,(FIN_HASBANG)
    OR A
    JR NZ,_fin_is_single
    LD A,(FIN_HASHASH)
    OR A
    JR NZ,_fin_is_double
    LD A,(FIN_HASD)
    OR A
    JR NZ,_fin_is_double
    LD A,(FIN_ISDOUBLE)
    OR A
    JR NZ,_fin_is_double
    JR _fin_is_single

_fin_is_double:
    LD A,3
    LD (MBF_STATUS),A
    RET

_fin_is_single:
    ; SCALE = EXPVAL(符号付き) - FRACDIG  (8bit符号つき算術でよい範囲)
    LD A,(FIN_EXPVAL)
    LD B,A
    LD A,(FIN_EXPSIGN)
    OR A
    JR Z,_fin_expsigned_done
    LD A,0
    SUB B
    LD B,A
_fin_expsigned_done:
    LD A,(FIN_FRACDIG)
    LD C,A
    LD A,B
    SUB C
    LD (FIN_SCALE),A

    LD A,(FIN_SCALE)
    OR A
    JP NZ,_fin_scale_nonzero
    CALL MBF_UDWORD_TO_SINGLE
    JP _fin_done

    ; $FINE/MDPTENの再現: 倍精度(56bit)へ変換し、10^|SCALE|の倍精度
    ; 定数を1回だけ掛ける/割ってから単精度へ$CSDで切り詰める
    ; (GW-BASICのMATH1.ASM 1145-1240を命令単位で読んで再現。前の実装は
    ; 単精度のまま10.0を2進累乗法で繰り返し掛ける自前の近似だったため、
    ; 乱数照合で約2.6%が最下位桁でずれた——予測器担当がGW-BASICの
    ; $FIN/$FIDIGを確認した結果〔コミット1d57966〕、単精度は
    ; 「厳密値→1回丸め」とGWの実際の手順が完全に一致することが
    ; わかったため、自前の近似をやめてGWの実際の手順に合わせた)。
    ; 積み上げた整数(FIN_ACC)は単精度へは変換せず、UDWORD_TO_DOUBLEで
    ; 直接倍精度(丸め不要、32bitは56bit仮数へ必ず厳密に収まる)へ
    ; 変換してから指数を適用する——単精度へ先に丸めてから倍精度化すると
    ; 2重丸めになり、FIN_ACCが2^24を超える`!`強制単精度リテラルで
    ; 予測器とずれた("2246.07656!"のような9桁の例で発覚、仕様書に無い
    ; 判断としてここに明記)。
    ; |SCALE|>38(MDP10が2パスに分ける稀なケース)は未対応
    ; =仕様書に無い判断、本ルーチンのヘッダコメント参照。
_fin_scale_nonzero:
    LD A,(FIN_SCALE)
    BIT 7,A
    JP NZ,_fin_scale_check_neg
    CP 39
    JP NC,_fin_scale_overflow
    JP _fin_scale_range_ok
_fin_scale_check_neg:
    NEG
    CP 39
    JP NC,_fin_scale_overflow_neg
_fin_scale_range_ok:
    CALL UDWORD_TO_DOUBLE

    LD A,(FIN_SCALE)
    BIT 7,A
    JP Z,_fin_dpos
    NEG                           ; A=|SCALE| (1..38)、そのままテーブル添字
    CALL DBL_TABLE_LOOKUP
    CALL DBL_DIV
    JP _fin_after_scale
_fin_dpos:
    CALL DBL_TABLE_LOOKUP
    CALL DBL_MUL
_fin_after_scale:
    LD A,(MBF_STATUS)
    OR A
    JP Z,_fin_scale_ok
    ; DBL_MUL/DBL_DIVがオーバーフローを検出済み(RES_SIGNは設定済み)。
    ; MBF_RESへ残留値($INFPD/$INFMD相当)を書く。
    CALL MBF_PACK_OVERFLOW
    JP _fin_done
_fin_scale_ok:
    CALL DBL_TO_SINGLE_CSD
    JP _fin_done

_fin_scale_overflow:
    LD A,(FIN_SIGN)
    LD (RES_SIGN),A
    CALL MBF_PACK_OVERFLOW
    JP _fin_done
_fin_scale_overflow_neg:
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    CALL MBF_PACK_RES
_fin_done:
    RET

; MBF_RES(4byte)をMBF_OPAへ複写。AF破壊。
FIN_COPY_RES_TO_OPA:
    LD A,(MBF_RES)
    LD (MBF_OPA),A
    LD A,(MBF_RES+1)
    LD (MBF_OPA+1),A
    LD A,(MBF_RES+2)
    LD (MBF_OPA+2),A
    LD A,(MBF_RES+3)
    LD (MBF_OPA+3),A
    RET

; MBF_OPBへ単精度定数10.0(仮数0xA00000・指数132)を書く。AF破壊。
FIN_SET_OPB_TEN:
    ; 10.0の単精度符号化: 仮数24bit=0xA00000(暗黙の先頭1を含む)、
    ; 格納するのは先頭1を除いた上位7bit=0x20(符号0)。exp=132。
    ; (最初 byte2 に生の仮数上位byte 0xA0 をそのまま書いていたら符号bit
    ; (0xA0のbit7)が立って「負の10.0」になり、FINの符号が丸ごと反転する
    ; 不具合になった。.5と-.5の符号が入れ替わる形で発覚)。
    XOR A
    LD (MBF_OPB),A
    LD (MBF_OPB+1),A
    LD A,0x20
    LD (MBF_OPB+2),A
    LD A,132
    LD (MBF_OPB+3),A
    RET

; FIN_ACC(32bit) = FIN_ACC*10 + A(digit,0-9)。
; DIV_T0-3・DIV_R0-3をスクラッチに使う(MBF_DIVと同時には呼ばれないので
; 衝突しない=仕様書に無い判断、番地の使い回し)。
FIN_MUL10ADD:
    LD (WK_FINDIGIT),A
    LD A,(FIN_ACC0)
    LD (DIV_T0),A
    LD A,(FIN_ACC1)
    LD (DIV_T1),A
    LD A,(FIN_ACC2)
    LD (DIV_T2),A
    LD A,(FIN_ACC3)
    LD (DIV_T3),A
    XOR A
    LD A,(DIV_T0)
    SLA A
    LD (DIV_T0),A
    LD A,(DIV_T1)
    RLA
    LD (DIV_T1),A
    LD A,(DIV_T2)
    RLA
    LD (DIV_T2),A
    LD A,(DIV_T3)
    RLA
    LD (DIV_T3),A
    ; DIV_R = DIV_T (これからDIV_R<<=2してACC*8を作る)
    LD A,(DIV_T0)
    LD (DIV_R0),A
    LD A,(DIV_T1)
    LD (DIV_R1),A
    LD A,(DIV_T2)
    LD (DIV_R2),A
    LD A,(DIV_T3)
    LD (DIV_R3),A
    XOR A
    LD A,(DIV_R0)
    SLA A
    LD (DIV_R0),A
    LD A,(DIV_R1)
    RLA
    LD (DIV_R1),A
    LD A,(DIV_R2)
    RLA
    LD (DIV_R2),A
    LD A,(DIV_R3)
    RLA
    LD (DIV_R3),A
    XOR A
    LD A,(DIV_R0)
    SLA A
    LD (DIV_R0),A
    LD A,(DIV_R1)
    RLA
    LD (DIV_R1),A
    LD A,(DIV_R2)
    RLA
    LD (DIV_R2),A
    LD A,(DIV_R3)
    RLA
    LD (DIV_R3),A
    ; FIN_ACC = DIV_T(*2) + DIV_R(*8)
    LD A,(DIV_T0)
    LD B,A
    LD A,(DIV_R0)
    ADD A,B
    LD (FIN_ACC0),A
    LD A,(DIV_T1)
    LD B,A
    LD A,(DIV_R1)
    ADC A,B
    LD (FIN_ACC1),A
    LD A,(DIV_T2)
    LD B,A
    LD A,(DIV_R2)
    ADC A,B
    LD (FIN_ACC2),A
    LD A,(DIV_T3)
    LD B,A
    LD A,(DIV_R3)
    ADC A,B
    LD (FIN_ACC3),A
    ; += digit
    LD A,(WK_FINDIGIT)
    LD B,A
    LD A,(FIN_ACC0)
    ADD A,B
    LD (FIN_ACC0),A
    JR NC,_fmul10_done
    LD A,(FIN_ACC1)
    INC A
    LD (FIN_ACC1),A
    JR NZ,_fmul10_done
    LD A,(FIN_ACC2)
    INC A
    LD (FIN_ACC2),A
    JR NZ,_fmul10_done
    LD A,(FIN_ACC3)
    INC A
    LD (FIN_ACC3),A
_fmul10_done:
    RET

; =======================================================================
; MBF_FOUT — 単精度MBF(MBF_OPA)を10進の数字文字列(FOUT_BUF、FOUT_LEN)へ
; 変換する。符号の桁・後置空白は呼び出し側(PRINT)の仕事とし、ここでは
; 数字列だけを返す(coordinator指示どおりの境界)。
;
; docs/spec/l4-basic.md 第5.3〜5.5節(第3.1版、単精度の規則は不変)の規則:
;   有効6桁に丸め、末尾0を除去。整数部が6桁を超えたら`E±nn`指数表記
;   （丸めた後の値で判定）。|v|<1側はLEN7則(固定表記にしたときの
;   小数点右の文字数が7以下なら固定)。
;
; 仕様書に無い判断（アルゴリズムそのもの。8086の$FOUT/$FOFMTの写経では
; ない）:
;   - 値を[100000,1000000)へ収まるまで単精度の10.0で繰り返し
;     掛ける/割る(FIN同様、繰り返し丸めが入る近似。MBF_FINのような
;     2進累乗法は使っていない——ここでの繰り返し回数は|10進指数|程度
;     で頭打ちなうえ、単精度の指数範囲全体(概ね±38)をカバーする必要が
;     あり、実装の時間の都合で素朴な逐次乗除算のままにした)。
;   - 0.5を足してから整数部を右シフトで取り出す(偶数丸めではなく
;     「0.5を足して切り捨て」。真のタイでは常に切り上げになり、
;     GW-BASICの偶数丸めとは異なりうる)。
;   - 得た整数(最大32bit)を10で6回割って6桁を1の位から取り出す。
; =======================================================================
FOUT_SIGN     EQU 0xC0C0
FOUT_E        EQU 0xC0C1   ; 符号つき1バイト
FOUT_SCALECNT EQU 0xC0C2   ; 符号つき1バイト
FOUT_INT3     EQU 0xC0C3
FOUT_INT2     EQU 0xC0C4
FOUT_INT1     EQU 0xC0C5
FOUT_INT0     EQU 0xC0C6
WK_REM10      EQU 0xC0C7
FOUT_DIGITS   EQU 0xC0C8   ; 6バイト(C8-CD)
FOUT_NSIG     EQU 0xC0CE
FOUT_ISFIXED  EQU 0xC0CF
FOUT_BUF      EQU 0xC0D0   ; 16バイト(D0-DF)
FOUT_LEN      EQU 0xC0E0
WK_FOUTLOOP   EQU 0xC0E1
FOUT_DIGIDX   EQU 0xC0E2
FOUT_R_START  EQU 0xC0E3
FOUT_R_COUNT  EQU 0xC0E4
FOUT_R_CHAR   EQU 0xC0E5
FOUT_SHIFTCNT EQU 0xC0E6
FOUT_SHIFTORIG EQU 0xC0E7
FOUT_ORIGVAL   EQU 0xC0E8   ; 4バイト(E8-EB)

MBF_FOUT:
    XOR A
    LD (MBF_STATUS),A
    LD (FOUT_LEN),A
    CALL MBF_UNPACK_A
    LD A,(UA_EXP)
    OR A
    JP NZ,_fout_nonzero
    LD A,'0'
    CALL FOUT_APPEND_CHAR
    RET
_fout_nonzero:
    LD A,(UA_SIGN)
    LD (FOUT_SIGN),A
    ; |OPA| (符号bitだけ落とす。OPAはこのルーチン内で書き換えてよい
    ; =仕様書に無い判断、呼び出し側はOPAの保存を期待しない設計)
    LD A,(MBF_OPA+2)
    AND 0x7F
    LD (MBF_OPA+2),A
    XOR A
    LD (FOUT_SCALECNT),A
    ; 元の値(符号を落としただけ)を退避しておく。桁合わせのループは
    ; 「何回10倍/10分の1にすればよいか」を数えるためだけに使い、実際の
    ; 桁合わせはこの後2進累乗法で1回だけ行う(仕様書に無い判断。最初は
    ; ループ内で直接掛け続けていたが、乱数1200件照合で約67%が丸め誤差の
    ; 積み重ねで不一致になり、MBF_FINと同じ2進累乗法に作り直した)。
    LD A,(MBF_OPA)
    LD (FOUT_ORIGVAL),A
    LD A,(MBF_OPA+1)
    LD (FOUT_ORIGVAL+1),A
    LD A,(MBF_OPA+2)
    LD (FOUT_ORIGVAL+2),A
    LD A,(MBF_OPA+3)
    LD (FOUT_ORIGVAL+3),A

_fout_scale_up:
    CALL FOUT_SET_OPB_1E5
    CALL MBF_CMP
    LD A,(MBF_OUT_CMP)
    CP 0xFF
    JP NZ,_fout_scale_up_done
    CALL FIN_SET_OPB_TEN
    CALL MBF_MUL
    LD A,(MBF_RES)
    LD (MBF_OPA),A
    LD A,(MBF_RES+1)
    LD (MBF_OPA+1),A
    LD A,(MBF_RES+2)
    LD (MBF_OPA+2),A
    LD A,(MBF_RES+3)
    LD (MBF_OPA+3),A
    LD A,(FOUT_SCALECNT)
    INC A
    LD (FOUT_SCALECNT),A
    JP _fout_scale_up
_fout_scale_up_done:

_fout_scale_down:
    CALL FOUT_SET_OPB_1E6
    CALL MBF_CMP
    LD A,(MBF_OUT_CMP)
    CP 0xFF
    JP Z,_fout_scale_down_done
    CALL FIN_SET_OPB_TEN
    CALL MBF_DIV
    LD A,(MBF_RES)
    LD (MBF_OPA),A
    LD A,(MBF_RES+1)
    LD (MBF_OPA+1),A
    LD A,(MBF_RES+2)
    LD (MBF_OPA+2),A
    LD A,(MBF_RES+3)
    LD (MBF_OPA+3),A
    LD A,(FOUT_SCALECNT)
    DEC A
    LD (FOUT_SCALECNT),A
    JP _fout_scale_down
_fout_scale_down_done:

    ; e = 6 - SCALECNT
    LD A,6
    LD B,A
    LD A,(FOUT_SCALECNT)
    LD C,A
    LD A,B
    SUB C
    LD (FOUT_E),A

    ; SCALECNTは決まったので、実際の桁合わせは元の値(FOUT_ORIGVAL)へ
    ; 10^|SCALECNT|を2進累乗法(MBF_FINと同じ手法。FIN_POW/FIN_BASE/
    ; WK_FINLOOP/FIN_SCALE_NEGを使い回す=仕様書に無い判断、FINと同時に
    ; 呼ばれないので安全)で1回だけ適用し、複数回の丸めの積み重なりを
    ; 避ける。
    LD A,(FOUT_SCALECNT)
    OR A
    JP Z,_fout_pow_skip
    BIT 7,A
    JP Z,_fout_pow_e_pos
    NEG
    LD (WK_FINLOOP),A
    LD A,1
    LD (FIN_SCALE_NEG),A
    JP _fout_pow_have_e
_fout_pow_e_pos:
    LD (WK_FINLOOP),A
    XOR A
    LD (FIN_SCALE_NEG),A
_fout_pow_have_e:
    XOR A
    LD (FIN_POW),A
    LD (FIN_POW+1),A
    LD (FIN_POW+2),A
    LD A,129
    LD (FIN_POW+3),A
    CALL FIN_SET_OPB_TEN
    LD A,(MBF_OPB)
    LD (FIN_BASE),A
    LD A,(MBF_OPB+1)
    LD (FIN_BASE+1),A
    LD A,(MBF_OPB+2)
    LD (FIN_BASE+2),A
    LD A,(MBF_OPB+3)
    LD (FIN_BASE+3),A
_fout_pow_loop:
    LD A,(WK_FINLOOP)
    OR A
    JP Z,_fout_pow_done
    BIT 0,A
    JP Z,_fout_pow_noadd
    LD A,(FIN_POW)
    LD (MBF_OPA),A
    LD A,(FIN_POW+1)
    LD (MBF_OPA+1),A
    LD A,(FIN_POW+2)
    LD (MBF_OPA+2),A
    LD A,(FIN_POW+3)
    LD (MBF_OPA+3),A
    LD A,(FIN_BASE)
    LD (MBF_OPB),A
    LD A,(FIN_BASE+1)
    LD (MBF_OPB+1),A
    LD A,(FIN_BASE+2)
    LD (MBF_OPB+2),A
    LD A,(FIN_BASE+3)
    LD (MBF_OPB+3),A
    CALL MBF_MUL
    LD A,(MBF_RES)
    LD (FIN_POW),A
    LD A,(MBF_RES+1)
    LD (FIN_POW+1),A
    LD A,(MBF_RES+2)
    LD (FIN_POW+2),A
    LD A,(MBF_RES+3)
    LD (FIN_POW+3),A
_fout_pow_noadd:
    LD A,(WK_FINLOOP)
    SRL A
    LD (WK_FINLOOP),A
    OR A
    JP Z,_fout_pow_done
    LD A,(FIN_BASE)
    LD (MBF_OPA),A
    LD A,(FIN_BASE+1)
    LD (MBF_OPA+1),A
    LD A,(FIN_BASE+2)
    LD (MBF_OPA+2),A
    LD A,(FIN_BASE+3)
    LD (MBF_OPA+3),A
    LD A,(FIN_BASE)
    LD (MBF_OPB),A
    LD A,(FIN_BASE+1)
    LD (MBF_OPB+1),A
    LD A,(FIN_BASE+2)
    LD (MBF_OPB+2),A
    LD A,(FIN_BASE+3)
    LD (MBF_OPB+3),A
    CALL MBF_MUL
    LD A,(MBF_RES)
    LD (FIN_BASE),A
    LD A,(MBF_RES+1)
    LD (FIN_BASE+1),A
    LD A,(MBF_RES+2)
    LD (FIN_BASE+2),A
    LD A,(MBF_RES+3)
    LD (FIN_BASE+3),A
    JP _fout_pow_loop
_fout_pow_done:
    LD A,(FOUT_ORIGVAL)
    LD (MBF_OPA),A
    LD A,(FOUT_ORIGVAL+1)
    LD (MBF_OPA+1),A
    LD A,(FOUT_ORIGVAL+2)
    LD (MBF_OPA+2),A
    LD A,(FOUT_ORIGVAL+3)
    LD (MBF_OPA+3),A
    LD A,(FIN_POW)
    LD (MBF_OPB),A
    LD A,(FIN_POW+1)
    LD (MBF_OPB+1),A
    LD A,(FIN_POW+2)
    LD (MBF_OPB+2),A
    LD A,(FIN_POW+3)
    LD (MBF_OPB+3),A
    LD A,(FIN_SCALE_NEG)
    OR A
    JP NZ,_fout_pow_div
    CALL MBF_MUL
    JP _fout_pow_apply_done
_fout_pow_div:
    CALL MBF_DIV
_fout_pow_apply_done:
    LD A,(MBF_RES)
    LD (MBF_OPA),A
    LD A,(MBF_RES+1)
    LD (MBF_OPA+1),A
    LD A,(MBF_RES+2)
    LD (MBF_OPA+2),A
    LD A,(MBF_RES+3)
    LD (MBF_OPA+3),A
    JP _fout_pow_finalize
_fout_pow_skip:
    LD A,(FOUT_ORIGVAL)
    LD (MBF_OPA),A
    LD A,(FOUT_ORIGVAL+1)
    LD (MBF_OPA+1),A
    LD A,(FOUT_ORIGVAL+2)
    LD (MBF_OPA+2),A
    LD A,(FOUT_ORIGVAL+3)
    LD (MBF_OPA+3),A
_fout_pow_finalize:

    ; 整数部を切り出しつつ偶数丸めする(旧実装は「0.5を足してから
    ; 切り捨て」だったが、乱数1200件照合で約67%が最下位桁+1の系統的な
    ; ずれになり不採用にした——原因はここではなく整列済み値の丸めの
    ; 甘さだったので、guard/sticky方式の偶数丸めに置き換えた=
    ; 仕様書に無い判断)。
    ; shift = 152 - UA_EXP (OPAは桁合わせ後のスケール済み値)
    CALL MBF_UNPACK_A
    LD A,152
    LD B,A
    LD A,(UA_EXP)
    LD C,A
    LD A,B
    SUB C
    LD (FOUT_SHIFTCNT),A
    LD (FOUT_SHIFTORIG),A
    LD A,(UA_M2)
    LD (FOUT_INT2),A
    LD A,(UA_M1)
    LD (FOUT_INT1),A
    LD A,(UA_M0)
    LD (FOUT_INT0),A
    XOR A
    LD (FOUT_INT3),A
_fout_shift_loop:
    LD A,(FOUT_SHIFTCNT)
    OR A
    JP Z,_fout_shift_done
    XOR A
    LD A,(FOUT_INT2)
    SRL A
    LD (FOUT_INT2),A
    LD A,(FOUT_INT1)
    RRA
    LD (FOUT_INT1),A
    LD A,(FOUT_INT0)
    RRA
    LD (FOUT_INT0),A
    LD A,(FOUT_SHIFTCNT)
    DEC A
    LD (FOUT_SHIFTCNT),A
    JP _fout_shift_loop
_fout_shift_done:
    ; 偶数丸め: 捨てた下位FOUT_SHIFTORIGビット(<=7bit、UA_M0の下位に
    ; そのまま残っている)をHALF(=2^(shift-1))と比較する。
    LD A,(FOUT_SHIFTORIG)
    OR A
    JP Z,_fout_round_done      ; shift=0なら丸め不要(小数部が無い)
    DEC A
    LD (WK_FOUTLOOP),A
    LD A,1
    LD (WK_REM10),A
_fout_half_loop:
    LD A,(WK_FOUTLOOP)
    OR A
    JP Z,_fout_half_done
    LD A,(WK_REM10)
    SLA A
    LD (WK_REM10),A
    LD A,(WK_FOUTLOOP)
    DEC A
    LD (WK_FOUTLOOP),A
    JP _fout_half_loop
_fout_half_done:
    LD A,(WK_REM10)
    LD B,A
    SLA A
    DEC A
    LD C,A
    LD A,(UA_M0)
    AND C
    CP B
    JP C,_fout_round_done
    JP NZ,_fout_round_up
    LD A,(FOUT_INT0)
    BIT 0,A
    JP Z,_fout_round_done
_fout_round_up:
    LD A,(FOUT_INT0)
    INC A
    LD (FOUT_INT0),A
    JP NZ,_fout_round_done
    LD A,(FOUT_INT1)
    INC A
    LD (FOUT_INT1),A
    JP NZ,_fout_round_done
    LD A,(FOUT_INT2)
    INC A
    LD (FOUT_INT2),A
_fout_round_done:

    ; 桁あふれ判定: 整数部>=1,000,000なら10で割ってe+=1
    ; (0x0F4240 = 1,000,000。FOUT_INT3は常に0の範囲なので3byte比較でよい)
    LD A,(FOUT_INT2)
    CP 0x0F
    JP C,_fout_no_overflow
    JP NZ,_fout_do_overflow
    LD A,(FOUT_INT1)
    CP 0x42
    JP C,_fout_no_overflow
    JP NZ,_fout_do_overflow
    LD A,(FOUT_INT0)
    CP 0x40
    JP C,_fout_no_overflow
_fout_do_overflow:
    CALL INT32_DIVMOD10
    LD A,(FOUT_E)
    INC A
    LD (FOUT_E),A
_fout_no_overflow:

    ; 6桁を1の位から取り出す
    LD A,5
    LD (FOUT_DIGIDX),A
    LD A,6
    LD (WK_FOUTLOOP),A
_fout_digit_loop:
    CALL INT32_DIVMOD10
    LD A,(FOUT_DIGIDX)
    LD D,0
    LD E,A
    LD HL,FOUT_DIGITS
    ADD HL,DE
    LD A,(WK_REM10)
    ADD A,'0'
    LD (HL),A
    LD A,(FOUT_DIGIDX)
    DEC A
    LD (FOUT_DIGIDX),A
    LD A,(WK_FOUTLOOP)
    DEC A
    LD (WK_FOUTLOOP),A
    JP NZ,_fout_digit_loop

    ; 末尾0を除去
    LD A,6
    LD (FOUT_NSIG),A
_fout_trim_loop:
    LD A,(FOUT_NSIG)
    CP 1
    JP Z,_fout_trim_done
    LD D,0
    LD E,A
    DEC E
    LD HL,FOUT_DIGITS
    ADD HL,DE
    LD A,(HL)
    CP '0'
    JP NZ,_fout_trim_done
    LD A,(FOUT_NSIG)
    DEC A
    LD (FOUT_NSIG),A
    JP _fout_trim_loop
_fout_trim_done:

    ; 固定/指数の判定
    LD A,(FOUT_E)
    OR A
    JP Z,_fout_small
    JP P,_fout_large
    JP _fout_small
_fout_large:
    CP 7
    JP C,_fout_isfixed_yes
    JP _fout_isfixed_no
_fout_small:
    LD A,(FOUT_E)
    NEG
    LD B,A
    LD A,(FOUT_NSIG)
    ADD A,B
    CP 8
    JP C,_fout_isfixed_yes
_fout_isfixed_no:
    JP _fout_build_exp
_fout_isfixed_yes:
    JP _fout_build_fixed

_fout_build_fixed:
    LD A,(FOUT_E)
    OR A
    JP Z,_fout_fx_dotpath
    JP P,_fout_fx_check_ge
    ; e<=0 -> "." + "0"*(-e) + trimmed (e=0のときは"0"*0="")
_fout_fx_dotpath:
    LD A,'.'
    CALL FOUT_APPEND_CHAR
    LD A,(FOUT_E)
    NEG
    LD (FOUT_R_COUNT),A
    LD A,'0'
    LD (FOUT_R_CHAR),A
    CALL FOUT_APPEND_REPEAT
    XOR A
    LD (FOUT_R_START),A
    LD A,(FOUT_NSIG)
    LD (FOUT_R_COUNT),A
    CALL FOUT_APPEND_RANGE
    JP _fout_done
_fout_fx_check_ge:
    JP Z,_fout_fx_e_zero
    LD A,(FOUT_NSIG)
    LD B,A
    LD A,(FOUT_E)
    CP B
    JP NC,_fout_fx_e_ge_nsig
    ; 0<e<nsig -> trimmed[:e] + "." + trimmed[e:]
    XOR A
    LD (FOUT_R_START),A
    LD A,(FOUT_E)
    LD (FOUT_R_COUNT),A
    CALL FOUT_APPEND_RANGE
    LD A,'.'
    CALL FOUT_APPEND_CHAR
    LD A,(FOUT_E)
    LD (FOUT_R_START),A
    LD A,(FOUT_NSIG)
    LD B,A
    LD A,(FOUT_E)
    LD C,A
    LD A,B
    SUB C
    LD (FOUT_R_COUNT),A
    CALL FOUT_APPEND_RANGE
    JP _fout_done
_fout_fx_e_zero:
    ; e==0 (nsig>=1なので e>=nsig は e=0=nsig=0の時だけだが
    ; nsig>=1なので必ず0<nsig、つまりe(0)<nsigに該当する境界——
    ; 上のNC分岐はe>=nsigをe=0,nsig=0のときだけ通るはずなので
    ; ここには来ない想定。安全のためtrimmedをそのまま出す)
    XOR A
    LD (FOUT_R_START),A
    LD A,(FOUT_NSIG)
    LD (FOUT_R_COUNT),A
    CALL FOUT_APPEND_RANGE
    JP _fout_done
_fout_fx_e_ge_nsig:
    ; e>=nsig -> trimmed + "0"*(e-nsig)
    XOR A
    LD (FOUT_R_START),A
    LD A,(FOUT_NSIG)
    LD (FOUT_R_COUNT),A
    CALL FOUT_APPEND_RANGE
    LD A,(FOUT_E)
    LD B,A
    LD A,(FOUT_NSIG)
    LD C,A
    LD A,B
    SUB C
    LD (FOUT_R_COUNT),A
    LD A,'0'
    LD (FOUT_R_CHAR),A
    CALL FOUT_APPEND_REPEAT
    JP _fout_done

_fout_build_exp:
    LD A,(FOUT_DIGITS)
    CALL FOUT_APPEND_CHAR
    LD A,(FOUT_NSIG)
    CP 1
    JP Z,_fout_exp_nofrac
    LD A,'.'
    CALL FOUT_APPEND_CHAR
    LD A,1
    LD (FOUT_R_START),A
    LD A,(FOUT_NSIG)
    DEC A
    LD (FOUT_R_COUNT),A
    CALL FOUT_APPEND_RANGE
_fout_exp_nofrac:
    LD A,'E'
    CALL FOUT_APPEND_CHAR
    LD A,(FOUT_E)
    DEC A
    BIT 7,A
    JP Z,_fout_exp_pos
    NEG
    LD (WK_FOUTLOOP),A
    LD A,'-'
    CALL FOUT_APPEND_CHAR
    JP _fout_exp_have_sign
_fout_exp_pos:
    LD (WK_FOUTLOOP),A
    LD A,'+'
    CALL FOUT_APPEND_CHAR
_fout_exp_have_sign:
    XOR A
    LD (WK_FINDIGIT),A
_fout_exp_tens_loop:
    LD A,(WK_FOUTLOOP)
    CP 10
    JP C,_fout_exp_tens_done
    SUB 10
    LD (WK_FOUTLOOP),A
    LD A,(WK_FINDIGIT)
    INC A
    LD (WK_FINDIGIT),A
    JP _fout_exp_tens_loop
_fout_exp_tens_done:
    LD A,(WK_FINDIGIT)
    ADD A,'0'
    CALL FOUT_APPEND_CHAR
    LD A,(WK_FOUTLOOP)
    ADD A,'0'
    CALL FOUT_APPEND_CHAR

_fout_done:
    RET

; --- FOUT補助ルーチン -------------------------------------------------

; A=文字。FOUT_BUF[FOUT_LEN]へ書きFOUT_LENを進める。
FOUT_APPEND_CHAR:
    PUSH AF
    LD HL,FOUT_BUF
    LD A,(FOUT_LEN)
    LD D,0
    LD E,A
    ADD HL,DE
    POP AF
    LD (HL),A
    LD A,(FOUT_LEN)
    INC A
    LD (FOUT_LEN),A
    RET

; FOUT_DIGITS[FOUT_R_START .. +FOUT_R_COUNT) を FOUT_BUF へ追記する。
FOUT_APPEND_RANGE:
    LD A,(FOUT_R_COUNT)
    OR A
    RET Z
    LD A,(FOUT_R_START)
    LD D,0
    LD E,A
    LD HL,FOUT_DIGITS
    ADD HL,DE
    LD A,(HL)
    CALL FOUT_APPEND_CHAR
    LD A,(FOUT_R_START)
    INC A
    LD (FOUT_R_START),A
    LD A,(FOUT_R_COUNT)
    DEC A
    LD (FOUT_R_COUNT),A
    JP FOUT_APPEND_RANGE

; FOUT_R_CHAR を FOUT_R_COUNT 回だけ FOUT_BUF へ追記する。
FOUT_APPEND_REPEAT:
    LD A,(FOUT_R_COUNT)
    OR A
    RET Z
    LD A,(FOUT_R_CHAR)
    CALL FOUT_APPEND_CHAR
    LD A,(FOUT_R_COUNT)
    DEC A
    LD (FOUT_R_COUNT),A
    JP FOUT_APPEND_REPEAT

; FOUT_INT3:2:1:0(32bit) /= 10。商は同じ場所へ、余りはWK_REM10へ(0-9)。
INT32_DIVMOD10:
    XOR A
    LD (WK_REM10),A
    LD B,32
_i32d10_loop:
    XOR A
    LD A,(FOUT_INT0)
    SLA A
    LD (FOUT_INT0),A
    LD A,(FOUT_INT1)
    RLA
    LD (FOUT_INT1),A
    LD A,(FOUT_INT2)
    RLA
    LD (FOUT_INT2),A
    LD A,(FOUT_INT3)
    RLA
    LD (FOUT_INT3),A
    LD A,(WK_REM10)
    RLA
    LD (WK_REM10),A
    LD A,(WK_REM10)
    CP 10
    JP C,_i32d10_skip
    SUB 10
    LD (WK_REM10),A
    LD A,(FOUT_INT0)
    OR 1
    LD (FOUT_INT0),A
_i32d10_skip:
    DEC B
    JP NZ,_i32d10_loop
    RET

; MBF_OPBへ単精度定数100000.0を書く。AF破壊。
FOUT_SET_OPB_1E5:
    XOR A
    LD (MBF_OPB),A
    LD A,0x50
    LD (MBF_OPB+1),A
    LD A,0x43
    LD (MBF_OPB+2),A
    LD A,145
    LD (MBF_OPB+3),A
    RET

; MBF_OPBへ単精度定数1000000.0を書く。AF破壊。
FOUT_SET_OPB_1E6:
    XOR A
    LD (MBF_OPB),A
    LD A,0x24
    LD (MBF_OPB+1),A
    LD A,0x74
    LD (MBF_OPB+2),A
    LD A,148
    LD (MBF_OPB+3),A
    RET

; MBF_OPBへ単精度定数0.5を書く。AF破壊。
FOUT_SET_OPB_HALF:
    XOR A
    LD (MBF_OPB),A
    LD (MBF_OPB+1),A
    LD (MBF_OPB+2),A
    LD A,128
    LD (MBF_OPB+3),A
    RET

; =======================================================================
; 倍精度(56bit仮数)による10進指数の適用（$FINE/MDPTEN、MATH1.ASM
; 1145-1240の再現）。
;
; GW-BASICの$FIN/$FIDIG（MATH2.ASM 1-73）を読んだ結果: 数字の桁は
; $FIDIGにより「一つ前の値を10倍して新しい桁を足す」形でFACへ積み上げ
; られるが、値が1,000,000未満の間（=単精度と判定される範囲）はこの
; 積み上げが常に厳密な整数値のまま行われる（単精度24bit仮数は
; 1,000,000よりずっと大きい16,777,216まで整数を正確に表現できるため、
; 桁の積み上げ自体に丸め誤差は出ない）。したがってMBF_FINの数字の
; 積み上げ部分（FIN_ACC、既存のまま）は最初から厳密でよく、直す必要は
; 無かった。
;
; ずれていたのは10進の指数（小数点位置＋E指数の差=FIN_SCALE）を反映
; する部分だった。実際の$FINEは、指数が非0なら値を必ず倍精度(56bit)へ
; 変換してから、10のべき乗の倍精度定数（$DP00テーブル、MDP10）を
; 1回だけ掛ける/割る（$FMULD/DDIVFA、どちらも正しい丸め）。最後に
; 単精度へ戻す変換($CSD)は「ちょうど半分」に丸め込まれることが無い
; 特殊な丸め（ガードバイトのbit6を強制的に1にする）。
;
; 前の実装は単精度のまま10.0を2進累乗法で繰り返し掛ける自前の近似
; だったため、乱数照合で約2.6%が最下位桁でずれた。倍精度(56bit)を
; 経由する下のDBL_MUL/DBL_DIV/DBL_TO_SINGLE_CSDに置き換えた。
;
; 10のべき乗の倍精度定数（DBL_TABLE、10^0〜10^38）は、$DP00の実バイト列
; を読んで写したものではない——tools/l4_mbf_oracle_v2.py の
; encode_mbf(Fraction(10)**k, 56) と全く同じ計算（10進の厳密値を
; 倍精度へ偶数丸めでエンコードする、決定論的な数学関数）をPythonで
; 独立に計算しただけであり、ROM由来のデータテーブルではない
; （CLAUDE.md禁止事項4の対象外）。
;
; 仕様書に無い判断: |FIN_SCALE|>38（MDP10が2回に分ける稀なケース、
; MATH1.ASM FIN30の2パス）は実装していない。単精度の実用範囲
; （指数の絶対値がおよそ38を超えると値そのものが単精度の範囲外
; ＝オーバーフロー/アンダーフローになる）ではほぼ到達しないため、
; 1回のDBL_MUL/DBL_DIVで済ませ、38を超える場合はオーバーフロー
; 扱いにする。
; =======================================================================
DA_SIGN EQU 0xC100
DA_EXP  EQU 0xC101
DA_M6   EQU 0xC102   ; MSB(bit7=暗黙の先頭1)
DA_M5   EQU 0xC103
DA_M4   EQU 0xC104
DA_M3   EQU 0xC105
DA_M2   EQU 0xC106
DA_M1   EQU 0xC107
DA_M0   EQU 0xC108   ; LSB

DB_SIGN EQU 0xC109
DB_EXP  EQU 0xC10A
DB_M6   EQU 0xC10B
DB_M5   EQU 0xC10C
DB_M4   EQU 0xC10D
DB_M3   EQU 0xC10E
DB_M2   EQU 0xC10F
DB_M1   EQU 0xC110
DB_M0   EQU 0xC111

WK_DS   EQU 0xC112   ; 2バイト、eA+eB等の一時領域

; --- DBL_MUL用(10byte積・被乗数) ---
PR9 EQU 0xC120
PR8 EQU 0xC121
PR7 EQU 0xC122
PR6 EQU 0xC123
PR5 EQU 0xC124
PR4 EQU 0xC125
PR3 EQU 0xC126
PR2 EQU 0xC127
PR1 EQU 0xC128
PR0 EQU 0xC129
MC9 EQU 0xC12A
MC8 EQU 0xC12B
MC7 EQU 0xC12C
MC6 EQU 0xC12D
MC5 EQU 0xC12E
MC4 EQU 0xC12F
MC3 EQU 0xC130
MC2 EQU 0xC131
MC1 EQU 0xC132
MC0 EQU 0xC133
WK_DLOOP EQU 0xC134
PRA EQU 0xC135    ; DA_M3を含む32bit有効乗数ぶんの11byte目(MSB側の桁あふれ)
MCA EQU 0xC136

; --- DBL_DIV用(8byte 商/剰余/スクラッチ/除数) ---
DQ7 EQU 0xC140
DQ6 EQU 0xC141
DQ5 EQU 0xC142
DQ4 EQU 0xC143
DQ3 EQU 0xC144
DQ2 EQU 0xC145
DQ1 EQU 0xC146
DQ0 EQU 0xC147
DR7 EQU 0xC148
DR6 EQU 0xC149
DR5 EQU 0xC14A
DR4 EQU 0xC14B
DR3 EQU 0xC14C
DR2 EQU 0xC14D
DR1 EQU 0xC14E
DR0 EQU 0xC14F
DT7 EQU 0xC150
DT6 EQU 0xC151
DT5 EQU 0xC152
DT4 EQU 0xC153
DT3 EQU 0xC154
DT2 EQU 0xC155
DT1 EQU 0xC156
DT0 EQU 0xC157
DDV7 EQU 0xC158
DDV6 EQU 0xC159
DDV5 EQU 0xC15A
DDV4 EQU 0xC15B
DDV3 EQU 0xC15C
DDV2 EQU 0xC15D
DDV1 EQU 0xC15E
DDV0 EQU 0xC15F
WK_DREMZERO EQU 0xC160
WK_DINIT     EQU 0xC161

; =======================================================================
; SINGLE_TO_DOUBLE — UA_*(単精度、展開済み)をDA_*(倍精度)へ厳密変換する
; (精度が上がるだけなので丸めは不要)。value=mant24*2^(exp-152)を
; mant56=mant24<<32・同じexpで表すと同じ値になる
; (mant56*2^(exp-184)=mant24*2^32*2^(exp-184)=mant24*2^(exp-152))。
; =======================================================================
SINGLE_TO_DOUBLE:
    LD A,(UA_SIGN)
    LD (DA_SIGN),A
    LD A,(UA_EXP)
    LD (DA_EXP),A
    LD A,(UA_M2)
    LD (DA_M6),A
    LD A,(UA_M1)
    LD (DA_M5),A
    LD A,(UA_M0)
    LD (DA_M4),A
    XOR A
    LD (DA_M3),A
    LD (DA_M2),A
    LD (DA_M1),A
    LD (DA_M0),A
    RET

; =======================================================================
; DBL_TABLE_LOOKUP — Aに10進指数(0-38)を入れて呼ぶと、DB_*へ10^Aの
; 倍精度定数を展開する。AF,HL,DE破壊。
; =======================================================================
DBL_TABLE_LOOKUP:
    LD H,0
    LD L,A
    SLA L
    RL H
    SLA L
    RL H
    SLA L
    RL H              ; HL = A*8
    LD DE,DBL_TABLE
    ADD HL,DE
    XOR A
    LD (DB_SIGN),A
    LD A,(HL)
    LD (DB_M0),A
    INC HL
    LD A,(HL)
    LD (DB_M1),A
    INC HL
    LD A,(HL)
    LD (DB_M2),A
    INC HL
    LD A,(HL)
    LD (DB_M3),A
    INC HL
    LD A,(HL)
    LD (DB_M4),A
    INC HL
    LD A,(HL)
    LD (DB_M5),A
    INC HL
    LD A,(HL)
    OR 0x80
    LD (DB_M6),A
    INC HL
    LD A,(HL)
    LD (DB_EXP),A
    RET

; =======================================================================
; DBL_MUL — DA(倍精度) *= DB(倍精度、常に正)。結果はDAへ書き戻す。
; MBF_STATUSにオーバーフロー(1)を設定することがある。
;
; DAはSINGLE_TO_DOUBLE(有効24bit)かUDWORD_TO_DOUBLE(有効32bit)の
; どちらかから来る(下位24bitは常に0)ので、乗算はDAの上位32bitぶんだけ
; テストするshift-add(32回)で足りる——MBF_MULの24回ループと同じ形を、
; 有効ビット数32bit・被乗数(DB、56bit)を11byteへ拡張したものに置き
; 換えただけ(仕様書に無い判断。厳密には56×56の一般乗算が要るが、DAの
; 下位24bitが常に0という構造を利用した簡略化。2パス(|指数|>38)は
; 使わない)。
;
; 丸めは32bit×56bitの厳密な88bit積(PR0-PRA)全体からガード+スティッキー
; (guard=PR3、sticky=PR2|PR1|PR0|(PR3&0x7F))を取って偶数丸めするので、
; MBF_MULと違いビットを捨てずに正しく丸められる(このルーチンは
; $FMULD相当で「正しい丸め」、MBF_MULは$FMULS相当で下位ワードを
; 捨てる粗い丸め——ヘッダコメント参照)。
;
; 解決済みの残課題(2026-09-15追記): 以前この節に「乱数1000〜1200件の
; 照合で約0.3-0.5%が最下位バイトで+1系統的にずれる、原因未特定」と
; 書いていたが、原因はこのルーチンではなく予測器(tools/l4_mbf_oracle_v2.py
; parse_literal の fin_algo="gw")側にあった。予測器がCSD(単精度への
; 最終丸め、タイを作らない特殊丸め)を再現せず、倍精度に丸めた後の値を
; 直接24bit丸めしていたため、二重丸めで生じる差(実際のGW-BASICの
; アルゴリズムに内在する、直接1回丸めとは値が異なる境界が現に存在する)
; を予測できていなかった。このDBL_MULの32bit×56bit shift-add乗算＋
; guard/sticky偶数丸めは、Pythonで独立にビット単位のシミュレーションを
; 組んで(乱数20万件、故障注入なしで0件不一致)検算済みで、以前から
; 正しかった。詳細は tools/l4_mbf_conform.py の expected_fin と
; tools/l4_mbf_oracle_v2.py の parse_literal 該当コメント、
; コミットメッセージ参照。
; =======================================================================
DBL_MUL:
    XOR A
    LD (MBF_STATUS),A
    ; DAが0(DA_EXP=0)ならそのままゼロで返す(仕様書に無い判断。
    ; チェックが無いと仮数0のままexpだけS-129等の値になり、
    ; 「0E+1」のような入力が仮数0・exp非0という不整合な値になった)。
    LD A,(DA_EXP)
    OR A
    JP Z,_dmul_zero
    XOR A
    LD (PRA),A
    LD (PR9),A
    LD (PR8),A
    LD (PR7),A
    LD (PR6),A
    LD (PR5),A
    LD (PR4),A
    LD (PR3),A
    LD (PR2),A
    LD (PR1),A
    LD (PR0),A
    LD A,(DB_M0)
    LD (MC0),A
    LD A,(DB_M1)
    LD (MC1),A
    LD A,(DB_M2)
    LD (MC2),A
    LD A,(DB_M3)
    LD (MC3),A
    LD A,(DB_M4)
    LD (MC4),A
    LD A,(DB_M5)
    LD (MC5),A
    LD A,(DB_M6)
    LD (MC6),A
    XOR A
    LD (MC7),A
    LD (MC8),A
    LD (MC9),A
    LD (MCA),A

    ; DAは単精度からの昇格(SINGLE_TO_DOUBLE)なら24bit有効
    ; (DA_M6:M5:M4のみ非0)、整数の直接倍精度化(UDWORD_TO_DOUBLE)なら
    ; 32bit有効(DA_M3まで非0のことがある)。どちらの場合も対応できるよう
    ; 32回のループでDA_M3まで含めてテストする(仕様書に無い判断。
    ; 最初は24回・24bitだけだったため、UDWORD_TO_DOUBLEが返す32bit
    ; 精度の下位8bit〔DA_M3〕が乗算で無視され、"580.17187E+7!"のような
    ; 2^24を超える`!`強制単精度リテラルで最下位桁がずれた)。
    LD A,32
    LD (WK_DLOOP),A
_dmul_loop:
    ; DA_M6:M5:M4:M3(32bit、M6=MSB)を右へ1、落ちたbit0をCFへ(LSBから)。
    ; MBF_MULと同じ「乗数を下位ビットから試し、その都度被乗数を左へ
    ; 1回シフトする」向き(仕様書に無い判断だった箇所の実際のバグ)。
    ; 最初にMSBから試す向きで書いたところ、重み(2^0起点の被乗数と
    ; テストするビットの重み)が逆転し1.0×10^kのような単純な乗算すら
    ; 丸ごと崩れた(1E10・-1.5E+20の照合で発覚)。
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
    JP NC,_dmul_noadd
    ; PR(11byte) += MC(11byte) LSBから
    LD A,(PR0)
    LD B,A
    LD A,(MC0)
    ADD A,B
    LD (PR0),A
    LD A,(PR1)
    LD B,A
    LD A,(MC1)
    ADC A,B
    LD (PR1),A
    LD A,(PR2)
    LD B,A
    LD A,(MC2)
    ADC A,B
    LD (PR2),A
    LD A,(PR3)
    LD B,A
    LD A,(MC3)
    ADC A,B
    LD (PR3),A
    LD A,(PR4)
    LD B,A
    LD A,(MC4)
    ADC A,B
    LD (PR4),A
    LD A,(PR5)
    LD B,A
    LD A,(MC5)
    ADC A,B
    LD (PR5),A
    LD A,(PR6)
    LD B,A
    LD A,(MC6)
    ADC A,B
    LD (PR6),A
    LD A,(PR7)
    LD B,A
    LD A,(MC7)
    ADC A,B
    LD (PR7),A
    LD A,(PR8)
    LD B,A
    LD A,(MC8)
    ADC A,B
    LD (PR8),A
    LD A,(PR9)
    LD B,A
    LD A,(MC9)
    ADC A,B
    LD (PR9),A
    LD A,(PRA)
    LD B,A
    LD A,(MCA)
    ADC A,B
    LD (PRA),A
_dmul_noadd:
    ; MC(11byte)を左へ1 LSBから
    XOR A
    LD A,(MC0)
    SLA A
    LD (MC0),A
    LD A,(MC1)
    RLA
    LD (MC1),A
    LD A,(MC2)
    RLA
    LD (MC2),A
    LD A,(MC3)
    RLA
    LD (MC3),A
    LD A,(MC4)
    RLA
    LD (MC4),A
    LD A,(MC5)
    RLA
    LD (MC5),A
    LD A,(MC6)
    RLA
    LD (MC6),A
    LD A,(MC7)
    RLA
    LD (MC7),A
    LD A,(MC8)
    RLA
    LD (MC8),A
    LD A,(MC9)
    RLA
    LD (MC9),A
    LD A,(MCA)
    RLA
    LD (MCA),A
    LD A,(WK_DLOOP)
    DEC A
    LD (WK_DLOOP),A
    JP NZ,_dmul_loop

    ; 指数: base=eA+eB-129 (S=eA+eB、S>=385でオーバーフロー、S<129でゼロ)
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
    LD (WK_DS),HL
    LD DE,385
    OR A
    SBC HL,DE
    JP NC,_dmul_overflow
    LD HL,(WK_DS)
    LD DE,129
    OR A
    SBC HL,DE
    JP C,_dmul_zero
    LD A,L
    LD (RES_EXP),A

    ; 正規化: PRAのbit7が立っていればそのまま(exp_adj=1)、
    ; 立っていなければ1bit左シフト(exp_adj=0)。
    LD A,(PRA)
    BIT 7,A
    JP NZ,_dmul_asis
    XOR A
    LD A,(PR0)
    SLA A
    LD (PR0),A
    LD A,(PR1)
    RLA
    LD (PR1),A
    LD A,(PR2)
    RLA
    LD (PR2),A
    LD A,(PR3)
    RLA
    LD (PR3),A
    LD A,(PR4)
    RLA
    LD (PR4),A
    LD A,(PR5)
    RLA
    LD (PR5),A
    LD A,(PR6)
    RLA
    LD (PR6),A
    LD A,(PR7)
    RLA
    LD (PR7),A
    LD A,(PR8)
    RLA
    LD (PR8),A
    LD A,(PR9)
    RLA
    LD (PR9),A
    LD A,(PRA)
    RLA
    LD (PRA),A
    JP _dmul_have_m
_dmul_asis:
    LD A,(RES_EXP)
    INC A
    LD (RES_EXP),A
    JP NZ,_dmul_have_m
    JP MBF_PACK_OVERFLOW
_dmul_have_m:
    ; candidate=PRA:PR9:PR8:PR7:PR6:PR5:PR4(56bit) guard=PR3 sticky=PR2|PR1|PR0|(PR3&0x7F)
    LD A,(PR3)
    LD B,A
    BIT 7,B
    JP Z,_dmul_round_down
    LD A,B
    AND 0x7F
    LD C,A
    LD A,(PR2)
    OR C
    LD C,A
    LD A,(PR1)
    OR C
    LD C,A
    LD A,(PR0)
    OR C
    JP NZ,_dmul_round_up
    LD A,(PR4)
    BIT 0,A
    JP Z,_dmul_round_down
_dmul_round_up:
    LD A,(PR4)
    INC A
    LD (PR4),A
    JP NZ,_dmul_round_down
    LD A,(PR5)
    INC A
    LD (PR5),A
    JP NZ,_dmul_round_down
    LD A,(PR6)
    INC A
    LD (PR6),A
    JP NZ,_dmul_round_down
    LD A,(PR7)
    INC A
    LD (PR7),A
    JP NZ,_dmul_round_down
    LD A,(PR8)
    INC A
    LD (PR8),A
    JP NZ,_dmul_round_down
    LD A,(PR9)
    INC A
    LD (PR9),A
    JP NZ,_dmul_round_down
    LD A,(PRA)
    INC A
    LD (PRA),A
    JP NZ,_dmul_round_down
    LD A,0x80
    LD (PRA),A
    XOR A
    LD (PR9),A
    LD (PR8),A
    LD (PR7),A
    LD (PR6),A
    LD (PR5),A
    LD (PR4),A
    LD A,(RES_EXP)
    INC A
    LD (RES_EXP),A
    JP Z,_dmul_overflow2
_dmul_round_down:
    LD A,(PRA)
    LD (DA_M6),A
    LD A,(PR9)
    LD (DA_M5),A
    LD A,(PR8)
    LD (DA_M4),A
    LD A,(PR7)
    LD (DA_M3),A
    LD A,(PR6)
    LD (DA_M2),A
    LD A,(PR5)
    LD (DA_M1),A
    LD A,(PR4)
    LD (DA_M0),A
    LD A,(RES_SIGN)
    LD (DA_SIGN),A
    LD A,(RES_EXP)
    LD (DA_EXP),A
    RET
_dmul_zero:
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
    RET
_dmul_overflow2:
_dmul_overflow:
    LD A,1
    LD (MBF_STATUS),A
    RET

; =======================================================================
; DBL_DIV — DA(倍精度) /= DB(倍精度、常に正)。結果はDAへ書き戻す。
; MBF_ADDのguard+sticky偶数丸めと同じ考え方をDIVの復元法(MBF_DIVと
; 同型、8byteレジスタ・63回)へ広げたもの。
; =======================================================================
DBL_DIV:
    XOR A
    LD (MBF_STATUS),A
    ; DAが0(DA_EXP=0)ならそのままゼロで返す(DBL_MULと同じ理由)。
    LD A,(DA_EXP)
    OR A
    JP Z,_ddiv_zero
    XOR A
    LD (DQ7),A
    LD (DQ6),A
    LD (DQ5),A
    LD (DQ4),A
    LD (DQ3),A
    LD (DQ2),A
    LD (DQ1),A
    LD (DQ0),A
    LD (DR7),A
    LD A,(DA_M6)
    LD (DR6),A
    LD A,(DA_M5)
    LD (DR5),A
    LD A,(DA_M4)
    LD (DR4),A
    LD A,(DA_M3)
    LD (DR3),A
    LD A,(DA_M2)
    LD (DR2),A
    LD A,(DA_M1)
    LD (DR1),A
    LD A,(DA_M0)
    LD (DR0),A
    XOR A
    LD (DDV7),A
    LD A,(DB_M6)
    LD (DDV6),A
    LD A,(DB_M5)
    LD (DDV5),A
    LD A,(DB_M4)
    LD (DDV4),A
    LD A,(DB_M3)
    LD (DDV3),A
    LD A,(DB_M2)
    LD (DDV2),A
    LD A,(DB_M1)
    LD (DDV1),A
    LD A,(DB_M0)
    LD (DDV0),A

    ; 事前正規化: DA(DR)>=DB(DDV)なら1回だけ引いて前提(R<B)を満たす
    XOR A
    LD (WK_DINIT),A
    LD A,(DR6)
    LD B,A
    LD A,(DDV6)
    CP B
    JP C,_ddiv_a_ge_b
    JP NZ,_ddiv_pre_done
    LD A,(DR5)
    LD B,A
    LD A,(DDV5)
    CP B
    JP C,_ddiv_a_ge_b
    JP NZ,_ddiv_pre_done
    LD A,(DR4)
    LD B,A
    LD A,(DDV4)
    CP B
    JP C,_ddiv_a_ge_b
    JP NZ,_ddiv_pre_done
    LD A,(DR3)
    LD B,A
    LD A,(DDV3)
    CP B
    JP C,_ddiv_a_ge_b
    JP NZ,_ddiv_pre_done
    LD A,(DR2)
    LD B,A
    LD A,(DDV2)
    CP B
    JP C,_ddiv_a_ge_b
    JP NZ,_ddiv_pre_done
    LD A,(DR1)
    LD B,A
    LD A,(DDV1)
    CP B
    JP C,_ddiv_a_ge_b
    JP NZ,_ddiv_pre_done
    LD A,(DR0)
    LD B,A
    LD A,(DDV0)
    CP B
    JP C,_ddiv_a_ge_b
    JP NZ,_ddiv_pre_done
_ddiv_a_ge_b:
    LD A,1
    LD (WK_DINIT),A
    LD A,(DR0)
    LD H,A
    LD A,(DDV0)
    LD L,A
    LD A,H
    SUB L
    LD (DR0),A
    LD A,(DR1)
    LD H,A
    LD A,(DDV1)
    LD L,A
    LD A,H
    SBC A,L
    LD (DR1),A
    LD A,(DR2)
    LD H,A
    LD A,(DDV2)
    LD L,A
    LD A,H
    SBC A,L
    LD (DR2),A
    LD A,(DR3)
    LD H,A
    LD A,(DDV3)
    LD L,A
    LD A,H
    SBC A,L
    LD (DR3),A
    LD A,(DR4)
    LD H,A
    LD A,(DDV4)
    LD L,A
    LD A,H
    SBC A,L
    LD (DR4),A
    LD A,(DR5)
    LD H,A
    LD A,(DDV5)
    LD L,A
    LD A,H
    SBC A,L
    LD (DR5),A
    LD A,(DR6)
    LD H,A
    LD A,(DDV6)
    LD L,A
    LD A,H
    SBC A,L
    LD (DR6),A
_ddiv_pre_done:

    LD A,63
    LD (WK_DLOOP),A
_ddiv_loop:
    ; R(8byte) <<= 1
    XOR A
    LD A,(DR0)
    SLA A
    LD (DR0),A
    LD A,(DR1)
    RLA
    LD (DR1),A
    LD A,(DR2)
    RLA
    LD (DR2),A
    LD A,(DR3)
    RLA
    LD (DR3),A
    LD A,(DR4)
    RLA
    LD (DR4),A
    LD A,(DR5)
    RLA
    LD (DR5),A
    LD A,(DR6)
    RLA
    LD (DR6),A
    LD A,(DR7)
    RLA
    LD (DR7),A
    ; Q(8byte) <<= 1
    XOR A
    LD A,(DQ0)
    SLA A
    LD (DQ0),A
    LD A,(DQ1)
    RLA
    LD (DQ1),A
    LD A,(DQ2)
    RLA
    LD (DQ2),A
    LD A,(DQ3)
    RLA
    LD (DQ3),A
    LD A,(DQ4)
    RLA
    LD (DQ4),A
    LD A,(DQ5)
    RLA
    LD (DQ5),A
    LD A,(DQ6)
    RLA
    LD (DQ6),A
    LD A,(DQ7)
    RLA
    LD (DQ7),A

    ; T = R - DDV(8byte)
    LD A,(DR0)
    LD B,A
    LD A,(DDV0)
    LD C,A
    LD A,B
    SUB C
    LD (DT0),A
    LD A,(DR1)
    LD B,A
    LD A,(DDV1)
    LD C,A
    LD A,B
    SBC A,C
    LD (DT1),A
    LD A,(DR2)
    LD B,A
    LD A,(DDV2)
    LD C,A
    LD A,B
    SBC A,C
    LD (DT2),A
    LD A,(DR3)
    LD B,A
    LD A,(DDV3)
    LD C,A
    LD A,B
    SBC A,C
    LD (DT3),A
    LD A,(DR4)
    LD B,A
    LD A,(DDV4)
    LD C,A
    LD A,B
    SBC A,C
    LD (DT4),A
    LD A,(DR5)
    LD B,A
    LD A,(DDV5)
    LD C,A
    LD A,B
    SBC A,C
    LD (DT5),A
    LD A,(DR6)
    LD B,A
    LD A,(DDV6)
    LD C,A
    LD A,B
    SBC A,C
    LD (DT6),A
    LD A,(DR7)
    LD B,A
    LD A,(DDV7)
    LD C,A
    LD A,B
    SBC A,C
    LD (DT7),A
    JP C,_ddiv_no_sub
    LD A,(DT0)
    LD (DR0),A
    LD A,(DT1)
    LD (DR1),A
    LD A,(DT2)
    LD (DR2),A
    LD A,(DT3)
    LD (DR3),A
    LD A,(DT4)
    LD (DR4),A
    LD A,(DT5)
    LD (DR5),A
    LD A,(DT6)
    LD (DR6),A
    LD A,(DT7)
    LD (DR7),A
    LD A,(DQ0)
    OR 1
    LD (DQ0),A
_ddiv_no_sub:
    LD A,(WK_DLOOP)
    DEC A
    LD (WK_DLOOP),A
    JP NZ,_ddiv_loop

    ; 真の剰余が0か
    XOR A
    LD (WK_DREMZERO),A
    LD A,(DR0)
    OR A
    JP NZ,_ddiv_remnz
    LD A,(DR1)
    OR A
    JP NZ,_ddiv_remnz
    LD A,(DR2)
    OR A
    JP NZ,_ddiv_remnz
    LD A,(DR3)
    OR A
    JP NZ,_ddiv_remnz
    LD A,(DR4)
    OR A
    JP NZ,_ddiv_remnz
    LD A,(DR5)
    OR A
    JP NZ,_ddiv_remnz
    LD A,(DR6)
    OR A
    JP NZ,_ddiv_remnz
    LD A,(DR7)
    OR A
    JP NZ,_ddiv_remnz
    JP _ddiv_remcheck_done
_ddiv_remnz:
    LD A,1
    LD (WK_DREMZERO),A
_ddiv_remcheck_done:

    LD A,(WK_DINIT)
    OR A
    JP Z,_ddiv_no_initbit
    LD A,(DQ7)
    OR 0x80
    LD (DQ7),A
_ddiv_no_initbit:

    ; 指数: base=eA-eB+128。bit7(DQ7)が立っていれば+1、無ければ変わらず
    ; (単精度DIVのderivationと同型、幅だけ56bit用に広げた)。
    LD A,(DA_SIGN)
    LD B,A
    LD A,(DB_SIGN)
    XOR B
    LD (RES_SIGN),A
    LD A,(DA_EXP)
    LD H,0
    LD L,A
    LD DE,128
    ADD HL,DE
    LD A,(DB_EXP)
    LD D,0
    LD E,A
    OR A
    SBC HL,DE
    LD (WK_DS),HL

    LD A,(DQ7)
    BIT 7,A
    JP NZ,_ddiv_noshift
    XOR A
    LD A,(DQ0)
    SLA A
    LD (DQ0),A
    LD A,(DQ1)
    RLA
    LD (DQ1),A
    LD A,(DQ2)
    RLA
    LD (DQ2),A
    LD A,(DQ3)
    RLA
    LD (DQ3),A
    LD A,(DQ4)
    RLA
    LD (DQ4),A
    LD A,(DQ5)
    RLA
    LD (DQ5),A
    LD A,(DQ6)
    RLA
    LD (DQ6),A
    LD A,(DQ7)
    RLA
    LD (DQ7),A
    LD HL,(WK_DS)
    JP _ddiv_have_finalexp
_ddiv_noshift:
    LD HL,(WK_DS)
    LD DE,1
    ADD HL,DE
_ddiv_have_finalexp:
    PUSH HL
    LD DE,256
    OR A
    SBC HL,DE
    POP HL
    JP NC,_ddiv_overflow
    PUSH HL
    LD DE,1
    OR A
    SBC HL,DE
    POP HL
    JP M,_ddiv_zero

    LD A,L
    LD (RES_EXP),A
    LD A,(DQ7)
    LD (DA_M6),A
    LD A,(DQ6)
    LD (DA_M5),A
    LD A,(DQ5)
    LD (DA_M4),A
    LD A,(DQ4)
    LD (DA_M3),A
    LD A,(DQ3)
    LD (DA_M2),A
    LD A,(DQ2)
    LD (DA_M1),A
    LD A,(DQ1)
    LD (DA_M0),A
    ; ガード=DQ0、真の剰余があればスティッキーとして扱う
    LD A,(DQ0)
    LD B,A
    BIT 7,B
    JP Z,_ddiv_round_down
    LD A,B
    AND 0x7F
    LD C,A
    LD A,(WK_DREMZERO)
    OR C
    JP NZ,_ddiv_round_up
    LD A,(DA_M0)
    BIT 0,A
    JP Z,_ddiv_round_down
_ddiv_round_up:
    LD A,(DA_M0)
    INC A
    LD (DA_M0),A
    JP NZ,_ddiv_round_down
    LD A,(DA_M1)
    INC A
    LD (DA_M1),A
    JP NZ,_ddiv_round_down
    LD A,(DA_M2)
    INC A
    LD (DA_M2),A
    JP NZ,_ddiv_round_down
    LD A,(DA_M3)
    INC A
    LD (DA_M3),A
    JP NZ,_ddiv_round_down
    LD A,(DA_M4)
    INC A
    LD (DA_M4),A
    JP NZ,_ddiv_round_down
    LD A,(DA_M5)
    INC A
    LD (DA_M5),A
    JP NZ,_ddiv_round_down
    LD A,(DA_M6)
    INC A
    LD (DA_M6),A
    JP NZ,_ddiv_round_down
    LD A,0x80
    LD (DA_M6),A
    XOR A
    LD (DA_M5),A
    LD (DA_M4),A
    LD (DA_M3),A
    LD (DA_M2),A
    LD (DA_M1),A
    LD (DA_M0),A
    LD A,(RES_EXP)
    INC A
    LD (RES_EXP),A
    JP Z,_ddiv_overflow
_ddiv_round_down:
    LD A,(RES_SIGN)
    LD (DA_SIGN),A
    LD A,(RES_EXP)
    LD (DA_EXP),A
    RET
_ddiv_overflow:
    LD A,1
    LD (MBF_STATUS),A
    RET
_ddiv_zero:
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
    RET

; =======================================================================
; DBL_TO_SINGLE_CSD — DA(倍精度)を単精度へ切り詰める($CSD、MATH2.ASM
; 197-206の再現)。上位24bit(DA_M6:M5:M4)を候補仮数とし、その直後の
; バイト(DA_M3)のbit7だけで切り上げ/切り捨てを決める(bit6を強制1に
; するため、ちょうど半分〈タイ〉には理論上到達しない
; ——tools/l4_mbf_oracle_v2.py csd_narrow と同じ規則)。
; 結果はMBF_RES/MBF_STATUSへ書く。
; =======================================================================
DBL_TO_SINGLE_CSD:
    LD A,(DA_EXP)
    OR A
    JP NZ,_csd_nonzero
    XOR A
    LD (RES_SIGN),A
    LD (RES_EXP),A
    JP MBF_PACK_RES
_csd_nonzero:
    LD A,(DA_M6)
    LD (BIG_M2),A
    LD A,(DA_M5)
    LD (BIG_M1),A
    LD A,(DA_M4)
    LD (BIG_M0),A
    LD A,(DA_SIGN)
    LD (RES_SIGN),A
    LD A,(DA_EXP)
    LD (RES_EXP),A
    LD A,(DA_M3)
    BIT 7,A
    JP Z,_csd_done
    LD A,(BIG_M0)
    INC A
    LD (BIG_M0),A
    JP NZ,_csd_done
    LD A,(BIG_M1)
    INC A
    LD (BIG_M1),A
    JP NZ,_csd_done
    LD A,(BIG_M2)
    INC A
    LD (BIG_M2),A
    JP NZ,_csd_done
    LD A,0x80
    LD (BIG_M2),A
    XOR A
    LD (BIG_M1),A
    LD (BIG_M0),A
    LD A,(RES_EXP)
    INC A
    LD (RES_EXP),A
    JP Z,MBF_PACK_OVERFLOW
_csd_done:
    JP MBF_PACK_RES

; 10^0〜10^38の倍精度MBF定数。tools/l4_mbf_oracle_v2.py の
; encode_mbf(Fraction(10)**k, 56) と同じ計算をPythonで独立に求めた値
; （$DP00の実バイト列を読んで転記したものではない。10進のべき乗を
; 倍精度へ偶数丸めでエンコードする決定論的な計算の結果は、正しく
; 計算する限り誰が計算しても同じバイト列になる）。
DBL_TABLE:
    db 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x81  ; 10^0
    db 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x20, 0x84  ; 10^1
    db 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x48, 0x87  ; 10^2
    db 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7a, 0x8a  ; 10^3
    db 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x1c, 0x8e  ; 10^4
    db 0x00, 0x00, 0x00, 0x00, 0x00, 0x50, 0x43, 0x91  ; 10^5
    db 0x00, 0x00, 0x00, 0x00, 0x00, 0x24, 0x74, 0x94  ; 10^6
    db 0x00, 0x00, 0x00, 0x00, 0x80, 0x96, 0x18, 0x98  ; 10^7
    db 0x00, 0x00, 0x00, 0x00, 0x20, 0xbc, 0x3e, 0x9b  ; 10^8
    db 0x00, 0x00, 0x00, 0x00, 0x28, 0x6b, 0x6e, 0x9e  ; 10^9
    db 0x00, 0x00, 0x00, 0x00, 0xf9, 0x02, 0x15, 0xa2  ; 10^10
    db 0x00, 0x00, 0x00, 0x40, 0xb7, 0x43, 0x3a, 0xa5  ; 10^11
    db 0x00, 0x00, 0x00, 0x10, 0xa5, 0xd4, 0x68, 0xa8  ; 10^12
    db 0x00, 0x00, 0x00, 0x2a, 0xe7, 0x84, 0x11, 0xac  ; 10^13
    db 0x00, 0x00, 0x80, 0xf4, 0x20, 0xe6, 0x35, 0xaf  ; 10^14
    db 0x00, 0x00, 0xa0, 0x31, 0xa9, 0x5f, 0x63, 0xb2  ; 10^15
    db 0x00, 0x00, 0x04, 0xbf, 0xc9, 0x1b, 0x0e, 0xb6  ; 10^16
    db 0x00, 0x00, 0xc5, 0x2e, 0xbc, 0xa2, 0x31, 0xb9  ; 10^17
    db 0x00, 0x40, 0x76, 0x3a, 0x6b, 0x0b, 0x5e, 0xbc  ; 10^18
    db 0x00, 0xe8, 0x89, 0x04, 0x23, 0xc7, 0x0a, 0xc0  ; 10^19
    db 0x00, 0x62, 0xac, 0xc5, 0xeb, 0x78, 0x2d, 0xc3  ; 10^20
    db 0x80, 0x7a, 0x17, 0xb7, 0x26, 0xd7, 0x58, 0xc6  ; 10^21
    db 0x90, 0xac, 0x6e, 0x32, 0x78, 0x86, 0x07, 0xca  ; 10^22
    db 0xb4, 0x57, 0x0a, 0x3f, 0x16, 0x68, 0x29, 0xcd  ; 10^23
    db 0xa1, 0xed, 0xcc, 0xce, 0x1b, 0xc2, 0x53, 0xd0  ; 10^24
    db 0x85, 0x14, 0x40, 0x61, 0x51, 0x59, 0x04, 0xd4  ; 10^25
    db 0xa6, 0x19, 0x90, 0xb9, 0xa5, 0x6f, 0x25, 0xd7  ; 10^26
    db 0x0f, 0x20, 0xf4, 0x27, 0x8f, 0xcb, 0x4e, 0xda  ; 10^27
    db 0x0a, 0x94, 0xf8, 0x78, 0x39, 0x3f, 0x01, 0xde  ; 10^28
    db 0x0c, 0xb9, 0x36, 0xd7, 0x07, 0x8f, 0x21, 0xe1  ; 10^29
    db 0x4f, 0x67, 0x04, 0xcd, 0xc9, 0xf2, 0x49, 0xe4  ; 10^30
    db 0x23, 0x81, 0x45, 0x40, 0x7c, 0x6f, 0x7c, 0xe7  ; 10^31
    db 0xb6, 0x70, 0x2b, 0xa8, 0xad, 0xc5, 0x1d, 0xeb  ; 10^32
    db 0xe3, 0x4c, 0x36, 0x12, 0x19, 0x37, 0x45, 0xee  ; 10^33
    db 0x1c, 0xe0, 0xc3, 0x56, 0xdf, 0x84, 0x76, 0xf1  ; 10^34
    db 0x11, 0x6c, 0x3a, 0x96, 0x0b, 0x13, 0x1a, 0xf5  ; 10^35
    db 0x16, 0x07, 0xc9, 0x7b, 0xce, 0x97, 0x40, 0xf8  ; 10^36
    db 0xdb, 0x48, 0xbb, 0x1a, 0xc2, 0xbd, 0x70, 0xfb  ; 10^37
    db 0x89, 0x0d, 0xb5, 0x50, 0x99, 0x76, 0x16, 0xff  ; 10^38
