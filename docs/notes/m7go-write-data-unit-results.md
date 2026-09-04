# m7go: WRITE DATAコマンド自身のunitを公式と比較した結果

実施日: 2026-09-04

## 位置づけ

[m7gn](m7gn-write-data-unit-preregistration.md)が事前登録した測定の結果
である。`src/`・`tools/`はいずれも変更していない。事前登録した合格条件・
判定規則は測定後も動かしていない。探針（`--probe-site`）は使わず、
公式一式（条件O）と既定の混成ROM（条件M、探針引数なし）だけを比較した。

測定: `SAVE"2:.."`（B:へ保存）条件で、**公式サブROMはWRITE DATAコマンド
自身をB側で発行するが、自作サブROMはA側のまま**だった。`SAVE"1:.."`
（A:へ保存）条件では両者は完全に一致した。

## 陽性対照（最初に書く）

`tools/verify_drive_byte2_attribution.sh`と同じ考え方で、既定の混成ROM
（条件M）と`build_mixed_rom ... --break-drive-selector`（1.46節のドライブ
指定伝播を壊す既存の故障注入）を、同じ`SAVE"2:TQ"`条件・同じB:候補
（disk#8複製）で比較した。

- `compare_l3_entry_fdc.py --after-frame 700`の入口区間unit/head差件数:
  **32件**（0件より大きい）。

判定規則がunit/headの違いを実際に検出できることを確認した。**この陽性
対照が通ったため、以下の「差なし」「差あり」の判定を解釈する。**

## 判定規則の偽陽性チェック（ベースライン2run同士）

条件O・条件Mそれぞれについて、`SAVE"1:TQ"`・`SAVE"2:TQ"`の2run同士を
比較した。

| 条件 | FDCコマンド種別列 | ポート値列 | unit/head差 |
|---|---|---|---|
| 条件O・`SAVE"1:"`（2run） | 全長一致(124件) | 完全一致(18894件) | 差なし(0件) |
| 条件O・`SAVE"2:"`（2run） | 全長一致(124件) | 完全一致(18894件) | 差なし(0件) |
| 条件M・`SAVE"1:"`（2run） | 全長一致(124件) | 完全一致(18894件) | 差なし(0件) |
| 条件M・`SAVE"2:"`（2run） | 全長一致(100件) | 完全一致(16945件) | 差なし(0件) |

画面出力（`check_l3_screen_output.py --compare-report`）もすべて
`screen_compare=match`だった。判定規則はベースラインで偽陽性を作らない。

## 主指標: 条件O対条件M（WRITE DATAコマンド自身のunit/head）

### `SAVE"1:TQ"`（A:へ保存）

| 指標 | 条件O | 条件M |
|---|---|---|
| FDCコマンド種別列 | 全長一致(124件) | 同左 |
| FDCポート値列一致prefix | 1件（先頭SPECIFYパラメータで相違、後述） | 同左 |
| WRITE DATA unit/head分類 | `A/head0×1, A/head1×7` | `A/head0×1, A/head1×7`（**一致**） |
| SEEK/READ DATA/SENSE DRIVE STATUS unit/head | すべてA側 | すべてA側（**一致**） |
| unit/head差件数 | 0件 | 同左 |
| WRITEストリーム | 8件/2112バイト | 8件/2112バイト、**SHA-256完全一致** |
| 画面出力 | `screen_compare=match` | 同左 |

`SAVE"1:.."`条件では、WRITE DATA自身のunit/headを含め、入口区間の
unit/head分類が公式・自作で完全に一致した。

### `SAVE"2:TQ"`（B:へ保存）— 2run実施、両方で再現

| 指標 | 条件O | 条件M |
|---|---|---|
| FDCコマンド種別列 総件数 | 124件 | 100件（混成列が先に終端） |
| WRITE DATA発行件数 | 8件 | 5件 |
| WRITE DATA unit/head分類 | **`B/head0×1, B/head1×7`** | **`A/head0×1, A/head1×4`** |
| SEEK unit/head分類 | `B/head0×18` | `B/head0×12` |
| SENSE DRIVE STATUS unit/head分類 | `B/head0×19` | `B/head0×13` |
| READ DATA unit/head分類 | `B/head1×10` | `B/head1×7` |
| unit/head差件数 | — | **5件**（最初の差: コマンド33件目WRITE DATA、公式=B/head1、混成=A/head1） |
| WRITEストリーム | 8件/2112バイト | 5件/1064バイト、**SHA-256相違** |
| 画面出力 | `screen_compare=match`（1・2両条件とも一致） | 同左 |

