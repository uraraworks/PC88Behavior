# m7gr: WRITE DATAのunit指定をドライブ選択ビットから作る修正の測定結果

実施日: 2026-09-04

## 位置づけ

[m7gq](m7gq-write-data-unit-fix-preregistration.md)が事前登録した案1を
`src/l3_service/make_subrom.py`の`FDC_WRITE_SECTOR`へ実装し
（コミット`8a4c815`）、事前登録の合格条件どおりに測定した結果である。
事前登録の合格条件・判定規則は測定後も動かしていない。

## 実装内容（再掲）

`FDC_WRITE_SECTOR`のunit/head組み立てに、`FDC_SEEK`入口（1.46節）と
同じ情報源・同じ取り出し方——`REQ_HDR+2`のアドレスをHLへ、
`LD A,(HL)`、`AND 1`——を追加し、既存の`WRITE_PREV2`由来のH<<2計算と
`OR`合成してから`FDC_OUT`へ渡す。`break_drive_selector`が真のとき
（陰性対照ビルド）は、この新しい合成を丸ごと無効化し、旧来の
「ドライブ0固定 | (H<<2)」へ戻す（1.46節の陰性対照が伝播を壊す方向と
揃えた。事前登録には break_drive_selector 時の扱いの明記が無かったため、
実装側でこう決め、ここに明記する）。使った命令はすべてZ80の定義済み
命令（`LD HL,nn`・`LD A,(HL)`・`AND n`・`LD E,A`・`OR E`）である。

## 容量関門（実装コミット前に確認済み、再掲）

全32構成（8構成×`PC88_BULK_READ_INTERVENTION_LIMIT`=1〜4）で`build()`が
`SystemExit`を出さないことを確認した（0件）。既定ビルド（LIMIT=4）は
2031→2039バイト（+8、事前登録の予測どおり）。修正前後でSHA-256が
相違することも確認した。`break_drive_selector`版（陰性対照）もビルド
できることを確認した。

## 測定条件

- A:起動ディスク・B:候補ディスク: `disk#8`（`650cfac8`、`m7gd`・
  `m7gn`・`m7go`・`m7gm`と同一ディスク）の使い捨て複製2本（別々の複製
  ファイル、それぞれライトプロテクトを解除）。`m7gn`・`m7go`と同一条件。
- 打鍵: `--type-at 300 --type '\n' --type-at 700 --type '10 PRINT
  "T"\nSAVE"<N>:TQ"\n'`（N=1またはN=2）、`--frames 4200`。`m7gn`・`m7go`
  と同一。
- ROM条件:
  - **条件O（公式一式）**: `PC88_REF_ROM_DIR`の`*.ROM`をそのままコピー
    しただけのディレクトリ。
  - **条件M（修正後の既定混成）**: `build_mixed_rom`で作る、公式main
    一式＋自作サブROM（探針引数なし＝既定ビルド、本稿の修正を含む）。
  - **条件B（陽性対照）**: `build_mixed_rom ... --break-drive-selector`
    （既存の故障注入）。
- 判定器材: `tools/compare_l3_entry_fdc.py --after-frame 700`・
  `tools/hash_write_stream.py`・`tools/check_l3_screen_output.py
  --compare-report`（いずれも`m7gn`・`m7go`と同一）。

## 陽性対照（最初に書く）

条件M（修正後の既定混成）と条件B（`--break-drive-selector`）を、同じ
`SAVE"2:TQ"`条件・同じB:候補（disk#8複製）で比較した。

- `compare_l3_entry_fdc.py --after-frame 700`の入口区間unit/head差件数:
  **55件**（0件より大きい）。

判定規則は修正後のコードに対しても、unit/headの違いを実際に検出できる
ことを確認した。**この陽性対照が通ったため、以下の「差なし」「差あり」
の判定を解釈する。**

## 判定規則の偽陽性チェック（ベースライン2run同士）

条件O・条件Mそれぞれについて、`SAVE"1:TQ"`・`SAVE"2:TQ"`の2run同士を
比較した。

| 条件 | unit/head差 |
|---|---|
| 条件O・`SAVE"1:"`（2run） | 差なし(0件) |
| 条件O・`SAVE"2:"`（2run） | 差なし(0件) |
| 条件M・`SAVE"1:"`（2run） | 差なし(0件) |
| 条件M・`SAVE"2:"`（2run） | 差なし(0件) |

