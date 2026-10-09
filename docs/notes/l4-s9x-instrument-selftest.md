# l4-s9x — 器具と自己検査（第1回）

2026-10-09。事前登録は l4-s9x-getput-preregistration.md。公式ROM・公式ディスクは実行していない。公式のGET配列形式、誤り、貼付け、速度、一致数はまだ測定していない。src/ は変更していない。commit/push はしていない。

## 成果物

- tools/l4_getput_measure.py: 固定88腕。measure/describe/report/tally/speed/expected/check/selftest。各腕2走、数値だけのTSV。公式は環境変数PC88_REF_ROM_DIRのみを受け取る。--work-dirは絶対パス必須。@省略はマニュアルで許された構文。
- tools/l4_getput_selftest.sh: 陰性対照と自作HEADのROMビルド・8腕×2走。公式の保存観測・既存期待値を開かない。
- tools/l4_getput_conform.sh: 自作全腕と公式期待値の比較入口。第1回では期待値が無いことを明示してrc=2で止まる。
- tools/run_all_selftests.sh: selftestを期待rc=0で登録。全体実行には別段の公式測定を伴う検査があり得るので、この回は全体を走らせず登録とshell構文だけを確認した。

画面写しは自作ラベルの厳密な整数だけを抽出する。非数値、重複、未完了は拒否し、例外にも本文を含めない。GET失敗時は配列を出さず、成功時だけ描いた模様を含む整数配列と初期値0の番兵を出す。単精度/倍精度配列の格納値を浮動小数として表示しない。PEEK/ROMメモリの探索/漢字PUTを行わない。生の画面・VRAM・PPM・印ログはfinallyで消す。IOログは採らない。

## 検証

自作HEAD **dcdd976**。作業先は許可範囲内の `tmp/s9x-work/`（依頼の `../tmp/s9x-work/` は書き込み拒否）。絶対パスで以下を実行し、長い出力は selftest-verified.log に保存して末尾だけを読んだ。

```sh
PYTHONDONTWRITEBYTECODE=1 tools/l4_getput_selftest.sh --work-dir "$PWD/tmp/s9x-work/selftest-verified"
```

- 手計算: little endianのヘッダ・行B/R/G・MSBの弱い仮説、白黒、5演算、省略XOR。
- 合成画面とVRAM: カラー9×3、白黒17×3、開始添字3の成功GETを数値として抽出し、配列違いと要素欠落を検出。
- 較正: 空画面、白1画素とPPM、0/32767/-32768/-1の符号。画素ずれ・画素欠落・黒表示・符号異常・較正腕欠落・終了印欠落・VRAM末尾非0を拒否。
- 計時: 印1/2の欠落・重複・逆順・負の差・回数プローブ欠落を拒否。1/2以外の初期化書き込みは計時印ではない。
- 合成期待値/check: 一致3腕、画素ずれ・配列違い・結果違い・腕欠落・2走不一致を検出。不一致の2走からの期待値生成を拒否。これは公式期待値ではなく一時的な自己検査fixtureで、終了時に消去した。
- 自作ROM: base-cls3/cal-vis/cal-num/fmt-c-9-3/put-c-pset/sp-nop/sp-get/sp-put の **8腕×2走が一致して関門通過**。GETとPUTの誤り2、GET失敗時の配列非取得、sp-get/sp-putでそれぞれ100回の誤りを確認。これは未実装の陰性対照であり、公式との一致数ではない。自作GET/PUTが実装された後は、この未実装対照を更新する必要がある。
- 自作ROMのVRAM故障注入で、空画面が1画素へ変わり判定がdifferになる。生写しの消去も確認。
- bash -n、Python ASTの構文、git diff --checkを確認。src/差分なし。公式期待値 tests/conformance/expected_l4_getput.tsv は未作成。

## 自己検査中に見つけた器具の修正

計時の順序関門を強めた最初の版は、印の書き込みログにある1/2以外の初期化も列に含め、sp-nop/sp-get/sp-putを関門落ちにした。失敗ログ selftest-final.log を作業先に残す。事前登録は印1・2の各1件と順序を要求するので、その2種類だけの列で順序を判定するよう修正した。逆順や重複を拒否し、初期値0を許す対照を追加。修正後の全自己検査が通過した。公式測定後に器具を曲げたものではない。

## 次回への入口

親は commit_1（事前登録）を先に確定し、続いて commit_2（器具）を確定する。次回の公式実行時にのみROM/DISK_DIR/DISKB環境変数を設定する。現器具はディスク無しのBASICで、ディスク画像を挿入しない。事前登録の全腕を2走し、関門落ちは追補を確定してから再測定する。公式と自作の結果ノート、期待値TSVの生成、conformは次回。速度は100回が誤りなしで終わった場合だけ成功測定とし、フレーム数を期待値の同値判定から外す。

commit_1.txt と commit_2.txt は tmp/s9x-work にある。作業物・資料画像・一時ビルド・生データをコミットに含めない。親が依頼の ../tmp/s9x-work に移す際も、事前登録の予測を変えない。