2回目のrun（`off_s2_r2`対`mix_s2_r2`）でも同じ分類・同じ差件数（5件）が
再現した。

## U1〜U3のどれか（事前登録の枠に沿った判定）

- **U3**（陽性対照が通らない）: **不成立。** 陽性対照（32件差）は通った。
- **U1**（条件OもA側で発行）: **不成立。** `SAVE"2:.."`条件で条件Oは
  WRITE DATAをB側で発行した。
- **U2**（条件OはB側で発行）: **成立。** 自作サブROMは`FDC_WRITE_SECTOR`
  のunit/head組み立てが「ドライブ0固定 | (H<<2)」のままで、B:へ保存する
  条件でもWRITE DATAをunit Aで発行し続けている。これは**現在到達可能な
  条件で実際に起きている食い違い**である。

## 言えること・言えないこと

**言えること:**

- `SAVE"1:.."`（A:へ保存）条件では、WRITE DATAコマンド自身のunit/head
  を含め、公式・自作サブROMのFDC入口区間分類・WRITEストリーム内容
  （SHA-256）は完全一致する。
- `SAVE"2:.."`（B:へ保存）条件では、公式サブROMはWRITE DATAコマンド
  自身をB側で発行するが、自作サブROMはA側のまま発行する。これは2回の
  独立測定で再現した。
- 同条件で、自作サブROMはSEEK・READ DATA・SENSE DRIVE STATUSのunit/head
  はB側へ切り替えている（`m7gm`の観測と整合）にもかかわらず、WRITE DATA
  自身だけがA側に留まっている。これは`src/l3_service/make_subrom.py`の
  `FDC_WRITE_SECTOR`がunit/head組み立てで`REQ_HDR+2`bit0・
  `REQ_UNIT_HEAD`を参照していない、という既知のコード上の事実
  （本稿冒頭・`m7gn`に記載）と整合する観測である。
- 自作サブROMのWRITE系コマンド件数・総バイト数も公式より少ない
  （5件/1064バイト対8件/2112バイト）。これはunit/head不一致の直接の
  帰結なのか、B:候補ディスクの読み取り結果に別の要因が絡むのかは、
  本稿では切り分けていない。

**言えないこと:**

- 件数・バイト数の差（5件対8件）の原因そのもの（unit/head不一致だけで
  説明できるか、それとも別の実装差も混ざっているか）は調べていない。
- `disk#8`以外のB:候補（`m7gg`の残り候補群）でも同じパターンが出るかは
  未確認。
- 修正方針そのもの（`REQ_HDR+2`bit0・`REQ_UNIT_HEAD`をWRITE DATA組み立て
  へ反映する具体案）は本稿では検討していない。次稿で事前登録してから
  行う。
- データポート値列そのもの（値）、画面本文、公式ディスクの実データは
  見ていない・記録していない。

## 事前登録の遵守状況

[m7gn](m7gn-write-data-unit-preregistration.md)は測定開始前にコミット
した（コミット`7e3fd39`）。測定後の書き換え・amendは行っていない。
合格条件6項目は以下のとおり満たした:

1. 判定規則を条件O・条件Mそれぞれのベースライン2run同士へ先に当てて
   「差なし」を確認してから、条件O対条件Mへ当てた。
2. 陽性対照（`--break-drive-selector`）でunit/head差32件を確認した。
3. `build_mixed_rom`が出す混成ROMディレクトリ内のサブROM（`DISK.ROM`）
   のSHA-256は、全4回の混成ビルド（`SAVE"1:"`×2・`SAVE"2:"`×2）で
   同一だった。条件Oのサブサブディレクトリ（公式`*.ROM`一式のコピー）
   のSHA-256も全4回のコピーで同一だった（コピーのみなので当然だが、
   毎回確認した）。故障注入版（`--break-drive-selector`）は既定の混成
   ビルドと異なるSHAになることも確認した（意図した相違）。
