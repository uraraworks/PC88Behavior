#!/usr/bin/env python3
"""
make_subrom.py — L3 サービスルーチン（自作サブROM / DISK.ROM 相当）を組み立てる

根拠は `docs/spec/l3-subrom.md`（第30版）**だけ**である。公式 ROM も
公式ディスクの内容も一度も参照していない。

  なぜ Python でバイト列を組むのか: `src/l1_ipl/make_ipl_rom.py`（M4）と
  同じ理由。外部依存ゼロで第三者が `python3 make_subrom.py <出力先>` だけで
  同じ ROM を再生成できる。

## このファイルが実装するもの（仕様書 6節・1.10〜1.13節・1.15〜1.17節）

- 起動順序（1.16節・6節11項）。`OUT $F7,0x08` → `OUT $FF,0x91` →
  単発`IN $FE`読み2回 → RECVプリミティブ1回（**応答のSENDは行わない**）
  → `OUT $F8,0x05` → `OUT $F8,0xFF` → FDC初期化、という4条件で
  1バイトも違わず一致した手順をそのまま再現する。$FF=0x91・単発
  $FE読みの意味論は未確定（3節）だが、値そのものは確定しているため
  観測どおり再現する（推測ではなく観測の再現）。
- SEND/RECV の1バイト送受信ハンドシェイク（$FC/$FD/$FE/$FF 経由）。
  main 側の手順（1.10節）に **サブ側から見て正しく応答する**こと
  （6節5項。main のコードは自作できないので、mainが期待する外部
  インタフェースとしてここは固定である）。
- 交換#3/#4の応答対応（1.11・1.23節・6節6項）。交換#3の固定8バイト
  要求では実データ応答を開始せず、内部状態から作る1バイト応答を返す。
  続く交換#4の2バイト要求で、先にFDCから得て保持した実データ256バイトを
  `RESP_ACTIVE`経路へ接続する。交換#3の1バイトは意味未特定であり、
  ブラックボックス介入から再構成した観測応答を返す。意味が判明した場合に
  ルール生成へ差し替えるTODOを残す。
- μPD765 相当の FDC（`$FA`=ステータス、`$FB`=データ）を使ったセクタ
  読み出し。**コマンド体系は公開仕様（μPD765/8272データシート）に
  従って自分で書く**。公式ROMと同じFDCコマンド列を出す必要はない
  （仕様書 0節）。

## このファイルが実装しないもの

- 起動時の高速バルクモード（5635件のバースト転送、1.6節・1.10節）。
  仕様書 3節「未確定として残すこと」に明記されているとおり、
  「サブが要求を受けてから最初に応答するまでの遅延・手順」の測定は
  未着手であり、バルクモードの起動条件・トリガーの具体的な手順は
  仕様書に記載が無い。**推測で埋めない**という規律（CLAUDE.md）に
  従い、ここでは実装しない。`tools/verify_l3.sh` の報告を参照。
- 書き込み側（267バイト連続SENDバースト）と、そのsub側対応物と
  見られる「ストリーミングRECVループ」（1.17節）。仕様書 6節7項・
  12項により本マイルストーンのスコープ外。
- **値に基づくディスパッチ（1.17節・6節12項）。** 通常のRECV+SEND
  応答ペアとストリーミングRECVループを切り替える条件は、RECV
  プリミティブで受け取るデータの値（伏せ字済みで読めない）に依存する
  可能性が高いという以上のことが確定できていない。**推測で分岐条件を
  作らない**という規律に従い、本実装は確定済みの構造（起動時RECV1回、
  定常状態のRECV直後の即時SEND応答）のみを実装し、値による分岐は
  一切行わない。

## アイドル判別（第8版で追加、第10版でビット判定へ置き換え。
##                `docs/notes/m6l-idle-dispatch.md`・`docs/notes/
##                m6m-fe-bit-analysis.md`・仕様書1.19節・3節）

`docs/notes/m6k-mixed-divergence.md`第1部で報告された混成ROM実走の
デッドロックは、旧版のディスパッチャ（`REQ_LOOP`が毎回、何も確認せず
いきなり`OUT $FF,0x0B`（RECVプリミティブ手順1）を書いていたこと）が
直接原因だった。mainが逆に「subが送る番」を期待している局面で、
subが先に「RECVする（＝mainが送る番だと決め打つ）」と宣言してしまい、
互いに相手の`$FE`遷移を待ち続けて止まっていた。

**確定している範囲だけで直す。** `IDLE_DISPATCH`は`$FF`へ何も書かずに
`IN $FE`を読み、以下のどちらかのビット条件が成立するまでポーリングする:

- `bit3=1`（`FE_BIT_IDLE_RECV`）: 仕様書1.17節・1.19節・
  `docs/notes/m6k-mixed-divergence.md`第5部の「アイドル待ち」
  （`pc=00CC`）が4条件・観測全252件で例外なく到達し、その直後に必ず
  RECVへ進んでいた**確定済みの条件**。第8版までは到達値`0x08`との
  完全一致(`CP`)で判定していたが、これは観測されたentry値
  （`0x00`/`0x01`のみ、いずれもbit3=0）が偶然狭かったために結果的に
  正しく動いていたに過ぎない。entry値にbit3以外の未観測ビットが
  変化した値（例:`0x09`,`0x0C`）が現れると完全一致判定は誤って
  「まだアイドル」と判定し続ける——これが実際に混成ROM実走で
  報告されたデッドロック（main`IN $FE pc=37DC`1,041,413回・
  sub`IN $FE pc=00CC`1,048,477回のスピン）の見立てであり、第10版で
  `bit3=1`のビット判定（`AND`命令）へ置き換えて解消する。
- `bit1=1`（`FE_BIT_IDLE_SEND`）: 仕様書1.15節「sub視点のSENDプリミティブ
  手順1」が待つビットと同じ。**これは確定した判別条件ではない。**
  実測コーパス（`measurements/m6c-sub-*`・`m6g-d0-boot-run{1,2}`）には
  「アイドル待ちから直接SENDへ進む」事例が1件も無く（1.17節）、
  この値がアイドル時のバレ読みで実際にこの意味で現れるかどうかは
  未検証である。**仕様書の確定範囲（1.15節のSEND手順1のビット）から
  導いた暫定構造であり、値の裏付けは無い。** 第10版で、SEND手順6の
  定常サイトにおいて`bit1=1`→SEND開始・`bit3=1`→RECV開始という同じ
  対応が実際に両方観測される事例を確認した（1.19節）ため、この慣行
  自体が同一サブROM内の別サイトで存在することは確定したが、
  pc=00CC本体でこの分岐が実際に使われているかどうかは依然として
  未確認である。判定方式だけを完全一致からビット判定に揃えたが、
  確定度の格上げではない。

`bit1=1`に達したら`SEND_BYTE`を1回呼んで`IDLE_DISPATCH`へ戻る。

**第20版で訂正・再変更**: 第9版は「でっちあげた値を送らない」ため
`FDC_SENSE_DRIVE_STATUS`を実発行してST3を送る構造に差し替えたが、
混成ROM実走診断（22:16版）で**この場面（単発1バイト応答）では公式
subがFDCを一切叩かず、その場で1バイト送っていること**が構造として
確定した（分岐点103、基準側は`IN $FE`×2の直後に`OUT $FD`が来る
だけで`$FA`/`$FB`に触れない。混成側だけがFDCポーリングへ迂回して
分岐していた）。したがって第9版のFDC問い合わせ構造は**構造自体が
誤り**であり、値ではなく手順が公式と食い違っていた。

構造は測定で確定したので直すが、**送るべき値そのものは依然として
未確定のまま**である（1.18節・3節、ラウンド#0を含む単発応答の
中身は伏せ字済みで読めない）。

**第21版で再訂正**: 第20版は値に意味を持たせない`0x00`固定を暫定的に
置いたが、この状態で実走診断（main側の構造一致件数）を取り直すと
第9版（FDC問い合わせ構造、258件）より後退した（102件、m6t参照）。
「構造さえ合わせれば値は何でもよい」という想定はここでは成り立たず、
この1バイトの値がmain側の分岐に影響することが分かった。第21版は
`LAST_FDC_RESULT`というRAM上の1バイトに`FDC_IN`が実際に読み取った
最新の結果バイトを保持し、この場面ではFDCへ新規アクセスせずそれを
送る構造で両立を試みたが、main側一致件数は102件のままで第9版の
水準（実測は137件、5adf82e）を再現できなかった。

**第22版で再々訂正**: 仕様書5.1節・1.14節・1.15節の適合条件は
「mainが受け取るデータ列」であり、sub内部のI/O列が公式と一致する
ことそのものは適合条件ではない。第9版の`FDC_SENSE_DRIVE_STATUS`
実発行構造（main側137件一致）を優先し、こちらへ戻した。これは
第20版・6c0563dの測定結果（この場面でFDCイベント0件が99.6%）と
**食い違う**選択だが、ST3の値そのものは推測ではなくFDCが実際に
持つドライブ状態から得られる値であり、mainが受け取るバイト列を
公式と一致させるためにはその値が必要である。公式subがFDCを叩かずに
どこからこの値を得ているかはROM内部のワークエリア構造に踏み込む
領域でありクリーンルーム規律上測定では届かない（3節に未確定として
記録）。結果としてsub側I/O列は分岐点103で再び公式と食い違うが、
それは適合条件の対象外として許容する。`LAST_FDC_RESULT`のRAM機構は
使われなくなったため第22版で削除した。
`bit3=1`に達したら8バイトヘッダのRECV受信（`REQ_HEADER_RECV`）へ進む。
どちらのビットも立っていない中間値のあいだはポーリングを続ける
（`WAIT_FE_*`と同じ、ビット条件が成立するまで単純に回すスタイル）。

## プリミティブ1回ごとにディスパッチャへ戻る（第9版で修正）

**第8版の実装には別のバグがあった。** `IDLE_DISPATCH`は導入したものの、
`REQ_HEADER_RECV`（8バイトヘッダ受信）と応答送信（256バイト）を
それぞれ「一塊」として実装し、塊の**途中**では`IDLE_DISPATCH`に戻らず
`RECV_BYTE`/`SEND_BYTE`を機械的に8回・256回連続で呼んでいた。

ユーザーが2026-08-12に報告した公式環境での混成ROM実走で、これが
デッドロックを起こすことが分かった。sub側のイベント列（畳み込み後）は、
起動時RECV1回のあとIDLE_DISPATCHが1回だけ働いて8バイトヘッダ受信に
入り、1バイト目のRECVは成立した（`IN $FC`でデータを受け取り
`OUT $FF 0x0C`でRECVプリミティブの手順7まで完了）。ところが**その直後、
`IDLE_DISPATCH`に戻らず**、`_hdr_loop`のDJNZがそのまま2バイト目の
RECV開始（`OUT $FF 0x0B`）に落ち、そのまま`$FE`待ちで永久停止した。
同じ時刻、公式mainは`OUT $FF`（1.10節main側RECVプリミティブの開始
＝「subが送る番」）を出して`IN $FE`でスピンし、タイムアウトしていた。
つまり**mainは8バイト連続で送るとは限らず、1バイトだけ送って
RECVへ切り替えることがある**——sub側が「一度RECVに入ったら8バイト
連続で来る」と決め打ちしていたこと自体が誤りだった。

**確定している範囲だけで直す。** `REQ_HEADER_RECV`・応答送信を
「塊」として実装するのをやめ、RAM上のポインタ（`HDR_PTR`・
`RESP_PTR`・`RESP_ACTIVE`）で進行状態を持たせ、**`RECV_BYTE`/
`SEND_BYTE`を1回呼ぶたびに必ず`IDLE_DISPATCH`へ戻る**構造にした。
8バイト集まったら（あるいは256バイト送り終えたら）その場で
次の処理（シーク・読み出し・応答準備、または応答フェーズの終了）を
行うが、**次に何をするか（RECVを続けるかSENDに切り替わるか）は
毎回`IDLE_DISPATCH`が`$FE`を読んで決める**。アイドル判別条件
そのもの（`bit1=1`＝SEND分岐が未確定であること）は変えていない
（第10版で判定方式をビット判定に揃えたのみ、上の「アイドル判別」節
参照）。

## $FA/$FB のポート番号について

サブが FDC とどう通信するかは内部実装なので本来自由（仕様書0節）だが、
**このハーネス（vendor/quasi88-libretro）の FDC デバイスは $FA/$FB に
固定配置されている**（サブ CPU から見えるアドレス空間の物理配置。
GPL の第三者エミュレータ実装 `src/pc88sub.c`・`src/fdc.c` を確認した。
`docs/spec/l3-subrom.md` 2.1節が pio.c を読んだのと同じ扱いで、
公式ROMとは無関係・読むことは規律上の禁止対象外）。ポート番号は
選べないが、**そこに何のバイト列を送るか（コマンド体系）は
公開仕様に従って自分で決めている**。

## $FE/$FF の意味論について（第6版で全面改訂）

**旧版（第5版まで）の実装は誤りだった。** 以前はここで「ポートCは
たすき掛け配線で、sub 側が `OUT $FE` に直接マスク値を書き込む」という
理論を採用していたが、これは自作サブROM＋自作試験用mainドライバ
（`tools/make_l3_test_main.py`）同士を組ませて動かした結果を根拠にして
おり、**双方が自作である以上「仕様書どおりの相手」を検証したことには
ならなかった**（誤解を共有したまま両者が「動く」ように調整し合って
いた）。公式サブROMを公式環境で実走させた測定（`docs/spec/l3-subrom.md`
1.15節・6節10項）により、**公式subは`$FE`に一度も書き込まない**ことが
確定した。したがって本版では `OUT $FE` を一切行わない。

sub がすることは `OUT $FF` にフェーズコード（1.12節の8値の部分集合）を
書くことだけであり、相手（main）の`$FF`書き込みが`$FE`側にどう映るかは
PIOハードウェアの仕事であって sub 側コードが関与しない。sub は
`IN $FE` で相手の状態を読み、仕様書 1.15節の遷移表に記載された
**到達値**（矢印の右側・`⇄`の右側の値）に達するまで待つ。

## $FE 待ちのビット判定（第10版で全面改訂。仕様書1.19節・3節・6節15項）

**第9版までの実装は「到達値との完全一致（`CP`命令）」でループを
抜けていたが、これは実際に観測された範囲の値でしか正しく動かない。**
混成ROM実走で main が `IN $FE pc=37DC`（1.13節「SEND前」）で
1,041,413回、sub が `IN $FE pc=00CC`（1.17節「アイドル待ち」）で
1,048,477回スピンしてデッドロックした。仕様書1.19節
（`docs/notes/m6m-fe-bit-analysis.md`）は、既存ログの再解析
（追加測定なし）により、これらの待ちが**単一ビットのテストで説明できる**
ことを確定した——「意味を持つビットの隣で別のビットが動いている」ため、
完全一致判定は観測されなかった値の組み合わせを取りこぼす。

具体的な待ちとビット（1.19節の表をそのまま転記。`AND`命令でビットを
取り出し、`Z`フラグでループを続けるか判定する）:

| sub の待ち | 仕様書の遷移 | 効いているビット | 例外 |
|---|---|---|---|
| RECVプリミティブ・手順2（相手のデータ準備待ち） | `20→21` / `28→21` | `bit0=1` | 0件(4条件) |
| RECVプリミティブ・手順6（相手の受理解除待ち） | `41→40` | `bit0=0` | 0件(4条件) |
| SENDプリミティブ・手順1（相手の受信準備待ち） | `00→02` | `bit1=1` | 0件(4条件) |
| SENDプリミティブ・手順4（相手の受理確認待ち） | `12⇄14` | `bit2=1`（`bit1=0`も同格） | 0件(4条件) |

SENDプリミティブ手順6（「`IN $FE` でステータス相当を読む（スピン）」）は
第9版までは「仕様書が境界的な待ちと明記しており確定した目標値が無い」
として単発読み捨て（ブロックしない）にしていた。仕様書1.19節が
定常状態の同型サイトを再解析した結果、**待ちの終了条件自体は
`bit2=0`で単一ビット説明できる**ことが確定した（従来「単一の固定値
読みではない」としていた記述の訂正——待ちの終了条件と、終了後の
分岐先を決める値の2つの異なる情報が1バイトに同居していたための
混同だった）。本版ではここも`bit2=0`へのビット待ちに変更する。
終了後に何を返すか（結果値のbit1/bit3による後続分岐）はここでは
使わない——呼び出し元（`IDLE_DISPATCH`）が改めて`$FE`を読んで
決めるため、待ちを終えた時点の値そのものは捨ててよい。

アイドル判別（`IDLE_DISPATCH`）のビット判定への置き換えは、上の
「アイドル判別」節（第8版で追加、第10版で更新）を参照。

## run境界（連続受信の途中か終わりか）の判別（第11版で追加。
##          `docs/notes/m6n-run-boundary.md`・仕様書1.20節・3節・6節16項）

コミット`c73fb00`後の混成ROM実走で、mainの構造的一致プレフィックスが
137件のまま前進しなかった。原因は、mainが複数バイト連続SEND（run、
例えば8バイトヘッダの2バイト目以降）では`OUT $FF 0F`を省略して
直接「相手の受信準備待ち」（`bit1=1`）に入るのに対し、旧`RECV_DISPATCH`
はRECVを1回終えるたびに無条件で`IDLE_DISPATCH`へ戻っていたことに
あった。`IDLE_DISPATCH`はそこで改めて`$FE`を読みに行くだけで**何も
書かない**ため、mainが待っている`bit1=1`（＝subが`OUT $FF,0x0B`を
書くこと）がいつまでも来ず、mainは`bit1`を待ち、subは（何も書かずに）
mainの新しい合図を待つ、という相互デッドロックになっていた。

仕様書1.20節（`docs/notes/m6n-run-boundary.md`）で、sub の
`OUT $FF=0x0C`（RECV完遂）直後の後継サイトを再解析したところ、
4条件すべて・全サンプルで例外なく、各サイトが「必ずRECVへ進む」か
「必ずSENDへ進む」かに一意に決まることが確定した。**ただし、公式sub
の実行コードがどちらへ分岐するかの選択根拠（多くの場合`$FE`/`$FF`を
一切経由しない直接再武装）は、値を見ない本手法の観測範囲外で確認
できなかった。**

**確定できなかった選択根拠を推測で埋める代わりに、確定済みの範囲
（1.19節の2つのビット）だけを新しい局面へ機械的に適用した暫定構造を
採る。** `RECV_DISPATCH`は、8バイト未満で継続する場合、
`IDLE_DISPATCH`へ戻る前に**直ちに再武装**（`OUT $FF,0x0B`。
mainが`bit1=1`を待ってスピンしている場合があるため、武装を後回しに
すると上記の相互デッドロックを再現してしまう）したうえで、
`$FE`のポーリングで`bit1`（`FE_BIT_SEND_RECV_READY`。相手がRECV役に
転じた＝応答を求めている合図）と`bit0`（`FE_BIT_RECV_DATA_READY`。
相手が続けてデータを書いた＝runが続いている合図）の両方を同時に
見張り、先に立った方へ分岐する。`bit0`が先ならRECVプリミティブの
残り手順（`RECV_BYTE_ARMED`、手順2〜7）を続ける。`bit1`が先なら
`IDLE_DISPATCH`（既存のSEND経路）に委ねる。**使っているビットは
いずれも別の文脈（1.19節）で確定済みのものであり、新しい推測を
追加していない。** ただし「RECV完遂直後に毎回この2ビットを同時
ポーリングする」という構造自体は公式subの観測された振る舞い
（直接再武装のケースは`$FE`/`$FF`を経由せず無条件に分岐する）とは
異なる**自作subの暫定的な設計選択**であり、確定した判別条件では
ない（仕様書1.20節・3節・6節16項）。

## run境界駆動への書き換え（第13版。`docs/notes/m6k-mixed-divergence.md`
##                        第10部・仕様書1.18節・1.20節・3節・6節17項）

コミット`c9f5a0f`（FDCタイムアウト分岐修正）後、混成ROMを公式環境で
実走したところ、mainの構造的一致プレフィックスは179→180件に前進し
（FDCが完走するようになった）、その先で新たな分岐点が見つかった。
**サブROMがラウンド境界を無視して受信バイトを通算8バイト貯め、
それを1.11節の固定8バイトヘッダと取り違えていた。** 1.18節が確定した
起動シーケンスの構造（可変長ラウンドのSEND→RECV往復、ラウンドごとに
応答が返る）によれば、起動シーケンス最初の3ラウンドは2バイト・
1バイト・5バイトという短い独立した要求であり、それぞれ単独で応答が
返るはずだった。ところが第11版までの`RECV_DISPATCH`は、runの継続/
終了の判別（16項のbit0/bit1同時ポーリング）こそrun境界で行っていた
ものの、**応答形式の決定（8バイト到達で即座にシーク・読み出し・
応答フェーズへ進むかどうか）は依然として通算バイト数（`HDR_PTR`が
`REQ_HDR+8`に達したか）だけで判定していた**。そのため、3ラウンドの
通算2+1+5=8バイトが「8バイトヘッダが1つ揃った」と誤認され、
sub側は256バイト応答フェーズを開始してしまう一方、mainは（本来の
短いラウンドどおり）1バイトの応答しか受け取らずに次のラウンドへ
進もうとする——**両者が同時に「送る側」になって固着する**
（main側`pc=37DC`で262,144回、sub側`pc=01B3`で262,145回のスピンで
停止することを確認した。詳細は`docs/notes/m6k-mixed-divergence.md`
第10部）。

**確定している範囲だけで直す。** runの終端（`RECV_DISPATCH`が
継続ポーリング中に`bit1=1`を観測すること、16項で既に確定済みの
判別条件）そのものを、応答をいつ・どの形式で返すかの駆動条件に
格上げする。固定バイト数（8バイト）での打ち切りを廃し、bit0が
立ち続ける限りrunは何バイトでも継続を許す。runが終わった時点で
初めて、そのrunを一つの要求として確定する。この判断に使うビット
（`bit0`＝RECVプリミティブ手順2、`bit1`＝SENDプリミティブ手順1）は
16項から変えていない。

**第29版で応答形式の対応を訂正した。** 第13版の「`RUN_LEN==8`なら
256バイト応答」という規則は撤回する。交換#3の固定8バイト要求では
FDCデータを`SECTOR_BUF`へ準備しても`RESP_ACTIVE`を立てず、内部状態
1バイト応答を保留する。続く交換#4の2バイト要求が完了したとき初めて、
準備済み`SECTOR_BUF`を`RESP_ACTIVE`へ接続する。交換#3の内部状態応答は
意味未特定であり、第30版のブラックボックス介入で挙動から再構成した観測値を
返す。意味が判明した場合はルール生成へ差し替える。

**run開始時の状態初期化（第13版で追加）。** `RECV_DISPATCH`への
進入時（＝`IDLE_DISPATCH`が`bit3=1`を観測し新しいrunが始まる時点）に
`HDR_PTR`をREQ_HDRへ、`RUN_LEN`を0へ、そして**`RESP_ACTIVE`も0へ**
明示的にリセットする。旧構造は`RESP_ACTIVE`を応答フェーズ終了時にしか
クリアしておらず、応答送信の途中でmainが送り手へ戻った場合（run長が
8でない短いラウンドが応答の合間に割り込む場合）、残留した
`RESP_ACTIVE=1`が次のrunの`SEND_DISPATCH`判定を汚す余地があった。

**受信バッファの拡張（第13版で追加）。** `REQ_HDR`の受信バッファを
8バイトから`REQ_HDR_CAPACITY`（16バイト）へ拡張した。1.18節は最大
12バイトのラウンドを確認しており、8バイト固定のままでは長いrunの
受信中にバッファをはみ出す。`RUN_LEN`が`REQ_HDR_CAPACITY`に達したら
以降は格納だけ止め（`HDR_PTR`は進めない）、カウンタ自体は`0xFF`まで
飽和させながら受信は止めない——runの継続/終了判別（bit0/bit1）を
乱さないようにするため。

**`HDR_STORE_AND_CHECK`のセマンティクス変更。** 第11版までは
「格納してZ=1なら8バイト到達」という意味を持っていたが、応答形式の
判断を通算バイト数から切り離した結果、この呼び出し元での即時判定は
不要になった。第13版では「格納して`RUN_LEN`を進めるだけ」の
サブルーチンに縮小した（上限到達時の格納スキップ・カウンタ飽和は
このサブルーチン内で完結する）。

**回帰テスト（`--fixed-byte-cutoff-test`）。** `tools/verify_l3.sh`
の規約どおり、有効時は本版で修正した旧構造（通算8バイトで打ち切る）
をそのまま復元するフラグを用意した。`tools/make_l3_test_main.py
--fixed-byte-cutoff-test`（2バイト・1バイト・5バイトの独立した
3ラウンド、値の並びは合わせると1.11節のヘッダと同じ形になる）を
使い、新実装ではPASS・このフラグを立てた版ではFAILすることを実際に
確認した。

## FDC結果/コマンドフェーズの終了判定とタイムアウト時の中止（第12版で修正）

コミット`ce3bd5b`（SENSE INTERRUPT STATUSの結果バイト数修正＋FDCステータス
待ちタイムアウト追加）を公式環境の混成ROMで実走したところ、mainの構造的
一致プレフィックスは179件のまま前進せず、sub側は「`IN $FA`を65,535回
ポーリング→タイムアウトして`OUT $F9`を記録→**タイムアウトしたのにそのまま
`IN $FB`を読む**」という3つ組を15回繰り返して測定イベント上限を食い潰して
いた。

**原因は`FDC_IN`/`FDC_OUT`の構造そのものにあった。** 旧実装はタイムアウト
時の分岐と正常時の分岐が同じ着地点（同じラベル）に合流しており、
タイムアウトを記録した**直後に無条件で`IN $FB`（またはOUT）を実行して
いた**。μPD765/8272データシートの規定では、結果フェーズのバイトを読める
のは`RQM=1`かつ`DIO=1`（bit6、FDC→CPU方向）のときだけであり、最後の結果
バイトを読み終えると`RQM=1`のまま`DIO`はCPU→FDC方向（0）に戻り、FDCは次の
コマンドバイトを待つ状態（コマンドフェーズ）に入る。旧実装は`RQM`と`DIO`の
両方を待ち条件には使っていたが、**待ちを諦めた後の分岐（タイムアウト
処理）では読み書きをせずに中止する、という設計になっていなかった**。

本版では次の3点を直す（すべてμPD765/8272データシートの規定のみを根拠とし、
`vendor/quasi88-libretro/src/fdc.c`は参照していない。経緯は
`docs/notes/fdc-datasheet-only-going-forward.md`）:

1. **タイムアウト時は読み書きしない。** `FDC_IN`/`FDC_OUT`のタイムアウト
   分岐と正常分岐を完全に分離し、タイムアウト側は`$FB`に一切触れずに戻る。
2. **結果/データフェーズが待たずに終わっていた場合も同様に中止する。**
   `FDC_IN`側で`RQM=1`かつ`DIO=0`を観測した場合（＝待つ前に既に
   コマンドフェーズへ戻っている＝呼び出し側が期待したバイトはもう無い）、
   `FDC_OUT`側で`RQM=1`かつ`DIO=1`を観測した場合（＝コマンドを受け付ける
   状態ではなく結果データが溜まっている＝呼び出し側との食い違い）は、
   タイムアウトを待たずに即座に中止する。
3. **同一コマンド内でタイムアウト／中止が繰り返し発生しないようにする。**
   RAM上に1バイトの中断フラグ（`FDC_ABORT`）を置き、FDCコマンド1つ分の
   呼び出し列（`FDC_SPECIFY`・`FDC_SENSE_INT`・`FDC_RECALIBRATE`・
   `FDC_SENSE_DRIVE_STATUS`・`FDC_SEEK`・`FDC_READ_SECTOR`の各入口）で
   クリアする。一度中断すると、そのコマンドの残りの`FDC_IN`/`FDC_OUT`
   呼び出しはポートに一切触れずに即座に戻る（ポーリングも記録も発生
   しない）ため、1コマンドあたり実際にタイムアウトのポーリングが起こる
   のは最大1回だけになる。タイムアウト回数自体も0xFFFFから
   `FDC_WAIT_TIMEOUT`（下のdocstring参照）へ大幅に縮小した。

いずれも仕様書に根拠のある値ではなく、この実装だけの判断であることを
コード中のコメントに明記した。$F9への記録（診断用マーカー）は残すが、
公式subには存在しないイベントなので適合テストに出すROMでは無効化できる
オプション（`--disable-fdc-timeout-mark`）を追加した（既定は有効のまま）。
"""

