# m7gq: WRITE DATAのunit指定をドライブ選択ビットから作る修正を事前登録する

実施日: 2026-09-04

## 位置づけ

[m7go](m7go-write-data-unit-results.md)は、`SAVE"2:.."`（B:へ保存）条件で
公式サブROMがWRITE DATAコマンド自身をB側で発行するのに対し、自作サブROMは
A側のまま発行し続けることを実測で確定した（U2成立）。`SAVE"1:.."`（A:へ
保存）条件では両者は完全一致（WRITEストリームSHA-256まで同一）だった。

本稿はこの食い違いを直す修正の**事前登録**である。**測定しない。実装も
しない。** `src/`・`tools/`は本稿の作業終了時点で元の状態に戻す（下記
「調査」節でビルド確認のためだけに一時的に当てる）。実装と測定は次稿で
行う。

`docs/notes/m7gl-write-path-drive-axis-preregistration.md`・
`docs/notes/m7gm-write-path-drive-axis-results.md`・
`docs/notes/m7gk-save-drive-syntax.md`・`docs/spec/l3-subrom.md`
1.35節・1.46節・1.56節・3節・
`docs/notes/m7ft-boot-drive-selector-both-sides-preregistration.md`・
`docs/notes/m7fv-capacity-compression-results.md`を踏まえる。段番号は
0起点で統一し種別名を併記する。

## 直す対象（再掲）

`src/l3_service/make_subrom.py`の`FDC_WRITE_SECTOR`（1694行付近）は、
WRITE DATAコマンドのunit/headバイトを、`WRITE_PREV2`（データ部直前2バイト
目、論理トラック）のbit0だけから「ドライブ0固定 | (H<<2)」として組み立てて
おり、**`REQ_HDR+2` bit0（1.46節のドライブ指定）も`REQ_UNIT_HEAD`も参照
していない。**

## 調査: 符号化候補とバイト数の実測

`m7ft`と同じ作法で、候補を実際に`src/l3_service/make_subrom.py`へ当てて
`build()`を8構成（`default`・`break_write_ack`・`break_response`・
`inject_spurious_sense_int`・`restore_request_kind_length6`・
`intervene_no_disk_wait`・`fast_no_disk_response_ready`・
`force_post_bulk_active`、`m7fg`が確定した8構成）×
`PC88_BULK_READ_INTERVENTION_LIMIT`=1〜4の全32通りで直接呼び出し、
`SystemExit`の有無だけで判定した（`find_fetch_window_straddles`・
`find_out_of_window_blocks`の2関門。使用量の数値比較は判定に使わない。
参考として併記する）。検証は`/tmp`配下のスクリプトから`build()`を直接
呼ぶ形で行い、リポジトリへは追加していない。両候補とも適用後に`git diff`
を確認してから元へ戻した。適用前のベースライン（現行HEAD）も同じ32構成で
先に確認し、全32構成で`SystemExit`が0件であること（`default`@LIMIT=4=
2031バイト、`restore_request_kind_length6`@LIMIT=4=2039バイト）を確認
してから候補を当てた。

### 案1: `REQ_HDR+2` bit0を`FDC_SEEK`入口と同じ形で読み、合成する

`FDC_SEEK`の入口（1636〜1645行）が1.46節の共有伝播として行っているのと
同じ読み方——`REQ_HDR+2`のアドレスをHLへ、`LD A,(HL)`、`AND 1`——を
`FDC_WRITE_SECTOR`の先頭に追加し、既存の`WRITE_PREV2`由来のH計算
（`AND 1; RLCA; RLCA`）とOR合成してから`FDC_OUT`へ渡す。

追加命令: `LD HL,nn`(3) `LD A,(HL)`(1) `AND n`(2) `LD E,A`(1) の4命令5バイトを
先頭に追加し、既存計算の直後に`OR E`(1)を追加。合計+8バイト。

実測: `default`@LIMIT=4が2039バイト（ベースライン2031から+8）、
`restore_request_kind_length6`@LIMIT=4が2047バイト（+8）。**32構成中
`SystemExit`は0件。全構成で容量関門を通った。**

**意味的な正しさ**: `REQ_HDR+2`は各FILES要求ごとに受信ヘッダとして新しく
上書きされる領域であり（`HDR_STORE_AND_CHECK`が受信バイトを順に格納する
共通経路を通る）、WRITE要求自身が持つドライブ指定を毎回読み直すことになる。
`FDC_SEEK`の入口が同じ`REQ_HDR+2` bit0を読んで自分の発行にも
`REQ_UNIT_HEAD`への伝播にも使っている（1.46節）のと同じ情報源なので、
**WRITE DATA自身の発行とSEEK/SENSE/READの発行が、同じ生の情報源から独立に
一致する**形になる。

### 案2: `REQ_UNIT_HEAD`のbit0を読み、合成する

