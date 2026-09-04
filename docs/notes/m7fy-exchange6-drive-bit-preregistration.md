# m7fy: 交換#6経路のドライブビットを故障注入で切り分ける（事前登録）

実施日: 2026-09-04

## 位置づけ

本稿は`m7fx`の「次にやること」の1つ、**#6-ii（交換#6経路）**を対象にした
測定を実装より前に事前登録するものである。**本稿では測定しない。
エミュレータは動かさない。`src/`・`tools/`も変更しない。実装と測定は
次稿で行う。**

`m7fx`は、`_exchange6_prepare_sector`（`src/l3_service/make_subrom.py`
2366行、以下すべて本稿執筆時点の行番号）が、交換#6のREAD座標を正規化
するために`REQ_HDR+2`を`REQ_HDR+4`（C、目的シリンダ）へ転記したあと、
その転記元である`REQ_HDR+2`自体はそのまま残し、`jr`で
`_exchange3_prepare_sector`（2338行）へ落ちることを読解で確認した。
その先の`_seek_sense_f7_read_shared`（1592行）が呼ぶ`FDC_SEEK`
（1556行）・`FDC_SENSE_DRIVE_STATUS`（1541行）は、いずれも**同じ
`REQ_HDR+2`のbit0を1.46節のドライブ指定伝播として読む**（1558-1567行、
1543-1547行）。さらに`FDC_SEEK`はbit0を`REQ_UNIT_HEAD`（0x430E）へ
`OR`で合成し（1565-1567行）、これを`FDC_READ_SECTOR`（1879行）が
READ DATAのunit/head引数として使う。**つまりSEEK・SENSE DRIVE
STATUS・READ DATAの3つが、いずれも同じ`REQ_HDR+2`のbit0を経由して
末端のドライブ選択を決めている。**

一方、この同じ`REQ_HDR+2`は、`_exchange6_prepare_sector`自身が
「シリンダ値の転記元」として明示的に読み書きに使ったバイトでもある
（1.32節）。**1つのバイトがシリンダ値とドライブ指定の2つの意味で
使われている**という、`m7fx`が読解だけで具体的に特定できた唯一の
箇所を、本稿から測定で切り分ける。

## 転記の実物（2366-2377行）

```
2366  a.label("_exchange6_prepare_sector")
2367  a.ld_a(0x02)
2368  a.ld_mem_a(BOOT_READ_PAIR_STAGE)
2369  a.ld_hl_imm(REQ_HDR + 2)
2370  a.ld_a_hl()
2371  a.ld_hl_imm(REQ_HDR + 4)
2372  a.ld_hl_a()
2373  a.ld_hl_imm(REQ_HDR + 0)
2374  a.ld_a_hl()
2375  a.ld_hl_imm(REQ_HDR + 6)
2376  a.ld_hl_a()
2377  a.jr("_exchange3_prepare_sector")
```

転記2組（`REQ_HDR+2`→`REQ_HDR+4`、`REQ_HDR+0`→`REQ_HDR+6`）は2369-2376行
で完結する。以降で扱う3つの故障注入は、**2376行の直後・2377行の`jr`の
直前**へ置く。この位置は転記が終わった後なので、注入は`REQ_HDR+4`（C）
には一切影響せず、**ドライブ指定だけを独立に動かせる**——これが本介入の
要点であり、注入位置をここに選んだ理由である。

`_exchange3_prepare_sector`（2338行）は入口で`REQ_HDR+4`を読み直して
Aへ入れ（2343-2344行）、これをSEEKの目的シリンダ引数として使う。この
読み出しは注入位置より後であり、注入対象の`REQ_HDR+2`には触れない
（`REQ_HDR+4`は転記済みの値のまま）。

## `BOOT_READ_PAIR_STAGE`への副作用が無いことの確認

`_exchange6_prepare_sector`は入口（2367-2368行）で`BOOT_READ_PAIR_STAGE`
（0x430C）へ`0x02`を書く。`_exchange3_prepare_sector`の共有本体は、
`_seek_sense_f7_read_shared`呼び出し後（2352行）に`BOOT_READ_PAIR_STAGE`
を読み、`0x02`または`0x04`かどうかで単発応答保留（`EXCHANGE3_RESPONSE_
PENDING`）を立てるかどうかを分岐する（2352-2358行）。本稿の3つの注入は
いずれも`REQ_HDR+2`だけを対象とし、`BOOT_READ_PAIR_STAGE`にも
`REQ_HDR+4`にも触れないため、**この分岐（交換#6が単発応答保留を立てる
という既存の挙動）には副作用を与えない**ことを読解で確認した。

## 事前登録する介入（3つの故障注入フラグ）

いずれも上記2376行の直後・2377行の`jr`の直前へ、`if break_...:`ガード
付きで置く。**3つとも`if break_...:`ガードの内側に置くので、既定ビルド
（全`break_*`がFalse）には1バイトも影響しない。**

