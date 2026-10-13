# l4-s9z INPUT / LINE INPUT 第2回結果

2026-10-13。CLAUDE.mdに従い画面本文・公式ROMバイト列を閲覧・転記しない。src変更、commit、run_all実行なし。原事前登録30ae92e、原器具220837d。追補1で失敗診断を保存する。観測は同一操作の独立2走と各段300フレーム離れた2時点一致に基づく。画面比較は同じROM内の事前候補の一致分類であり、ROM間の生署名照合ではない。

元測定は75腕中72通過。3腕の元診断はValueError/223行のみで原因は不明。失敗時に段情報を捨てる器具の不備を追補1で修正し、関門を維持して再測定した。構文2腕は入力0回、安定・到達印あり・完了印なし・要求関門成立・入力列枯渇。直接モードへの移行とは断定しない。追補1続編で固定入力を延長した。構文2腕は入力1回後ERR2/誤り1/初期値12/終了印1で通過し、エラー番号予測は一致。retry-shortは最初の不足後q-space-redo-upperで全体再入力となり、2回目も不足して列枯渇。元の不足時追加要求予測は外れ。

数値印の配列はキー順。先頭2個はERRと誤り件数、その後は各変数のFIX値（小数腕のみ100倍）、文字列はLEN/先頭ASC/末尾ASC/ASC和、巨大数腕はSGN/範囲外フラグ/FIX作業印。終了印は通過腕すべて1。空文字のASC32は器具の規約。候補列は段0から順で、[]はゼロ一致（候補外）。比較不能・対象外は数値を無効にしない。候補名から画面本文を復元しない。

| 腕 | 元予測（数値・分類で要約） | 観測値印 | 入力回数 | 画面状態 / 段別一致候補ID | 予測判定 |
|---|---|---|---|---|---|

