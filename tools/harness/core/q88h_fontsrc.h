/*
 * q88h_fontsrc.h — PC88Behavior 計測ハーネス / フォント供給源の可視化
 *
 * docs/spec/l2-font.md 第3節は「font_mem 系が、ROM読み込みの成否に関係なく
 * 出所不明の built_in_font_* に差し替わる」経路を7箇所挙げている（同節の表）。
 * これでは自作フォントを置いても、実際にどの供給源が font_mem を埋めたのか
 * 外部から確認できない。このファイルは「どの領域が、どの供給源で埋まったか」
 * という**タグと書き込み回数だけ**を記録する。
 *
 * グリフのバイト列そのものは一切記録しない。CRC32（fontsrc_crc32）だけは
 * 例外的に持つが、これは「同じ内容かどうか」を比較するための128bit未満の
 * ダイジェストであり、そこからグリフのバイト列を復元することはできない
 * ——q88h_trap.h が AF/BC/DE/HL のレジスタ値は記録してもROMの中身は
 * 記録しないのと同じ考え方（docs/PLAN.md 第5節）。
 *
 * シンボル名を retro_ で始めているのは q88h_trace.h 等と同じ理由。
 * 上流の link.T が `global: retro_*; local: *;` でエクスポートを絞っているため。
 */
#ifndef Q88H_FONTSRC_H_INCLUDED
#define Q88H_FONTSRC_H_INCLUDED

#include <stdint.h>

#define Q88H_FONTSRC_MAGIC   0x4C423838u   /* "88BL" (LE)。他の q88h_* バッファと
                                             * 同じ合言葉でよい（バッファ取り違え検出用
                                             * であって、ファイル種別の判別には使っていない） */
#define Q88H_FONTSRC_VERSION 1u

/* 領域: font_mem / font_mem2 / font_mem3 それぞれの ANK半分・グラフィック半分。
 * docs/spec/l2-font.md 1節の構成（各4096バイト = 2048(ANK) + 2048(graph)）と対応させる。 */
enum {
    Q88H_FONTSRC_REGION_FONT1_ANK = 0,   /* font_mem[0x000-0x7FF]  実際に画面へ出る */
    Q88H_FONTSRC_REGION_FONT1_GRAPH,     /* font_mem[0x800-0xFFF]  実際に画面へ出る */
    Q88H_FONTSRC_REGION_FONT2_ANK,       /* font_mem2[0x000-0x7FF] 描画には使われない(1節) */
    Q88H_FONTSRC_REGION_FONT2_GRAPH,     /* font_mem2[0x800-0xFFF] 描画には使われない(1節) */
    Q88H_FONTSRC_REGION_FONT3_ANK,       /* font_mem3[0x000-0x7FF] 描画には使われない(1節) */
    Q88H_FONTSRC_REGION_FONT3_GRAPH,     /* font_mem3[0x800-0xFFF] 描画には使われない(1節) */
    Q88H_FONTSRC_REGION_COUNT
};

/* 供給源のタグ。「どうやって埋まったか」だけを表す語彙で、値そのものは含まない。 */
enum {
    Q88H_FONTSRC_NONE = 0,       /* まだ一度も設定されていない（初期値） */
    Q88H_FONTSRC_ROM_FILE,       /* 外部ROMファイルを読み込み、内容をそのまま使用 */
    Q88H_FONTSRC_KANJI_DERIVED,  /* FONT.ROM が無く、漢字ROM由来データをANK代わりに使用
                                   * （docs/spec/l2-font.md 2節「漢字ROMを使わずANKだけで
                                   * 動くか」の上流フォールバックに相当。実際に kanji_rom
                                   * の読み込みが成功している場合のみ使う——5節の方針5） */
    Q88H_FONTSRC_UNAVAILABLE,    /* 代替データを持たない。0埋め（空白グリフ）にした。
                                   * 出所不明の built_in_font_* だった箇所の置き換え。
                                   * font.h 削除の理由は CLAUDE.md 情報の流れ参照 */
    Q88H_FONTSRC_BUILTIN_UNKNOWN /* [font.h 削除前の過渡状態でのみ使用] 出所不明の
                                   * built_in_font_* をまだ使っている、という自己申告タグ。
                                   * font.h 削除後のコードはこのタグを一切出さない。 */
};

typedef struct {
    uint32_t magic, version;

    /* 領域ごとの「現在の」供給源タグ。複数回書かれた場合は最後に書かれた値
     * （＝実際に画面へ出る値）が残る。 */
    uint8_t  region_src[Q88H_FONTSRC_REGION_COUNT];
    uint8_t  pad[2];

    /* 領域ごとに何回書き込まれたか。1 が正常、2 以上は二重ロードの兆候
     * ——l2-font.md 3節が問題にした「memory_allocate() の結果を
     * libretro.c が踏みつぶす」構図を、タグの中身を見なくても検出できる。 */
    uint32_t region_writes[Q88H_FONTSRC_REGION_COUNT];

    /* 領域ごとの内容の CRC32（IEEE 802.3 多項式）。グリフのバイト列そのもの
     * ではなく、外部ファイルの内容が font_mem まで欠落・混入なく届いたかを
     * フロントエンド側で独立に比較するためのダイジェスト。 */
    uint32_t region_crc32[Q88H_FONTSRC_REGION_COUNT];
} q88h_fontsrc_t;

#ifdef __cplusplus
extern "C" {
#endif

q88h_fontsrc_t *retro_q88h_fontsrc(void);

/* 採取内容を全消去する。q88h_trap.c の retro_q88h_trap_reset と同じ理由で、
 * 呼び出しごとに前回の起動の痕跡を残さない。 */
void retro_q88h_fontsrc_reset(void);

/* 領域の供給源タグ・書き込み回数・CRC32 を更新する。パッチ側
 * （memory.c / LIBRETRO/libretro.c）の各フォント読み込み分岐から呼ぶ。
 * data/len を渡すと CRC32 を計算して記録する（len==0 なら 0埋め扱いで
 * crc32(空) を記録する）。 */
void q88h_fontsrc_set(int region, uint8_t src, const uint8_t *data, uint32_t len);

/* データを取らず、タグと書き込み回数だけ更新する版
 * （呼び手が CRC32 を計算する材料を持たない/不要な場合用）。 */
void q88h_fontsrc_set_tag(int region, uint8_t src);

#ifdef __cplusplus
}
#endif

#endif /* Q88H_FONTSRC_H_INCLUDED */
