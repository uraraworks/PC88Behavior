# l4-t1 直接モードの GO TO / GO SUB — 第2回結果

2026-10-14、記録担当。最初に CLAUDE.md 全文を読み、その規律に従った。
公式ROMのバイト列・内部資料・画面本文は読まず、記録しない。src/・tools/ は変更せず、commit はしない。
作業ファイルの参照・作成は tmp/t1-work/ に限定した。公式の再測定は行わない。

## 根拠・採用範囲

事前登録は [l4-t1-direct-goto-preregistration.md](l4-t1-direct-goto-preregistration.md)（2446278）、器具は `tools/l4_directgoto_measure.py`（912728e）。
親が実行した公式測定 `tmp/t1-work/ref.tsv` は16腕×独立2走、全腕の関門通過、measure rc=0（親の報告）。
本担当は数値TSVから expected を生成し、公式自身の check を通して採用した。
自作の対照は `tmp/t1-work/selfrun.md` と最終追加修正の `tmp/t1-work/追加修正/selfrun.tsv`（全16腕×2走、較正・関門通過）。旧試走は採用しない。

条件はコア既定 N88 V2、ディスクなし、小文字打鍵、各走 NEW、ON ERROR ハンドラ設定下の直接コマンド。
10・30行への到達をそれぞれ印10・30、RETURN後の同じ直接行の後続文を77、次の独立した直接行を88で識別する。
GO TO腕の飛び先はEND、GO SUB腕の飛び先はRETURNで終わる。誤りは公開ERR/ERLをハンドラ内で採り、RESUME 9020・ENDで抜ける。
段1=初期化、2=前印、3=測る文（飛び先・RETURNを含む）、4=同一行の後続、5=次直接行とa診断、6=完了。
画面ではなく測定用RAMの数値と書込み順を使う。各表の観測は独立2走一致値。

## 各腕の予測と観測

予測欄は事前登録の「飛び先／同一行戻り／測る文ERR」を表示する。全腕で後続ERR0・次行88を予測した。
誤りがなければ段を「なし」とし、予測は誤り発生を測る文の段3に置く。
cal-pokeは追加でcal=213、colon-spacedはa=1を予測した。弱い予測も強い予測へ書き換えない。
以下の打鍵の具体形は事前登録の腕表で固定されており、画面の転記ではない。

| 腕 | 予測：飛び先/同一行/ERR（発生時は段3） | 観測：飛び先 | 観測：同一行/次行 | 観測：最初ERR@段→最後ERR@段（回数） | 後続ERR | 予測判定 |
|---|---|---|---|---|---|---|
| `cal-poke` | なし/0/0 | なし | 0/88 | なし（0回） | 0 | 当たり |
| `cal-error` | なし/0/13 | なし | 0/88 | 13@3→13@3（1回） | 0 | 当たり |
| `goto-packed` | 30/0/0 | 30 | 0/88 | なし（0回） | 0 | 当たり |
| `goto-spaced` | 30/0/0 | 30 | 0/88 | なし（0回） | 0 | 当たり |
| `gosub-packed` | 30/77/0 | 30 | 77/88 | なし（0回） | 0 | 当たり |
| `gosub-spaced` | 30/77/0 | 30 | 77/88 | なし（0回） | 0 | 当たり |
| `goto-two-spaces` | なし/0/2 | なし | 0/88 | 2@3→2@3（1回） | 0 | 当たり |
| `goto-adjacent` | なし/0/2 | なし | 0/88 | 2@3→2@3（1回） | 0 | 当たり |
| `goto-name` | なし/0/2 | なし | 0/88 | 2@3→2@3（1回） | 0 | 当たり |
| `gosub-two-spaces` | なし/0/2 | なし | 0/88 | 2@3→2@3（1回） | 0 | 当たり |
| `colon-spaced` | 30/0/0 | 30 | 0/88 | なし（0回） | 0 | 当たり |
| `if-spaced` | 30/0/0 | 30 | 0/88 | なし（0回） | 0 | 当たり |
| `on-spaced` | 30/0/0 | 30 | 0/88 | なし（0回） | 0 | 当たり |
| `goto-missing` | なし/0/8 | なし | 0/88 | 8@3→8@3（1回） | 0 | 当たり |
| `goto-packed-missing` | なし/0/8 | なし | 0/88 | 8@3→8@3（1回） | 0 | 当たり |
| `goto-line10` | 10/0/0 | 10 | 0/88 | なし（0回） | 0 | 当たり |

事前予測は16/16腕で当たり。cal-pokeはcal=213、colon-spacedはa=1、他腕はa=0。初期化ERR・前印ERR・後続ERRは全腕0。
公式の誤りはcal-errorのERR13、境界負例4腕のERR2、存在しない行2腕のERR8で、各走1回・最初/最後とも段3。段4〜6での誤りはない。
公式で誤りの出た7腕の最初/最後ERLはすべて範囲外印255を持ち、値は**不明**。値欄0をERL=0と解釈しない。
誤りのない腕のERL欄0は未発生時の初期値であり、ERLの観測値ではない。ERLは事前予測していないため、予測一致数に入れない。

