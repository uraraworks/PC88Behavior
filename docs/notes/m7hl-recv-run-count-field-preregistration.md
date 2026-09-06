# m7hl: 連続READの周期「9」が受信runのフィールドに現れるかを、値を出さずに測る — 事前登録

## 位置づけ

`docs/spec/l3-subrom.md` 1.57節（第144版）が3節へ引き継いだ「公式が新しい
受信runを待たずに連続READへ移行してよいとどう判断しているか」は未確定の
ままである。この判断規則が分からないまま「連続READにする」とだけ真似ると、
条件が違えば破綻する実装になる。

[m7hb](m7hb-consecutive-read-rule-results.md)は、`disk#10`で連続READ区間が
**きっちり9件**で区切られ、12周期すべてで例外なく一致することを確定した
一方、この「9」が

- **H2（固定回数上限）**: `general_read_request`相当の箇所が内部に持つ
  固定カウンタに由来する
- **H1派生（1トラック分）**: main→subの要求そのものが「何レコード読むか」
  を伝えており、subはそれに従っている

のどちらに由来するかを**区別できなかった**（両仮説が同じ観測を予測する
ため）と記録した。そのうえでm7hbは「次に何を測れば絞れるか」の筆頭として
**値を出さない count-comparator の新設**を挙げた。

**本稿はそのcount-comparatorを事前登録する。** m7hc〜m7hjの4周は、この
提案ではなく「データの大きさ・位置」という別軸を辿り、いずれも絞り込みに
至らなかった（N4・O4・P3・P3）。本稿は軸をm7hbの提案へ戻す。

**本稿は測定と記録だけを行い、`src/`は修正しない。** 新設するのは
`tools/`の解析器（測定器）のみである。

## なぜこの区別が実装上重要か

- H1派生が正なら、公式の判断規則は**要求の中にある**。自作
  `general_read_request`は受け取った要求からレコード数を読み、1回のSEEKの
  あと同数のREAD DATAを発行すればよい。規則は条件によらず移植できる。
- H2が正なら、規則は**subの内部状態**にある。これはROM内部のワークエリア
  構造に当たり、3節の既存項目（第23版の`SEND_DISPATCH_IDLE`）と同様
  **クリーンルーム規律上は測定では届かない**領域に入る。その場合は
  「届かないことを測定で示した」として3節へ格上げし、この軸の追跡を
  打ち切る根拠にする。

**どちらに転んでも前進する。** C2（区別する位置が無い）は失敗ではない。

## 段階0（本稿）: 事前登録を測定前にコミットする

本稿は測定を1回も走らせる前に単独でコミットする。測定後の書き換え・amendは
行わない。新設ツールのコミットは本稿より後に行う。

## 測定条件（共通。m7ha・m7hbと同一に固定する）

- ROM: `PC88_REF_ROM_DIR`（未設定時`private/rom`）の公式一式（条件O）。
  混成ROM（条件M）は陽性対照でのみ使う。
- A: `disk#8`（`650cfac8`）の使い捨て複製（起動可能ディスク）。
- B: `disk#10`（`0c6f7a53`、`READ DATA` 108件、12周期が出る唯一の候補）。
- 打鍵: `--type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n'
  --frames 3000`（m7gy・m7gz・m7haと同一）。
- ディスクは`tools/stage_disk_by_digest.sh`でダイジェストから中立パスを
  得てから使う。実ファイル名を扱う経路を作らない。
- 測定はフォアグラウンドで行い、測定中に`git stash`・ブランチ切替・
  `src/`の編集をしない。

## 新設する測定器: `tools/compare_recv_run_fields.py`

**設計の中心は「値を1つも出さないこと」である。**

入力: iolog 1本。内部で既存モジュールだけを使う（二重実装しない）。

- `tools/analyze_main_to_sub.parse_iolog`
- `tools/analyze_record_boundaries.window_a_runs`（受信run＝sub視点
  `IN $FC`連続列）
- `tools/analyze_write_path.parse_commands`（FDCコマンド列）
- `tools/compare_l3_entry_fdc.command_names`（種別名列）

出力（標準出力に出してよいものを列挙し、これ以外は出さない）:

