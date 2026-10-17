# l4-t4 追補1 事前登録

2026-10-18。公式再測定前に固定。CLAUDE.mdのクリーンルーム規律に従う。
第1回の記録・腕・署名・予測を置換しない。公式ROMはこの作業では実行しない。

第1回の親要約を追補の根拠とする。定数CALLはERR2、変数経由だけ実行されたため、定数で書かれた破壊・引数・境界腕は目的を測れていない。
USRでは1の整数候補が型を問わずHL+6に一致し、偶然一致が疑われる。書換腕は一致せず介入なし。
BSAVE/BLOADは全腕ERR33。両ドライブを空媒体としたためディスクBASICが有効でない起動を関門が見逃した。第1回を有効なBSAVE仕様測定と読み替えない。
VARPTR配列の器具定義を確認したところ、setupは `dim a(4)` と `a(3)=1` であった。代入漏れではないので今回は配列再走を追加しない。不一致の理由は未確定。

## 測定・予測・判定

CALLは変数qを経由。正常番地再確認は実行印213と復帰を予測。破壊後の復帰、引数受理と入口DE/HL/BCの指す先、範囲外や小数の変換は未確定。
文字列変数はERR13、未定義変数はERR5を仮説とし、違えばその番号を残す。
-1/65535を含め全腕全反復を独立起動する。フロントエンドの壁時計制限180秒、固定フレーム終了で完了印がない場合とも不明。暴走を正常復帰とみなさない。

USRは整数12345、単12345!、倍12345#、文字列t4own、整数23456。
入口Aは整数02/単04/倍08/文字列03を予測。入口値と符号化の位置は独立に判定し、一致だけで引数の所在地と断定しない。
HL・DE・BCそれぞれに、以下6候補を同じ順で照合する。クロス対照は12345腕中の整数23456候補と23456腕中の整数12345候補の両方向を残し、不一致を予測する。


|候補|既知符号化|
|---|---|
|int12345|39 30|
|single12345|00 e4 40 8e|
|double12345|00 00 00 00 00 e4 40 8e|
|text|74 34 6f 77 6e|
|int23456|a0 5b|
|descriptor|長さ5＋下位先の2バイト番地。その先がt4own|

MBFは器具内の自作関数mbf_integerで正整数の先頭1を除く仮数と指数+129から生成する。整数は下位先。
各レジスタを中心に-32〜+32を昇順で比較。元レジスタがRAM 0x8000〜0xFFFF外なら255、最初の一致のずれ+33を1〜65、一致なし0。
候補全体がRAMに収まるときだけ読む。文字列記述子候補は3バイトがRAM内、長さ5、参照先5バイトもRAM内のときだけt4ownと照合。
未一致バイトは記録しない。格納欄p32〜p37=HL、p38〜p43=DE、p44〜p49=BC、各欄の候補順は上表。
引数受渡し中の誤りで後処理に到達しない初期値0は未測定。USR書換腕は今回測らず、ずれ確定後の追補2へ送る。

BSAVEの測定対象名は2:t4own、較正専用名は2:t4cal。ドライブ1はPC88_REF_DISK_DIRとM6FF_FROZEN_CONFIG（既定tools/m6ff_frozen.tsv）のreference_disk名を用いた作業域コピー、ドライブ2は自作空媒体。
コピー後のドライブ1像は読取り・照合・ハッシュ・出力せず、各起動のfinallyで削除する。ファイルコピー操作だけに用いる。
ドライブ2だけで自作名のディレクトリ・FAT鎖・既知本体を照合する。自作/公式で媒体構成を変えない。
環境変数・参照ファイルが無ければ全腕起動前に関門失敗で止める。

## 関門

両器具はmeasure冒頭に署名・合成自己検査を毎回実施。第1回腕定義と入力署名も検証する。
開始・初期化・段・誤り履歴・復帰・完了・安定600フレーム・取りこぼし0・全腕各2走一致・較正POKE/ERRORの既存関門を保つ。
BSAVEは較正POKE/ERRORに続き、最初の保存腕として `bsave "2:t4cal",&hc100,1` を置く。
公式はこの腕の誤り0とドライブ2での名前一致が必須。較正以外の全腕全反復の最初の誤り番号が1種類なら（0だけの場合も含む）一様として全腕無効。
自作はBSAVE/BLOAD未実装のため、この陽性対照のERR2@段1と一様ERR2に限り既知として免除する。印・打鍵・ログ・安定・2走一致等は免除しない。公式にはこの免除を適用しない。
合成陽性は全印・媒体形式を通過し非一様のとき通る。陰性は媒体名だけ欠落させ陽性対照で拒否、較正を保ったまま誤りを一様化して一様判定で拒否する。自作免除と環境欠落も検査。
関門落ちでも採れた誤り番号を保持し、画面比較は無効（今回画面本文・画面比較自体は採らない）。較正不成立は全腕無効。凍結値・期待値を公式結果に合わせない。

