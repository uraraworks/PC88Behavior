# l4-s9n 追補2 — 誤りそのものが OUT 0x40 の bit 5 を動かすのかを分ける

状態: **測定前**（2026-10-07）。本追補は腕の追加と測定の前に固定する。追補1までの結果（887d3e7）は既に見ている。
既存の予測・腕・関門は変えない。公式ROMのバイト列・逆アセンブルは読んでいない。

## 経緯と問い

結果ノート（887d3e7）で、`beep "a"`（ERR 13）・`beep 0,1`（ERR 2）・`beep -1`・`beep 256`（ERR 5）は、誤りになるのに bit 5 の立ち上がり・立ち下がりが出た。
2つの機序が考えられ、今の腕では分けられない。
- (A) BEEP 文が引数の評価・検査より前に鳴らす（文の機序）。
- (B) 誤りの処理そのもの（メッセージの表示）がブザーを鳴らす（誤りの機序）。

## 出典と読んだ範囲

MIT公開ソース `../refs/GW-BASIC/` の `GWMAIN.ASM` 455–576（ERROR から ERRFIN まで。トラップの有無の分岐・メッセージの表示・行番号の表示）を読み、
**ブザーを鳴らす呼び出しは見つからなかった**（BEEP の呼び出しは `GWSTS.ASM` の BEEP と、画面ドライバの制御文字 `^G` の処理にあるだけ）。検索0件を不存在の根拠にしない。
したがって G_GW は「誤りは鳴らさない」。ただし N88-BASIC が GW と同じとは限らず、観測で differ になりうる。予測は書き換えない。

## 腕（直接モード、全て `s9nv 1 7` を出させる。窓は最初の本体行から）

誤りの有無と、トラップ（表示なし）と、BEEP の有無を組み合わせる。(A)なら「トラップされた `beep "a"` でも鳴る」、(B)なら「トラップされた誤りは鳴らず、表示された誤りは鳴る」。

| 腕 | 打鍵（本体） | G_GW の予測 |
|---|---|---|
| e-none-print | 直接: `print 1` | 変化なし（誤りのない対照） |
| e-direct-syntax | 直接: `print 1+` | ERR 2、変化なし |
| e-direct-undef | 直接: `goto 999` | ERR 8、変化なし |
| e-direct-div0 | 直接: `print 1/0` | ERR 11、変化なし |
| e-direct-type | 直接: `a$=1` | ERR 13、変化なし |
| e-direct-error5 | 直接: `error 5` | ERR 5、変化なし |
| e-prog-ok | 行 `10 print 1` / `run` | 変化なし（誤りのないプログラムの対照） |
| e-prog-undef | 行 `10 goto 999` / `run` | ERR 8、変化なし |
| e-prog-type | 行 `10 a$=1` / `run` | ERR 13、変化なし |
| e-trap-type | 行 `10 on error goto 30:a$=1` / `30 print 2:end` / `run` | 誤りは表示されず、変化なし |
| e-trap-error5 | 行 `10 on error goto 30:error 5` / `30 print 2:end` / `run` | 表示されず、変化なし |
| e-prog-beep | 行 `10 beep` / `run` | bit 5 の立ち上がり・立ち下がり（陽性対照） |
| e-prog-beep-str | 行 `10 beep "a"` / `run` | 予測なし（ERR 13 は表示される。鳴るかは(A)(B)で割れる） |
| e-trap-beep-str | 行 `10 on error goto 30:beep "a"` / `30 print 2:end` / `run` | 予測なし（(A)なら鳴る、(B)なら鳴らない） |
| e-trap-beep-neg | 行 `10 on error goto 30:beep -1` / `30 print 2:end` / `run` | 予測なし（同上、ERR 5 の型） |

予測あり12腕・予測なし3腕。判定の読み方（結果ノートに書く）: 表示された誤り（e-direct-*・e-prog-undef・e-prog-type）が鳴り、トラップされた誤り（e-trap-type・e-trap-error5）が鳴らなければ (B)。
表示された誤りも鳴らず、e-trap-beep-str が鳴れば (A)。両方鳴れば両方。

## 器具と再測定

`tools/l4_widthbeep_measure.py` に上の15腕を足す（採取形・ポート記録は e8886db のまま、関門は同じ）。再測定は**追補2の15腕＋対照12腕だけ**（`measure --only`）。
結果は `official_round3.tsv` に別ファイルで保存し、`official_final.tsv` は書き換えない。全体は `merge`（基に無い腕を補う）→ `rejudge` で作り直す。
対照12腕が既知値に一致しなければ再測定を採用しない。自作ROMも同じ15腕を測る。期待値 TSV は予測あり腕を足して更新する。

## 決めないこと

誤りの種類ごとの網羅（ERR 2・5・8・11・13 のみ）、BEEP の長さ、トラップ時の `resume`。
