# M5 下ごしらえ — フォント供給源の可視化 / font.h 削除 自己検証記録

測定日: 2026-08-07
対象: `tools/harness/fontsrc_selftest.sh`。公式 ROM は一切使わない
（すべて `make_test_rom.py --enable-font` が生成する自作の合成データ）。

---

## 何を作ったか

`docs/spec/l2-font.md` 3節が挙げた「font_mem 系が ROM 読み込みの成否に
関係なく出所不明の `built_in_font_*`（`font.h`）へ差し替わる」経路の
下ごしらえとして:

- `tools/harness/core/q88h_fontsrc.h` / `.c` — font_mem/font_mem2/font_mem3
  の6領域（ANK/GRAPH × 3面）について、供給源タグ・書き込み回数・CRC32
  だけを記録する（グリフのバイト列は一切記録しない）。
- `tools/patches/0007-font-src.patch` — 供給源タグの配線のみ（挙動は変えず、
  当時まだ `font.h` を使っていた分岐を含めてタグを付けた「可視化」段階）。
- `tools/patches/0008-font-remove-builtin.patch` — `font.h` 削除に伴う
  参照修正。`built_in_font_*` を使っていた分岐を 0埋め＋`UNAVAILABLE`タグに
  置き換え、かつ「ROM読み込みに成功した内容を上書きしない」ように分岐を
  直した（font_mem・font_mem2・font_mem3 の ANK/GRAPH 計6箇所のうち、
  実際に「成功しても上書きされていた」バグが有ったのは font_mem ANK・
  font_mem GRAPH・font_mem2 ANK・font_mem3 GRAPH の4箇所）。
  併せて `load_system_file()` に `filestream_read()` の戻り値チェックを足し、
  KANJI1.ROM のANKフォールバックには実際の読み込み成否
  （`q88h_knj1_loaded`）のガードを追加した。
- `tools/setup_harness.sh` に `src/font.h` の rm と、削除後コードに
  `built_in_font_*` の実参照が残っていないことの検査を追加。
- `tools/harness/make_test_rom.py` に `--enable-font` を追加。
  自作パターン（`byte[i] = (i*137+59) & 0xFF`）の FONT.ROM (4096 bytes) と、
  期待 CRC32 を標準出力する。
- `tools/harness/fontsrc_selftest.sh` — 本ファイルが記録する自己検証。

## 確認した内容（すべて自作の合成ROMのみ使用）

1. FONT.ROM を用意した場合、font_mem ANK/GRAPH とも `ROM_FILE` タグになり、
   CRC32 が生成時の期待値と一致する（外部ファイルの内容が font_mem —
   実際に画面へ出る唯一のバッファ（l2-font.md 1節）—まで欠落・混入なく
   届いている）。
2. FONT.ROM も KANJI1.ROM も無い場合、font_mem ANK は `UNAVAILABLE` タグ・
   CRC32=00000000（0埋め）になる。
3. FONT.ROM が無く KANJI1.ROM だけ（自作パターン）がある場合、font_mem ANK
   は `KANJI_DERIVED` タグになる——「実際に読み込みが成功した場合だけ」
   フォールバックが効くことの確認（`q88h_knj1_loaded` ガード）。
4. 書き込み回数はいずれも 2 になる。内訳は `memory_allocate()`
   （memory.c、上流の標準ロード経路）の空振り1回＋`libretro.c` 独自ロードの
   実ロード1回。**この「二重に書く」構造そのもの（l2-font.md 6節「経路を
   1本化する」）は今回のセッションでは解消していない**——
   `memory_allocate()` 側は `osd_dir_rom()` が libretro 版では常に NULL の
   ため実際のファイル探索は必ず失敗し、0埋めを書き込むだけの無害な空振りに
   終わる。今回閉じたのは「成功時に中身を上書きする」実害のある経路だけで、
   構造の一本化は次のマイルストーンへ持ち越し。

## わざと壊して検査が落ちることの確認

`src/LIBRETRO/libretro.c` の Font1 成功分岐（`load_system_file(FONT_ROM,...)`
が成功した直後）に、以下の1行を一時的に復活させた:

```
memset(&font_mem[0x000], 0xAA, 0x800); /* PC88Behavior selftest: わざと壊す */
```

（旧コードが `built_in_font_ANK` で上書きしていたのと同じ形の破壊——
「読み込みに成功したのに中身を差し替える」バグの再現）

- 再ビルドして `fontsrc_selftest.sh` を実行した結果:
  `NG: font_mem ANK の CRC32 が 7AC10820 。期待値は FC8B8B71` で **失敗した**
  （終了コード1）。CRC32 による照合が意図どおり機能していることを確認した。
- 該当行を削除して再ビルドし、`fontsrc_selftest.sh` が再び合格することを
  確認した（終了コード0）。

## 次に測るべきこと（今回はやらない）

- `font_mem`/`font_mem2`/`font_mem3` の読み込み経路を `memory_allocate()`
  と `libretro.c` の一本に統合する（l2-font.md 6節1）。今回は「成功時の
  上書き」だけを閉じ、「無害だが二重に書く」構造は残した。
- グラフィック文字（0x100-0x1FF 相当）用データの用意（l2-font.md 7節、
  unscii-8 は対象外）。
- 自作 ANK フォント（unscii-8 由来、l2-font.md 4節）の実装。今回は
  検証用の合成データ（`make_test_rom.py --enable-font`）のみで確認した。
