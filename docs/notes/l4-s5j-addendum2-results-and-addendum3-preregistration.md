# l4-s5j — 追補2結果と追補3の事前登録

記録日: 2026-10-03。追補2は親が公式ROMで測定済み。
前回の登録は [追補1結果と追補2の事前登録](l4-s5j-addendum1-results-and-addendum2-preregistration.md)。
本担当は公式ROM測定を実行せず、追補3の候補と腕を測定前に固定する。

## 追補2の結果

A群60腕各2走。unstable 0・gate_failed 0。
親の集計と自分で打った行のLIST観測を根拠とする。
生の結果の所在: `../tmp/l4s5j-work/official_add2.tsv`。

| 候補 | agree | differ |
|---|---:|---:|
| G_A | 29 | 31 |
| G_B | 20 | 40 |
| G_0 | 10 | 50 |
| G_C | 44 | 16 |
| G_D | 40 | 20 |
| G_E | 58 | 2 |
| G_F | 59 | 1 |
| G_G | 48 | 12 |

G_Eの外れはa47とa48。G_Fの外れはa48のみ。
以下は入力した行に対応するLIST表示だけで、他の画面本文は含まない。

| 腕 | 打った行 | 観測LIST行 | 比較 |
|---|---|---|---|
| a47 | `1040 go subx.5` | `1040 GOSUB .5` | G_Eは不一致、G_Fは一致 |
| a48 | `1050 go subx&h1` | `1050 GOSUB &H1` | G_E/G_Fは `1050 GOSUB&H1` で不一致、G_Gは一致 |

## 追補3の固定候補

G_A〜G_Gの予測は変更しない。**G_H**を追加する。
G_HはG_Eと同じだが、`GOSUB` の後に空白1個を出す条件を、
「残りの最初の文字がASCIIの英字・数字・`.`・`&`」とする。
これは数値定数か名前の連なりを始めうる文字を候補条件としたもの。
`go`＋空白ちょうど1個＋`sub`を詰め、直後の1文字は何であれ消費する。
続く空白は消費せず、残りには既存N_Dを掛ける。行末なら `GOSUB` だけ。
文字列・REM・DATA・`'`以降・名前内部は既存の保護を維持する。
小文字ASCIIの打鍵を前提とし、行末空白は抽出器に合わせて落とす。

### 既存60腕の事後照合

selftest内で `write_predict(..., add3=True)`（predict-add3と同じ出力処理）を通し、
a01〜a60のG_H予測署名を親のofficial_add2.tsvの走1署名と照合した。
同TSVの60腕は全て走1・走2が安定。比較用の60署名をselftestに固定した。

| 候補 | 既存60腕の署名一致 | 矛盾する腕 |
|---|---:|---|
| G_H | 60/60 | なし |

G_Hは既存60腕をすべて再現した。ただし追補2を見て作った事後候補なので、
この一致を独立した支持として扱わず、以下の新しい腕で確かめる。
追補3の新規腕の観測は未取得。

## 追補3の腕

正本は `tools/l4_s5j_measure.py` の `build_add3_arms()`。
既存A群60腕a01〜a60の入力・id・先行入力・番号帯を変えず全て再測定する。
新規18腕を加え、合計78腕（A群のみ）各2走。B群は測らない。
新規腕は本文が数字で始まらず、表示可能ASCIIのみ、小文字で打鍵する。
先行入力・エラー表の探りはなし。行番号2000〜2170は既存帯と衝突しない。

| id | 打った行 | 番号帯 |
|---|---|---|
| a61 | `2000 go subx&o7` | 2000〜2000 |
| a62 | `2010 go subx&7` | 2010〜2010 |
| a63 | `2020 go subx&` | 2020〜2020 |
| a64 | `2030 go suba&h10` | 2030〜2030 |
| a65 | `2040 go sub1&h1` | 2040〜2040 |
| a66 | `2050 go subx<1` | 2050〜2050 |
| a67 | `2060 go subx>1` | 2060〜2060 |
| a68 | `2070 go subx/2` | 2070〜2070 |
| a69 | `2080 go subx^2` | 2080〜2080 |
| a70 | `2090 go subx\2` | 2090〜2090 |
| a71 | `2100 go subx@` | 2100〜2100 |
| a72 | `2110 go subx!` | 2110〜2110 |
| a73 | `2120 go subx 1.5` | 2120〜2120 |
| a74 | `2130 go subx.` | 2130〜2130 |
| a75 | `2140 go subx..5` | 2140〜2140 |
| a76 | `2150 go subxa.b` | 2150〜2150 |
| a77 | `2160 a=1:go subx&h1:end` | 2160〜2160 |
| a78 | `2170 go sub&&h1` | 2170〜2170 |

## 測定・判定・出力

毎腕・毎走 `new`、先行入力、対象入力、`cls`、`list` を打つ既存手順を維持する。
打てない文字・重複LIST行・A群の行数が1本でない場合は `gate_failed`。
2走の署名が異なる場合は `unstable`。安定した署名を予測と比較し、
候補ごとのagree/differ/unstable/gate_failedを集計する。
全78腕agreeかつunstable・gate_failedゼロの場合だけ全腕を説明するとする。

`predict-add3 --out` は78腕×9候補（702予測）の入力・予測行・署名を出す。
`measure-add3 --rom-dir --out [--official] [--show-differs]` はA群のみ測り、
G_A/G_B/G_0/G_C/G_D/G_E/G_F/G_G/G_Hの分類列を出す。
通常は観測本文を出さない。`--show-differs` は安定した腕のG_Hがdifferのとき、
自分で打った行に対応する観測LIST行を出す（全候補differの既存条件も維持）。
不安定・関門不成立の腕や他の画面本文は出さない。
既存サブコマンドの腕・予測・出力は変更しない。

```sh
python3 tools/l4_s5j_measure.py predict-add3 --out /tmp/l4s5j-add3-predictions.tsv
python3 tools/l4_s5j_measure.py measure-add3 --rom-dir "$PC88_REF_ROM_DIR" --official --out /tmp/l4s5j-add3-signatures.tsv
tools/l4_s5j_selftest.sh --work-dir /private/tmp/l4s5j-add3-work
```

公式測定コマンドは親向けの手順例。本担当は実行しない。
検査は指定の `tools/l4_s5j_selftest.sh` のみ。
G_Hのa47・a48、`go sub10`→`GOSUB 0`、`go subx:end`→`GOSUB:END`、
`go sub1  x`→`GOSUB  X` の再現を検査する。
予測署名60腕照合、旧候補の予測不変、78腕156走の合成対照、
show-differsのG_H条件と不安定・関門不成立腕抑制も検査する。
`tests/conformance/`・`src/`は変更せず、コミット・git addは行わない。

検査結果: 上記selftestは終了コード0、既存・追加項目すべてOK。
公式ROM測定は未実行。