import argparse
import pathlib
import sys

# --------------------------------------------------------------------------
# ポート（仕様書 1.4節・1.7〜1.9節・1.12〜1.13節、および上記docstring）
# --------------------------------------------------------------------------

P_FDC_STAT = 0xFA   # IN: FDC メインステータス。bit7=RQM（仕様書1.7節）
P_FDC_DATA = 0xFB   # IN/OUT: FDC データ/コマンド
P_TC       = 0xF8   # OUT: FDC へ TC（ターミナルカウント）を送る。
                     # 第15版で訂正: 旧コメント「IN」はvendor実装由来の
                     # 方向の取り違え。仕様書1.21節・docs/notes/
                     # m6p-tc-and-f8.md参照——公式subは$F8を主にOUTで
                     # 使い、IN $F8は「OUT $F7,0x08直後の単発確認読み
                     # (値は常に0xFF)」に限られる。
P_PIO_A    = 0xFC   # sub からは OUT で main の $FD 書き込みが IN で読める（SEND受信）
P_PIO_B    = 0xFD   # sub の OUT がここに出ると main の IN $FC に見える（RECV送信）
P_PIO_C    = 0xFE   # ハンドシェイク状態。sub は IN のみ（仕様書6節10項: subはOUTしない）
P_STROBE   = 0xF7   # 起動時ハンドシェイクで書く（仕様書1.5節・1.16節。用途は未確定）

# ---- FDCステータス待ちタイムアウトの診断用マーカー（仕様書に根拠は無い。
#      下の FDC_WAIT_TIMEOUT の docstring 参照）----
# $F9 は vendor/quasi88-libretro/src/pc88sub.c の sub_io_out() switch に
# case が無い「未デコードポート」（同ファイル実測: f4/f7/f8/fb/fc/fd/fe/ff
# のみ処理され、それ以外は verbose_io ログを出すだけで no-op として黙って
# 捨てられる）。副作用が無いことを確認した上で、タイムアウト発生を
# iolog に残すためだけに使う。
P_FDC_TIMEOUT_MARK = 0xF9
FDC_TIMEOUT_MARK_VALUE = 0xA5   # 事実上何でもよい。ポートへの到達自体が信号

# ---- 起動順序で使う固定値（仕様書1.16節。4条件で1バイトも違わず一致） ----
BOOT_F7_VALUE = 0x08
BOOT_FF_VALUE = 0x91   # 1.12節の8種のフェーズコード語彙のいずれにも属さない
BOOT_F8_VALUE_1 = 0x05
BOOT_F8_VALUE_2 = 0xFF

