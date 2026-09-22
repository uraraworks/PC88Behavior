# m6i-b — 初回要求を許す状態境界の切り分け — 事前登録

記録日: 2026-09-22  
状態: 測定前

対象は、m6i-aで自作mainから自作subへ出した初回の単一セクタREADだけが成立せず、
A5の第2要求以後199回が成立した理由である。`docs/spec/l3-subrom.md` 1.65節が
確定した公式起動の順序を使い、通常READを許すために必要な状態境界が、
(a) FDC初期化完了、(b) 起動専用送信1件の消化、(c) ラウンド#0完了のどこかを
切り分ける。測定対象は自作mainと自作subだけであり、公式ROMは使わない。

## 1. 問い

自作main＋自作subで初回の通常READが成立するために必要な最早の状態境界は、
(b) 起動専用送信1件の消化、(a)+(b) の完了、(a)+(b)+(c) の完了のどれか。
また、状態を進めず同じ時間だけ待つ場合にも成立するなら、状態境界ではなく単なる
待ち時間で説明できるか。

副問は、m6i-a案AのA0/A1/A2/A4/A5について、(a)+(b)+(c)を完了する前置きを
加えると、元の到達条件へ届くようになるかである。結果条件はm6i-aから変更しない。

## 2. 腕（arm）

全腕で自作main ROM、自作sub ROM、m6i-aと同じ規則生成D88を使う。B1〜B5は
READ発行フレームを60に揃え、発行直前の状態を自作RAMマーカーと、値を含まない
順序・件数解析で確認する。`a`はFDC初期化7 batchの完了、`b`は起動専用SEND/RECV
1件の完了、`c`は2位置要求・1位置応答からなるラウンド#0の完了を表す。介入で
subを停止する腕は、停止解除後に同じ処理へ復帰させる。通常READはm6i-a A0と同じ
シリンダ0・ヘッド0・セクタ1、同じ交換列、同じ期待SHA-256を使う。

### B0 `immediate_reproduction`

- **何をするか**: m6i-a A0と同じ起動フックから、前置きなしで通常READを1回出す。
- **到達指標**: 起動フック、最初のSEND試行、timeoutまたは要求run完了の順を確認し、
  発行前に`a=0,b=0,c=0`であったことを確認する。
- **期待の形**: m6i-a A0と同じくtimeoutし、要求runは完了しない。これは再現腕で
  あり、この期待と違っても後続腕の結果へ読み替えない。

### B1 `elapsed_only_negative`

- **何をするか**: subをリセット直後の入口で停止し、mainも起動専用SENDを出さずに
  待つ。フレーム60でsubの停止を解除すると同時に通常READを出す。B2〜B5と同じ
  時間だけ経過させる陰性対照である。
- **到達指標**: フレーム0〜59にsubのCPU進行、FDC I/O、main→sub SENDが0件で、
  READ発行直前が`a=0,b=0,c=0`、発行フレームが60である。
- **期待の形**: 正常READは成立しない。成立した場合は「状態が変わったから」ではなく
  60フレーム待ったことだけで初回問題が消える形であり、状態境界の判定を止める。

### B2 `startup_consumed_before_init`

- **何をするか**: 起動専用SEND/RECVを1件だけ完了させ、subをFDC初期化の最初の
  I/O直前で停止する。フレーム60で通常READを出してから停止を解除する。
- **到達指標**: 起動専用SEND/RECVが各1件、READ発行前のFDC I/Oとラウンド#0応答が
  0件、状態が`a=0,b=1,c=0`、発行フレームが60である。
- **期待の形**: 256位置を受信し、SHA-256が
  `4ed6e24a1fb78f8c79423740e05a311c438bae0f09b9974e50619050fdb8540a`
  と一致して定常入力待ちへ戻るなら、(b)だけを満たした時点での発行で足りる。

### B3 `init_complete_startup_pending`

- **何をするか**: 状態直交化専用の自作subビルドで、起動専用RECVを保留したまま
  FDC初期化7 batchだけを完了し、その後は停止する。フレーム60で通常READを出して
  停止を解除する。この腕は公式の起動順を主張するものではない。
