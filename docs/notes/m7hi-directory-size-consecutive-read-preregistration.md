# m7hi: ディレクトリのファイル数を振って連続READが現れるかを測る — 事前登録

事前登録: ファイル数を振ってディレクトリ列挙の連続READを探す

## 位置づけ

[m7hb](m7hb-consecutive-read-rule-results.md)は、条件O・`disk#10`
（`0c6f7a53`）・`FILES 2`で「SEEK1回＋READ DATA9件連続」という12コマンド
周期が末尾まで例外なく続くことを確定した（R4判定、決定論性あり）。この
構造は今のところ`disk#10`だけで観測されている（`disk#1`・`disk#2`・
`disk#8`では現れない）。

[m7hf](m7hf-disk10-consecutive-read-origin-results.md)は、`disk#10`自体に
大きさ・位置を振る梃子（自作ファイルの新規書込み）を試みたが、
`OPEN...FOR OUTPUT`が`bad allocation table`で即座に打ち切られ、
`disk#10`へは新規ファイルを一切書けないことが分かった（O4、行き止まり）。

[m7hg](m7hg-disk8-large-file-consecutive-read-preregistration.md)/
[m7hh](m7hh-disk8-large-file-consecutive-read-results.md)は、書込み可能な
`disk#8`（`650cfac8`）上に**1本の大きいファイル**を作り（本体READ DATA
最大99件）、`OPEN...FOR INPUT`でファイル本体を最後まで読ませたが、
**連続READが1件も現れなかった**（S水準17件・M水準99件、いずれもrun長
すべて1、主判定Q4）。m7hhの「次に何を測れば絞れるか」1項が明記した
とおり、`disk#10`の連続READは`FILES 2`（**ディレクトリ**読み出し）で
観測されたものであり、m7hhが試したのは「ファイル本体の大きさ」という
別の変数だった。**「ディレクトリの大きさ（＝ファイル数）」という変数は、
m7hh・m7hg・m7he・m7hfのいずれでもまだ切り分けられていない。**

**問い: `disk#8`上に多数の小さいファイルを作ってディレクトリを大きくし、
`FILES 2`を打鍵すれば、`disk#10`が見せた連続READ構造が現れるか。**
現れるなら、その件数がファイル数に追随するか、一定かを見る。

**これは検証対象の仮説であって前提ではない。支持する結果が出ても、
他の説明（`disk#10`固有の別の性質、`bad allocation table`との関係等）が
残らないかを結果ノートで必ず検討する。**

**測定を1回も走らせる前に本稿をコミットする。**

## 測定条件（共通）

- ROM: 条件O（公式一式）は`tools/conform_l3.sh`の`copy_entry_roms`
  関数と同じ手順（`*.ROM`をコピーするだけ）を使い捨てスクリプトで
  再現する。陽性対照・`general_read_request`経路確認・段階3にのみ
  条件M（`build_mixed_rom`混成）を使う。
- A: `disk#8`（`650cfac8`）の使い捨て複製に固定（起動可能ディスク）。
  `tools/stage_disk_by_digest.sh`で作る。**A:には書き込まない**
  （`--save-to-disk-image`を付けても、打鍵はB:選択のコマンドしか
  発行しない）。
- B: `disk#8`（`650cfac8`）の**別の**使い捨て複製。水準ごとに別々の
  複製を`tools/stage_disk_by_digest.sh`で作る。複製直後、D88ヘッダの
  ライトプロテクトフラグ（オフセット26バイト目）を`m7gt`・`m7he`・
  `m7hg`と同じ手当てで0へ倒す。
- 書込み（ダミーファイル群の生成）はB:への`--save-to-disk-image`付き
  起動で行い、B:の複製ファイル自体を変化させる。
- 読み出し（`FILES 2`）は、書込みを終えたB:複製を**別の使い捨て複製
  としてコピーしてから**、`--save-to-disk-image`無しで起動して打鍵する。
- 打鍵の前置は既存稿と同一: `--type-at 300 --type '\n'`で起動直後の
  余分な入力を吸収してから、`--type-at 700`から本文を打つ。
- ファイル名は自作の通し名（`D001`〜、3桁固定幅）。公式ディスクの
  実ファイル名ではない。