1. `break_exchange6_drive_bit_clear`: `REQ_HDR+2`のbit0を0へ倒す。
   符号化案: `a.ld_hl_imm(REQ_HDR + 2)`に続けて`a.db(0xCB, 0x86)`
   （`RES 0,(HL)`）。計5バイト。
2. `break_exchange6_drive_bit_set`: 同位置でbit0を1へ倒す。
   符号化案: `a.ld_hl_imm(REQ_HDR + 2)` + `a.db(0xCB, 0xC6)`
   （`SET 0,(HL)`）。計5バイト。
3. **陽性対照** `break_exchange6_cylinder`: 転記済みの`REQ_HDR+4`（C）の
   ほうを別値へ倒す。具体的な倒し方は実装時に決めてよいが、**末端に
   必ず差が出ることが期待される注入**であること（例: `INC (HL)`で
   `REQ_HDR+4`を1増やし、SEEKの目的シリンダを変える案が候補。値の
   具体的な選び方は実装時に決める）。

**`RES 0,(HL)`（オペコード`0xCB 0x86`）と`SET 0,(HL)`（オペコード
`0xCB 0xC6`）は、いずれもZ80の定義済み命令である。** 公開されている
Z80命令表の事実であり、公式ROMの解析結果ではない。本リポジトリの
`Asm`クラス（475行）にはこの2命令のニーモニックが実装されていない
（`inc_hl`・`ld_a_hl`等はあるが`res`/`set`系のビット命令が無い）ため、
`db()`（498行、命令1個ぶんを1回の`db()`呼び出しで発行する既存の作法、
`m7fw`の`INC (HL)`と同じやり方）で直接発行する。**「未定義命令」では
なく「本リポジトリの`Asm`クラスに未実装」である**——`m7fw`「10) 親に
よる訂正」で`INC (HL)`について訂正された経緯を踏まえ、本稿では最初
からこの表現で書く。

## 事前登録する合格条件（測定前に固定する。後から動かさない）

判定に数値比較を使わない（`m7fg`が確定した基準）。

1. **既定ビルドのバイト不変**: 実装後の既定ビルド（全`break_*`がFalse）
   のサブROMが、実装前（現HEAD）の既定ビルドとSHA-256で完全一致すること。
   固定長8192バイトなのでファイルサイズは指標に使わない。**バイト一致は
   機能検証も兼ねる**——既定ビルドが1バイトも変わらなければ、WRITE経路・
   READ DATA経路・容量関門への退行はいずれも起こりえない。この論法は
   `m7fw`1)・`m7ck`（1.46節根拠）が同じ形で使ったものを踏襲する。
2. **容量関門**: 3つの注入ビルドそれぞれで`build()`が`SystemExit`を
   出さないこと。判定は`SystemExit`の有無だけで行い、使用量の数値比較は
   判定に使わない。既定ビルドの32構成（8構成×
   `PC88_BULK_READ_INTERVENTION_LIMIT`=1〜4）は条件1のバイト一致で
   自動的に担保されるが、念のため再確認する位置づけで書く。
3. **陽性対照（経路を踏んだ証拠）**: `break_exchange6_cylinder`が、
   ベースラインに対して末端に差を出すこと。**これが差を出さなければ、
   測定器がこの経路を見ていないか、そもそも交換#6が踏まれていないという
   意味であり、条件4・5の結果は解釈できない。** その場合は「効かなかった」
   ではなく「**測れていない**」と結論し、測定条件の選定からやり直す。
   加えて、陽性対照ROMのSHAがベースラインと異なること、および**
   q88measureへ実際に渡した`--rom-dir`内のサブROMのSHAが、全runで毎回
   ビルド直後の期待SHAと一致すること**を要件に含める
   （`feedback_positive_control_takes_its_own_shortcut.md`・
   `feedback_fault_injection_must_change_the_artifact.md`の論点を踏まえる）。
4. **合格条件を先にベースラインへ当てる**: 条件3・5の判定規則を、まず
   ベースライン同士（ベースライン2run）に当てて「差なし」と出ることを
   確認してから、注入版に当てる
   （`feedback_run_the_acceptance_rule_against_baseline.md`の教訓）。
5. **本測定**: `break_exchange6_drive_bit_clear`と
   `break_exchange6_drive_bit_set`のそれぞれについて、ベースラインとの
   末端の差の有無を見る。見る指標は
   （a）交換#6経路の`SEEK`/`SENSE DRIVE STATUS`/`READ DATA`のunit/head
   分類の一致・不一致、（b）FDCコマンド種別列の全長一致、
   （c）画面の行数・文字数・SHA-256。**値は記録しない**（種別名・段・
   一致／不一致・件数・SHAのみ）。
6. **決定論性**: ベースライン・注入3種とも各2run新規測定し、伏せ字後の
   バイト列が自己一致すること。

