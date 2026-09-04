# m7gf: 新しい起動ディスク（disk#3）で交換#6の目的シリンダを調べた結果

実施日: 2026-09-04

## 位置づけ

本稿は[m7ge](m7ge-disk3-exchange6-preregistration.md)が測定前に固定した
合格条件・予測に対する測定である。事前登録した4段階（適合確認・陽性対照・
本測定・既知条件の再現）以外を新たに追加した事実は無い。`src/`は本稿では
変更していない。名前は`disk#3`（`c29e67d4`）・`disk#8`（`650cfac8`）のみで
呼び、実ファイル名はどこにも書いていない。

## 測定条件（共通部分）

- ROM: `private/rom`（公式一式）と、本稿執筆時点の
  `src/l3_service/make_subrom.py`から`tools/lib_l3_measure.sh`の
  `build_mixed_rom`で作った4種の混成ROM（`baseline`＝全`break_*`False、
  `cylinder`＝`--break-exchange6-cylinder`、`clear`＝
  `--break-exchange6-drive-bit-clear`、`set`＝
  `--break-exchange6-drive-bit-set`）。加えて段階1用に公式ROM一式
  （`*.ROM`をそのままコピーしただけの条件O）を用意した。
- ディスクA: `disk#3`・`disk#8`それぞれの使い捨て複製（B:は無し、打鍵無し）。
- 実行: `q88measure --frames 1800`（`m7fz`/`m7gb`と同条件）。すべて
  フォアグラウンドで実行し、測定中に`git stash`・ブランチ切替・ファイル
  編集は行っていない。
- 4種の混成ROMの`DISK.ROM`のSHA-256は、ビルド直後と全測定終了後の両方で
  再ハッシュし、それぞれ期待値と一致することを確認した（4種は相互にも
  異なる）。公式ROM一式のディレクトリは`*.ROM`のみをコピーしたもので、
  測定中にコア実行状態のファイル（空の`.srm`）が1つ副生成されたが、
  `.ROM`拡張子のファイルには一切手を加えていないことを確認した
  （`build_mixed_rom`が`*.ROM`だけを対象にする設計どおり）。

## 段階1: 適合の確認（disk#3、公式一式 vs 既定の混成ROM）

**一致した。** `compare_l3_entry_fdc.py --after-frame 0`で、FDCコマンド
種別列は51件対51件で一致prefix51件（全長一致、rc=0）、`READ DATA`発行
件数9件対9件、入口区間unit/head分類も完全一致、画面出力も3行・111文字・
SHA一致（`screen_compare=match`、rc=0）。`disk#8`でこれまで確認されてきた
適合が、`disk#3`という新しい刺激の上でも成立することを確認した。

補足: FDCポート値列そのものの一致prefixは1件（2件目のSPECIFYパラメータで
早期に差）であり、`READ DATA`件数・種別列・unit/head分類・画面出力という
本稿の適合判定基準には含まれない指標では差があった。これは種別列一致
（rc=0）を適合の合否基準とする事前登録どおりの扱いであり、値そのものは
記録・解釈しない。

## 段階2: 陽性対照（disk#3、`--break-exchange6-cylinder`）

**通った。** `compare_l3_entry_fdc.py --after-frame 0 --list-all-stages`で、
最初の値差は段20（1起点、SEEK）「シリンダ指定 不一致」——`m7fz`が交換#6の
SEEK段として特定した位置と同じである。以降、段32・段36・段48でも
シリンダ指定不一致が続き（陽性対照は交換#6以降の複数SEEKへ波及する）、
画面出力は3行/111文字→1行/65文字、`screen_compare=mismatch`（rc=1）。
段階3を解釈してよい条件が満たされた。

## 段階3: 本測定（disk#3、`clear`/`set`）

### `break_exchange6_drive_bit_clear`（bit0を0へ）

**ベースラインと完全一致した。** FDCコマンド種別列51件対51件で一致
prefix51件（全長一致、rc=0）、FDCポート値列も一致prefix13833件（最初の
差「なし」）、`READ DATA`発行件数9件対9件、入口区間unit/head分類も完全
一致、画面出力もSHA一致（`screen_compare=match`、rc=0）。**予測B
（偶数）に合致する。**

### `break_exchange6_drive_bit_set`（bit0を1へ）

**ベースラインと大きく乖離した。** FDCコマンド種別列はベースライン51件・
本条件23件で一致prefix23件（コマンド24件目で混成側が先に終端）、
`READ DATA`発行件数9件対2件。入口区間unit/headの最初の差は「コマンド
20件目(SEEK)、公式=A/head0、混成=B/head0」、直後のコマンド21件目
（SENSE INTERRUPT STATUS）のST0も「公式=A/head0、混成=B/head0」で
不一致。画面出力は3行/111文字→1行/65文字、`screen_compare=mismatch`
（rc=1）。`m7fz`が`disk#8`で確認した`set`の崩壊パターン（コマンド20件目
SEEKでA→Bへ倒れ、以降のFDCコマンド列・READ DATA件数・画面出力が崩れる）
と同型である。

### 判定

`clear`はベースラインと一致し、`set`は乖離した。**`disk#3`でも交換#6の
目的シリンダは偶数だった（予測B）。** 「バグが無い」ではなく、試した
起動ディスクの範囲がもう1本増えた、と書く。

