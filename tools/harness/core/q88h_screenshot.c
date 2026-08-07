/*
 * q88h_screenshot.c — PC88Behavior 計測ハーネス / 画面ピクセルスナップショット
 * 詳細は q88h_screenshot.h を参照。
 */

#include <string.h>
#include "q88h_screenshot.h"

/* snapshot.c にパッチ（0009-screenshot.patch）で足す薄いラッパー。
 * make_snapshot()（static）を呼び、640x400 のインデックス画像とパレットから
 * R,G,B バイト列を組み立てて rgb_out へ書く。ロジックはすべて snapshot.c 側
 * （上流のVRAM2SCREEN変換）にあり、ここでは複製しない。 */
extern void q88h_snapshot_capture(unsigned char *rgb_out);

static q88h_screenshot_t g_shot;

static q88h_screenshot_t *ensure(void)
{
    if (g_shot.magic != Q88H_SCREENSHOT_MAGIC) {
        memset(&g_shot, 0, sizeof(g_shot));
        g_shot.magic   = Q88H_SCREENSHOT_MAGIC;
        g_shot.version = Q88H_SCREENSHOT_VERSION;
    }
    return &g_shot;
}

q88h_screenshot_t *retro_q88h_screenshot(void)
{
    return ensure();
}

void retro_q88h_screenshot_capture(void)
{
    q88h_screenshot_t *s = ensure();
    q88h_snapshot_capture(s->rgb);
    s->captured = 1;
}
