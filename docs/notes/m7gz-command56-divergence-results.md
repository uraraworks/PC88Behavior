# m7gz: FDCコマンド種別列56件目の食い違いの切り分け — 結果

実施日: 2026-09-04

## 位置づけ

[m7gy](m7gy-command56-divergence-preregistration.md)が事前登録した測定の
結果である。`src/`は本稿では変更していない。事前登録した合格条件・判定
規則は測定後も動かしていない。

## 陽性対照（最初に書く）

1. `build_mixed_rom ... --break-drive-selector`（1.46節の既存故障注入）
   を条件M・`FILES 2`・B:=`disk#10`で比較した。
   `compare_l3_entry_fdc.py --after-frame 700`のunit/head差件数は
   **15件**（0件より大きい）。
2. `tools/analyze_error_exchange_shape_selftest.sh`は全4項目OK・rc=0
   （基準抽出・故障注入検出2件・生値非出力を確認済み）。

**両方通ったため、以降の段階1〜3の解釈を行う。**

## 段階1で使う比較法についての補足（測定前提の確認）

事前登録時点では`--list-all-stages`の段番号を「全コマンド列上の絶対
位置」と想定していたが、実装（`compare_l3_entry_fdc.py`の`main()`）を
再確認したところ、`--after-frame`を指定すると`print_all_stage_details`
には**その窓で絞ったあとの部分列**が渡される。一方、見出しの「FDC
コマンド種別の一致prefix」（`m7gx`が「56件目」と呼んだ指標）は
**`--after-frame`の影響を受けない、起動からの完全な列**で計算される。
したがって段階1では**`--after-frame`を付けずに`--list-all-stages`を
実行**し、「段56」が起動からの完全な列上の絶対位置56（＝見出しの
「56件目」と同じ数え方）になるようにした。この点は事前登録の想定と
異なっていたため、ここに明記する（判定規則そのもの＝「段56の一致/
不一致で経路を判定する」は変更していない。数え方の窓を事前登録の
意図どおりに合わせただけである）。

## 判定規則をベースラインへ当てる（合格条件2）

条件M2run同士（探針なし、`disk#10`、`FILES 2`）を、`--after-frame`
無しの`--list-all-stages`で比較した。

| 比較 | 結果 |
|---|---|
| M run1 vs M run2（全段） | 完全一致（rc=0、不一致0件、段56含め全段「一致」） |

**判定規則は偽陽性を作らないことを確認した。** 以降、この方式で条件M
基準対「条件M+cyl探針」を比較する。

## 段階1: 56件目のSEEKを発行している経路

条件M基準（探針なし）を軸に、既存6箇所への`--probe-site X --probe-mode
cyl`注入版をそれぞれ比較した（`--after-frame`無し、`--list-all-stages`）。

| 箇所 | FDCコマンド種別列の一致prefix | 段56 |
|---|---:|---|
| `general_read_request` | 71件（全長一致） | **不一致** |
| `bulk_read_do` | 51件で種別差 | 段56に到達せず（52件目で列が短縮終端） |
| `recv_dispatch_hdr_done` | 71件（全長一致） | 一致 |
| `recv_dispatch_write_sector` | 71件（全長一致） | 一致 |
| `exchange11_fallthrough` | 31件で種別差 | 段56に到達せず（32件目で列が短縮終端） |
| `exchange14_prepare_first_read` | 71件（全長一致） | 一致 |

**`general_read_request`だけが段56で不一致を示した。** 他の3箇所
（`recv_dispatch_hdr_done`・`recv_dispatch_write_sector`・
`exchange14_prepare_first_read`）は段56まで到達しシリンダ指定が一致した
（＝この箇所の呼び出しではない）。`bulk_read_do`・`exchange11_
fallthrough`はcyl注入によってコマンド種別列そのものが早い段階（51件目・
31件目）で短縮終端してしまい、段56の判定材料が得られなかった
（探針がこれらの箇所を頻繁に——起動シーケンス中にも——通るため、cyl
注入がブート序盤から挙動を変え、`FILES 2`の当該区間まで到達する前に
コマンド列が変化したと見られる。この2箇所については「関与しない」と
断定はできず、「本測定法では判定不能」と扱う）。

### 決定論性（合格条件3）

`general_read_request`のcyl注入を独立にもう1回測定し、条件M基準
（もう1つの独立run）と比較した。

| run | 段56 |
|---|---|
| 1回目 | 不一致 |
| 2回目（独立再測定） | 不一致 |

**2run とも段56不一致で自己一致した。**

さらに、`general_read_request`のcyl注入が影響する段を全段列挙したところ、
**段48・52・56・60・64・68**の6段すべてが不一致だった（他の段は一致）。
条件M基準の完全列でこれら6段の種別を見ると、いずれも**SEEK**である
（48件目〜68件目、4件おき）。

