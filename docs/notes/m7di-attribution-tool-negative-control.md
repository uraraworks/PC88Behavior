# m7di: 帰属解析器自体の陰性対照

実施日: 2026-08-28

`docs/notes/m7dh-run-cutter-independent-anchor-attribution.md`のFE系M判定は
「独立境界アンカーcutでは例外が全条件0件になる」ことに依拠していた。しかし
このプロジェクトには「常に失敗する検出器は故障注入を必ず通過する」
（`docs/notes/feedback_fault_injection_needs_positive_control.md`系）、
「合格条件が失敗状態のほうを強く満たす」という過去事故があり、
**アンカーが常に0を返す壊れ方をしていても同じ結果になる**ため、m7dhの
時点ではこの区別ができていなかった。本稿は`tools/analyze_run_cutter_attribution.py`
自体に対する陰性対照とカテゴリ出し分け確認を行う。新規の公式実走は行わず、
すべて規則生成した合成ログ・合成イベントだけを使う。

## 試験方法

`tools/analyze_run_cutter_attribution_selftest.py`を新設した。3種類に分ける。

1. **分類器の出し分け(単体)**: `relation()`/`classify_group()`(FE系)と
   `run_relation()`/`classify_send()`(SEND系)を直接呼び、
   `boundary_match`・`false_split`・`false_merge`・`interrupt_boundary`・
   `log_endpoint`・`unanchored`の6カテゴリを手作りの座標だけでそれぞれ
   独立に作り分ける。`interrupt_boundary`は境界一致(`boundary_match`)を
   上書きすること、`log_endpoint`はさらにそれより優先されることも確認する。
2. **アンカーの陰性対照(FE系)**: 境界(landmark: `OUT $FD`選択・`IN $FC`)は
   一切崩さず、`IN $FE`読取りの値だけへ本物のbit0規則違反を仕込む。境界が
   正しい以上、現cutとアンカーcutの両方が同じ例外を検出しなければならない。
3. **混在版(FE系)**: 本物の違反と、境界だけが壊れた偽の違反(2読取りの間に
   無関係な別ポートI/Oを挿入して現cutだけを分割させる)を同一ログに混在させ、
   アンカーが本物だけを残すことを確認する。
4. **アンカーの陰性対照(SEND run系)**: 境界(選択イベントの並び)は崩さず、
   `0F`規則(継続位置への誤書込み)・偶奇規則(期待と異なる末尾pc)へ本物の
   違反を仕込む。
5. **正常形**: 何も仕込まない場合に例外0件であることの空振り確認。

合成ログは`tools/run_cutter_positive_selftest.py`と同じ流儀(seq/clock/frame/
cpu/kind/port/value/pc形式のテキスト)で書き出し、`analyze_run_cutter_attribution.analyze()`
をファイル経由でそのまま呼ぶ。データポートのpayloadは合成値でも実際の伏せ字
記法(`--`)または規則生成した非ゼロ値のみを使い、公式ログの値列は一切使わない。

## 結果

### 1. 分類器の出し分け(単体) — 6/6一致

| カテゴリ | FE系(classify_group) | SEND系(classify_send) |
|---|---|---|
| boundary_match | 一致 | 一致 |
| false_split | 一致 | 一致 |
| false_merge | 一致 | 一致 |
| unanchored | 一致 | 一致 |
| interrupt_boundary(boundary_match上書き) | 一致 | 一致 |
| log_endpoint(最優先) | 一致 | 一致 |

分類器は6カテゴリすべてを独立に出し分けられた。全部を1カテゴリへ落とす
壊れ方はしていない。

### 2. FE系アンカー陰性対照 — アンカー例外は0件に潰れなかった

境界を保ったまま`recv_pre`2件・`recv_post`2件へ本物のbit0違反を仕込んだ。

| 方向 | 現cut例外 | アンカー例外 | 帰属 |
|---|---:|---:|---|
| recv_pre | 2 | **2**（0件ではない） | boundary_match 2 |
| recv_post | 2 | **2**（0件ではない） | boundary_match 2 |