- **到達指標**: FDC初期化7 batchが完了し、起動専用SEND/RECVとラウンド#0が0件、
  状態が`a=1,b=0,c=0`、発行フレームが60である。
- **期待の形**: 正常READが成立すれば(a)単独で足り、(b)は必要条件ではない。
  成立しなければ、B2/B4/B5と合わせてのみ読む。

### B4 `init_and_startup_no_round0`

- **何をするか**: 通常順序で起動専用SEND/RECVとFDC初期化7 batchを完了し、
  ラウンド#0を開始する前で停止する。フレーム60で通常READを出して停止を解除する。
- **到達指標**: `b`の完了後に`a`が完了し、ラウンド#0の要求・応答は0件、状態が
  `a=1,b=1,c=0`、発行フレームが60である。
- **期待の形**: 正常READが成立すれば(a)+(b)で足り、(c)は必要条件ではない。

### B5 `round0_complete`

- **何をするか**: 通常順序で起動専用SEND/RECV、FDC初期化7 batch、ラウンド#0を
  完了して停止する。フレーム60で通常READを出して停止を解除する。
- **到達指標**: `b→a→c`が各1回この順に完了し、状態が`a=1,b=1,c=1`、
  発行フレームが60である。前置きの通信を通常READの要求runへ数えない。
- **期待の形**: 256位置、期待SHA-256、定常入力待ちへの復帰がすべて成立する。

### B6 `m6ia_reach_replay`

- **何をするか**: B5と同じ`b→a→c`前置き後、m6i-aのA0、A1、A2、A4-cont、
  A4-pair、A5を独立した枝として再走する。A5の200回に前置き通信を数えない。
- **到達指標**: 各枝でB5の前置き到達を確認した後、m6i-aに登録済みの各腕の
  到達指標をそのまま要求する。A5はREAD完了200回を要求する。
- **期待の形**: A0/A1/A2/A4/A5がすべて元の到達条件へ届く。到達後の結果条件と
  判定名はm6i-aのものをそのまま使い、到達だけを理由に合格へ読み替えない。

## 3. 関門（gate）

いずれかが偽なら測定腕へ進まず、全体を`gate_failed`として止める。

- **G1 自己検査**: `tools/run_all_selftests.sh`がrc=0で終わる。
- **G2 クリーンルーム検査**: `tools/check_cleanroom.sh`がrc=0かつNG 0件である。
- **G3 媒体と既存条件**: 規則生成媒体と空媒体のSHA-256、通常READの期待SHA-256、
  timeout上限、保存対象レジスタ、キー場面、画面署名がm6i-a追補1と一致する。
- **G4 状態観測の独立性**: `a`はFDC初期化完了、`b`は起動専用SEND/RECV、`c`は
  ラウンド#0応答受信の別マーカーで観測し、同じI/Oイベントを2状態へ重複計上しない。
- **G5 時刻と順序**: B1〜B5のREAD発行がすべてフレーム60で、B4/B5の通常順序が
  `b→a→c`、B1の停止中I/Oが0件である。状態が早く完成してもフレーム60まで待つ。
- **G6 ROM境界**: 各介入ビルドの差分が登録した1種類だけで、main ROM、sub ROM、
  拡張ROMが所定サイズと命令境界の検査を通る。介入なしビルドはm6i-a対象成果物と
  一致する。
- **G7 各腕の検出力**: 測定前に次の故障注入を各々1回行い、解析器が該当腕を
  `unreached`またはgate不成立にすることを確認する。B0は最初のSEND試行印を削除、
  B1は停止中にsubを1命令進める、B2は起動専用RECVを削除、B3は初期化batchを1件
  削除、B4はREAD前にラウンド#0応答印を挿入、B5はラウンド#0応答印を削除、B6は
  各枝のm6i-a到達印を1種類ずつ削除する。故障が検出されない腕は開始しない。
