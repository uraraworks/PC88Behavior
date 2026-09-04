# m7gv: `bulk_read_do`・交換#11・交換#14のunit指定を公式と比較した結果

実施日: 2026-09-04

## 位置づけ

[m7gu](m7gu-three-sites-unit-conformance-preregistration.md)が事前登録
した測定の結果である。`src/`・`tools/`はいずれも変更していない。事前
登録した合格条件・判定規則は測定後も動かしていない。実装は`m7gc`が既に
入れたコミットの`--probe-site`/`--probe-mode`をそのまま使った。

測定: `FILES 2`（B:読み）・`FILES 1`（A:読み）の双方、B:候補2本
（`disk#8`自身の複製・`disk#10`）で、`bulk_read_do`・交換#11
（`exchange11_fallthrough`）・交換#14（`exchange14_prepare_first_read`）
それぞれに対応する段のunit/head・シリンダ指定を公式サブROMと比較した。
**3箇所とも、全4条件で公式と完全に一致した。**

## 陽性対照（最初に書く）

`tools/verify_drive_byte2_attribution.sh`と同じ考え方で、既定の混成ROM
（条件M）と`build_mixed_rom ... --break-drive-selector`（1.46節のドライブ
指定伝播を壊す既存の故障注入）を、`FILES 2`条件・B:=`disk#8`自身の複製
で比較した。

- `compare_l3_entry_fdc.py --after-frame 0`のunit/head差件数: **21件**
  （0件より大きい）。

判定規則がunit/headの違いを実際に検出できることを確認した。**この陽性
対照が通ったため、以下の「一致」「不一致」の判定を解釈する。**

## 段の対応づけ（`cyl`注入、B:=`disk#8`自身の複製、`FILES 2`）

条件M（既定の混成ROM、探針なし）をベースラインとし、`--probe-site
<箇所> --probe-mode cyl`注入版と`compare_l3_entry_fdc.py --after-frame 0
--list-all-stages`で比較した。**その箇所だけを動かしたときに最初に
シリンダ不一致が現れる段**を、その箇所に対応する段として特定した
（`m7fz`が交換#6で使った手続きと同一）。

| 箇所 | 最初に不一致が現れた段（1起点、SEEK） |
|---|---|
| `exchange11_fallthrough` | 段24 |
| `exchange14_prepare_first_read` | 段28 |
| `bulk_read_do` | 段32 |

3箇所とも異なる段番号が得られ、出現順（交換#11→交換#14→bulk_read_do）
も呼び出し順の予想と整合した（隣接するREAD単位ブロックが4段おきに並ぶ
という`m7fz`の構造と一致）。**3箇所とも段の対応づけができた。** 対応
づけができなかった箇所は無い。

## 主指標: 公式対条件M（unit/head・シリンダ指定）

`compare_l3_entry_fdc.py --after-frame 0 --list-all-stages`で、上記3段
（段24・28・32）のシリンダ指定一致/不一致と、入口区間全体のunit/head差
件数を見た。

