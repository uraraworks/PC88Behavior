# m7it: 応答の位置の非対称を代表位置で埋め、「届かない」を格上げできるか決める — 事前登録

## 位置づけ

[m7is](m7is-response-direction-sweep-results.md)は判定T2で方向の非対称を埋め、
**交換run列60本すべてを両方向とも壊して累計191armでC型が0本**であることを
記録した。同時に、**本稿が新しく作った未閉**を正直に挙げた。

> **応答側の位置の非対称**——`--exchange-intervention`は位置を選べないため、
> `xor-first`（先頭1バイト）と`xor-all`（全体）の**中間が空いている。**

**本稿はこの中間を、代表位置で埋める。** そのうえで、**「『9』は測定では
届かない」を3節へ格上げできるかを決める。**

## 対象を絞る根拠

`m7is`が列挙した`sub→main` 30本のうち、**長さ1が25本**である。長さ1のrunは
`xor-first`＝`xor-all`＝唯一の位置であり、**`m7is`で既に全位置を触っている**
（合格条件5で25本すべて両モード一致を確認済み）。

**中間が空いているのは長さ2以上の5本だけである。**

| run | 長さ |
|---:|---:|
| 9 | 256 |
| 15 | 256 |
| 25 | 256 |
| **29** | **5632** |
| 33 | 256 |

**全位置を触ると6400armになり非現実的**なので、**代表位置**で埋める。

## 代表位置の決め方（測定前に固定。後から動かさない）

長さ`L`のrunについて、次の位置集合を採る（整数除算。重複は除く）。

```
{0, 1, 2, L/4, L/2, 3L/4, L-3, L-2, L-1}
```

- **L=256**: `{0, 1, 2, 64, 128, 192, 253, 254, 255}` → **9位置**
- **L=5632**: `{0, 1, 2, 1408, 2816, 4224, 5629, 5630, 5631}` → **9位置**

**先頭3・末尾3・四分位3を押さえる形**である。`xor-first`（位置0）は`m7is`で
既に測っているが、**本稿でも測り直して一致を確認する**（合格条件に含める）。

**arm数は 5 run × 9 位置 ＝ 45。armを後から追加しない・除かない。**

摂動は`XOR 0xFF`のみ（`m7iq`の位置掃引と揃える）。

## 道具の拡張（`tools/`のみ。`src/`は触らない）

`--exchange-intervention`は位置を選べず、`--request-intervention`（`m7id`で
新設）は`DIR_MAIN_TO_SUB`専用である。**`DIR_SUB_TO_MAIN`に位置指定で当てる
手段が無い。**

`--response-intervention RUN:POS:MODE:VALUE`（名称は実装時に確定してよい）を
新設する。要件:

- **`DIR_SUB_TO_MAIN`のrunにのみ適用**し、**run内の位置を指定できる**。
- `matched`／`applied`／`changed`件数を取得できること。
- **既存の`--exchange-intervention`・`--request-intervention`の挙動を
  1ビットも変えないこと。**
- 出力に値を載せない。

## 段階0（本稿）: 事前登録を測定前にコミットする

本稿は測定を1回も走らせる前に単独でコミットする。測定後の書き換え・amendは
行わない。道具の拡張も本コミット後に行う。

## 測定条件（`m7is`と同一に固定する）

- 条件Oのみ（公式ROM一式）。A:=`disk#8`（`650cfac8`）、B:=`disk#10`
  （`0c6f7a53`）。
- 打鍵は水準E（`--type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n'
  --frames 3000`）。
- 基準（摂動なし）は**FDC総数195・READ DATA 117・単発9本＋run長9が12本**。

## armの分類（`m7ih`の定義をそのまま使う。測定前に固定）

- **A型（保持）**: 並びが基準と完全一致。
- **B型**: run長が1と9だけで、run長9の本数が**12未満**。
- **C型**: **9でも1でもないrun長**が1本以上現れる。
- **D型**: 上のどれでもない（FDC総数が基準195の10倍＝1950超は無条件にD型）。

