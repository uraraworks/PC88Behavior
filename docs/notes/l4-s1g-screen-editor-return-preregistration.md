# l4-s1g — スクリーンエディタ「RETURNで画面上の行を読み直す」— 事前登録

記録日: 2026-09-19
状態: 事前登録、測定前

## この番号を選んだ理由

[l4-s1f](l4-s1f-screen-editor-preregistration.md)（本体・追補1〜3）は
矢印・INS/DEL・HOME/CLRの8キー条件を確定させたが、`RETURNによる「画面の
行を読み直して実行する」動作は…第2弾に回す`と明記して対象外にした
（同ノート「対象外（第2弾以降）」節）。本ノートがその第2弾で、次の空き記号
`l4-s1g`を使う。

## 位置づけ

[l4-design](l4-design.md) 段階1（main側L3の測定）の続き。`l4-s1b`が
`01:7`（RETURN）を「押すと複数セルが変化するため未判定」のままにしており
（`docs/spec/l3-main.md` 第9節・第16節項4）、本ノートはその中身、すなわち
「カーソルを画面上の既存の行へ移動してからRETURNを押すと何が実行される
のか」を測る事前登録である。**実装は行わない。測定も行わない。今回は
文書（本ノートと候補表・候補生成器具）を書いてコミットするところまで。**

## 資料との照合（既存の観測の再利用、新規の資料読みは無し）

本ノートは新しく資料を読まない。既存の測定結果・仕様書だけを候補の出所に
する。

- [l4-s1f-screen-editor-preregistration](l4-s1f-screen-editor-preregistration.md)
  「資料との照合」節: 『PC-8801FA／MA プログラマーズガイド』p.41
  「2.訂正」実行例 —「`LINE(0,0)-(300,100)` の `1` の位置へカーソルを移動し
  `2` を打つと `100` が `200` に変わる」「RETURNを押すと編集後の行がそのまま
  実行される」。これが本ノートQ1（`screen_wins`候補）の一次的な出所であり、
  対抗候補（`buffer_wins`）は資料からは排除できないため両方を当てる方針
  （同ノート「資料との照合」節末尾の書き方を踏襲）。
- [l4-s1f-screen-editor-results](l4-s1f-screen-editor-results.md)・
  [-results-boundary2](l4-s1f-screen-editor-results-boundary2.md)（末尾の
  訂正節を優先）: 確定した動作
  `←/→`=列±1（`no_change`、行の途中）・
  `←`真の境界=`wrap_prev_line_end`（前の行の列79へ）・
  `↑/↓`=`row_move`（行±1・列不変）・
  `HOME/CLR`無修飾=`clear`（画面全消去＋カーソル(0,0)）・
  `INS/DEL`無修飾（行の途中）=`del_left`・SHIFT=`ins_mode_only`。
  本ノードは、この確定済みの動作だけを使ってカーソルを組み立てる
  （新しいキー挙動は前提にしない）。
- `docs/spec/l4-basic.md` 第1節（直接モード: 打った行の相対行+1に出力、
  相対行+2に`Ok`）・第2節（正の整数は符号スペース1桁+数字+後置スペース1、
  例: 値`v`の出力行バイト列は「空白, 数字..., 空白, 空白...」）・第6節
  （構文の誤りは相対+1の1行だけが変わり`Ok`の行位置は動かない、非空白件数
  15件・列0-15）・第5.6節（範囲外・0除算は`Ok`が相対+3にずれる、出力が
  2行にわたる）。これらが本ノートの出力候補（数値署名・行オフセット）の
  出所。
- `docs/spec/l4-program.md` 第1節（行番号つきの行を打っても`Ok`は出ない。
  エコーだけが残る）・第2節（`LIST`は打鍵どおり大文字化して再現、`10 PRINT
  12`のように表示される）・第3.1節（同じ行番号を打ち直すと`replaced`）。
  これらが本ノート第4群（プログラム行の編集）の候補の出所。