## 段階4: 既知条件の再現（disk#8、`clear`）

**再現した。** `disk#8`で`clear`とベースラインを比較したところ、FDC
コマンド種別列51件対51件で一致prefix51件（全長一致、rc=0）、unit/head
分類完全一致、画面出力SHA一致（`screen_compare=match`、rc=0）。
`m7fz`/`m7gb`と同じ結果（一致＝偶数）が、本セッションの器材・手順でも
再現することを確認した。

## 決定論性

- `disk#3`のベースラインは2run新規測定し、`compare_l3_entry_fdc.py`
  （全長一致・ポート値一致prefix13833件で差なし）・
  `check_l3_screen_output.py`（`screen_compare=match`）とも run1/run2 間で
  「差なし」を確認した（合格条件1）。
- 差が出た2条件（`disk#3`の`cylinder`・`set`）は各2run新規測定し、
  `redact_iolog.py`で伏せ字化した後のバイト列のSHA-256が run1/run2 間で
  完全一致することを確認した（自己一致）。
- **1runにとどめた条件**: `disk#3`の`clear`（差が出なかったため1run）、
  段階1の公式条件O（`disk#3`、1run）、`disk#8`のベースラインと`clear`
  （いずれも再現確認の位置づけで各1run、差が出なかった）。これらは
  事前登録どおり「1runにとどめた」ことを明記する。

## 事前登録した合格条件の充足状況

1. 判定規則をベースラインへ先に当てる: 満たした（`disk#3`ベースライン
   run1/run2で差なし）。
2. 陽性対照: 満たした（段階2で段20から差、画面不一致）。
3. ROMの取り違え防止: 満たした（4種の混成ROMのSHA-256がビルド直後・
   全測定終了後で一致、相互に異なる）。
4. 決定論性: 満たした（差が出た条件は2runで自己一致。1runにとどめた
   条件は上記のとおり明記した）。
5. 名前の非記録: 満たした（本稿はコミット前に`git diff --cached`全文を
   確認し、実ファイル名が含まれないことを確認する）。

## 言えること・言えないこと

**言えること:**

- `disk#3`という新しい刺激の上でも、既定の混成ROMは公式ROM一式と
  FDCコマンド種別列・unit/head分類・画面出力が一致する（段階1）。
- `disk#3`でも交換#6の目的シリンダは偶数だった。`clear`探針の結果が
  `disk#8`と同じ形（一致）になった。
- 陽性対照・故障注入(`set`)の崩壊パターンは`disk#3`と`disk#8`で同型
  （交換#6のSEEK段で最初に発現、以降のFDCコマンド列・画面出力が崩れる）
  であり、器材・判定規則が起動ディスクを変えても同じように機能する
  ことを確認できた。

**言えないこと:**

- `disk#3`と`disk#8`が同一系統のディスクなのか、内容として別種のもの
  なのかは、本稿の測定（種別名・段番号・件数のみ）からは分からない。
  名前を見ない設計上、確かめる手段自体を持たない。
- 奇数シリンダ条件は、本稿を含めこれまでに試したどの起動ディスク
  （`disk#8`、`disk#3`、m7gbの4条件）でも見つかっていない。`private/disk`
  に残る他の8本はL3ディスクサービスに入らないと`m7gd`が判定しており、
  この探針で調べる対象にならない（起動時に交換#6自体へ到達しない）。
- 本稿はA:単独起動・打鍵無し・`--frames 1800`という条件でのみ測定した。
  `disk#3`をB:に使う、打鍵を伴う、といった条件は測っていない。

## 開示

手順上の逸脱・汚染は無かった。測定はすべてフォアグラウンドで実行した。
公式ROM一式のディレクトリに空の`.srm`ファイルが1つ副生成されたが
（`m7bz`で既知の副作用と同型）、`.ROM`拡張子ファイルには影響しておらず、
値を見る事故ではなかった。

## 情報境界

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容（実ファイル名を含む）は読んでいない。記録したのは公開FDCコマンド
種別名、段番号、unit/head分類の一致・不一致、件数、画面出力の行数・
文字数・SHA-256、ROMのSHA-256、rcだけである。データポート値列・画面
本文・シリンダ値・PCN値・実ファイル名は表示も転記もしていない。生ログ・
混成ROM一式・複製ディスクはリポジトリ外（scratchpad配下）に置き、
コミットしない。

## 検証

`tools/check_cleanroom.sh`は全項目OK、rc=0。`git status`で`private/`
由来の混入・生ログ・ROM像が無いことを確認した。コミット前に
`git diff --cached`全文を読み、実ファイル名が含まれないことを確認した。

根拠: [m7ge](m7ge-disk3-exchange6-preregistration.md)・
[m7gd](m7gd-boot-disk-screening.md)・
[m7fz](m7fz-exchange6-drive-bit-results.md)・
[m7fy](m7fy-exchange6-drive-bit-preregistration.md)・
[m7ga](m7ga-odd-cylinder-condition-search-preregistration.md)・
[m7gb](m7gb-odd-cylinder-condition-search-results.md)・
自作`src/l3_service/make_subrom.py`・`tools/compare_l3_entry_fdc.py`・
`tools/check_l3_screen_output.py`・`tools/redact_iolog.py`・
`tools/lib_l3_measure.sh`・`tools/lib_screen_boot_disks.sh`。
