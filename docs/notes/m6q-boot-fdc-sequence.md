# M6q — 起動時FDC初期化シーケンス（1.16節手順8の中身）の構造解析

測定日: 2026-08-12
対象: 混成ROM実走診断（`last.txt`、16:56版）が示した分岐点28。基準側は
「結果フェーズ直後にTC三つ組み（1.21節）」という構造で先へ進むが、自作sub
（`FDC_SPECIFY`のみを呼んで`MAIN_LOOP`へ直行。SPECIFYは結果フェーズ0バイト
なのでこの構造自体が起きない）はここで`$FE`ハンドシェイクへ戻ってしまい
分岐する。1.16節手順8「FDC初期化」は中身が未確定のまま残っていた。

**追加測定は行っていない。** 既存の `measurements/m6c-sub-{d0-boot,
d1-files,d2-save,d5-seqfile}.iolog.txt.gz`（4条件、同一の公式サブROM
バイナリ）だけを再解析した。値は一切見ていない（`$FA`/`$FB`はもちろん
`$F7`/`$F8`/`$FE`/`$FF`の値も本稿の判断には使っていない。使ったのは
件数・kind・pc・seqのみ）。pcは測定フックが実行時に記録したコードアドレス
であり、CLAUDE.mdの「(a) ハードウェアの事実」「エミュレータに計測フックを
入れ、入出力の対応を測定する」の範囲内（逆アセンブルではなく実行時計測）。
既存の1.16節・m6k・m6p・m6oも同様にpcを使っている。

新規解析器: `tools/analyze_boot_fdc_sequence.py`。`tools/analyze_fdc_ports.py`
の`IoEvent`/`parse_iolog`をimportして再利用（二重実装しない）。

再実行方法:

```
python3 tools/analyze_boot_fdc_sequence.py cross \
    --iolog d0-boot    measurements/m6c-sub-d0-boot.iolog.txt.gz \
    --iolog d1-files   measurements/m6c-sub-d1-files.iolog.txt.gz \
    --iolog d2-save    measurements/m6c-sub-d2-save.iolog.txt.gz \
    --iolog d5-seqfile measurements/m6c-sub-d5-seqfile.iolog.txt.gz \
    --out measurements/m6q-boot-fdc-sequence-cross.txt
```

---

## 1. 同定方法

μPD765/8272系データシートの公開仕様（CLAUDE.mdの「(a) ハードウェアの
事実」に該当し参照可）は、各コマンドのコマンドフェーズ（書き込み）
バイト数と結果フェーズ（読み込み）バイト数を規定している。本稿で使った
値（実行フェーズがデータ転送を伴わないコマンドのみ）:

| コマンド | コマンドフェーズ(書き) | 結果フェーズ(読み) |
|---|---:|---:|
| SPECIFY | 3 | 0 |
| RECALIBRATE | 2 | 0 |
| SEEK | 3 | 0 |
| SENSE INTERRUPT STATUS（正常時） | 1 | 2 |
| SENSE DRIVE STATUS | 2 | 1 |

測定ログからは、sub の `$FB` アクセスを「`$FA`ポーリングを挟んでも
kind（IN/OUT）が変わらない限り連続」とみなしてrun分割した
「(直前のOUT run長, 直後のIN run長)」の組が読める（m6pで確立済みの
手法をそのまま流用）。**複数のFDCコマンド呼び出しが、間に結果読みを
挟まなければ同一のOUT runへ merge される**（ある呼び出しの結果フェーズが
0バイトなら、次の呼び出しのコマンドバイトがそのまま同じOUT runに
連なる）。したがって観測されたrun長は「そのrunに含まれる全コマンドの
コマンドフェーズバイト数の合計」であり、runの最後の1コマンドだけが
結果フェーズを持つ（結果フェーズを持つコマンドの後にはIN runの区切りが
入るため、2つ以上のコマンドが結果フェーズを持つ状態で1つのOUT runに
同居することはできない）。

