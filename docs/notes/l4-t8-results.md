# l4-t8 ファンクションキーの展開・ON KEY — 公式測定の結果

2026-11-07。事前登録 `l4-t8-fkey-onkey-preregistration.md` の器具を、クラウドの測定環境で公式ROMに対して
走らせた。19腕すべて独立2走一致・関門通過。記録は `measurements/l4-t8/official.json`。

## 展開

| 腕 | 設定と操作 | 結果 |
|---|---|---|
| input | `key 1,"q7z"`、`input a$` 中に F1 → RETURN | a$ = "q7z"（LEN 3） |
| return | `key 1,"q7"+chr$(13)`、F1 だけ | 入力が終わり a$ = "q7"（LEN 2） |
| length15 | 15文字を設定 → F1 | 15文字すべて入る |
| length16 | 16文字を設定 → F1 | 先頭15文字だけ入る（KEY の保存長は15） |
| default | 起動時の既定のまま F1 | LEN 6（値は署名だけ記録。自作は同じ値を写さない） |
| shift | `key 6,"q7z"`、Shift+F1 | a$ = "q7z"（Shift+F1 は F6） |
| inkey | `key 1,"q7z"`、INKEY$ をループで読み F1 | "q"・"7"・"z" の順に1文字ずつ来る |

## ON KEY

| 腕 | 設定 | 結果 |
|---|---|---|
| on | `on key gosub 100,200`、`key(1) on`、ループ中に F1 | 行100へ飛び、RETURN で戻ってループの続きから終わりまで実行 |
| omitted | `on key gosub ,200`、`key(2) on`、F2 | 行200へ飛び、戻る |
| off | `key(1) off` で F1 | 飛ばない |
| stop | `key(1) stop` で F1、その後 `key(1) on` | 飛ばない（ON にした後も飛ばなかった） |
| undefined | `on key gosub 999,200` | その文で 8（ERL 20） |
| invalid0 / invalid11 | 直接 `key(0) on` / `key(11) on` | 5 |
| unset | ON KEY GOSUB の無いまま直接 `key(1) on` | 誤りなし |

- off・stop の腕では、ON KEY で捕まえなかった F1 の文字列がキー入力の待ち行列に残り、プログラム終了後の直接モードの行に入ったと見られる（その後の直接文の ERR が 56 になった）。仕様には「捕まえないときは通常のキーとして展開される」とだけ書く。
- stop で記憶した押下が ON で飛ぶかは、押下と `key(1) on` の時刻の前後を器具が記録しており、押下は ON より前だった。それでも飛ばなかった。マニュアルの記述と食い違うので、時刻を変えた追加測定の候補とする。