**アンカーcutは、境界が正しい真の違反を消さなかった。** m7dhで観測した
「アンカー例外0件」は、アンカーが常に0を返す壊れ方によるものではない。

### 3. FE系混在対照 — 本物と偽物を正しく分離した

本物の違反2件(pre)・2件(post)に加え、境界だけが壊れた偽の違反を各1件
混在させた。

| 方向 | 現cut例外(本物+偽物) | アンカー例外 | 帰属 |
|---|---:|---:|---|
| recv_pre | 3(2+1) | 2(本物のみ) | boundary_match 2, false_split 1 |
| recv_post | 3(2+1) | 2(本物のみ) | boundary_match 2, false_split 1 |

アンカーは偽物(境界差由来)だけを消し、本物は`boundary_match`として残した。
m7dhの実測で見た「境界が一致するのに例外が残る」パターンと、
「境界差に帰属できて消える」パターンの両方を、既知の混在比率で正しく
再現・分離できた。

### 4. SEND run系アンカー陰性対照 — アンカー例外は0件に潰れなかった

境界を保ったまま`0F`規則違反3件・偶奇規則違反2件を仕込んだ。

| 指標 | 現cut例外 | アンカー例外 | 帰属 |
|---|---:|---:|---|
| `0F` | 3 | **3**（0件ではない） | boundary_match 3 |
| 偶奇 | 2 | **2**（0件ではない） | boundary_match 2 |

なお実際のところ、m7dhの実測データ自体がSEND run系の`anchor.ff_exceptions`
／`anchor.parity_exceptions`をすでに非0（各条件8〜45件相当）で報告しており、
SEND側については「アンカーが常に0を返す」空検査だった可能性はm7dhの時点で
既に排除されていた。今回の陰性対照はそれを境界を保った状態で再確認したもの。

### 5. 正常形 — 空振り0件

違反を何も仕込まない場合、FE系・SEND系とも現cut例外は0件だった。

## 検出力・空振り

分類器出し分け12項目、アンカー陰性対照8項目、混在対照6項目、正常形4項目、
計30項目すべてが予測に一致した。不一致は0件、空振り(検出すべきでないものを
検出する誤検出)も0件だった。

`LC_ALL=C`と`LC_ALL=ja_JP.UTF-8`でそれぞれ実行し、標準出力の`diff`は0行、
両方ともrc=0で一致した。

## m7dhのM判定への位置づけ

**FE系M判定は保留へ差し戻さない。** 今回の陰性対照によって、m7dhがM判定の
根拠にした「独立境界アンカーcutでは例外が全条件0件になる」という結果が、
アンカーの構造的な欠陥（常に0を返す壊れ方）ではなく、実際に境界が正しい
場所では例外が生き残ることを確認したうえでの0件であることを示せた。
分類器も6カテゴリを独立に出し分けており、m7dhの「100%が`false_split`へ
帰属した」という報告が「分類器が`false_split`しか返せない」という空検査
由来ではないことも確認した。

以上により、m7dhのFE系M判定・SEND run系X判定はいずれも維持する。判定を
予測へ寄せるための緩和は行っていない。

## 情報境界

- 使用した入力はすべて本稿・`tools/analyze_run_cutter_attribution_selftest.py`
  内で規則生成した合成データであり、`private/`、公式ROM、公式ディスク、
  既存の実測ログは一切読んでいない。新規の公式実走も行っていない。
- データポートのpayloadは合成ログでも伏せ字(`--`)または規則生成した値のみ
  であり、公式ログの値列を転記していない。
- `src/`、`docs/spec/`、既存解析器(`analyze_run_boundary.py`等)の変更は
  行っていない。新設したのは`tools/analyze_run_cutter_attribution_selftest.py`
  と`tools/analyze_run_cutter_attribution_selftest.sh`、および
  `tools/run_all_selftests.sh`への登録行だけである。