- ディスクはすべて`tools/stage_disk_by_digest.sh`でダイジェストから
  中立パスを得てから使う。

## 打鍵の作り方（技術的上限の回避、`m7he`・`m7hg`と同一方針）

`m7hd`が特定した`MAX_KEYSTROKES 512`を、プログラム本文を長く打つのでは
なく、**少ない打鍵でランタイムがループしてファイルを作る**ことで回避
する。`OPEN`/`PRINT#`/`FOR`〜`NEXT`/`RIGHT$`/`STR$`は、GW-BASIC/
N88-BASIC共通の教科書的な言語仕様（(a)、CLAUDE.mdの「N88-BASICの
マニュアルを読む」対象と同じ性質の情報）であり、本稿の担当セッションは
この範囲の構文には確信があるため、`refs-nec-manuals-2026-09-04.md`の
判定係手順は追加では踏まない。**構文の妥当性そのものは段階1項目2で
実測して確認する**（確信と実測は別、という前回までの教訓を踏まえる）。
確信が持てない構文（新規に使う関数等）が出た場合は、判定「可」の資料
（`refs-nec-manuals-2026-09-04.md`）で確認し、見たページ番号を結果
ノートに記録する。

### ディレクトリ拡大プログラム（M本の空ファイルをループで作る）

```
10 FOR N=1 TO <M>
20 F$="2:D"+RIGHT$("000"+STR$(N),3)
30 OPEN "O",#1,F$
40 PRINT#1,"X"
50 CLOSE #1
60 NEXT N
```

ファイル名を**3桁固定幅**（`D001`〜`D999`）にすることで、`<M>`の桁数が
変わっても打鍵列の長さが変わらない（数値リテラル`<M>`自体の桁数差のみ）。
これが「打鍵数が本数によらずほぼ一定になる」という事前登録の要件に
対応する。

## 段階0（前提。段階1より前）: 打鍵列の長さを数える

上記プログラム＋`RUN\n`の打鍵列を、投入前に文字数で機械的に数え、512件
未満であることを確認してから投入する。超えていたら投入せず、行の書き方
を調整して作り直す（水準の数・意図は変えない）。同様に`FILES 2\n`の
打鍵列も数える。

## 水準（測定前に固定。ループ回数Mで規定）

| 水準 | M（ループ回数＝ファイル数） | ファイル名範囲 |
|---|---:|---|
| 少（S） | 8 | `D001`〜`D008` |
| 中（M） | 32 | `D001`〜`D032` |
| 多（L） | 128 | `D001`〜`D128` |

**`disk#8`の空き容量・ディレクトリ上限を超える可能性がある。超えたら
「超えた」と記録する**（`m7hh`のL水準が`Disk full`を記録したのと同じ
扱い。代替水準を後から追加しない）。

## 段階1: ファイル数を振ってディレクトリを大きくする

各水準、B:の独立した複製に対して:

1. `stage_disk_by_digest.sh 650cfac8`で複製、ライトプロテクト解除。
2. `--save-to-disk-image`付きで起動し、ディレクトリ拡大プログラムを
   打鍵、`RUN\n`。事前登録するframes: S=4200, M=9000, L=24000
   （`m7hc`のS=4200を踏襲し、ループ回数に応じて引き上げる。打鍵列自体は
   どの水準もほぼ同じ長さなので、frames差は実行時間の見込みであり打鍵
   の見込みではない）。
3. 完了確認は`tools/check_l3_entry_screen.py`の`reached()`関数を、
   本稿の打鍵内容（`run`直後に`ok`）に対応する形で確認する使い捨て
   スクリプトを書く。`Ok`が出なければSKIPとして数え、framesを1.5倍に
   してもう一度だけ試す。2回目も出なければ「完了しなかった」として
   記録するにとどめる（解釈しない）。`Disk full`・`bad allocation
   table`等のエラー表示が出た場合は、その事実を記録し解釈しない
   （別水準を追加しない）。
4. 保存後の複製をさらに複製し、`--save-to-disk-image`無しで起動して
   `FILES 2\n`を打鍵（frames: S=3000, M=4500, L=9000）。完了確認は
   `reached(['files 2'])`。

