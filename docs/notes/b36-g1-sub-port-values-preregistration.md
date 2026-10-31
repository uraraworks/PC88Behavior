# B36: スペース後の G1 で、サブの入力の値が最初に違う所を、値を出さずに探す — 事前登録

記録日: 2026-11-01
位置づけ: [B35](b35-sub-entry-registers-results.md) を反映しても、スペース後の分かれ目は変わらなかった。[B34](b34-g1-sub-reads-results.md) より RAM の初期内容でもない。残る入力はポートである。**このノートは測定より先にコミットする。**

腕 F の 4800 フレームの `--io-log`。SS はブランチの先頭のビルド。クラウドの実行環境で行う。実装は `tools/b36_sub_port_values.py`。

sub 節の発行元 `hi` の行について、`IN` のポートごとに値の並びを比べる。`IN $FE`・`IN $FA` は畳んで比べる（待ちの回数は比べない）。**値は出さない。** 件数と番号だけを出す。あわせて、最初に違う `IN` の行が、何番目の FDC コマンドの後かを B13 の番号で出す。

白リスト: `# 識別子: G1`、`port IN <4桁16進> <raw|collapsed> compared=<N> differ=<N> first=<N|none> left=<N> right=<N>`、`first-difference: none|IN <4桁16進> <N> fdc=<N>`。

判定: どのポートの何番目かをそのまま書く。`IN $FB` が最初なら FDC の結果かデータが違う。原因は書かない。

結果は `measurements/b36-g1-sub-port-values.txt`、`docs/notes/b36-g1-sub-port-values-results.md`。
