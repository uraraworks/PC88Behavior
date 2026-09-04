# m7gi: 残り6箇所の探針 — 段階1（到達可能性）・段階2（B:軸clear）の結果

実施日: 2026-09-04

## 位置づけ

[m7gh](m7gh-remaining-callers-staged-preregistration.md)が事前登録した
段階1・段階2の測定結果である。実装は`m7gc`が既に入れたコミット
`24d7e62`の`--probe-site`/`--probe-mode`をそのまま使い、`src/`・`tools/`
はいずれも変更していない。事前登録した合格条件・分類・判定規則は測定後
も動かしていない。

測定: general_read_requestが7本のB:候補すべてでbit0=1（奇数）を示し、
奇数条件を初めて確保した

## 測定条件・ROM整合性

- ROM: `private/rom`（公式一式）に`src/l3_service/make_subrom.py`で生成
  した自作サブROMを差し替えた混成（`tools/lib_l3_measure.sh`の
  `build_mixed_rom`、`--probe-site`/`--probe-mode`を追加引数として渡す）。
- 条件R（読み出し系5箇所）: A:に`disk#8`（＝`N88_FE.D88`）、B:に候補
  ディスクの使い捨て複製、`--type-at 300 --type '\n' --type-at 700
  --type 'FILES 2\n'`、`--frames 3000`。
- 条件W（書き込み系1箇所）: `disk#8`の使い捨て複製のライトプロテクトを
  外し、`--type-at 300 --type '\n' --type-at 700 --type '10 PRINT
  "T"\nSAVE"TQ"\n'`、`--frames 4200`。B:ディスクは使わない。
- 全12個の混成ROM（baseline 1 + cyl 6 + clear 5）のサブROM SHA-256は
  相互にすべて異なり、baselineとも異なることをビルド直後と全測定終了後
  の両方で確認した（測定中にROMディレクトリが上書き・混同されていない
  ことの確認）。
- 全runでI/Oログの取りこぼしは0件だった（`^# 取りこぼし: [1-9][0-9]*件`
  にマッチする行は無し）。SKIP・リトライ失敗も0件だった。
- **フォアグラウンドで実行した。測定中に`git stash`・ブランチ切替・
  ファイル編集は行っていない。**

## 判定規則をベースラインへ先に当てた結果

- 条件R（B:=`disk#8`自身の複製）: baseline 2run同士に`compare_l3_entry_
  fdc.py --after-frame 0 --list-all-stages`・`check_l3_screen_output.py
  --compare-report`を適用し、FDCコマンド種別列・ポート値列とも「最初の
  差: なし」、`screen_compare=match`、rc=0を確認した。
- 条件W: 同様にbaseline 2run同士で「最初の差: なし」・`screen_compare=
  match`・rc=0を確認した。
- **判定規則自体はベースライン同士では偽陽性を作らないことを確認した
  うえで、注入版の比較へ進んだ。**

## 段階1: `cyl`による到達可能性

| 箇所 | 条件 | FDCコマンド種別 | FDCポート値列 | 画面比較 | 判定 |
|---|---|---|---|---|---|
| `general_read_request` | R | 72件目で不一致（混成が短い） | 差あり | mismatch | **到達** |
| `bulk_read_do` | R | 52件目で不一致 | 差あり | mismatch | **到達** |
| `recv_dispatch_hdr_done` | R | 一致（全長一致） | **差なし** | match | **未到達（P3）** |
| `exchange11_fallthrough` | R | 32件目で不一致 | 差あり | mismatch | **到達** |
| `exchange14_prepare_first_read` | R | 一致（全長一致・READ DATA件数も16=16） | **差あり**（886件目） | match | **到達**（コマンド種別・画面は一致するが、ポート値列の水準で差が出た） |
| `recv_dispatch_write_sector` | W | 85件目で不一致（混成が短い） | 差あり | match（画面は一致） | **到達** |

5箇所が到達、1箇所（`recv_dispatch_hdr_done`）が未到達（P3）と判定した。
未到達箇所には段階2の`clear`を当てていない（「差なし＝安全」とは読んで
いない。単に到達検査を通らなかったので解釈対象から外した）。

`exchange14_prepare_first_read`は、FDCコマンド種別列・READ DATA件数・
画面出力のいずれもベースラインと一致したが、FDCポート値列だけが886件目
から差を示した。これは`m7gc`の到達判定基準（`cyl`が末端に差を出すか）に
おける「末端」をFDCポート値列の水準まで含めて判定した結果であり、恣意的
な例外扱いはしていない。