## 今回確定した規則

- 直接モードで `goto 30` と `go to 30` は30行へ飛び、ERR0。`go` と `to` の間の空白1個は受理され、空白2個の `go  to 30` は飛ばず段3でERR2。`go to30`・`go tox` も飛ばず段3でERR2。観測範囲で保存/LISTの詰め規則と整合する。
- `gosub 30` と `go sub 30` は30行を実行し、RETURN後に**呼び出した同じ直接行のコロン後の文**へ戻る（returned=77、段4通過）。次の独立した直接行も実行される（88）。`go  sub 30` は飛ばず段3でERR2、returned=0。
- `a=1:go to 30`・`if 1 then go to 30`・`on 1 go to 30` はいずれも30行へ飛び、誤りなし。文頭だけでなくこの3文脈で受理される。先行代入a=1は飛び先END後にも残る。
- 存在しない99行への `go to 99`・`goto 99` は到達印なし、段3でERR8が1回、後続ERR0。ハンドラのRESUME先ENDの後、次の独立した直接行へ進む。
- 直接GO TOで到達した10/30行のEND後、次の独立した直接行を受け付け、印88・完了段6に達する（goto-packed/spaced/line10、colon/if/on）。END後の段5〜6にERR2は出ない。

詰めという記述は観測された入力受理の規則を指し、内部のトークン・バイト列・処理位置は規定しない。
未確定: `go sub10`等の直後1文字消費が直接モードの飛び先に及ぼす効果、`go to.5`等の追加境界、大文字混在、RUN時の詰め、RETURNのない/多重GO SUB、スタック限界。
GO TO腕には元の直接行の分岐後の印を置いていないため、**END後に元の直接行の同一行後続を再開するかは未確定**。
ENDによるスタック・CONT状態の扱い、ハンドラなしの誤り後の応答、正確なERL値・画面文言も未確定。

## 期待値生成・照合

```sh
python3 tools/l4_directgoto_measure.py expected --out tests/conformance/expected_l4_directgoto.tsv tmp/t1-work/ref.tsv
python3 tools/l4_directgoto_measure.py check --expected tests/conformance/expected_l4_directgoto.tsv --measured tmp/t1-work/ref.tsv
python3 tools/l4_directgoto_measure.py check --expected tests/conformance/expected_l4_directgoto.tsv --measured tmp/t1-work/追加修正/selfrun.tsv
```

expectedはrc=0、公式由来16腕の全22値を生成。公式自身のcheckは**一致16腕・不一致0腕、rc=0**。
自作のcheckは**一致1腕・不一致15腕、rc=1**。一致はcal-pokeだけ。照合単位は腕で、各2走の関門・計画・較正・一致を検査してから全22値を比較する。
ERLの範囲外印も照合対象であり、予測なし・値不明を照合除外へ変更していない。フレーム・PC・書込み順をROM間の期待値にはしない。

## 自作試走との違い

自作のERR2は13腕×2走=26件、すべて段3。公式のERR2は境界負例4腕×2走=8件に限られる。
自作のgoto-packed/gosub-packedは30行へ、goto-line10は10行へ到達してから段3でERR2となる。
段3は飛び先とRETURNを含むため、この値だけで原因文やEND/RETURN内部の不具合位置は確定しない。
空白1個のGO TO/GO SUB、colon/if/on、go to 99の6腕は自作では到達印なし・ERR2（colonのa=1は残る）。公式では前5腕が30行へ到達してERR0、go to 99はERR8。
自作のGO SUBはreturned=0、公式のpacked/spacedは77。両ROMとも全腕で次行88・後続ERR0。

全22値の相違内訳は次のとおり。これは主たるcheckの一致数を変更するものではない。

| 相違の種類 | 腕 | 数 |
|---|---|---|
| ERL欄だけ相違（公式は範囲外、値不明；自作は0取得） | `cal-error`, `goto-two-spaces`, `goto-adjacent`, `goto-name`, `gosub-two-spaces`, `goto-packed-missing` | 6 |
| 到達・戻り・ERR等にも相違 | `goto-packed`, `goto-spaced`, `gosub-packed`, `gosub-spaced`, `colon-spaced`, `if-spaced`, `on-spaced`, `goto-missing`, `goto-line10` | 9 |

較正cal-errorは両ROMともERR13@段3が1回で関門を通るが、ERLの取得状態が違うため公式期待値とのcheckでは不一致。
境界負例4腕とgoto-packed-missingも、飛び先・戻り・ERR・段・次行は同じだがERLの取得状態が違う。
本担当は実装修正を行わず、この差を数値観測として残す。