- `tools/l4_s1f_window_probe.py`（window限定署名、末尾空白を除いて
  SHA-256）・`tools/l4_vram_probe.py`の`--row-signature`（行全体の署名、
  同じ正規化規則）・`--nonblank-summary-rows`（出力が現れた行を、内容を
  出さずに件数だけで特定する）。器具はすべて既存、新規追加は本ノートの
  候補生成器具（下記）のみ。

## 器具の使い方（既存確認、l4-s1fからの引き継ぎ）

- `--key-matrix`と`--type`は同時併用不可（`tools/harness/frontend/main.c`
  1766〜1776行）。本ノードの腕は矢印・HOME/CLR・RETURN等の非ASCIIキーと
  BASICの文字列を同じ1走で打つため、**文字キーも含めすべて`--key-matrix`
  で組む**（l4-s1fと同じ方針）。文字キーのport:bitは`docs/spec/l3-main.md`
  第9節のQ1文字コード対応表（無修飾・小文字）から機械的に引く。表自体は
  既存資料であり本ノートが新規に作るものではない。実装担当が
  `tools/l4_s1g_arms.py`（新規、`tools/l4_s1f_arms.py`の構成に倣う）で
  参照コードに落とし込む。CAPS/SHIFTは使わない（キーワードは小文字で
  打ち、`docs/spec/l4-program.md`第2.2節どおりLIST等が大文字化して表示
  する。l4-c2の条件節と同じ「小文字表記」の方針）。
- **出力行・`Ok`行の場所を事前に決め打ちしない。** RETURNを画面上の
  既存行（プロンプト以外の位置）で押した場合、出力がどの行に現れるかは
  本ノートが測ろうとしている問いの一部（Q4「カーソル位置」）であるため、
  各腕とも、RETURN後に`--nonblank-summary-rows`（既存器具、追加B）で
  「直前の写しでは空白だった行のうち、新たに非空白になった行」を特定
  してから、その行に対して`--row-signature`（追加C）を適用する、という
  2段階の手順を取る。新しい解析道具は不要。
- HOME/CLR（無修飾）で画面を初期化してから各腕を始める
  （`clear`＝全消去＋カーソル(0,0)、l4-s1fで確定済み）。これにより
  「真の(行0,列0)」から出発できる（l4-s1f追補2の作法を踏襲）。
- 打つBASIC文字列は自分で選んだ内容であり、`l4-c2`「本文を出さない取り扱い」
  節と同じ扱い（自分が指定した打鍵文字列は書いてよい）。ROMが出す`Ok`は
  `docs/spec/l4-basic.md`・`l4-program.md`が既に繰り返し使っている固定
  トークンとしての扱いを引き継ぐ（新たに画面から読み取って書き出すもの
  ではなく、既存仕様書の記法をそのまま使うだけ）。エラーメッセージの
  **文言そのもの**（第6節・第5.6節の非数値出力2腕と同じ扱い）は一切
  扱わない。件数・行オフセットだけで判定する。

## 器具の自己検査（新規に要る分）

- **HOME/CLR初期化後にBASIC文字列＋特殊キーを混ぜた連続打鍵チェーンの
  自己検査**: 陽性対照PC1（下記）を1走走らせ、`docs/spec/l4-basic.md`
  第1節の並び（相対+1に出力、相対+2に`Ok`）と一致することを確認する。
  一致しなければ、多打鍵チェーンのタイミング式を見直す（l4-s1fの
  「連続打鍵チェーンの自己検査」と同じ考え方、対象がBASIC文字列に
  変わっただけ）。
- 既存の`tools/harness/vram_dump_selftest.sh`・
  `vram_dump_dynamic_selftest.sh`・`key_matrix_selftest.sh`・
  `mem_write_log_selftest.sh`・`screen_content_leak_selftest.sh`は
  流用する（新規追加なし）。
- 候補生成器具`tools/l4_s1g_candidates.py`自体の自己検査:
  `--check`オプションで再生成した候補表が既存ファイル
  （`docs/notes/l4-s1g-candidate-table.json`）と一致することを確認する
  （決定論性、`l4_s1f_arms.py --check`と同じ作法）。本ノートのコミットに
  同梱して確認済み（下記「候補」節）。

