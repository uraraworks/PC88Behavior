# l4-c7 — 整数オペランドのみの四則演算丸め、適合場面固定・結果

実施日: 2026-09-20
事前登録: [l4-c7-integer-arithmetic-rounding-conformance-
preregistration.md](l4-c7-integer-arithmetic-rounding-conformance-preregistration.md)
（本ノートと同じコミットに器具（`tools/conform_l4.sh`のARITH場面追加）
とともに収録）。

## 実施内容

事前登録どおり、公式ROM（`PC88_REF_ROM_DIR`、コマンドごとに環境変数で
付与、`private/rom`）で40腕（K1〜K8・L1〜L8・M1〜M16・N1〜N8）を各2走
（計80走）実施した。写し(前)は全腕690固定、写し(後)・走行フレームは
`docs/notes/l4-s7b-integer-only-rounding-preregistration.md`の表の値を
そのまま使用（打鍵文字列は変更していない）。

## 関門

- G1（器具の自己検査）: `tools/conform_l4.sh`のARITH場面用検出力自己
  検査（a〜d・群の印切り替えe）が全てOK
- G2（取りこぼし0・打てない文字の警告0）: 40腕×2走=80走全てで打てない
  文字の警告0件
- G3（決定論性）: 40腕全てでrun1/run2の記録（cell_count/
  ok_relative_row/sha256）が完全一致
- G4（陰性対照）: 既存の陰性対照（何も打たない走）を流用、変化0件
- G8（出力完了の確認）: 40腕全てで`ok_relative_row`=2（`Ok`行が出力の
  2行後に現れた）を確認

G1〜G4・G8すべて真。gate_failed腕は無し。

## 期待値の採用

40腕全てでG3（2走一致）を満たし、その記録を`tests/conformance/
expected_l4_arith.tsv`に採用した（値は含めずcell_count/
ok_relative_row/sha256のみ、CLAUDE.md禁止事項4・禁止事項7を遵守。
本ノートの数値はいずれも自分で打った式(`print cdbl(...)`の引数)の
直接の結果であり、画面本文・エラー表示は含めていない）。見出し
コメントは`# group arith selfmade=not_implemented_yet`（自作main ROM
側の実装（`src/l4_basic/mbf_single.asm`のawayタイブレークへの変更）
はこのあとの別コミットで行う）。

興味深い性質として、加算腕(K1〜K8)と対応する減算腕(L1〜L8、`A!-
(-B!)`の形で数学的にはK群と同じ`A+B`を計算する)は、cell_count・
sha256とも完全に一致した（K1==L1、K2==L2、…、K8==L8）。これは公式
ROMが両方の式で同じ数値結果を出したことの直接の証拠であり、l4-s7bの
away丸め結論（K/L群はいずれもtie_disc/tie_ctrl/controlで同じ規則が
働く）と整合する。

## 判定後の行き先

`src/l4_basic/mbf_single.asm`のMBF_ADD/MBF_SUB/MBF_MUL/MBF_DIVを
`docs/spec/l4-basic.md`5.3a節に合わせて直したあと、群の印を
`implemented`へ切り替えて自作側の照合を行う（後続コミット）。

## 生データの扱い

写し(vram.bin)・分類結果・stdout/stderrはリポジトリ外の作業ディレク
トリ(scratchpad配下)に置き、本ノートを書いたあと削除する。コミット
するのは本ノートと`tests/conformance/expected_l4_arith.tsv`のみ。