## 段階2: 56件目の直前の受信runと、その前後の構造

`analyze_main_to_sub.parse_iolog`・`analyze_record_boundaries.window_a_
runs`・`analyze_write_path.parse_commands`を呼ぶ使い捨てスクリプト
（scratchpad配下、コミットしていない）で、条件M基準の完全コマンド列上の
位置56（SEEK）の直前に完了した受信run（sub視点`IN $FC`連続列）を求めた。

- **run長5**で、直後（次の受信runが始まるまでの区間）に**READ**が現れる。
  1.36節の表で「run長5・直後READ」の組み合わせは**1種類だけ**
  （27/27件で一致した`0x02`類）であり、これに一致する。**先頭バイトの
  実値は書かない**（1.36節が既に公開している分類名を指すだけである）。

**さらに、位置48〜68周辺の受信runと直後コマンドの並びを比較すると、
条件Oと条件Mで構造そのものが違うことが分かった：**

| 条件 | 位置48〜60のコマンド種別列 | この区間の受信run |
|---|---|---|
| 条件O（公式） | SEEK,SENSE,SENSE_DRIVE,READ,**SEEK,SENSE,SENSE_DRIVE,READ,READ,READ,READ,READ,READ**（52で1回reseekした後は56以降reseekなしでREADが連続） | run長5が2回（48直前・52直前）出た後、**56に至るまで新しい受信runは無い** |
| 条件M（混成） | SEEK,SENSE,SENSE_DRIVE,READ,SEEK,SENSE,SENSE_DRIVE,READ,**SEEK**,SENSE,SENSE_DRIVE,READ,SEEK...（4件ずつSEEKで再開する単位が延々と続く） | run長5が48直前・52直前に加え、**56の直前にも新たに1回**出る |

**言えること**: 条件Oは、2回目のSEEK（位置52）以降はREADを連続発行する
だけで新しい受信runを必要としない区間がある（バルク的な連続READ）。
条件Mは、位置56の直前に**もう1回**同じ形（run長5、1.36節の`0x02`類と
同じ形）の受信runが挟まっており、`general_read_request`はこの新しい
runを受けるたびに**SEEKから再開する**——連続READへ移行せず、レコード
ごとに毎回SEEKを含む4コマンド単位（SEEK→SENSE INTERRUPT STATUS→
SENSE DRIVE STATUS→READ）をやり直している。位置48・52で条件O・Mが
一致するのは、この2回のSEEKまでは両者とも同じ動きをするためであり、
違いは**3回目以降のレコードで条件Oが連続READへ移行するのに対し、
条件Mが移行せずSEEKを繰り返す**点にある。

## 段階3: 既知のエラー経路との関係

[m7gx](m7gx-disk10-divergence-results.md)が本セッション中に確立した表
（56件目の分岐位置・分岐直前要求が公式/混成とも6バイトで一致・分岐後
応答runが公式/混成とも長さ1という`unreadable_disk`との部分同型、交換
run構造の先頭一致prefixが`unreadable_disk`ほど揃わない未解明点）を出発点
として引用する（再測定はしていない）。

本稿で新たに特定した`general_read_request`は、1.47節・1.48節が扱う
交換#3型エラー応答（READ DATA結果がST0 IC=異常終了かつST1 MISSING
ADDRESS MARKのときの1バイト応答差し替え）や、`FDC_SEEK`共通入口の
ドライブ指定伝播（1.46節）とは異なる役割——「FILES経路の一般READ要求
ハンドラ」（`docs/spec/l3-subrom.md`第140版追記・`m7gi`・`m7gj`が既に
そう記録している）である。仕様書・既存ノートを`general_read_request`
で検索した範囲では、1.47節・1.48節の記述箇所にこの名前は現れず、
**両者を直接結びつける記述は見つからなかった。**

一方、1.37節は「起動時バルク後の最初のREAD完了直後、`0x06`→`0xC0`→
`0x12`の交換を経て256件を連続送信する（追加のSEEKを挟まない）」経路を
確定している。段階2で見た「条件Oは3レコード目以降SEEKなしで連続READする」
という構造は、**この1.37節の連続送信の性質と同じ系列に見える**が、
1.37節の測定対象は起動時バルク直後の256件送信という別条件であり、
`FILES 2`のディレクトリ読み出し中に同じ`0x06`/`0xC0`/`0x12`交換が
使われているかどうかは、本稿では確認していない。

**言えること**: `general_read_request`は1.47節・1.48節（エラー応答経路）
とは仕様書上で結びつかない、別の役割の箇所である。
**言えないこと**: 条件Oの連続READ構造が1.37節と同じ機構（`0x06`/`0xC0`/
`0x12`交換）によるものかどうかは、本稿では確認していない（次に何を
測ればよいかは下記）。したがって「新しい分岐ではなく1.47節・1.48節に
帰着する」とは言えず、`m7gx`が残した部分同型の未解明点も本稿では解消
していない。