| cal-num | 値印0,-32768,32767 | [0, 0, 0, -32768, 32767] | 0 | excluded / [[]] | 当たり |
| cal-error | ERR13・初期値12 | [13, 1, 12] | 0 | excluded / [[]] | 当たり |
| prompt-semi | semi/plain=q-space、comma=none、nonewline=改行抑止 | [0, 0, 1] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| prompt-comma | semi/plain=q-space、comma=none、nonewline=改行抑止 | [0, 0, 1] | 1 | valid / [["space"], ["none"]] | 当たり |
| prompt-plain | semi/plain=q-space、comma=none、nonewline=改行抑止 | [0, 0, 1] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| prompt-nonewline | semi/plain=q-space、comma=none、nonewline=改行抑止 | [0, 0, 1] | 1 | valid / [["q-space"], []] | 不明（継続印の位置が候補外） |
| count-1 | 左から1〜1 | [0, 0, 1] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| count-2 | 左から1〜2 | [0, 0, 1, 2] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| count-3 | 左から1〜3 | [0, 0, 1, 2, 3] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| count-4 | 左から1〜4 | [0, 0, 1, 2, 3, 4] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| count-5 | 左から1〜5 | [0, 0, 1, 2, 3, 4, 5] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| count-6 | 左から1〜6 | [0, 0, 1, 2, 3, 4, 5, 6] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| count-7 | 左から1〜7 | [0, 0, 1, 2, 3, 4, 5, 6, 7] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| count-8 | 左から1〜8 | [0, 0, 1, 2, 3, 4, 5, 6, 7, 8] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| type-default | 各数値型・文字列・配列を受理し固定値代入 | [0, 0, 23] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| type-int | 各数値型・文字列・配列を受理し固定値代入 | [0, 0, 23] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| type-single | 各数値型・文字列・配列を受理し固定値代入 | [0, 0, 23] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| type-double | 各数値型・文字列・配列を受理し固定値代入 | [0, 0, 23] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| type-string | 各数値型・文字列・配列を受理し固定値代入 | [0, 0, 3, 120, 122, 363] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| type-array | 各数値型・文字列・配列を受理し固定値代入 | [0, 0, 23] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| type-mixed | 各数値型・文字列・配列を受理し固定値代入 | [0, 0, 1, 2, 3, 2, 120, 121, 241, 4] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| number-sign | 符号・小数・E/D指数・空白を受理、空=0、基数は予測なし | [0, 0, -12] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| number-plus | 符号・小数・E/D指数・空白を受理、空=0、基数は予測なし | [0, 0, 12] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| number-decimal | 符号・小数・E/D指数・空白を受理、空=0、基数は予測なし | [0, 0, 125] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| number-exp | 符号・小数・E/D指数・空白を受理、空=0、基数は予測なし | [0, 0, 100] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| number-dexp | 符号・小数・E/D指数・空白を受理、空=0、基数は予測なし | [0, 0, 100] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| number-hex | 符号・小数・E/D指数・空白を受理、空=0、基数は予測なし | [0, 0, 16] | 1 | valid / [["q-space"], ["q-space"]] | 予測なし（基数） |
| number-oct | 符号・小数・E/D指数・空白を受理、空=0、基数は予測なし | [0, 0, 8] | 1 | valid / [["q-space"], ["q-space"]] | 予測なし（基数） |
| number-spaces | 符号・小数・E/D指数・空白を受理、空=0、基数は予測なし | [0, 0, 12] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| number-empty | 符号・小数・E/D指数・空白を受理、空=0、基数は予測なし | [0, 0, 0] | 1 | excluded / [["q-space"], ["q-space", "q"]] | 当たり |
| string-bare | 引用符除去・引用内保持・非引用端空白除去・空LEN0 | [0, 0, 2, 120, 121, 241] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| string-quoted | 引用符除去・引用内保持・非引用端空白除去・空LEN0 | [0, 0, 2, 120, 121, 241] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| string-comma | 引用符除去・引用内保持・非引用端空白除去・空LEN0 | [0, 0, 3, 120, 121, 285] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| string-spaces | 引用符除去・引用内保持・非引用端空白除去・空LEN0 | [0, 0, 2, 120, 121, 241] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| string-quoted-spaces | 引用符除去・引用内保持・非引用端空白除去・空LEN0 | [0, 0, 4, 32, 32, 305] | 1 | valid / [["q-space"], ["q-space"]] | 当たり |
| string-empty | 引用符除去・引用内保持・非引用端空白除去・空LEN0 | [0, 0, 0, 32, 32, 0] | 1 | excluded / [["q-space"], ["q-space", "q"]] | 当たり |
| retry-short | 不足は追加要求 | [0, 0, 4, 5] | 3 | valid / [["q-space"], ["q-space-redo-upper"], ["q-space-redo-upper-twice"], ["q-space-redo-upper-twice"]] | 外れ（再入力） |
| retry-excess | 余剰・型違いは再入力 | [0, 0, 4, 5] | 2 | valid / [["q-space"], ["q-space-redo-upper"], ["q-space-redo-upper"]] | 当たり |
| retry-bad-first | 余剰・型違いは再入力 | [0, 0, 4, 5] | 2 | valid / [["q-space"], ["q-space-redo-upper"], ["q-space-redo-upper"]] | 当たり |
| retry-bad-last | 余剰・型違いは再入力 | [0, 0, 4, 5] | 2 | valid / [["q-space"], ["q-space-redo-upper"], ["q-space-redo-upper"]] | 当たり |
| retry-overflow | 桁あふれは再入力またはERR6、予測なし | [6, 1, 1, 0, 12] | 1 | valid / [["q-space"], ["q-space"]] | 予測なし（ERR6観測） |
| retry-int-overflow | 桁あふれは再入力またはERR6、予測なし | [6, 1, 12] | 1 | valid / [["q-space"], ["q-space"]] | 予測なし（ERR6観測） |
| line-semi | 区切り・引用符・両端空白保持、接尾none、nonewline改行抑止 | [0, 0, 6, 32, 34, 385] | 1 | valid / [["space"], ["none"]] | 一部外れ（末尾空白2個非保持） |
| line-plain | 区切り・引用符・両端空白保持、接尾none、nonewline改行抑止 | [0, 0, 6, 32, 34, 385] | 1 | valid / [["space"], ["none"]] | 一部外れ（末尾空白2個非保持） |
| line-nonewline | 区切り・引用符・両端空白保持、接尾none、nonewline改行抑止 | [0, 0, 6, 32, 34, 385] | 1 | valid / [["space"], []] | 一部外れ（末尾空白2個非保持）・改行不明 |
| line-empty | LEN0 | [0, 0, 0, 32, 32, 0] | 1 | excluded / [["space"], ["space", "none"]] | 当たり |
| line-numeric | ERR13 | [13, 1, 12] | 0 | valid / [[]] | 当たり |
| syntax-input-separator | ERR2（入力前に完了する操作設計） | [2, 1, 12] | 0 | excluded / [[]] | 当たり |
| syntax-input-missing | ERR2（入力前に完了する操作設計） | [2, 1, 12] | 1 | excluded / [[], []] | ERR2一致・入力前完了の想定外 |
| syntax-input-variable | ERR2（入力前に完了する操作設計） | [2, 1, 12] | 1 | excluded / [[], []] | ERR2一致・入力前完了の想定外 |
| syntax-line-separator | ERR2（入力前に完了する操作設計） | [2, 1, 12] | 0 | excluded / [[]] | 当たり |
| syntax-line-missing | ERR2（入力前に完了する操作設計） | [2, 1, 12] | 0 | excluded / [[]] | 当たり |
| syntax-line-variable | ERR2（入力前に完了する操作設計） | [2, 1, 12] | 0 | excluded / [[]] | 当たり |
| direct-input | ERR12 | [0, 0, 7] | 1 | valid / [[], []] | 外れ（受理） |
| direct-line | ERR12 | [0, 0, 1, 55, 55, 55] | 1 | valid / [[], []] | 外れ（受理） |
| length-input-79 | 上限255仮説 | [0, 0, 79, 120, 120, 9480] | 1 | valid / [["q-space"], []] | 上限は不明（観測254で頭打ち） |
| length-line-79 | 上限255仮説 | [0, 0, 79, 120, 120, 9480] | 1 | valid / [["space"], ["none"]] | 上限は不明（観測254で頭打ち） |
| length-input-80 | 上限255仮説 | [0, 0, 80, 120, 120, 9600] | 1 | valid / [["q-space"], []] | 上限は不明（観測254で頭打ち） |
| length-line-80 | 上限255仮説 | [0, 0, 80, 120, 120, 9600] | 1 | valid / [["space"], ["none"]] | 上限は不明（観測254で頭打ち） |
| length-input-81 | 上限255仮説 | [0, 0, 81, 120, 120, 9720] | 1 | valid / [["q-space"], []] | 上限は不明（観測254で頭打ち） |
| length-line-81 | 上限255仮説 | [0, 0, 81, 120, 120, 9720] | 1 | valid / [["space"], []] | 上限は不明（観測254で頭打ち） |
| length-input-127 | 上限255仮説 | [0, 0, 127, 120, 120, 15240] | 1 | valid / [["q-space"], []] | 上限は不明（観測254で頭打ち） |
| length-line-127 | 上限255仮説 | [0, 0, 127, 120, 120, 15240] | 1 | valid / [["space"], []] | 上限は不明（観測254で頭打ち） |
| length-input-128 | 上限255仮説 | [0, 0, 128, 120, 120, 15360] | 1 | valid / [["q-space"], []] | 上限は不明（観測254で頭打ち） |
| length-line-128 | 上限255仮説 | [0, 0, 128, 120, 120, 15360] | 1 | valid / [["space"], []] | 上限は不明（観測254で頭打ち） |
| length-input-129 | 上限255仮説 | [0, 0, 129, 120, 120, 15480] | 1 | valid / [["q-space"], []] | 上限は不明（観測254で頭打ち） |
| length-line-129 | 上限255仮説 | [0, 0, 129, 120, 120, 15480] | 1 | valid / [["space"], []] | 上限は不明（観測254で頭打ち） |
| length-input-254 | 上限255仮説 | [0, 0, 254, 120, 120, 30480] | 1 | valid / [["q-space"], []] | 上限は不明（観測254で頭打ち） |
| length-line-254 | 上限255仮説 | [0, 0, 254, 120, 120, 30480] | 1 | valid / [["space"], []] | 上限は不明（観測254で頭打ち） |
| length-input-255 | 上限255仮説 | [0, 0, 254, 120, 120, 30480] | 1 | valid / [["q-space"], []] | 上限は不明（観測254で頭打ち） |
| length-line-255 | 上限255仮説 | [0, 0, 254, 120, 120, 30480] | 1 | valid / [["space"], []] | 上限は不明（観測254で頭打ち） |
| length-input-256 | 上限255仮説 | [0, 0, 254, 120, 120, 30480] | 1 | valid / [["q-space"], []] | 上限は不明（観測254で頭打ち） |
| length-line-256 | 上限255仮説 | [0, 0, 254, 120, 120, 30480] | 1 | valid / [["space"], []] | 上限は不明（観測254で頭打ち） |
| length-input-260 | 上限255仮説 | [0, 0, 254, 120, 120, 30480] | 1 | valid / [["q-space"], []] | 上限は不明（観測254で頭打ち） |
| length-line-260 | 上限255仮説 | [0, 0, 254, 120, 120, 30480] | 1 | valid / [["space"], []] | 上限は不明（観測254で頭打ち） |