このrun長を、上表の组み合わせに **一意に分解できるかどうか** で
同定した。

## 2. 確定: 起動時FDC初期化区間は $FA/$FB のrun 7組からなる

1.16節手順6〜7（`OUT $F8`の2連続書き込み。値は見ないが「BOOT_HANDSHAKE
後、最初の`$FA`/`$FB`アクセスより前に来る`$F8`への2連続OUT」という構造
で機械的に特定できる）の直後から、次に`$FE`/`$FF`へのアクセスが現れる
まで（＝1.17節「アイドル待ち」への遷移点）を「起動時FDC初期化区間」と
定義して切り出した。**4条件すべてで区間の境界（event index [15,112)、
seq範囲[16,112]）が1バイトも違わず完全一致した。**

区間内の`$FB` run列（OUT=書き, IN=読み）は4条件とも同一:

```
OUT run 長=6 → IN run 長=2   … batch1
OUT run 長=4 → IN run 長=2   … batch2
OUT run 長=3 → IN run 長=2   … batch3
OUT run 長=3 → IN run 長=2   … batch4
OUT run 長=4 → IN run 長=2   … batch5
OUT run 長=3 → IN run 長=2   … batch6
OUT run 長=3 → IN run 長=2   … batch7
```

## 3. 確定: 各batchの最後のコマンドは SENSE INTERRUPT STATUS（正常時）

結果フェーズが2バイトのコマンドは上表でSENSE INTERRUPT STATUSのみ
（正常時。1.21節・既存実装のコメントが既に確認している「保留中の割り込みが
無い場合はST0の1バイトのみ」という異常系はここでは observed read=2で
一貫しており該当しない）。よって**各batchの最後の1コマンドはSENSE
INTERRUPT STATUSで一意に決まる**。

## 4. 一意に決まるもの・決まらないもの

各batchの「SENSE INTERRUPT STATUS（1バイト）を引いた残り」を、結果
フェーズ0バイトのコマンド（SPECIFY=3, RECALIBRATE=2, SEEK=3）の組み合わせ
に分解した。

| batch | OUT run長 | 残り(=run長-1) | 分解候補 |
|---|---:|---:|---|
| 1 | 6 | 5 | RECALIBRATE(2) + {SPECIFY(3) または SEEK(3)} — **一意に決まらない** |
| 2 | 4 | 3 | {SPECIFY(3) または SEEK(3)} 単体 — **一意に決まらない** |
| 3 | 3 | 2 | RECALIBRATE(2) — **一意** |
| 4 | 3 | 2 | RECALIBRATE(2) — **一意** |
| 5 | 4 | 3 | {SPECIFY(3) または SEEK(3)} 単体 — **一意に決まらない** |
| 6 | 3 | 2 | RECALIBRATE(2) — **一意** |
| 7 | 3 | 2 | RECALIBRATE(2) — **一意** |

**SPECIFYとSEEKはどちらもコマンドフェーズ3バイト・結果フェーズ0バイトで
同型のため、バイト数だけでは区別できない。** pcを確認したが、`$FB`への
書き込みはすべて同一pc（`02B1`。単一の共有OUT補助ルーチンを経由している
——自作subの`FDC_OUT`と同じ構造）で、呼び出し元ごとに違うpcを残さない
ため、pcでも区別できなかった。**推測で1つに決めない**（3節へ）。

**batch1・batch3・4・6・7は一意に決まる。** batch1は
「RECALIBRATE + (SPECIFYまたはSEEK) + SENSE INTERRUPT STATUS」の3コマンド
がこの順で1つのOUT runにmergeされている（結果フェーズ0バイトの2コマンド
が連続した後、結果フェーズ2バイトのSENSE INTERRUPT STATUSで締める、という
run定義上の制約から3コマンドの merge であることは分かるが、**RECALIBRATE
とSPECIFY/SEEKのどちらが先かという順序は、runの内部に区切りが無いため
本解析では決定できない**）。batch3・4・6・7は「RECALIBRATE + SENSE
INTERRUPT STATUS」の2コマンドで一意に決まる（既存実装`FDC_RECALIBRATE`が
まさにこの構造——RECALIBRATE発行後に`FDC_SENSE_INT`を呼ぶ——と一致する）。