FDCコマンド種別列もいずれも「なし（全長一致）」だった。判定規則は
ベースラインで偽陽性を作らない。

## 主指標: `SAVE"2:TQ"`条件でのWRITE DATA unit/head（条件O対条件M）

| 指標 | 条件O | 条件M（修正後） |
|---|---|---|
| FDCコマンド種別列 | 全長一致(124件) | 同左 |
| FDC WRITE DATA発行件数 | 8件 | **8件**（修正前は5件） |
| WRITE DATA unit/head分類 | `B/head0×1, B/head1×7` | `B/head0×1, B/head1×7`（**一致**） |
| SEEK/READ DATA/SENSE DRIVE STATUS unit/head | すべてB側 | すべてB側（一致） |
| 入口区間unit/head差件数 | — | **0件**（修正前は5件） |
| WRITEストリーム件数/バイト数 | 8件/2112バイト | 8件/2112バイト |
| WRITEストリームSHA-256 | — | **完全一致**（修正前は相違） |
| 画面出力 | `screen_compare=match` | 同左 |

2回目のrunでも同じ結果（unit/head差0件、コマンド種別列全長一致）が
再現した。**主指標は合格した。** WRITE DATAコマンド自身のunit/headが
公式と一致するようになり、WRITEストリームの内容（SHA-256）まで公式と
完全一致するようになった。これは事前登録の予測（主指標のみ一致）を
超え、末尾の書き込み内容そのものも一致した。

## 壊していないこと: `SAVE"1:TQ"`条件（条件O対条件M）

| 指標 | 条件O | 条件M（修正後） |
|---|---|---|
| FDCコマンド種別列 | 全長一致(124件) | 同左 |
| FDC WRITE DATA発行件数 | 8件 | 8件 |
| WRITE DATA unit/head分類 | `A/head0×1, A/head1×7` | `A/head0×1, A/head1×7`（一致） |
| 入口区間unit/head差件数 | — | **0件** |
| WRITEストリームSHA-256 | — | **完全一致**（修正前と同じく一致） |
| 画面出力 | `screen_compare=match` | 同左 |

2回目のrunでも同じ結果が再現した。`SAVE"1:.."`条件は修正前と同様、
公式との完全一致を維持している。**壊していないことを確認した。**

## 退行なし

`tools/conform_l3.sh`を実行した（`PC88_REF_ROM_DIR`・`PC88_REF_DISK_DIR`
を環境変数で指定）。適合条件2の判定に必要な`PC88_REF_DISKB`には、
`m7gd`が「L3サービスに入らない起動をする」と分類した既知のデータ
ディスク1本（`0cd0727b`。`650cfac8`とは別本、diskB専用の私物ではなく
`m7gg`の screening 結果から性質が一致するものを選んだ）を指定した。

- SKIP: **0件**。
- NG: 3件（すべて既知の検出力自己検査の陰性対照。「自己検査b/c/d」で、
  比較ロジック自体をわざと壊した入力に対して不一致を正しく検出できた
  ことを示すもので、失敗ではない）。
- OK: 434件。
- 判定: `conform_l3: 適合（このスクリプトが判定できる範囲）`

READ経路・起動区間は`conform_l3.sh`本体（適合条件1〜5、混成ROMの
I/Oストリーム照合、`RUN"file"`・`MERGE`・`BSAVE`等の需要入口測定）に
含まれており、いずれもOKだった。

## 決定論性

差の有無を問わず、`SAVE"1:TQ"`・`SAVE"2:TQ"`の各条件（条件O・条件Mとも）
を2runずつ実施し、両runで同じunit/head分類・同じFDCコマンド種別列・
同じWRITEストリームSHA-256が再現することを確認した。陽性対照
（`--break-drive-selector`）は`m7go`と同様、既存スクリプトが決定論性を
検証済みの既知の故障注入であるため1runのみ実施した。

## 元ディスクを壊さない

全複製は`scratchpad`配下（リポジトリ外）に作成し、`private/`配下へは
書き込んでいない。複製元ディスク（`650cfac8`）のSHA-256は、全測定
終了後に確認し、測定前と不変であることを確認した
（`ORIG_UNCHANGED=yes`）。`stage_disk_by_digest.sh`が作った使い捨て
複製2本（A:・B:それぞれのステージング元）のSHA-256も、全測定前後で
不変だった（`STAGED_UNCHANGED=yes`）。

## 修正後サブROMの取り違え防止

