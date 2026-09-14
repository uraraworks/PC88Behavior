# m7lw — B:媒体未挿入の待ちの途中で媒体を差したあとの続きを、公式と混成で比べる — 事前登録

## 位置づけ

- [m7lu](m7lu-no-disk-sub-drive-wait-diagnosis.md)（1.62節）: 公式subは、B:に媒体が無いまま
  一般READ要求（長さ5）を受けると、SENSE DRIVE STATUSを繰り返して媒体の挿入を待つ。
- [m7lv](m7lv-no-disk-drive-wait-implementation-results.md)（1.63節）: 自作subにも同じ待ちを
  入れ、no_diskの画面が公式と一致した。採用の理由は「媒体を差せば進む」ことだったが、
  **差したあとの続き（再アーム・6バイト目以降）は測れていない**（途中で媒体を差す器具が
  無かった）と m7lv の「言えないこと」に書いた。
- 本稿はその穴を埋める。器具は q88measure の `--insert-disk2` / `--insert-disk2-at`
  （コミット `db293af`。挿入直後に `filename_get_disk(1)` が指定パスを返すことを末端で
  確かめ、挿入関数を呼ばない故障注入版がそこで落ちることを自己検査で確認済み）。

**実装は変えない。** 自作サブROMは HEAD（生成器 sha `4f0b85c0344b`）のまま測る。

## 場面

- ROM: 公式一式（official）／公式main＋自作sub（mixed、`build_mixed_rom`）。
- A: 参照用ディスク（適合テストの diskA と同じもの）の使い捨て複製。B: 起動時は空。
- 打鍵: `--type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n'`（適合テストの no_disk と同じ）。
- `--frames 4000`。B:へ差す媒体とフレーム（腕）は次の2×2:

| 腕 | 差す媒体 | 差すフレーム I |
|---|---|---|
| COPY-800 | A:と同じ参照用ディスクの別の使い捨て複製（適合テストの drive2 の B:と同じ作り方） | 800 |
| COPY-1200 | 同上 | 1200 |
| UNREAD-800 | `tools/make_l3_testdisk.py` の引数なしの生成物（適合テストの unreadable_disk の B:と同じ） | 800 |
| UNREAD-1200 | 同上 | 1200 |

- 各腕を official 2回・mixed 2回走らせる。
- 陰性対照 NOINS: 媒体を差さず `--frames 1300`、official・mixed 各1回。

## 関門（1つでも偽なら `gate_failed`。判定しない）

- G1 器具の末端: 挿入のある全走で、`--out` レポートの `insert2` 行が成功を示し、
  `actual` が指定したパスである。
- G2 取りこぼし: 全走で I/Oログの取りこぼし0件。
- G3 陰性対照: NOINS の official・mixed とも、+0（frame 700以降で最初の main→sub run）の
  長さが5、+0の後の交換runが0本、+0以降の READ DATA が0件、frame 1200〜1299 の各フレームで
  SENSE DRIVE STATUS が100件以上（＝挿入が無ければ待ちの終わりの検出器は発火しない）。
- G4 決定論性: 各腕の official 2回どうし、mixed 2回どうしで、I/Oログのデータ行
  （見出し行を除く）が一致する。

## 腕ごとの指標（official・mixed それぞれ）

- R（待ちに入り、差したら抜けた）: 次の3つがすべて真。
  (a) frame 760〜I−1 のすべてのフレームで SENSE DRIVE STATUS が100件以上（待ちに入っていた）。
  (b) SENSE DRIVE STATUS が100件以上のフレームの最後を F_end とすると、I−1 ≦ F_end ≦ I+10。
  (c) frame I 以降に READ DATA が1件以上ある。
- E（mainの末端）: official 1回目と mixed 1回目で、main `IN $FD` 列と main `IN $FC` 列の
  件数・SHA-256 が一致する。**ただし UNREAD 腕では `IN $FC` は件数の一致だけを求め、
  SHA-256 は記述に回す**（1.58節で、読めない媒体への9件後の応答値は合否に使わないと決めて
  あるため。適合テストの `B:規則生成媒体: main IN $FCは分岐（同件数）` と同じ扱い）。
