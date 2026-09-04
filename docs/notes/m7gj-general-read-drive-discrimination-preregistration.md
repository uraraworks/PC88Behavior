# m7gj: `general_read_request`の`clear`結果はドライブ指定か奇数シリンダかを弁別する事前登録

実施日: 2026-09-04

## 位置づけ

事前登録: general_read_requestのclear相違がドライブ指定か奇数シリンダかを弁別する

[m7gi](m7gi-remaining-callers-stage12-results.md)は`general_read_request`
で`clear`（`REQ_HDR+2`のbit0を0へ強制）がB:候補7本すべてでベースラインと
相違したことから、「この経路ではbit0が自然状態で1（奇数シリンダ相当）」
と解釈した。**この解釈には誤りの疑いが強い**という指摘を受けた。本稿は
その弁別測定を事前登録する。`m7gi`は書き換えず、`m7gi`側に訂正節を追記
する（次稿）。

## 疑いの内容とコード上の裏付け

`src/l3_service/make_subrom.py`を読み直した。

1. **`_general_read_request`は`REQ_HDR+2`を読まない・書かない。** 目的
   シリンダは`REQ_HDR+3`（論理トラック）から`rra`で作り、`REQ_HDR+4`
   （`FDC_SEEK`/`FDC_READ_SECTOR`が読む共有位置）へ置く。交換#6
   （`_exchange6_prepare_sector`）が持っていた「`REQ_HDR+2`を`REQ_HDR+4`
   へ転記する」という構造（`m7fy`/`m7fz`/1.56節の前提）は、この箇所には
   **無い**。
2. **`FDC_SEEK`自身が`REQ_HDR+2`を読む。** `FDC_SEEK`の入口
   （`break_drive_selector=False`の既定経路）は次の命令列を持つ
   （1.46節・`m7cj`/`m7ck`で恒久化済みの実装、探針とは無関係の既存
   コード）:
   ```
   a.ld_hl_imm(REQ_HDR + 2)
   a.ld_a_hl()
   a.and_a(0x01)
   a.ld_e_a()                  # E ← REQ_HDR+2 bit0（呼び出し元が積んだEを上書き）
   a.ld_a_mem(REQ_UNIT_HEAD)
   a.or_e()
   a.ld_mem_a(REQ_UNIT_HEAD)
   ```
   `_general_read_request`は`FDC_SEEK`呼び出し直前に`a.ld_e(0x00)`して
   いるが、この`E`は`FDC_SEEK`入口で**無条件に上書きされる**（呼び出し元
   のEは使われない）。すなわち`FDC_SEEK`は常に`REQ_HDR+2`のbit0を
   ドライブ選択（E、後続SENSE/READのunit）へ使う。
3. `m7gc`の`general_read_request`探針は、`FDC_SEEK`呼び出し直前
   （`_emit_probe`の位置）で`REQ_HDR+2`を直接`clear`/`set`する。
   これは**`FDC_SEEK`が数命令後に読む、まさに同じバイトを上書きして
   いる**。つまりこの箇所の`clear`/`set`は、交換#6のような「シリンダと
   ドライブ指定の同居」を検査しているのではなく、**恒久実装済みの
   ドライブ選択ビットそのものを強制**している。
4. `_general_read_request`冒頭の`intervene_no_disk_wait`分岐コメントに
   「FILES 2では既存のbyte2 bit0伝播によりB-unit/head0を問い合わせる」
   と既に明記されている。

**これらはコード読解であり、公式ROM・逆アセンブルは見ていない。**
自作`src/l3_service/make_subrom.py`のみを読んだ。

### 疑いの論理

条件R（`m7gh`/`m7gi`）は`FILES 2`＝B:を読む打鍵である。`REQ_HDR+2`
bit0が1.46節のドライブ指定なら、B:を読むときに自然状態でbit0=1になる
のは**正常動作**である。`clear`（0へ強制）はA:を見に行かせるので、
B:読み込みを期待する条件Rの末端が壊れるのは当然であり、「奇数シリンダ」
の証拠にならない。

## 弁別測定

**同じ箇所・同じ探針（`--probe-site general_read_request --probe-mode
clear`）で、打鍵を`FILES 1`（A:を読む）に変えて測る。** 他の条件は
条件R（B:=`disk#8`起動、`--frames 3000`、`--type-at 300 --type '\n'
--type-at 700`）と揃える。B:候補は`disk#10`を含め1〜2本で十分とする
（条件Rの結果は7本すべてで一様だったため、弁別に必要な条件数は少ない）。

