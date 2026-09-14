# l4-s1c — 属性の値の意味と、白黒モードで属性が変わらなかった理由 — 事前登録

記録日: 2026-09-15
状態: 事前登録、測定前

## 位置づけ

l4-s1a（`b29bc85`、結果ノート `docs/notes/l4-s1a-text-vram-results.md`）は
属性域40バイトが (位置バイト, 値バイト) の対×20組であることを判定したが、値の
意味は測っていない。また同ノート末尾の訂正の追記に、次の2点が未解釈のまま
残っている:

- A3m（白黒モード、`CONSOLE ,,,0:COLOR n:PRINT "Q7Z"`）でn=0〜7の8通りとも
  属性域の並びが同一だった。
- A3m・A3cで目印の件数が腕により1件と2件に分かれた（エコーと印字を合わせて
  2件になるのが見込みだった）。

本測定はこの2点と、カラーモードでの値バイトの決まり方を測る。
**実装は行わない。測定のみ。**

## 問い

- Q1 モード: 起動直後の既定のテキストモードはカラーか白黒か。`CONSOLE ,,,0`
  ／`,,,1` を打つと、画面は消えるか（エコー行が残るか）。
- Q2 白黒モードの値: 白黒モードで `COLOR n`（マニュアル2-29: 0ノーマル／
  1シークレット／2ブリンク／3=1／4リバース／5リバース・シークレット／
  6リバース・ブリンク／7=5）を指定して印字したとき、印字した区間の値バイトは
  何か。8通りで同じなら、その理由の候補（COLORの第1引数が白黒モードでは別の
  意味を持つ、CONSOLEの指定が効いていない、等）を腕で切り分ける。
- Q3 カラーモードの値: `COLOR n`（0〜7）で値バイトがどう決まるか（l4-s1aの
  記述では0x20刻み）。n=7（白）が既定の並びと区別できない理由（既定色が白で
  対を置かない、が候補）。
- Q4 件数の揺れ: A3m・A3c相当の条件で、打鍵の各段階（CONSOLEを打った直後／
  COLORを打った直後／PRINTの後）の目印の件数。

## 条件

- 公式ROM一式、ディスク無し、既定のBASICモード（コア既定N88 V2）、既定のDIP。
  l4-s1aと同条件。
- 目印: `q7z`（追補2で確定した表記。q88measureの打鍵注入は英字をシフト無しで
  小文字として送るため、`--type`にも小文字で書く）。打鍵は英数・記号・改行の
  みで、l4-s1aで実際に使えたもの（`console`・`color`・`print`・カンマ・
  コロン・引用符・数字）だけを使う。
- 読んだマニュアルの頁: l4-s1aと同じ（2-29〜2-30 COLOR、2-39 CONSOLE、
  出所は `refs/manual_squashed.txt`）。

### 打鍵と走行フレームの決め方

- 起動settle: l4-s1aと同じ `--type-at 300 --type '\n'`。
- 実コマンドの打鍵開始: l4-s1aと同じ `--type-at 700`。
  根拠: `tools/conform_l3.sh` の全シナリオが採る値をそのまま流用する
  （l4-s1a事前登録の踏襲）。
- `--mem-write-from-frame 700`。打鍵開始フレームと一致させる。
- `--key-hold` / `--key-gap` は指定せず、`tools/harness/frontend/main.c` の
  既定値（各4フレーム）を使う。`schedule_typing()`（同ファイル302〜341行）
  の実装により、1文字（`\n`も1文字として数える）ごとに `hold+gap=8` フレーム
  進む。これは l4-s1a が使った値と同じ。

#### 各行の完了フレームの計算式

1行にまとめず、**命令ごとに行を分けて打ち**（下記「腕」参照）、1つの
`--type` に複数行を `\n` 区切りで並べる。各行の完了フレームは

```
line_end(k) = 700 + 8 * (その行までに打った文字数の累計、\nも1文字)
dump(k)     = line_end(k) + 20   （実行の余裕。根拠は次段落）
```