**ファイル数が実際に増えたことの独立確認**: 各水準の保存後複製をさらに
複製し`FILES 2\n`を打鍵、`check_l3_screen_output.py --compare-report`で
水準間（S対M、M対L、S対L、および書込み前の未書込み参照複製対S）の画面
署名を比較する。すべての組が`mismatch`でなければ、その水準（ペア）は
「ファイル数が変わった」と言えないので解釈しない。確認できない水準は
解釈しない。

**連続READ件数・周期構造の記述**: 各水準の`FILES 2`測定iologに対し、
`tools/compare_l3_entry_fdc.command_names`（既存関数）を呼び、
`READ DATA`が連続する区間のrun長列と総`READ DATA`件数を求める使い捨て
スクリプトを書く（値そのものは見ない、件数と連続長だけを求める）。

## 段階2（段階1で連続READが現れた場合のみ）: 件数が何に追随するかを見る

水準間で連続READの件数を比べる。

- 件数が**ファイル数に追随する** ⇒ ディレクトリの大きさが効いている（P1）
- 件数が**一定**（例えば`disk#10`が見せた9のまま） ⇒ 上限がある。トラック
  やセクタの区切りに対応する可能性（**ただし断定しない。** 区別できる
  観測が無ければ「区別できない」と書く）（P2）

## 段階3（段階1で連続READが現れた水準がある場合のみ）: 条件Oと条件Mの比較

段階1で連続READが現れた水準のうち、**件数が最も多い水準**（同数なら
最初に現れた水準）について、条件O（公式）と条件M（混成、探針なし）の
`FILES 2`読み出しを、同じ書込み済み複製（の別コピー）に対して
`--list-all-stages`で比較する。

1.57節が記録した「公式は位置48・52の2回のSEEK後、新しい受信runを要求
せず連続READへ移行するのに対し、混成の`general_read_request`はレコード
ごとに新しい受信runを受け取り直し、連続READへ移行しない」という差が、
`disk#10`に依存しないこの条件でも再現するかを見る。再現すれば、
`disk#10`に依存しない再現条件を得たことになる（1.57節の重要な補強）。

## 事前登録する合格条件（測定前に固定。後から動かさない）

1. **陽性対照**: `build_mixed_rom ... --break-drive-selector`
   （1.46節の既存故障注入）を条件M・`FILES 2`・B:=本稿のS水準複製
   （`disk#8`由来）で比較し、`tools/compare_l3_entry_fdc.py
   --after-frame 700`のunit/head差件数が0件より大きいことを確認する。
   あわせて`tools/analyze_error_exchange_shape_selftest.sh`のrc=0
   （全項目OK）を確認する。**通らなければ以降を解釈しない。**
2. **判定規則を先にベースラインへ当てる**: 条件Oを本稿のS水準の
   `FILES 2`測定で独立2回測り、`--list-all-stages`（`--after-frame`
   無し）で「差なし」と出ることを確認する。
3. **梃子が効いたことの独立確認**: ファイル数が実際に増えたことを、
   `FILES`表示の署名変化（`mismatch`）で確認する。確認できない水準は
   解釈しない。
4. **読み出し経路の確認**: 段階1で連続READが最も多く現れた水準
   （現れなければS水準）の`FILES 2`打鍵について、条件M・
   `--probe-site general_read_request --probe-mode cyl`と探針なし基準を
   `--list-all-stages`で比較し、いずれかのSEEK段でシリンダ指定の
   不一致が出れば「通る」とする。
5. **決定論性**: 差が出た水準は2run測って自己一致を確認する。1runに
   とどめた水準は明記する。
6. **元ディスクを壊さない**: 使い捨て複製のみを使い、全測定後に
   `disk#8`の元ファイルのハッシュが不変であることを確認して記録する。
7. 成果物に実ファイル名が含まれないこと（自作の通し名`D001`〜`D128`と、
   ディスクの通し番号・ダイジェストのみで表す）。

## 事前登録する予測（測定前に書く。どれになるかは予測しない）

- **P1**: 連続READが現れ、件数がファイル数に追随する ⇒ ディレクトリの
  大きさが効いている
- **P2**: 連続READが現れるが件数は一定 ⇒ 上限がある。何が上限を決める
  かは次稿