## 対象外（今回も対象外のまま。後回しにしない）

- **論理行（80文字を越えて2行にまたがる行）の読み直し。** l4-s1fの
  `boundary_reflow`（`01:7`の複数セル変化、未判定のまま）と同種の複雑さを
  持ち込むため対象外。次の事前登録の材料として列挙するに留める。
- **挿入モードで列79まで詰まった行への挿入。** l4-s1f追補2が「実文字での
  行充填手順が新規に要る」として持ち越したのと同じ理由で対象外のまま。
- **G7相当（Q2＝CRTC/iologとQ3＝目印座標の突き合わせ）は、本ノートでは
  最初から対象外と決める。** l4-s1f本体・追補2・追補3のいずれも、iolog
  のフレーム番号と`--vram-dump-at`のフレーム番号を対応付ける解析器具が
  無いままQ3（目印挿入による直接確認）のみで判定し、事後に「G7未実施」
  と訂正する手順違反を繰り返した（`l4-s1f-screen-editor-results.md`
  「訂正（レビューによる）」節「G7未実施の位置づけ」）。本ノートは同じ
  過ちを繰り返さないよう、**測定前に**「Q2（CRTC/iolog）は実施しない、
  判定はすべてQ1（行署名・件数）とQ3相当（非空白行の出現位置）で行う」と
  明記する。やる場合に要る器具（iolog内`frame`列と`--vram-dump-at`の
  フレーム値の単位対応付け）は、必要になった時点で別途事前登録する。

## 問い

- Q1（どちらの行が実行されるか）: カーソルを画面上の既存の内容の途中へ
  戻して一部を上書きし、RETURNを押したとき、実行されるのは「上書き前に
  打った文字列（打鍵バッファ）」か「上書き後に画面に表示されている内容」
  かを、出力の数値で区別する。
- Q2（RETURNを押すカーソル位置の影響）: 上書き直後の位置・行末・行頭の
  3位置でQ1を繰り返し、読む範囲（行全体／カーソルまで／カーソルから後）
  がカーソル位置に依存するかを見る。
- Q3（別の行へ移ってからのRETURN）: ↑で画面上の別の（既に実行済みの）
  直接モード文の行へカーソルを移し、編集せずにRETURNを押すと、その行が
  再実行されるか。
- Q4（プログラム行の編集）: `LIST`で表示された行番号つきの行をカーソルで
  書き換えてRETURNを押すと、登録されているプログラムの内容が書き換わるか。
- Q5（行末の古い文字の扱い）: 元の行より短い内容で上書きしたとき、上書き
  されずに残った行末の古い文字は、読み直しの対象に含まれるか。
- Q6（RETURN後のカーソル位置）: 各腕で、RETURNを押した後カーソルがどこに
  移るか（次の行の列0か、それ以外か）を目印文字で確認する。

## 腕

各腕、HOME/CLR初期化 → 準備打鍵 → （関門P: 対象キー無しで目印を打つ
対照走）→ 本走（対象操作＋RETURN） → 出力行の特定（`--nonblank-summary-rows`）
→ 出力行・`Ok`行の署名（`--row-signature`）、という手順を踏む。決定論性
のため各2走。関門Pは対照走であり本走とは別の1走（2走）。

### 群R（Q1・Q2、どちらの行が実行されるか、カーソル位置3種）

準備: HOME/CLR → `print 12`（8打鍵、カーソル列8） → `←`×2（列6、`1`の上）
→ `4`を打って上書き（`1`→`4`、カーソル列7、画面上は`print 42`）。

| # | 位置決め（準備の続き） | RETUENを押す位置 | 候補 |
|---|---|---|---|
| R1a | 追加なし | 列7（上書き直後） | `buffer_wins`(→12) / `whole_line`(→42) / `from_cursor_to_end`(列7から末尾のみ＝`2`単独、構文の誤り相当) / `from_start_to_cursor`(列0〜7＝`print 4`、→4) |
| R1b | `→`×1 | 列8（行末） | `buffer_wins`(→12) / `whole_line`(→42、`from_cursor_to_end`と縮退) / `from_start_to_cursor`(列0〜8＝`print 42`、`whole_line`と縮退) |
| R1c | `←`×7 | 列0（行頭） | `buffer_wins`(→12) / `whole_line`(→42、`from_cursor_to_end`と縮退) / `from_start_to_cursor`(列0〜0＝空、無入力相当) |

