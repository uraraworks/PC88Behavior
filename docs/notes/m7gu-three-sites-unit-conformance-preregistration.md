# m7gu: `bulk_read_do`・交換#11・交換#14のunit指定は公式と一致するか — 事前登録

## 位置づけ

[m7gi](m7gi-remaining-callers-stage12-results.md)（訂正節付き）は
`FILES 2`（B:読み）条件で、`general_read_request`のbit0=1が
[m7gj](m7gj-general-read-drive-discrimination-preregistration.md)の弁別
測定によりドライブ指定として正常だったと確定した一方、`bulk_read_do`・
`exchange11_fallthrough`（交換#11）・`exchange14_prepare_first_read`
（交換#14）の3箇所はいずれもbit0=0のままだった（B:候補7条件すべて）。

`m7go`（WRITE DATA unit）は、同じ形の観察——ある経路だけドライブ指定が
自作サブROMに伝播していない——を公式ROMとの直接比較で実際の欠落として
確定させた前例である。本稿はその網のかけ方を読み側の3箇所に対して適用
する。

**問い**: 同じB:読み出しの最中に、`bulk_read_do`・交換#11・交換#14が
`FDC_SEEK`へ伝えるunit/headは、公式サブROMと一致するか。

- 一致 ⇒ bit0=0はこれらの経路では仕様どおりであり、1.46節の伝播はこれら
  の経路には要らない。
- 不一致 ⇒ `m7go`と同じ形の実装欠落。修正は本稿では行わず、次稿で事前
  登録してから行う。

**どちらになるかは予測しない。**

## 測定条件

- ROM: `private/rom`（公式一式=条件O）と、`tools/lib_l3_measure.sh`の
  `build_mixed_rom`が作る混成（公式main一式＋自作サブROM＝条件M、探針
  引数なしの既定ビルド）。
- 条件R2（`FILES 2`＝B:読み、主条件）: A:に`disk#8`
  （`650cfac8`、起動可能ディスク、`m7gd`で確認済み）、B:に候補ディスク
  の使い捨て複製。打鍵は`m7gh`/`m7gi`と同一
  （`--type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n'
  --frames 3000`）。
- 条件R1（`FILES 1`＝A:読み、対照条件）: 同じA:/B:構成で打鍵のみ
  `FILES 1\n`に変える（`m7gj`が使った対応と同一）。
- B:候補ディスクは、`m7gi`が奇数条件確保の主対象とした`disk#10`
  （`0c6f7a53`）を主とし、決定論性確認・段の対応づけには`disk#8`自身の
  複製（B:=A:と同一内容）も併用する（`m7gh`/`m7gi`の条件Rと同じ構成）。
- 全ディスクは`tools/stage_disk_by_digest.sh`でダイジェストから中立パス
  を得てから使う（`m7gp`の運用）。実ファイル名を扱う経路を作らない。

## 段階0（本稿）: 事前登録を測定前にコミットする

本稿は測定を1回も走らせる前にコミットする。測定後の書き換え・amendは
行わない。

## 段階1（主測定）: 公式との比較

`FILES 2`条件で条件O対条件Mを比較し、`bulk_read_do`・交換#11・交換#14
それぞれが発行する`SEEK`/`SENSE DRIVE STATUS`/`READ DATA`のunit/head
分類を見る（`tools/compare_l3_entry_fdc.py --after-frame <各箇所の入口
フレーム相当>`、`m7go`と同じ器材）。`FILES 1`条件でも同じ比較を行い、
対照とする（A:条件で一致するなら差はB:条件に固有と言える）。

**段の対応づけ**: `--probe-site <箇所> --probe-mode cyl`
（`m7gc`実装済み、`m7gi`段階1で到達確認済み）を混成ROM（条件M）に注入し、
`tools/compare_l3_entry_fdc.py --after-frame 0 --list-all-stages`で
ベースライン（条件M、探針なし）と比較する。**その箇所だけを動かした
ときに最初に変化する段番号**を、その箇所に対応する段として特定する
（`m7fz`が交換#6で使った手続きと同一）。対応づけができた箇所だけ、主
指標のunit/head分類をその箇所の結果として解釈する。対応づけができない
箇所は「できなかった」と明記し、その箇所の主指標は解釈しない。

## 段階2（従属測定）: `set`でbit0の効き方を見る

段階1の結果に関わらず、3箇所それぞれで`--probe-mode set`をB:候補
（`disk#10`、必要なら追加候補）で測り、`m7gc`/`m7gh`が定義した
P1（bit0=1が実際に効く/壊れる）・P2（未到達）・P4（現状bit0=0で動作、
1へ強制しても壊れない）の区別を付ける。`cyl`による到達は`m7gi`で確認
済みだが、本稿でも`cyl`を改めて実施し確認する。

## 判定に使う器材（既存、新規実装なし）

- `tools/compare_l3_entry_fdc.py`（`--after-frame`・`--list-all-stages`
  の両モード）
