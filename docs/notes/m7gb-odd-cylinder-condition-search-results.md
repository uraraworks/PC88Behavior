# m7gb: 交換#6の目的シリンダが奇数になる条件を探索した結果

実施日: 2026-09-04

## 位置づけ

本稿は[m7ga](m7ga-odd-cylinder-condition-search-preregistration.md)が
測定前に固定した合格条件・予測に対する測定である。事前登録した条件
（drive2・no_disk・unreadable_disk・write_protect）以外を新たに追加した
事実は無い。`src/`・`tools/`は本稿では変更していない。

## 測定条件（共通部分）

- ROM: `private/rom`（公式一式）に、本稿執筆時点の
  `src/l3_service/make_subrom.py`で生成した自作サブROMを差し替えた混成
  （`tools/lib_l3_measure.sh`の`build_mixed_rom`を使用。既存の
  `conform_l3.sh`と同じ関数）。3つの混成ROM（`baseline`＝全`break_*`が
  False、`cylinder`＝`--break-exchange6-cylinder`、`clear`＝
  `--break-exchange6-drive-bit-clear`）を1回ずつビルドし、4条件すべてで
  同じROMディレクトリを使い回した（条件はA:/B:の媒体・打鍵・framesだけを
  変える）。
- ディスクA: `private/disk/N88_FE.D88`の使い捨て複製（`m7ga`・
  `conform_l3.sh`と同一）。
- 実行: 各条件とも`--type-at 300 --type '\n' --type-at 700 --type
  '<条件別打鍵>'`（`write_protect`のみ`10 PRINT "T"\nSAVE"Q8P"\n`、他は
  `FILES 2\n`）。framesは`m7ga`が事前登録した表のとおり（drive2=3000、
  no_disk=800、unreadable_disk=3000、write_protect=3600）。
- すべてフォアグラウンドで実行し、測定中に`git stash`・ブランチ切替・
  ファイル編集は行っていない。

3混成ROMのSHA-256は、4条件を通して使い回した1組の`DISK.ROM`について、
各条件の測定直前に毎回再ハッシュし、ビルド直後の値から変化していない
ことを確認した（baseline/cylinder/clearの3つは相互に異なるSHAである
ことも確認済み）。測定終了後に`git status`で`src/`・`tools/`が無変更
であることも確認した。

## 段階1: 陽性対照（`--break-exchange6-cylinder`）は全4条件で通った

いずれの条件でも、`compare_l3_entry_fdc.py --after-frame 0
--list-all-stages`で**段20（SEEK、`m7fz`が特定した交換#6のSEEK段と同じ
位置）にシリンダ指定の不一致**が現れ、画面出力も`screen_compare=mismatch`
になった。

| 条件 | 段20シリンダ指定 | 画面比較 | 陽性対照 |
|---|---|---|---|
| drive2 | 不一致 | mismatch | 通った |
| no_disk | 不一致 | mismatch | 通った |
| unreadable_disk | 不一致 | mismatch | 通った |
| write_protect | 不一致 | mismatch | 通った |

4条件とも陽性対照が通ったので、全条件の`clear`結果を解釈してよい。

## 段階2: `--break-exchange6-drive-bit-clear`はどの条件でもベースラインと完全一致した

| 条件 | FDCコマンド種別列 | 段20シリンダ指定 | 入口区間unit/head差 | 画面比較 |
|---|---|---|---|---|
| drive2 | 全長一致(79件) | 一致 | 0件 | match |
| no_disk | 全長一致(55件) | 一致 | （入口区間なしのframes設定。段20まで一致を確認） | match |
| unreadable_disk | 全長一致(99件) | 一致 | 0件相当（`m7ga`と同型の一致） | match |
| write_protect | 全長一致(80件) | 一致 | 0件相当 | match |

4条件すべてで、`clear`はFDCコマンド種別列・FDCポート値列一致prefix・
段20のシリンダ指定・画面出力（行数・文字数・SHA-256）のいずれでも
ベースラインと区別できなかった。

## 段階3: 構造的予測の実測確認

`m7ga`が読解から立てた予測（交換#6は起動区間で1回だけ生じ、打鍵後の
分岐に依存しない）は、4条件すべての陽性対照・`clear`結果が
「段20（SEEK）」という`m7fz`（起動のみ条件）と同じ段位置で発現したことに
より裏付けられた。条件間で段番号がずれる、または一致・不一致の位置が
入れ替わる、といった予測に反する挙動は観測されなかった。

