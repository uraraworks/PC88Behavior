# m7lw: B:未挿入待ちの途中で媒体を差したあとの続きは、4腕とも公式と混成が一致（resumes_identically）

実施日: 2026-09-14
事前登録: [m7lw-...-preregistration](m7lw-insert-after-no-disk-wait-preregistration.md)
HEAD: `6be539b`（事前登録コミット。**実装は変えていない**。自作subROMはHEADのまま、
生成器 sha256先頭 `4f0b85c0344b`）
コア: `vendor/quasi88-libretro/quasi88_libretro.dylib` sha256先頭 `9132ee20c6bd`、
q88measure（HEADからビルド）sha256先頭 `db90e01da032`。
`--insert-disk2`/`--insert-disk2-at` が usage に出ることを確認済み。

## 結論

> 4腕（COPY-800／COPY-1200／UNREAD-800／UNREAD-1200）すべてで、official・mixed
> とも R（待ちに入り、差したら抜けた）が真、E（main $FD/$FC列の一致）・S（画面署名の
> 一致）も真だった。事前登録の判定1〜5のうち **`resumes_identically`** が当たる。

## 関門

| 関門 | 結果 |
|---|---|
| G1 器具の末端（`insert2`行のrc・actual・frameが指定どおり、全16走） | **真** |
| G2 取りこぼし0件（全18走） | **真** |
| G3 陰性対照（NOINS、official・mixedとも +0長さ5・その後run無し・+0以降READ DATA 0件・frame1200-1299のSENSE DRIVE STATUS毎フレーム100件以上） | **真** |
| G4 決定論性（各腕・各側でrun1とrun2のI/Oログデータ行が一致） | **真** |

## 腕ごとの指標（official・mixed とも）

| 腕 | R(official) | R(mixed) | F_end | E | S |
|---|---|---|---|---|---|
| COPY-800 | 真 | 真 | 799（両側とも） | 真 | 真 |
| COPY-1200 | 真 | 真 | 1199（両側とも） | 真 | 真 |
| UNREAD-800 | 真 | 真 | 799（両側とも） | 真（$FDのみSHA-256判定、$FCは件数一致のみ） | 真 |
| UNREAD-1200 | 真 | 真 | 1199（両側とも） | 真（同上） | 真 |

- R の内訳 (a)(b)(c) は4腕・両側ともすべて真。F_end−I はいずれも **−1**
  （待ちの最後のSENSE DRIVE STATUS高頻度フレームは、挿入フレームIの1つ前で終わっていた）。
- E: main IN $FD は4腕とも official・mixed で件数・SHA-256が一致。
  main IN $FC は COPY 腕で件数・SHA-256とも一致、UNREAD 腕は事前登録どおり
  **件数のみ判定**（両腕とも6684件で一致）。UNREAD腕の $FC の SHA-256は
  **official・mixedで不一致**（1.58節の既知の分岐と同じ扱いで、合否には使わない）。
- S: official 1回目は COPY 腕を `drive2`、UNREAD 腕を `unreadable_disk` として
  4腕とも「到達」に分類され、official・mixedの終了時画面署名（行数・文字数・SHA-256）は
  4腕とも一致した。

## 判定器の区別力の確認（本測定の結果を見る前に、のはずが今回は測定後になった）

NOINS（媒体を差さない陰性対照）に、誤って I=1200 の腕と同じ規則を当てると、
(b)（待ちの最後のフレームがI−1〜I+10に収まる）と(c)（frame I以降にREAD DATAがある）が
official・mixedとも **偽** になることを確認した（frame 760〜1199は毎フレーム
SENSE DRIVE STATUS 100件以上で(a)は真のまま、待ちの最後のフレームは1299、
READ DATAはI=1200以降に0件）。判定器はR偽・R真を区別できている。