**`FILES 1`がA:を読む打鍵かどうか自体の確からしさ**: `docs/spec/
l3-subrom.md` 1.46節は「`FILES 1/2`公式・混成各2回比較」を根拠に
`byte2 bit0`をドライブ指定と確定させており、`FILES 1`はドライブ指定
biti0=0（A:）、`FILES 2`はbit0=1（B:）に対応するという実測が既にある
（`m7cj`/`docs/notes/m7cj-drive-selector-request-byte.md`）。したがって
「`FILES 1`がA:を読む打鍵である」という前提は、本稿で新たに仮定した
ものではなく、既存の実測済み記述を引用している。

### 2通りの予測（測定前に固定）

- **予測A（ドライブ指定として正常）**: `FILES 1`条件で`clear`が
  ベースラインと**一致**する。bit0の自然値はFILES 1では既に0相当であり、
  `clear`（0へ強制）は実効的な変化を生まない。この場合、`general_read_
  request`の`clear`相違は**ドライブ指定ビットの正常動作**であり、
  「奇数シリンダ」解釈は誤りだったことになる。
- **予測B（奇数解釈が生き残る）**: `FILES 1`条件でも`clear`が
  ベースラインと**相違し続ける**。この場合、bit0はドライブに追随して
  いない別の意味を持つ可能性が残り、次の切り分けが要る。

## 事前登録する合格条件（測定前に固定。後から動かさない）

1. **判定規則を先にベースラインへ当てる**: `FILES 1`条件のベースライン
   （`--probe-site`未指定）2run同士に`tools/compare_l3_entry_fdc.py`・
   `tools/check_l3_screen_output.py`を当て、「差なし」を確認してから
   注入版へ当てる。
2. **到達確認済みであることを引用する**: `m7gi`が`general_read_request`
   の`cyl`陽性対照で到達を確認済み（条件Rでの`cyl`注入）である。本稿は
   同じ`FDC_SEEK`直前の位置への探針を打鍵だけ変えて使うため、到達可能性
   自体を`FILES 1`で再確認しない（打鍵を変えても注入位置のコード経路
   自体は変わらないため）。ただし`FILES 1`で当該箇所自体に到達しない
   （＝一般READ要求が一度も発行されない）可能性はゼロではなく、その
   場合はFDCコマンド種別列にREAD単位が現れるかで確認する。
3. **ROMの取り違え防止**: `--rom-dir`へ渡したサブROMのSHA-256が、全run
   で期待SHAと一致することを確認する。`m7gi`で既にビルド済みの
   `general_read_request_clear`ROM・baseline ROMをそのまま再利用し、
   使用前後でSHAが変わっていないことを確認する（新規ビルドはしない）。
4. **決定論性**: 差が出た条件は2run測って自己一致を確認する。
5. **名前の非記録**: 成果物に実ファイル名が含まれないこと。

## 測定の実務

- フォアグラウンドで実行する。測定中は`git stash`・ブランチ切替・
  ファイル編集を行わない。
- 生ログ・混成ROMはリポジトリ外（scratchpad配下）に置き、コミットしない。
- 出力は件数・一致/不一致・rcに絞る。値の列・実ファイル名は出さない。
- `src/`は変更しない。新しい`tools/`成果物は作らない（既存のツールを
  そのまま呼ぶ）。

## 結果ノートの扱い

結果は`m7gi`に**訂正節として追記**する（元の記述は残す）。誤りと判明
した場合は「どう誤っていたか」を明記する。詳細な測定条件・生データは
必要に応じて`docs/notes/m7gj-general-read-drive-discrimination-results.md`
に別途書いてもよい。

## 情報境界

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容は読んでいない。本稿は自作`src/l3_service/make_subrom.py`・
`docs/spec/l3-subrom.md` 1.46節・`m7gc`・`m7gi`のコード読解・記述読解
のみで構成した。測定はまだ行っていない。

## 根拠リンク

[m7gi](m7gi-remaining-callers-stage12-results.md)・
[m7gh](m7gh-remaining-callers-staged-preregistration.md)・
[m7gc](m7gc-remaining-callers-probe-preregistration.md)・
`docs/spec/l3-subrom.md` 1.46節・1.56節・自作
`src/l3_service/make_subrom.py`。
