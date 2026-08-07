/*
 * q88h_screenshot.h — PC88Behavior 計測ハーネス / 画面ピクセルスナップショット
 *
 * これまでの計測フック（q88h_trace / q88h_fontsrc 等）は「ROM がどこまで
 * 届いたか」を見るもので、font_mem（フォントが載るバッファ）まで届いた
 * ことしか確認できなかった。バッファに届いた ≠ 画面に出た、という点は
 * このプロジェクトで繰り返し踏んできた型（docs/notes/m4c-int-log.md 等）
 * なので、末端＝実際に描画されたピクセルまで見るためのフックを足す。
 *
 * ロジックは複製しない。上流 QUASI88 には既に「VRAM/フォントの内容を
 * 640x400 のインデックス画像へ変換し、パレットを適用してファイルへ書く」
 * 経路（snapshot.c の make_snapshot() + screen-snapshot.c の
 * VRAM2SCREEN_ALL 系ルーチン）がある。これは実際の描画ループ
 * （screen-vram*.h）と同じ変換テーブルを使うので、フロントエンドの
 * libretro video_cb 用バッファを覗くより忠実——ここには公式ROMも
 * ROM由来のバイト列も一切関係しない、上流のBSD-3ソースコードの
 * 変換ロジックそのもの。
 *
 * make_snapshot() は snapshot.c 内の static 関数なので、このヘッダの
 * 実装（q88h_screenshot.c）からは呼べない。そこで snapshot.c 側に
 * ごく薄い1関数のラッパー q88h_snapshot_capture() だけをパッチで足し
 * （tools/patches/0009-screenshot.patch）、ロジックはそのまま使う。
 *
 * シンボル名を retro_ で始めているのは他の q88h_* と同じ理由。
 * 上流の link.T が `global: retro_*; local: *;` でエクスポートを絞って
 * いるため（Linux ビルドでの話。macOS では制限が掛からないことを
 * 確認済みだが、移植性のため合わせておく）。
 */
#ifndef Q88H_SCREENSHOT_H_INCLUDED
#define Q88H_SCREENSHOT_H_INCLUDED

#include <stdint.h>

#define Q88H_SCREENSHOT_MAGIC   0x53423838u  /* "88BS" (LE) */
#define Q88H_SCREENSHOT_VERSION 1u

#define Q88H_SCREENSHOT_W 640
#define Q88H_SCREENSHOT_H 400

typedef struct {
    uint32_t magic, version;

    uint8_t captured;   /* retro_q88h_screenshot_capture() が1回以上呼ばれたら1 */
    uint8_t pad[3];

    /* R,G,B インターリーブ、行優先、640x400。パレット適用済みの
     * そのままのピクセル値であって、圧縮も変換もしていない。 */
    uint8_t rgb[Q88H_SCREENSHOT_W * Q88H_SCREENSHOT_H * 3];
} q88h_screenshot_t;

#ifdef __cplusplus
extern "C" {
#endif

q88h_screenshot_t *retro_q88h_screenshot(void);

/* 今の画面状態（VRAM+フォント+パレット）を1枚キャプチャして rgb[] へ格納する。
 * 呼ぶたびに上書きする——連番保存はフロントエンド側の役目にする。 */
void retro_q88h_screenshot_capture(void);

#ifdef __cplusplus
}
#endif

#endif /* Q88H_SCREENSHOT_H_INCLUDED */
