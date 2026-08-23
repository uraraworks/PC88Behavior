# m7ca: サブROMの挙動不変容量圧縮

## 情報境界

この作業は `CLAUDE.md` の情報境界を守り、`docs/spec/`、既存の自作実装、
自作ROM・自作main・自作ディスクによる自己検証だけを用いた。公式ROM・公式
ディスクのバイト列は読まず、出力せず、保存していない。`PC88_REF_ROM_DIR` と
`PC88_REF_DISK_DIR` は未設定であり、`private/` は参照していない。比較用ログは
自作物だけから一時ディレクトリへ生成し、コミット対象に含めていない。

前回 `m7bz-save-reachability.md` の「実装と容量」にある、AF保存除去、SENSE
INTERRUPT末尾の `RET Z` / `JP` 化、起動時RAMゼロ化ループの3件とは重複しない。
既定値、`BULK_READ_INTERVENTION_LIMIT`、故障注入、生成される機能構成、判定条件、
期待値は変更していない。

## 圧縮項目と容量

| 圧縮 | 削減 |
|---|---:|
| `FDC_BEGIN`にコマンド先頭バイト送出を統合 | 20バイト |
| 起動FDC列で保持済みE（ドライブ番号）を再利用 | 8バイト |
| 高速バルク5入口の開始・終了列と位置1/2本体を共有 | 36バイト |
| **合計** | **64バイト** |

`python3 src/l3_service/make_subrom.py <一時出力先>` と、自己検証と同じ
`--force-post-bulk-active` の両経路で実測し、いずれもコード長は
**2046/2048バイトから1982/2048バイト**になった。空きは2バイトから66バイトへ
増えた。

## 挙動不変の根拠と全呼出元監査

### 1. `FDC_BEGIN`への先頭バイト送出統合（20バイト）

旧列は全呼出元で `CALL FDC_BEGIN; LD A,command; CALL FDC_OUT` だった。新列は
`LD A,command; CALL FDC_BEGIN` とし、`FDC_BEGIN`がAFを一時保存して従来どおり
`FDC_ABORT`と`WINDOW_RUN_POS`を0にした後、AFを戻して`FDC_OUT`へ末尾JPする。
従って、RAM書き込み順、FDCの待ち・中断条件、`OUT $FB`の値と位置、復帰時の
A/DE/HL/BC、スタック最終状態は同じである。

全8呼出元は次のとおり。

- `FDC_SPECIFY`: 先頭値`0x03`。復帰後は従来と同じ第2・第3バイトを送る。
- `FDC_SENSE_INT`: 先頭値`0x08`。復帰後は直ちに`FDC_IN`し、Aを上書きする。
- `FDC_RECALIBRATE`: 先頭値`0x07`。復帰後はEからunitをロードして送る。
- `FDC_SENSE_DRIVE_STATUS`: 先頭値`0x04`。復帰後はA=0のunitを送る。
- `FDC_SEEK`: 目的Cは入口の`PUSH AF`で別に保持済み。先頭値`0x0F`の送出後、
  Eからunitを送り、保存した目的Cを復元するため、AFの意味も変わらない。
- `FDC_WRITE_SECTOR`: 先頭値`0x45`。復帰後は従来と同じWRITEパラメータ列へ進む。
- `FDC_READ_SECTOR`: 先頭値`0x46`。復帰後は従来と同じ単一READパラメータ列へ進む。
- `FDC_READ_BULK`: 先頭値`0x46`。復帰後は従来と同じ複数READパラメータ列へ進む。

故障注入版も同じ8入口を通る。`FDC_BEGIN`のクリアと`FDC_OUT`の中断判定の間に
新しい分岐はなく、`--break-fdc-timeout-reads-anyway`等の検出条件は変えていない。

### 2. 起動FDC列のE再利用（8バイト）

起動batch1でE=0、batch4でE=1をロードした後、同じドライブを使う直後の
SEEK/RECALIBRATEにあった計4個の冗長な`LD E,n`（各2バイト）を除いた。

