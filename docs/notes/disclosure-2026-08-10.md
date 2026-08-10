# 開示記録 2026-08-10

`CLAUDE.md`「汚染したとき」の書き方（[contamination-2026-08-07.md](contamination-2026-08-07.md)）
を踏襲する。隠さない。

## 何を公開状態に置いたか

`measurements/*.iolog.txt`（追跡39件・合計約459MB、非圧縮）に、
**main/sub 双方の CPU が `$FB`/`$FC`/`$FD`（データポート）に対して
発行した IN/OUT の value 列**がそのまま記録されていた。

- `$FC`/`$FD`: main⇔sub 間の PIO データ経路（`docs/spec/l3-subrom.md` 1.2節・1.6節）
- `$FB`: sub が自分の FDC（実ディスク）を叩くデータポート（同ノート1.9節）

これらのポートを通じて記録された値は、**公式ディスク（diskA・diskB。
`private/` 配下の私物）から実際に読み出されたデータそのもの**である。
順序（seq/clock）・PC・frame も付随して記録されているため、
形式が違うだけの複製に等しい（バイト列を並べ替えたコピーではなく、
発生順まで込みで持っている）。

対象ポートの件数（ファイル別。`tools/hash_io_stream.py` で件数のみ抽出。
**値そのものはここにも書かない**）:

```
l1-boot-io-disk.iolog.txt        34617
l1-boot-io.iolog.txt                  0
m6-sub-d0-boot.iolog.txt          38583
m6-sub-d1-files.iolog.txt         43243
m6-sub-d2-save.iolog.txt          47912
m6-sub-d5-seqfile.iolog.txt       56107
m6-sub-nodisk.iolog.txt               0
m6c-sub-d0-boot.iolog.txt         38583
m6c-sub-d1-files.iolog.txt        43243
m6c-sub-d2-save.iolog.txt         47912
m6c-sub-d5-seqfile.iolog.txt      56107
m6c-sub-nodisk.iolog.txt              0
m6d-inv-blankdisk.iolog.txt           0
m6d-inv-frames-100.iolog.txt      38583
m6d-inv-frames-1200.iolog.txt     38583
m6d-inv-frames-150.iolog.txt      38583
m6d-inv-frames-180.iolog.txt      38583
m6d-inv-frames-1800.iolog.txt     38583
m6d-inv-frames-200.iolog.txt      38583
m6d-inv-frames-220.iolog.txt      38583
m6d-inv-frames-250.iolog.txt      38583
m6d-inv-frames-280.iolog.txt      38583
m6d-inv-frames-300.iolog.txt      38583
m6d-inv-frames-3600.iolog.txt     38583
m6d-inv-frames-60.iolog.txt       34617
m6d-inv-frames-600.iolog.txt      38583
m6d-inv-frames-65.iolog.txt       37769
m6d-inv-frames-70.iolog.txt       37769
m6d-inv-frames-75.iolog.txt       37769
m6d-inv-frames-80.iolog.txt       38583
m6d-inv-frames-85.iolog.txt       38583
m6d-inv-frames-90.iolog.txt       38583
m6d-inv-frames-900.iolog.txt      38583
m6d-inv-frames-95.iolog.txt       38583
m6e-diskB-boot.iolog.txt         177280
m6e-diskB-boot3600.iolog.txt     177280
m6e-diskB-boot600.iolog.txt      117611
m6g-d0-boot-run1.iolog.txt        38583
m6g-d0-boot-run2.iolog.txt        38583
----------------------------------------
合計                            1,759,479 件
```

（`main`/`sub`×`$FB`/`$FC`/`$FD`×`IN`/`OUT` の全12組を各ファイルで合算した数。
0件のファイルはブート初期化のみでデータポートに触れていない測定）。

このうち diskA 起動時の main/`$FD`/IN 列（`tests/conformance/expected.tsv`
の `m6g-d0-boot` 行、`docs/spec/l3-subrom.md` 5.2節条件1）だけでも 5635件
（末尾73件は0x00パディング、実質5562件）——これは N88-BASIC 起動シーケンスの
一部を、順序込みでそのまま複製したものに等しい。

