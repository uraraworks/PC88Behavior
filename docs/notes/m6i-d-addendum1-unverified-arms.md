# m6i-d 追補1 — ゲートへ到達しない腕も「未検証」に数える（測定前）

記録日: 2026-09-23  
状態: 測定前。**腕は1走も回していない。**

## 1. 何が抜けていたか

[事前登録](m6i-d-gate-release-audit-preregistration.md) §4 は、腕ごとの判定を
3種（`arm_gate_released` / `arm_gate_never_released` / `arm_gate_not_entered`）
置きながら、**総合判定を `arm_gate_never_released` の件数だけで定義していた。**
`arm_gate_not_entered` が出た腕がどこに数えられるかが書かれていない。

このままだと、たとえば D-B1 が `arm_gate_not_entered` で D-B5 が
`arm_gate_never_released` だった場合に `m6i_d_only_b5_never_released`
（＝汚染は B5 に限られる）が成立してしまう。**B1 が検証されていないのに
「B5 だけ」と読める。**

## 2. `arm_gate_not_entered` は取り違えとは限らない

事前登録 §4 は `arm_gate_not_entered` について

> ゲートを持つはずの腕でこれが出たら、観測かROMの取り違えを疑う。

と書いた。**これは一面的である。** sub がゲートの手前で止まっている場合にも
同じ観測になる。m6i-b の B1 は「sub をリセット直後の入口で停止する」腕であり、
停止がゲートのスピンではなく別の機構（例えば sub CPU がリセット保持されている）
で起きていれば、**ゲートは1度も実行されない。**

そして重要なのは、**そのときも B1 の timeout は状態についての結果ではない**
ことである。sub が動いていないのだから、「60フレーム待っただけでは状態が
足りない」ではなく「sub がそもそも走っていない」になる。
**ゲートが解除されなかった場合と、区別する実益が無い。** どちらも
「その腕の m6i-b の結果を状態の結果として読めない」という同じ帰結になる。

なお m6i-b 結果は B1 について「停止中（frame 0〜59）の sub の CPU 進行…は
0件」と記録している。ただしこの `exec` はハーネスのトレース範囲内の実行回数
であり、**sub が1命令も動いていないことを意味するとは限らない。**
本追補はこの値を根拠にしておらず、**どちらの場合でも結論が変わらない形に
判定を直す**ことだけを行う。

## 3. 直し方

### 腕ごとの判定（変更なし）

`arm_gate_released` / `arm_gate_never_released` / `arm_gate_not_entered`
の3種はそのまま使う。腕ごとにどれが出たかは結果として必ず記録する。

### 「未検証腕」を導入する

- **未検証腕**: `arm_gate_released` **以外**の判定が付いた腕
  （`arm_gate_never_released` または `arm_gate_not_entered`）。
  その腕の m6i-b の結果は、状態についての結果として読めない。

### 総合判定の名前と定義を直す

件数を数える対象を「`arm_gate_never_released` の腕」から「**未検証腕**」へ
変える。名前が中身とずれないよう、3つを改名する。

| 事前登録の名 | 本追補での名 | 定義 |
|---|---|---|
| `m6i_d_only_b5_never_released` | `m6i_d_only_b5_unverified` | 未検証腕が D-B5 のみ |
| `m6i_d_multiple_arms_never_released` | `m6i_d_multiple_arms_unverified` | 未検証腕が2つ以上 |
| `m6i_d_no_arm_never_released` | `m6i_d_no_arm_unverified` | 未検証腕が0 |

`m6i_d_b1_control_void` は名前を変えないが、定義を広げる。

- `m6i_d_b1_control_void`: **D-B1 が未検証腕である。**
  m6i-b の陰性対照は成立していない。事前登録のとおり、他の総合判定と併記する。

`m6i_d_observation_unusable` と `m6i_d_inconclusive` は変更しない。

### 副問も揃える

- `m6i_b_b2_b4_survive`: D-B2 と D-B4 が**ともに** `arm_gate_released`。
- `m6i_b_b2_b4_do_not_survive`: D-B2・D-B4 の一方以上が未検証腕。

## 4. 行き先の対応

事前登録 §5 を、改名にあわせて読み替える。中身は変えない。

- `m6i_d_only_b5_unverified`: 汚染は B5 だけ。B5 相当を m6i-e で取り直す。
- `m6i_d_multiple_arms_unverified`: 汚染が広い。腕を個別に救わず、停止方式を
  設計し直してから全腕を取り直す。
- `m6i_d_no_arm_unverified`: m6i-c と食い違うので、切り分けを別稿へ送る。
  **m6i-c の結果を上書きしない。**
- `m6i_d_b1_control_void`: 「待ち時間だけでは足りない」を m6i-b の根拠で
  述べない。陰性対照を、解除に他方の進行を要しない停止方式で作り直す。

## 5. 変わらないもの

- 腕の構成7種、ROM を1バイトも変えないこと、観測定義（sub run・ゲート run・
  最後のゲート run 基準の解除）、`gate_run_min_length` = 32、関門 G1〜G7、
  本文・値列を出さない規律は変更しない。
- `arm_gate_not_entered` が観測やROMの取り違えでも起こりうることは変わらない。
  **その可能性を消したのではなく、どちらでも結論が同じになるようにした。**
  取り違えを疑う必要があるかは、関門G4（ROM のバイト同一性）が別途答える。
