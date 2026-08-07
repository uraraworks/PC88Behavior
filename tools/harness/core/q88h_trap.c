/*
 * q88h_trap.c — PC88Behavior 計測ハーネス / トラップROM足場
 * 詳細は q88h_trap.h を参照。
 */

#include <string.h>
#include "q88h_trap.h"

static q88h_trap_t g_trap;      /* メイン CPU */
static q88h_trap_t g_trap_sub;  /* サブ CPU（ディスク側） */

static q88h_trap_t *ensure(q88h_trap_t *t)
{
    if (t->magic != Q88H_TRAP_MAGIC) {
        /* 初回アクセス時に初期化する。コア側の初期化順にもフロントエンド側の
         * 呼び出し順にも依存したくないため（q88h_trace.c と同じ考え方）。 */
        memset(t, 0, sizeof(*t));
        t->magic   = Q88H_TRAP_MAGIC;
        t->version = Q88H_TRAP_VERSION;
        t->mode    = Q88H_TRAP_OFF;
    }
    return t;
}

q88h_trap_t *retro_q88h_trap(void)     { return ensure(&g_trap); }
q88h_trap_t *retro_q88h_trap_sub(void) { return ensure(&g_trap_sub); }

void retro_q88h_trap_reset(void)
{
    /* map と mode はフロントエンドが起動のたびに明示的に設定し直す値なので、
     * ここでは触らない。触ってしまうと「リセットしたらトラップが消えていた」
     * という無言の変化になり、reset の呼びどころを間違えたときに気づけない。 */
    uint8_t  map[0x10000],  map_sub[0x10000];
    uint8_t  mode,          mode_sub;

    memcpy(map,     g_trap.map,     sizeof(map));
    memcpy(map_sub, g_trap_sub.map, sizeof(map_sub));
    mode     = g_trap.mode;
    mode_sub = g_trap_sub.mode;

    memset(&g_trap,     0, sizeof(g_trap));
    memset(&g_trap_sub, 0, sizeof(g_trap_sub));
    ensure(&g_trap);
    ensure(&g_trap_sub);

    memcpy(g_trap.map,     map,     sizeof(map));
    memcpy(g_trap_sub.map, map_sub, sizeof(map_sub));
    g_trap.mode     = mode;
    g_trap_sub.mode = mode_sub;
}

void q88h_trap_record(q88h_trap_t *t, uint16_t addr, uint8_t kind,
                       uint16_t caller, uint16_t prev_fetch, uint16_t sp,
                       uint16_t af, uint16_t bc, uint16_t de, uint16_t hl)
{
    q88h_trap_ev_t *e;

    if (kind == Q88H_TRAP_EXEC) t->exec_hits[addr]++;
    else                        t->data_hits[addr]++;

    if (t->n_events >= Q88H_TRAP_MAX_EVENTS) {
        t->n_dropped++;
        return;
    }

    e = &t->ev[t->n_events];
    t->n_events++;

    e->seq        = t->n_events;   /* 1始まりの通し番号 */
    e->addr       = addr;
    e->caller     = caller;
    e->prev_fetch = prev_fetch;
    e->sp         = sp;
    e->af      = af;
    e->bc      = bc;
    e->de      = de;
    e->hl      = hl;
    e->kind    = kind;
    e->pad     = 0;
}
