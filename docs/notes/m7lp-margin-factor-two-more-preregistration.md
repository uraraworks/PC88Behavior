# m7lp: 余白をもう12バイト作る——応答開始の列とN=1の送出列を集約する（純粋なコード移動） — 事前登録

## 位置づけ

[m7lo](m7lo-more-failure-shapes-results.md)で、**公式は削除マーク（ICは正常・ST2=CONTROL MARK）でも9件読み直し、
ほかの失敗と同じ応答を返す**が、自作は読み直さないことが分かった。**失敗の判定にST2のCMを加える作り直しをする**
（次のm7lq）。

**その作り直しは容量が足りない。** 素直な書き方（`FDC_IN_7`で結果3件目のST2を読み、CMが立っていれば`LAST_ST0`を
異常終了扱いにする）は+13バイトで、今の余白15では変種21個中10個が窓の関門で止まる（測定前に試して確かめた）。
**変種まで収めるには既定で21バイト以上の余白が要り、あと6バイト以上足りない。**

**本稿は[m7ld](m7ld-margin-factor-eot-gpl-dtl-results.md)・[m7lj](m7lj-margin-factor-reset-hdr-run-results.md)と同じ流儀で
余白を作る**——一字一句同一の命令列をサブルーチンへ集約する。命令列は1バイトも変えない。

## 何をするか（今のHEADで重複する命令列を数え直して選んだ）

1. **`ACTIVATE_SECTOR_RESPONSE`**: `ld (RESP_PTR),hl ; ld a,1 ; ld (RESP_ACTIVE),a ; xor a ; ld (SECTOR_READY),a`
   （末尾`ret`）。`SEND_DISPATCH`と`_post_read_activate_response`の2箇所。
   **直前の`ld hl,SECTOR_BUF`は含めない**——`_post_read_activate_response`ではその直後に故障注入（`break_response`）の
   分岐が入るので、含めると故障注入が効かなくなる。**最初は6命令で集約しようとして、この分岐のために2箇所目が
   文面で一致せず、気づいた。**
2. **`FDC_OUT_THEN_N1`**: `call FDC_OUT ; ld a,1 ; call FDC_OUT`（末尾は`jp FDC_OUT`）。WRITE・単発READ・バルクREADの3箇所。

**レジスタと状態**: 1は戻った時点のA=0・HL・フラグ（`xor a`の結果）が元と同じ。2は`FDC_OUT`がAFを保存して戻るので、
戻った時点のA=1・フラグが元と同じ。違うのは共有列の実行中にスタックが1段深いことだけ。

**試しの書き換えで測った（測定前。自作コードの大きさだけ）**:

| 版 | 既定 | 余白 | 関門で止められた変種 |
|---|---|---|---|
| HEAD | 2033 | 15 | 0個 |
| **この書き換え** | **2021** | **27** | **0個** |
| この書き換え＋m7lqの素直な書き方（CM） | 2034 | 14 | **0個** |

## 合格条件（**測定前に固定する。1つでも偽なら採用しない**。m7ljと同じ4つ）

1. 判定行の全集合が、同じ実行群のBASEと一致し、総合判定は適合（色コードを落とした判定行）。
2. データを運ぶポート（main IN `$FD`・`$FC`、sub OUT/IN `$FB`）のイベント列が、全iologでBASEと一致
   （m7ldの比較器。ポーリングのポートは比べない——m7ldで決めた範囲のまま）。
3. 決定論性: 書き換え版を独立2回、判定行の集合が一致。
4. 全長2021で関門を通る。変種フラグを1つずつ立てた全ビルドが関門を通る（拒否0個）。`tools/run_all_selftests.sh`が
   rc=0（worktreeの切り離したHEADへ使い捨てでコミットして回す。置き場由来の`check_cleanroom.sh`の1件を除く）。
   `tools/check_cleanroom.sh`は本体の作業ツリーで全項目OK。

## 採用したら

`src/`の変更として単独でコミットする（測定のコミットを先に）。**余白は27バイトになり、m7lqの容量の前提が満たされる。**

## 言えないこととして先に書いておくこと

- 実行のタイミングが同じだとは言わない（ポーリングは比べていない）。
- 本稿は自作の実装を測っている。

## 禁止（本稿の測定中も例外なく適用）

公式ROM・公式ディスクのバイト列を読まない・出力しない・逆アセンブルしない。`private/`の中身を見ない。データポート値・時刻・
frame番号・画面本文を出力しない（比較器はハッシュの一致・不一致と本数だけを出す）。

## 結果ノート

`docs/notes/m7lp-margin-factor-two-more-results.md` に書く。合格条件と比較の範囲を後から動かさない。

## 根拠リンク（`ls`で存在確認済み）

[m7lo](m7lo-more-failure-shapes-results.md)（**作り直しの動機**）・[m7lj](m7lj-margin-factor-reset-hdr-run-results.md)・
[m7ld](m7ld-margin-factor-eot-gpl-dtl-results.md)（**同じ流儀の前例と、比較の範囲**）・[m7li](m7li-retry-on-result-error-results.md)（変種で余白を見積もる教訓）・
`src/l3_service/make_subrom.py`（`SEND_DISPATCH`・`_post_read_activate_response`・`FDC_WRITE_SECTOR`・`FDC_READ_SECTOR`・`FDC_READ_BULK`）。