（R1b・R1cで一部候補が縮退する点は、事前登録の時点で明記しておく。
判定はR1aを主根拠にし、R1b・R1cは「縮退により区別できない」ことの
確認に使う——l4-s1fのINS/DEL候補が行頭・行末で縮退した扱いと同じ考え方）。

候補の期待署名（`print_12`→12、`print_42`→42、`print_4`→4）は
`docs/notes/l4-s1g-candidate-table.json`に測定前に機械計算済み
（下記「候補」節）。`from_cursor_to_end`（構文の誤り相当）は数値候補が
無いため、`docs/spec/l4-basic.md`第6節の構造（出力行が数値候補と不一致、
かつ`Ok`行が相対+2のまま）で判定する。

### 群U（Q3、別の行へ移ってRETURN）

準備: HOME/CLR → `print 12`+RETURN（実行、出力`12`・`Ok`の3行） →
`print 34`+RETURN（実行、出力`34`・`Ok`の3行、カーソルは次の空行の列0）。

| # | 位置決め | 対象操作 | 候補 |
|---|---|---|---|
| U1 | `↑`を6回（`print 12`の入力行の列0へ戻る。関門Pで実測確認） | 編集せずRETURN | `reexec_appends`(新しい`12`＋`Ok`が現在の末尾に追加される) / `no_reexec`(出力が増えない、カーソルだけ動く) |

U1の`reexec_appends`候補の期待署名は`print_12`（既存候補、値12）を流用する。

### 群E（Q4、プログラム行の編集）

準備: HOME/CLR → `new`+RETURN → `10 print 12`+RETURN（登録、`Ok`無し、
`docs/spec/l4-program.md`第1節） → `list`+RETURN（`LIST`出力
`10 PRINT 12`が画面に現れる）。

| # | 位置決め | 対象操作 | 候補 |
|---|---|---|---|
| E1 | `↑`で`LIST`が表示した行へ戻り、`1`(の値の1桁目)の上へ`←`で合わせる（関門Pで実測確認） | `4`で上書き（`1`→`4`）→RETURN | `line_registration_updated`(その後`run`+RETURNの出力が`42`) / `line_registration_unchanged`(出力が`12`のまま) |

E1の判定は、対象操作の直後にさらに`run`+RETURN（1打鍵チェーンとして
続ける）を打ち、その出力行の署名で行う（`print_42`／`print_12`、既存
候補を流用）。

### 群T（Q5、行末に残った古い文字）

準備: HOME/CLR → `print 123`（9打鍵、カーソル列9） → `←`×3（列6、
`1`の上） → `4`を打って上書き（`1`→`4`、カーソル列7、画面上は
`print 423`、列8-9に旧`2``3`がそのまま残る）。

| # | RETURNを押す位置 | 候補 |
|---|---|---|
| T1 | 列7（上書き直後） | `reads_whole_row`(→`print 423`相当、出力423) / `reads_up_to_cursor`(→`print 4`相当、出力4) / `reads_from_cursor`(→`23`単独、行番号23として解釈される可能性——`docs/spec/l4-program.md`第3.2節「行番号だけを打つと削除」に類似の構造。数値出力にはならず、出力行なしの構造で判定する) |
| T2 | 列8（`→`×1で1つ進めてからRETURN、旧`2`の直後） | `reads_whole_row`(→423) / `reads_up_to_cursor`(→`print 42`相当、出力42) |

T群の候補署名は`print_423`（新規、値423）・`print_4`・`print_42`
（いずれも既存候補）を流用する。

### 対照

- **陽性対照PC1**: HOME/CLR → `print 12`+RETURN（編集なし）。
  出力署名が`print_12`候補と一致することを確認する（器具の自己検査を
  兼ねる、G4相当）。