- run の**通し番号**と**長さ**（バイト数）
- 2つのrunの同じ位置 p について、`eq(a[p], b[p])` の**真偽**
- 同じく `cmp(a[p], b[p])` の**符号のみ**（`-1` / `0` / `+1`）
- 位置番号 p そのもの（オフセットは構造であって内容ではない）
- 件数・rc・真偽値

出さないもの: **バイト値、差の絶対値、シリンダ値、PCN値、画面本文、
実ファイル名。** 値を保持する変数は比較関数の内部にとどめ、
`print`・`sys.stderr`へ到達する経路を作らない。

`tools/screen_content_leak_selftest.sh`と同型の自己検査
（`tools/recv_run_field_leak_selftest.sh`。**陰性対照つき**——わざと値を
出す版を作って検査が赤くなることを確認する）を同時に新設し、これが通ら
ないうちは本測定を実施しない。

## 段階1: 対応づけが成立するかを先に検査する（成立しなければ段階2はやらない）

m7hbは、受信run終了時刻とSEEK発行の対応づけが数千〜2万クロックの開きを
示し、**間に新しいrunが挟まっていないのに複数回SEEKが発行される**区間が
あることを記録した。対応づけが壊れたまま段階2を走らせると、比較の意味が
無い。よって段階1で対応づけの成否そのものを判定する。

判定する項目（すべて真偽・件数のみ）:

1. 起動からの完全なFDCコマンド種別列で、連続READ区間（run長9）が12回、
   m7hbと同じ位置に再現するか（決定論性の再確認）。
2. 各 SEEK 段の直前に**完了している**受信runが一意に定まるか。定まらない
   段（直前runが無い／同一runが複数段に対応する）の**件数**を数える。
3. 連続READ区間の入口（12箇所）それぞれについて、直前完了runが一意に
   定まるか。

**中止規則（測定前に固定）:** 項目3で一意に定まらない箇所が1件でもあれば、
段階2は**実施しない**。そのときは主判定をN（対応づけ不成立）とし、無言で
SKIPせず「実施しなかった」と明記する。項目2の不定件数が0でなくても、
項目3が全12箇所で一意なら段階2は実施してよい（比較対象は入口runのみの
ため）。

## 段階2: 入口runと単発区間runを、値を出さずに比較する

比較する2群:

- **群R（連続READ区間の入口）**: 段階1項目3で一意に定まった12本のrun。
- **群S（単発区間）**: 同じログ内で、直後のREAD DATAが単発（run長1）で
  終わる段の直前完了run。m7hbが数えた単発区間から、群Rと重複しないものを
  すべて採る（本数は測定で決まる。事前には固定しない）。

比較の手順:

1. 群R内の12本について、run長がすべて一致するかを見る。一致しなければ
   位置ごとの比較は長さが共通する範囲までに限る（その旨を明記する）。
2. 位置 p ごとに、群R内の12本が**互いに全て等しい**か（`eq`の真偽のみ）。
3. 全て等しかった位置 p について、群Sの同位置と等しいか。
4. 等しくなかった位置 p について、`cmp(群R, 群S)` の符号が群S全本で
   一貫するか。

## 事前登録する判定（測定前に固定。後から動かさない）

- **C1（要求レコード数説を支持）**: ある位置 p が存在して、(a) 群R内12本で
  互いに等しく、(b) 群Sの同位置と異なり、(c) 符号が「群R > 群S」で群S全本
  一貫する。
- **C2（内部状態説を支持＝測定では届かない）**: 上の条件を満たす位置が
  1つも無い。すなわち受信runの内容だけでは連続と単発を区別できない。
- **C3（どちらも支持しない）**: 位置は見つかるが符号が一貫しない、または
  「群R < 群S」である。
- **N（対応づけ不成立）**: 段階1の中止規則に該当し、段階2を実施しなかった。
- **O（測定不能）**: 陽性対照が通らない、ログが取れない等。

**どの判定になるかは予測しない。** 予測を書くと、そこへ寄せて読む余地が
できる。

## 事前登録する合格条件（測定前に固定）

1. **陽性対照（測定より先に通す）**
   - `build_mixed_rom ... --break-drive-selector`（1.46節の既存故障注入）で
     `tools/compare_l3_entry_fdc.py --after-frame 700`のunit/head差件数が
     0件より大きいこと。
   - `tools/analyze_error_exchange_shape_selftest.sh` が rc=0（全項目OK）。
   - `tools/recv_run_field_leak_selftest.sh` が rc=0（**陰性対照込み**——
     わざと値を出す版で赤くなることを含む）。
   - 新設comparatorの**故障注入**: 同一runどうしで`eq`が全位置True、
     1バイトだけ差し替えたrunでその位置だけFalseになること。
