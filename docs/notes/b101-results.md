# B101 結果：INKEY$ が返す特殊キーの文字コード

実施: 2026-11-17、クラウド（公式 ROM の BASIC、76キー）。[事前登録](b101_preregistration.md) のとおり、自作プログラムが POKE した RAM から読み、画面は読んでいない。値は BASIC の振る舞いの測定値。全キーの表はクラウドの集計（summary.json）にある。

| キー | INKEY$ |
|---|---|
| ESC | 1B |
| ↑ ↓ ← → | 1E 1F 1D 1C |
| HOME/CLR | 0C |
| SHIFT+HOME/CLR | 0B |
| INS/DEL | 7F |
| SHIFT+INS/DEL | 12 |
| TAB | 09 |
| ROLL UP / ROLL DOWN | F8 / F9 |
| HELP | 01 |
| CTRL+英字 | 01〜1A（英字の順。CTRL+C・CTRL+O・CTRL+S は値が出ない） |
| COPY・STOP | 値が出ない |
| f1〜f5・SHIFT+f1〜f5 | 既定のファンクションキー定義の文字列（4〜7文字）。自作の KEY 既定値とは一致しない |

自作表と一致したのは、テンキー全部・GRPH+A〜D・カナ+SHIFT+A〜D の25キー。残り51キーは自作表の値が0（CTRL 表も英字の位置が0）だった。

## 判定

- ESC・カーソル・HOME/CLR・INS/DEL・TAB・ROLL・HELP・CTRL+英字（C・O・S を除く）の値を自作の INKEY$ 表に入れる（[l3-main](../spec/l3-main.md) 第4.5版）。
- CTRL+C・CTRL+O・CTRL+S・COPY・STOP は INKEY$ に値を出さない（中断・一時停止など別の働きを持つとみられる。既存の自作の STOP/CTRL+C の扱いは変えない）。
- ファンクションキーは INKEY$ では KEY 定義の文字列を返す。自作の KEY 既定値は自作の文字列であり、公式の既定値を写すことはしない（禁止事項6に準じ、公式の文言は持ち込まない）。したがって f1〜f5 の INKEY$ が公式と同じ文字列になることは求めない。3080 がファンクションキーで何を積むかは未確定のまま。