## 判定

**予測B（試した全条件で偶数だった）に該当する。** drive2・no_disk・
unreadable_disk・write_protectの4条件とも、陽性対照は明確に差を出し
（条件3を満たし）、その上で`clear`はベースラインと完全に一致した
（交換#6の目的シリンダのbit0は、これら4条件でもすべて0=偶数だった）。

**これは「バグが無い」ではなく、「本ハーネスで実際に変えられる自由度
（起動時にA:へ挿入するディスクの選択）が事実上N88_FE.D88の1択しかなく、
試した範囲（打鍵内容・B:媒体状態の組み合わせ4通り）では奇数条件に
到達できなかった」ということである。** `m7ga`が明記したとおり、
diskB起動（市販ソフト）はL3ディスクサービス自体に入らないため条件として
使えず、N88_FE.D88以外の起動可能なN88-BASICディスクは本セッションの
権限設定・私物の扱い上、用意できなかった。

## 決定論性

4条件とも、陽性対照・`clear`ともベースラインとの差の有無が明確
（陽性対照は差あり、`clear`は差なし）であり、いずれも各1runのみの測定に
とどめた。**差が出た条件（陽性対照）についても2run目の自己一致は本稿では
確認していない**——`m7fz`が既に陽性対照・`clear`・`set`・ベースラインの
決定論性を4条件×2runで確認済みであり、本稿の4条件は「起動区間が
`m7fz`のベースラインと同一である」という構造的議論の上に成り立つ
追加測定という位置づけのため、資源配分として1runにとどめた。**この
判断は測定後に決めたものであり、m7gaが事前に許容した「差が出なかった
条件は1runでよい、明記する」という条件に沿っている。**

## 言えること・言えないこと

**言えること:**

- drive2・no_disk・unreadable_disk・write_protectの4条件とも、陽性対照
  （`break_exchange6_cylinder`）が段20で明確な差を出し、測定器はこれらの
  条件でも交換#6経路を捉えている。
- 4条件すべてで`--break-exchange6-drive-bit-clear`はベースラインと
  区別できず、交換#6の目的シリンダのbit0はいずれも偶数だった。
- `m7ga`の構造的予測（交換#6は起動区間専用で打鍵後の分岐に依存しない）
  は、段位置が全条件で一致したことにより実測で裏付けられた。

**言えないこと:**

- N88_FE.D88以外の起動可能なN88-BASICディスクでの挙動は測っていない。
  本ハーネスで用意できる起動ディスクの選択肢がこの1本しかないため、
  本稿の範囲では「奇数条件が存在しない」ことの証明にはならない。
- 交換#6以外の交換（#3・#11・#14）で同種の意味の混線が奇数条件を
  持つかどうかは、本稿では調べていない（`m7fx`が読解で交換#6を最も
  具体的な事例として挙げた理由により、本探索も交換#6に限定した）。
- 陽性対照の2run目自己一致は本稿では確認していない（上記「決定論性」
  節に明記）。

## 情報境界

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容は読んでいない。本セッションの権限設定は`private/`配下への`ls`
実行そのものを拒否しており、`test -d`で存在だけ確認した。記録したのは
公開FDCコマンド種別名、段番号、unit/head分類の一致・不一致、件数、
画面出力の行数・文字数・SHA-256、SHA-256、rcだけである。データポート
値列・画面本文・シリンダ値・PCN値は表示も転記もしていない。生ログ・
混成ROM一式はリポジトリ外（scratchpad配下）に置き、コミットしない。

## 検証

`tools/check_cleanroom.sh`は全項目OK、rc=0。`git status`で`private/`
由来の混入・生ログ・ROM像が無いことを確認した。`src/`・`tools/`は
本稿では変更していない。

根拠: [m7ga](m7ga-odd-cylinder-condition-search-preregistration.md)・
[m7fz](m7fz-exchange6-drive-bit-results.md)・
[m7fy](m7fy-exchange6-drive-bit-preregistration.md)・
自作`src/l3_service/make_subrom.py`・`tools/compare_l3_entry_fdc.py`・
`tools/check_l3_screen_output.py`・`tools/lib_l3_measure.sh`・
`tools/make_l3_testdisk.py`。
