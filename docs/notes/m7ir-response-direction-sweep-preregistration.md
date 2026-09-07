# m7ir: 応答（sub→main）を掃引して、「9」が動くかを見る — 事前登録

## 位置づけ

[m7iq](m7iq-early-exchange-allpos-results.md)は判定S2で位置の非対称を埋め、
**累計131armでC型（9以外のrun長）が0本**、**現れたrun長は`1`と`9`だけ**である
ことを記録した。同時に**残る未閉経路を3つ**挙げた。その第2が本稿の対象である。

> **`sub→main`方向（応答）は一度も「9」を狙って壊していない。**

`m7iq`は「位置の非対称を埋めた今、方向の非対称を埋めるのが筋」と書いた。
**本稿はそれを行う。**

## 道具の制約（設計に織り込む）

`sub→main`を触る手段は既存の`--exchange-intervention RUN:MODE:VALUE`である
（`m7ie`で確認したとおり、このフックは**`DIR_SUB_TO_MAIN`にのみ**適用される。
`m7id`で新設した`--request-intervention`は`DIR_MAIN_TO_SUB`専用）。

**このフックは位置を選べない。** モードは`xor-all`・`xor-first`・`xor-tail`・
`replace-all`・`replace-first`である。したがって`m7iq`のような「全位置を1つずつ」
という掃引はできない。

**代わりに強弱2種類を当てる:**

- **`xor-first`**: 先頭1バイトだけを変える。`m7io`／`m7iq`が`main→sub`で
  「位置0」を壊したのと**対になる**。
- **`xor-all`**: run全体を変える。**最も強い摂動**であり、長いrun（256・5632）
  では破壊的になるが、**C型を探すには取りこぼしが少ない。**

**`xor-tail`・`replace-*`は使わない**（`xor-all`と`xor-first`で強弱の両端を
押さえられるため。使わないことをここに明記する）。

## 段階0（本稿）: 事前登録を測定前にコミットする

本稿は測定を1回も走らせる前に単独でコミットする。測定後の書き換え・amendは
行わない。候補runの列挙も本コミット後に行う。

## 測定条件（`m7iq`と同一に固定する）

- 条件Oのみ（公式ROM一式）。A:=`disk#8`（`650cfac8`）、B:=`disk#10`
  （`0c6f7a53`）。
- 打鍵は水準E（`--type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n'
  --frames 3000`）。
- 基準（摂動なし）は**FDC総数195・READ DATA 117・単発9本＋run長9が12本**。

## 段階1: 候補runの列挙（規則を先に固定する）

**候補の規則（測定前に固定）:**

> 条件Oの交換run列（`analyze_error_exchange_shape.exchange_runs`）のうち、
> **方向が`sub→main`**であるものすべて。

**記録すること**: 候補の個数と、各runの番号・長さ・開始clock。
**個数がいくつであっても、規則どおりに列挙されたものをそのまま全部使う。
後から候補を足さない・除かない。**

## 段階2: 各候補runへ強弱2種の摂動を当てる

各候補runについて、次の2 armを測る。

- `--exchange-intervention <RUN>:xor-first:0xFF`
- `--exchange-intervention <RUN>:xor-all:0xFF`

**arm数は候補個数の2倍**になる。

各armについて記録する（値は出さない）:

- `matched`・`applied`・`changed`（介入が届いたか）
- FDCコマンド総数、READ DATA総数
- **READ DATAのrun長の並び（完全な列）**とその多重集合
- run長9のrunの本数

## armの分類（`m7ih`の定義をそのまま使う。測定前に固定）

- **A型（保持）**: 並びが基準と完全一致。
- **B型**: run長が1と9だけで、run長9の本数が**12未満**。
- **C型**: **9でも1でもないrun長**が1本以上現れる。
- **D型**: 上のどれでもない（FDC総数が基準195の10倍＝1950超は無条件にD型）。

**追加で印を付ける（分類は変えない）**: READ DATA総数が**20未満**のarmは
**「入口場面へ到達していない可能性」**として印を付ける（`m7in`・`m7ip`と同じ）。

## 事前登録する判定（測定前に固定。後から動かさない）

- **T1（「9」が動いた）**: C型のarmが1つ以上ある。
- **T2（「9」は動かないが影響はある）**: C型が無く、B型またはD型が1つ以上ある。
- **T3（何も変わらない）**: 全armがA型。
- **O（測定不能）**: 基準が再現しない、決定論性が確認できない。
- **O'（介入が届かなかったarmがある）**: `changed`が0のarmは判定に用いず記録
  する。全armが該当した場合は主判定をO'とする。

**どの判定になるかは予測しない。**

**併せて記録する（判定とは別）**: **C型が1本でもあれば、その事実とrun長の並びを
必ず書く。** 「9」が動く条件を探すのが上位の目的であり、主判定が何であれ
C型は最重要の観測である。

## 事前登録する合格条件（測定前に固定）

