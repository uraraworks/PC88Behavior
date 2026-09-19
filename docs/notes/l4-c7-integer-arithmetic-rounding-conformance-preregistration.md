# 事前登録: l4-c7 — 整数オペランドのみの四則演算丸め、適合場面固定

記録日: 2026-09-20
状態: 事前登録、測定・実装前。`l4-s7b`（`docs/notes/
l4-s7b-integer-only-rounding-results.md`、`90110f7`/`daa7080`）の延長。

## 位置づけ

`l4-s7b`で、単精度四則演算の丸めは「正しい丸め・タイはaway(0から遠い
側)」と確定した。`src/l4_basic/mbf_single.asm`のMBF_ADD/MBF_SUBは
コード上まだ偶数丸め、MBF_MULの既定は粗いROUNS再現のままで、l4-s7bの
申し送り(手順5)はこの食い違いを指摘するにとどめ実装は変えていない。

本ノートは、l4-s7bで使った40腕（整数オペランド、`print cdbl(<式>)`、
`docs/notes/l4-s7b-integer-only-rounding-preregistration.md`「腕」節
の表と完全に同一）を、`l4-c1b`/`l4-c2c`/`l4-c3`/`l4-c5`と同じ作法で
`tools/conform_l4.sh`の適合の場面として追加するための事前登録である。
名前は`l4-c6`が既に別の場面（`l4-c6-screen-editor-conformance-
results.md`、スクリーンエディタ）に使われているため、次の空き番号
`l4-c7`を採る。

**公式側の期待値を実装より先に固定し、自作main ROM側は
`not_implemented_yet`から始める**（CLAUDE.md「コミット規律」の「測定
コミットが実装コミットに先行する」の順序、`l4-c3`と同じ運用）。

## 比べるもの・記録する内容・期待値ファイルの書式

`l4-c3`「比べるもの」「記録する内容」節の定義をそのまま引き継ぐ
（`tools/l4_print_conform_record.py`を無改変で使う。出力行の非空白
セル列の(相対行,列0,文字コード)の並び・`Ok`行の相対行のみを見る。
値そのもの・SHA-256以外は一切コミットしない）。

期待値ファイル: `tests/conformance/expected_l4_arith.tsv`。書式は
`l4-c3`と同一:
```
arm<TAB>cell_count<TAB>ok_relative_row<TAB>sha256
```
見出しコメント`# group arith selfmade=<status>`で1群("arith")のみの
実装状態を管理する（`l4-c5`のprogramsと同じ、FS/FDのような細分は
しない）。

## 腕（40腕、1群"arith"）

`l4-s7b-integer-only-rounding-preregistration.md`「腕」節の表と
完全に同一（打鍵文字列・フレーム値とも変更しない。以下に腕idだけ
再掲する。式の内容は同ノート参照）。

- K1〜K8（加算、8腕: tie_disc×4・tie_ctrl×3・control×1）
- L1〜L8（減算、8腕: tie_disc×4・tie_ctrl×3・control×1）
- M1〜M16（乗算、16腕: tie_disc×3・tie_ctrl×2・half_plus_sticky×3・
  half_minus_eps×3・false_tie×3・control×2）
- N1〜N8（除算、8腕: half_minus_eps×2・half_plus_sticky×2・
  false_tie×3・control×1）

計40腕。

## 条件・フレーム

`l4-s7b`「測定方法・関門」節と同一（`l4-s3a`以来の条件・器具）。
写し(前)は全腕690固定。写し(後)・走行フレームは腕ごとに`l4-s7b`の表
の値をそのまま使う(打鍵文字列長からの機械的な式`line_end=700+8*
打鍵文字数(\nを1文字として含む)`・`dump=line_end+20`・
`run=dump+200`で導出済みの値を再計算せず埋め込む。l4-c3のように
実行時に式から算出する形にはしない——l4-s7bは腕によって打鍵文字数の
数え方の余地が無い`cdbl(...)`の固定形のため、値を直接埋め込むほうが
取り違えの余地が無い)。

自作main ROMは測定開始時のHEADで`python3 src/build_main_rom.py <新規
dir>`により1回だけ組み立て、以後の全走で複製して使い回す。公式ROM
一式は`PC88_REF_ROM_DIR`から走ごとに新しいROMディレクトリへ`cp -p`
するだけ（中身は読まない）。ディスク無し。

## 判定名

`l4-c3`と同一の4つ（`conform`/`not_conform`/`gate_failed`/
`not_implemented_yet`）。定義も同一。

## 関門

`l4-c3`のG1〜G5・G8と同一。

- G1 器具の自己検査
- G2 取りこぼし0・打てない文字の警告0
- G3 決定論性（公式ROM側、各腕2走の記録が完全一致）
- G4 陰性対照（何も打たない走で差分0件。既存の陰性対照を使い回す）
- G5 自作ROM側の`tools/l4_basic_selftest.sh`・`tools/l3_main_
  selftest.sh`が測定時HEADでrc=0（自作側の照合を行う腕についてのみ）
- G8 出力完了の確認（`ok_relative_row`が得られる。現れない腕は
  `gate_failed`）

## 検出力の自己検査（`tools/conform_l4.sh`が常に実行する。公式環境
不要）

`l4-c3`分の自己検査a〜dと同じ構造（合成VRAM写しでSHA-256の検出力・
期待値の件数/SHA-256改変の検出を確認）を、ARITH場面用に追加する。
群の印切り替え自己検査e（`not_implemented_yet`→`implemented`で
実際に判定が走ることの確認）も同様に追加する。

## 判定後の行き先

- 公式側の期待値40腕すべてが固定できたら（G1〜G4・G8を満たし、各腕
  2走の記録が一致）、`tests/conformance/expected_l4_arith.tsv`を
  `# group arith selfmade=not_implemented_yet`の状態でコミットする。
- `src/l4_basic/mbf_single.asm`のMBF_ADD/MBF_SUB/MBF_MUL/MBF_DIVを
  `docs/spec/l4-basic.md`5.3a節（away丸め）に合わせて直したあと、
  群の印を`implemented`へ切り替えて自作側の照合を行う。
- 既存の適合（`l4-c1b`〜`l4-c5`・`tools/l4_basic_selftest.sh`・
  `tools/l3_main_selftest.sh`）が壊れていないことも合わせて確認する
  （丸めの変更はMBF_FOUTの内部スケーリング(`*`/`/`10)にも影響しうる
  ため）。

## 結果ノート

`docs/notes/l4-c7-integer-arithmetic-rounding-conformance-results.md`
に書く。関門・判定名・腕は本ノートから動かさない。

## 根拠リンク

`docs/notes/l4-s7b-integer-only-rounding-preregistration.md`（腕・
フレーム値の原型）・`docs/notes/l4-s7b-integer-only-rounding-
results.md`（`daa7080`、away丸めの確定・実装への申し送り）・
`docs/notes/l4-c3-float-print-conformance-scene-preregistration.md`
（`71d81a8`、比べるもの・記録する内容・期待値ファイルの作法・判定名・
関門・検出力自己検査の直接の原型）・`tools/conform_l4.sh`（既存の
適合テストランナー）・`docs/spec/l4-basic.md`第3.9版5.3a節（丸め
規則の確定根拠）。