一つでも欠ければ合格と呼ばない。

## 事前登録する予測（測定前に3通りとも書く）

- **H1（bit0が効く）**: clearとsetで末端に差が出る、または互いに違う
  結果になる → この経路はシリンダ由来のバイトのbit0を実際にドライブ
  指定として使っており、`m7fx`が読解で特定した意味の混線が機能的に
  効いている。→ 次稿で修正介入を設計する。
- **H0（bit0が効かない）**: clear・setとも末端がベースラインと完全一致
  する（かつ**陽性対照は差を出している**）→ この経路の観測可能な末端に
  bit0は影響しない。混線は読解上のものにとどまる。→ **直さない判断の
  根拠として記録して終える。** 「差が無かったから安全」ではなく
  「陽性対照が通った上で差が無かった」と書く。
- **測定不能**: 陽性対照が差を出さない → 上記条件3のとおり、測定条件の
  選定からやり直す。

## 調べて書くこと: どの測定条件で交換#6が踏まれるか

**確定的な特定はできなかったが、有力な手がかりが1つある。**

1.46節第113版（`docs/spec/l3-subrom.md` 2233-2246行）は、条件O・条件M
の起動ログを`tools/compare_l3_entry_fdc.py`へ`--after-frame 0`で渡して
再解析し、**「起動区間」に`READ DATA` 9件を含む区間が入っていること、
その9件のunit/headが両条件で完全一致したこと**を記録している。1.32節
（交換#6/#7）・1.33節（交換#11/#12）・1.34節（交換#14、累積7/11/12件
境界でのFDCと高速バルク駆動）は、いずれも診断ディスク起動シーケンスの
中でFDC READ系（＝`READ単位`＝SEEK・SENSE INTERRUPT STATUS・SENSE DRIVE
STATUS・READ DATAの4コマンド単位、`compare_l3_entry_fdc.py`の
`compact()`が畳む単位）を発行する箇所であり、交換#3(1)・交換#6(1)・
交換#11(1)・交換#14（`BULK_READ_INTERVENTION_LIMIT`に応じて複数）を
合算すると9件に符合しうる。**したがって`tools/compare_l3_entry_fdc.py
--after-frame 0 --list-all-stages`（`m7ex`・1.46節第113版が使った形）が、
交換#6のSEEK/SENSE DRIVE STATUS/READ DATA段を含む区間を観測できる
可能性が高い。**

ただし、**9件のうちどの段番号（`--list-all-stages`が振る1起点の通し
番号）が交換#6に対応するかは、本稿の読解範囲では特定できていない。**
`tools/analyze_boot_exchange.py`（起動シーケンスのSEND/RECV runを
時間窓で束ねる器材）や`tools/analyze_request_kinds.py`（受信runの先頭
バイト・run長で要求種別を分類する器材）を使えば、交換#6の受信run
（1.36節がいう先頭バイト`0x02`・run長5の窓、`m7fx`の#6-ii到達経路と
同じもの）から対応するSEEK段を絞り込める可能性があるが、**本稿ではその
絞り込み作業自体は行っていない。次稿の測定実施時に、これらの器材を
使って段番号を特定し、条件3の陽性対照（`break_exchange6_cylinder`が
その段に差を出すこと）で特定自体を検証する。**

`diag_l3_mixed.py`はWRITE経路寄りの器材（`m7fw`5)節参照）であり、
READ経路の交換#6には`compare_l3_entry_fdc.py`のほうが直接的に対応する
と考えられるが、これも実測で確認していない推測である。

## 情報境界

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容は読んでいない。本稿は既存の`docs/spec/l3-subrom.md`・
`docs/notes/m7fx-*.md`・`docs/notes/m7fw-*.md`・`docs/notes/m7ft-*.md`と
自作`src/l3_service/make_subrom.py`のコード読解のみで構成した。値
（バイト値・データポート値）は一切書いていない。Z80の命令オペコード
（`0xCB 0x86`・`0xCB 0xC6`）は公開命令表の事実として明記したが、これは
禁止事項が対象とする「ROM由来のバイト列」ではない。行番号・ラベル名・
分岐条件のみを記録した。測定・ビルド・エミュレータ実行はいずれも
行っていない。

## 根拠リンク

[m7fw](m7fw-boot-drive-selector-adoption.md)・
[m7fx](m7fx-fdc-seek-propagation-callers-reading.md)・
[m7ft](m7ft-boot-drive-selector-both-sides-preregistration.md)・
[m7fr](m7fr-boot-drive-selector-preregistration.md)・
[m7fs](m7fs-boot-drive-selector-results.md)・
[m7fv](m7fv-capacity-compression-results.md)・
[m7ex](m7ex-boot-region-drive-selector-difference.md)・
L3仕様1.22節・1.25〜1.28節・1.32節・1.33節・1.34節・1.46節・
自作`src/l3_service/make_subrom.py`。
