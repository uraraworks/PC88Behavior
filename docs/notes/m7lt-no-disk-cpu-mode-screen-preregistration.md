# 事前登録: no_diskの5対6は、サブCPUの駆動方式（モード0/1/2）を変えても残るか

## 位置づけ

no_diskの+0要求長（公式5・混成6）について、[m7lr](m7lr-no-disk-main-interrupt-attribution-results.md)は
main側割り込み受理の差（683/679件）を介入で除外できず判定を出さなかったが、診断（事前登録外）で
「起動時交換が混成で数フレーム遅れる」ことと「+0の要求が両側とも同じフレーム759に始まる」ことの
差として数の上で説明がついた。**起動時交換の時間の形**（公式のrun0が7フレーム、混成は後半
run28/29/33で遅れrun35で+5）が次の容疑者として残っている。

ただしこれまでのm7l系列の測定はすべて、計測ハーネス（QUASI88）を`cpu_timing=0`
（`q88_sub_cpu_mode`未指定時の既定値、`src/initval.h`の`DEFAULT_CPU`）で走らせてきた。
モード0はPIO Cの受け渡しでmain/subを排他的に切り替え、FDCはsub側のstateでしか進まない
（`pc88sub.c`の`sub_INT_update`→`fdc_ctrl`という上流の構造。読んだのは公開されている
libretroコアのソース構成であって、公式ROMではない）。つまり、これまで観測してきた
「起動時交換の時間の形」はmain/subの**並行**時間ではなく、ハーネスが選んだ駆動方式が
作った時間である可能性がある。

本稿は、この依存を次の容疑者の追跡に進む前にふるい分ける。**モード1（交互1命令）・
モード2（5μsずつ交互）でも公式5・混成6の分岐が残るか**を測る
（`tools/search_error_response_candidate.py cpu-mode-screen`）。

## 器具（本稿より前に単独コミット済み）

- フロントエンド`--sub-cpu-mode N`（N∈{0,1,2}）: 指定時だけ`q88_sub_cpu_mode`へ値を返す。
  無指定時の挙動は変更前と完全に同じ（NULLを返す）。走り終わりに
  `q88h: core_option q88_sub_cpu_mode requested=N returned=X`を出す（無指定でも出す）。
- `search_error_response_candidate.py`の`calibration_measure`に`sub_cpu_mode`キーワード引数
  （既定None、argv不変）と、新モード`cpu-mode-screen`（`--scenario no_disk`専用）。
  **校正ファイルに依存しない**: +0は`locate_plus0_no_disk`が構造だけで同定する
  （「start_frameが700以上の最初のmain→sub run」）。駆動方式でrun分割自体が変わりうる
  ため、保存済みcalibrationのaxis番号は使わない。
- 判定を担う純関数`classify_cpu_mode_screen`（5判定）と、その根拠となる
  `cpu_mode_screen_reached_ok`（G3）・`cpu_mode_screen_deterministic`（G1）・
  `cpu_mode_screen_effective`（G2）。いずれも合成データだけで自己検査済み
  （`tools/search_error_response_candidate_selftest.sh`）。
- フロントエンドの自己検査`tools/sub_cpu_mode_selftest.sh`（公式ROM不要。自作サブROM＋
  試験用mainドライバ＋自作テストディスクの組で、不正値の拒否とcore_option証跡を確認）。

**本稿までにm7ls・m7lrが確立した結論はすべてモード0での話である**ことをここに明記する。
本稿の測定でモード1/2に切り替えると、それらの結論（683/679件・起動時交換の遅れの形など）が
同じ形で再現するかどうかは本稿では検証しない（対象は+0要求長の5対6だけ）。

## 測定前の関門（すべて真でなければ測定しない）

- **P1** 器具の自己検査と陽性対照2つ（済み）。
  - 陽性対照1: フロントエンドが値を返し忘れる故障（requestedは数えるがreturned=none）を
    G2（`cpu_mode_screen_effective`）が`ineffective`と判定することを確認した。
  - 陽性対照2: G2の「m0と指紋が異なる」条件を外した故障版で、「値は返したが実際には
    効いていない」組（指紋がm0と同一）が有効に化けることを確認した。これにより、
    その条件がこの検出を担っていることを裏付けた。
- **P2** `tools/run_all_selftests.sh`がrc=0（測定前に確認）。
- **P3** G0（同一性）: 各側で`none`（引数なし）と`m0`（`--sub-cpu-mode 0`明示）のI/Oログ指紋が
  一致すること（＝「引数なし」が実際にモード0であることの確認）。測定時に確認し、
  偽なら測定を打ち切る。

## 条件（測定前に固定する。後から動かさない）

側（official／mixed）× 条件7つを走らせる。`--frames 900`、打鍵は既定
（frame 300に改行、frame 700に`FILES 2`）。

| 条件 | `--sub-cpu-mode` | 役割 |
|---|---|---|
| none | 指定しない | 対照（これまでのm7l系列と同じ、モード0のはず） |
| m0 | 0 | モード0の明示指定（G0でnoneと比較） |
| m0_repeat | 0 | m0の決定論性確認 |
| m1 | 1 | 交互1命令 |
| m1_repeat | 1 | m1の決定論性確認 |
| m2 | 2 | 5μsずつ交互 |
| m2_repeat | 2 | m2の決定論性確認 |

