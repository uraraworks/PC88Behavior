# m6i-k 追補1 — 対照から成否を外し、解釈と成否を別々に判定して取り直す — 事前登録

記録日: 2026-09-30  
状態: **測定前・判定器未作成**  
本体: `docs/notes/m6i-k-read-request-geometry-preregistration.md`（以下「本体」）、結果 `docs/notes/m6i-k-results.md`（d238280）

## 0. 何のための追補か

本体の測定は `m6i_k_inconclusive` だった。対照（行1・6）の条件に「成功」を含めたため、主問（解釈）と別の軸である
P1 の効果（成否）で P1=0x00 の腕が対照失敗になった（結果 §4）。

本追補は**判定規則だけを直し、同じ器具・同じ腕・同じ座標で新しく2走ずつ取り直す**。
**本体の結果を見た後の事前登録である**ことを明記する。したがって本追補の予測（§4）は、結果 §3 の観察を
**測定前に固定した再現**であり、新しい発見の主張ではない。再現しなければ結果 §3 の観察は捨てる。

## 1. 変えないもの

- 器具: コミット 3060a34 の `tools/measure_m6ik.sh`・`tools/analyze_m6ik.py`・測定ROMの組み方（`src/build_main_rom.py` の `--inject-m6ik-arm`）・
  `tools/m6ik_frozen.tsv`。**1バイトも変えない**（G11）。
- 腕（本体 §3）、座標（本体 §4）、行の分類（本体 §5.1・§5.2、訂正後）、`index_disagree` の扱い（本体 §8 訂正後）。
- 関門 G2〜G9（本体 §6）。`measure_m6ik.sh` が従来どおり検査する。
- 公式からは sub ROM（`DISK.ROM`）だけを使い、公式ディスクは使わない。

## 2. 変えるもの

### 2.1 対照の条件

行1・6 の対照は **「`agree` に分類されたこと」だけ**を条件にする（READ DATA が発行され、その C/H/R が表の座標と一致した）。
**成否は条件に入れない。** `no_read`・`other`・`index_disagree` なら対照失敗（`control_failed`）。

### 2.2 判定を2つに分ける

**主判定（解釈）** — 本体 §8 の総合判定名（`m6i_k_conversion_by_17`・`m6i_k_conversion_needs_both`・`m6i_k_conversion_by_p1_after_17`・
`m6i_k_no_conversion`・`m6i_k_other`・`m6i_k_measurement_blind`・`m6i_k_inconclusive`・`gate_failed`）を、§2.1 の対照条件で求める。
腕の要約（`logical`／`cylinder`／`split_by_drive`／`mixed`）と K-FR・`index_disagree` の扱いは本体どおり。

**副判定（成否）** — 主判定が `gate_failed`・`m6i_k_inconclusive`・`m6i_k_measurement_blind` 以外のときだけ求める。
行1〜6 の成否（本体 §5.2 の「最終的に256位置を受け取れたか」）で:

- `p1_success_split`: P1=0x00 の腕（K-00・K-F0）は行1〜6 が**すべて** `failed`、P1=0x01 の腕（K-01・K-F1・K-M1・K-FR）は行1〜6 が**すべて** `success`。
- `p1_success_other`: それ以外。腕×行の成否表を記録する。

**副次（本体 §8 のまま）**: K-M1 が `split_by_drive`（ドライブ1の行2・5 が `logical`、ドライブ2の行3・4 が `cylinder`）なら
「`0x17` の2バイト目のビット0がドライブ1」と記録する。事前送信のあとの sub `OUT $FD` の件数（全腕）も記録する。

## 3. 走らせ方

- 測定は、判定器を入れたコミット（作業ツリーがクリーンな HEAD）で `tools/measure_m6ik.sh` を新しい作業先に対して1回実行する（6腕×2走）。
  **本体の測定（`run2`）の結果ファイルは使わない。**
- `measure_m6ik.sh` が出す本体規則の判定（`judgment.json`）は記録するが、本追補の判定には使わない。
  本追補の判定は、同じ走の腕ごとの結果ファイル（12個）を新しい判定器 `tools/judge_m6ik_add1.py` に渡して求める。
