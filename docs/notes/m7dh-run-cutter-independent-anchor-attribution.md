# m7dh: run切り出し誤差の独立境界アンカーによる実測帰属

実施日: 2026-08-28

`docs/notes/m7df-run-cutter-error-preregistration.md`で事前登録した観測方法の
3〜5を実施し、`docs/notes/m7dg-run-cutter-positive-selftest.md`で成立させた
陽性対照の上に、新規実測とM/R/X判定を積む。

## 実測

`tools/measure.sh`でQUASI88の同一ビルドから、共通clock付きiolog/intlogを
`d0-boot`・`d1-files`・`d2-save`・`d5-seqfile`相当の4条件×各2走で新規取得した。
生ログはリポジトリ外の一時領域だけに置き、コミットしていない。

| 条件 | frames | 打鍵 | iologイベント数 | intlogイベント数 |
|---|---:|---|---:|---:|
| d0-boot | 1800 | なし | 173844 | 15354 |
| d1-files | 2400 | `FILES` | 208778 | 17759 |
| d2-save | 3600 | `SAVE`+`FILES` | 251310 | 20748 |
| d5-seqfile | 6000 | `OPEN`/`PRINT#`/`INPUT#` | 327340 | 26209 |

各条件のrun1とrun2は、iolog/intlog統合の正規化SHA-256が**完全一致**した
（決定論的。`docs/notes/m6-conformance.md`のm6g決定論性確認と同型）。
以降の集計・attributionもrun1/run2で完全一致し、揺れは0件だった。

## 独立境界アンカー

`tools/analyze_run_cutter_attribution.py`を新設した。アンカーは次だけを使う。

- FEスピン系: main視点の受信選択イベント（`OUT $FD`選択・`IN $FC`）を
  ランドマークとし、その前後区間だけを`IN $FE`スピンの境界とする
  （`anchored_fe_spins`）。
- SEND run系: main視点の選択イベント列を方向（SEND/RECV）だけで束ねる
  （`anchor_send_runs`）。

**判定対象の`0F`有無、run長偶奇、末尾pc、FE bit0成否はアンカー構築に使っていない。**
`validate()`で共通clock一意性、CPU別seq単調性、intlock clock単調性を検査し、
構造の正規化SHA-256を事前に固定した上でアンカーを作った。

## FEスピン系: 結果

| 条件・方向 | 現cutスピン数 | 現cut例外 | アンカースピン数 | アンカー例外 | 帰属内訳 |
|---|---:|---:|---:|---:|---|
| d0 RECV前 | 525 | 0 | 525 | 0 | — |
| d0 RECV後 | 526 | 1 | 525 | 0 | false_split 1 |
| d1 RECV前 | 1179 | 2 | 1177 | 0 | false_split 2 |
| d1 RECV後 | 1179 | 2 | 1177 | 0 | false_split 2 |
| d2 RECV前 | 1833 | 3 | 1830 | 0 | false_split 3 |
| d2 RECV後 | 1833 | 3 | 1830 | 0 | false_split 3 |
| d5 RECV前 | 1974 | 3 | 1971 | 0 | false_split 3 |
| d5 RECV後 | 1975 | 4 | 1971 | 0 | false_split 4 |

4条件×2方向×2走のすべてで、現cut例外は**100%が`false_split`**へ帰属し、
`boundary_match`・`interrupt_boundary`・`log_endpoint`は0件だった。アンカー
cutでは例外が全条件で0件になり、正常位置の分子・分母は不必要に変わらなかった
（各方向のスピン総数の差は例外件数と同数）。2走の帰属カテゴリと補正後構造は
完全一致した。

**判定: FEスピン系（RECV前・RECV後とも）= M（手法由来）。**
m7dfの到達条件1〜4をすべて満たす。合成selftest（m7dg）が同型の`false_split`
誤差を再現できることも既に確認済みであり、率が似ただけの判定ではない。

## SEND run系: 結果

| 条件 | 現cut run数 | アンカーrun数 | `0F`例外 | 偶奇例外 |
|---|---:|---:|---:|---:|
| d0-boot | 22 | 18 | 8 | 8 |
| d1-files | 40 | 35 | 16 | 14 |
| d2-save | 58 | 53 | 23 | 22 |
| d5-seqfile | 82 | 67 | 45 | 37 |
| 合計 | 202 | 173 | 92 | 81 |

### `0F`例外の帰属（合計92件）