**追加で印を付ける（分類は変えない）**: READ DATA総数が**20未満**のarmは
**「入口場面へ到達していない可能性」**として印を付ける。

## 事前登録する判定（測定前に固定。後から動かさない）

- **U1（「9」が動いた）**: C型のarmが1つ以上ある。
- **U2（「9」は動かないが影響はある）**: C型が無く、B型またはD型が1つ以上ある。
- **U3（何も変わらない）**: 45armすべてがA型。
- **O（測定不能）**: 基準が再現しない、位置0の結果が`m7is`の`xor-first`と
  食い違う、既存挙動が非回帰でない、決定論性が確認できない。
- **O'（介入が届かなかったarmがある）**: `changed`が0のarmは判定に用いず記録
  する。全armが該当した場合は主判定をO'とする。

**どの判定になるかは予測しない。**

## 格上げの条件（これも測定前に固定する）

**U2またはU3（＝C型が0本）の場合に限り**、3節へ次の項目を**格上げして記録する。**

> **「連続READのrun長『9』は、main⇔subの交換を触る経路では動かせない。」**
> 根拠は累計**236arm**（`m7ii` 40・`m7ik` 12・`m7im` 9・`m7iq` 70・`m7is` 60・
> 本稿45）で、**交換run列60本すべてを両方向とも壊し、run長は常に`1`か`9`
> だけだった**こと。

**格上げの際に必ず併記すること（省略しない）:**

1. **「『9』の出所はROM内部である」とは主張しない。** 言えるのは
   「これらの経路では届かない」までである（3節・第28版と同じ書き方）。
2. **測っていない範囲を数字で明記する**——(a)要求側のビットの非対称
   （入口場面より前の18本は`XOR 0xFF`のみ。全ビットなら**560arm**未測）、
   (b)応答側の非代表位置（長さ2以上の5本で**6400 − 45 = 6355位置**が未測）、
   (c)ディスクの側（`m7il`が土俵無しと記録）。
3. **U1が出た場合は格上げしない。** 追跡を続ける。

## 事前登録する合格条件（測定前に固定）

1. `tools/recv_run_field_leak_selftest.sh`が全項目OK・rc=0。
2. `tools/analyze_error_exchange_shape_selftest.sh`がrc=0。
3. **既存挙動の非回帰**（コア再ビルドを伴うため必須）:
   - 摂動なしの条件Oの生ログが、拡張前と**バイト一致**すること。
   - `--exchange-intervention 9:xor-all:0xFF`（条件O・水準E）の結果が
     `m7is`の記録と一致すること。
   - `--request-intervention 36:0:xor:0xFF`（条件O・水準E）の結果が
     `m7ik`の記録（FDC183・READ108・run長9が11本）と一致すること。
   いずれか食い違えば判定O。
4. **`m7is`との一致**: 5本の**位置0**のarmが、`m7is`の`xor-first`の記録と
   FDC総数・READ総数・run長の並びで一致すること。食い違えば判定O。
5. **介入が届いていることをarmごとに確認**: 各armで`changed>=1`。
6. **決定論性**: 基準と、**C型に分類された全arm**、および**A型・B型・D型
   それぞれの最初の1arm**について、生ログが独立2回でバイト一致すること。
7. **実行したarm数を出力に載せ、45であることを確認する**。
8. `tools/check_cleanroom.sh`が全項目OK。

## 実務上の取り決め（測定前に固定）

- 各armの生ログは指標を取り出した直後にscratchpad内で削除する。決定論性の
  確認対象は**その場で2回走らせて比較**してから消す。
- 掃引が長引く場合はバックグラウンドで走らせてよいが、**測定中に`git stash`・
  ブランチ切替・`src/`の編集はしない。**
- **委譲する場合の指示には、値・バイト列に加えて「実ファイル名・パスを書くな」
  を明示し、`tools/stage_disk_by_digest.sh`の使用を指示する**（`m7ie`で
  委譲先の報告に実ファイル名が混入した経路。`m7gp`・`m7hj`に続く3度目だった）。