`build_mixed_rom`が出す混成ROMディレクトリ内のサブROM（`DISK.ROM`）の
SHA-256は、実装コミット直後に容量関門確認で得た既定ビルド（LIMIT=4）の
値と一致することを確認した。`--break-drive-selector`版は既定ビルドと
異なるSHAになることも確認した（意図した相違）。

## F1〜F4のどれか（事前登録の枠に沿った判定）

- **F3**（主指標が通らない）: 不成立。主指標は通った。
- **F4**（容量関門に落ちる）: 不成立。32構成すべて通過した。
- **F2**（主指標は通るが`SAVE"1:"`条件が変わる）: 不成立。`SAVE"1:"`
  条件は修正前と同じく公式と完全一致した。
- **F1**（主指標が通り、`SAVE"1:"`条件も不変）: **成立。採用。**

## 言えること・言えないこと

**言えること:**

- `SAVE"2:TQ"`（B:へ保存）条件で、修正後の自作サブROMはWRITE DATAコマンド
  自身のunit/headを公式と一致させ（`B/head0×1, B/head1×7`）、
  WRITEストリームの内容（SHA-256、8件/2112バイト）まで公式と完全一致
  させた。これは2回の独立測定で再現した。
- `SAVE"1:TQ"`（A:へ保存）条件は、修正前と同様、WRITE DATA unit/headを
  含め公式との完全一致を維持した。
- `tools/conform_l3.sh`はSKIP 0件で「適合」判定を維持し、退行は見られ
  なかった。

**言えないこと（本稿では測っていない範囲）:**

- `disk#8`以外のB:候補（`m7gg`の残り候補群）でも同じ結果が出るかは
  未確認。
- B:へのSAVEを含む条件のすべての打鍵パターン（ファイル名の長さ、
  複数ファイルの連続SAVE、SAVE中のエラー条件等）は測っていない。
- `SAVE"1:"`・`SAVE"2:"`以外のドライブ指定構文（相対パス、`FILES`との
  組み合わせ等）でのWRITE DATA unit/headは測っていない。
- **本稿の一致（F1）をもって「公式サブROMのWRITE経路すべてに一致した」
  とは言えない。** 測ったのは`SAVE"1:TQ"`・`SAVE"2:TQ"`という単一の
  打鍵パターン、単一のB:候補ディスクに対する結果である。

## 検証

`tools/check_cleanroom.sh`は全項目OK、rc=0。`git status`で`private/`
由来の混入・生ログ・ROM像・ディスク複製が無いことを確認した。生ログ・
混成/公式ROM一式・ディスク複製はリポジトリ外（scratchpad配下）に置き、
コミットしていない。測定はすべてフォアグラウンドで実行し、測定中に
`git stash`・ブランチ切替・ファイル編集は行っていない。

## 情報境界 / 根拠リンク

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容は、成果物には含めていない。記録したのは公開FDCコマンド種別名、
件数、一致prefix件数、unit/head分類名、画面出力の行数・文字数・
SHA-256、WRITEストリームの件数・バイト数・SHA-256、rc、
`conform_l3.sh`のOK/NG/SKIP件数、ディスクの通し番号・ダイジェスト
だけである。

根拠（`ls`で存在確認済み）:
[m7gq](m7gq-write-data-unit-fix-preregistration.md)・
[m7go](m7go-write-data-unit-results.md)・
[m7gn](m7gn-write-data-unit-preregistration.md)・
[m7gm](m7gm-write-path-drive-axis-results.md)・
[m7gl](m7gl-write-path-drive-axis-preregistration.md)・
[m7gk](m7gk-save-drive-syntax.md)・
[m7gg](m7gg-data-disk-screening.md)（B:候補の性質確認）・
[m7gd](m7gd-boot-disk-screening.md)（disk#8・diskB相当の分類の出所）・
[m7gp](m7gp-disk-name-leak-path-closed.md)（`stage_disk_by_digest.sh`）・
`docs/spec/l3-subrom.md` 1.35節・1.46節・1.56節・
自作`src/l3_service/make_subrom.py`（`FDC_WRITE_SECTOR`、コミット
`8a4c815`）・`tools/lib_l3_measure.sh`（`build_mixed_rom`・
`run_q88measure_retry`）・`tools/compare_l3_entry_fdc.py`・
`tools/hash_write_stream.py`・`tools/check_l3_screen_output.py`・
`tools/stage_disk_by_digest.sh`・`tools/conform_l3.sh`・
`tools/check_cleanroom.sh`。
