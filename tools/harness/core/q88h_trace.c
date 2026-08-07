/*
 * q88h_trace.c — PC88Behavior 計測ハーネス / バスアクセス採取
 * 詳細は q88h_trace.h を参照。
 */

#include <string.h>
#include "quasi88.h"
#include "memory.h"
#include "q88h_trace.h"

static q88h_trace_t g_trace;

q88h_trace_t *retro_q88h_trace(void)
{
    if (g_trace.magic != Q88H_TRACE_MAGIC) {
        /* 初回アクセス時に初期化する。コア側の初期化順に依存したくないため */
        memset(&g_trace, 0, sizeof(g_trace));
        g_trace.magic   = Q88H_TRACE_MAGIC;
        g_trace.version = Q88H_TRACE_VERSION;
    }
    return &g_trace;
}

void retro_q88h_trace_reset(void)
{
    memset(&g_trace, 0, sizeof(g_trace));
    g_trace.magic   = Q88H_TRACE_MAGIC;
    g_trace.version = Q88H_TRACE_VERSION;
}

/*
 * テキスト VRAM の読み出し。
 *
 * 「打鍵が届いているか」「コマンドが実行されたか」を確かめるために要る。
 * 画面に出ている文字は ROM を実行した結果として外部から観測できるものであり、
 * ROM のバイト列そのものではない。測ってよい対象（docs/PLAN.md 第5節の表）。
 *
 * PC-88 のテキスト画面は 1 行あたり 80 バイトの文字コードに続けて
 * 属性が並ぶ構成で、行の間隔は 120 バイト。既定の先頭は F3C8h。
 */
void retro_q88h_text(uint8_t *dst, uint32_t rows, uint32_t cols, uint32_t stride)
{
    uint32_t r, c;
    for (r = 0; r < rows; r++)
        for (c = 0; c < cols; c++)
            dst[r * cols + c] = main_ram
                ? main_ram[(Q88H_TEXT_BASE + r * stride + c) & 0xFFFF]
                : 0;
}
