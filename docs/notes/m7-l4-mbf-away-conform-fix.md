# 単精度四則演算away丸め化後のZ80実照合の修正

記録日: 2026-09-20（`759de46`でMBF_ADD/SUB/MUL/DIVをaway丸めへ変更した
直後、親から`tools/l4_mbf_z80_selftest.sh`のrc=1報告を受けて対応）。

## 問題

1. `tools/l4_mbf_conform.py`の`expected_binop`（add/sub/mul/div専用）は
   比較相手に`tools/l4_mbf_oracle_v2.py`の`gw_binop`（GWの粗い丸め・
   偶数タイ）を使い続けており、away丸め実装後はN=400照合でadd/sub/mul
   が不一致16/8/14件になっていた。
2. `div --fault div_sticky`（陰性対照）が不一致0になり、故障注入点が
   踏まれていない疑いが出た。

## 対応1: 比較相手をaway丸め予測器へ切替え

`tools/l4_mbf_oracle_v11_away.py`を新設（v2の`_encode_single_away`
（REP01用に先行実装済み）をそのまま呼ぶ薄いラッパ、二重実装しない）。
`tools/l4_mbf_conform.py`の`expected_binop`をこちらへ切替え（v2自体は
無変更。cmp/neg/itos/itod/stod/dtos/fin/dfin/fout/dfout/d*(倍精度)は
従来どおりv2を直接使う）。

## 対応2: div_sticky不一致0の原因究明（数学的に証明）

**単精度MBF除算は、24bit正規化仮数どうしの割り算である限り、
「guard=0x80ちょうど・真の剰余=0」という真のタイに到達することが
数学的にありえない。** 証明の要旨: 除数の仮数mBはbit23=1固定・末尾に
最大23個の0を持ちうる(mB=mBp\*2^t、mBpは奇数、0≦t≦23)。真のタイは
商Q(25bit、guard bit=1すなわち最下位ビットが1=奇数)がmA\*2^24=Q\*mB
を満たすことを要求するが、これはQがmBpの倍数であることに加えて
2^(24-t)の倍数であることを要求する。t≦23なので24-t≧1、すなわちQは
偶数でなければならないが、guard bit=1の定義よりQは奇数——矛盾。
よって除算はタイに到達しない（l4-s7bが実測で「作れなかった」としていた
現象の数学的な理由が本件で確定した）。

この帰結として、`_add_round`（ADD/SUB/DIV共通）の真のタイ分岐
（sticky=0のときaway=常に切り上げ）はDIVからは実行時に一度も通らず、
旧div_sticky故障（DIVの剰余→WK_STICKY反映を外す）は「本来届かない
sticky=0状態」を人工的に作るだけになった。away化後は、その人工的な
sticky=0状態でも「常に切り上げ」（sticky!=0・WK_BORROW=0の場合と同じ
結論）になるため、故障の効果が消えた。**これはバグではなく、away化に
よってDIVの取りうる状態がより単純になった結果**（旧偶数丸めでは
sticky=0とsticky!=0で結論が分かれ得たため故障が検出できていた）。

## 対応3: 故障注入の付け直し

`tools/l4_mbf_conform.py`:
- `FAULT_TIE_EVEN`（新設）: `_add_round`の真のタイ分岐をaway→旧偶数
  丸めへ戻す。ADD/SUB/DIV共通コードなのでop問わず使える。
- `FAULT_MUL_COARSE`: 内容を作り直し。旧版(guardバイトのマスクを
  緩める)はaway化で到達不能になった分岐を書き換えるだけで無効化して
  いたため、`MBF_MUL`の入口自体をWK_MUL_ROUNDMODE=0(旧既定)へ戻す形に
  変更。
- `FAULT_DIV_STICKY`: 削除（検出不能であることを対応2で証明したため）。

`tools/l4_mbf_z80_selftest.sh`:
- `add --fault sticky` → `add --fault tie_even`（sticky無視はadd
  (同符号,WK_BORROW=0)でも数学的に検出不能——DIVと同じ理屈。away規則
  下ではguard bit7=1なら常に切り上げなのでWK_STICKYの値が結論に
  影響しない）。
- `sub --fault tie_even`を追加（`sub --fault sticky`は従来どおり有効
  なため残す。異符号=WK_BORROW=1の場合はsticky=0/!=0で結論が分かれる
  ため、この故障は今も検出力を持つ）。
- `mul --fault mul_coarse`はそのまま（内容変更）。
- `div --fault div_sticky` → `div --fault round_truncate`（DIVが
  実際に到達する全域=タイ以外の丸め判定が機能していることを確認する）。

## 検証結果

`tools/l4_mbf_z80_selftest.sh`: rc=0（全項目OK、正常系14・故障注入
(単精度4+倍精度10)・倍精度22、計50項目）。

正常系の不一致件数（開発時規模、ターミナルで直接実行）:
- add N=5000: 不一致0
- sub N=5000: 不一致0
- mul N=5000（frames=400、N=3000時にframes=200では時間切れ〔missing〕
  が33件出たため引き上げ済み）: 不一致0
- div N=5000: 不一致0

故障注入（陰性対照、`--expect-ng`）の不一致件数:
- add --fault tie_even: 800件中17件不一致
- sub --fault sticky: 800件中15件不一致
- sub --fault tie_even: 800件中12件不一致
- add/sub --fault round_truncate: 400件中93件/34件不一致
- mul --fault mul_coarse: 400件中14件不一致
- div --fault round_truncate: 400件中121件不一致

## 既存の適合への影響

`src/l4_basic/mbf_single.asm`・`src/l4_basic/interp.asm`は本対応では
変更していない（`tools/l4_mbf_conform.py`・
`tools/l4_mbf_oracle_v11_away.py`（新設）・`tools/l4_mbf_z80_selftest.sh`
のみ）。`tools/conform_l4.sh`・`tools/l4_basic_selftest.sh`は本対応の
対象外（別途`759de46`で確認済み、変更なし）。