## 言えないこととして先に書いておくこと

- **代表位置は全位置ではない。** 9位置で漏れる可能性は残る。格上げの際に
  未測の位置数（6355）を明記するのはこのためである。
- **摂動は`XOR 0xFF`のみ**で、ビットの非対称は本稿でも埋まらない。
- **U3・U2が出ても「『9』の出所はROM内部である」とは主張しない。**
- run長や本数から元の値を逆算しない（禁止事項5）。
- 条件O・`disk#10`という1本のディスク・1条件である。一般性は主張しない。

## 結果ノート

結果は `docs/notes/m7iu-response-position-results.md` に書く。事前登録（本稿）の
代表位置・分類・判定規則・格上げ条件を後から動かさない。手順逸脱・事故は隠さず
開示節に書く。

## 禁止（本稿の測定中も例外なく適用）

- 公式ROMのバイト列を読まない・出力しない・保存しない。逆アセンブルしない。
- **公式ディスクのイメージを直接読まない**（D88のヘッダ・セクタ情報を含む）。
- 受信run・応答run・交換runのバイト値、FDCデータポート値、シリンダ値、PCN値を
  出力しない。出してよいのは件数・run長・位置番号・交換run番号・clock・
  **ビットマスクの指定値とモード名**・真偽値・rcのみ。
- **値を掃引・推論で復元しない。run長や本数から元の値を逆算しない。**
- 画面本文の生の行を報告・ノート・コミットメッセージ・ツール出力へ書かない
  （禁止事項7）。
- **公式ディスクの実ファイル名を展開して表示しない**（委譲先の報告を含む）。
- 第三者の逆アセンブルリスト・解析記事のコード断片を参照しない。

## 根拠リンク（`ls`で存在確認済み）

[m7is](m7is-response-direction-sweep-results.md)（本稿の出所。191arm、応答側の
位置の非対称という未閉、長さ1が25本で既に全位置を触っていること）・
[m7ir](m7ir-response-direction-sweep-preregistration.md)・
[m7iq](m7iq-early-exchange-allpos-results.md)（70arm、位置掃引の型）・
[m7ip](m7ip-early-exchange-allpos-preregistration.md)・
[m7io](m7io-early-exchange-sweep-results.md)・
[m7im](m7im-position5-results.md)（9arm）・
[m7ik](m7ik-cycle-request-correspondence-results.md)（12arm。合格条件3の照合先）・
[m7ii](m7ii-bit-flip-runlength-shape-results.md)（40arm）・
[m7ih](m7ih-bit-flip-runlength-shape-preregistration.md)（型の定義）・
[m7ie](m7ie-request-position-intervention-results.md)（`--exchange-intervention`が
`DIR_SUB_TO_MAIN`専用であることの確認、委譲先の実ファイル名混入の記録）・
[m7id](m7id-request-position-intervention-preregistration.md)（`--request-
intervention`の設計。本稿の拡張はこれと対になる）・
[m7il](m7il-position5-preregistration.md)（ディスク案の土俵が無いことの記録）・
[m7gp](m7gp-disk-name-leak-path-closed.md)（実ファイル名漏洩の経路を塞いだ稿）・
[m7hb](m7hb-consecutive-read-rule-results.md)（「9件×12周期」の構造）・
`docs/spec/l3-subrom.md` 1.36節・1.57節・3節（第145〜162版。第28版の書き方の
先例）・
`tools/analyze_error_exchange_shape.py`（`exchange_runs`）・
`tools/harness/frontend/main.c`（`--exchange-intervention`・
`--request-intervention`）・
`tools/harness/core/q88h_exchange_intervention.c`／`.h`（拡張対象）・
`tools/setup_harness.sh`（コアへの同期とビルド）・
`tools/compare_l3_entry_fdc.py`（`command_names`）・
`tools/recv_run_field_leak_selftest.sh`・
`tools/analyze_error_exchange_shape_selftest.sh`・
`tools/stage_disk_by_digest.sh`・`tools/check_cleanroom.sh`。
