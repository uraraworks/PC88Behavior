# PC88Behavior

PC-8801 の ROM を、公式 ROM のコードを**一切読まずに**、外部から観測した振る舞いだけを
根拠に書き起こすプロジェクト。名前の "Behavior" はその手法そのものを指す。

PC-88 は ROM が機械の本体で、抜くとディスクを読むコードすら無くなる。
だから ROM 無しでこの機械を動かすには、ROM を作るしかない。

## このリポジトリに入っていないもの

- 公式 ROM のバイナリ、およびその一部バイト列
- 公式 ROM の逆アセンブル結果
- 吸い出したディスクイメージ、市販ソフト

これらは `private/`（git 管理外）に隔離されており、コミット履歴に一度も現れない。
公開しているのは**文書・ソース・ビルドスクリプト・適合性テスト**だけで、
すべて第三者が独立に再導出できるものに限っている。

## 手法

逆アセンブルを読む代わりに、エミュレータに計測フックを入れ、ROM の入口に入力を振って
出力を採取する。採れるのは「こう与えたらこう返る」という**事実**であり、表現ではない。

副次的に、手元に原典コードが存在しない状態になる。写経しようにも写経元が無い。
規律を守るのではなく、破れない構造にしてある。

## 状態

M1 完了（計測ハーネス）、M3 着手（需要プロファイル）。

公式 ROM を測ったところ、メイン ROM 32KB のうち実行されるのは現時点で 22.2%、
サブ ROM (DISK.ROM) 2KB のうち 533 バイト。まだ飽和していない＝測り足りない。

- 設計と進め方: [docs/PLAN.md](docs/PLAN.md)
- 土台にした QUASI88-libretro の調査: [docs/notes/m1-quasi88-survey.md](docs/notes/m1-quasi88-survey.md)
- 需要プロファイル: [docs/notes/m3-demand-profile.md](docs/notes/m3-demand-profile.md)

### 手元で再現する

公式 ROM は各自で用意すること（`private/rom/` に置く。このリポジトリには含まない）。

```
tools/setup_harness.sh    # 上流をピン留めコミットで取得・改変・ビルド・疎通試験
tools/check_cleanroom.sh  # 防御が効いているかの検査
tools/measure.sh <名前> --frames 600
tools/profile.py --growth measurements/*.txt
```

## ライセンス

MIT License（[LICENSE](LICENSE)）。文書・測定結果・ツールを含め全体に適用する。

土台に使っている QUASI88 / QUASI88-libretro は BSD 3-Clause で、
本リポジトリには第三者のコードを含まない（ピン留めコミットへのパッチのみ）。
詳細は [docs/notes/m1-quasi88-survey.md](docs/notes/m1-quasi88-survey.md)。

## 測定結果について

`measurements/` に入っているのは、公式 ROM を動かしたときに
**どの番地にどの種類のアクセスがあったか**の記録である。
ROM の内容（バイト列）は含まない。

条件が意図どおりだったかを結果自身で検証できるよう、終了時のテキスト画面も
残している。ただしディスクのファイル一覧だけは私物の内容なので伏せている
（`tools/redact.py`）。
