# m7ge: 新しい起動ディスク（disk#3）で交換#6の目的シリンダを調べる（事前登録）

実施日: 2026-09-04

## 位置づけ

[m7ga](m7ga-odd-cylinder-condition-search-preregistration.md)/
[m7gb](m7gb-odd-cylinder-condition-search-results.md)は「本ハーネスで
変えられる自由度は起動ディスクの選択が事実上1択（`disk#8`、`650cfac8`）」
という前提の下で探索し、試した範囲では奇数シリンダ条件（`m7fz`が確立した
探針`--break-exchange6-drive-bit-clear`がベースラインと相違する条件）に
到達できなかった（予測B）。その後、
[m7gd](m7gd-boot-disk-screening.md)が名前を出さない選別により、
もう1本 L3ディスクサービスに入る起動ディスク（`disk#3`、`c29e67d4`）を
発見した。**これは「試した範囲」を実際に1本増やせる、m7gbの続きとして
初めて得られた新しい自由度である。** 本稿はこの`disk#3`で交換#6の目的
シリンダを調べる測定を事前登録する。**本稿では測定しない。**

## 名前を出さない運用

対象ディスクは常に「`disk#3`（`c29e67d4`）」、比較対象の既知ディスクは
常に「`disk#8`（`650cfac8`）」と呼ぶ。両ダイジェストは
[m7gd](m7gd-boot-disk-screening.md)の選別結果と同じ計算方法
（basenameのSHA-256先頭8桁）で得たものであり、`disk#8`はこれまでの
起動ディスクとして`m7fz`/`m7ga`/`m7gb`が使ってきたものと同一である
（`m7gd`の表で`OUT $FC`件数5,635件・判定「L3に入る」が両者一致するため）。
実ファイル名は本稿・結果稿・コミットメッセージ・スクリプトのいずれにも
書かない。ディスクの選択は`tools/lib_screen_boot_disks.sh`の
`list_disk_basenames`が返すソート順の通し番号で行う（`disk#3`は
その3番目のエントリ）。

## 探針・器材（`m7fz`/`m7ga`から変更しない）

- 探針: `src/l3_service/make_subrom.py`の`--break-exchange6-drive-bit-clear`
  （`REQ_HDR+2`のbit0を0へ強制）。ベースラインと一致すれば偶数、相違すれば
  奇数。
- 陽性対照: `--break-exchange6-cylinder`。
- 種別列比較: `tools/compare_l3_entry_fdc.py --after-frame 0
  --list-all-stages`（値ではなく種別名・段番号・一致/不一致のみ出力）。
- 画面比較: `tools/check_l3_screen_output.py --compare-report`
  （行数・文字数・SHA-256のみ出力）。
- 混成ROMは`tools/lib_l3_measure.sh`の`build_mixed_rom`で作る。

## 測定する内容（この順で実施する）

### 段階1: 適合の確認（disk#3、公式一式 vs 既定の混成ROM）

`disk#3`をA:に挿入し、**公式ROM一式（条件O、`*.ROM`をそのままコピー）**と
**既定の混成ROM（探針フラグ無しの自作サブROM）**で1回ずつ起動測定
（`--frames 1800`、打鍵無し）する。`compare_l3_entry_fdc.py --official
<公式> --mixed <混成> --after-frame 0`でFDCコマンド種別列・unit/head分類
が一致するかを見る。`disk#8`ではこの適合が既に確認されている
（`tools/conform_l3.sh`の起動測定と同条件）。**これは奇数シリンダの話とは
独立した価値を持つ測定である**——新しい刺激（新しいディスクの中身）の
上でも自作サブROMが公式と一致するかどうかは、それ自体が発見になりうる。

### 段階2: 陽性対照（`disk#3`、`--break-exchange6-cylinder`）

既定の混成ROMをベースラインとし、`--break-exchange6-cylinder`版と比較する。
**通ることを段階3の解釈条件にする。** `OUT $FC`が多数出ること
（`m7gd`で確認済み、5,635件相当）は「L3サービスに入っている」証拠に
すぎず「交換#6を踏んでいる」証拠ではないため、ここで段20付近
（1起点、`m7fz`が特定した交換#6のSEEK段）に差が出ることを別途確認する。
差が出なければ「`disk#3`はL3に入るが交換#6は踏んでいないか観測窓が外れて
いる」と扱い、**段階3の結果を解釈しない**（「差なし＝偶数」と読まない）。

### 段階3: 本測定（`disk#3`、`clear`/`set`）

既定の混成ROMをベースラインとし、`--break-exchange6-drive-bit-clear`と
`--break-exchange6-drive-bit-set`をそれぞれ比較する。