- **陰性対照NC1**: HOME/CLR後、何も打鍵しない走（settleのみ）。
  vram差分・iolog差分ともに0件（G5相当、l4-s1fと同じ定義）。

### 関門P（位置確認、対象キー無しの対照走）

R1a/R1b/R1c・U1・E1・T1/T2の**準備手順すべて**について、対象操作
（上書き・RETURN）を行わず、その位置で直接目印文字を打つ対照走を用意し、
目印の座標が意図した位置と一致することを確認してから本走を行う
（l4-s1f追補3の反省を踏襲——「対象キーを押す直前の位置を実測せず頭の
計算に頼ったために起きた見落とし」と同じ轍を踏まない）。対照走・本走とも
各2走。

### 腕数の集計

群R(3) + 群U(1) + 群E(1) + 群T(2) + 陽性対照(1) + 陰性対照(1) = **9腕**
（本走、各2走=18走）。関門Pの対照走はこのうち対象操作を持つ7腕
（R1a/R1b/R1c/U1/E1/T1/T2）に対応し、**7腕**（各2走=14走）。
合計 **16腕・32走**（本走18走＋関門P対照14走）。腕数の目安（20腕前後）
より少ないが、群R内の縮退（R1b・R1cの一部候補がR1aと同じ値に潰れる）を
承知のうえ絞った結果であり、本文中に明記した。

## 候補

Q1・Q3・Q4・Q5（どの数値が出力されるか）の期待署名は、`docs/spec/
l4-basic.md`第2節（正の整数の書式）の規則から機械的に導ける。測定前に
`tools/l4_s1g_candidates.py`で計算し、`docs/notes/l4-s1g-candidate-table.json`
にコミットする（本ノートに同梱。中身は数値・正規化後長・SHA-256のみで
画面本文ではない——自分で選んだ仮説値であり、l4-s1fの候補生成
〔`tools/l4_s1f_candidates_v2.py`〕・l4-c2の期待値作りと同じ位置づけ）。

候補表に含まれる値: `print_12`(12)・`print_42`(42)・`print_4`(4)・
`print_423`(423)・`print_34`(34)。各値について、1桁ずらしたダミー候補
（`_fault_dummy_of_*`）も同梱し、G8（故障注入）にそのまま使える。

`from_cursor_to_end`（構文の誤り相当）・`reads_from_cursor`（行番号解釈
相当）は、値ではなく構造（`docs/spec/l4-basic.md`第6節の非数値パターン・
`docs/spec/l4-program.md`第3.2節の行削除パターン）で判定するため、候補
表には値を持たない。測定時は「候補表のどの数値署名にも一致しない、かつ
`Ok`行が相対+2のまま」で`from_cursor_to_end`系、「出力行自体が現れない」で
`reads_from_cursor`系、と記録する。

## 本文を出さない取り扱い（禁止事項7）

- 写し・iolog・解析結果は使い捨ての作業ディレクトリに置き、コミットしない。
- 出力行・`Ok`行は`--row-signature`（件数・正規化後長・SHA-256のみ）で
  記録し、文字コードの並びそのものは出さない。ただし、自分が打った
  BASIC文字列（`print 12`等）と、その直接の結果として妥当な数値
  （12・42・4・423・34、候補表に既に載せた値）は、l4-basic.md・l4-c2と
  同じ扱いで値のまま書いてよい。**それ以外の実測出力**（想定外の値や
  エラー表示の文言）は一切書かない。
- 判定表（候補と実測署名の一致／不一致）は候補名と真偽値だけを記録する。

## 関門

- G1 器具: 既存の自己検査（`key_matrix_selftest`等）＋本ノート新規の
  「BASIC文字列＋特殊キー混在チェーンの自己検査」（PC1で兼ねる）＋
  `tools/l4_s1g_candidates.py --check`がOK。
- G2 取りこぼし0、打鍵系の警告0。
- G3 決定論性: 各腕2走で、出力行の位置・署名、`Ok`行の相対位置、目印座標が
  一致。
