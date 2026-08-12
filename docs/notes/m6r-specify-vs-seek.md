# M6r — 起動時FDC初期化 batch2・5 は SPECIFY か SEEK か

測定日: 2026-08-12
対象: `docs/notes/m6q-boot-fdc-sequence.md`が未確定として残した、
batch2・5（コマンドフェーズ3バイト・結果フェーズ0バイト）が
SPECIFYかSEEKかの判別。バイト数・pcでは区別できないため、μPD765A
データシートの別の規定（MSRのSeek Busyビット）を使う。

**追加測定は行っていない。** m6qと同じ4条件ログ
（`measurements/m6c-sub-{d0-boot,d1-files,d2-save,d5-seqfile}.iolog.txt.gz`）
を再解析した。今回は判定の主軸として`$FA`（MSR、制御ポート。CLAUDE.md
上「読んでよい」対象）の値を初めて使う。`$FB`（データポート）の値は
一切見ていない。

新規解析器: `tools/analyze_m6r_msr.py`。既存の`analyze_fdc_ports.py`/
`analyze_boot_fdc_sequence.py`の関数（`parse_iolog`・
`find_boot_init_window`・`segment_runs`）をそのままimportして再利用した
（二重実装しない）。

## 1. 判別の主軸 — μPD765A MSR bit3〜0（Seek Busy）

データシート公開仕様（CLAUDE.md「(a) ハードウェアの事実」）: MSR
（このプロジェクトでは`$FA`）のbit3〜0はドライブ0〜3のSeek Busy
（D0B〜D3B）。SEEK/RECALIBRATEでは対象ドライブのビットが立ち、Seek
完了後もSENSE INTERRUPT STATUSを実行するまで保持される。SPECIFYでは
立たない。

各batchの「最後のコマンドバイト送信直後〜SENSE INTERRUPT STATUSの
コマンドバイト送信直前」に読んだ`IN $FA`の値の下位4ビットを、4条件で
確認した。

```
python3 tools/analyze_m6r_msr.py d0-boot d1-files d2-save d5-seqfile
```

結果（4条件で1バイトも違わず完全一致）:

| batch | 種別（m6qでの確定/未確定） | この位置のFA下位4bit |
|---|---|---:|
| 1 | RECALIBRATE+{SPECIFYまたはSEEK}（順序未確定） | `0001`（D0B） |
| 2 | 未確定（本稿の対象） | `0001`（D0B） |
| 3 | RECALIBRATE（確定） | `0001`（D0B） |
| 4 | RECALIBRATE（確定） | `0010`（D1B） |
| 5 | 未確定（本稿の対象） | `0010`（D1B） |
| 6 | RECALIBRATE（確定） | `0010`（D1B） |
| 7 | RECALIBRATE（確定） | `0100`（D2B） |

## 2. 対照群の検証（先に確認）

対照群として使えるのはbatch3・4・6・7（RECALIBRATE、m6qで一意に確定
済み）。これらは全件、対応するドライブのビットが立っている
（batch3/4→D0B/D1B、batch6/7→D1B/D2B）。**さらに、区間内の全55件の
`IN $FA`を通しで見ると、SENSE INTERRUPT STATUSの結果読み出し直後は
必ず下位4bitが`0000`に戻る**（例: batch1のSENSE INT結果読み後
`seq31,33`は`0xd0`＝下位4bit`0000`。全batch共通）。つまり「コマンド
実行中はビットが立ち、SENSE INTで消える」というデータシートの規定
どおりにビットが実際にトグルすることを、RECALIBRATE対照群で先に確認
できた。**対照群が期待どおりの挙動を示したので、この軸を判定根拠として
採用する。**

## 3. batch2・5の判定 — SEEK

batch2は直前のbatch1がすでにSENSE INTERRUPT STATUSでドライブ0の
保留状態を消しているにもかかわらず、**batch2自身の最後のコマンド
バイト送信後にD0Bが立っている**。SPECIFYはどのドライブのビットも
立てないコマンドなので、SPECIFYであればここは`0000`のままのはずである
（対照群で確認した「ビットは実際にトグルする」という前提のもとでは、
何もしなければ立たない）。**D0Bが立つのはSEEKまたはRECALIBRATE以外に
説明がなく、batch2はRECALIBRATEではない（m6qでRECALIBRATE候補は
batch3・4・6・7で使い切っており、byte数の分解上batch2はRECALIBRATE単体
にはなり得ない）ので、SEEKと判定する。** batch5も同型の理由で
SEEK（対象ドライブ1）と判定する。