全区間を監査すると、E=0の再利用箇所はbatch2 SEEKとbatch3 RECALIBRATE、
E=1はbatch5 SEEKとbatch6 RECALIBRATEである。間に現れる
`FDC_RECALIBRATE`、`FDC_SEEK`、`FDC_SENSE_INT`、`FDC_BEGIN`、`FDC_IN`、
`FDC_OUT`は、DEを変更する場合に必ずpush/popで復元する。単発`OUT $F8`はAだけを
変更する。故障注入`inject_spurious_sense_int`で追加される`FDC_SENSE_INT`もDEを
保存する。従って各再利用点のEは旧即値と同じで、FDCコマンド列も同じである。

### 3. 高速バルク送信5入口の共有（36バイト）

旧5入口に重複していた
`WAIT_FE_RECV_ACK_DONE`→`OUT $FF,09`→`WAIT_FE_RECV_DATA_READY`を
`BULK_SEND_BEGIN`へ共有した。通常終端の`OUT $FF,08`→
`WAIT_FE_RECV_ACK_DONE`は`BULK_SEND_END`へ共有した。位置1/2は、その間も
「定数を`$FC`へ、0を`$FD`へ出す」点が同一なので、定数Aだけを入口で選び
`BULK_SEND_CONST`へ共有した。

全5入口の監査は次のとおり。

- `BULK_SEND_ONE`: BEGIN直後にHLを進めてAをロードするため、BEGINの最終Aは
  旧来どおり不使用。2チャネル出力後はENDへ末尾JPし、HLの進みも同じ。
- `BULK_SEND_POSITION3`: BEGIN直後に`(HL)`をAへロードする。2チャネル出力と
  `INC HL`後にENDへ進み、A/HLとI/O順は同じ。
- `BULK_SEND_FINAL_DUPLICATE`: BEGIN直後に`(HL)`をロードする。終端固有の
  `OUT $FF,08`→`OUT $FF,91`は共有ENDへ入れず従来位置に残した。
- `BULK_SEND_POSITION1`: 定数をAF保存してBEGINを呼び、復元後に従来と同じ
  `$FC=観測応答、$FD=0`を出しENDへ進む。
- `BULK_SEND_POSITION2`: 上と同じ経路で、入口定数だけが従来値`5632/256`。

BEGIN/ENDはBC/DE/HLに触れない。BEGINのCALL/RETと各入口のCALL、ENDへの末尾JPは
最終スタックを変えず、待ちのビット条件、ポート、値、回数、順序を変えない。

## 検証

### 圧縮前後I/O比較

圧縮前生成器を一時保存し、圧縮前後それぞれについて、自己検証と同じ自作main、
自作テストディスク、要求`0:1,3:5,7:8`、120フレームでI/Oログを保存した。
生ログは一時出力パスと、圧縮で移動する発行元PC列が異なるため、そのままでは
差分ゼロではない。発行元PCを挙動と誤認せず、全イベントから
`seq, clock, frame, cpu, IN/OUT, port, value`を抽出して比較したところ、
**10,832件対10,832件で差分ゼロ**だった。

### 自己検証層

圧縮後の`tools/verify_l3.sh`はrc=0。通常READ、割り込み後復帰、0F省略run、
SENSE INTERRUPT可変結果数、タイムアウト中断、2+1+5 run、バルク後READ、WRITEの
窓・座標・応答がすべて成功した。既存の全故障注入（dispatch復帰、run継続、
応答反転、SENSE結果数、タイムアウト後読出し、固定長打切り、旧READ種別判別、
WRITE窓、WRITE座標、WRITE応答）は引き続き不一致、未達、または症状ありとして
検出され、壊した版が合格した項目は0件だった。

`tools/run_all_selftests.sh`を外側の`LC_ALL=C`と`LC_ALL=ja_JP.UTF-8`で実行した。
両方ともラッパrc=0、全32項目のrcは期待値0、NG 0件、Traceback 0件だった。
公式環境を必要とする`tools/conform_l3.sh`だけは両方で
`SKIP(公式環境なし。本体未実行、自己検査のみrc=0)`、残る31項目はOKで、
それ以外の本体SKIPは0件だった。

### 走らせられなかった検証

公式ROM・公式ディスク用環境変数が未設定のため、`tools/conform_l3.sh`の本体は
実行していない。従って適合条件1・5の公式環境実走を今回の合格とは主張しない。
同じ理由で、公式環境が必要な条件4も今回のセッションでは未実行である。
`verify_l3.sh`自身が明示する、高速バルクの公式5635件比較とWRITE後のディスク
再読出しも判定不能のままであり、合格扱いしていない。