## 腕と署名

`--round addendum1` が既定。`--round first` は第1回定義の再現用で今回再走しない。較正2腕は両集合で共通。
第1回のPLAN_SHA/PROGRAM_SHAは器具内にそのまま保持。以下は追補の別署名。


mlcall: PLAN `706c17284c27f430831de0271ba0eae9fbd41373c35c23701933db3a079a1be1` / PROGRAM `10899cafb6fd0404ed967e0a34bb45934ff2bc862562b295722973cdf7bc3bc0`

|腕|刺激|予測|入力SHA-256|
|---|---|---|---|
|cal-poke|poke &hc310,213|cal213・ERR0|f3bdaebca258961459b7b499e500496d3d41ed953ac9b7d996e2bf146ae310d1|
|cal-error|error 13|ERR13、段1|11baa34c6401190951ddc8d38dc99af77aec102f142c9de479ec3ad36dd44c7c|
|a1-call-variable|call q|実行印213・正常復帰を再確認|1664e1e083582ebf4ce7a45197eb20a7f04fa979ca80a65042ec9a68a44b6a9b|
|a1-call-clobber|call q|レジスタ破壊後も正常復帰の仮説|15c08585ec3daed972d0c11164511d49b8f118ba4f6b5b5c8557549292fc6ddf|
|a1-call-args-one|call q(x)|ERR/入口/復帰を未確定として測る|c7176e1e7cb62ce5235b8512958d0e3c9d1ad99507497cfb98c36d8cb34af41b|
|a1-call-args-mixed|call q(x%,y$)|ERR/入口/復帰を未確定として測る|ae54d46624740e7a3591af1ef8c69cfce350f72ec9fe5904ac712842489d93fa|
|a1-call-minus1|call q|範囲/丸め未確定。-1/65535の時間切れは不明|23bc85506ae74ebe766714e6f3f394bb5d890b2a6fc5293999ad2bdc30c023e9|
|a1-call-65535|call q|範囲/丸め未確定。-1/65535の時間切れは不明|94ff4eba98188f338001557ac869406c283179a5df8c2dd3efcd97444f07285c|
|a1-call-65536|call q|範囲/丸め未確定。-1/65535の時間切れは不明|efc04658cbaf14d7623c5fd56a431c6a6abe3d62bce98a91a9fc5f065bb81454|
|a1-call-fraction|call q|範囲/丸め未確定。-1/65535の時間切れは不明|c0c0933bf97b4317b3cc58538e42e12fd1ba12de0d7372d3bd62d038de7ce0cc|
|a1-call-string|call q$|型ERR13を仮説|2245bf22e6de529679f6fa00653ec7dcf20aaef867ff09a22f4f0b9288365bfd|
|a1-call-undefined|call q|未定義ERR5を仮説|5a6189000d0275b549b85096f94a7b5d5e62e1b4676edb3112a34acd5ac50479|
|a1-usr-int|def usr0=&hc000 / y%=usr0(x%)|A型値02/04/08/03、候補位置は未確定。異値整数候補は不一致の仮説|fd39c729b7cd1c67640b94f1d0942d9d0047a2467e855363f8e9930b766a4819|
|a1-usr-single|def usr0=&hc000 / y!=usr0(x!)|A型値02/04/08/03、候補位置は未確定。異値整数候補は不一致の仮説|c38b094afabaca330950460f4b04791a8f91f005e57f7c470e8d04499141e1fc|
|a1-usr-double|def usr0=&hc000 / y#=usr0(x#)|A型値02/04/08/03、候補位置は未確定。異値整数候補は不一致の仮説|75876bfbdfa236b86f6d87d8c7d0c77842e5529758acedb860cad8014c37977a|
|a1-usr-string|def usr0=&hc000 / y$=usr0(x$)|A型値02/04/08/03、候補位置は未確定。異値整数候補は不一致の仮説|b5086c59beb8b0db420564ef99fddd5451053404a91f1e6247b0ba1052b37fbf|
|a1-usr-cross23456|def usr0=&hc000 / y%=usr0(x%)|A型値02/04/08/03、候補位置は未確定。異値整数候補は不一致の仮説|dde1ff4f6c17fbf6c2180a0e8cfb967287a342843d839d6507f6c2b166c0b781|

