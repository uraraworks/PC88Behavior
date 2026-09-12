# m7lv: 自作subに媒体待ちを入れた候補は合格条件（1〜9・4b）がすべて真、採用する。no_diskの画面も公式と一致

実施日: 2026-09-12（19:39〜20:05）
事前登録: [m7lv-...-preregistration](m7lv-no-disk-drive-wait-implementation-preregistration.md)・
追補: [m7lv-...-preregistration-addendum](m7lv-no-disk-drive-wait-implementation-preregistration-addendum.md)（条件4b）
仕様: 1.63節（第211版 `ce6946c`、手順2は第212版 `6af7942`で訂正）
HEAD: `555f3ed`（**測定前に単独コミット済み**。合格条件と数え方は本稿で動かしていない）

worktree上でBASE（実装前のHEAD）と候補を切り替えて測定した。BASEの生成器 sha256先頭
`6f62519f19c1`、候補 `4f0b85c0344b`。

## 結論

> **採用する。自作subの一般READ要求に、`SEEK`の後`SENSE DRIVE STATUS`のST3 bit3が
> 1になるまで繰り返す折り返し（+4バイト）を加えたところ、合格条件1〜9・4bがすべて真になった。
> no_diskの画面署名（frame 900）も公式と一致した——1.49節（`m7cn`）の模倣が画面で一致しなかったのは
> 待つ位置の違いによる、という1.62節の推定が、観測として裏付けられた。**

候補の中身: `_general_read_request`で`FDC_SEEK`の後、`SENSE DRIVE STATUS`→ST3のbit3を見て
0なら`SENSE DRIVE STATUS`へ戻る折り返し（+4バイト）。実装担当は仕様書（1.63節）と`src/`だけを
見て作った。

## 条件表

| 条件 | 内容 | 結果 |
|---|---|---|
| 1 | ビルド（窓の関門・変種の拒否0個） | **真**（2034→2038バイト、窓0x0800までの余白10バイト、変種フラグ21種すべて通過） |
| 2 | 門の全体 | **真**（使い捨てコミット上で`run_all_selftests.sh`実行、NGは置き場由来の`check_cleanroom.sh`1件だけ。HEAD基準の回帰ガード`early_response_rom_selftest.sh`も通過） |
| 3 | no_diskの+0要求長5・+0後に交換runなし | **真**（候補1回目・2回目とも。長さ5、+0の後の交換run 0本） |
| 4 | +0以降のFDCコマンド先頭3つ・READ DATA 0件・SENSE DRIVE STATUS 1000件以上・frame 760以降のsub PIO 0件 | **真**（先頭3つがSEEK・SENSE INTERRUPT STATUS・SENSE DRIVE STATUS、READ DATA 0件、SENSE DRIVE STATUS 92,182件、sub PIO 0件） |
| 4b | +0以降のSEEK・SENSE INTERRUPT STATUSがちょうど1件ずつ | **真**（SEEK 1件・SENSE INTERRUPT STATUS 1件） |
| 5 | frame 900の画面署名が公式と一致 | **真** |
| 6 | 既存の適合テスト（`m7lf`の同一性）が悪化しない | **真**（BASE対 候補1回目・2回目とも。(a)総合判定=適合、(b)OK行を失わない〔失った形0〕、(c)NG 3→3〔既知の陽性対照〕、(d)`--`〔未到達〕9→**6**。数字を伏せて初めて一致とみなされた行は既知の1本〔`m7le`で調べた試験用mainドライバ構成の陽性対照〕だけ） |
| 7 | 1.58節の失敗の形（9媒体）が変わらない | **真**（MA・ND・G-CRC・G-OK・DEL・IDCRC・MAMD・IDBAD・SDで混成のREAD DATA件数・連続・最長・単位がBASEと完全一致。G-OKは(14,0,1)単位0、他は(117,96,9)単位12） |
| 8 | `src/`の差分は一般READ要求の箇所だけ | **真**（`cand.diff`で4バイト追加のみ） |
| 9 | 決定論性（候補2回） | **一致**（判定行の集合・9媒体の数と単位・no_diskの数が一致） |

## `--`が9→6に減った3行（判定行の見出しのみ。画面本文・交換値は書かない）

- `B:媒体未挿入: main IN $FCは分岐（公式6672件／混成7448件）`
- `B:媒体未挿入-mixed: 画面期待値と不一致（事実報告。適合条件1〜5の失格にはしない）`
- `B:媒体未挿入: 公式一式と混成の画面出力が不一致（位置・分類は下記。失格にはしない）`

いずれもno_disk（媒体未挿入）に関する判定行で、5対6の分岐と画面不一致が解消したことに
対応する。3行のうち、数字を伏せて初めて一致とみなされた行はこの中には含まれない
（該当の1本は別の既知の陽性対照）。

## 記述（合否に使わない）

待ちの間のSENSE DRIVE STATUSは公式1フレームあたり1289.2件、候補653.8件（密度はおよそ
半分。`m7cn`の模倣も約661件/フレームだった。合わせていない）。媒体のある場面
（MA・G-OK・G-CRC・ND）で、frame 700以降・最初のREAD DATAより前のSENSE DRIVE STATUSは
公式・BASE・候補とも1件——媒体は起動時から入っていて入れ替えが起きていないので、
QUASI88の「入れ替え直後の1回だけbit3=0」は現れず、公式がbit3で待つという推定の裏付けにも
反証にもならなかった。場面のI/Oログは各10〜74MB・取りこぼし0件。

## 言えないこと

- エミュレータ上の振る舞いである。
- 公式の判定規則がbit3だとは言わない。
- 待ちの途中で媒体を差した後の続きは測っていない。
- 問い合わせの密度は公式と違う。

## 禁止の遵守

公式ROM・公式ディスク・`private/`の内容には触れていない。判定器は件数・真偽・一致記号・
判定行の見出しだけを出す。画面本文は書いていない。

## 根拠リンク

[m7lv 事前登録](m7lv-no-disk-drive-wait-implementation-preregistration.md)・
[m7lv 事前登録（追補）](m7lv-no-disk-drive-wait-implementation-preregistration-addendum.md)・
[m7lv測定（ST3 bit3）](m7lv-st3-two-side-media-signal.md)・
[m7lu](m7lu-no-disk-sub-drive-wait-diagnosis.md)・`src/l3_service/make_subrom.py`（`_general_read_request`）。