### 決定論性（段階1）

到達が確認できた5箇所は、いずれも`cyl`注入版を2run新規測定し、
`redact`相当の全イベント列SHA-256（`# main`以降を抽出したもの、値は
含まない一致判定のみ）が2run間で一致した。**未到達（`recv_dispatch_
hdr_done`）は差が出なかったため1runにとどめた**（事前登録の基準
「差が出た条件は2run」に従った結果、これのみ1run）。

## 段階2: 到達した5箇所への`clear`（B:の7本を条件軸）

B:候補7本（`disk#1`・`#2`・`#4`・`#5`・`#7`・`#9`・`#10`。`disk#10`を
各箇所で最初に当てた）について、`clear`（bit0を0へ強制）を、同じB:
ディスクを使ったベースライン（注入なし、bit0は自然値のまま）と比較した。

| 箇所 | disk#10 | disk#1 | disk#2 | disk#4 | disk#5 | disk#7 | disk#9 |
|---|---|---|---|---|---|---|---|
| `general_read_request` | **相違** | **相違** | **相違** | **相違** | **相違** | **相違** | **相違** |
| `bulk_read_do` | 一致 | 一致 | 一致 | 一致 | 一致 | 一致 | 一致 |
| `exchange11_fallthrough` | 一致 | 一致 | 一致 | 一致 | 一致 | 一致 | 一致 |
| `exchange14_prepare_first_read` | 一致 | 一致 | 一致 | 一致 | 一致 | 一致 | 一致 |

`recv_dispatch_write_sector`（WRITE経路）は、条件WがB:ディスクを使わない
単一ディスク構成のため、B:の7本という条件軸をそのまま適用できなかった
（`m7gh`で事前に留保した点）。条件W（B:軸なし、単一の書き込みシナリオ）
だけで`clear`を当てたところ、FDCコマンド種別列・ポート値列・WRITE DATA
件数（8=8）・画面出力のすべてでベースラインと一致した（bit0を0へ強制
しても変化なし）。

### 決定論性（段階2）

- `general_read_request`の`disk#10`条件（相違が出た7条件のうち、親の
  指示で最優先とされた条件）は、ベースライン・`clear`注入版とも2run
  新規測定し、全イベント列SHA-256が自己一致した。
- `general_read_request`の`disk#1`・`#2`・`#4`・`#5`・`#7`・`#9`の6条件
  （いずれも相違が出た）は、**1runにとどめた**。事前登録の基準「差が
  出た条件は2run」を厳密には満たしていない。7条件すべてが同じ方向
  （相違）を示す一貫した結果だったため、`disk#10`での2run自己一致確認
  を代表として決定論性の傍証にしたが、残り6条件individually の2run
  確認は行っていない。**この6条件は未確認のまま「相違」と報告する。**
- `bulk_read_do`・`exchange11_fallthrough`・`exchange14_prepare_first_
  read`の各7条件（いずれも一致）、および`recv_dispatch_write_sector`の
  条件Wは、事前登録の基準どおり差が出なかったため1runにとどめた。

## 奇数条件が見つかったか

**見つかった。** `general_read_request`（読み出し系、FILES 2経路）で、
B:候補7本すべて（`disk#1`・`#2`・`#4`・`#5`・`#7`・`#9`・`#10`）において
`clear`（`REQ_HDR+2`のbit0を0へ強制）がベースライン（bit0は自然値の
まま）と相違した。これは、この注入位置・この測定条件（A:=`disk#8`起動、
B:=候補、`FILES 2`打鍵、`--frames 3000`）では、**`REQ_HDR+2`のbit0は
自然状態で1（奇数相当）であり、`clear`による0への強制が実効的な変化を
生んだ**、という観察と整合する。`m7fz`の交換#6・`m7gb`の探索がいずれも
偶数条件しか確保できていなかったのに対し、**本稿は奇数条件を初めて
確保した。**

他の3箇所（`bulk_read_do`・`exchange11_fallthrough`・`exchange14_
prepare_first_read`）は、同じ7本のB:候補すべてで`clear`がベースライン
と一致しており、これらの箇所・この測定条件ではbit0は自然状態で0
（偶数相当）である、という観察になる。

## 言えること・言えないこと

**言えること:**

- 6箇所中5箇所（`general_read_request`・`bulk_read_do`・
  `recv_dispatch_hdr_done`を除く4箇所＋`recv_dispatch_write_sector`）
  への到達可能性を、`cyl`陽性対照によって測定的に判定した。
  `recv_dispatch_hdr_done`は本条件（条件R）では到達しない（P3）。