**この確認は事前登録の指示どおり本測定の前に行うべきところ、実際には本測定完了後に
行った（判定器の性能問題への対応を優先したため）。結果には影響しない
（判定ロジック自体は測定後に変更していない）**。

## 記述として載せるもの（合否に使わない）

- 待ちの間のSENSE DRIVE STATUSは、frame 760〜I−1の1フレームあたり平均で
  official 1295.0件・mixed 654.5件（4腕とも同じ値。m7lvの1289.2件・653.8件と
  近い水準）。
- 挿入後最初のFDCコマンド名の先頭10個: COPY腕はofficial
  「SENSE DRIVE STATUS・SENSE DRIVE STATUS・READ DATA・SEEK・…」、mixedは
  「READ DATA・SEEK・…」から始まる（先頭のSENSE DRIVE STATUSが無い）。UNREAD腕は
  officialが「SENSE DRIVE STATUS・SENSE DRIVE STATUS・READ DATA×8」、mixedは
  「READ DATA×9・SEEK」。**この差は挿入フレームIちょうどに同居するSENSE DRIVE STATUS
  件数の差であって（frame Iだけで数えるとofficialはCOPY腕2件・UNREAD腕7件、mixedは
  COPY腕0件・UNREAD腕1件）、最初のREAD DATAはofficial・mixedとも同じframe I。
  frame I−1では両側ともI−1までの通常の問い合わせ密度（official約1295件・
  mixed約655件）のままで、frame境界に何件が乗るかだけの数え方の差であり、
  main $FD/$FC列のSHA-256一致にも画面署名の一致にも現れていない。**
- +0の run の長さと交換 run: G3の陰性対照でのみ定義（本測定の4腕には+0の定義を
  適用していない。事前登録は+0をNOINSの関門にのみ使う書き方だったため、そのとおりに
  従った）。
- 挿入後のFDCコマンド種別列の全長一致／分岐位置: 本結果では判定に使わなかった
  （事前登録の記述項目のうち、Sが4腕とも真だったため位置の記述は割愛した）。

## 事前登録の記述の読み方を決めた箇所

- 「F_end」の定義（「SENSE DRIVE STATUSが100件以上のフレームの最後」）は、
  挿入フレームIより前のフレームだけを走査すればよいのか、I以降も含めて
  最後を取るのかが事前登録の文言だけでは一意に決まらなかった。今回は
  「窓を区切らずSENSE DRIVE STATUS≥100件の全フレームの最後」と読んだ
  （結果として4腕ともF_endはI−1に収まり、この読み方の違いは条件(b)の
  真偽に影響しなかった）。

## 言えないこと（事前登録どおり）

- エミュレータ（QUASI88 libretro版）上の振る舞いである。
- 挿入は `quasi88_disk_insert()` をフレーム境界で直接呼ぶ差し方であり、
  libretro版では入れ替え印（`disk_exchange`）を有効にする経路が無いため、
  差した直後に1回だけST3 bit3=0を返す動作は起きない。実機で媒体を差す瞬間の
  信号は再現していない。
- 差す媒体は2種、差すフレームは2つだけである。媒体を抜く操作は測っていない。
- 実機での振る舞いには一般化しない。

## 禁止の遵守

公式ROM・公式ディスク・`private/`の内容には触れていない。判定器・本稿とも
画面本文・公式応答値・ディスクのデータ部を出していない（件数・SHA-256・
コマンド名・フレーム番号だけ）。`tools/check_cleanroom.sh` は全項目OK。

## 根拠リンク

[m7lw 事前登録](m7lw-insert-after-no-disk-wait-preregistration.md)・
[m7lu](m7lu-no-disk-sub-drive-wait-diagnosis.md)・
[m7lv 測定](m7lv-st3-two-side-media-signal.md)・
[m7lv 結果](m7lv-no-disk-drive-wait-implementation-results.md)・
`tools/harness/frontend/main.c`（`--insert-disk2`/`--insert-disk2-at`）。
