# m7cf: FILES/LOAD需要入口は既に終端まで一致していた

実施日: 2026-08-23

## 情報境界

公式ROM一式＋公式diskAの使い捨て複製、および公式main ROM一式＋自作sub ROMを
同条件で実行した。公式ROM・公式ディスクの内容や`private/`配下は読んでいない。
生iolog、ROM複製、ディスク複製、標準出力・標準エラーはすべてリポジトリ外の
`mktemp -d`配下だけに置いた。本稿へ残すのは件数、SHA-256、公開μPD765
コマンド名、位置と記号化した分類だけで、`$FB/$FC/$FD`やFDCデータの値は
出していない。公式ディスク原本へは書き込んでいない。

## 測定条件とLOADの設計判断

共通して300FでRETURN、700Fから打鍵した。FILESは`FILES`を実行し2400F、
LOADは`10 PRINT "T"`を入力して`SAVE`、`NEW`、同名`LOAD`の順に実行し4800Fとした。
各実行は新規ROMディレクトリと新規ディスク複製を使い、300秒で打ち切る条件にした。
LOADだけ複製のライトプロテクトを解除した。

既存ファイルのLOADを選ばなかった理由は、媒体に元からあるファイル内容へ期待値を
依存させず、適合済みのSAVE経路の直後からLOAD入口を一意に作れるためである。
従ってこのLOAD測定は「書込済みファイルを同一実行内で読み戻す複合経路」を意味し、
既存ファイルだけを読む単独LOADの網羅性は主張しない。

## 公式・混成の比較

公開コマンド名を次の記号で短縮する。

- `R` = SEEK → SENSE INTERRUPT STATUS → SENSE DRIVE STATUS → READ DATA
- `W` = SEEK → SENSE INTERRUPT STATUS → SENSE DRIVE STATUS → WRITE DATA
- `P` = SPECIFY → RECALIBRATE → SENSE INTERRUPT STATUS → SEEK →
  SENSE INTERRUPT STATUS → RECALIBRATE → SENSE INTERRUPT STATUS →
  RECALIBRATE → SENSE INTERRUPT STATUS → SEEK → SENSE INTERRUPT STATUS →
  RECALIBRATE → SENSE INTERRUPT STATUS → RECALIBRATE → SENSE INTERRUPT STATUS

| 入口 | 公式FDC種別列 | 混成FDC種別列 | 一致prefix |
|---|---|---|---:|
| FILES | `P → R×16`（79件） | 同左（79件） | 79件（全長） |
| LOAD | `P → R×16 → SENSE DRIVE STATUS → W×6 → R → W → R → W → R×9`（156件） | 同左（156件） | 156件（全長） |

| 入口・列 | 公式件数 | 混成件数 | SHA-256 |
|---|---:|---:|---|
| FILES main `IN $FD` | 5635 | 5635 | `e26b22e7eec0d20725b25a34c00bc968820e1c7434c21cc45e0fb61939315ab7` |
| FILES main `IN $FC` | 7964 | 7964 | `7b9cfe61b8ef21cea7765549cffc4133135403df3b559d13f60159f9fcdd31c1` |
| LOAD main `IN $FD` | 5635 | 5635 | `e26b22e7eec0d20725b25a34c00bc968820e1c7434c21cc45e0fb61939315ab7` |
| LOAD main `IN $FC` | 9526 | 9526 | `f81bfb69eecd4e2d29e1baee0ea9c4bc266a989d17bb773b91fb6d21e46b3b9c` |

`IN $FD`は両入口とも起動時バルク5635件だけであり、それ単独では入口到達を
識別できない。そのため追加判定は同じ件数＋SHA形式の`IN $FC`も併用する。
これは5.2節の適合条件を変更・置換するものではなく、入口固有の到達指標である。

## 最初の差と停止位置

FDCコマンド**種別**列とmainの`IN $FC/$FD`列には最初の差が無く、いずれも
全長一致した。従って混成はFILES 79件目、LOAD 156件目まで到達し、観測区間に
停止・デッドロックは無い。

内部FDCポートの値列まで広げると、両入口とも一致prefixは1件で、最初の差は
2件目、最初のSPECIFYのパラメータ1件目における**同方向の値差**だった。
値は出していない。これはsub内部のFDC設定差であり、公開コマンド種別列とmainが
受け取る全列の一致を崩していない。5.1節どおり内部実装一致を新条件にはしない。

## 決定論性・判定器・次の境界

公式／混成×FILES／LOADの4条件を各2回実行した。iologヘッダの使い捨てパスを
除くmain/sub全イベント列は各組で完全一致し、FDC種別列、件数、SHA-256も一致した。

`conform_l3.sh`へ両入口を追加し、公式期待値と混成を同じ判定器へ通す。混成の列が
公式件数に届かなければ「失格」でなく「未到達」、公式件数へ届いてSHAだけ違えば
到達後の不一致とする。各入口の公式ログに対し、期待値のSHA末尾と件数をそれぞれ
壊したコピーが不一致になる故障注入を実行する。

FILES/LOADについて新たに実装すべき境界は観測されず、`make_subrom.py`は変更しない。
次は別の需要入口を同じ型で測る。既存ファイル単独LOADと、FDC内部パラメータ差を
解消すべきかは今回の測定からは確定しない。

## 検証結果

環境変数設定下の`conform_l3.sh`はrc=0で、FILES/LOADの期待SHA・件数を壊した
4故障をすべて不一致検出した。`LC_ALL=C tools/run_all_selftests.sh`は33/33項目で
C・UTF-8ともrc=0、結果表のNG 0・Traceback 0・SKIP行0だった。ただし直接実行した
`conform_l3.sh`では`PC88_REF_DISKB`未設定のため既存条件2だけSKIPであり、今回これを
再合格とは数えない。FILES/LOADおよびdiskAを使う既存判定は実走済みである。