## E1〜E5の判定

- **E1**（経路が特定でき、直前の受信runが1.36節の分類に収まる）:
  **成立。** `general_read_request`が段56のSEEKを発行しており（cyl注入
  2run自己一致で確認）、直前の受信runは1.36節の「run長5・直後READ」類
  （`0x02`類）に一致する。
- **E2**（直前の受信runが1.36節の分類外）: 不成立（E1の分類に収まった）。
- **E3**（既知のエラー経路と同型）: **不成立。** 段階3で見たとおり、
  `general_read_request`は1.47節・1.48節のエラー応答経路とは仕様書上
  結びつかず、この分岐自体は`unreadable_disk`のエラー分類とは別種の
  話（読み出し中の連続READ移行の欠落）である可能性が高いが、確証は
  無い。
- **E4**（経路が特定できない）: 不成立（E1で特定できた）。ただし
  `bulk_read_do`・`exchange11_fallthrough`の2箇所は本測定法では判定
  不能だったことは明記する（下記）。
- **E5**（陽性対照不通過）: 不成立。陽性対照は2件とも通った。

**E1が主判定である。** 本稿で新たに見えた構造（条件Oは複数レコードで
SEEKを再利用するが条件Mはレコードごとに再SEEKする）は、E1を裏づける
具体的なメカニズムの記述であり、E3は積極的に支持されなかった。

## 言えること・言えないこと（総括）

**言えること:**

- FDCコマンド種別列56件目のSEEK（公式=READ DATA、混成=SEEK）は、
  `general_read_request`（FILES経路の一般READ要求ハンドラ、`docs/spec/
  l3-subrom.md`第140版追記で既に存在が記録済みの箇所）が発行している。
  cyl注入2run独立測定で自己一致（決定論性）を確認した。
- `general_read_request`のcyl注入は、条件M基準の完全コマンド列上で
  段48・52・56・60・64・68（すべてSEEK、4件おき）を動かした。他の
  3箇所（`recv_dispatch_hdr_done`・`recv_dispatch_write_sector`・
  `exchange14_prepare_first_read`）は段56に到達しつつ一致したため、
  この箇所ではないと言える。
- 56件目の直前の受信run（sub視点）はrun長5・直後READというパターンで、
  1.36節の`0x02`類に一致する（先頭バイトの実値は書いていない）。
- 条件Oと条件Mの構造差が具体的に分かった: 位置48・52の2回のSEEK・
  READまでは条件O・M共通だが、**条件Oは3レコード目以降SEEKなしで
  連続READへ移行する一方、条件Mは`general_read_request`がレコードごと
  に新しい受信run（同じ`0x02`類）を受けてSEEKからやり直す。**
- `general_read_request`は仕様書上、1.47節・1.48節（エラー応答経路）
  とは結びつかない別の役割の箇所である。

**言えないこと:**

- `bulk_read_do`・`exchange11_fallthrough`へのcyl注入は、ブート序盤
  から挙動を変えてコマンド種別列を51件目・31件目で短縮終端させたため、
  この2箇所が段56に関与するかどうかは本測定法では判定できなかった
  （関与しないとは断定していない）。
- 条件Oの「3レコード目以降SEEKなしで連続READ」という構造が、1.37節が
  確定した`0x06`→`0xC0`→`0x12`交換と同じ機構によるものかどうかは、
  本稿では確認していない。
- `m7gx`が残した「交換run構造の先頭一致prefixが`unreadable_disk`ほど
  揃わない」という未解明点は、本稿では解消していない。
- `general_read_request`自体の実装（`src/`のどの分岐が連続READへ移行
  しないのか）は、本稿では調べていない（`src/`を修正しない事前登録の
  範囲内。ただし`general_read_request`という箇所の存在自体は
  `docs/spec/l3-subrom.md`・既存ノートに既に記録済みの公開情報であり、
  本稿はその箇所を通してのみ言及した）。
- データポート値列そのもの（値）、画面本文、公式ディスクの実データは
  見ていない・記録していない。

## 次に何を測れば絞れるか

- **1.37節の`0x06`/`0xC0`/`0x12`交換が`FILES 2`のディレクトリ読み出し
  区間でも使われているかを、値を見ずに交換run構造だけで確認する。**
  もし条件Oの56件目の直前・直後にこの3ステップ交換が現れるなら、
  `general_read_request`が実装していないのはこの継続機構だと絞り込める。
- `bulk_read_do`・`exchange11_fallthrough`は、ブート区間だけを避ける
  探針（たとえば`--reset-at`や起動シーケンス通過後にだけ効く条件）が
  無いため、今回の6箇所の`cyl`注入では判定できなかった。これらの2箇所
  が段56に関与しないことを確認するには、ブート序盤への影響を避ける
  新しい探針条件（例えば`FILES 2`区間だけを狙った条件分岐）が要る。