- **G8 結果検出力**: 合成入力で、256位置一致、1位置欠落、SHA不一致、timeout、
  定常入力待ち未復帰を別々に識別し、B6ではm6i-aの既存陰性対照を再び通す。
- **G9 未確定値の凍結**: 次項の値を測定前に器具の設定ファイルへ固定し、値または
  腕・判定名が本稿と違えばエミュレータ起動前に`gate_failed`で止める。

### 測定前に凍結する

本稿の時点で、次を凍結する。予備走で変更せず、満たせなければ結果を見ずに
事前登録をやり直す。

| 項目 | 凍結値 |
|---|---|
| B1〜B5の通常READ発行 | frame 60 |
| B0〜B4の測定期限 | 600 frames |
| B5の測定期限 | 600 frames |
| B6 A0/A1/A2/A4各枝 | 各600 frames |
| B6 A5 | 6000 frames、通常READ 200回 |
| 反復数 | 各腕・各枝2走。2走の判定が一致しなければ`unreached` |
| timeout上限 | 65535 |
| 正常媒体SHA-256 | `d3becfe5051f7002d268824a2da2824f543442e71ae3226e4d22139e0adce05c` |
| 空媒体SHA-256 | `2adb9833e0170aa9dfa5c5eb7c4b180307520cb8b2a671d6ee9db0903a3e8deb` |
| セクタ1 SHA-256 | `4ed6e24a1fb78f8c79423740e05a311c438bae0f09b9974e50619050fdb8540a` |
| セクタ2 SHA-256 | `f0cb8924325dbf2dece67fbebf41a9ee1ffbcd88fe8493ca18cbb49129d3ab0f` |
| A5保存対象 | `AF,BC,DE,HL,IX,IY` |
| キー場面 | `base_Q` |
| 画面ベースライン | 3行、20文字、SHA-256 `580684fbac954c32feb596092a55859a03090d0030a2297c8bb39a3424583f8e` |

## 4. 判定名

判定は関門、到達、結果の順で付ける。到達条件を満たさない腕を結果条件へ
読み替えない。2走が一致しない腕も`unreached`である。

- `gate_failed`: G1〜G9のいずれかが偽。腕ごとの成否は付けない。
- `unreached`: 関門通過後に腕の到達指標を満たさない。停止位置違い、状態値違い、
  発行フレーム違い、必要マーカー欠落も含む。
- `immediate_failure_reproduced`: B0が到達し、通常READがtimeoutした。
- `immediate_failure_not_reproduced`: B0が到達したが正常READが成立した、または
  m6i-aと異なる形で終了した。
- `elapsed_only_rejected`: B1が到達し、正常READが成立しなかった。
- `elapsed_only_sufficient`: B1が到達し、正常READが成立した。
- `b_only_sufficient`: B2が到達し、正常READが成立した。
- `b_only_insufficient`: B2が到達したが正常READが成立しなかった。
- `a_without_b_sufficient`: B3が到達し、正常READが成立した。
- `a_without_b_insufficient`: B3が到達したが正常READが成立しなかった。
- `ab_without_c_sufficient`: B4が到達し、正常READが成立した。
- `ab_without_c_insufficient`: B4が到達したが正常READが成立しなかった。
- `abc_sufficient`: B5が到達し、正常READが成立した。
- `abc_insufficient`: B5が到達したが正常READが成立しなかった。
- `m6ia_arms_reached_after_abc`: B6の全枝がm6i-aの元の到達条件を満たした。
  1枝以上が元の到達条件を満たさない場合、この結果判定は付けず、その枝を
  `unreached`とする。

以下の境界判定は、B0〜B5がすべて到達し、`immediate_failure_reproduced`が
成立することを共通の前提とする。

- `m6i_b_startup_consumption_boundary`: `elapsed_only_rejected`、
  `b_only_sufficient`、`a_without_b_insufficient`、`ab_without_c_sufficient`、
  `abc_sufficient`が成立する。
- `m6i_b_init_without_startup_boundary`: `elapsed_only_rejected`、
  `b_only_insufficient`、`a_without_b_sufficient`、`ab_without_c_sufficient`、
  `abc_sufficient`が成立する。
