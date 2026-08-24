# m7cp — 応答準備clock掃引の不成立とPIO handoff probe

日付: 2026-08-25

## 結論

`ready-sweep`の校正は通ったが、shift -5〜-1 / +1〜+8の全13介入armで、
指定した量が実測clock差へ反映されなかった。対照を含む14点の掃引結果から
タイミング帰属の結論は一切採らない。**指定量＝実効clockの照合チェックが
無ければ、14点ぶん「遅延を振っても指標が動かない」という無意味な結論を
出していた。** この関門は緩めず回帰検査として残す。

支配点をPIO C handoffへ切り替えた`ready-handoff-probe`はrc=0だった。
`defer_once`では応答準備が5→7clock、到達clock差が相対-1で29→31、
相対+0で-76→-74と、いずれも正確に2clock遅くなった。それでも要求長は6、
`exchange_prefix`は36のままだった。従って、**遅い方向へ2clockずらしても
分岐は生まれない。** 一方、`handoff_now`は対照とfingerprintまで同一で
`ineffective`に分類された。これは公式の2clockへ寄せる介入が成立しなかった、
すなわち**速い方向の測定手段をまだ持っていない**ことの記録である。
「タイミングは原因ではない」とは結論しない。

## 原因

旧介入は対象RECV前の`q88h_io_in()`で`z80main_cpu.state0`を動かした。
しかし既定の`cpu_timing=0`では、main/subの切替は`pio_read_C()`が連続読出しを
検出し、`select_main_cpu`を反転して`CPU_BREAKOFF()`することで決まる。
`state0`は直後の`z80_emu()`戻り値へ入るだけで、timing 0のスケジューラは
その戻り値を使わない。従ってCPU予算は応答準備待ちの支配点ではなく、全armが
効かなかったのは量換算の問題ではない。

旧`ready-sweep`はshift -5〜-1 / +1〜+8の全13 armで指定量と実効clockが
一致せず、対照を含む14点の結論生成前にrc=2で停止した。照合チェックが
無ければ14点ぶんの無意味な結論を出していた。

## 測定設計の切替

係数を掛けてclock差へ合わせる修正はしない。旧`ready-sweep`は結論生成前に
明示的に停止する。代わりに`ready-handoff-probe`を追加し、校正軸の相対-1応答
直前だけで、実際の支配点であるmain側PIO C handoffへ次の離散介入を行う。

- `handoff_now`: 対象FE読出しが通常切替点でなければ、その場でmain→subへ切り替える。
- `defer_once`: 次の通常main→sub切替を1回だけ抑止する。

コア証跡は対象待機への命中、mode、実際のaction、作用回数1を必須にする。
各armの応答準備clock差は「指定量」ではなく観測結果として記録する。数値shiftを
指定したとは扱わないため、ここから言えるのはPIO handoffが待ちを動かすかまでで、
公式と同じ機序や+0要求長の原因だとはまだ言わない。既存の+257ログ陽性対照、
arm別入力指紋、成果物変化関門も維持する。

これは「待ちを支配している要因を仮定で決めない」という既往の前例に従う
切替である。ボトルネック候補を信じる前に介入し、CPU予算への数値介入が
実効clockを動かさないことを確認してから、実際に切替を起こすPIO C handoffを
支配点として特定し、離散介入へ移った。

## 実走

ハーネスを更新後、既存の校正済みstate-dirを使って次を実行する。

```sh
PC88_ERROR_RESPONSE_OPT_IN=1 python3 tools/search_error_response_candidate.py \
  ready-handoff-probe --scenario no_disk --frames 900 --state-dir "$PC88_STATE_DIR"
```

結果は次のとおりだった（rc=0）。

```text
arm=control          ready_clock=5 req_len=6 ex_prefix=36 arrival={-3:4, -2:25, -1:29, +0:-76} fp=16972254a24f
arm=handoff_now      ready_clock=5 req_len=6 ex_prefix=36 arrival={-3:4, -2:25, -1:29, +0:-76} fp=16972254a24f
arm=defer_once       ready_clock=7 req_len=6 ex_prefix=36 arrival={-3:4, -2:25, -1:31, +0:-74} fp=b91c0993a429
arm=clock_shift_257  arrival={-3:261, -2:282, -1:286, +0:181}
ineffective_arms: ['handoff_now']
result=handoff_controls_ready_wait
```

`defer_once`は成果物を変え、応答準備と関係する到達差だけを正確に2clock
遅らせた一方、要求長とprefixを変えなかった。陽性対照`clock_shift_257`も
全到達差を+257動かしており、指標は生きている。対して`handoff_now`は
成果物が対照とビット単位で同一だった。自作subはこのハーネスで出せる最速で
既に応答しており、観測された5clockはhandoff以外の未特定要因に支配される。
従って公式の2clockへ寄せる実験はできていない。確定したのは遅い方向の
2clock摂動が分岐を生まれないことだけで、速い方向は未測定である。

## 情報境界

集約するのは件数、間隔、相対clock差、作用証跡、構造・画面署名とSHA-256だけである。
交換値、生FE値、PC、絶対clock、私物の場所は結果へ保存しない。
公式ROM・公式ディスクの内容や値の列は読まず、記録しない。仕様へ渡すのは
介入の成立性、相対clock差、要求長、prefix、fingerprintによる同一性と測定限界だけである。