| 条件 | 段24(交換#11) | 段28(交換#14) | 段32(bulk_read_do) | 入口区間unit/head差件数 | 画面比較 |
|---|---|---|---|---|---|
| `FILES 1`・B:=disk#8自身 | 一致 | 一致 | 一致 | 0件 | match |
| `FILES 2`・B:=disk#8自身 | 一致 | 一致 | 一致 | 0件 | match |
| `FILES 1`・B:=disk#10 | 一致 | 一致 | 一致 | 0件 | match |
| `FILES 2`・B:=disk#10 | 一致 | 一致 | 一致 | 0件 | **mismatch**（後述） |

**3箇所とも、4条件すべてでシリンダ指定・unit/head分類が公式と完全に
一致した。**

`FILES 2`・B:=`disk#10`条件のみ、画面出力が`mismatch`だった。しかし
これは段24・28・32よりずっと後（コマンド56件目、公式=READ DATA・混成=
SEEK）で公式・混成のFDCコマンド列長が乖離したことに起因しており、
乖離の起点は段4（`general_read_request`付近のSEEK、シリンダ指定
不一致）である。この段4の不一致は本稿が対応づけた3箇所（段24・28・32）
より前に位置し、`disk#10`固有の未解決の課題（`docs/notes/
m7gs-odd-cylinder-by-layout-change-preregistration.md`・`m7gt-odd-
cylinder-by-layout-change-results.md`が扱う「配置替えでの奇数シリンダ」
系の話題と同型）と見られるが、**本稿ではこの乖離の原因を調べていない。**
段24・28・32自体は、この乖離の影響を受けずにシリンダ指定・unit/headとも
公式と一致し続けている。

## 段階2: `set`によるP1/P2/P4判定（B:=`disk#10`、`FILES 2`）

`--probe-mode set`（bit0を1へ強制）を条件Mベースライン（`disk#10`、
`FILES 2`）と比較した。

| 箇所 | `cyl`（到達） | `set`対ベースライン | `clear`対ベースライン（m7gi既測定） | 判定 |
|---|---|---|---|---|
| `exchange11_fallthrough` | 到達（本稿で再確認、段24） | **相違**（一致prefix32件で終端、unit/head差6件、画面mismatch） | 一致（`m7gi`） | **P4** |
| `exchange14_prepare_first_read` | 到達（本稿で再確認、段28） | **相違**（一致prefix52件で終端、unit/head差11件、画面mismatch） | 一致（`m7gi`） | **P4** |
| `bulk_read_do` | 到達（本稿で再確認、段32） | **相違**（一致prefix48件で終端、unit/head差8件、画面mismatch） | 一致（`m7gi`） | **P4** |

3箇所とも`cyl`が差を出し（到達）、`set`が差を出し、`clear`は差を出さ
ない——**P4（交換#6と同型）** である。これは、これらの箇所が呼び出す
`FDC_SEEK`共通入口（1.46節で恒久実装済み）が`REQ_HDR+2`のbit0を実際に
読んでおり、bit0を強制的に1にすれば挙動が変わる（＝伝播機構自体は
効いている）が、本測定条件（`FILES 2`、B:候補2本）では自然状態でbit0
が0のままである、という観察と整合する。

## C1〜C3のどれか（事前登録の枠に沿った判定）

- **C3**（陽性対照が通らない／段の対応づけができない）: **不成立。**
  陽性対照（21件差）は通り、3箇所とも段の対応づけができた。
- **C2**（いずれかが公式と食い違う）: **不成立。** 4条件×3箇所すべてで
  シリンダ指定・unit/head分類が公式と一致した。
- **C1**（3箇所とも公式と一致）: **成立。** bit0=0はこれら3箇所の本測定
  条件では公式と一致しており、1.46節の伝播（`FDC_SEEK`共通入口が
  `REQ_HDR+2`のbit0を無条件に読む構造）は、これら3箇所の呼び出し元
  それぞれに個別の伝播処理を追加しなくても、公式と同じ結果を生んでいる。

## 言えること・言えないこと

**言えること:**

- `exchange11_fallthrough`・`exchange14_prepare_first_read`・
  `bulk_read_do`の3箇所は、`FILES 1`（A:読み）・`FILES 2`（B:読み）の
  双方、B:候補2本（`disk#8`自身の複製・`disk#10`）の計4条件で、対応
  する段（段24・28・32）のシリンダ指定とunit/head分類が公式サブROMと
  完全に一致した。`m7go`がWRITE DATAで見つけたような実装欠落は、この
  3箇所には見つからなかった。
- 段の対応づけは`cyl`注入による段番号特定で3箇所とも成功し、`m7fz`の
  手続きの再現性を確認した。
- 段階2の`set`測定により、3箇所とも`cyl`到達・`set`相違・`clear`一致
  という交換#6と同型のP4分類になることを確認した。これは、探針位置が
  独立の伝播ロジックではなく`FDC_SEEK`共通入口（1.46節）を経由している
  ことと整合する。

**言えないこと:**

- `FILES 2`・`disk#10`条件で観測された段4付近のシリンダ不一致・後段の
  FDCコマンド列長乖離・画面mismatchの原因は、本稿では調べていない
  （`m7gs`/`m7gt`が扱う「配置替えでの奇数シリンダ」系の話題と同型に
  見えるが、確認していない）。
- 本稿が確認したのは`disk#8`自身の複製・`disk#10`の2本のB:候補だけで
  ある。`m7gi`が使った他のB:候補（`disk#1`・`#2`・`#4`・`#5`・`#7`・
  `#9`）では確認していない。
- `disk#10`条件（FILES1・FILES2とも）の主指標比較は1runにとどめた
  （差が出なかったため、事前登録の基準どおり）。`disk#8`自身の複製
  条件（FILES1・FILES2とも）は2run実施し、両runで同じ結果（3箇所とも
  一致）を確認した。
- 段階2の`set`測定は、`bulk_read_do`のみ2run実施して自己一致
  （決定論性）を確認した。`exchange11_fallthrough`・`exchange14_
  prepare_first_read`の`set`測定は1runにとどめた（3箇所とも同じ方向
  ——相違——を示した一貫性を、`bulk_read_do`の2run自己一致確認を代表
  として決定論性の傍証にしたが、残り2箇所individually の2run確認は
  行っていない）。
- 陽性対照（`--break-drive-selector`）は1runのみ実施した（`m7gn`/`m7go`
  と同様、既存の`tools/verify_drive_byte2_attribution.sh`が既に決定論性
  を検証済みの故障注入であるため）。
- データポート値列そのもの（値）、画面本文、公式ディスクの実データは
  見ていない・記録していない。

## 事前登録の遵守状況

[m7gu](m7gu-three-sites-unit-conformance-preregistration.md)は測定開始
前にコミットした（コミット`57dd14e`）。測定後の書き換え・amendは行って
いない。合格条件6項目は以下のとおり満たした:

1. 陽性対照（unit/head差21件）で判定規則の検出力を確認した。
2. 判定規則は条件O・条件Mそれぞれの2run同士（`FILES 1`・`FILES 2`、
   B:=`disk#8`自身の複製）に先に当て、FDCコマンド種別列全長一致・
   unit/head差0件・画面`match`を確認してから、条件O対条件Mへ当てた。
3. 段の対応づけは`cyl`注入とベースラインの比較で3箇所とも根拠を示した
   （上表）。対応づけができなかった箇所は無い。
4. 全9種のROM（official・default・broken・cyl×3・set×3）のサブROM
   SHA-256は相互にすべて異なることを、ビルド直後と全19回の測定終了後
   の両方で確認した（変化なし）。
5. 決定論性: 差が出なかった`disk#8`自身条件（FILES1・FILES2）は2run
   実施し自己一致を確認した。差が出なかった`disk#10`条件（FILES1・
   FILES2）は1runにとどめた（明記済み、事前登録の基準どおり）。差が
   出た`set`測定は`bulk_read_do`のみ2run実施し自己一致を確認、他の
   2箇所は1runにとどめた（上記「言えないこと」に明記）。
6. 本稿・事前登録・コミットメッセージのいずれにも実ファイル名を含めて
   いない（`disk#N`とダイジェストのみで呼んだ）。

## 開示

手順上の逸脱・汚染は無かった。測定はすべてフォアグラウンド（`run.sh`を
直接実行、`run_in_background`は使用していない）で行い、測定中に`git
stash`・ブランチ切替・ファイル編集は行っていない。全19+2=21回の
q88measure実行はいずれも1回目でrc=0だった（SKIP・リトライ失敗0件）。
ディスクは`tools/stage_disk_by_digest.sh`でダイジェストから中立パスを
得てから使い、実ファイル名を扱う経路を作らなかった。生ログ・混成ROM・
ディスク複製はすべてリポジトリ外（scratchpad配下）に置き、コミットして
いない。

## 検証

`tools/check_cleanroom.sh`は全項目OK、rc=0。`git status`で`private/`
由来の混入・生ログ・ROM像・ディスク複製が無いことを確認した。`src/`・
`tools/`は本稿では変更していない。

## 情報境界 / 根拠リンク

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容（実ファイル名を含む）は、成果物には含めていない。記録したのは
公開FDCコマンド種別名、件数、一致prefix件数、段番号、一致/不一致の
真偽、画面出力の比較結果、SHA-256、rc、ディスクの通し番号・ダイジェスト
だけである。

根拠（`ls`で存在確認済み）:
[m7gu](m7gu-three-sites-unit-conformance-preregistration.md)・
[m7gi](m7gi-remaining-callers-stage12-results.md)・
[m7gj](m7gj-general-read-drive-discrimination-preregistration.md)・
[m7go](m7go-write-data-unit-results.md)・
[m7gp](m7gp-disk-name-leak-path-closed.md)・
[m7fz](m7fz-exchange6-drive-bit-results.md)・
[m7gs](m7gs-odd-cylinder-by-layout-change-preregistration.md)・
[m7gt](m7gt-odd-cylinder-by-layout-change-results.md)・
`docs/spec/l3-subrom.md` 1.33節・1.34節・1.36節・1.46節・1.56節・3節・
自作`src/l3_service/make_subrom.py`（`--probe-site`/`--probe-mode`、
本稿では変更していない）・`tools/lib_l3_measure.sh`（`build_mixed_rom`・
`run_q88measure_retry`）・`tools/compare_l3_entry_fdc.py`・
`tools/check_l3_screen_output.py`・`tools/stage_disk_by_digest.sh`・
`tools/verify_drive_byte2_attribution.sh`（陽性対照の作法の出所）。