- `tools/check_l3_screen_output.py --compare-report`
- `tools/verify_drive_byte2_attribution.sh`と同じ考え方の陽性対照
  （`build_mixed_rom ... --break-drive-selector`）
- `tools/stage_disk_by_digest.sh`

## 事前登録する合格条件（測定前に固定。後から動かさない）

判定に数値比較を使わない。

1. **陽性対照**: `build_mixed_rom ... --break-drive-selector`
   （1.46節のドライブ指定伝播を壊す既存の故障注入）と既定の混成ROM
   （条件M）を、`FILES 2`条件・同じB:候補で比較し、
   `compare_l3_entry_fdc.py --after-frame 0`のunit/head差件数が0件より
   大きいことを確認する。通らなければ以降を解釈しない。
2. **判定規則を先にベースラインへ当てる**: 条件O2run同士・条件M2run
   同士（`FILES 1`・`FILES 2`それぞれ）に判定規則を当てて「差なし」と
   出ることを確認してから、条件O対条件Mへ当てる。
3. **段の対応づけの根拠を示す**: 主指標を語る段が、実際にその経路の段
   であることを`cyl`注入とベースラインの比較（`--list-all-stages`の
   段番号の一致/不一致）で示す。対応づけができない箇所は「できなかった」
   と書き、その箇所の主指標は解釈しない。
4. **ROMの取り違え防止**: `--rom-dir`へ実際に渡したROMディレクトリ内の
   サブROMのSHA-256が、全runで毎回ビルド直後の期待SHAと一致すること。
   条件Oは公式`*.ROM`をそのままコピーしただけであること。
5. **決定論性**: 差が出た条件は2run測って自己一致を確認する。1runに
   とどめた条件は明記する。
6. 成果物に実ファイル名が含まれないこと（ダイジェスト・通し番号のみ）。

## 事前登録する予測（測定前に書く。どれになるかは予測しない）

- **C1**: 3箇所とも公式と一致 ⇒ bit0=0はその経路で正しい。1.46節の伝播
  はそれらの経路には要らないということであり、仕様として記録する。
- **C2**: いずれかが公式と食い違う ⇒ `m7go`と同じ形の実装欠落。現在到達
  可能な食い違いとして記録し、修正は次稿で事前登録してから行う（本稿
  では修正しない）。
- **C3**: 陽性対照が通らない／段の対応づけができない ⇒ 解釈しない。

## 禁止（本稿にも適用）

- 結果が予測と合わなくても、上記の合格条件・判定規則を動かさない。
  当てはまらない結果は「当てはまらない」と書く。
- `src/`を修正しない（C2という判定が出ても本稿では直さない）。
- 値（バイト値・データポート値・シリンダ値・画面本文）を書かない。
- リポジトリに存在しないファイル名を引かない。実ファイル名は書かない。

## 測定の実務

- 混成ROMは`build_mixed_rom`で作る。公式一式は`PC88_REF_ROM_DIR`の
  `*.ROM`を`cp -p`でコピーするだけ。
- **フォアグラウンドで走らせる。`run_in_background`は使わない。**
- **測定中に`git stash`・ブランチ切替・ファイル編集を重ねない。**
- 無言でSKIPする分岐を作らない。SKIP・リトライ失敗は件数を数えて記録
  する。
- 生ログ・混成ROM・ディスク複製はリポジトリ外（scratchpad配下）に置き、
  **コミットしない。**
- 出力は`grep -c`等で件数・一致/不一致・rcに絞る。値の列を画面に出さ
  ない。
- **`src/`は変更しない。修正もしない。**
- **使い捨てのデバッグでもディスクの実ファイル名を展開して表示しない。**

## 情報境界 / 根拠リンク

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容（実ファイル名を含む）は、本稿の作業・成果物に含めない。

根拠（`ls`で存在確認済み）:
[m7gi](m7gi-remaining-callers-stage12-results.md)・
[m7gj](m7gj-general-read-drive-discrimination-preregistration.md)・
[m7go](m7go-write-data-unit-results.md)・
[m7gq](m7gq-write-data-unit-fix-preregistration.md)・
[m7gr](m7gr-write-data-unit-fix-results.md)・
[m7gp](m7gp-disk-name-leak-path-closed.md)・
[m7fz](m7fz-exchange6-drive-bit-results.md)・
`docs/spec/l3-subrom.md` 1.33節・1.34節・1.36節・1.46節・1.56節・3節・
`src/l3_service/make_subrom.py`（`--probe-site`/`--probe-mode`、本稿では
変更しない）・`tools/lib_l3_measure.sh`（`build_mixed_rom`・
`run_q88measure_retry`）・`tools/compare_l3_entry_fdc.py`・
`tools/check_l3_screen_output.py`・`tools/stage_disk_by_digest.sh`・
`tools/verify_drive_byte2_attribution.sh`（陽性対照の作法の出所）。
