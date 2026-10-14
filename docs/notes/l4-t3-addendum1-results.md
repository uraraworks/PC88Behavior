# l4-t3 追補1 OUT正常出力の結果

2026-10-14。事前登録は [out-output-preregistration](l4-t3-addendum1-out-output-preregistration.md)、器具は `tools/l4_out_output_measure.py`。公式ROMのバイト列・画面本文は読まない／出さない。src変更・git commitなし。作業はtmp/t3-work/のみ。

## 測定条件と証拠

自作HEADは64623dd。`src/build_main_rom.py`を実行し、tmp/t3-work/addendum1-self/にビルド（終了0）。ソースは測定のために閲覧・変更していない。両ROMともディスクなし、コア既定N88 V2。全18腕×独立2走で、固定planのRUN区間・限定RAM印・I/Oログを使用する。

ポート0x54〜0x5Bは [l1-ipl仕様第5a節](../spec/l1-ipl.md)でパレット出力と確認した。負数-172/-171.5と65535近傍65371も低位が同範囲になる候補であり、p=-1/65535の正常出力は安全性未確定として測らない。

stage1と復帰印の間にFOR待ちを入れ、境界フレームOUTと区間外パレットOUTを拒否する。対照2腕にパレットOUTがないことを要求する。その他のOUT/IN値・PC・生ログは成果物へ残さず、ハーネスstdout/stderrも捕捉して捨てる。I/Oイベントのportはuint8_tであり、4桁表記でも上位8bitを測れない。

合成自己検査は陽性抽出、非対象ポート値の除外、境界・区間外・未知値・取りこぼし・件数・連番、plan・反復・関門・本文キーの陰性、捕捉stdout/stderrの秘密文字列非出力、成功／失敗時の生ログ削除を検査し通過。

## 関門と照合

自作は18腕×2走、全関門・較正通過。測定TSVはtmp/t3-work/addendum1-self.tsv。現行器具で固定plan・2走・数値印・較正を再検証し、自作専用期待値との照合は18一致・0不一致。全腕で測定区間のパレットOUTは0件。正常14腕はERR0、v255-5/v256はERR5、cal-pokeは213/ERR0、cal-errorはERR13。

その後、PC88_REF_ROM_DIRを環境変数で渡して公式を測定。公式も全18腕×2走、全関門・較正通過。測定TSVはtmp/t3-work/addendum1-ref.tsv。公式TSVを固定plan・2走・論理印・較正まで再検証し、`expected`でtmp/t3-work/addendum1-official-expected.tsvを生成、`check`は公式自身18一致・0不一致。これを新設 `tests/conformance/expected_l4_out_output.tsv` にコピーした。自作との同じ照合は4一致・14不一致（正常14腕のOUT欠落）で、誤り番号・数値印の差はない。既知差として免除していない。

## 公式観測（両走一致）

以下の出力は各1回。空欄ではなく「なし」と記した腕は0回。低位ポートだけを観測し、上位8bitは全腕不明。

|腕|入力（測る文）|ERR|実効ポート（低8bit）|出力値|
|---|---|---:|---|---:|
|cal-poke|poke &he790,213|0|なし|なし|
|cal-error|error 13|13|なし|なし|
|v0|out 84,0|0|0x54|0|
|v1|out 84,1|0|0x54|1|
|v255|out 84,255|0|0x54|255|
|v1-49|out 84,1.49|0|0x54|1|
|v1-5|out 84,1.5|0|0x54|2|
|v254-5|out 84,254.5|0|0x54|255|
|v255-49|out 84,255.49|0|0x54|255|
|v255-5|out 84,255.5|5|なし|なし|
|v256|out 84,256|5|なし|なし|
|p-plus256|out 340,1|0|0x54|1|
|p-plus65280|out 65364,1|0|0x54|1|
|p-near65535|out 65371,1|0|0x5B|1|
|p-negative|out -172,1|0|0x54|1|
|p84-49|out 84.49,1|0|0x54|1|
|p84-5|out 84.5,1|0|0x55|1|
|p-negative-half|out -171.5,1|0|0x54|1|

全18腕の事前予測と一致。追加した切捨て候補254は観測されなかった。値は1.49→1、1.5→2、254.5→255、255.49→255で、最近傍整数化に整合し、正の半端は大きい側。255.5は整数化後256となる規則に整合してERR5、出力なし。255を単に上限として小数の生値を比較する規則では255.49受理を説明できない。

ポートは340/65364/-172→0x54、65371→0x5Bで、整数化後の下位8bitに整合する。84.49→0x54、84.5→0x55、-171.5→0x54で、負の半端は-172になる規則と整合する。**ただし低8bitだけを見ており、CPUの16bitポート上位・16bit化の時点は確定しない。** パレットをCPUがどう駆動したか・画面の色・音は測っていない。

## 再現コマンドと残存未測定

自作はビルド後、次の `measure` を公式より先に実行した。全腕関門通過を確認してから公式を実行した。

```sh
python3 tools/l4_out_output_measure.py measure --rom-dir "$PWD/tmp/t3-work/addendum1-self/rom" --work-dir "$PWD/tmp/t3-work/addendum1-self/runs" --out "$PWD/tmp/t3-work/addendum1-self.tsv"
PC88_REF_ROM_DIR="$PWD/private/rom" python3 tools/l4_out_output_measure.py measure --official --work-dir "$PWD/tmp/t3-work/addendum1-ref" --out "$PWD/tmp/t3-work/addendum1-ref.tsv"
python3 tools/l4_out_output_measure.py expected --measured "$PWD/tmp/t3-work/addendum1-ref.tsv" --out "$PWD/tmp/t3-work/addendum1-official-expected.tsv"
python3 tools/l4_out_output_measure.py check --measured "$PWD/tmp/t3-work/addendum1-ref.tsv" --expected "$PWD/tmp/t3-work/addendum1-official-expected.tsv"
python3 tools/l4_out_output_measure.py check --measured "$PWD/tmp/t3-work/addendum1-self.tsv" --expected "$PWD/tmp/t3-work/addendum1-official-expected.tsv"
```

最後のcheckはOUT欠落を検出して終了1が正しい。CLIの作業・期待値パスはtmp/t3-work内だけなので、コミット済み期待値を使う際も同領域へコピーする。

正常整数値0〜255の全数走査、ポートの全受理範囲・端点（p=-1/65535の正常値を含む）、さらに大きい／小さい数、負の値の小数境界、型・式評価・正常値での過多引数、他の機器ポートの副作用は未測定。CPUの上位8bitは器具の制約で不明。今回のOUTの整数化観測をINP/WAITの丸め規則へ流用しない。

## 親がコミットする単位

1. 事前登録追補: `docs/notes/l4-t3-addendum1-out-output-preregistration.md`。
2. 器具: `tools/l4_out_output_measure.py`。
3. 測定: 本結果ノート、新設の `tests/conformance/expected_l4_out_output.tsv`（関門通過した公式観測から生成）。
4. 仕様: `docs/spec/l4-program.md` 第4.23.2節・版履歴・第8節33項の参照更新。

既存 `expected_l4_portio.tsv` は変更しない。tmp/t3-work/内の自作ROM・生ログ・作業TSVはコミットしない。