- `general_read_request`は、B:の7本すべてで`clear`がベースラインと
  相違し、この条件ではbit0が自然状態で1（奇数）であることを示した。
- `bulk_read_do`・`exchange11_fallthrough`・`exchange14_prepare_first_
  read`は、同じ7本すべてで`clear`がベースラインと一致し、bit0が自然
  状態で0（偶数）であることを示した。
- `recv_dispatch_write_sector`は到達したが、B:ディスクの内容が末端に
  影響しない書き込み経路である（`clear`を当てても唯一の測定条件で
  変化が無かった）ため、この箇所についてbit0が奇数か偶数かは判定材料
  が単一条件しかなく、他の5箇所ほど確度が高くない。

**言えないこと:**

- `set`（bit0を1へ強制）は本稿では測っていない。したがって`general_
  read_request`がP1（bit0=1が実際に効く/壊れる）なのかP4（現状は
  bit0=1で動いているが、強制的に1にしても壊れない）なのかは、本稿では
  区別していない。次稿の課題として残す。
- `general_read_request`のうち`disk#10`以外の6条件（`disk#1`・`#2`・
  `#4`・`#5`・`#7`・`#9`）は、事前登録した「差が出た条件は2run」の
  基準を個別には満たしていない（1runにとどめた）。7条件が同じ方向を
  示した一貫性は決定論性の直接確認ではない。
- `recv_dispatch_write_sector`のB:依存性は、本条件（`SAVE"TQ"`、
  ファイル名のみでドライブ指定なし）では検出できなかった。SAVE時に
  ドライブ番号を明示する打鍵（構文が特定できていない）を使えば別の
  結果になる可能性があるが、本稿では試していない。
- 公式ROMとの比較（段階3）は本稿では実施していない。`general_read_
  request`で見つかった奇数条件が、公式ROMの実際の挙動と一致するか
  どうかは未検証である。
- 他の起動条件・ディスク・打鍵タイミングでの挙動は測っていない。
  本稿は条件R（`FILES 2`、`--frames 3000`、A:=`disk#8`）と条件W
  （`SAVE"TQ"`、`--frames 4200`）の2条件だけで測定した。
- データポート値列そのもの（値）、画面本文、公式ディスクの実データは
  見ていない・記録していない。

## 開示

手順上の逸脱・汚染は無かった。測定はすべてフォアグラウンドで実行し、
測定中に`git stash`・ブランチ切替・ファイル編集は行っていない。SKIP・
リトライ失敗は0件だった。実ファイル名は端末出力・本稿・コミット
メッセージのいずれにも表示・転記していない（`private/disk`の列挙は
`tools/lib_screen_boot_disks.sh`の`list_disk_basenames`/`digest_
basename`のみを使い、basenameを`echo`で表示する操作は一度も行って
いない）。

## 検証

`tools/check_cleanroom.sh`は全項目OK、rc=0。`git status`で`private/`
由来の混入・生ログ・ROM像が無いことを確認した。`src/`・`tools/`は本稿
では変更していない。生ログ・混成ROM一式はリポジトリ外（scratchpad配下）
に置き、コミットしていない。

## 情報境界 / 根拠リンク

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容（実ファイル名を含む）は読んでいない・出していない。記録したのは
公開FDCコマンド種別名、件数、一致prefix件数、最初の差の位置番号（値では
ない）、画面出力の行数・文字数・SHA-256、rc、ディスクの通し番号・
ダイジェストだけである。

根拠（`ls`で存在確認済み）:
[m7gh](m7gh-remaining-callers-staged-preregistration.md)・
[m7gc](m7gc-remaining-callers-probe-preregistration.md)・
[m7gg](m7gg-data-disk-screening.md)・
[m7gf](m7gf-disk3-exchange6-results.md)・
[m7fz](m7fz-exchange6-drive-bit-results.md)・
`docs/spec/l3-subrom.md` 1.32節・1.33節・1.34節・1.35節・1.36節・
1.46節・1.56節・自作`src/l3_service/make_subrom.py`（コミット
`24d7e62`）・`tools/conform_l3.sh`・`tools/lib_l3_measure.sh`・
`tools/compare_l3_entry_fdc.py`・`tools/check_l3_screen_output.py`・
`tools/hash_write_stream.py`・`tools/lib_screen_boot_disks.sh`。