- **P3**: 連続READが現れない ⇒ **ディレクトリの大きさでもない。**
  `disk#10`の別の性質による。次に何を比べれば絞れるかを書く
  （`bad allocation table`（`m7hf`）との関係を含めて検討する）
- **P4**: 段階3で1.57節の差が再現する ⇒ `disk#10`非依存の再現条件を
  得た
- **P5**: 陽性対照が通らない／ファイルを作れない ⇒ 解釈しない

## 測定の実務

- **フォアグラウンドで走らせる。`run_in_background`を使わない。**
- **測定中に`git stash`・ブランチ切替・ファイル編集を重ねない。**
- 無言でSKIPする分岐を作らない。SKIP・リトライ失敗・`Disk full`等は
  記録する。
- 生ログ・ディスク複製はリポジトリ外（scratchpad配下）に置き、
  **コミットしない。**
- 出力は`grep -c`等で件数・一致/不一致・rcに絞る。**値の列を画面に
  出さない。**
- **`src/`と`tools/`は変更しない。** 特に`tools/harness/frontend/main.c`
  は変更しない。
- **使い捨てのデバッグでもディスクの実ファイル名を展開して表示しない。**

## 結果ノート

`docs/notes/m7hj-directory-size-consecutive-read-results.md`に書いて
コミットする。陽性対照・経路確認・梃子の独立確認を**最初に**書く。
段階1 → 段階2 → 段階3 → P1〜P5の判定 →「言えること・言えないこと」→
開示（資料を見た場合はページ番号も）→情報境界→根拠リンク（`ls`で実在
確認、存在しないファイル名を引かない）。**仮説が支持されても、他の
説明が残らないかを必ず書く。決まらなければ「決まらなかった」と書く。**
もっともらしい説明で埋めない。次に何を測れば絞れるかを具体的に書く。

## 禁止

- **結果が予測と合わなくても、条件や水準を後から足したり動かしたり
  しない。**
- **`src/`・`tools/`を修正しない。**
- 値（バイト値・データポート値・シリンダ値・画面本文）を書かない。
- **公式ROMの逆アセンブル・バイト列の観察はしない。**
- 資料を読む場合、**立入禁止範囲に入らない。(b)(c)に着地したらその場で
  離れて記録する。**

## 根拠リンク（`ls`で存在確認済み）

[m7hb](m7hb-consecutive-read-rule-results.md)・
[m7hc](m7hc-consecutive-read-count-origin-preregistration.md)・
[m7hd](m7hd-consecutive-read-count-origin-results.md)・
[m7he](m7he-disk10-consecutive-read-origin-preregistration.md)・
[m7hf](m7hf-disk10-consecutive-read-origin-results.md)・
[m7hg](m7hg-disk8-large-file-consecutive-read-preregistration.md)・
[m7hh](m7hh-disk8-large-file-consecutive-read-results.md)（次に測る
べきものとしてファイル数を提案した出所）・
[m7gt](m7gt-odd-cylinder-by-layout-change-results.md)（ライトプロテクト
解除の手当ての出所）・[m7gk](m7gk-save-drive-syntax.md)・
[m7gp](m7gp-disk-name-leak-path-closed.md)・
[m7gg](m7gg-data-disk-screening.md)（`disk#10`のREAD DATA件数突出の
出所）・[m7gz](m7gz-command56-divergence-results.md)（`general_read_
request`探針手法・1.57節の構造差の確立元）・
`docs/spec/l3-subrom.md` 1.57節（第144版）・1.36節・1.37節・3節・
`tools/compare_l3_entry_fdc.py`（`command_names`・`--list-all-stages`）・
`tools/check_l3_screen_output.py`・`tools/check_l3_entry_screen.py`
（`reached`・`screen_rows`）・`tools/stage_disk_by_digest.sh`・
`tools/analyze_error_exchange_shape_selftest.sh`・
`tools/lib_l3_measure.sh`（`build_mixed_rom`）・`tools/conform_l3.sh`
（`copy_entry_roms`）・`tools/harness/frontend/main.c`
（`MAX_KEYSTROKES`・`--save-to-disk-image`・`schedule_typing`・
`--disk2`）・`tools/check_cleanroom.sh`。