制御ポート（`$FA`/`$FE`/`$FF`/`IN 40`/CRTC等）・pc・frame・clock は
ハードウェアの事実または自分の測定であり、`tools/cmp_io.py` の分岐点検出に
必要なので**残した**（`tools/redact_iolog.py` 冒頭コメント参照）。

## いつからいつまで

最初にデータポートを含む iolog をコミットしたのは
**2026-08-07、コミット `623e1cf`**（M4: 公式ROMの起動I/O列を測定
(l1-boot-io / l1-boot-io-disk)）。以降 M6/M6c/M6d/M6e/M6g の各測定で
2026-08-08 にかけて追加され、最終的に39ファイルになった。

このリポジトリは GitHub の public リポジトリ（`uraraworks/PC88Behavior`）に
push されており、`origin/main` は本記録作成時点で `71a57d6`
（2026-08-10、これらのiologを全て含む）を指している。つまり
**2026-08-07 から本記録作成（2026-08-10）まで、少なくとも3日間、
未加工のデータポート値列が public に push された状態だった。**

本セッションでの伏せ字・gzip化・tree からの除去は、方針として
**push しない**（下記「なぜ履歴を書き換えないか」）。したがって
**この記録を書いている時点でも、`origin/main` には未加工の値列を含む
iolog がそのまま残っている。** ローカルでの手当てはコミットに残るが、
公開側への反映（push）は、この記録と手当ての妥当性を後で確認できる状態に
してから、別途行う。

## なぜ問題か

`CLAUDE.md` 禁止事項4は文言上「ROM 由来のバイト列」を対象にしており、
今回のデータは ROM ではなく**ディスク**（diskA/diskB）から読み出された
実データなので、字義通りには当たらない。

しかし置かない理由は同じである。禁止事項4の趣旨は「独立実装の主張が、
公式の中身をそのまま含むリポジトリでは成り立たない」ことにある。
ROM かディスクかは出所の違いであって、**「公式媒体から読み出した実データを
順序込みでそのまま複製したものを置かない」という趣旨には等しく反する。**

このプロジェクトの主張の核は、`docs/PLAN.md` 第3節が述べる
**手続きの構造的な潔白さ**（自分で測った・自分で書いた・第三者が再現できる）
であって、個々のバイトの合法性の立証ではない。**製品のバイト列が生で
リポジトリに載っていると、その主張自体が弱くなる。** 「読んでいない」
という手続きの主張と、「公式の実データをそのまま配布している」という
事実は、同じリポジトリの中で両立しない。

## どう対処したか

1. **データポートの value 列のみ伏せ字。** `tools/redact_iolog.py`
   （直前のコミット `6902e95` で追加済み）で `$FB`/`$FC`/`$FD` の
   IN/OUT value を固定文字列 `--` に置換した。
2. **制御ポート・pc・frame・clock は残した。** ハードウェアの事実・
   自分の測定であり、`cmp_io.py` の分岐点検出（適合条件の判定）に必要で、
   消すと解析能力が落ちるため。
3. **伏せる前の値列のハッシュを各ファイル末尾に記録した。** 伏せる
   (cpu, port, kind) の組ごとに件数と SHA-256 を追記した（`tools/
   hash_io_stream.py` の `hash_values()` と同一計算）。**値そのものは
   一切書いていない。** これにより、伏せ字後も
   `tests/conformance/expected.tsv` のような適合判定は継続可能
   （件数+ハッシュの一致で判定できる）。
4. **gzip した。** 伏せ字後、全39件を `.gz` にした。`tools/cmp_io.py`・
   `tools/hash_io_stream.py`・`tools/redact_iolog.py` は `6902e95` で
   すでに `.gz` を透過的に読める。追加で `tools/analyze_main_to_sub.py`・
   `tools/analyze_fdc_ports.py`・`tools/analyze_sub_proto.py`・
   `tools/verify_analyzer_corruption.py` も同じ gz 透過オープンを
   共有するよう直した（別実装しない）。`*.intlog.txt`（16件・22MB）も
   同様に gzip した（伏せ字は不要。割り込みモード・レベル・PC のみで
   値の列を持たないため）。