# ---- TC三つ組み（仕様書1.21節、第15版）。OUT $F8,0x07 -> OUT $F7,0x08 ->
#      IN $F8(結果は捨てる。値は常に0xFFだが意味は未確定なので分岐に
#      使わない) が4条件・全事例で例外なく隣接することを確認済み。 ----
FDC_TC_VALUE = 0x07

RQM  = 0x80   # $FA bit7
DIO  = 0x40   # $FA bit6（1='FDCからホストへ'方向）

# ---- $FF フェーズコード語彙（仕様書1.12節。SEND系/RECV系で共通） ----
PH_SEND_START_SET = 0x0F   # （sub SENDでは使わない。main SENDの語彙）
PH_SEND_START_CLR = 0x0E   # （同上）
PH_SEND_DATA_SET  = 0x09
PH_SEND_DATA_CLR  = 0x08
PH_RECV_START_SET = 0x0B
PH_RECV_START_CLR = 0x0A
PH_RECV_ACK_SET   = 0x0D
PH_RECV_ACK_CLR   = 0x0C

# ---- sub視点の $FE 待ちビットマスク（第10版。仕様書1.19節・
#      docstring「$FE 待ちのビット判定」参照。完全一致(CP)からビット
#      判定(AND)へ置き換えた。マスクは「テストするビット」、
#      *_WANT_SET は「そのビットが1になったら抜けるか(True)/
#      0になったら抜けるか(False)」）----
FE_BIT_RECV_DATA_READY = 0x01   # bit0=1: RECVプリミティブ手順2(20→21 / 28→21)。0例外
FE_RECV_DATA_READY_WANT_SET = True
FE_BIT_RECV_ACK_DONE   = 0x01   # bit0=0: RECVプリミティブ手順6(41→40)。0例外
FE_RECV_ACK_DONE_WANT_SET = False
FE_BIT_SEND_RECV_READY = 0x02   # bit1=1: SENDプリミティブ手順1(00→02)。0例外
FE_SEND_RECV_READY_WANT_SET = True
FE_BIT_SEND_ACK_DONE   = 0x04   # bit2=1: SENDプリミティブ手順4(12⇄14。bit1=0も同格だがbit2採用)。0例外
FE_SEND_ACK_DONE_WANT_SET = True
FE_BIT_SEND_STATUS_CLEAR = 0x04  # bit2=0: SENDプリミティブ手順6(「境界的な待ち」)。定常サイトで0例外
FE_SEND_STATUS_CLEAR_WANT_SET = False

# ---- アイドル判別（上のdocstring「アイドル判別のビット化」節を参照。
#      第8版で追加、第10版でビット判定へ置き換え） ----
FE_BIT_IDLE_RECV = 0x08   # 確定: bit3=1。1.17節「アイドル待ち(pc=00CC)」の到達条件(4条件252件で例外なし)
FE_BIT_IDLE_SEND = FE_BIT_SEND_RECV_READY  # 未確定: bit1=1。SENDプリミティブ手順1と同じビットからの類推(pc=00CC自体では裏付け無し)

# --------------------------------------------------------------------------
# ごく小さな Z80 アセンブラ（src/l1_ipl/make_ipl_rom.py の Asm を踏襲）
# --------------------------------------------------------------------------


