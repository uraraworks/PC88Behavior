/*
 * q88h_iolog.c — PC88Behavior 計測ハーネス / 順序付き I/O 記録
 * 詳細は q88h_iolog.h を参照。
 */

#include <string.h>
#include "q88h_iolog.h"

static q88h_iolog_t g_iolog;      /* メイン CPU */
static q88h_iolog_t g_iolog_sub;  /* サブ CPU（ディスク側） */

static q88h_iolog_t *ensure(q88h_iolog_t *l)
{
    if (l->magic != Q88H_IOLOG_MAGIC) {
        /* 初回アクセス時に初期化する。コア側の初期化順にもフロントエンド側の
         * 呼び出し順にも依存したくないため（q88h_trace.c / q88h_trap.c と同じ考え方）。 */
        memset(l, 0, sizeof(*l));
        l->magic   = Q88H_IOLOG_MAGIC;
        l->version = Q88H_IOLOG_VERSION;
        l->enabled = 0;
    }
    return l;
}

q88h_iolog_t *retro_q88h_iolog(void)     { return ensure(&g_iolog); }
q88h_iolog_t *retro_q88h_iolog_sub(void) { return ensure(&g_iolog_sub); }

void retro_q88h_iolog_reset(void)
{
    /* enabled はフロントエンドが起動のたびに明示的に設定し直す値なので、
     * ここでは触らない（q88h_trap.c の retro_q88h_trap_reset と同じ理由）。
     * map[0x10000] のようなでかい配列を保持しているわけではないので、
     * スカラ値を退避してから memset するだけで足りる。 */
    uint8_t en, en_sub;

    ensure(&g_iolog);
    ensure(&g_iolog_sub);
    en     = g_iolog.enabled;
    en_sub = g_iolog_sub.enabled;

    memset(&g_iolog,     0, sizeof(g_iolog));
    memset(&g_iolog_sub, 0, sizeof(g_iolog_sub));
    ensure(&g_iolog);
    ensure(&g_iolog_sub);

    g_iolog.enabled     = en;
    g_iolog_sub.enabled = en_sub;
}

void retro_q88h_iolog_set_enabled(int enabled)
{
    ensure(&g_iolog);
    ensure(&g_iolog_sub);
    g_iolog.enabled     = enabled ? 1 : 0;
    g_iolog_sub.enabled = enabled ? 1 : 0;
}

void retro_q88h_iolog_set_frame(uint32_t frame)
{
    ensure(&g_iolog);
    ensure(&g_iolog_sub);
    g_iolog.frame     = frame;
    g_iolog_sub.frame = frame;
}

void q88h_iolog_record(q88h_iolog_t *l, uint8_t kind, uint8_t port,
                        uint8_t value, uint16_t pc)
{
    q88h_iolog_ev_t *e;

    if (l->n_events >= Q88H_IOLOG_MAX_EVENTS) {
        l->n_dropped++;
        return;
    }

    e = &l->ev[l->n_events];
    l->n_events++;

    e->seq   = l->n_events;   /* 1始まりの通し番号 */
    e->frame = l->frame;
    e->pc    = pc;
    e->kind  = kind;
    e->port  = port;
    e->value = value;
    e->pad   = 0;
}