- `clear`が**相違** ⇒ その条件のシリンダは奇数。潜在バグが顕在化する
  条件を初めて手に入れたことになる。
- `clear`が**一致** ⇒ 偶数。「試した範囲」が1本増えるだけ。
- `set`は`m7fz`と同じく参考として測る（H1の裏付けの再確認。本稿の主判定は
  `clear`）。

### 段階4: 既知条件の再現（`disk#8`、`clear`のみ）

同じ判定規則で`disk#8`の`clear`をベースラインと1回比較し、`m7fz`/`m7gb`と
同じ結果（一致＝偶数）が本セッションでも再現することを確認する
（器材・手順が変わっていないことの確認であり、新しい探索ではない）。

## 事前登録する合格条件（測定前に固定。後から動かさない）

判定に数値比較を使わない。

1. **判定規則を先にベースラインへ当てる**: `disk#3`のベースライン2run
   （既定の混成ROMで同一条件を2回測定）に`compare_l3_entry_fdc.py
   --after-frame 0 --list-all-stages`・`check_l3_screen_output.py
   --compare-report`を適用し、いずれも「差なし」となることを確認して
   から、注入版と比較する。
2. **陽性対照**: 段階2（`--break-exchange6-cylinder`）が段20付近で差を
   出すこと。差が出なければ段階3を「解釈しない」として扱う。
3. **ROMの取り違え防止**: q88measureへ実際に渡した`--rom-dir`内の
   サブROM（`DISK.ROM`）のSHA-256が、全runで毎回ビルド直後の期待SHAと
   一致すること。公式ROM一式のディレクトリ（段階1の条件O）は中身を
   読まずcpするだけであることを確認する。
4. **決定論性**: 差が出た条件は2run測って自己一致を確認する。1runに
   とどめた条件があれば結果稿に明記する。
5. **名前の非記録**: 成果物（ノート・コミットメッセージ・スクリプト・
   標準出力）に実ファイル名が含まれないこと。コミット前に`git diff
   --cached`全文を読んで確認する。

一つでも欠ければ、その条件の判定は「解釈しない」に留める。

## 事前登録する予測（測定前に4通り）

- **A: `clear`が相違** ⇒ `disk#3`で奇数条件を発見。[l3-subrom.md](../spec/l3-subrom.md)
  1.56節が「到達できていない」とした穴が埋まる。次稿で公式ROMとの比較
  （このシリンダで公式実装がどう振る舞うか）に進む。
- **B: `clear`が一致** ⇒ `disk#3`でも偶数。「バグが無い」ではなく
  「試した範囲がもう1本増えた」と書く。
- **C: 陽性対照（段階2）が差を出さない** ⇒ `disk#3`はL3サービスに入るが
  交換#6は踏まない（あるいは観測窓が外れている）。段階3は解釈しない。
- **D: 段階1で公式と食い違う** ⇒ 奇数シリンダとは別の適合上の発見。
  本稿ではその事実の記録に徹し、原因究明は次稿で事前登録してから行う。

## 測定の実務

- 混成ROMは`tools/lib_l3_measure.sh`の`build_mixed_rom`で作る
  （`m7fz`/`m7gb`と同じ作法）。
- **フォアグラウンドで走らせる。`run_in_background`を使わない。**
- **測定中に`git stash`・ブランチ切替・ファイル編集を重ねない。**
- 無言でSKIPする分岐を作らない。SKIPが出たら件数を数えて記録する。
- 生ログ・混成ROM・複製ディスクは**リポジトリ外**
  （scratchpad配下）に置き、コミットしない。
- 出力は`grep -c`等で件数・一致/不一致・rcに絞る。値の列を画面に出さない。
- **`src/`は変更しない。** `tools/`は変更しない（本稿は測定のみ）。

## 情報境界

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容（ファイル名を含む）は読んでいない。記録するのはダイジェスト・段
番号・種別名・一致/不一致・件数・SHA-256・rcだけであり、値（シリンダ値・
データポート値・画面本文・実ファイル名）は書かない。

## 根拠リンク

[m7gd](m7gd-boot-disk-screening.md)・
[m7fz](m7fz-exchange6-drive-bit-results.md)・
[m7fy](m7fy-exchange6-drive-bit-preregistration.md)・
[m7ga](m7ga-odd-cylinder-condition-search-preregistration.md)・
[m7gb](m7gb-odd-cylinder-condition-search-results.md)・
[l3-subrom.md](../spec/l3-subrom.md) 1.56節・
自作`src/l3_service/make_subrom.py`・`tools/conform_l3.sh`・
`tools/lib_l3_measure.sh`・`tools/lib_screen_boot_disks.sh`・
`tools/compare_l3_entry_fdc.py`・`tools/check_l3_screen_output.py`。