- S（画面）: `tools/check_l3_entry_screen.py` が official 1回目のレポートを、COPY腕は
  `--scenario drive2`、UNREAD腕は `--scenario unreadable_disk` で「到達」と分類し、かつ
  official 1回目と mixed 1回目の終了時画面署名（`tools/check_l3_screen_output.py` の
  行数・文字数・SHA-256）が一致する。official が到達と分類されない腕は S を「判定不能」とする。

## 判定（関門がすべて真のとき、4腕を通して1つ）

1. `resumes_identically`: 4腕すべてで official・mixed とも R が真、E と S が真。
   → 実装は変えない。仕様に新節（1.64節）を置き「差したあとの続きは公式と一致」と記す。
   適合テストに場面を足すかは人間が決める。
2. `mixed_keeps_waiting`: official の R が真で mixed の R が偽の腕が1つ以上ある。
   → 自作subの待ちの終わり検出の不具合。修正は別の事前登録で行う。
3. `official_keeps_waiting`: official の R が偽の腕が1つ以上ある（mixed の真偽は問わない）。
   → 公式は差しても（このエミュの差し方では）抜けない。記述し、進め方は人間が決める。
4. `resumes_differently`: 4腕すべてで official・mixed とも R が真だが、E か S が偽の腕が
   1つ以上ある。→ 最初の食い違いの位置を記述し、次は診断（別の事前登録）。
5. `inconclusive`: 上のいずれにも当たらない（S が判定不能の腕がある等）。

判定1〜5の順に当てはめ、最初に当たったものを採る。

## 記述として載せるもの（合否に使わない）

- 腕ごと・側ごとの F_end − I（差してから待ちを抜けるまでのフレーム数）。
- 挿入後最初の FDC コマンド名の先頭10個（名前と unit/head だけ）。
- +0 の run の長さと、+0 以降の交換 run の長さの列（件数だけ）。
- 挿入後の FDC コマンド種別列が全長一致するか、しないなら最初の分岐位置
  （`tools/compare_l3_entry_fdc.py` の位置と分類だけ）。
- 待ちの間の SENSE DRIVE STATUS の1フレームあたり件数（m7lv では公式1289・自作654）。
- UNREAD 腕の main `IN $FC` の SHA-256 が一致したかどうか。

## 言えないこととして先に書いておくこと

- **エミュレータ（QUASI88 libretro版）上の振る舞いである。**
- 挿入は `quasi88_disk_insert()` をフレームの境目で直接呼ぶ差し方である。libretro版では
  libretro層が `config_init()` を呼ばず、入れ替え印（`disk_exchange`）を有効にする経路が無いため、
  **差した直後に1回だけ ST3 bit3=0 を返す動作は起きない**（差した次の SENSE DRIVE STATUS から bit3=1）。実機で媒体を差す瞬間の
  ドライブの信号（入れ替え直後の状態変化など）は再現していない。
- 差す媒体は2種、差すフレームは2つだけである。媒体を抜く操作は測らない。
- 実機での振る舞いには一般化しない。

## 結果ノート

`docs/notes/m7lw-insert-after-no-disk-wait-results.md` に書く。関門・指標・判定と
数え方を後から動かさない。画面本文・公式の応答値・ディスクのデータ部は書かない
（件数・SHA-256・コマンド名・位置だけ）。

## 根拠リンク

[m7lu](m7lu-no-disk-sub-drive-wait-diagnosis.md)・
[m7lv 測定](m7lv-st3-two-side-media-signal.md)・
[m7lv 結果](m7lv-no-disk-drive-wait-implementation-results.md)・
`vendor/quasi88-libretro` の `src/quasi88.c`（`quasi88_disk_insert`）と `src/fdc.c`
（入れ替え印・SENSE DEVICE STATUS の ST3 生成）。
