# m7gn: WRITE DATAコマンド自身のunitは公式と一致するか — 事前登録

## 位置づけ

[m7gm](m7gm-write-path-drive-axis-results.md)の段階Aは、`SAVE"2:.."`
（B:へ保存）でSEEK・READ DATA・SENSE DRIVE STATUSのunit/headが全件B側へ
切り替わる一方、**WRITE DATAコマンド自身のunit/headは`SAVE"1:.."`・
`SAVE"2:.."`の両条件ともA側のまま**だったと記録した。

`src/l3_service/make_subrom.py`のWRITE DATA組み立て（`FDC_WRITE_SECTOR`）を
確認したところ、unit/headを「ドライブ0固定 | (H<<2)」で組み立てており、
`REQ_HDR+2`bit0も`REQ_UNIT_HEAD`も参照していない（コメントにも
「unit/head = drive0 | (H<<2)」とある）。つまり自作サブROMはB:へ保存する
条件でもWRITE DATAをunit Aで発行している。

**本稿の問い**: 公式サブROMは同じ条件（`SAVE"2:.."`）でWRITE DATAコマンド
自身のunitをA側・B側のどちらで発行するか。

- 公式もA側 ⇒ 自作は公式と一致している。1.35節の仕様として記録する
  （欠陥ではない）。
- 公式はB側 ⇒ 自作サブROMの実装欠落である。交換#6（1.56節）の潜在的な
  食い違いと違い、**現在到達可能な条件で実際に起きている食い違い**であり、
  優先度が高い。

**どちらになるかは予測しない。** 枠だけをここに固定する。

## 測定条件（m7gmの段階Aと同一条件を維持し、比較対象だけ差し替える）

- A:起動ディスク・B:候補ディスク: `disk#8`（`650cfac8`、`m7gd`で確認済み
  の起動可能ディスク）の使い捨て複製2本（別々の複製ファイル、それぞれ
  ライトプロテクトを外す）。m7gmの段階Aと同一。
- 打鍵: `--type-at 300 --type '\n' --type-at 700 --type '10 PRINT
  "T"\nSAVE"<N>:TQ"\n'`（N=1またはN=2）、`--frames 4200`。m7gmと同一。
- ROM条件（m7gmとの違いはここ）:
  - **条件O（公式一式）**: `PC88_REF_ROM_DIR`の`*.ROM`をそのままコピー
    しただけのディレクトリ（`tools/verify_drive_byte2_attribution.sh`の
    `copy_roms_for_mode official`と同じ手順、サブROMも公式のまま）。
  - **条件M（既定の混成）**: `build_mixed_rom`（`tools/lib_l3_measure.sh`）
    で作る、公式main一式＋自作サブROM（探針引数なし＝既定ビルド）。
    m7gmが使ったのと同じ組み立て。
  - 探針（`--probe-site`）は使わない。**既定ビルドどうしの比較**である。

## 判定に使う器材（既存、新規実装なし）

- `tools/compare_l3_entry_fdc.py --after-frame 700`
  （`--official`/`--mixed`という引数名だが、任意の2本のiologを比較できる
  汎用ツールなので、条件O同士・条件M同士の自己一致確認にもそのまま使う。
  FDCコマンド種別列・ポート値列の一致prefix、および入口区間の
  unit/head分類——`print_entry_classification`はコマンド名ごと
  （WRITE DATA・SEEK・READ DATA・SENSE DRIVE STATUS等）にunit/head分類
  件数を出すため、WRITE DATAだけを抜き出して見られる）。
- `tools/hash_write_stream.py`（WRITE系コマンドの件数・総バイト数・
  SHA-256）。
- `tools/check_l3_screen_output.py --compare-report`（画面出力比較）。

## 事前登録する手順

1. **陽性対照を先に実施する**: `tools/verify_drive_byte2_attribution.sh`
   と同じ考え方で、条件Mの既定ビルドと`build_mixed_rom ... 
   --break-drive-selector`（1.46節のドライブ指定伝播を壊してdrive0固定へ
   戻す既存の故障注入）を`SAVE"2:TQ"`条件で比較し、
   `compare_l3_entry_fdc.py --after-frame 700`のunit/head差件数が0件より
   大きいことを確認する。これは「判定規則がunit/headの違いを実際に
   検出できるか」を確かめる目的であり、WRITE経路そのものの結論には
   使わない。
2. 条件O・条件Mそれぞれについて、`SAVE"1:TQ"`・`SAVE"2:TQ"`の2run同士を
   比較し、`compare_l3_entry_fdc.py`・`hash_write_stream.py`・
   `check_l3_screen_output.py --compare-report`が「差なし」を返すことを
   確認する（判定規則がベースラインで偽陽性を作らないことの確認）。
3. 条件O対条件Mを、`SAVE"1:TQ"`・`SAVE"2:TQ"`それぞれについて比較する。
   主指標は**WRITE DATAコマンドのunit/head分類**（条件O側・条件M側）。
   対照として、SEEK・READ DATA・SENSE DRIVE STATUSのunit/head分類、
   FDCコマンド種別列の全長一致・一致prefix、画面出力の行数・文字数・
   SHA-256も記録する。