## +0の構造的定義（測定前に固定する）

**「start_frameが700以上の最初のmain→sub run」**（`locate_plus0_no_disk`）。
校正ファイルのaxis番号は使わない（駆動方式でrun分割が変わりうるため）。

各条件で記録するもの:
- +0が存在するか、+0の要求長、+0の開始フレーム
- +0より前のrun数
- 起動終わりフレーム（start_frame<700の最後のrunのend_frame）
- +0より前の(方向,長さ)列の指紋（SHA-256先頭12桁、`run_context_sha256`を流用）
- I/Oログ全体の指紋（生ログのSHA-256。値を含むハッシュだが、出力するのはハッシュだけ）
- フロントエンドのcore_option行（requested/returned）
- `metric_source_sha256`相当（走ごとの入力ファイル指紋）

## 関門（測定時にコードで判定し、JSONへ残す）

- **G0 同一性**: 各側で`none`と`m0`のI/Oログ指紋が一致。偽なら結果は`gate_failed`
  （測定結論を出さない）。
- **G1 決定論性**: 各(側,モード∈{m0,m1,m2})で本体とその`_repeat`の、I/Oログ指紋・
  +0の有無・+0の要求長が一致。偽の組があれば`nondeterministic`。
- **G2 到達**: m1/m2の各走（本体・repeatとも）でrequested≥1かつreturnedが指定値、
  かつI/Oログ指紋が同じ側のm0と**異なる**。偽の組があればその組は`ineffective`。
- **G3 +0の成立**: `none`を含む全条件の各走（本体・repeatとも）で、+0が存在し
  起動終わりフレーム<700。偽の組は`unreached`。

## 判定規則（測定前に固定する。この順）

1. `gate_failed`（G0不成立）
2. `nondeterministic`（G1不成立の組が1つでもある）
3. `inconclusive_ineffective_arms`（G2・G3のいずれかで無効な組が1つでもある。
   ineffectiveとunreachedを区別せずまとめて扱う）
4. `split_persists`: m1・m2の**両方**で公式5・混成6が成立
5. `split_changes`: 上記以外（どちらかのモードで公式・混成の要求長が一致する、
   または5/6以外の値が出る）

判定関数`classify_cpu_mode_screen`は純関数として切り出し済みで、合成行で5判定すべてが
出ることを自己検査済み。

## 判定ごとに次にやること（測定前に決めておく）

- **`split_persists`** → 案B（モード0のまま、コアでsubを指定runでNフレーム止める介入で
  「起動時交換の時間の形」を帰属させる）へ進む。駆動方式は次の容疑者の追跡に無関係と
  扱ってよい。
- **`split_changes`** → **どの駆動方式を正典にするかは人間が決める。**
  適合テスト全体（m7l系列に限らずconform_l3等すべて）の前提に関わるため、
  エージェントは推測で決めない。ここで測定を止め、判断を仰ぐ。
- **`inconclusive_ineffective_arms`／`nondeterministic`／`gate_failed`** → 器具を
  直すところから（腕・窓・判定規則は動かさない。器具のバグを疑う）。

## 記述として載せるもの（合否に使わない）

- 各組の+0長さ・開始フレーム・起動終わりフレーム・+0前のrun数。
- 公式・混成の対照で、+0より前の(方向,長さ)列が先頭から何本一致するか
  （`prefix_agreement_count`）。
- +0開始フレームの公式・混成差（`none`・`m0`・`m1`・`m2`それぞれ）。

## 言えないこと

- **エミュレータ上の振る舞いである。**
- **モード1・モード2も実機の並行動作の近似にすぎない。** どれが実機に近いかは
  本稿では決めない（決めるための材料も本稿は持たない）。
- 公式mainが要求長を何で決めているかは言わない。
- `split_persists`になっても、「駆動方式を変えても分岐が残る」以上のことは言わない
  （起動時交換の時間の形が原因だと確定するものではない。それは案Bの仕事）。

## 禁止（本稿の測定中も例外なく適用）

公式ROM・公式ディスクのバイト列を読まない・出力しない・逆アセンブルしない。`private/`の
中身を見ない。道具は交換値・FDC生値・画面本文・PC・割り込みlevel・絶対clockを保存・
出力しない（件数・長さ・方向・フレーム番号・一致・指紋だけ）。私物のパスは環境変数
だけで渡す。**本稿の測定（公式環境での実走）はまだ実施しない**（器具と事前登録のみを
このコミットへ含める）。

## 結果ノート

`docs/notes/m7lt-no-disk-cpu-mode-screen-results.md`に書く。条件・+0の定義・関門・
判定規則を後から動かさない。

## 根拠リンク

[m7lr 事前登録](m7lr-no-disk-main-interrupt-attribution-preregistration.md)・
[m7lr 結果](m7lr-no-disk-main-interrupt-attribution-results.md)（次の容疑者として
「起動時交換の時間の形」を残した診断）・
[m7ls 事前登録](m7ls-no-disk-keystroke-shift-preregistration.md)・
[m7ls 結果](m7ls-no-disk-keystroke-shift-results.md)（m7l系列がモード0で測ってきた
これまでの結論）・仕様1.50〜1.60節・3章（no_diskの残差）。