## 確定範囲と留保

- INPUTの要求分類はsemi/plainがq-space、commaは入力後none。入力前spaceは既知等価組の代表であり、接尾空白の存在を断定しない。先頭セミコロン2腕は完了時ゼロ一致で、改行抑止はこの候補群では未確定。
- 変数1〜8個の左からの正常代入を確認。8を上限とは断定しない（9個以上は未測定）。通常数値・整数・単精度・倍精度・文字列・整数配列要素・混在を受理。
- 符号、小数、E/D指数、両端空白を数値として受理。基数腕の値は16/8。空数値0、空文字LEN0。
- INPUT文字列は固定短文の数値印で引用符除去、引用内区切り・空白保持、非引用端空白除去と一致。数値印は任意文字列を一意に識別するものではない。
- 余剰と数値型違いは2回で値4,5、q-space-redo-upperに一致し、全体を再入力。巨大数・整数桁あふれはERR6/誤り1/入力1、初期値12保持。再入力途中の部分代入は不明。
- LINE INPUTの固定文字列はLEN6/先頭32/末尾34/和385。区切りと引用符、先頭空白は保持するが、入力末尾の空白2個の保持予測には一致しない。入力器のスケジュールは空白を削除しないが、編集段階と命令段階の区別は未測定。数値変数はERR13、空はLEN0。
- INPUT/LINE INPUTは直接モードで受理、ERR0/入力1。ERR12予測は外れ。
- 長さ固定点79/80/81/127/128/129/254でLENは投入長と一致、255/256/260では両命令とも254。先頭末尾120、和120×LEN。入力編集上限と文字列命令上限は分離できないため、言語上限255は確定しない。