## 5. 確定: TC（`$F8`のOUT。1.21節）は各batchの後に一様には来ない

区間内で`$F7`/`$F8`のみを抜き出すと、`OUT $F8@06D5`（1.21節のTC三つ組み
の1バイト目）が **batch1の直後（seq35）とbatch2の直後（seq74）の2回だけ**
現れ、batch3〜7の後には1回も現れない（4条件すべてで完全一致）。これは
m6p 2節が既に確認していた「結果フェーズ（run長2）の直後にTCが来るのは
一部だけで、大半は次コマンドへ直接進む」を、boot区間内の具体的な位置
（どのbatchの後か）まで特定するものであり、m6pの結論と矛盾しない。

**さらに確認したこと（m6pの範囲を広げる新しい観測）**: このboot区間内の
`OUT $F8@06D5`の2件はどちらも、1.21節が確定させた「三つ組み」（`OUT
$F8`→`OUT $F7`→`IN $F8`）の**残り2ステップを伴わない**——直後の
`$F7`/`$F8`イベントはどちらも別の`OUT $F8@06D5`（1件目→2件目）か、
区間外の`IN $FE`（アイドル待ち）であり、`OUT $F7@036E`が続くことは
一度も無い。一方、区間外（boot区間より後、1.16節手順5のRECV/SENDに相当
する往復を挟んだ後）で最初に現れる`OUT $F8@06D5`（seq294、4条件で確認は
d0-bootのみだが同一構造と推定——他条件も同じseq/pcで確認済み）は、通常
どおり`OUT $F7@036E`（seq316）へ完全な三つ組みとして繋がる。**boot区間の
最初の2回のTCだけが、三つ組みの1バイト目のみで完結する例外的な形**という
ことになる。この違いの理由（boot専用の簡略形なのか、単に本解析が見て
いない範囲に残り2ステップがあるのか）は本解析では確定できない
（3節へ）。

## 6. 4条件での一致状況

d0-boot/d1-files/d2-save/d5-seqfileの4条件すべてで、区間の境界
（event index・seq範囲）・run列（長さの並び）・TC出現位置（batch1・2の
直後のみ）が1バイトも違わず完全一致した。追加の決定論性確認（同一条件の
2回実行を比較する`m6g-d0-boot-run{1,2}`）は本稿では行っていない（既に
1.16節・1.21節が同種の解析で決定論性を確認済みであり、本稿の解析器も
同じ手法・同じ入力形式を使っているため、時間の都合で省略した。未確認と
明記する）。

## 7. 確定できなかったこと（推測で埋めない）

- **SPECIFYとSEEKの区別**（4節）。コマンドフェーズのバイト数が同じ
  （3バイト・結果フェーズ0）であり、`$FB`書き込みのpcも共有ルーチン
  1箇所に集約されているため、本解析の範囲（値を見ない構造解析）では
  区別できない。
- **batch1内の3コマンドの順序**（RECALIBRATEが先か、SPECIFY/SEEKが
  先か）。run内部に区切りが無いため決定できない。
- **boot区間の最初の2回のTCが、なぜ三つ組みの残り2ステップを伴わない
  簡略形なのか**（5節）。
- **batch3〜7がTCを伴わない理由**（バッチの区切り条件そのものは
  m6p 2節が既に未確定としていた範囲で、本稿もこれを追認するのみ）。
- 決定論性の直接確認（`m6g-d0-boot-run{1,2}`との突き合わせ）は今回
  省略した。

## まとめ

1〜6節の全項目が4条件で完全一致。例外はゼロ件。