- `m6i_b_either_a_or_b_boundary`: `elapsed_only_rejected`、`b_only_sufficient`、
  `a_without_b_sufficient`、`ab_without_c_sufficient`、`abc_sufficient`が成立する。
- `m6i_b_init_and_startup_boundary`: `elapsed_only_rejected`、
  `b_only_insufficient`、`a_without_b_insufficient`、`ab_without_c_sufficient`、
  `abc_sufficient`が成立する。
- `m6i_b_round0_completion_boundary`: `elapsed_only_rejected`、
  `b_only_insufficient`、`a_without_b_insufficient`、`ab_without_c_insufficient`、
  `abc_sufficient`が成立する。
- `m6i_b_elapsed_time_only`: `elapsed_only_sufficient`が成立する。この場合は後続腕の
  形にかかわらず、状態境界の判定を付けない。
- `m6i_b_no_registered_boundary`: `elapsed_only_rejected`と`abc_insufficient`が
  成立する。
- `m6i_b_nonmonotonic`: B0〜B5がすべて到達したが、上の7総合判定のどれにも
  当てはまらない。
- `m6i_b_inconclusive`: 関門は通過したが、B0〜B6の1腕以上が`unreached`である。

## 5. 判定後の行き先

- `m6i_b_startup_consumption_boundary`: 通常READ前に起動専用SEND/RECVを1件完了する
  前置きを採用し、(a)/(c)を一般的な許可条件にはしない。
- `m6i_b_init_without_startup_boundary`: (a)単独で成立したのは状態直交化介入下だけ
  なので実装へ直結せず、通常順序での最小前置きを別稿で確認する。
- `m6i_b_either_a_or_b_boundary`: (a)と(b)のいずれでも成立する非単調な形なので、
  共通する下位状態を別稿で切り分ける。
- `m6i_b_init_and_startup_boundary`: 通常順序の`b→a`完了を前置きとして採用し、
  (c)を一般的な許可条件にはしない。
- `m6i_b_round0_completion_boundary`: 通常順序の`b→a→c`完了を前置きとして採用する。
- `m6i_b_elapsed_time_only`: 状態境界を実装せず、固定待ちの期限・再現性を別稿で
  事前登録する。本稿から待ち値を実装へ直結しない。
- `m6i_b_no_registered_boundary`または`m6i_b_nonmonotonic`: (a)(b)(c)以外の状態、
  介入による副作用、要求キューイングを別稿で切り分ける。
- `m6i_b_inconclusive`: 到達器具または期限だけを直す追補を先に置き、結果条件と
  判定名は緩めない。
- B6の副問は総合判定と独立に、全枝到達時だけ`m6ia_arms_reached_after_abc`を
  記録する。届かない枝は`unreached`のままとし、到達後の合否だけをm6i-aの
  判定名で記録する。

## 6. 本文に出さないもの

- 測定終了時のテキスト画面本文、main↔subのデータポート値列、セクタ本文は、
  標準出力、標準エラー、結果ノート、コミットメッセージへ出さない。件数、順序、
  真偽、SHA-256、判定名だけを扱う。
- I/Oログを残す場合は`tools/redact_iolog.py`で値列を伏せ、
  `tools/check_cleanroom.sh`を通す。ログの`--out`ファイルは直接開かない。
- 本文またはデータ列の漏えいを検出した走は結果に使わず`gate_failed`とする。

### この測定で決まらないこと

- 公式ROM内部の実装、公式の送受信値、実機での絶対時間は決まらない。
- (a)(b)(c)を実現する命令列や、ラウンド#0の意味論は決まらない。
- B3は状態直交化の介入であり、公式起動で`a→b`順が許されるとは主張しない。
- 成立した境界より後の状態が不要とは言えても、別媒体、WRITE、複数セクタREAD、
  BASIC命令一般に同じ境界を一般化しない。
- B6はm6i-aの到達回復だけを問い、m6i-a全体の合格や案A採用を自動的に決めない。