5. **非圧縮の `.iolog.txt`/`.intlog.txt` は tree から `git rm` した。**
   履歴には残る（下記）。
6. **`tools/conform_l3.sh` の検出力の自己検査の入力を、実測ログから
   合成フィクスチャ（`tests/fixtures/conform_l3_selftest.iolog.txt` +
   `.expected.tsv`、公式データ不使用）に切り替えた。** 伏せ字後の
   `measurements/m6g-d0-boot-run1.iolog.txt` を自己検査の入力に使うと、
   マスクされた `--` が抽出されて `tests/conformance/expected.tsv` の
   本番用ハッシュと一致しなくなる（マスク後の値が元と一致しないのは
   伏せ字の目的そのものなので、これは正しい動作。ただし自己検査が
   誤って「不一致」になってしまうのは本末転倒）。自己検査に要るのは
   「比較ロジックが機能しているか」だけなので、公式データ不要な
   合成フィクスチャに切り替えた（`tools/redact_iolog_selftest.sh` の
   作り方を流用）。
7. `docs/` 内で `.iolog.txt` を個別に名指ししているノート（12件）は、
   当時の記述を書き換えず、末尾に本記録への追記リンクを1行足した。

## なぜ履歴を書き換えないか

`CLAUDE.md` コミット規律「行き止まりを `git reset` で消さない。失敗した
試行を残す」に従う。理由は3つ:

1. **contemporaneous な証拠としての価値。** いつ・どういう経緯で
   データポートを含む形式を選び、いつ気づいて直したかという時系列
   そのものが、プロセスの証拠になる。履歴を書き換えると、この記録が
   後から作れてしまい、証拠として無意味になる。
2. **`docs/notes/m6e-diskB-boot*` の72MB超問題（`docs/PLAN.md`「運用上の
   課題」）で既に一度、同じ理由で履歴書き換えをしない判断をしている。**
   一貫性を保つ。
3. **隠すと「汚染したとき」の規律に反する。** この規律は「隠さない」を
   一番手に置いている。履歴からデータを消す（force-push で書き換える）
   ことは、事実上「見えなくする」であり、規律の精神と矛盾する。

**明記する: 上記の対処後も、`git log` の過去のコミット（`623e1cf` 以降）
には、伏せ字前の未加工のデータポート値列がそのまま残り続ける。**
tree（現在のファイル一覧）からは消えるが、履歴からは消えない。
これは意図した結果であり、見落としではない。

## 見落としていた理由

`measurements/*.iolog.txt` のヘッダには最初から
「ROM の内容は含まない」と書かれていた（各ファイル冒頭）。これは
**正しい**——記録しているのは OUT/IN の発生順・ポート・値・PC・
フレーム番号であって、ROM のコード自体を書き出したものではない。

しかし、そのヘッダの文言は**ROM についてしか主張していなかった**。
`$FB`/`$FC`/`$FD` の value 列が公式ディスクの実データそのものである
ことについては、当時何も検討していなかった。「ROM を読んでいない」
ことに意識が向き、「ディスクから読み出した内容を記録している」ことに
気づくまで時間がかかった（`6902e95` で `redact_iolog.py` を作った
セッションで初めて明確に意識した）。

## ルール化

- `CLAUDE.md` 禁止事項4に、公式ディスク由来のバイト列も対象にする旨を
  追記した。
- `tools/check_cleanroom.sh` に、伏せ字されていない `.iolog.txt`
  （非 `.gz`、または `.gz` でもデータポートの値が残っているもの）と
  50MB超のファイルを検出する項目を追加した。わざと壊して検出力を
  確認済み（下記「回帰確認」）。
- `docs/PLAN.md`「運用上の課題」に対処済みとして追記した。
- `CONTRIBUTING.md` に、測定ログを送る際の注意を追記した。
