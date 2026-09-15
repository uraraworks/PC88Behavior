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