## 事前登録する合格条件（測定前に固定。後から動かさない）

判定に数値比較を使わない。

1. **判定規則を先にベースラインへ当てる**: 条件O2run同士・条件M2run同士
   に判定規則を当てて「差なし」と出ることを確認してから、条件O対条件Mに
   当てる。
2. **陽性対照**: 上記手順1で、故障注入版とのunit/head差件数が0件より
   大きいことを確認する。**陽性対照が差を出さなければ、本測定の
   『差なし』は解釈しない**（測定器の作り直しから）。
3. **ROMの取り違え防止**: `build_mixed_rom`が出す混成ROMディレクトリ内
   のサブROM（`DISK.ROM`）のSHA-256が、全runで毎回ビルド直後の期待SHA
   と一致すること。条件Oは公式`*.ROM`をそのままコピーしただけであること
   （中身は読まない）。
4. **決定論性**: 差が出た条件は2run測って自己一致を確認する。1runに
   とどめた条件は結果ノートに明記する。
5. **元ディスクを壊さない**: 複製はリポジトリ外（scratchpad配下）に置く。
   `private/`配下へ書き込む経路を作らない。全測定の最後に元ファイルの
   ハッシュが不変であることを確認して記録する。
6. 成果物（本稿・結果ノート・コミットメッセージ）に実ファイル名を含め
   ない（通し番号disk#Nとダイジェストのみで呼ぶ）。

## 事前登録する予測（測定前に書く。どれになるかは予測しない）

- **U1**: 条件Oも`SAVE"2:.."`でWRITE DATAをA側で発行する ⇒ 自作は公式と
  一致している。1.35節の仕様として記録する（欠陥ではない）。
- **U2**: 条件Oは`SAVE"2:.."`でWRITE DATAをB側で発行する ⇒ 自作サブROM
  の実装欠落である。現在到達可能な食い違いとして記録し、修正の検討は
  次稿で事前登録してから行う（**本稿では修正しない**）。
- **U3**: 陽性対照が通らない、または判定規則がunit/headの差を検出できない
  ⇒ 解釈しない。測定器の作り直しから。

## 禁止（本稿にも適用）

- 結果が予測と合わなくても、上記の合格条件・判定規則を動かさない。
- `src/`を修正しない（U2という判定が出ても本稿では直さない）。
- 値（バイト値・データポート値・シリンダ値・画面本文）を書かない。
- リポジトリに存在しないファイル名を引かない。実ファイル名は書かない。

## 測定の実務

- 混成ROMは`tools/lib_l3_measure.sh`の`build_mixed_rom`で作る。公式一式は
  `PC88_REF_ROM_DIR`の`*.ROM`を`cp -p`でコピーするだけ
  （`tools/verify_drive_byte2_attribution.sh`の`copy_roms_for_mode
  official`と同じ）。
- **フォアグラウンドで走らせる。`run_in_background`は使わない。**
- **測定中に`git stash`・ブランチ切替・ファイル編集を重ねない。**
- 無言でSKIPする分岐を作らない。SKIP・リトライ失敗は件数を数えて記録する。
- 生ログ・混成ROM・ディスク複製はリポジトリ外に置き、**コミットしない。**
- 出力は`grep -c`等で件数・一致/不一致・rcに絞る。値の列を画面に出さない。
- **`src/`は変更しない。修正もしない。** 本稿は測定と記録だけ。

## 情報境界 / 根拠リンク

- [docs/notes/m7gm-write-path-drive-axis-results.md](m7gm-write-path-drive-axis-results.md) —
  本稿が出発点とする段階Aの表（WRITE DATA自身のunit/headが両条件とも
  A側のままだったという観測）
- [docs/notes/m7gl-write-path-drive-axis-preregistration.md](m7gl-write-path-drive-axis-preregistration.md) —
  m7gmの事前登録
- [docs/notes/m7gk-save-drive-syntax.md](m7gk-save-drive-syntax.md) —
  `SAVE"<ドライブ番号>:<ファイル名>"`構文の出所（m7gmで実測の裏取り済み）
- `docs/spec/l3-subrom.md` 1.35節（WRITE経路）・1.46節（ドライブ指定
  伝播の恒久実装）・1.56節（交換#6の同居構造、対比のため）
- `tools/lib_l3_measure.sh`（`build_mixed_rom`・`run_q88measure_retry`）
- `tools/compare_l3_entry_fdc.py`・`tools/hash_write_stream.py`・
  `tools/check_l3_screen_output.py`
- `tools/verify_drive_byte2_attribution.sh`（陽性対照の作法の出所、
  `--break-drive-selector`故障注入）
- `tools/lib_screen_boot_disks.sh`（disk#8の識別に使う
  `list_disk_basenames`・`digest_basename`）
- `src/l3_service/make_subrom.py`（`FDC_WRITE_SECTOR`のunit/head組み立て。
  今回の問いの出所。本稿では変更しない）
