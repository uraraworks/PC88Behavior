# M6s — TC(`$F8`)位置の訂正: batch2ではなくbatch4だった

測定日: 2026-08-12
対象: 混成ROM実走診断（19:11版）が示した反証。sub側の構造的一致
プレフィックスがm6q・1.22節（第16〜18版）の実装後、35件→40件に前進した
上で分岐点41に止まった。中身:

```
基準[40] IN  $FB (seq49)   ← SENSE INT の結果2バイト目
基準[41] IN  $FA (seq50)   ← そのまま次のコマンドへ進む(TC無し)
混成[40] IN  $FB (seq49)
混成[41] OUT $F8 (seq50)   ← 自作subがTCを出している(m6q準拠の実装)
```

混成[42]以降は基準[41]以降と同じ構造をなぞっており、TC 1個ぶんずれて
いるだけ。つまり**基準ログのbatch2の結果フェーズ直後にはTCが無い**。
m6qの「TCはbatch1・batch2の直後にのみ現れる」（1.22節第16版、確定
セクション5）は誤りだった。

**追加測定は行っていない。** `docs/notes/m6q-boot-fdc-sequence.md`が
使ったのと同じ既存4条件ログ（`measurements/m6c-sub-{d0-boot,d1-files,
d2-save,d5-seqfile}.iolog.txt.gz`）を、seq番号を明示的に出力する新しい
解析器で再解析しただけ。値は一切見ていない（件数・kind・pc・seqのみ）。

新規解析器: `tools/analyze_tc_position_by_seq.py`。`tools/
analyze_boot_fdc_sequence.py`の`find_boot_init_window`/`segment_runs`を
importして再利用（二重実装しない）。m6qの`analyze_boot_fdc_sequence.py`
がTC検出に使っていた`find_tc_triads`は**三つ組み（`OUT $F8`→`OUT $F7`
→`IN $F8`）が揃わないと1件も検出しない**関数であり、1.22節・m6q5節が
自ら書いているとおり起動区間のTCは単発（三つ組みの残り2ステップを
伴わない）なので、`analyze_boot_fdc_sequence.py`をそのまま再実行すると
「区間内TC三つ組み検出数: 0」となり**TCの位置を1件も報告しない**
（実際に`measurements/m6q-boot-fdc-sequence-cross.txt`を再実行して確認
した。この保存済み出力ファイル自体に、run列とは別に「[i] 直後にTC
三つ組み」の注記が1つも無いことも確認した）。

再実行方法:

```
python3 tools/analyze_tc_position_by_seq.py cross \
    --iolog d0-boot   measurements/m6c-sub-d0-boot.iolog.txt.gz \
    --iolog d1-files  measurements/m6c-sub-d1-files.iolog.txt.gz \
    --iolog d2-save   measurements/m6c-sub-d2-save.iolog.txt.gz \
    --iolog d5-seqfile measurements/m6c-sub-d5-seqfile.iolog.txt.gz \
    --out measurements/m6t-tc-position-by-seq-cross.txt
```

（出力ファイル名は先に採番した`m6t`のまま残す。ノート番号を`m6s`に
した後で気づいたための不一致であり、実害が無いため付け替えない。）

---

## 1. m6qが何をどう誤ったか

`tools/analyze_boot_fdc_sequence.py`の保存済み出力
（`measurements/m6q-boot-fdc-sequence-cross.txt`）は、run列(0-13)を
機械的に列挙しているだけで、TCの位置（どのrunの直後か）は一切
記録していない（三つ組み検出が0件だったため）。したがって1.22節・
m6q5節の「TCはbatch1・batch2の直後にのみ現れる」という記述は、
**この解析器の出力からは導出できない**。実際にどう導出したかの
再実行可能な手順は残っていない（追加のアドホックな確認作業を
経由したと考えられるが、そのスクリプトはコミットされていない）。

recovered した具体的な誤りは次のとおりと推定できる: 起動区間内で
単発`OUT $F8@06D5`が2回現れること自体は正しく見つけていたが
（本稿の解析でも同じ2回、seq35とseq74で確認——3節）、その**2回目を
「2番目に位置するTC」という順序でしか数えず、「2番目のIN run(batch2)
の直後」と取り違えた**。実際には1回目のTC（seq35）はbatch1（IN run
[32,34]）の直後で正しいが、2回目のTC（seq74）はbatch2ではなく
**batch4（IN run [71,73]）の直後**であり、間にTCを伴わないbatch2
（IN run [47,49]）・batch3（IN run [59,61]）が挟まっている。

## 2. 正しい位置

`tools/analyze_tc_position_by_seq.py`の出力（d0-boot、4条件で完全
一致・3節）:

```
batch1: OUT run seq=[17,29] -> IN run seq=[32,34]
    直後: OUT $F8 seq=35 pc=06D5   ← TCあり
batch2: OUT run seq=[37,44] -> IN run seq=[47,49]
    直後: (F7/F8イベント無し)       ← TCなし
batch3: OUT run seq=[51,56] -> IN run seq=[59,61]
    直後: (F7/F8イベント無し)       ← TCなし
batch4: OUT run seq=[63,68] -> IN run seq=[71,73]
    直後: OUT $F8 seq=74 pc=06D5   ← TCあり
batch5: OUT run seq=[76,83] -> IN run seq=[86,88]
    直後: (F7/F8イベント無し)       ← TCなし
batch6: OUT run seq=[90,95] -> IN run seq=[98,100]
    直後: (F7/F8イベント無し)       ← TCなし
batch7: OUT run seq=[102,107] -> IN run seq=[110,112]
    直後: (F7/F8イベント無し)       ← TCなし
```

**正: TCはbatch1・batch4の直後にのみ現れる。batch2・3・5・6・7の
直後には現れない。**

## 3. 実走観測との検算

課題として与えられた実走診断の観測は「基準側 seq40=IN $FB(seq49)、
seq41=IN $FA(seq50)」。本解析のd0-bootログでも、seq49はbatch2の
IN run終端（IN $FB, pc=02A1）、seq50はその直後のIN $FA（pc=02A8。
次コマンドの`$FA`ポーリング）であり、`OUT $F8`は現れない
（参照: 生イベント列 seq45-60抜粋、上記出力ファイル参照）。**実走観測
と本解析は完全に一致した。** 混成側が分岐点41で`OUT $F8`を出して
いたのは、1.22節第16〜18版の実装がm6qの誤った記述（batch2の直後に
TCを出す）どおりに作られていたためである。

## 4. 4条件での一致

d0-boot/d1-files/d2-save/d5-seqfileの4条件すべてで、区間境界
（index[15,112)、seq[16,112]）・batch境界のseq・TCの位置（batch1の
直後=seq35、batch4の直後=seq74、他は無し）が1バイトも違わず完全一致
した。

## まとめ

- m6q・1.22節（第16〜18版）の「TCはbatch1・batch2の直後」は誤り。
- 正しくは「TCはbatch1・batch4の直後」。
- 誤りの原因は、TC出現の順序（1番目・2番目）とbatch番号（1番目の
  batch・2番目の batch）を混同したこと（2回目のTCの直前に、TCを
  伴わないbatch2・batch3が挟まっていたのを見落とした）。
- m6q・m6p のノート自体は書き換えない（履歴を残す。CLAUDE.md
  「汚染したとき」と同じ精神で、誤りを消さずここに記録する）。