## 事前登録の遵守状況

[m7gy](m7gy-command56-divergence-preregistration.md)は測定開始前に
コミットした（コミット`757a22a`）。測定後の書き換え・amendは行って
いない。合格条件6項目は以下のとおり満たした:

1. 陽性対照2件（unit/head差15件、selftest全OK rc=0）を先に通した。
2. 判定規則を条件M2run同士（`--after-frame`無し・`--list-all-stages`）
   へ先に当て、「全段一致」を確認してから条件M基準対「条件M+cyl」6件
   へ当てた。
3. 決定論性: 差が出た`general_read_request`は2run実施し自己一致を
   確認した。`bulk_read_do`・`exchange11_fallthrough`・
   `recv_dispatch_hdr_done`・`recv_dispatch_write_sector`・
   `exchange14_prepare_first_read`は1runにとどめた（明記済み）。
4. 対照条件: 本稿は`disk#10`固有性の再検証ではなく56件目の内部原因の
   切り分けが目的のため対照は置かないと事前登録した。この方針どおり
   `disk#1`等の対照測定は行っていない。
5. 元ディスク（`disk#8`・`disk#10`の複製元）は、本稿の全測定で読み取り
   のみ（`FILES 2`のみ、`--save-to-disk-image`未指定、SAVE系キー入力
   なし）だったため書き込みは発生していない。
6. 本稿・事前登録・コミットメッセージのいずれにも実ファイル名を
   含めていない（`disk#N`とダイジェストのみで呼んだ）。先頭バイトの
   実値・シリンダ値・画面本文も書いていない。

事前登録からの逸脱として、段階1で使う`--list-all-stages`の比較窓を
「段階1で使う比較法についての補足」節に記した理由により`--after-frame`
無しに変更した。判定規則自体（段56の一致/不一致で経路を判定する）は
変えていない。

## 開示

手順上の逸脱は上記1件（比較窓の補足）のみで、汚染は無かった。測定は
すべてフォアグラウンドで実行し（`run_in_background`は使用していない）、
測定中に`git stash`・ブランチ切替・ファイル編集は行っていない。全11回
のq88measure実行（official 1回・条件M基準2回・break-drive-selector
1回・cyl探針6回・`general_read_request`cyl再測定1回）はいずれも1回目で
rc=0だった（SKIP・リトライ失敗0件）。ディスクは`tools/stage_disk_by_
digest.sh`でダイジェストから中立パスを得てから使い、実ファイル名を
扱う経路を作らなかった。生ログ・混成ROM・ディスク複製・使い捨て解析
スクリプトはすべてリポジトリ外（scratchpad配下）に置き、コミットして
いない。

## 検証

`tools/check_cleanroom.sh`は全項目OK、rc=0。`git status`で`private/`
由来の混入・生ログ・ROM像・ディスク複製が無いことを確認した。`src/`は
本稿では変更していない。

## 情報境界 / 根拠リンク

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容（実ファイル名を含む）は、成果物には含めていない。記録したのは
公開FDCコマンド種別名、件数、一致prefix件数、段番号、一致/不一致の
真偽、run長、既存仕様書節が既に公開済みの分類名（1.36節の`0x02`類等）
、rc、ディスクの通し番号・ダイジェストだけである。先頭バイトの実値・
シリンダ値・PCN値・データポート値列・画面本文は書いていない。

根拠（`ls`で存在確認済み）:
[m7gy](m7gy-command56-divergence-preregistration.md)・
[m7gx](m7gx-disk10-divergence-results.md)・
[m7gw](m7gw-disk10-divergence-preregistration.md)・
[m7gv](m7gv-three-sites-unit-conformance-results.md)・
[m7gi](m7gi-remaining-callers-stage12-results.md)・
[m7gj](m7gj-general-read-drive-discrimination-preregistration.md)・
[m7gc](m7gc-remaining-callers-probe-preregistration.md)・
`docs/spec/l3-subrom.md` 1.36節・1.37節・1.46節・1.47節・1.48節・
第140版追記・3節・
`src/l3_service/make_subrom.py`（`--probe-site`/`--probe-mode`、
本稿では変更していない）・`tools/lib_l3_measure.sh`（`build_mixed_rom`・
`run_q88measure_retry`）・`tools/compare_l3_entry_fdc.py`・
`tools/analyze_error_exchange_shape_selftest.sh`・
`tools/analyze_main_to_sub.py`・`tools/analyze_record_boundaries.py`・
`tools/analyze_write_path.py`（段階2の使い捨てスクリプトが再利用した
既存モジュール）・`tools/stage_disk_by_digest.sh`。
