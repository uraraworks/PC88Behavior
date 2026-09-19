#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_oracle_v6_m6.py — 候補M6(COS(x)=SIN(x+π/2)を角度領域で単精度加算
してから単精度SINをやり直す旧形)

l4-s6c(`docs/notes/l4-s6c-single-precision-range-reduction-results.md`)
で候補M5(範囲縮約を単精度で行う)が42腕中22腕で完全一致したが、
x=50000のCOS(C17)・TAN(C18、COSに依存)だけ大きく外れた。親が公式値
から、`COS(x) = SIN(単精度で丸めたx+π/2)`(M5のSIN手順で計算し直す)
という候補を事後の当てはめとして見つけ、C17を含む複数腕と矛盾しない
ことを確認した。M6はこれをコード化したもの(係数の当てはめはしない、
構造のみ変更)。

## GWソース上の現在の構造(根拠)

`MATH1.ASM`(`edf82c2e`)952-966行、`$COS`のコードは次の順序である:

```
COS: AND $FACM1,177O        ; 符号を消す(cos(-x)=cos(x))
     CALL RR                ; 倍精度でfrac(x/2π)を得る(SINと共有)
     CALL ONEARG             ; ARG=1に初期化
     MOV $ARG,177O            ; ARG=倍精度1/4(1/4回転)
     CALL $FADDD              ; FAC=frac(x/2π)+1/4
     CALL RR1                  ; 1を超えていれば再度frac化
     JMP SHORT SIN30           ; SINの量子化処理(SIN30以降)へ合流
```

つまり現行(v3・M5とも踏襲)は「**xを範囲縮約した後の"回転数の端数"に
1/4を足す**」という手順で、RR(範囲縮約)そのものはSINと1回しか呼ばない
(共有によるコード節約)。

M6は、この共有をやめ、**xそのものに(角度領域で)π/2を単精度で足してから、
SINの手順(RRを含む)を丸ごとやり直す**という、より素朴な(共有を
していない)旧式の実装を仮定する。これは現存するソースの実際のコード
そのものではない(現存するソースは既に共有型)。旧版ソースが無いため、
「共有をやめた場合にどう書けば同じ結果になるはずか」という**最小限の
構造の反転**として実装する。係数(SINCN等)・SIN自体の範囲縮約(M5の
ままの単精度RR)は変更していない。

## 単精度π/2定数

`tools/l4_mbf_oracle_v3.py`の`PI2`(`MATH1.ASM 1137-1138`、$ATANの
ATN100ラベルで使われている単精度π/2定数、DX=7733O・BX=100511O)を
そのまま再利用する(独自の定数は作らない)。ATN以外の場所でこの値が
実際に使われていたかどうかは現存するソースからは分からないが、
「単精度のπ/2」という値自体はこの1つしかソースに現れないため、これを
使う。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import l4_mbf_oracle_v3 as v3  # noqa: E402
import l4_mbf_oracle_v5_m5 as m5  # noqa: E402
from tools.l4_mbf_oracle_v2 import GwNum, force_to_single, gw_binop  # noqa: E402

# SINはM5(単精度範囲縮約)のまま変更しない。
sin_impl = m5.sin_impl


def cos_impl(x: GwNum) -> GwNum:
    """M6: a = x + π/2 (単精度、$FADDS相当)、SIN(a)をM5の手順で計算し直す。
    符号処理(cos(-x)=cos(x))はSIN側の符号処理と独立に効くはずだが、
    x+π/2の単精度加算がそのまま単精度SINへ渡るだけなので、符号の
    特別扱いは不要(SIN自身が負角を判定する)。"""
    a = gw_binop(x, v3.PI2, "+")  # $FADDS(単精度、丸めはv2のgw_binopに委譲)
    a = force_to_single(a)
    return m5.sin_impl(a)


def tan_impl(x: GwNum) -> GwNum:
    s = m5.sin_impl(x)
    c = cos_impl(x)
    return gw_binop(s, c, "/")  # $FDIVS: sin/cos (M0・M5と同一、不変更)