`FDC_SEEK`は自分の入口で`REQ_HDR+2` bit0を`REQ_UNIT_HEAD`へ`OR`合成して
いる（1645行、`LD A,(REQ_UNIT_HEAD); OR E; LD (REQ_UNIT_HEAD),A`）。WRITE
経路は`FDC_WRITE_SECTOR`の直前に必ず`_seek_sense_f7_shared`（1661行）を
経由しており、これが無条件に`FDC_SEEK`を呼ぶ（1663行）。したがって
`FDC_WRITE_SECTOR`が実行される時点では、直前の`FDC_SEEK`呼び出しにより
`REQ_UNIT_HEAD`のbit0は既に今回のドライブ指定へ更新されているはずである
——という理屈で、`REQ_UNIT_HEAD`のbit0を読み、`WRITE_PREV2`由来のH<<2と
OR合成する案。

追加命令: 既存計算の直後に`LD B,A`(1) `LD A,(REQ_UNIT_HEAD)`(3) `AND n`(2)
`OR B`(1、Z80定義済みオペコード`0xB0`。**未定義命令ではない**——本
リポジトリの`Asm`クラスに`or_b`ヘルパが未実装なだけであり、`a.db(0xB0)`で
直接発行すれば動く）。合計+7バイト。

実測: `default`@LIMIT=4が2038バイト（+7）、
`restore_request_kind_length6`@LIMIT=4が2046バイト（+7）。**32構成中
`SystemExit`は0件。全構成で容量関門を通った。** 案1より1バイト小さい。

**WRITE経路が`FDC_SEEK`を必ず通るかの確認**: `_recv_dispatch_write_sector`
（1867行付近）は`a.call("_seek_sense_f7_shared")`を経て`FDC_WRITE_SECTOR`
を呼ぶ直前まで、この一本の経路しか読解上見つからなかった（`grep`で
`FDC_WRITE_SECTOR`の呼び出し元を確認し、1箇所のみ）。`_seek_sense_f7_shared`
自身は無条件に`FDC_SEEK`を呼ぶ（`break_drive_selector`のような条件分岐
なし）。したがって「WRITE経路が`FDC_SEEK`を必ず通る」ことは読解で
**確認できた。**

**ただし、`REQ_UNIT_HEAD`がその時点で期待どおりの値かは確認できなかった。**
`REQ_UNIT_HEAD`への書き込みは`grep`で4箇所（`FDC_SEEK`入口のOR合成
〈1645行〉・`_general_read_request`〈1816行、`drive0 | (H<<2)`の**全体
上書き**〉・交換系準備2箇所〈2512・2533行、同じく全体上書き〉）しか無く、
**`FDC_SEEK`のOR合成だけが、bit0を「1へ立てる」ことはできても「0へ戻す」
ことができない**（`OR`はビットをクリアしない）。他の3箇所は`REQ_UNIT_HEAD`
全体を上書きする（`drive0 | (H<<2)`、bit0を常に0にしてから使う）ため、
その直後に`FDC_SEEK`が呼ばれれば正しい値になるが、**WRITE経路には
このような「使う直前にbit0を0クリアしてから`FDC_SEEK`を呼ぶ」書き込みが
無い。** つまり案2は、`FDC_WRITE_SECTOR`実行時点の`REQ_UNIT_HEAD` bit0が
「直前の`FDC_SEEK`が今回の`REQ_HDR+2` bit0を正しくOR合成した結果」である
ことに依存しており、**もし過去のどこかの操作でbit0=1（ドライブB）が
一度でも立ち、その後ドライブAへ戻る操作で`REQ_UNIT_HEAD`を明示的に
0クリアしないまま`FDC_SEEK`が呼ばれた場合、OR合成では古いbit0=1が残り
続ける可能性を読解だけでは排除できなかった。** `m7go`の実測（`SAVE"1:"`
条件は単独のA:のみへの保存で、そのセッション内で先にB:操作が起きていない
と見られる）はこの懸念を直接には検証していない。**したがって案2は、
確認できなかった前提の分だけ弱い。**

## どちらを採るか

**案1を採る。** 理由:

- 案1は`REQ_HDR+2`という、各FILES要求ごとに新しく上書きされる生の情報源を
  直接読む。`FDC_SEEK`の入口が同じ情報源を同じ形で読んでいるため、
  WRITE DATA自身の発行とSEEK/SENSE/READの発行が独立に同じ結論へ至る
  （どちらも「今回の要求のbit0」を見る）。
- 案2は`REQ_UNIT_HEAD`という、`OR`だけで更新されクリアされない中間状態を
  経由する。WRITE経路にはこの中間状態を使う直前に0クリアする書き込みが
  無いことを読解で確認しており、**過去の状態が残る可能性を排除できて
  いない。** 案2の方が1バイト小さいが、この差は次節「容量が塞いだ場合」
  の圧縮候補で埋め合わせられる規模であり、正しさの不確実性と引き換える
  理由にならない。
- 両案とも32構成すべてで容量関門を通ったため、容量を理由に案2を選ぶ必要は
  無い。

## 合格条件（測定前に固定。後から動かさない。数値比較は使わない）

1. **主指標**: `SAVE"2:.."`条件で、WRITE DATAコマンドのunit/headがB側に
   なり、公式と一致すること（`tools/compare_l3_entry_fdc.py`の入口区間
   unit/head分類、WRITE DATAだけを見る）。
2. **壊さないこと（同じくらい重要）**: `SAVE"1:.."`条件で、公式との一致が
   修正前と同じままであること。WRITEストリームのSHA-256
   （`tools/hash_write_stream.py`）を含めて確認する。
3. **容量関門**: 全32構成（8構成×`PC88_BULK_READ_INTERVENTION_LIMIT`=
   1〜4）で`build()`が`SystemExit`を出さないこと。判定は`SystemExit`の
   有無だけ（`m7fg`の基準）。使用量の数値比較は使わない。
4. **陽性対照**: `tools/verify_drive_byte2_attribution.sh`と同じ考え方で、
   `build_mixed_rom ... --break-drive-selector`（既存の故障注入、`m7go`で
   既に32件のunit/head差を検出済み）を、修正後の既定ビルドと比較し、
   判定規則がunit/head差を検出できることを先に確認してから、公式対修正後
   の比較を解釈する。
5. **判定規則を先にベースラインへ当てる**: 修正前どうし・修正後どうしの
   2run比較で「差なし」と出ることを確認してから、修正前対修正後・公式対
   修正後に当てる。
6. **退行なし**: READ経路・起動区間・`tools/conform_l3.sh`（適合条件1〜5
   すべて合格、**SKIP 0件**を確認する。SKIPは合格の顔をする）に退行が
   無いこと。
7. **決定論性**: 差が出た条件は2run測り、自己一致を確認する（`m7go`と
   同じ作法）。
8. **元ディスクを壊さない**: 書き込みを伴うため使い捨て複製
   （`tools/stage_disk_by_digest.sh`で中立パスを得た上で複製）を使い、
   全測定後に元ファイルのハッシュが不変であることを確認する。
9. 成果物（本稿・次稿・コミットメッセージ）に実ファイル名を含めない。

一つでも欠ければ合格と呼ばない。

## 予測（測定前に書く。どれになるかは予測しない）

- **F1**: 主指標が通り、`SAVE"1:"`条件も不変 ⇒ 採用
- **F2**: 主指標は通るが`SAVE"1:"`条件が変わる ⇒ 別の経路（案2で懸念した
  ような中間状態の副作用、あるいは未確認の別要因）を壊している。採用しない
- **F3**: 主指標が通らない ⇒ 符号化か理解が誤り
- **F4**: 容量関門に落ちる ⇒ 本稿の実測（32構成成功）と矛盾するので
  まず再実測して原因を切り分ける

## 容量が塞いだ場合の段取り

本稿の実測では案1・案2とも32構成すべてで容量関門を通ったため、現時点では
容量は塞いでいない。**次稿の測定段階で、何らかの理由（本稿で見落とした
構成の組み合わせ等）により容量が塞ぐことが分かった場合は、`m7fv`が
共有4命令列のサブルーチン化で余地を空けたのと同じように、圧縮候補を
別稿で事前登録してから行う。合格条件を緩めて押し込まない。**

## 検証

`tools/check_cleanroom.sh`は全項目OK、rc=0。`git status`で`src/`に変更が
残っていないこと（案を当ててビルド確認した後、必ず元に戻したこと）を
確認した。`private/`由来の混入・生ログ・ROM像・ディスク複製は無い。

## 情報境界 / 根拠リンク

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容は、成果物には含めていない。記録したのはZ80命令のニーモニック
（公開命令表の事実）、追加バイト数、32構成中の`SystemExit`件数、採否の
理由だけである。

根拠（`ls`で存在確認済み）:
[m7go](m7go-write-data-unit-results.md)・
[m7gn](m7gn-write-data-unit-preregistration.md)・
[m7gm](m7gm-write-path-drive-axis-results.md)・
[m7gl](m7gl-write-path-drive-axis-preregistration.md)・
[m7gk](m7gk-save-drive-syntax.md)・
[m7ft](m7ft-boot-drive-selector-both-sides-preregistration.md)・
[m7fv](m7fv-capacity-compression-results.md)・
[m7fg](m7fg-capacity-criterion-was-wrong.md)・
`docs/spec/l3-subrom.md` 1.35節・1.46節・1.56節・3節・
自作`src/l3_service/make_subrom.py`（`FDC_SEEK`・`FDC_WRITE_SECTOR`・
`_seek_sense_f7_shared`・`_general_read_request`、本稿では変更していない）・
`tools/check_cleanroom.sh`・`tools/stage_disk_by_digest.sh`・
`tools/verify_drive_byte2_attribution.sh`・
`tools/compare_l3_entry_fdc.py`・`tools/hash_write_stream.py`。