- G1: **測定するのと同じコミット**で `tools/run_all_selftests.sh` を回し rc=0 であること（本体の測定では1行ぶん違うコミットだった。結果 冒頭の開示）。

## 4. 予測（結果 §3 を固定した再現）

- 主判定 `m6i_k_conversion_by_17`（K-F0・K-F1 が `logical`、K-00・K-01 が `cylinder`）。
- 副判定 `p1_success_split`。
- K-M1 は `split_by_drive`、事前送信のあとの `OUT $FD` は全腕0件。
- 各腕の行ごとの分類・成否・READ DATA の回数が、本体の測定（d238280 の表）と一致する。一致しない欄があれば記録する
  （主判定・副判定の規則には入れない）。

## 5. 関門（本体 G1〜G9 に加えて）

- **G10 判定器の検出力**: `judge_m6ik_add1.py` の自己検査で、合成の腕結果について次を示す。
  (a) 対照行が `agree` かつ `failed` → 対照失敗に**ならない**。
  (b) 対照行が `no_read`・`other`・`index_disagree` → 対照失敗になる。
  (c) P1=0x00 の腕に `success` の行が1つ → `p1_success_other`。
  (d) P1=0x01 の腕に `failed` の行が1つ → `p1_success_other`。
  (e) `logical` の腕が0本 → `m6i_k_conversion_by_p1_after_17` にならない。
  (f) K-FR に `other` 以外の行 → `m6i_k_measurement_blind`、副判定は求めない。
  (g) 結果ファイルが12個でない・腕が欠ける・2走で欄が食い違う → `m6i_k_inconclusive` 以下（合格側に倒れない）。
- **G11 器具の不変**: `tools/measure_m6ik.sh`・`tools/analyze_m6ik.py`・`tools/judge_m6ik.py`・`tools/check_m6ik_gates.py`・
  `tools/m6ik_frozen.tsv`・`src/build_main_rom.py` の SHA-256 が、コミット 3060a34 のものと一致する。判定器が測定前に検査し、違えば `gate_failed`。
- **G12 本追補の凍結**: 判定名・予測・腕と P1 の対応を判定器の設定に固定し、本稿と違えば `gate_failed`（本体 G8 と同じ作り）。

## 6. 判定後の行き先

- 主判定 `m6i_k_conversion_by_17` かつ副判定 `p1_success_split`: 仕様書 l3-subrom に次を起こす。
  (1) `0x02` の T は、`0x17, m` で有効にされたドライブでは C=T>>1・H=T&1、そうでないドライブでは C=T・H=0。
  確かめたのは「`m=0x0F` で両ドライブが有効」「`m=0x01` でドライブ1だけが有効」の2点だけなので、仕様書には
  「m のビット0がドライブ1に対応する。ドライブ2に対応するビットは `0x0F` に含まれるが、どのビットかは未測定」と書く。
  (2) P1=0x00 の `0x02` は End of Cylinder で失敗し、P1=0x01 は1セクタ読みとして成功する（P1 の他の値は未測定）。
  (3) `0x17` に応答は無い。(4) 1.36節の「`0x17` 長さ7」は `0x17, m` と後続の `0x02` 要求の連結の可能性が高いと注記する（確定はしない）。
  そのあと実装（自作 main の起動時の `0x17, 0x0F` 送信と、読み要求の P1=0x01、自作 sub の `0x17` 対応）を、
  このセッションの文脈を持たない担当へ渡す。FILES・LOAD・SAVE の適合器具への hybrid 腕の追加も同じ担当へ。
- 予測と違う主判定・副判定: 仕様書へは書かない。表を記録し、次の問いを立てる。結果 §3 の観察のうち再現しなかったものは捨てる。
- `m6i_k_inconclusive`・`m6i_k_measurement_blind`・`gate_failed`: 器具ではなく判定器か手順の不具合を疑い、追補2で直してから取り直す。

## 7. 本文に出さないもの

本体 §10 と同じ。画面は使わない。データ部の値列は出さない（件数・SHA-256・刻印4バイト・FDC 引数・結果ステータスの復号名のみ）。