2. **判定規則をベースラインへ当てる**: 条件Oを独立2回測定し、段階1の
   3項目・段階2の比較結果が2回で完全一致すること（偽陽性を作らない
   ことの確認）。一致しなければ判定はOとする。
3. **`general_read_request`を通ることの確認**: 本測定の打鍵が当該経路を
   通ることを`--probe-site general_read_request --probe-mode cyl`で確認する
   （m7hjと同じ方法）。
4. **元ディスクを壊さない**: 測定前後で`disk#8`・`disk#10`の原本ダイジェスト
   が不変であること。

## 言えないこととして先に書いておくこと

- **位置 p が見つかっても、それが「レコード数」を意味する保証は無い。**
  C1は「区別する位置が要求の中にある」ことしか言わない。意味の特定は
  別の測定（介入）を要する。本稿でその位置の**値を読んで意味を推定する
  ことはしない**（3節・第23版と同じ線引き）。
- 本稿は`disk#10`という1本のディスク・1条件のサンプルである。他候補では
  連続READ構造が現れない（m7hb）ため、一般性は主張しない。
- C2が出ても「規則が存在しない」ではなく「受信runの内容では区別できない」
  としか言えない。

## 測定の実務

- 生ログ・ディスク複製・使い捨てスクリプトはリポジトリ外
  （scratchpad配下）に置き、コミットしない。
- コミットするのは本稿・新設ツール2本・結果ノート・（あれば）仕様更新
  のみ。
- コミット前に`tools/check_cleanroom.sh`と`git status`で`private/`由来の
  混入が無いことを確認する。

## 結果ノート

結果は `docs/notes/m7hm-recv-run-count-field-results.md` に書く。事前登録
（本稿）の条件・群の定義・判定規則を後から動かさない。手順逸脱・事故は
隠さず開示節に書く。

## 禁止（本稿の測定中も例外なく適用）

- 公式ROMのバイト列を読まない・出力しない・保存しない。逆アセンブルしない。
- 受信runのバイト値・FDCデータポート値・シリンダ値・PCN値を出力しない。
- 画面本文の生の行を報告・ノート・コミットメッセージ・ツール出力へ書かない
  （禁止事項7）。完了判定は`tools/check_l3_screen_output.py`・
  `tools/check_l3_entry_screen.py`で行う。
- 公式ディスクの実ファイル名を展開して表示しない。
- 第三者の逆アセンブルリスト・解析記事のコード断片を参照しない。

## 根拠リンク（`ls`で存在確認済み）

[m7hb](m7hb-consecutive-read-rule-results.md)（本稿の出所。count-comparator
を提案した箇所）・[m7ha](m7ha-consecutive-read-rule-preregistration.md)・
[m7gy](m7gy-command56-divergence-preregistration.md)・
[m7gz](m7gz-command56-divergence-results.md)（`general_read_request`探針
手法・1.57節の確立元）・
[m7gg](m7gg-data-disk-screening.md)（`disk#10`のREAD DATA件数の出所）・
[m7hj](m7hj-directory-size-consecutive-read-results.md)（直前周。軸を
戻す判断の出所）・
[m7hk](m7hk-screen-content-leak-path-closed.md)（漏洩経路の自己検査の型）・
`docs/spec/l3-subrom.md` 1.57節（第144版）・1.36節・1.37節・3節・
`tools/analyze_record_boundaries.py`（`window_a_runs`）・
`tools/analyze_main_to_sub.py`（`parse_iolog`）・
`tools/analyze_write_path.py`（`parse_commands`）・
`tools/compare_l3_entry_fdc.py`（`command_names`・
`stage_cylinder_consistency`・`--list-all-stages`）・
`tools/screen_content_leak_selftest.sh`（自己検査の型）・
`tools/analyze_error_exchange_shape_selftest.sh`・
`tools/stage_disk_by_digest.sh`・`tools/lib_l3_measure.sh`
（`build_mixed_rom`）・`tools/check_cleanroom.sh`。