で決める。実行の余裕を20フレームとする根拠: l4-s1aのA4（スクロール）観測で、
`PRINT "q7z"` 1行（12文字、96フレーム）を26回連続で打った際のスクロール
発生間隔が96フレーム＝純粋な打鍵時間と一致しており、COLOR/CONSOLE/PRINTの
ような磁気ディスクI/Oを伴わないコマンドの実行自体には目立った追加フレームが
掛かっていないと読める。したがって20フレーム（次の行の2〜3文字目を打っている
頃）の余裕で実行完了後の状態を捉えられると見込む。なお各行の打鍵エコーは
実行後に自動で次の行（次のY座標）へ送られるため、次の行の打鍵が始まっていても
既に確定した行（前の行）のVRAM内容を上書きしない。

行ごとの文字数（`\n`込み）:
- `console ,,,0\n` / `console ,,,1\n`: 13文字
- `color n\n`（nは1桁）: 8文字
- `print "q7z"\n`: 12文字
- 結合行 `console ,,,M:color n:print "q7z"\n`: 33文字

これから各腕の完了フレームは:

| 行 | 累計文字数 | line_end | dump |
|---|---|---|---|
| B0: color n | 8 | 764 | 784 |
| B0: print | 20 | 860 | 880 |
| B1/B2: console | 13 | 804 | 824 |
| B1/B2: color n | 21 | 868 | 888 |
| B1/B2: print | 33 | 964 | 984 |
| B3: 結合行（33文字） | 33 | 964 | 984 |

- 走行フレーム数: 全腕共通で `--frames 1200`。最後の写し（984）＋200以上
  ある（「最後の写し＋100以上」の条件を満たす）。全腕がSと呼べる規模
  （最大33文字）で揃うため、l4-s1aのようなグループ分けはしない。
- 各腕は2回走らせる（G3）。乱数要因は無いため同一の打鍵列を再実行するだけ。

### 腕

- **B0** 既定（CONSOLEを打たない）、n=0〜7の8腕:
  `--type-at 700 --type 'color n\nprint "q7z"\n'`
  写し: `--vram-dump-at 784`（colorの後）・`--vram-dump-at 880`（printの後）
- **B1** 白黒、n=0〜7の8腕:
  `--type-at 700 --type 'console ,,,0\ncolor n\nprint "q7z"\n'`
  写し: `--vram-dump-at 824`（consoleの後）・`888`（colorの後）・`984`
  （printの後）
- **B2** カラー、n=0〜7の8腕:
  `--type-at 700 --type 'console ,,,1\ncolor n\nprint "q7z"\n'`
  写し: B1と同じ3フレーム（824・888・984）
- **B3** 同じ行で（l4-s1aのA3m/A3cの再現）、n=0,4,7 × モード{白黒,カラー}の
  6腕:
  `--type-at 700 --type 'console ,,,0:color n:print "q7z"\n'`（白黒、n=0,4,7）
  `--type-at 700 --type 'console ,,,1:color n:print "q7z"\n'`（カラー、n=0,4,7）
  写し: `--vram-dump-at 984`（結合行の後、1回のみ。l4-s1aの1行仕様の再現が
  目的なので途中の写しは取らない）

腕の総数: B0(8) + B1(8) + B2(8) + B3(6) = 30腕。

- 採るもの: l4-s1aと同じ一式。
  - `--vram-dump PATH --vram-dump-at F` を腕ごとの写し枚数ぶん指定（複数指定
    で出力ファイル名に `.fNNNNNN` が付く。コミット `04201be`）。
  - `--mem-write-log PATH --mem-write-range 0xF3C8-0xFF7F
    --mem-write-from-frame 700`。
  - `--io-log`。
  - 解析は `tools/l4_vram_probe.py`。既存モード（目印の位置・目印行の属性域）
    に加え、差分モード（`--diff-before`/`--diff-after`、コミット`02035a4`）で
    段階間（console後→color後、color後→print後）のVRAM変化バイトを見る
    （Q1の画面消去・Q4の件数変化の切り分けに使う）。

## 関門

- G1 器具: 測定時HEADで `vram_dump_selftest.sh`・`vram_dump_dynamic_selftest.sh`・
  `mem_write_log_selftest.sh`・`mem_write_pc_selftest.sh` がOK
  （l4-s1aと同じ一式）。