- G4 陽性対照: PC1の出力署名が`print_12`候補と一致。
- G5 陰性対照: NC1でvram差分・iolog差分ともに0件。
- G6 反映の遅れ: `docs/spec/l3-main.md`第8節の既存値（D=10）を流用し、
  RETURN・上書き・目印いずれの反映も確認できることの確認のみ
  （再決定しない）。
- G7: 対象外（上記「対象外」節のとおり、実施しない）。
- G8 故障注入: 候補表の`_fault_dummy_of_*`が、対応する実測署名と必ず
  不一致になることを、実測データに対して確認する（`l4-s1f`のG8再確認と
  同じ作法——候補表生成時の設計だけでなく実測署名への当てはめまで行う）。
- G9（新設・関門P）: R1a/R1b/R1c・U1・E1・T1/T2の全腕で、対象操作を押す
  直前の位置を、対象操作無しの対照走で実測確認できている
  （上記「関門P」節）。確認できない腕は本走を行わない。

## 判定

- 群R・群U・群E・群T: 各腕`unique_survivor(候補名)`／`no_survivor`／
  `multiple_survivors`。縮退が事前に分かっている腕（R1b・R1cの一部）は
  `multiple_survivors`が出ても設計どおりの縮退として記録し、`no_survivor`
  ・意図しない`multiple_survivors`とは区別する。
- G9未確認（関門P不一致）の腕は測定せず「腕を組み直す」（l4-s1f追補3と
  同じ扱い）。
- 群R全体としての結論（`buffer_wins`か`whole_line`か、あるいはカーソル
  位置依存の`from_*`系か）は、R1aの`unique_survivor`を主根拠にし、
  R1b・R1cは縮退の確認に使う（本ノート「群R」節に明記済みの方針）。

## 判定後の行き先

`docs/spec/l3-main.md`の`01:7`（RETURN）の記述、および`docs/spec/
l4-basic.md`・`l4-program.md`のRETURN再読込に関する節の追記は、別担当
（判定後の実装担当）が行う。本事前登録の問い・候補・腕数・関門・判定の
数え方は測定後に書き換えない。

## 結果ノート

`docs/notes/l4-s1g-screen-editor-return-results.md`に書く。関門・指標・
判定と数え方を後から動かさない。

## 根拠リンク

[l4-s1f-screen-editor-preregistration](l4-s1f-screen-editor-preregistration.md)
（対象外とした経緯、CAPS/`--key-matrix`の作法）・
[l4-s1f-screen-editor-preregistration-addendum](l4-s1f-screen-editor-preregistration-addendum.md)
（window署名の正規化規則）・
[l4-s1f-screen-editor-preregistration-addendum2](l4-s1f-screen-editor-preregistration-addendum2.md)・
[-addendum3](l4-s1f-screen-editor-preregistration-addendum3.md)（関門P、
位置確認を対照走で行う作法とその根拠となった見落とし）・
[l4-s1f-screen-editor-results](l4-s1f-screen-editor-results.md)（確定した
`clear`/`row_move`/`del_left`/`ins_mode_only`、G7未実施の訂正——本ノートが
G7を最初から対象外にした理由）・
[l4-s1f-screen-editor-results-boundary2](l4-s1f-screen-editor-results-boundary2.md)
（真の境界での`wrap_prev_line_end`）・
[l4-c2-print-conformance-preregistration](l4-c2-print-conformance-preregistration.md)
（`--row-signature`でエラー行を件数・SHA-256だけ扱う作法、値を出して
よい範囲の判断）・
`docs/spec/l4-basic.md`第1・2・5.6・6節（直接モードの行オフセット、整数の
書式、誤りの行オフセット）・
`docs/spec/l4-program.md`第1・2・3.1・3.2節（行番号つきの行・`LIST`・
置き換え・削除）・
`tools/l4_s1f_window_probe.py`・`tools/l4_vram_probe.py`
（`--row-signature`・`--nonblank-summary-rows`）・
`tools/l4_s1g_candidates.py`・`docs/notes/l4-s1g-candidate-table.json`
（本ノートで新規に作った候補生成器具と候補表）。
