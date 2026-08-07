/*
 * q88h_trace.c — PC88Behavior 計測ハーネス / バスアクセス採取
 * 詳細は q88h_trace.h を参照。
 */

#include <string.h>
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