**ドライブ単位のグルーピングも整合する**: batch1・2・3がドライブ0
（RECALIBRATE混在+SEEK+RECALIBRATE）、batch4・5・6がドライブ1
（RECALIBRATE+SEEK+RECALIBRATE）、batch7がドライブ2（RECALIBRATE単体）
という3ドライブ分の初期化列に読める。各ドライブで「RECALIBRATE →
SEEK → RECALIBRATE」という順（またはbatch1内の順序不明を踏まえた同型
の並び）は、起動時にヘッドを一度動かして media 検出等を行い、最後に
基準位置へ戻す、という一般的なFDC初期化の流れとして矛盾しない
（推測ではなく、構造とビットパターンの整合性としての傍証）。

**batch1内の順序（RECALIBRATE先かSPECIFY/SEEK先か）は本稿でも決定
できない。** batch1は最初のコマンドであり、その直前のドライブ0の
ビット状態はリセット直後で`0000`と仮定できるが、RECALIBRATEと
SEEK/SPECIFYのどちらが先でも、2つ目のコマンド実行後の時点ではD0Bは
「立っている（SEEKが関与）」か「RECALIBRATEの分がまだ残っている」かの
どちらでも同じ観測（`0001`）になり、順序では区別がつかない。3節
（未確定）にそのまま残す。

## 4. 補助的な筋道との整合（決め手にはしない）

**実行時間**: `last_cmd`（最終コマンドバイト送信）から`sense_int_cmd`
（SENSE INTコマンドバイト送信）までの共通クロック差を全batchで比較
すると、batch1〜7すべてclock差=3で完全に同一だった（d0-boot）。
これは「ROMが機械的完了を待たずに次のコマンドを送っている」という
課題文の注記どおりで、**SEEKかRECALIBRATEかを区別する情報を含まない**
（差別化なし。補強にも反証にもならない、想定どおりの結果）。

**「SPECIFYの直後にSENSE INTを出す動機は薄い」論拠**: 課題文の指示
どおり判定に使っていない。

## 5. SEEKの目標シリンダ番号は main へ渡らない

batch2・batch5のSENSE INTERRUPT STATUS結果読み出し（`IN $FB`×2）の
直後のsubの次のアクセスを確認した（4条件同一構造）:

```
...
IN  $FB (SENSE INT結果2バイト目, pc=02A1)
IN  $FA (ポーリング)
OUT $FB (次のbatchの最初のコマンドバイト, pc=02B1)   ← 直後に次コマンド
```

batch2→batch3、batch5→batch6のどちらも、結果読み出しの直後は
**即座に次のFDCコマンド送信**であり、`$FD`/`$FC`へのOUT（mainへの
応答経路、1.14節）も`$FE`ハンドシェイクへの遷移も一度も挟まない。
つまりSENSE INTERRUPT STATUSの結果（ST0/PCN）は、boot区間内では
sub内部で完結し、**mainへは渡らない**。

さらに、これは「観測していないから渡らないと仮定する」という弱い
主張ではなく、**構造的な裏付けがある**: batch2（ドライブ0のSEEK）の
直後にbatch3（ドライブ0のRECALIBRATE）が続き、batch5（ドライブ1の
SEEK）の直後にbatch6（ドライブ1のRECALIBRATE）が続く。RECALIBRATEは
無条件にトラック0へ戻すコマンドであり、**直前のSEEKがどのシリンダを
指定していたかに関わらず、batch3・batch6の完了時点でドライブの物理
位置はトラック0に確定する**。つまりSEEKの目標シリンダの値は、
起動シーケンスの最終的な観測可能状態（区間終了時のドライブ位置）に
一切影響しない。

**限界**: これは「区間内で観測した範囲」と「batch3・batch6が実際に
実行される」ことに依存する結論である。区間外（1.17節以降）でmainが
何らかの経路でこの中間シリンダ位置に依存する処理をしている可能性は
本稿では確認していない（構造上、区間終了後は$FE/$FFのアイドル待ちに
入ることをm6qが確認済みであり、そこから先はこの区間のSEEK結果を
参照する経路が無いと考えられるが、これは「未確認」であって「確認して
否定した」わけではない）。

## まとめ

- batch2・batch5: **SEEK**と判定（主軸のMSR bit判定。対照群
  batch3/4/6/7で先に方法の妥当性を確認済み）。
- batch1内の順序: 未確定のまま（3節）。
- SEEKの目標シリンダ値: mainへ渡らず、直後のRECALIBRATEで上書き
  されるため、**実装上は任意の値で構造的に等価**（5節の限界を含めて
  仕様書に明記する）。