## 検証と引き渡し

再測定3腕はすべて独立2走一致で通過。最終画面分類は有効64腕・対象外11腕・比較不能0腕。retry-shortは値4,5、ERR0/誤り0/入力3/終了印1。構文2腕はERR2/誤り1/入力1/初期値12/終了印1。元72腕と再測定3腕をref-final.tsvへ合成し、較正2腕が元測定と再測定で観測完全一致することも確認した。合成は欠測を書き換えず、元ref.tsv/diagnostic.tsv/continuation.tsvを保持する。

`expected`コマンドで `tests/conformance/expected_l4_input.tsv`（75腕）を作成。`check --measured tmp/s9z-work/ref-final.tsv` は75一致/0不一致、rc=0。`check --measured tmp/s9z-work/repair2-rerun/selfrun.tsv` は26一致/49不一致、rc=1。自作のうち3腕は追補前の操作列で、改訂checkでは操作列不一致のため欠測扱い。保存された入力回数もretry-short=1、構文2腕=0で公式3/1/1と異なる。残り72腕で26一致/46不一致。49をすべて実装だけの原因と断定しない。

自己検査は両measure冒頭で成功（入力列枯渇、完了印のみ・値印欠落の拒否、画面候補同一化/範囲ずらし、画面欠落、数値改変、較正、2走、本文漏洩の陰性対照）。失敗診断を保存してもvalid=false。既存72腕は改訂器具でも関門維持。プロセス情報取得psは拒否されたため実行時間等は不明とし測定を継続した。srcビルドは今回実行せず、ユーザー指定済み自作測定を使用。src変更・commit・run_allなし。

親のコミット順序:

1. 事前登録追補: `docs/notes/l4-s9z-addendum1-diagnostics.md`、`docs/notes/l4-s9z-addendum1-continuation.md`。先に確定した予測は変更しない。
2. 器具: `tools/l4_input_measure.py`（失敗段診断保持、固定入力列延長、2回再入力候補、陰性対照、公式ROMの器具側ハッシュ読出し廃止・公式checkpoint再利用停止）。
3. 測定: `docs/notes/l4-s9z-results.md`、`tests/conformance/expected_l4_input.tsv`。数値・署名・候補分類のみ。作業TSV/ログ/診断器具写しはtmp/s9z-work内に保持しコミット対象にしない。

## 失敗診断（追補1、独立2走一致）

| 腕 | 段 | stable / ready / completed | 変化セル数 | 一致候補ID | SHA-256（14行1120文字） |
|---|---|---|---|---|---|
| retry-short | 0 | 1 / 1 / 0 | 0 | ["q-space"] | 4e0fd13b56e481e3335621e0eac5abf723e0a222cef36f113ac2d462ae3f1375 |
| retry-short | 1 | 1 / 1 / 0 | 1 | ["q-space-redo-upper"] | efe873fb2300c1d56647f8feac4ce44f86515699c80b8aca003c27bcfa01f22a |
| retry-short | 2 | 1 / 1 / 0 | 1 | [] | cfcaebad405a303271f987df572f2ec7f6d019c37982703299bb5dfe3589bedf |
| syntax-input-missing | 0 | 1 / 1 / 0 | 0 | [] | 4e0fd13b56e481e3335621e0eac5abf723e0a222cef36f113ac2d462ae3f1375 |
| syntax-input-variable | 0 | 1 / 1 / 0 | 0 | [] | cfb2ad6a870bd2525ff3426df31983144bcb89f9d7bfbdce1e3d2c65fbc60b43 |