| 帰属カテゴリ | 件数 | 割合 |
|---|---:|---:|
| boundary_match（現cutとアンカーの境界が完全一致） | 48 | 52% |
| false_split（アンカーが偽分割を検出） | 27 | 29% |
| interrupt_boundary（境界近傍に割り込み受理） | 17 | 18% |

### 偶奇・末尾pc反例の帰属（合計81件）

| 帰属カテゴリ | 件数 | 割合 |
|---|---:|---:|
| boundary_match | 50 | 62% |
| false_split | 31 | 38% |
| interrupt_boundary | 0 | 0% |

`log_endpoint`（ログ端）はどちらの指標にも0件だった。4条件×2走とも、
帰属カテゴリの内訳とrun数・例外数は完全一致した。

## SEND run系のM/R/X判定

m7dfの到達条件へ、`0F`と偶奇を別々に照らす。

- **M条件2**「現cut例外が全件、境界差（偽結合／偽分割／割り込み／ログ端）へ
  一意に帰属する」は、`0F`が52%・偶奇が62%を`boundary_match`（境界が現cutと
  完全に一致している）に帰属するため**不成立**。境界が同じなのに例外が残る
  以上、手法の境界誤認だけでは説明できない。
- **R条件3**「例外位置の直近に割り込み受理、ログ端、別ポートI/O、許容イベント
  だけの曖昧境界が0件」は、`0F`が29%＋18%＝47%、偶奇が38%を`false_split`／
  `interrupt_boundary`に帰属するため**不成立**。境界そのものが揺れている
  例外が無視できない割合で残る以上、独立アンカーで境界が確定したとは言えない。

`0F`・偶奇のどちらも、M・Rいずれの到達条件も満たさない。事前登録どおり
「片方だけ残るならその指標だけをRとする」を試みたが、**どちらの指標も
片方に寄らず両条件を割合的に満たさなかった**。

**判定: SEND run系（`0F`・偶奇とも）= X（混在／識別不能）。**
帰属は`boundary_match`：`0F`48件・偶奇50件、`false_split`＋`interrupt_boundary`：
`0F`44件・偶奇31件と、件数付きで残す。「混在」を一括で解消しない。

## m7df予測との整合

m7dgの合成陽性対照は、少数の境界欠落・偽分割・偽結合が現cutへ機械的に反映
されることを23/23腕で示した。今回の実測でも、`false_split`・`interrupt_boundary`
という同種のカテゴリが実際に現れ、少なくとも一部（FEスピン系の全数、SEND run系の
false_split分）は同じ機序で説明できる。一方、SEND run系の過半数を占める
`boundary_match`はm7dgのどの故障腕にも対応しない——独立アンカーが現cutと同じ
境界を引いた上でなお例外が残る挙動は、境界誤認モデルからは予測されていない。
この不一致自体がSEND run系をXへ分類する根拠であり、m6nの84〜99%域を
境界誤認だけで説明し切る仮説を今回のデータは支持しない。

## 到達条件・不合格条件との対応（m7df）

| 系統・指標 | 判定 | 根拠 |
|---|---|---|
| FEスピン系 RECV前 | M | 例外100% false_split、アンカー例外0、2走完全一致 |
| FEスピン系 RECV後 | M | 同上 |
| SEND run系 `0F` | X | boundary_match 52%・false_split+interrupt 47%で両条件とも不成立 |
| SEND run系 偶奇・末尾pc | X | boundary_match 62%・false_split 38%で両条件とも不成立 |

到達条件を緩めていない。SEND run系がM/Rどちらにも到達しない結果を、
そのままXとして記録する。

## 情報境界

- 新規実測に用いたのはQUASI88コアと`private/rom`・`private/disk`配下の
  公式ROM・公式ディスクだけである。`xxd`/`od`/`hexdump`/`strings`/逆アセンブラは
  使っていない。逆アセンブルも行っていない。
- `private/`配下のファイル内容、および`$FB`/`$FC`/`$FD`等データポートの
  値列は本稿・標準出力・コミット対象のどこにも転記していない。記録したのは
  件数、率、pc/port/kindの種別、境界帰属カテゴリ、SHA-256（先頭16桁のみ表示）、
  frames・打鍵内容（BASICコマンド文字列。ROM内部情報ではない）だけである。
- 生iolog/intlog、`--io-log`/`--int-log`出力、および解析結果JSONはすべて
  リポジトリ外の一時領域に置き、コミットしていない。
- `cmp -l`等でログのファイル内容そのものを出力する操作は行っていない。
  切り分けは件数・カテゴリ・SHA-256だけで行った。
