# m7lv — QUASI88ではST3 bit3（TWO SIDE）が媒体の有無を表し、READYは媒体なしでも1

日付: 2026-09-12
HEAD: 393d8ec
駆動方式: モード0（既定、`q88_sub_cpu_mode`未指定）
フレーム数: `--frames 900`

事前登録のない測定である。`tools/analyze_no_disk_signals.py`の`load`・`status_samples`・
`bit_domain`をリポジトリ外の使い捨てスクリプトから呼んだ。

## 位置づけ

`m7lu`（1.62節）は、公式subが一般READ要求の5バイト目の後でドライブの準備待ちに入り、
自作subにも同じ待ちを持たせる方針をユーザーが決めたことを記録した。その待ちを自作subに
実装するには「準備ができた」をどう検出するかが要る。本稿はこのエミュレータ（QUASI88）の
`SENSE DRIVE STATUS`のST3が、媒体の有無でどう変わるかを測る。

## 実測

混成（公式main＋自作sub）、駆動方式モード0、900フレーム。frame 700以降に現れる
`SENSE DRIVE STATUS`のST3を対象に、各ビットへ現れた値の集合（`bit_domain`）を取った。

- B:媒体なし（no_disk、標本1件）
- B:自作テスト用ディスク入り（unreadable_diskの場面、`tools/make_l3_testdisk.py`の
  既定＝片面、標本12件）

| bit | 意味 | no_disk | 自作ディスク入り |
|---|---|---|---|
| 7 | FAULT | {0} | {0} |
| 6 | WRITE PROTECTED | {0} | {0} |
| 5 | READY | {1} | {1} |
| 4 | TRACK 0 | {0} | {0} |
| 3 | TWO SIDE | {0} | {1} |
| 2 | HEAD | {0} | {0} |
| 1 | US1 | {0} | {0} |
| 0 | US0 | {1} | {1} |

**違うのはbit3だけ。READYは媒体が無くても1のまま変わらない。**

`m7cn`（1.49節、第83版）で見えたbit6の差は、当時比べた正常B:の媒体が書き込み禁止
だったためと推定する（今回の自作ディスクはWP=0で、bit6は媒体あり側も{0}）。

## QUASI88のソースの読み

`vendor/quasi88-libretro`の`src/fdc.c`、SENSE DEVICE STATUSのST3生成
（2184〜2201行付近）。

- ドライブ番号が範囲外なら`ST3_FT`（FAULT）を立てる。
- 範囲内で、「媒体が無い（`disk_not_exist`）」**または**「媒体入れ替え直後の印
  （`disk_ex_drv`のそのドライブのビット）が立っている」ときは、READY
  （`fdc.status`由来）・TRACK 0・HEAD・USだけを組み立て、**TS（`ST3_TS`）もWP
  （`ST3_WP`）も立てない**。この分岐は同時に入れ替えの印を反転させる（＝入れ替え
  直後は1回だけこの形になり、次回は下の分岐に落ちる）。
- それ以外（媒体あり）は、READY・WP（媒体の書き込み禁止属性）・TRACK 0・
  **TS（面の数によらず常に立てる）**・HEAD・US。
- READYはどちらの分岐でも同じ`fdc.status`から取っており、媒体の有無で分かれて
  いない。

## 結論（観測とソースの読みを合わせて）

- **このエミュレータでは、ST3 bit3=1 ⇔ 媒体が入っている（入れ替え直後の1回を除く）。**
  片面媒体でも面数にかかわらずbit3=1になる（実測の自作ディスクは片面）。
- これは、公式subがunreadable_disk（片面の自作ディスク、1.58節）では待たずに
  READ DATAへ進むことと整合する。
- READYは媒体の有無で変わらないので、待ちの終わり検出にREADYは使えない。

## 言えないこと

- 実機のTWO SIDEの意味、実機のREADYの振る舞いには一般化しない
  （エミュレータで測った値はエミュレータの実装を測っている）。
- 公式subが実際にbit3を見て判断しているとは言わない——このエミュレータ上では
  bit3と「媒体あり」を区別できない、までしか言えない。
- 入れ替え直後の1回だけbit3=0になる形が、待ちの継続中に媒体を差した場合の続きに
  どう影響するかは測っていない。

## 次

`docs/notes/m7lv-no-disk-drive-wait-implementation-preregistration.md`で、自作subの
待ちを「ST3 bit3=1になるまでSEEK→SENSE DRIVE STATUSを繰り返す」形として事前登録する。
