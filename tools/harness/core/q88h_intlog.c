/*
 * q88h_intlog.c — PC88Behavior 計測ハーネス / 割り込み受理ログ
 * 詳細は q88h_intlog.h を参照。
 */

#include <string.h>
#include "q88h_intlog.h"

static q88h_intlog_t g_intlog;      /* メイン CPU */
static q88h_intlog_t g_intlog_sub;  /* サブ CPU（ディスク側） */

static q88h_intlog_t *ensure(q88h_intlog_t *l)
{
    if (l->magic != Q88H_INTLOG_MAGIC) {
        /* 初回アクセス時に初期化する。コア側の初期化順にもフロントエンド側の
         * 呼び出し順にも依存したくないため（q88h_iolog.c と同じ考え方）。 */
        memset(l, 0, sizeof(*l));
        l->magic   = Q88H_INTLOG_MAGIC;
        l->version = Q88H_INTLOG_VERSION;
        l->enabled = 0;
    }
    return l;
}

q88h_intlog_t *retro_q88h_intlog(void)     { return ensure(&g_intlog); }
q88h_intlog_t *retro_q88h_intlog_sub(void) { return ensure(&g_intlog_sub); }

void retro_q88h_intlog_reset(void)
{
    /* enabled はフロントエンドが起動のたびに明示的に設定し直す値なので、
     * ここでは触らない（q88h_iolog.c の retro_q88h_iolog_reset と同じ理由）。 */
    uint8_t en, en_sub;

    ensure(&g_intlog);
    ensure(&g_intlog_sub);
    en     = g_intlog.enabled;
    en_sub = g_intlog_sub.enabled;

    memset(&g_intlog,     0, sizeof(g_intlog));
    memset(&g_intlog_sub, 0, sizeof(g_intlog_sub));
    ensure(&g_intlog);
    ensure(&g_intlog_sub);

    g_intlog.enabled     = en;
    g_intlog_sub.enabled = en_sub;
}

void retro_q88h_intlog_set_enabled(int enabled)
{
    ensure(&g_intlog);
    ensure(&g_intlog_sub);
    g_intlog.enabled     = enabled ? 1 : 0;
    g_intlog_sub.enabled = enabled ? 1 : 0;
}

void retro_q88h_intlog_set_frame(uint32_t frame)
{
    ensure(&g_intlog);
    ensure(&g_intlog_sub);
    g_intlog.frame     = frame;
    g_intlog_sub.frame = frame;
}

void q88h_intlog_record(q88h_intlog_t *l, uint8_t im, uint8_t level,
                         uint16_t ret_pc, uint16_t handler_pc)
{
    q88h_intlog_ev_t *e;

    if (l->n_events >= Q88H_INTLOG_MAX_EVENTS) {
        l->n_dropped++;
        return;
    }

    e = &l->ev[l->n_events];
    l->n_events++;

    e->seq        = l->n_events;   /* 1始まりの通し番号 */
    e->frame      = l->frame;
    e->ret_pc     = ret_pc;
    e->handler_pc = handler_pc;
    e->im         = im;
    e->level      = level;
    e->pad[0] = e->pad[1] = 0;
}