class Asm:
    def __init__(self, org=0x0000):
        self.code = bytearray()
        self.org = org
        self.labels = {}
        self.fixups = []

    @property
    def pc(self):
        return self.org + len(self.code)

    def label(self, name):
        if name in self.labels:
            raise ValueError(f"ラベル重複: {name}")
        self.labels[name] = self.pc

    def db(self, *bs):
        for b in bs:
            if not 0 <= b <= 0xFF:
                raise ValueError(f"バイト範囲外: {b:#x}")
            self.code.append(b)

    def dw_imm(self, nn):
        self.db(nn & 0xFF, (nn >> 8) & 0xFF)

    def _abs(self, name):
        self.fixups.append((len(self.code), name, "abs"))
        self.db(0x00, 0x00)

    def _rel(self, name):
        self.fixups.append((len(self.code), name, "rel"))
        self.db(0x00)

    def resolve(self):
        for pos, name, kind in self.fixups:
            if name not in self.labels:
                raise ValueError(f"未定義ラベル: {name}")
            addr = self.labels[name]
            if kind == "abs":
                self.code[pos] = addr & 0xFF
                self.code[pos + 1] = (addr >> 8) & 0xFF
            else:
                delta = addr - (self.org + pos + 1)
                if not -128 <= delta <= 127:
                    raise ValueError(f"相対ジャンプが届かない: {name} ({delta})")
                self.code[pos] = delta & 0xFF

    # ---- 命令 ----
    def di(self):        self.db(0xF3)
    def ei(self):         self.db(0xFB)
    def ret(self):        self.db(0xC9)
    def nop(self):        self.db(0x00)
    def inc_hl(self):     self.db(0x23)
    def dec_b(self):      self.db(0x05)
    def inc_c(self):      self.db(0x0C)
    def ld_a_hl(self):    self.db(0x7E)
    def ld_hl_a(self):    self.db(0x77)
    def ld_a_b(self):     self.db(0x78)
    def ld_a_c(self):     self.db(0x79)
    def ld_b_a(self):     self.db(0x47)
    def ld_c_a(self):     self.db(0x4F)
    def push_af(self):    self.db(0xF5)
    def pop_af(self):     self.db(0xF1)
    def push_bc(self):    self.db(0xC5)
    def pop_bc(self):     self.db(0xC1)
    def push_hl(self):    self.db(0xE5)
    def pop_hl(self):     self.db(0xE1)
    def push_de(self):    self.db(0xD5)
    def pop_de(self):     self.db(0xD1)
    def dec_de(self):     self.db(0x1B)   # DEC DE（フラグは変化しない。ゼロ判定は別途 LD A,D / OR E で行う）
    def ld_a_d(self):     self.db(0x7A)
    def ld_a_e(self):     self.db(0x7B)   # LD A,E（第18版で追加。FDCルーチンのドライブ番号引数化に使う）
    def ld_e_a(self):     self.db(0x5F)   # LD E,A
    def or_e(self):        self.db(0xB3)
    def or_a(self):        self.db(0xB7)   # OR A（キャリーを0にするためだけに使う）
    def sbc_hl_de(self):    self.db(0xED, 0x52)   # SBC HL,DE（ED 42はSBC HL,BC。取り違え注意）

    def ld_a(self, n):    self.db(0x3E, n)
    def ld_b(self, n):    self.db(0x06, n)
    def ld_c(self, n):    self.db(0x0E, n)
    def ld_e(self, n):    self.db(0x1E, n)   # LD E,n（第18版で追加。FDCルーチンのドライブ番号引数化に使う）
    def and_a(self, n):   self.db(0xE6, n)
    def or_n(self, n):    self.db(0xF6, n)
    def cp_n(self, n):    self.db(0xFE, n)
    def ld_sp(self, nn):  self.db(0x31, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_de_imm(self, nn): self.db(0x11, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl_imm(self, nn): self.db(0x21, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl_mem(self, addr): self.db(0x2A, addr & 0xFF, (addr >> 8) & 0xFF)  # LD HL,(nn)
    def ld_mem_hl(self, addr): self.db(0x22, addr & 0xFF, (addr >> 8) & 0xFF)  # LD (nn),HL
    def ld_a_mem(self, addr):  self.db(0x3A, addr & 0xFF, (addr >> 8) & 0xFF)  # LD A,(nn)
    def ld_mem_a(self, addr):  self.db(0x32, addr & 0xFF, (addr >> 8) & 0xFF)  # LD (nn),A
    def ld_hl(self, name):   self.db(0x21); self._abs(name)
    def call(self, name):    self.db(0xCD); self._abs(name)
    def jp(self, name):      self.db(0xC3); self._abs(name)
    def jp_nz(self, name):   self.db(0xC2); self._abs(name)   # JP NZ,nn（第13版で追加。相対ジャンプが届かない遠方分岐用）
    def jp_z(self, name):    self.db(0xCA); self._abs(name)   # JP Z,nn
    def jr(self, name):      self.db(0x18); self._rel(name)
    def jr_nz(self, name):   self.db(0x20); self._rel(name)
    def jr_z(self, name):    self.db(0x28); self._rel(name)
    def jr_nc(self, name):   self.db(0x30); self._rel(name)   # JR NC,e（第13版で追加。run長カウンタの上限判定に使う）
    def jr_c(self, name):    self.db(0x38); self._rel(name)
    def inc_a(self):         self.db(0x3C)   # INC A（第13版で追加）
    def djnz(self, name):    self.db(0x10); self._rel(name)

    def in_port(self, port):
        """IN A,(port)"""
        self.db(0xDB, port)

    def out_a(self, port):
        """OUT (port),A（A の値をそのまま出す。記録はしない——l3は
        OUT列比較の対象ではなく、末端(main の IN $FD)だけが適合条件
        （仕様書5.1節））。"""
        self.db(0xD3, port)

    def out_imm(self, port, value):
        self.ld_a(value)
        self.out_a(port)


# --------------------------------------------------------------------------
# RAM 配置（サブ側は 0x4000-0x7FFF のみ書き込み可。vendor sub_mem_write）
# --------------------------------------------------------------------------

STACK      = 0x6000
SECTOR_BUF = 0x4000    # 256バイトのセクタ読み出しバッファ
# ---- 第13版でREQ_HDRの領域を8バイトから拡張（下のREQ_HDR_CAPACITY参照）。
#      HDR_PTR(0x4300)まで0x100バイトの余地があるため衝突しない。 ----
REQ_HDR    = 0x4200    # 要求ヘッダの受信バッファ（先頭REQ_HDR_CAPACITYバイトまで格納）
REQ_HDR_CAPACITY = 16  # 第13版で8→16へ拡張。1.18節の最大12バイトのラウンドに余裕を持たせる

# ---- ディスパッチャの進行状態（第9版で追加。上のdocstring「プリミティブ
#      1回ごとにディスパッチャへ戻る」参照）----
HDR_PTR     = 0x4300   # 2バイト: ヘッダ受信中の書き込み位置(REQ_HDR..REQ_HDR+REQ_HDR_CAPACITY)
RESP_PTR    = 0x4302   # 2バイト: 応答送信中の読み出し位置(SECTOR_BUF..SECTOR_BUF+256)
RESP_ACTIVE = 0x4304   # 1バイト: 0=応答フェーズでない、非0=応答送信中
# ---- 第12版で追加。FDC_IN/FDC_OUTが「タイムアウトした／待たずに相手が
#      フェーズを終えていた」ことを検出したら1を立てる。同一FDCコマンド
#      呼び出し列の残りのFDC_IN/FDC_OUTはこれを見て即座に戻り、ポートに
#      触れない（上のモジュールdocstring「FDC結果/コマンドフェーズの
#      終了判定とタイムアウト時の中止」節参照）。仕様書に根拠の無い、
#      この実装だけの判断。 ----
FDC_ABORT   = 0x4305   # 1バイト: 0=正常、非0=このFDCコマンドは中断済み
# ---- 第13版で追加。RECV完遂ごとにインクリメントする「run内で受け取った
#      バイト数」のカウンタ。REQ_HDR_CAPACITY到達後は格納だけ止めるが
#      カウンタ自体は0xFFで飽和するまで増え続ける（上のモジュールdocstring
#      「run境界駆動への書き換え」節参照）。 ----
RUN_LEN     = 0x4306   # 1バイト: 現在のrunで受け取ったバイト数（run開始時に0へ初期化）
# ---- 第29版で追加。交換#3ではSECTOR_BUFを直接RESP_ACTIVEへ接続せず、
#      内部状態1バイトの応答を先に返す。続く交換#4の2バイト要求が完了した
#      時点でSECTOR_BUFの256バイト応答を開始する。 ----
SECTOR_READY = 0x4307  # 1バイト: 交換#4へ渡す256バイトがSECTOR_BUFに準備済み
EXCHANGE3_RESPONSE_PENDING = 0x4308  # 1バイト: 交換#3の内部状態応答が未送信
ROUND0_RESPONSE_PENDING = 0x4309  # 1バイト: 起動系列最初の観測応答が未送信
EXCHANGE3_REQUEST_ACTIVE = 0x430A  # 1バイト: 第32版の2/5/1分節要求を受信中
BOOT_SINGLE_RESPONSE_COUNT = 0x430B  # 1バイト: 起動時交換順序（値に依存しない）
EXCHANGE3_OBSERVED_RESPONSE = 0xC0
ROUND0_OBSERVED_RESPONSE = 0x3F
# 後続単発応答は、m7hで確定した要求グループ→応答グループの決定関数。
# 要求グループのサイト種別はsubから観測できないが、観測9グループの要求内容は
# 相互にすべて異なるため、外部プロトコルとして見える要求内容の完全一致で実装する。
OBSERVED_SINGLE_RESPONSE_BY_REQUEST = (
    ((0x00, 0x07), 0x3F),  # 要求グループ1 → 応答グループ1
    ((0x06,), 0x80),  # 要求グループ2 → 応答グループ2
    ((0x0B, 0x07, 0x5F, 0x00, 0x01), 0x77),  # 要求グループ3 → 応答グループ3
    ((0x17, 0x0F, 0x02, 0x01, 0x00, 0x00, 0x01, 0x06), 0xC0),  # 要求グループ4 → 応答グループ4
    ((0x02, 0x01, 0x00, 0x00, 0x02, 0x06), 0xC0),  # 要求グループ5 → 応答グループ4
    ((0x0B, 0x07, 0xEF, 0x00, 0x01), 0xEF),  # 要求グループ6 → 応答グループ5
    ((0x0B, 0x07, 0xEE, 0x00, 0x01), 0x00),  # 要求グループ7 → 応答グループ6
    ((0x17, 0x0F, 0x02, 0x01, 0x00, 0x03, 0x03, 0x06), 0xC0),  # 要求グループ8 → 応答グループ4
    ((0x02, 0x01, 0x00, 0x25, 0x0D, 0x06), 0xC0),  # 要求グループ9 → 応答グループ4
)
# TODO(仕様第30版): 挙動から再構成した観測値。意味未特定。
# 意味が判明した場合は、この定数を意味に基づくルール生成へ差し替える。
# ---- 第21版で追加したLAST_FDC_RESULT（FDC_INの最新結果バイトを保持し
#      SEND_DISPATCH_IDLE/IDLE_SEND_BRANCHへ渡すRAM）は、第22版で
#      両ラベルをFDC_SENSE_DRIVE_STATUS実発行構造へ戻したことで
#      使われなくなったため削除した（上のモジュールdocstring
#      「第22版で再々訂正」節参照）。 ----

ROM_SIZE = 0x2000      # DISK.ROM の上限（vendor memory.c: load_rom(...,0x2000,...)）


def build_subrom(break_response=False, break_dispatch_return=False,
                  break_run_continuation=False,
                  inject_spurious_sense_int=False,
                  break_sense_int_result_count=False,
                  break_fdc_timeout_reads_anyway=False,
                  disable_fdc_timeout_mark=False,
                  break_fixed_byte_cutoff=False):
    """break_response: 検証器（tools/verify_l3.sh）をわざと壊すためのフラグ。
    応答256バイトの先頭1バイトを1ビットだけ反転させる。verify_l3.sh の
    「わざと壊して検出できるか確認する」手順で使う。ここで壊す1ビットは
    ROM由来ではなく、自作の応答データに対する自己テスト用の変更。

    break_dispatch_return: 第9版で修正したバグ（RECV_BYTE/SEND_BYTEを
    1回終えてもIDLE_DISPATCHへ戻らず、8バイトヘッダ・256バイト応答を
    「一塊」として決め打ちしていた旧構造）を意図的に再現するフラグ。
    tools/verify_l3.sh の回帰テストが検出力を持つことを確認するためだけ
    に使う。既定（False）では新構造（プリミティブ1回ごとに
    IDLE_DISPATCHへ戻る）を使う。

    break_run_continuation: 第11版で修正したバグ（RECVを1回終えるたびに
    無条件でIDLE_DISPATCHへ戻り、そこで何も書かずに$FEを読みに行くだけ
    だったため、mainの継続SENDバイト(0F省略)がbit1=1を待ってスピンする
    局面で相互デッドロックしていた旧構造）を意図的に再現するフラグ。
    tools/verify_l3.sh の`--run-continuation-test`回帰テストが検出力を
    持つことを確認するためだけに使う。既定（False）では新構造（直ちに
    再武装してbit0/bit1をポーリングする、上のモジュールdocstring
    「run境界の判別」節参照）を使う。

    inject_spurious_sense_int: 起動時FDC初期化（batch1・batch2）が
    それぞれ自分のSENSE INTERRUPT STATUSで保留中の割り込みを使い切った
    直後（＝FDC側に保留中の割り込みが1件も無いことが保証できる時点）で
    SENSE INTERRUPT STATUS を1回よけいに呼ぶ。μPD765
    データシートの規定により、この状況では結果フェーズがST0(Invalid
    Command)の1バイトだけで終わり、通常の2バイト目（PCN）は来ない。
    tools/verify_l3.sh がこの状況を意図的に作り出し、FDC_SENSE_INTの
    結果バイト数の扱いを検証するためのフラグ。

    break_sense_int_result_count: FDC_SENSE_INTを「ST0のInterrupt Code
    フィールドを見ずに常に2バイト読む」旧実装（本版で修正した挙動）に
    戻す。inject_spurious_sense_intと組み合わせ、この場合に無いはずの
    2バイト目を待つ状態を作って検出力を確認するためだけに使う。

    break_fdc_timeout_reads_anyway: 第12版で修正したバグ（FDC_IN/FDC_OUT
    がタイムアウトした後、あるいは待たずに相手が既にフェーズを終えて
    いたことを検出した後も、そのまま$FBを読み書きしていた旧構造）を
    意図的に再現するフラグ。tools/verify_l3.shの回帰テストが検出力を
    持つことを確認するためだけに使う。既定（False）では新構造
    （タイムアウト／中止時は一切ポートに触れない）を使う。

    disable_fdc_timeout_mark: $F9（FDC_TIMEOUT_MARK）への書き込みを
    無効化する。このポートは公式subには存在しない診断専用のイベントで
    あり、適合テストに提出するROMでは立てるべきではない。既定（False）
    では有効（$F9への記録を残す）のまま。

    break_fixed_byte_cutoff: 第13版で修正したバグ（run境界〔bit1の
    観測〕ではなく、通算8バイト受け取ったことだけでrunを打ち切っていた
    旧構造）を意図的に再現するフラグ。m6k-mixed-divergence.md第10部が
    診断した「複数ラウンドに分かれた受信（例:2+1+5=8バイト）を1つの
    8バイトヘッダに取り違える」バグをそのまま再現する。
    tools/verify_l3.sh の`--fixed-byte-cutoff-test`回帰テストが検出力を
    持つことを確認するためだけに使う。既定（False）では新構造（run終了
    〔bit1観測〕まで受信を続け、run長で応答形式を判断する、上の
    モジュールdocstring「run境界駆動への書き換え」節参照）を使う。"""
    a = Asm(0x0000)

    # ====================================================================
    # リセットベクタ
    # ====================================================================
    a.di()
    a.ld_sp(STACK)
    # ポートC（$FF/$FE）に関する明示的なモード設定は行わない。
    # 旧版はここで `OUT $FF,0x99` という初期化を行っていたが、その値は
    # 仕様書のどこにも根拠が無い（1.12節が確定しているsubのOUT $FF値は
    # 08-0Eの7種のみで0x99は含まれない）。旧版の値は自作サブROM＋自作
    # 試験用mainドライバ同士を動かして辻褄合わせした結果であり、今回の
    # 見直しの対象そのものである。**仕様に無いので入れない。**
    a.jp("BOOT_HANDSHAKE")

    # ====================================================================
    # ハンドシェイク・プリミティブ（仕様書 1.15節。sub視点で確定した手順）
    #
    # sub は $FF にフェーズコードを書くだけで、$FE には一度も書き込まない
    # （仕様書6節10項）。$FE は相手(main)の$FF書き込みがハードウェア越しに
    # 見える読み取り専用の窓であり、sub 側コードはその値がどう作られるかに
    # 関与しない——ここが旧版（たすき掛け理論・OUT $FE直接書き込み）から
    # の最大の変更点。
    # ====================================================================

    # ---- IN $FE をポーリングし、指定のビットが確定条件を満たすまで待つ
    #      （第10版。仕様書1.19節。完全一致(CP)からビット判定(AND)へ
    #      置き換えた。want_set=Trueならビットが1になるまで、Falseなら
    #      0になるまでループする） ----
    for name, mask, want_set in (
        ("WAIT_FE_RECV_DATA_READY",   FE_BIT_RECV_DATA_READY,   FE_RECV_DATA_READY_WANT_SET),
        ("WAIT_FE_RECV_ACK_DONE",     FE_BIT_RECV_ACK_DONE,     FE_RECV_ACK_DONE_WANT_SET),
        ("WAIT_FE_SEND_RECV_READY",   FE_BIT_SEND_RECV_READY,   FE_SEND_RECV_READY_WANT_SET),
        ("WAIT_FE_SEND_ACK_DONE",     FE_BIT_SEND_ACK_DONE,     FE_SEND_ACK_DONE_WANT_SET),
        ("WAIT_FE_SEND_STATUS_CLEAR", FE_BIT_SEND_STATUS_CLEAR, FE_SEND_STATUS_CLEAR_WANT_SET),
    ):
        a.label(name)
        a.label(name + "_LOOP")
        a.in_port(P_PIO_C)
        a.and_a(mask)
        if want_set:
            a.jr_z(name + "_LOOP")    # ビットがまだ0ならループ続行
        else:
            a.jr_nz(name + "_LOOP")   # ビットがまだ1ならループ続行
        a.ret()

    # ---- RECV_BYTE: main の SEND を受け取る。結果は A ----
    # 仕様書1.15節「sub視点のRECVプリミティブ」の手順1〜7をそのまま。
    # 第11版で RECV_BYTE_ARMED を切り出した（run境界判別、上のdocstring
    # 「run境界の判別」節参照）。手順1(OUT $FF,0x0B)だけを呼び出し側が
    # 先に済ませている場合はRECV_BYTE_ARMEDへ直接入る。
    a.label("RECV_BYTE")
    a.out_imm(0xFF, PH_RECV_START_SET)      # 手順1: OUT $FF,0x0B
    a.label("RECV_BYTE_ARMED")              # 手順1を済ませた状態から始める入口
    a.call("WAIT_FE_RECV_DATA_READY")       # 手順2: 相手のデータ準備待ち(bit0=1)
    a.out_imm(0xFF, PH_RECV_START_CLR)      # 手順3: OUT $FF,0x0A
    a.in_port(P_PIO_A)                      # 手順4: IN $FC（main OUT $FDと対応）
    a.push_af()
    a.out_imm(0xFF, PH_RECV_ACK_SET)        # 手順5: OUT $FF,0x0D
    a.call("WAIT_FE_RECV_ACK_DONE")         # 手順6: 相手の受理解除待ち(bit0=0)
    a.out_imm(0xFF, PH_RECV_ACK_CLR)        # 手順7: OUT $FF,0x0C
    a.pop_af()
    a.ret()

    # ---- HDR_STORE_AND_CHECK: 受け取ったバイト(A)をREQ_HDRへ格納し、
    #      RUN_LEN（runで受け取った通算バイト数）を進める。
    #      第11版では「Z=1ならREQ_HDR+8に到達」という8バイト固定の
    #      セマンティクスを持っていたが、第13版でrun境界駆動に書き換えた
    #      ため不要になった——runがいつ終わるかはRUN_LENの値ではなく
    #      bit1の観測で決める（呼び出し側、RECV_DISPATCH参照）。ここは
    #      「格納して数える」だけのサブルーチンに縮小した。
    #      REQ_HDR_CAPACITY（16バイト）に達したら以降は格納しない
    #      （HDR_PTRは進めない）が、RUN_LENのカウント自体は0xFFで
    #      飽和するまで続ける——run長がバッファ容量を超えても受信は
    #      止めず、呼び出し側が完成したrunを分類できるようにする
    #      （上のモジュールdocstring「run境界駆動への書き換え」節参照）。
    #      第11版から変わらず、run境界判別ループから複数箇所で呼ぶため
    #      切り出している（二重実装しない）。 ----
    a.label("HDR_STORE_AND_CHECK")
    a.push_af()                       # 受け取ったバイトを退避
    a.ld_a_mem(RUN_LEN)
    a.cp_n(REQ_HDR_CAPACITY)
    a.jr_nc("_hdr_store_skip")        # RUN_LEN >= CAPACITY: もう格納しない
    a.pop_af()
    a.push_af()
    a.ld_hl_mem(HDR_PTR)
    a.ld_hl_a()
    a.inc_hl()
    a.ld_mem_hl(HDR_PTR)
    a.label("_hdr_store_skip")
    a.pop_af()                        # スタック平衡のため復元（以降Aは未使用）
    a.ld_a_mem(RUN_LEN)
    a.cp_n(0xFF)
    a.jr_z("_hdr_run_len_done")       # 0xFFで飽和、これ以上は増やさない
    a.inc_a()
    a.ld_mem_a(RUN_LEN)
    a.label("_hdr_run_len_done")
    a.ret()

    # ---- SEND_BYTE: main の RECV に応答して1バイト送る。引数は A ----
    # 仕様書1.15節「sub視点のSENDプリミティブ」の手順1〜6をそのまま。
    # 0x0F/0x0E相当の書き込みは4条件で一度も観測されなかった（1.15節）ので
    # ここでは書かない。
    a.label("SEND_BYTE")
    a.push_af()
    a.call("WAIT_FE_SEND_RECV_READY")       # 手順1: 相手の受信準備待ち(bit1=1)
    a.pop_af()
    a.out_a(P_PIO_B)                        # 手順2: OUT $FD（main IN $FCと対応）
    a.out_imm(0xFF, PH_SEND_DATA_SET)       # 手順3: OUT $FF,0x09
    a.call("WAIT_FE_SEND_ACK_DONE")         # 手順4: 相手の受理確認待ち(bit2=1)
    a.out_imm(0xFF, PH_SEND_DATA_CLR)       # 手順5: OUT $FF,0x08
    a.call("WAIT_FE_SEND_STATUS_CLEAR")     # 手順6: ビット判定へ変更(第10版、bit2=0)
    # ↑ 第9版までは「境界的な待ち」として単発読み捨てだった。仕様書1.19節
    # （定常サイトの再解析）により、待ちの終了条件自体はbit2=0で単一ビット
    # 説明できることが確定した——1.15節の「単一の固定値読みではない」と
    # いう記述はこの点を訂正する。終了後に何を返すか（結果値のbit1/bit3
    # による後続分岐）はここでは使わない。呼び出し元(IDLE_DISPATCH)が
    # 改めて$FEを読んで次の動作を決めるため、読み捨ててよい。
    a.ret()

    # ---- SEND_BOOT_SINGLE_TRACKED: 起動時の単発応答を1件送り、交換順序を
    #      数える。第32版1.25節の分節開始は要求値ではなく、交換#0〜#2の
    #      3応答を完遂したという外部構造だけで決める。引数Aは送信値。 ----
    a.label("SEND_BOOT_SINGLE_TRACKED")
    a.push_af()
    a.ld_a_mem(BOOT_SINGLE_RESPONSE_COUNT)
    a.inc_a()
    a.ld_mem_a(BOOT_SINGLE_RESPONSE_COUNT)
    a.cp_n(3)
    a.jr_nz("_boot_single_track_done")
    a.ld_hl_imm(REQ_HDR)
    a.ld_mem_hl(HDR_PTR)
    a.ld_a(0x00)
    a.ld_mem_a(RUN_LEN)
    a.ld_a(0x01)
    a.ld_mem_a(EXCHANGE3_REQUEST_ACTIVE)
    a.label("_boot_single_track_done")
    a.pop_af()
    a.call("SEND_BYTE")
    a.ret()

    # ====================================================================
    # 起動順序（仕様書 1.16節。4条件で1バイトも違わず一致した手順を
    # そのまま再現する）。
    #
    #   OUT $F7,0x08 → OUT $FF,0x91 → IN $FE(単発)×2 →
    #   RECVプリミティブ1回(応答のSENDは行わない) →
    #   OUT $F8,0x05 → OUT $F8,0xFF → FDC初期化
    #
    # 手順3〜4の単発IN $FEの意味論・手順5で受け取るバイトの用途は
    # 未確定（仕様書3節）。値そのものは確定しているので、mainが外部
    # インタフェースとして要求している可能性を考え、観測どおり再現する
    # （推測ではなく観測の再現。仕様書6節11項）。
    #
    # 6節12項（判別条件は未確定）に従い、手順5で受け取ったバイトの値を
    # 見て分岐すること（推測によるディスパッチ）はしない——結果は捨てる。
    # ====================================================================
    a.label("BOOT_HANDSHAKE")
    a.out_imm(P_STROBE, BOOT_F7_VALUE)     # 手順1: OUT $F7,0x08
    a.out_imm(0xFF, BOOT_FF_VALUE)         # 手順2: OUT $FF,0x91
    a.in_port(P_PIO_C)                     # 手順3: IN $FE（単発、読み捨て）
    a.in_port(P_PIO_C)                     # 手順4: IN $FE（単発、読み捨て）
    a.call("RECV_BYTE")                    # 手順5: RECVプリミティブ1回（応答なし）
    a.out_imm(P_TC, BOOT_F8_VALUE_1)       # 手順6: OUT $F8,0x05
    a.out_imm(P_TC, BOOT_F8_VALUE_2)       # 手順7: OUT $F8,0xFF
    a.call("FDC_SPECIFY")                  # 手順8: FDC初期化開始
    # ---- 仕様書1.22節（第16版〜第19版）で確定した起動時FDC初期化の
    #      batch1〜7を再現する。ドライブ割り当て（1.22節・
    #      `docs/notes/m6r-specify-vs-seek.md`）: batch1/2/3=ドライブ0、
    #      batch4/5/6=ドライブ1、batch7=ドライブ2。第18版で
    #      `FDC_RECALIBRATE`/`FDC_SEEK`をドライブ番号引数化(E)した
    #      ことで、旧版がドライブ0決め打ちのため見送っていたbatch3以降
    #      を実装できるようになった。
    #      batch1: SPECIFY+RECALIBRATE+SENSE INTERRUPT STATUS
    #      （write=6バイト・read=2バイト）。FDC_RECALIBRATEは内部で
    #      FDC_SENSE_INTまで呼ぶ既存ルーチン。直後の単発`OUT $F8,0x07`は
    #      1.22節で確認した「三つ組みの1バイト目のみ、$F7/IN $F8を
    #      伴わない簡略形」をそのまま再現する（1.21節のFDC_TC
    #      サブルーチンは使わない——あちらは`OUT $F7`/`IN $F8`まで
    #      含む完全な三つ組み用）。
    a.ld_e(0x00); a.call("FDC_RECALIBRATE")   # ドライブ0
    a.out_imm(P_TC, FDC_TC_VALUE)          # 単発TC（$F7/IN $F8は伴わない）
    #      batch2: SEEK+SENSE INTERRUPT STATUS（write=4バイト・
    #      read=2バイト、ドライブ0）。第17版（`docs/notes/
    #      m6r-specify-vs-seek.md`）でSPECIFYではなくSEEKと確定した
    #      ——MSR($FA)のSeek Busyビット（対照群RECALIBRATE=batch3/4/6/7で
    #      先に妥当性確認済み）が、batch2の最終コマンドバイト送信後に
    #      ドライブ0分立っており、SPECIFYは決してこのビットを立てない
    #      ため。目標シリンダは`0x00`固定（任意値でよい）: 同ノート5節の
    #      とおり、この結果はmainへ渡らずsub内部で消費され、かつ直後の
    #      RECALIBRATE（batch3、ドライブ0を無条件にトラック0へ戻す）で
    #      上書きされるため、値は区間の最終観測可能状態に影響しない。
    a.ld_e(0x00); a.ld_a(0x00); a.call("FDC_SEEK")   # ドライブ0, シリンダ0
    #      batch2の直後にはTCを発行しない。1.22節第19版（m6s、既存ログの
    #      seq番号レベル再解析で実走診断が反証）で訂正済み：TCが来るのは
    #      batch1・batch4の直後のみで、batch2の直後には来ない。旧版
    #      （第16〜18版）はTCの出現順序（区間内で1番目・2番目に見つかる
    #      こと）とbatch番号（1番目・2番目のbatch）を取り違えていた。
    if inject_spurious_sense_int:
        # 検出力確認用（tools/verify_l3.sh --break-sense-int-count系）。
        # batch1（RECALIBRATE）・batch2（SEEK）はどちらも内部で
        # FDC_SENSE_INTまで呼び、その時点で保留中だった割り込みを
        # 使い切っている。この時点では、FDC側に保留中の割り込みは1件も
        # 無いことが構造上保証できる。ここでさらにSENSE INTERRUPT
        # STATUSを呼ぶと、μPD765データシートの規定により結果フェーズは
        # ST0(Invalid Command)の1バイトのみで終わる。
        a.call("FDC_SENSE_INT")
    #      batch3: 1.22節第19版が確定したとおりTCを発行しない
    #      （RECALIBRATE、ドライブ0、write=3バイト・read=2バイト）。
    a.ld_e(0x00); a.call("FDC_RECALIBRATE")   # ドライブ0
    #      batch4: RECALIBRATE（ドライブ1）。1.22節第19版で訂正した
    #      とおり、この直後にTCが来る（旧版がbatch2直後としていたのは
    #      誤りで、正しくはbatch4直後。単発TC、$F7/IN $F8は伴わない）。
    a.ld_e(0x01); a.call("FDC_RECALIBRATE")   # ドライブ1
    a.out_imm(P_TC, FDC_TC_VALUE)          # 単発TC（batch4直後、1.22節第19版）
    #      batch5〜7: TCは発行しない（1.22節第19版でbatch1・4以外に
    #      TCが無いことを確定済み）。
    #      batch5: SEEK（ドライブ1、write=4バイト・read=2バイト）。
    #      目標シリンダはbatch2と同じ理由で`0x00`固定（直後のbatch6
    #      RECALIBRATEが無条件にトラック0へ戻すため、値は区間の最終
    #      観測可能状態に影響しない。仕様書1.22節第17版）。
    a.ld_e(0x01); a.ld_a(0x00); a.call("FDC_SEEK")   # ドライブ1, シリンダ0
    #      batch6: RECALIBRATE（ドライブ1）。
    a.ld_e(0x01); a.call("FDC_RECALIBRATE")   # ドライブ1
    #      batch7: RECALIBRATE（ドライブ2）。
    a.ld_e(0x02); a.call("FDC_RECALIBRATE")   # ドライブ2
    a.jp("MAIN_LOOP")

    # ====================================================================
    # FDC（μPD765 相当。$FA=ステータス、$FB=データ。公開仕様に基づく実装）
    # ====================================================================

    # ---- FDCステータス待ちのタイムアウト回数。μPD765データシートには
    #      根拠が無い、この実装だけの判断（下のFDC_IN/FDC_OUTのdocstring
    #      参照）。0xFFFF回のポーリングでも実機を模す時間ではなく、単に
    #      「有限回で必ず抜ける」ことだけを保証する値として選んでいた
    #      （前版）。第12版で0x0400へ大幅に縮小した。理由: 中断フラグ
    #      （FDC_ABORT）の導入により、1つのFDCコマンド呼び出し列の中で
    #      実際にポーリングしてタイムアウトし得るのは最大1回だけになった
    #      （一度中断すると残りのFDC_IN/FDC_OUTは即座に戻り、ポートに
    #      触れない）。したがって上限を小さくしても「タイムアウトが繰り
    #      返し発生して測定イベント上限を食い潰す」問題は再発しない一方、
    #      正常な待ち時間（実測上、数百回程度のポーリングで揃うことが
    #      多い）を誤って打ち切らない余裕は残すため、0xFFFFより十分小さく
    #      かつ0を大きく上回る値として選んだ。実機のタイミングを表す値
    #      ではない。 ----
    FDC_WAIT_TIMEOUT = 0x0400

    # ---- タイムアウト発生を記録するだけの補助ルーチン。
    #      仕様書のどこにも根拠が無い、実装上の判断（このファイルだけの
    #      追加。P_FDC_TIMEOUT_MARK のdocstring参照）。AFのみ使い、
    #      呼び出し元のDE/HL/BCには触れない。
    #      disable_fdc_timeout_mark=True の場合は $F9 への書き込みを
    #      行わない（$F9は公式subに存在しない診断専用ポートであり、
    #      適合テストへ提出するROMではこのイベント自体を出さない選択肢
    #      を用意する）。 ----
    a.label("FDC_TIMEOUT_MARK")
    if not disable_fdc_timeout_mark:
        a.push_af()
        a.out_imm(P_FDC_TIMEOUT_MARK, FDC_TIMEOUT_MARK_VALUE)
        a.pop_af()
    a.ret()

    # ---- FDCコマンド1つ分の呼び出し列の先頭で FDC_ABORT をクリアする
    #      補助ルーチン（第12版で追加）。FDC_SPECIFY/FDC_SENSE_INT/
    #      FDC_RECALIBRATE/FDC_SENSE_DRIVE_STATUS/FDC_SEEK/
    #      FDC_READ_SECTORの各入口で呼ぶ。呼ばないと、過去に別のFDC
    #      コマンドで一度中断したフラグが残ったまま次のコマンドも
    #      即座に中断扱いになってしまう。AFのみ使う。 ----
    a.label("FDC_BEGIN")
    a.push_af()
    a.ld_a(0x00)
    a.ld_mem_a(FDC_ABORT)
    a.pop_af()
    a.ret()

    # ---- TC三つ組み（仕様書1.21節、第15版）。呼び出し元がFDCコマンド
    #      バッチ（例: 1セクタ分のデータフェーズ＋結果フェーズ）を
    #      読み終えた後に呼ぶ。$F8はOUTで送る（P_TCのdocstring参照。
    #      旧実装はここをINで読んでおり方向を取り違えていた）。
    #      個々のFDCコマンド呼び出し1回ごとに呼ぶものではない
    #      （どの単位がバッチかは未確定。仕様書3節・6節21項）。 ----
    a.label("FDC_TC")
    a.push_af()
    a.out_imm(P_TC, FDC_TC_VALUE)        # OUT $F8,0x07
    a.out_imm(P_STROBE, BOOT_F7_VALUE)   # OUT $F7,0x08
    a.in_port(P_TC)                      # IN $F8（単発、読み捨て。常に0xFF）
    a.pop_af()
    a.ret()

    # ---- FDC がホストへデータを渡す準備ができるまで待って IN する。
    #      第12版で全面書き直し（上のモジュールdocstring「FDC結果/
    #      コマンドフェーズの終了判定とタイムアウト時の中止」節参照）。
    #      **中止条件（いずれもタイムアウトを待たず、$FBに一切触れずに
    #      戻る）**:
    #        - 既にこのFDCコマンド呼び出し列内で中断済み（FDC_ABORT≠0）
    #        - μPD765/8272データシートの規定により、RQM=1かつDIO=0を
    #          観測した場合。これは「相手が待たずに結果/データフェーズを
    #          終えてコマンドフェーズへ戻った」ことを意味し、呼び出し側が
    #          期待していたバイトはもう無い（例: SENSE INTERRUPT STATUSを
    #          割り込み保留無しで呼んだ直後の2バイト目のように、期待した
    #          結果バイト数より少ないバイトしか無い場合）
    #        - FDC_WAIT_TIMEOUT回ポーリングしてもRQM=1にならない
    #      （旧実装はタイムアウト分岐と正常分岐が同じ着地点に合流して
    #      おり、タイムアウト後も無条件で$FBを読んでいた——これが
    #      ce3bd5b実走で観測された「タイムアウト直後にIN $FBを読む」
    #      挙動の原因） ----
    a.label("FDC_IN")
    a.push_de()
    a.ld_a_mem(FDC_ABORT)
    a.or_a()
    a.jr_nz("_fdc_in_aborted")     # 既に中断済み: ポートに触れず戻る
    a.ld_de_imm(FDC_WAIT_TIMEOUT)
    a.label("_fdc_in_wait")
    a.in_port(P_FDC_STAT)
    a.and_a(RQM | DIO)
    a.cp_n(RQM | DIO)
    a.jr_z("_fdc_in_ready")         # RQM=1,DIO=1: データレディ
    if not break_fdc_timeout_reads_anyway:
        a.cp_n(RQM)
        a.jr_z("_fdc_in_abort")     # RQM=1,DIO=0: フェーズは既に終わっている
    a.dec_de()
    a.ld_a_d()
    a.or_e()
    a.jr_nz("_fdc_in_wait")
    a.call("FDC_TIMEOUT_MARK")
    if break_fdc_timeout_reads_anyway:
        # 検出力確認用（tools/verify_l3.sh用）。ce3bd5b時点の旧挙動を
        # 再現する: タイムアウトしても中断せず、そのまま$FBを読みに行く。
        a.jr("_fdc_in_ready")
    a.label("_fdc_in_abort")
    a.ld_a(0x01)
    a.ld_mem_a(FDC_ABORT)
    a.label("_fdc_in_aborted")
    a.pop_de()
    a.ret()
    a.label("_fdc_in_ready")
    a.pop_de()
    a.in_port(P_FDC_DATA)
    # 第21版で追加したLAST_FDC_RESULTへの保持は、第22版でSEND_DISPATCH_IDLE
    # 側がFDC_SENSE_DRIVE_STATUS実発行構造へ戻り不要になったため削除した。
    a.ret()

    # ---- ホストから FDC へ1バイト送る（コマンド/パラメータ共通）。
    #      第12版で全面書き直し。考え方はFDC_INと対称:
    #        - 既に中断済みなら$FBに触れず戻る
    #        - RQM=1かつDIO=1（μPD765/8272データシートの規定で、コマンド
    #          バイトを受け付ける状態ではなく、読まれるべき結果データが
    #          残っている状態）を観測したら、書き込まずに即座に中断する
    #        - タイムアウトしたら書き込まずに中断する（旧実装は送ろうと
    #          していた値をタイムアウト後もそのままOUTしていた） ----
    a.label("FDC_OUT")               # 引数: A = 送る値
    a.push_af()
    a.push_de()
    a.ld_a_mem(FDC_ABORT)
    a.or_a()
    a.jr_nz("_fdc_out_aborted")
    a.ld_de_imm(FDC_WAIT_TIMEOUT)
    a.label("_fdc_out_wait")
    a.in_port(P_FDC_STAT)
    a.and_a(RQM | DIO)
    a.cp_n(RQM)
    a.jr_z("_fdc_out_ready")        # RQM=1,DIO=0: コマンド/パラメータを受付可能
    if not break_fdc_timeout_reads_anyway:
        a.cp_n(RQM | DIO)
        a.jr_z("_fdc_out_abort")    # RQM=1,DIO=1: 結果データが残っている食い違い
    a.dec_de()
    a.ld_a_d()
    a.or_e()
    a.jr_nz("_fdc_out_wait")
    a.call("FDC_TIMEOUT_MARK")
    if break_fdc_timeout_reads_anyway:
        a.jr("_fdc_out_ready")
    a.label("_fdc_out_abort")
    a.ld_a(0x01)
    a.ld_mem_a(FDC_ABORT)
    a.label("_fdc_out_aborted")
    a.pop_de()
    a.pop_af()
    a.ret()
    a.label("_fdc_out_ready")
    a.pop_de()
    a.pop_af()
    a.out_a(P_FDC_DATA)
    a.ret()

    # ---- SPECIFY（起動時に1回。SRT/HUT/HLT の値は公開仕様のパラメータで、
    #      ROM由来ではない。タイミング固定値は自由に選べる） ----
    a.label("FDC_SPECIFY")
    a.call("FDC_BEGIN")                 # このコマンドの中断フラグをクリア(第12版)
    a.ld_a(0x03); a.call("FDC_OUT")     # コマンド: SPECIFY
    a.ld_a(0xDF); a.call("FDC_OUT")     # SRT/HUT
    a.ld_a(0x02); a.call("FDC_OUT")     # HLT/ND
    a.ret()

    # ---- SENSE INTERRUPT STATUS。
    # μPD765/8272データシート: この結果フェーズのバイト数は固定2バイト
    # ではない。ST0（r0）のInterrupt Codeフィールド（bit7-6）が
    # 「Invalid Command」（10）の場合——このコマンドが発行された時点で
    # 保留中の（SEEK/RECALIBRATE完了による）割り込みが1件も無かった
    # 場合に該当する——結果フェーズはST0の1バイトのみで終わり、2バイト目
    # （PCN）は存在しない。呼ぶたびに機械的に2バイト読んでいた旧実装は、
    # この場合に来ないはずの2バイト目を待ち続けて無限スピンする
    # （FDC_IN側のタイムアウトはこれを止血するが、根本はここで直す）。
    # r0のIC field(bit7-6)を確認し、Invalid Command(10xxxxxx)でなければ
    # （＝正常に割り込みを拾えた場合）だけ2バイト目を読む。 ----
    a.label("FDC_SENSE_INT")
    a.call("FDC_BEGIN")                 # このコマンドの中断フラグをクリア(第12版)
    a.ld_a(0x08); a.call("FDC_OUT")
    a.call("FDC_IN")     # r0 = ST0
    if break_sense_int_result_count:
        # 検出力確認用（tools/verify_l3.sh --break-sense-int-count）:
        # 本版で修正する前の挙動（ST0の中身を見ずに無条件で2バイト目を
        # 読む）をそのまま再現する。
        a.call("FDC_IN")     # r1（本来存在しない場合がある）
    else:
        a.and_a(0xC0)         # ST0 bit7-6 = Interrupt Code field
        a.cp_n(0x80)          # 10 = Invalid Command（保留中の割り込み無し）
        a.jr_z("_fdc_sense_int_done")   # r1(PCN)は存在しない。読まない
        a.call("FDC_IN")     # r1 = PCN
        a.label("_fdc_sense_int_done")
    a.ret()

    # ---- RECALIBRATE（指定ドライブをトラック0へ）。
    #      引数: E = ドライブ番号(0-3)。第18版でドライブ番号引数化した
    #      （仕様書1.22節・`docs/notes/m6r-specify-vs-seek.md`が
    #      batch1/2/3をドライブ0、batch4/5/6をドライブ1、batch7を
    #      ドライブ2と確定させたが、旧実装はドライブ0決め打ちで
    #      batch3以降を再現できなかった）。
    #      μPD765/8272データシート（公開仕様）: RECALIBRATEコマンド
    #      フェーズ第2バイトの下位2ビット(US1,US0)がドライブ選択、
    #      bit2(HD)がヘッド選択。本実装はヘッド0のみを扱うため、
    #      第2バイトはE(ドライブ番号)をそのまま使う。
    #      Eはこのファイルの他のFDCサブルーチン(FDC_BEGIN/FDC_OUT/
    #      FDC_IN/FDC_SENSE_INT)がいずれもDEを保存して戻るため、
    #      呼び出しをまたいでも壊れない。 ----
    a.label("FDC_RECALIBRATE")
    a.call("FDC_BEGIN")                 # このコマンドの中断フラグをクリア(第12版)
    a.ld_a(0x07); a.call("FDC_OUT")     # コマンド: RECALIBRATE
    a.ld_a_e(); a.call("FDC_OUT")       # unit=E(ドライブ番号), head=0
    a.call("FDC_SENSE_INT")
    a.ret()

    # ---- SENSE DRIVE STATUS（第9版で追加。仕様書6節14項）。
    # μPD765/8272 系データシートに定義されたコマンド0x04。他のコマンドと
    # 違い割り込み待ち・実行フェーズ（データ転送）を持たず、コマンド
    # フェーズ2バイト（コマンド＋unit/head）を送った直後に結果フェーズ
    # 1バイト（ST3）を返す、もっとも単純な「コマンド→結果」の往復。
    # 呼ぶたびに毎回ホスト側の状態（RECALIBRATE/SEEK/READ実行中かどうか）
    # に関わらず一意に定義された結果が返るため、他のFDCシーケンスの
    # 副作用を気にせず独立に呼べる。結果（ST3）はAレジスタに残す。
    a.label("FDC_SENSE_DRIVE_STATUS")
    a.call("FDC_BEGIN")                 # このコマンドの中断フラグをクリア(第12版)
    a.ld_a(0x04); a.call("FDC_OUT")     # コマンド: SENSE DRIVE STATUS
    a.ld_a(0x00); a.call("FDC_OUT")     # unit=0, head=0
    a.call("FDC_IN")                    # 結果フェーズ: ST3（1バイト、Aに残る）
    a.ret()

    # ---- SEEK（引数: E=ドライブ番号(0-3), A=目的シリンダ）。
    #      第18版でドライブ番号引数化（FDC_RECALIBRATEと同じ根拠・
    #      同じビット割り当て。上のFDC_RECALIBRATEのコメント参照）。----
    a.label("FDC_SEEK")
    a.push_af()
    a.call("FDC_BEGIN")                 # このコマンドの中断フラグをクリア(第12版)
    a.ld_a(0x0F); a.call("FDC_OUT")     # コマンド: SEEK
    a.ld_a_e(); a.call("FDC_OUT")       # unit=E(ドライブ番号), head=0
    a.pop_af();  a.call("FDC_OUT")      # 目的シリンダ
    a.call("FDC_SENSE_INT")
    a.ret()

    # ---- READ DATA 1セクタ（256バイト固定・N=1）。
    #      引数: (REQ_C)=シリンダ, (REQ_R)=セクタ番号。
    #      結果は SECTOR_BUF の256バイトに入る。 ----
    a.label("FDC_READ_SECTOR")
    a.call("FDC_BEGIN")                 # このコマンドの中断フラグをクリア(第12版)
    # コマンド: READ DATA。MF(bit6)=1 必須——このハーネスの FDC は
    # sec_buf.density(セクタのID部の密度)と command.MF の一致を見る
    # （vendor src/fdc.c sector_density_mismatch()）。
    # DISK_DENSITY_DOUBLE=0x00（tools/make_l3_testdisk.py の density=0x00
    # 相当）に対しては MF=1（倍密度コマンド）が要る。実測して確かめた
    # （最初 MF=0 で送っていたら Missing Address Mark で毎回失敗した）。
    a.ld_a(0x46); a.call("FDC_OUT")
    a.ld_a(0x00); a.call("FDC_OUT")     # unit=0, head=0
    a.ld_hl_imm(REQ_HDR + 3); a.ld_a_hl(); a.call("FDC_OUT")   # C = シリンダ(byte3)
    a.ld_a(0x00); a.call("FDC_OUT")     # H = 0
    a.ld_hl_imm(REQ_HDR + 4); a.ld_a_hl(); a.call("FDC_OUT")   # R = セクタ(byte4)
    a.ld_a(0x01); a.call("FDC_OUT")     # N = 1 (256バイト/セクタ)
    a.ld_hl_imm(REQ_HDR + 4); a.ld_a_hl(); a.call("FDC_OUT")   # EOT = R（このセクタで終わり）
    a.ld_a(0x2A); a.call("FDC_OUT")     # GPL
    a.ld_a(0xFF); a.call("FDC_OUT")     # DTL（N!=0なので無視される）

    # データ転送: 256バイト（B=0 を DJNZ で 256 回まわす定石）。
    # FDC_IN は A を破壊するので、ループカウンタ(B)・書き込み先(HL)は
    # 呼び出しの前後で自然に保持される（FDC_IN/FDC_OUT は BC/HL に触れない）。
    a.ld_hl_imm(SECTOR_BUF)
    a.ld_b(0x00)
    a.label("_read_loop")
    a.call("FDC_IN")
    a.ld_hl_a()          # (HL) <- A
    a.inc_hl()
    a.djnz("_read_loop")

    # 結果フェーズ（ST0,ST1,ST2,C,H,R,N の7バイト）は読み捨てる
    for _ in range(7):
        a.call("FDC_IN")
    # 第15版で訂正: 旧実装はここで(結果フェーズを読む前に) IN $F8 で
    # 「TCを送ろうとして」いたが、方向(IN)も位置(結果フェーズの前)も
    # 誤りだった。仕様書1.21節: 公式subは256+7=263バイト(データ+結果)を
    # 読み終えた後にOUT $F8,0x07(TC)->OUT $F7,0x08->IN $F8の三つ組みを
    # 送る。
    a.call("FDC_TC")
    a.ret()

    if break_dispatch_return:
        # ====================================================================
        # 第9版で修正したバグをわざと再現する版（tools/verify_l3.sh の
        # 回帰テストが検出力を持つことを確認するためだけに使う。上の
        # build_subrom() docstring・第9版のモジュールdocstring参照）。
        # RECV_BYTE/SEND_BYTEを1回終えてもIDLE_DISPATCHへ戻らず、
        # 8バイトヘッダ・256バイト応答を「一塊」として決め打ちしていた
        # 旧構造をそのまま復元する。
        # ====================================================================
        a.label("MAIN_LOOP")
        a.ld_e(0x00); a.call("FDC_RECALIBRATE")   # ドライブ0（第18版でドライブ番号引数化。意味は変えない）
        a.label("REQ_LOOP")

        a.label("IDLE_DISPATCH")
        a.in_port(P_PIO_C)
        a.ld_b_a()                       # 元の値をBに退避(AND破壊対策)
        a.and_a(FE_BIT_IDLE_RECV)        # bit3=1なら確定済みのRECV分岐(第10版)
        a.jr_nz("REQ_HEADER_RECV")
        a.ld_a_b()
        a.and_a(FE_BIT_IDLE_SEND)        # bit1=1なら未確定のSEND分岐(判定方式のみビット化)
        a.jr_nz("IDLE_SEND_BRANCH")
        a.jr("IDLE_DISPATCH")

        a.label("IDLE_SEND_BRANCH")
        # 第22版で下のSEND_DISPATCH_IDLEと揃えて再訂正: 第21版の
        # LAST_FDC_RESULT保持方式をやめ、5adf82e相当のFDC_SENSE_DRIVE_STATUS
        # 実発行に戻す（下のSEND_DISPATCH_IDLEのdocstring参照。この分岐は
        # --break-dispatch-return の回帰専用でありディスパッチ復帰の有無
        # だけを検出対象にしているため、送る値自体はどちらでもよいが
        # 本番構造と揃える）。
        a.call("FDC_SENSE_DRIVE_STATUS")
        a.call("SEND_BYTE")
        a.jr("IDLE_DISPATCH")

        a.label("REQ_HEADER_RECV")
        a.ld_hl_imm(REQ_HDR)
        a.ld_b(8)
        a.label("_hdr_loop")
        a.call("RECV_BYTE")
        a.ld_hl_a()
        a.inc_hl()
        a.djnz("_hdr_loop")

        a.ld_hl_imm(REQ_HDR + 3)
        a.ld_a_hl()
        a.ld_e(0x00)          # ドライブ0（第18版でドライブ番号引数化。意味は変えない）
        a.call("FDC_SEEK")

        a.call("FDC_READ_SECTOR")
        if break_response:
            a.ld_hl_imm(SECTOR_BUF)
            a.ld_a_hl()
            a.db(0xEE, 0x01)
            a.ld_hl_a()
        a.ld_hl_imm(SECTOR_BUF)
        a.ld_b(0x00)
        a.label("_resp_loop")
        a.ld_a_hl()
        a.call("SEND_BYTE")
        a.inc_hl()
        a.djnz("_resp_loop")

        a.jr("REQ_LOOP")

        return a

    # ====================================================================
    # メインループ（仕様書 1.11・1.23節: 交換#3/#4の状態機械）
    #
    #   02 01 00 <b3> <b4> 06 12 60
    #
    # byte0/1/2/5/6/7 は全件で固定（1.11節）。本実装はこれらを検査しない。
    # 第29版では固定8バイト要求を256バイト応答へ直接結び付けず、交換#3の
    # 1バイト内部状態応答を挟んだ後、交換#4の2バイト要求で実データ応答を
    # 開始する。
    #
    # 第9版で修正: 8バイトヘッダ受信・256バイト応答送信を「一塊」として
    # 扱わない。RAM上の進行状態（HDR_PTR/RESP_PTR/RESP_ACTIVE）を使い、
    # RECV_BYTE/SEND_BYTEを1回呼ぶたびに必ずIDLE_DISPATCHへ戻る
    # （上のモジュールdocstring「プリミティブ1回ごとにディスパッチャへ
    # 戻る」参照）。
    # ====================================================================
    a.label("MAIN_LOOP")
    # 進行状態を初期化する（起動直後の1回だけ）。第13版でRUN_LENを追加。
    a.ld_hl_imm(REQ_HDR)
    a.ld_mem_hl(HDR_PTR)
    a.ld_a(0x00)
    a.ld_mem_a(RESP_ACTIVE)
    a.ld_mem_a(RUN_LEN)
    a.ld_mem_a(SECTOR_READY)
    a.ld_mem_a(EXCHANGE3_RESPONSE_PENDING)
    a.ld_mem_a(EXCHANGE3_REQUEST_ACTIVE)
    a.ld_mem_a(BOOT_SINGLE_RESPONSE_COUNT)
    a.ld_a(0x01)
    a.ld_mem_a(ROUND0_RESPONSE_PENDING)
    # 第21版で追加したLAST_FDC_RESULTの起動時初期化は、第22版でこの
    # RAM機構自体を削除したため不要になった。
    # ---- ここにあった`a.ld_e(0x00); a.call("FDC_RECALIBRATE")`(ドライブ0)は
    #      第20版で削除した。由来: 最初の実装(2491385)時点ではBOOT_HANDSHAKE
    #      に起動時FDC初期化が無く、ここがFDC初期化の唯一の箇所だった。
    #      その後1.22節（第16〜19版、batch1〜7）でBOOT_HANDSHAKE側に
    #      起動時FDC初期化区間[event 15,112)を実装したが、この古い呼び出しは
    #      消し忘れて残っていた。1.22節はこの区間がbatch1〜7（RECALIBRATE
    #      ドライブ0×2＋ドライブ1×2＋ドライブ2×1・SEEKドライブ0/1×1ずつ）で
    #      尽きること、区間終了直後は1.17節のアイドル待ち（$FE/$FF
    #      ハンドシェイク）へ遷移することを確定させており、MAIN_LOOP入口での
    #      追加RECALIBRATEは仕様上不要。混成ROM実走診断（19:23版）でも、
    #      基準側は分岐点93(IN $FB, batch7のSENSE INT完了)の直後の分岐点94で
    #      IN $FEへ進むのに対し、この行が残っていた混成subは分岐点94で
    #      IN $FA（FDC_RECALIBRATEのMSRポーリング開始）を出し、以降
    #      OUT $FB×3（RECALIBRATEコマンド2バイト+SENSE INTERRUPT STATUS
    #      コマンド1バイト）を続けて基準から外れていた。基準に合わせて削除。

    # ---- アイドル判別（上のdocstring「アイドル判別」節を参照） ----
    # $FF へ何も書かずに $FE を読み、どちらの側かが確定するまで待つ。
    # bit3=1 は確定済みの条件（1.17・1.19節「アイドル待ち」）、bit1=1 は
    # 1.15節SEND手順1と同じビットからの類推であり未確定（docstring参照）。
    # 第10版で完全一致(CP)からビット判定(AND)へ置き換えた。
    # どのプリミティブ(RECV_DISPATCH/SEND_DISPATCH)を1回終えても、
    # 必ずここへ戻ってくる——次に何をするかは毎回ここが決める。
    a.label("IDLE_DISPATCH")
    a.in_port(P_PIO_C)
    a.ld_b_a()                       # 元の値をBに退避(AND破壊対策)
    a.and_a(FE_BIT_IDLE_RECV)        # bit3=1なら確定済みのRECV分岐
    a.jr_nz("RECV_DISPATCH")
    a.ld_a_b()
    a.and_a(FE_BIT_IDLE_SEND)        # bit1=1なら未確定のSEND分岐(判定方式のみビット化)
    a.jp_nz("SEND_DISPATCH")
    a.jr("IDLE_DISPATCH")

    # ---- RECV_DISPATCH: 1つのrun（mainがsubへ送り手であり続ける区間）を
    #      最初から最後まで処理し、必ずIDLE_DISPATCHへ戻る。
    #
    #      第13版でrun境界駆動に書き換えた（m6k-mixed-divergence.md第10部
    #      の診断、上のモジュールdocstring「run境界駆動への書き換え」節
    #      参照）。**runの終端は「通算8バイト受け取ったこと」ではなく
    #      「bit1=1（相手がSEND待ちに転じたこと）を先に観測したこと」で
    #      決める。** bit0が先に立ち続ける限り、8バイトを超えても
    #      受信を続ける（1.18節: ラウンドは1〜12バイトと幅がある）。
    #      第29版では交換状態も見る:
    #        - 交換#3の固定8バイト要求: FDC実データをSECTOR_BUFへ準備するが
    #          RESP_ACTIVEには接続せず、内部状態1バイト応答を保留する
    #        - 続く交換#4の2バイト要求: 準備済みSECTOR_BUFをRESP_ACTIVEへ
    #          接続し、256バイト応答を開始する
    #      これにより「交換#3で実データ先頭を返す」旧構造を除去する。 ----
    a.label("RECV_DISPATCH")
    # run開始: 進行状態を初期化する。RESP_ACTIVEもここで明示的にクリア
    # する——応答送信の途中でmainが送り手へ戻った場合の残留状態を断ち、
    # 次のrunを汚さないようにするため(break_fixed_byte_cutoff時はこの
    # 初期化自体を省き、m6k第10部が診断した「ラウンド境界を無視して
    # 通算で貯め込む」旧構造を忠実に再現する——HDR_PTR/RUN_LENは
    # MAIN_LOOP起動時の1回と、8バイト到達後の巻き戻ししか行わない)。
    if not break_fixed_byte_cutoff:
        # 第32版1.25節: 交換#3の要求は2/5/1境界をまたいで同じ8件を
        # 蓄積する。アイドル復帰によるRECV_DISPATCH再入では状態を消さない。
        a.ld_a_mem(EXCHANGE3_REQUEST_ACTIVE)
        a.or_a()
        a.jr_nz("_recv_dispatch_state_ready")
        a.ld_hl_imm(REQ_HDR)
        a.ld_mem_hl(HDR_PTR)
        a.ld_a(0x00)
        a.ld_mem_a(RUN_LEN)
        a.ld_mem_a(RESP_ACTIVE)
        a.label("_recv_dispatch_state_ready")
    a.call("RECV_BYTE")               # A = 受け取ったバイト
    a.call("HDR_STORE_AND_CHECK")     # REQ_HDRへ格納しRUN_LENを進める

    if not break_fixed_byte_cutoff:
        # 第32版1.25節の分節境界。値ではなく、起動時交換順序で立てた
        # EXCHANGE3_REQUEST_ACTIVEと観測件数だけを使う。
        a.ld_a_mem(EXCHANGE3_REQUEST_ACTIVE)
        a.or_a()
        a.jr_z("_recv_dispatch_after_first_progress")
        a.ld_a_mem(RUN_LEN)
        a.cp_n(2)
        a.jp_z("IDLE_DISPATCH")
        a.cp_n(7)
        a.jp_z("_exchange3_prepare_sector")
        a.cp_n(8)
        a.jp_z("_exchange3_request_done")
        a.label("_recv_dispatch_after_first_progress")

    if break_fixed_byte_cutoff:
        # tools/verify_l3.sh の`--fixed-byte-cutoff-test`回帰テストが
        # 検出力を持つことを確認するためだけに使う（上のbuild_subrom()
        # docstring参照）。第13版で修正した旧構造（bit1を見ずHDR_PTRが
        # REQ_HDR+8に達したことだけで打ち切る）をそのまま復元する。
        # 複数ラウンドに分かれた受信(例: 2+1+5=8バイト)が1つの8バイト
        # ヘッダに取り違えられるバグ(m6k-mixed-divergence.md第10部)を
        # 再現する。
        a.ld_hl_mem(HDR_PTR)
        a.ld_de_imm(REQ_HDR + 8)
        a.or_a()
        a.sbc_hl_de()
        a.jr_z("_recv_dispatch_hdr_done")

    if break_run_continuation:
        # 第11版で修正したバグをわざと再現する版（tools/verify_l3.sh の
        # `--run-continuation-test`回帰テストが検出力を持つことを確認
        # するためだけに使う。上のbuild_subrom() docstring参照）。
        # 無条件でIDLE_DISPATCHへ戻り、そこで何も書かずに$FEを読みに
        # 行くだけの旧構造をそのまま復元する。
        # （RECV_DISPATCHが大きくなりIDLE_DISPATCHから遠いため、
        # 相対ジャンプ(JR)ではなく絶対ジャンプ(JP)を使う）
        a.jp("IDLE_DISPATCH")
    else:
        # ---- run継続ループ：bit0/bit1同時ポーリング。仕様書1.20節・
        #      6節16項、上のモジュールdocstring「run境界の判別」節
        #      参照。使うビットは第11版から変えていない。 ----
        a.label("_recv_dispatch_continue")
        a.out_imm(0xFF, PH_RECV_START_SET)    # RECVプリミティブ手順1を先出しで実行
        a.label("_recv_dispatch_poll")
        a.in_port(P_PIO_C)
        a.ld_b_a()                            # 元の値をBに退避(AND破壊対策)
        a.and_a(FE_BIT_SEND_RECV_READY)       # bit1: 相手がSEND待ちに転じた(run終了)合図
        if break_fixed_byte_cutoff:
            a.jp_nz("IDLE_DISPATCH")          # 旧構造の再現: run長を見ず即座に委ねる（遠方分岐のためJP）
        else:
            a.jr_nz("_recv_dispatch_run_done")    # 新構造: run終了。RUN_LENで応答形式を判断
        a.ld_a_b()
        a.and_a(FE_BIT_RECV_DATA_READY)       # bit0: 相手が続けてデータを書いた(runが続いている)合図
        a.jr_z("_recv_dispatch_poll")
        a.call("RECV_BYTE_ARMED")             # 武装済みの状態から手順2〜7を続ける
        a.call("HDR_STORE_AND_CHECK")
        if break_fixed_byte_cutoff:
            a.ld_hl_mem(HDR_PTR)
            a.ld_de_imm(REQ_HDR + 8)
            a.or_a()
            a.sbc_hl_de()
            a.jr_nz("_recv_dispatch_continue")    # まだ8バイト未満: ポーリングを繰り返す
            # Z: 8バイト到達。そのまま_recv_dispatch_hdr_doneへ落ちる
        else:
            # 最初の受信と同じ2/5/1境界判定。2件後はアイドルへ戻り、
            # 7件後はFDCデータを準備し、8件後に単発応答を保留する。
            a.ld_a_mem(EXCHANGE3_REQUEST_ACTIVE)
            a.or_a()
            a.jr_z("_recv_dispatch_continue")
            a.ld_a_mem(RUN_LEN)
            a.cp_n(2)
            a.jp_z("IDLE_DISPATCH")
            a.cp_n(7)
            a.jp_z("_exchange3_prepare_sector")
            a.cp_n(8)
            a.jp_z("_exchange3_request_done")
            a.jr("_recv_dispatch_continue")       # bit1が先に立つまで受信を続ける

    if not break_fixed_byte_cutoff:
        # ---- run終了(bit1観測)。要求長だけでなく交換状態で形式を判断する ----
        a.label("_recv_dispatch_run_done")
        a.ld_a_mem(EXCHANGE3_REQUEST_ACTIVE)
        a.or_a()
        a.jp_nz("IDLE_DISPATCH")
        a.ld_a_mem(SECTOR_READY)
        a.or_a()
        a.jp_nz("_recv_dispatch_maybe_exchange4")

        # 交換#3: 固定8バイト要求。ここではFDC実データ応答を開始しない。
        a.ld_a_mem(RUN_LEN)
        a.cp_n(8)
        a.jp_nz("IDLE_DISPATCH")
        # run長==8: _recv_dispatch_hdr_doneへ落ち、データ準備だけを行う。

    # 固定8バイト要求の完了: 次の要求受信に備えてポインタを巻き戻す。
    # break_fixed_byte_cutoffの検出力用旧構造もここへ入る。
    a.label("_recv_dispatch_hdr_done")
    a.ld_hl_imm(REQ_HDR)
    a.ld_mem_hl(HDR_PTR)

    # FDCから256バイトを読み出して保持する。ただし交換#3では
    # RESP_ACTIVEを立てない。応答は下のEXCHANGE3_RESPONSE_PENDING経路で
    # 内部状態1バイトだけを返す。
    a.ld_hl_imm(REQ_HDR + 3)
    a.ld_a_hl()
    a.ld_e(0x00)
    a.call("FDC_SEEK")

    a.call("FDC_READ_SECTOR")
    if break_response:
        a.ld_hl_imm(SECTOR_BUF)
        a.ld_a_hl()
        a.db(0xEE, 0x01)
        a.ld_hl_a()
    a.ld_a(0x01)
    a.ld_mem_a(SECTOR_READY)
    a.ld_mem_a(EXCHANGE3_RESPONSE_PENDING)
    a.jp("IDLE_DISPATCH")

    if not break_fixed_byte_cutoff:
        # 第32版1.25節: 2+5件を受信した時点でFDC実データを準備する。
        # 最後の1件はFDC完了後に別のRECVとして受けるため、要求ポインタと
        # RUN_LENは保持し、ここでは単発応答をまだ有効にしない。
        a.label("_exchange3_prepare_sector")
        a.ld_hl_imm(REQ_HDR + 3)
        a.ld_a_hl()
        a.ld_e(0x00)
        a.call("FDC_SEEK")
        a.call("FDC_READ_SECTOR")
        if break_response:
            a.ld_hl_imm(SECTOR_BUF)
            a.ld_a_hl()
            a.db(0xEE, 0x01)
            a.ld_hl_a()
        a.ld_a(0x01)
        a.ld_mem_a(SECTOR_READY)
        a.jp("IDLE_DISPATCH")

        # FDC完了後の最後の1件を受信した。交換#3の単発応答だけを保留し、
        # 交換#4が来るまでSECTOR_READYは維持する。
        a.label("_exchange3_request_done")
        a.ld_a(0x00)
        a.ld_mem_a(EXCHANGE3_REQUEST_ACTIVE)
        a.ld_a(0x01)
        a.ld_mem_a(EXCHANGE3_RESPONSE_PENDING)
        a.jp("IDLE_DISPATCH")

    if not break_fixed_byte_cutoff:
        # 交換#4: 交換#3で実データが準備済みの場合だけ、続く2バイト要求を
        # 256バイト応答開始のトリガーとして扱う。
        a.label("_recv_dispatch_maybe_exchange4")
        a.ld_a_mem(RUN_LEN)
        a.cp_n(2)
        a.jp_nz("IDLE_DISPATCH")

        a.ld_hl_imm(SECTOR_BUF)
        a.ld_mem_hl(RESP_PTR)
        a.ld_a(0x01)
        a.ld_mem_a(RESP_ACTIVE)
        a.ld_a(0x00)
        a.ld_mem_a(SECTOR_READY)
        a.jp("IDLE_DISPATCH")

    # ---- SEND_DISPATCH: SENDを1回だけ行い、必ずIDLE_DISPATCHへ戻る。
    #      優先順位は交換#4の256バイト応答、交換#3の内部状態1バイト応答、
    #      その他の従来単発応答。交換#3をRESP_ACTIVEへ入れないことが
    #      第29版の修正点である。
    a.label("SEND_DISPATCH")
    a.ld_a_mem(RESP_ACTIVE)
    a.or_a()
    a.jr_z("SEND_DISPATCH_ONE_BYTE")

    a.ld_hl_mem(RESP_PTR)
    a.ld_a_hl()
    a.call("SEND_BYTE")
    a.ld_hl_mem(RESP_PTR)
    a.inc_hl()
    a.ld_mem_hl(RESP_PTR)
    a.ld_de_imm(SECTOR_BUF + 256)
    a.or_a()
    a.sbc_hl_de()                     # RESP_PTR(更新後) - (SECTOR_BUF+256)
    a.jp_nz("IDLE_DISPATCH")          # まだ256バイト送り終えていない（遠方分岐のためJP）

    # 256バイト送り終えた: 応答フェーズを終了する
    a.ld_a(0x00)
    a.ld_mem_a(RESP_ACTIVE)
    a.jp("IDLE_DISPATCH")   # 遠方分岐のためJP

    a.label("SEND_DISPATCH_ONE_BYTE")
    a.ld_a_mem(EXCHANGE3_RESPONSE_PENDING)
    a.or_a()
    a.jr_z("SEND_DISPATCH_IDLE")

    # 交換#3: 意味未特定の内部状態応答を1バイトだけ送る。
    # TODO(仕様第30版): 挙動から再構成した観測値。意味未特定。
    # 意味が判明した場合は、意味に基づくルール生成へ差し替える。
    a.ld_a(0x00)
    a.ld_mem_a(EXCHANGE3_RESPONSE_PENDING)
    a.ld_a(EXCHANGE3_OBSERVED_RESPONSE)
    a.call("SEND_BYTE")
    a.jp("IDLE_DISPATCH")

    a.label("SEND_DISPATCH_IDLE")
    # 起動系列の最初の単発応答は、BOOT_HANDSHAKEが要求先頭を消費するため
    # REQ_HDRだけでは識別できない。MAIN_LOOP開始後の最初の単発送信へ一度だけ適用する。
    a.ld_a_mem(ROUND0_RESPONSE_PENDING)
    a.or_a()
    a.jr_z("_observed_single_by_request")
    a.ld_a(0x00)
    a.ld_mem_a(ROUND0_RESPONSE_PENDING)
    a.ld_a(ROUND0_OBSERVED_RESPONSE)
    a.call("SEND_BOOT_SINGLE_TRACKED")
    a.jp("IDLE_DISPATCH")

    # m7hの要求グループ→応答グループ決定関数。意味未特定の観測応答であり、
    # 意味が判明した場合は要求の意味に基づくルール生成へ差し替える。
    a.label("_observed_single_by_request")
    a.ld_a_mem(RUN_LEN)
    a.cp_n(2)
    a.jp_nz("_observed_request_next_1")
    a.ld_hl_imm(REQ_HDR + 0)
    a.ld_a_hl()
    a.cp_n(0x00)
    a.jp_nz("_observed_request_next_1")
    a.ld_hl_imm(REQ_HDR + 1)
    a.ld_a_hl()
    a.cp_n(0x07)
    a.jp_nz("_observed_request_next_1")
    a.ld_a(OBSERVED_SINGLE_RESPONSE_BY_REQUEST[0][1])
    a.call("SEND_BYTE")
    a.jp("IDLE_DISPATCH")
    a.label("_observed_request_next_1")
    a.ld_a_mem(RUN_LEN)
    a.cp_n(1)
    a.jp_nz("_observed_request_next_2")
    a.ld_hl_imm(REQ_HDR + 0)
    a.ld_a_hl()
    a.cp_n(0x06)
    a.jp_nz("_observed_request_next_2")
    a.ld_a(OBSERVED_SINGLE_RESPONSE_BY_REQUEST[1][1])
    a.call("SEND_BOOT_SINGLE_TRACKED")
    a.jp("IDLE_DISPATCH")
    a.label("_observed_request_next_2")
    a.ld_a_mem(RUN_LEN)
    a.cp_n(5)
    a.jp_nz("_observed_request_next_3")
    a.ld_hl_imm(REQ_HDR + 0)
    a.ld_a_hl()
    a.cp_n(0x0B)
    a.jp_nz("_observed_request_next_3")
    a.ld_hl_imm(REQ_HDR + 1)
    a.ld_a_hl()
    a.cp_n(0x07)
    a.jp_nz("_observed_request_next_3")
    a.ld_hl_imm(REQ_HDR + 2)
    a.ld_a_hl()
    a.cp_n(0x5F)
    a.jp_nz("_observed_request_next_3")
    a.ld_hl_imm(REQ_HDR + 3)
    a.ld_a_hl()
    a.cp_n(0x00)
    a.jp_nz("_observed_request_next_3")
    a.ld_hl_imm(REQ_HDR + 4)
    a.ld_a_hl()
    a.cp_n(0x01)
    a.jp_nz("_observed_request_next_3")
    a.ld_a(OBSERVED_SINGLE_RESPONSE_BY_REQUEST[2][1])
    a.call("SEND_BOOT_SINGLE_TRACKED")
    a.jp("IDLE_DISPATCH")
    a.label("_observed_request_next_3")
    a.ld_a_mem(RUN_LEN)
    a.cp_n(8)
    a.jp_nz("_observed_request_next_4")
    a.ld_hl_imm(REQ_HDR + 0)
    a.ld_a_hl()
    a.cp_n(0x17)
    a.jp_nz("_observed_request_next_4")
    a.ld_hl_imm(REQ_HDR + 1)
    a.ld_a_hl()
    a.cp_n(0x0F)
    a.jp_nz("_observed_request_next_4")
    a.ld_hl_imm(REQ_HDR + 2)
    a.ld_a_hl()
    a.cp_n(0x02)
    a.jp_nz("_observed_request_next_4")
    a.ld_hl_imm(REQ_HDR + 3)
    a.ld_a_hl()
    a.cp_n(0x01)
    a.jp_nz("_observed_request_next_4")
    a.ld_hl_imm(REQ_HDR + 4)
    a.ld_a_hl()
    a.cp_n(0x00)
    a.jp_nz("_observed_request_next_4")
    a.ld_hl_imm(REQ_HDR + 5)
    a.ld_a_hl()
    a.cp_n(0x00)
    a.jp_nz("_observed_request_next_4")
    a.ld_hl_imm(REQ_HDR + 6)
    a.ld_a_hl()
    a.cp_n(0x01)
    a.jp_nz("_observed_request_next_4")
    a.ld_hl_imm(REQ_HDR + 7)
    a.ld_a_hl()
    a.cp_n(0x06)
    a.jp_nz("_observed_request_next_4")
    a.ld_a(OBSERVED_SINGLE_RESPONSE_BY_REQUEST[3][1])
    a.call("SEND_BYTE")
    a.jp("IDLE_DISPATCH")
    a.label("_observed_request_next_4")
    a.ld_a_mem(RUN_LEN)
    a.cp_n(6)
    a.jp_nz("_observed_request_next_5")
    a.ld_hl_imm(REQ_HDR + 0)
    a.ld_a_hl()
    a.cp_n(0x02)
    a.jp_nz("_observed_request_next_5")
    a.ld_hl_imm(REQ_HDR + 1)
    a.ld_a_hl()
    a.cp_n(0x01)
    a.jp_nz("_observed_request_next_5")
    a.ld_hl_imm(REQ_HDR + 2)
    a.ld_a_hl()
    a.cp_n(0x00)
    a.jp_nz("_observed_request_next_5")
    a.ld_hl_imm(REQ_HDR + 3)
    a.ld_a_hl()
    a.cp_n(0x00)
    a.jp_nz("_observed_request_next_5")
    a.ld_hl_imm(REQ_HDR + 4)
    a.ld_a_hl()
    a.cp_n(0x02)
    a.jp_nz("_observed_request_next_5")
    a.ld_hl_imm(REQ_HDR + 5)
    a.ld_a_hl()
    a.cp_n(0x06)
    a.jp_nz("_observed_request_next_5")
    a.ld_a(OBSERVED_SINGLE_RESPONSE_BY_REQUEST[4][1])
    a.call("SEND_BYTE")
    a.jp("IDLE_DISPATCH")
    a.label("_observed_request_next_5")
    a.ld_a_mem(RUN_LEN)
    a.cp_n(5)
    a.jp_nz("_observed_request_next_6")
    a.ld_hl_imm(REQ_HDR + 0)
    a.ld_a_hl()
    a.cp_n(0x0B)
    a.jp_nz("_observed_request_next_6")
    a.ld_hl_imm(REQ_HDR + 1)
    a.ld_a_hl()
    a.cp_n(0x07)
    a.jp_nz("_observed_request_next_6")
    a.ld_hl_imm(REQ_HDR + 2)
    a.ld_a_hl()
    a.cp_n(0xEF)
    a.jp_nz("_observed_request_next_6")
    a.ld_hl_imm(REQ_HDR + 3)
    a.ld_a_hl()
    a.cp_n(0x00)
    a.jp_nz("_observed_request_next_6")
    a.ld_hl_imm(REQ_HDR + 4)
    a.ld_a_hl()
    a.cp_n(0x01)
    a.jp_nz("_observed_request_next_6")
    a.ld_a(OBSERVED_SINGLE_RESPONSE_BY_REQUEST[5][1])
    a.call("SEND_BYTE")
    a.jp("IDLE_DISPATCH")
    a.label("_observed_request_next_6")
    a.ld_a_mem(RUN_LEN)
    a.cp_n(5)
    a.jp_nz("_observed_request_next_7")
    a.ld_hl_imm(REQ_HDR + 0)
    a.ld_a_hl()
    a.cp_n(0x0B)
    a.jp_nz("_observed_request_next_7")
    a.ld_hl_imm(REQ_HDR + 1)
    a.ld_a_hl()
    a.cp_n(0x07)
    a.jp_nz("_observed_request_next_7")
    a.ld_hl_imm(REQ_HDR + 2)
    a.ld_a_hl()
    a.cp_n(0xEE)
    a.jp_nz("_observed_request_next_7")
    a.ld_hl_imm(REQ_HDR + 3)
    a.ld_a_hl()
    a.cp_n(0x00)
    a.jp_nz("_observed_request_next_7")
    a.ld_hl_imm(REQ_HDR + 4)
    a.ld_a_hl()
    a.cp_n(0x01)
    a.jp_nz("_observed_request_next_7")
    a.ld_a(OBSERVED_SINGLE_RESPONSE_BY_REQUEST[6][1])
    a.call("SEND_BYTE")
    a.jp("IDLE_DISPATCH")
    a.label("_observed_request_next_7")
    a.ld_a_mem(RUN_LEN)
    a.cp_n(8)
    a.jp_nz("_observed_request_next_8")
    a.ld_hl_imm(REQ_HDR + 0)
    a.ld_a_hl()
    a.cp_n(0x17)
    a.jp_nz("_observed_request_next_8")
    a.ld_hl_imm(REQ_HDR + 1)
    a.ld_a_hl()
    a.cp_n(0x0F)
    a.jp_nz("_observed_request_next_8")
    a.ld_hl_imm(REQ_HDR + 2)
    a.ld_a_hl()
    a.cp_n(0x02)
    a.jp_nz("_observed_request_next_8")
    a.ld_hl_imm(REQ_HDR + 3)
    a.ld_a_hl()
    a.cp_n(0x01)
    a.jp_nz("_observed_request_next_8")
    a.ld_hl_imm(REQ_HDR + 4)
    a.ld_a_hl()
    a.cp_n(0x00)
    a.jp_nz("_observed_request_next_8")
    a.ld_hl_imm(REQ_HDR + 5)
    a.ld_a_hl()
    a.cp_n(0x03)
    a.jp_nz("_observed_request_next_8")
    a.ld_hl_imm(REQ_HDR + 6)
    a.ld_a_hl()
    a.cp_n(0x03)
    a.jp_nz("_observed_request_next_8")
    a.ld_hl_imm(REQ_HDR + 7)
    a.ld_a_hl()
    a.cp_n(0x06)
    a.jp_nz("_observed_request_next_8")
    a.ld_a(OBSERVED_SINGLE_RESPONSE_BY_REQUEST[7][1])
    a.call("SEND_BYTE")
    a.jp("IDLE_DISPATCH")
    a.label("_observed_request_next_8")
    a.ld_a_mem(RUN_LEN)
    a.cp_n(6)
    a.jp_nz("_observed_request_next_9")
    a.ld_hl_imm(REQ_HDR + 0)
    a.ld_a_hl()
    a.cp_n(0x02)
    a.jp_nz("_observed_request_next_9")
    a.ld_hl_imm(REQ_HDR + 1)
    a.ld_a_hl()
    a.cp_n(0x01)
    a.jp_nz("_observed_request_next_9")
    a.ld_hl_imm(REQ_HDR + 2)
    a.ld_a_hl()
    a.cp_n(0x00)
    a.jp_nz("_observed_request_next_9")
    a.ld_hl_imm(REQ_HDR + 3)
    a.ld_a_hl()
    a.cp_n(0x25)
    a.jp_nz("_observed_request_next_9")
    a.ld_hl_imm(REQ_HDR + 4)
    a.ld_a_hl()
    a.cp_n(0x0D)
    a.jp_nz("_observed_request_next_9")
    a.ld_hl_imm(REQ_HDR + 5)
    a.ld_a_hl()
    a.cp_n(0x06)
    a.jp_nz("_observed_request_next_9")
    a.ld_a(OBSERVED_SINGLE_RESPONSE_BY_REQUEST[8][1])
    a.call("SEND_BYTE")
    a.jp("IDLE_DISPATCH")
    a.label("_observed_request_next_9")
    # 第22版で再訂正: 第20版→第21版の変遷は以下の通り。
    #   第9版: FDC_SENSE_DRIVE_STATUSを実発行してST3を送る（5adf82e）。
    #   第20版: 混成ROM実走診断（22:16版、分岐点103）で「公式subは
    #     この場面でFDCを一切叩かず、その場で1バイト送るだけ」という
    #     I/O列の構造が確定したため、FDCを叩かない構造に変更。
    #     しかし送る値を無意味な0x00固定に戻した結果、main側の構造
    #     一致件数が第9版(137件)より後退した(102件、m6t参照)。
    #   第21版: LAST_FDC_RESULT（過去にFDC_INが実際に読み取った結果
    #     バイトを保持するRAM）を新設し、それを送ることでFDCを叩かず
    #     かつ実測値を送る、という両立を試みた。しかしmain側一致件数は
    #     102件のままで、第9版の137件を再現できなかった。
    #
    # 第22版: 適合条件は「mainが受け取るデータ列」であり(仕様書5.1節・
    # 1.14節・1.15節)、sub内部のI/O列が公式と一致することそのものは
    # 適合条件ではない。第9版のFDC_SENSE_DRIVE_STATUS実発行構造
    # （137件一致）を優先し、こちらへ戻す。
    #
    # これは第20版・6c0563dの測定結果と**食い違う**選択である:
    # 直前の測定(6c0563d)は「SENSE DRIVE STATUS構造は1バイト応答の
    # 直前には現れない」「1バイト応答の直前は4条件99.6%でFDCイベント
    # 0件」を確定させており、公式subがこの場面でFDCを叩いていないこと
    # を強く示している。にもかかわらずFDC_SENSE_DRIVE_STATUSを実発行
    # するのは、ST3の値そのものは推測ではなくFDCが実際に持つドライブ
    # 状態から得られる値であり、mainが受け取るバイト列を公式と一致
    # させる（適合条件）ためにはその値が必要だからである。公式subが
    # FDCを叩かずにどこからこの値を得ているか（内部ワークエリアに
    # 保持しているのか等）は、ROM内部のワークエリア構造に踏み込む
    # 領域でありクリーンルーム規律上測定では届かない（docs/spec/
    # l3-subrom.md 3節に未確定として記録）。
    #
    # 結果として、sub側のI/O列は分岐点103で公式と再び食い違う
    # （このSEND_DISPATCH_IDLEでFDCへOUT $FB×2/IN $FBが発生する）。
    # それは承知の上で許容する——適合条件はmain側のデータ列であり、
    # sub側のI/O列一致はそもそも目標に含まれていない。
    a.call("FDC_SENSE_DRIVE_STATUS")
    a.call("SEND_BYTE")
    a.jp("IDLE_DISPATCH")   # 遠方分岐のためJP

    return a


def build(break_response=False, break_dispatch_return=False,
          break_run_continuation=False,
          inject_spurious_sense_int=False,
          break_sense_int_result_count=False,
          break_fdc_timeout_reads_anyway=False,
          disable_fdc_timeout_mark=False,
          break_fixed_byte_cutoff=False):
    a = build_subrom(break_response=break_response,
                      break_dispatch_return=break_dispatch_return,
                      break_run_continuation=break_run_continuation,
                      inject_spurious_sense_int=inject_spurious_sense_int,
                      break_sense_int_result_count=break_sense_int_result_count,
                      break_fdc_timeout_reads_anyway=break_fdc_timeout_reads_anyway,
                      disable_fdc_timeout_mark=disable_fdc_timeout_mark,
                      break_fixed_byte_cutoff=break_fixed_byte_cutoff)
    a.resolve()
    code = bytes(a.code)
    if len(code) > ROM_SIZE:
        raise SystemExit(f"ROM に収まらない: {len(code)} > {ROM_SIZE}")
    rom = bytearray([0x00] * ROM_SIZE)
    rom[: len(code)] = code
    return rom, len(code)


def main():
    ap = argparse.ArgumentParser(
        description="L3 サブROム（DISK.ROM相当）を組み立てる（docs/spec/l3-subrom.md）")
    ap.add_argument("outdir")
    ap.add_argument("--break-response", action="store_true",
                     help="検証器をわざと壊すためのフラグ（tools/verify_l3.sh 用）。"
                          "応答256バイトの先頭を1ビット反転させる。")
    ap.add_argument("--break-dispatch-return", action="store_true",
                     help="第9版で修正したバグ（RECV/SEND完遂後にIDLE_DISPATCHへ"
                          "戻らない旧構造）をわざと再現するフラグ（tools/verify_l3.sh "
                          "の回帰テストの検出力確認用）。")
    ap.add_argument("--break-run-continuation", action="store_true",
                     help="第11版で修正したバグ（RECV完遂後、まだ8バイト未満でも"
                          "無条件でIDLE_DISPATCHへ戻り、mainの継続SENDバイト"
                          "(0F省略)と相互デッドロックする旧構造）をわざと再現する"
                          "フラグ（tools/verify_l3.sh の回帰テストの検出力確認用）。")
    ap.add_argument("--inject-spurious-sense-int", action="store_true",
                     help="起動直後、RECALIBRATE/SEEKを一度も発行していない時点で"
                          "SENSE INTERRUPT STATUSを1回よけいに呼ぶ。μPD765の仕様上"
                          "結果フェーズがST0の1バイトだけで終わる状況を意図的に作る"
                          "（tools/verify_l3.sh の検出力確認用）。")
    ap.add_argument("--break-sense-int-result-count", action="store_true",
                     help="FDC_SENSE_INTを、ST0のInterrupt Codeフィールドを見ずに"
                          "常に2バイト読む旧実装に戻す（tools/verify_l3.sh の"
                          "回帰テストの検出力確認用。--inject-spurious-sense-intと"
                          "組み合わせて使う）。")
    ap.add_argument("--break-fdc-timeout-reads-anyway", action="store_true",
                     help="第12版で修正したバグ（FDC_IN/FDC_OUTがタイムアウト、"
                          "または待たずに相手がフェーズを終えていたことを検出した"
                          "後も、そのまま$FBを読み書きしていた旧構造）をわざと"
                          "再現するフラグ（tools/verify_l3.sh の回帰テストの"
                          "検出力確認用）。")
    ap.add_argument("--disable-fdc-timeout-mark", action="store_true",
                     help="$F9（FDC_TIMEOUT_MARK、診断専用の未デコードポート。"
                          "公式subには存在しない）への書き込みを無効化する。"
                          "適合テストへ提出するROMではこのイベント自体を"
                          "出したくない場合に使う。")
    ap.add_argument("--fixed-byte-cutoff-test", action="store_true",
                     dest="break_fixed_byte_cutoff",
                     help="第13版で修正したバグ（run境界(bit1の観測)ではなく"
                          "通算8バイト受け取ったことだけでrunを打ち切っていた"
                          "旧構造）をわざと再現するフラグ（tools/verify_l3.sh "
                          "の回帰テストの検出力確認用）。")
    args = ap.parse_args()
    rom, used = build(break_response=args.break_response,
                       break_dispatch_return=args.break_dispatch_return,
                       break_run_continuation=args.break_run_continuation,
                       inject_spurious_sense_int=args.inject_spurious_sense_int,
                       break_sense_int_result_count=args.break_sense_int_result_count,
                       break_fdc_timeout_reads_anyway=args.break_fdc_timeout_reads_anyway,
                       disable_fdc_timeout_mark=args.disable_fdc_timeout_mark,
                       break_fixed_byte_cutoff=args.break_fixed_byte_cutoff)
    d = pathlib.Path(args.outdir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "DISK.ROM").write_bytes(rom)
    print(f"生成した: {d/'DISK.ROM'} ({ROM_SIZE} bytes, コード {used} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