4. `SAVE"2:.."`条件（差が出た条件）は2run測り、unit/head差件数5件・
   WRITE DATA分類が両runで一致することを確認した。`SAVE"1:.."`条件
   （差が出なかった条件）も同様に2run測り、両条件とも0件の一致を確認
   した（事前登録は「差が出た条件は2run」を最低条件としており、本稿
   では両条件とも2runずつ実施した）。故障注入版（陽性対照）は1runの
   み実施した（`m7gm`の`set`探針と同様、既存スクリプト
   `tools/verify_drive_byte2_attribution.sh`が既に決定論性を検証済みの
   既知の故障注入であるため）。
5. 全複製は`scratchpad`配下（リポジトリ外）に作成し、`private/`配下へは
   書き込んでいない。複製元ディスク（disk#8）のSHA-256は、全測定終了後
   に確認し、測定前と不変であることを確認した（`SRC_DISK_HASH_UNCHANGED=yes`）。
6. 本稿・事前登録・コミットメッセージのいずれにも実ファイル名を含めて
   いない。

## 開示

**手順上の逸脱が1件あった。** disk#8を特定する過程で、デバッグ目的の
一時的なシェルコマンド（`private/disk`配下のファイル一覧を`while read`
ループで1件ずつ表示するテストコマンド）を実行してしまい、10本の
ディスクイメージの実ファイル名が本セッションのツール呼び出し出力
（会話の透過的なログ）に一度だけ表示された。これはコミット・ノート・
コミットメッセージのいずれにも含まれておらず、以後の全ての作業・成果物
は通し番号`disk#N`とダイジェストのみで行った。しかし「実ファイル名を
一切標準出力に出さない」というこのタスクの規律そのものには違反した
事実であり、隠さず記録する。原因は`list_disk_basenames`の出力を
デバッグ用に直接ループ表示したことで、`tools/screen_data_disks.sh`等の
既存スクリプトが徹底している「ダイジェストのみ表示」の作法を、その場の
確認作業で外してしまった。以後、本稿を含む成果物には一切転記していない。

それ以外の手順上の逸脱・汚染は無かった。測定はすべてフォアグラウンドで
実行し、測定中に`git stash`・ブランチ切替・ファイル編集は行っていない。
SKIP・リトライ失敗は0件だった（全9回のq88measure実行はいずれも1回目で
rc=0）。

## 検証

`tools/check_cleanroom.sh`は全項目OK、rc=0。`git status`で`private/`
由来の混入・生ログ・ROM像・ディスク複製が無いことを確認した。`src/`・
`tools/`は本稿では変更していない。生ログ・混成/公式ROM一式・ディスク
複製はリポジトリ外（scratchpad配下）に置き、コミットしていない。

## 情報境界 / 根拠リンク

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容（実ファイル名を含む）は、成果物には含めていない（「開示」節に
記載のとおり、デバッグ出力に一度限り表示された事実はあるが、以後の
成果物には転記していない）。記録したのは公開FDCコマンド種別名、件数、
一致prefix件数、最初の差の位置番号（値ではない）、unit/head分類名、
画面出力の行数・文字数・SHA-256、WRITEストリームの件数・バイト数・
SHA-256、rc、ディスクの通し番号・ダイジェストだけである。

根拠（`ls`で存在確認済み）:
[m7gn](m7gn-write-data-unit-preregistration.md)・
[m7gm](m7gm-write-path-drive-axis-results.md)・
[m7gl](m7gl-write-path-drive-axis-preregistration.md)・
`docs/spec/l3-subrom.md` 1.35節・1.46節・1.56節・
自作`src/l3_service/make_subrom.py`（`FDC_WRITE_SECTOR`、本稿では変更
していない）・`tools/lib_l3_measure.sh`（`build_mixed_rom`・
`run_q88measure_retry`）・`tools/verify_drive_byte2_attribution.sh`
（陽性対照の作法・`--break-drive-selector`）・
`tools/compare_l3_entry_fdc.py`・`tools/hash_write_stream.py`・
`tools/check_l3_screen_output.py`・`tools/lib_screen_boot_disks.sh`。