1. `tools/recv_run_field_leak_selftest.sh`が全項目OK・rc=0。
2. `tools/analyze_error_exchange_shape_selftest.sh`がrc=0。
3. **基準の再現**: 摂動なしの条件OがFDC総数195・READ DATA 117・run長9が12本。
4. **介入が届いていることをarmごとに確認**: 各armで`changed>=1`。
5. **`xor-first`と`xor-all`の対応**: 長さ1のrunでは両モードが**同じ結果**に
   なるはずである（1バイトしかないため）。**長さ1のrunすべてで両者が一致する
   ことを確認する。** 一致しなければ判定O。**これは道具が期待どおり動いている
   ことの確認である。**
6. **決定論性**: 基準と、**C型に分類された全arm**、および
   **A型・B型・D型それぞれの最初の1arm**について、生ログが独立2回でバイト一致
   すること。
7. **実行したarm数を出力に載せ、候補個数の2倍と一致することを確認する**
   （`m7ig`でzshの語分割によりループが1回しか回らなかったため）。
8. `tools/check_cleanroom.sh`が全項目OK。

## 実務上の取り決め（測定前に固定）

- 各armの生ログは指標を取り出した直後にscratchpad内で削除する。決定論性の
  確認対象は**その場で2回走らせて比較**してから消す。
- **長いrun（256・5632）への`xor-all`は破壊的で、実行時間も長くなりうる。**
  掃引が長引く場合はバックグラウンドで走らせてよいが、**測定中に`git stash`・
  ブランチ切替・`src/`の編集はしない。**

## 言えないこととして先に書いておくこと

- **位置を選べないので、`main→sub`側と同じ密度では触れない。**
  `xor-first`と`xor-all`の2点しか押さえておらず、**中間の位置だけを変えた場合を
  測っていない。** 「応答の全位置を触った」とは言えない。
- **T3・T2が出ても「『9』の出所はROM内部である」とは主張しない。** 言えるのは
  「この経路では届かない」までである（`m7in`・`m7io`・`m7iq`と同じ線引き）。
- **入口へ到達していないarmは「9が動かなかった」の証拠として弱い。** 印を付けて
  区別する。
- run長や本数から元の値を逆算しない（禁止事項5）。
- 条件O・`disk#10`という1本のディスク・1条件である。一般性は主張しない。

## 結果ノート

結果は `docs/notes/m7is-response-direction-sweep-results.md` に書く。事前登録
（本稿）の候補規則・モード・分類・判定規則を後から動かさない。手順逸脱・事故は
隠さず開示節に書く。

## 禁止（本稿の測定中も例外なく適用）

- 公式ROMのバイト列を読まない・出力しない・保存しない。逆アセンブルしない。
- **公式ディスクのイメージを直接読まない**（D88のヘッダ・セクタ情報を含む）。
- 受信run・応答run・交換runのバイト値、FDCデータポート値、シリンダ値、PCN値を
  出力しない。出してよいのは件数・run長・位置番号・交換run番号・clock・
  **ビットマスクの指定値とモード名**・真偽値・rcのみ。
- **値を掃引・推論で復元しない。run長や本数から元の値を逆算しない。**
- 画面本文の生の行を報告・ノート・コミットメッセージ・ツール出力へ書かない
  （禁止事項7）。
- 公式ディスクの実ファイル名を展開して表示しない。
- 第三者の逆アセンブルリスト・解析記事のコード断片を参照しない。

## 根拠リンク（`ls`で存在確認済み）

[m7iq](m7iq-early-exchange-allpos-results.md)（本稿の出所。131armでC型0本、
残る未閉経路3つ、方向の非対称を次に埋めよという提案）・
[m7ip](m7ip-early-exchange-allpos-preregistration.md)・
[m7io](m7io-early-exchange-sweep-results.md)（`main→sub`の位置0掃引。本稿の
`xor-first`と対になる）・
[m7in](m7in-early-exchange-sweep-preregistration.md)（候補規則と印の型）・
[m7im](m7im-position5-results.md)・
[m7ik](m7ik-cycle-request-correspondence-results.md)・
[m7ii](m7ii-bit-flip-runlength-shape-results.md)・
[m7ih](m7ih-bit-flip-runlength-shape-preregistration.md)（型の定義）・
[m7ie](m7ie-request-position-intervention-results.md)（`--exchange-intervention`が
`DIR_SUB_TO_MAIN`専用であることの確認、交換run一覧）・
[m7id](m7id-request-position-intervention-preregistration.md)（`--request-
intervention`が`DIR_MAIN_TO_SUB`専用）・
[m7hb](m7hb-consecutive-read-rule-results.md)（「9件×12周期」の構造）・
`docs/spec/l3-subrom.md` 1.36節・1.57節・3節（第145〜161版）・
`tools/analyze_error_exchange_shape.py`（`exchange_runs`）・
`tools/harness/frontend/main.c`（`--exchange-intervention`のモード）・
`tools/harness/core/q88h_exchange_intervention.c`・
`tools/harness/core/q88h_exchange_intervention.h`（モード定義）・
`tools/compare_l3_entry_fdc.py`（`command_names`）・
`tools/recv_run_field_leak_selftest.sh`・
`tools/analyze_error_exchange_shape_selftest.sh`・
`tools/stage_disk_by_digest.sh`・`tools/check_cleanroom.sh`。