bsave: PLAN `06c4588b90f4134d830808f5d11db93e2604404ddf3a1a447ebbf5202a2ee1b4` / PROGRAM `c97d3e716d02896cdf22643a9152ecdc540c23f669ab893f878ee845ff574c7e`

|腕|刺激|予測|入力SHA-256|
|---|---|---|---|
|cal-poke|poke &hc310,213|cal213・ERR0|f3bdaebca258961459b7b499e500496d3d41ed953ac9b7d996e2bf146ae310d1|
|cal-error|error 13|ERR13、段1|11baa34c6401190951ddc8d38dc99af77aec102f142c9de479ec3ad36dd44c7c|
|a1-cal-disk|bsave "2:t4cal",&hc100,1|公式ではERR0かつドライブ2にt4cal必須。自作は未実装既知|4303f7a6010378cb220447ebbe39ab04d0eb5a78b97359835fa25ed5abb87eac|
|a1-bload-default|bsave "2:t4own",&hc100,64 / for j=0 to 63:poke 49408+j,0:next j / bload "2:t4own"|ERR番号、正常時は既知型との一致|a6c53f9f55a346324cab5af7e2911f682b353ad505915ee27f8a6f6a6c57ecad|
|a1-bload-relocate|bsave "2:t4own",&hc100,64 / for j=0 to 63:poke 49408+j,0:next j / bload "2:t4own",&hc200|ERR番号、正常時は既知型との一致|d5b4011203c640114434894496c4f75e800316d80d5bad59135b24738dc089cf|
|a1-bload-run|bsave "2:t4own",49408,6 / for j=0 to 5:poke 49408+j,0:next j / bload "2:t4own",r|保存した自作コードが実行印213を付けRET|c90c7f1607e44d98aed30d07c55ceef770988e2661c477ec97375d01f9c85ccd|
|a1-missing|bload "2:absent"|ERR番号、正常時は既知型との一致|ef38ce23ba5ce392147ea7db5ec747f031e3261b79d705f5c07757849b3c5e4e|
|a1-zero|bsave "2:t4own",&hc100,0|ERR番号、正常時は既知型との一致|39df659cd98dd649de64e221673792622fd9aa183094b462d12f390b472c24df|
|a1-overflow|bsave "2:t4own",65530,10|ERR番号、正常時は既知型との一致|eb68253677cc0e54f43df101939a8f926616953ac2a0485fd3af85fb5a8259fa|
|a1-save-missing|bsave "2:t4own",&hc100|ERR番号、正常時は既知型との一致|17f5489cb1dffe82ab3146e3a9bc951127af7a8cb17f3cce6bb82802b25d7484|
|a1-load-missing|bload|ERR番号、正常時は既知型との一致|72a95089aa425ab79e1d0184edd37c00733ad28cb325400068393192c02bce18|
|a1-drive|bload "9:t4own"|ERR番号、正常時は既知型との一致|77a0543c53fdb8427806cc4ed8fc33143b0388ffae9b26d5a6da4819625c670a|
|a1-extra|bload "2:t4own",&hc200,1|ERR番号、正常時は既知型との一致|7746b2b9405e4ece45116008da030e1f5748272c7a53ef66ae3a7633ac88bd86|
|a1-address-string|bsave "2:t4own","a",64|ERR番号、正常時は既知型との一致|59bf3bcdacd9f0eb457cae29f8ebad7c92baf96aa96127dd1bf50a212abf8f75|

## 今回測らないものと公式再測定コマンド

第1回の定数CALL、USR番号範囲やVARPTR各型の再走、USR書換、公式ROM実行、src変更、run_all、commitは行わない。
自作試走は指定2本のselftestのみ。詳細はtmp/t4-work/selfrun-addendum1.mdへ残す。
親はPC88_REF_ROM_DIR/PC88_REF_DISK_DIRを設定後、リポジトリで次を実行する（追補腕と較正だけ）。

```sh
python3 tools/l4_mlcall_measure.py measure --round addendum1 --official --work-dir "$PWD/tmp/t4-work/mlcall-official-addendum1" --out "$PWD/tmp/t4-work/mlcall-official-addendum1.tsv"
python3 tools/l4_bsave_measure.py measure --round addendum1 --official --work-dir "$PWD/tmp/t4-work/bsave-official-addendum1" --out "$PWD/tmp/t4-work/bsave-official-addendum1.tsv"
```

生成照合サブルーチンは候補ごとに共用し、格納欄wを呼出時に指定する。全入力8192文字以内も合成検査する。照合条件・腕定義は変更なし。

自己検査はERR0一様・ERR33一様の拒否、公式TSV全腕無効化後のERR33保持、自作ERR2のみの免除も含む。