- G2 取りこぼし0（`mem-write-log`・`iolog`とも）。stderrの「打てない文字」
  警告が0件。
- G3 決定論性: 各腕2回で、各写しファイルのsha256がrun1=run2で一致し、
  `mem-write-log`・`iolog`のデータ行（見出し除く）のsha256も一致する。
- G4 陰性対照: A0相当（何も打たない、settleの`\n`のみ）を1腕追加して走らせ、
  目印`q7z`のセルが0件。
- G5 起点: 解析道具の出力見出しが`origin=0`、同じHEADの
  `screen_content_leak_selftest.sh`のf2・f2nがOK。
- G6 本文漏れ: 同じHEADで`screen_content_leak_selftest.sh`全項目OK。
- G7 再現: B3のn=0,4,7で、l4-s1aのA3m・A3cと同じ属性域の並びが出る
  （l4-s1aの記述の値と結果ノートの範囲で照合）。目印件数もl4-s1a時点の記録
  （A3m・A3cでは印字結果のみ1〜2件、との記述）と付き合わせる。一致しなければ
  「再現せず」として記録し、Q4の解釈を保留する。

## 判定

- Q1: `default_color`／`default_mono`（B0のn=0時点、あるいは既定モードでの
  印字結果の属性値がB2のカラー既定値・B1の白黒既定値のどちらに近いかで
  判定）。CONSOLE直後の差分モードの結果から、`,,,0`／`,,,1`それぞれについて
  `clears_screen`／`keeps_screen`。
- Q2: 白黒8通りの値バイトの表（記述）と、`mono_codes_distinct`（8通りで値
  バイトが区別できる）／`mono_codes_identical`（区別できない場合はB1の
  console後・color後の差分モードの結果を根拠に、CONSOLE非反映かCOLOR無反映
  かを`console_ineffective`／`color_ineffective`／`inconclusive`で追記）。
- Q3: カラー各nの値バイトの表（記述）と、`color_step_0x20`／`other`。n=7の
  値が既定（B0・console無し）の値と一致するかどうかを付記する。
- Q4: B1・B2・B3それぞれの段階（console後／color後／print後）ごとの目印件数
  の表（記述）と、揺れが確認できた場合は`explained_by_stage`（どの段階で
  1件→2件に変わるかが特定できた）／`not_explained`。

判定後の行き先: 仕様書 `docs/spec/l3-main.md` へ観測として追記する
（l4-s1aの判定と同じ仕様書。実装は別担当が仕様書だけを見て行う）。

## 本文を出さない

l4-s1aと同じ取り扱い（禁止事項7）:

- 写し・記録・iologは使い捨ての作業ディレクトリ（リポジトリ外）に置き、
  結果ノートを書いたら削除する。
- 解析道具が出してよいもの／出してはいけないものはl4-s1aの事前登録と同じ。
- 解析道具は`screen_content_leak_selftest.sh`の対象に加え、陰性対照つきで
  本文が漏れないことを確かめてから使う（G1・G6）。

## 結果ノート

`docs/notes/l4-s1c-attribute-values-results.md` に書く。関門・指標・判定と
数え方を後から動かさない。

## 根拠リンク

[l4-s1a-text-vram-preregistration](l4-s1a-text-vram-preregistration.md)・
[l4-s1a-text-vram-results](l4-s1a-text-vram-results.md)（属性域が(位置,値)×20組
であることの判定、A3m・A3cの未解釈点の記録、番地の式
`addr = 0xF3C8 + row0*120 + col0`）・
[l4-s1a-text-vram-preregistration-addendum2](l4-s1a-text-vram-preregistration-addendum2.md)
（`8aeb8f5`、目印を`q7z`に改めた経緯）・
`tools/harness/frontend/main.c`
（`schedule_typing()` 302〜341行、`--key-hold`/`--key-gap`既定値、
`--vram-dump`/`--vram-dump-at`複数指定）・
コミット`04201be`（`--vram-dump`/`--mem-write-log`）・
コミット`02035a4`（`tools/l4_vram_probe.py`差分モード）・
`refs/manual_squashed.txt` 2-29〜2-30・2-39。
