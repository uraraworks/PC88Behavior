/*
 * main CPU の IN の返り値の1ビットを強制する。無設定時は値をそのまま返す。
 * リセット（retro_reset 等）では消えない。消すのは明示の reset 呼び出しだけ
 * （q88h_exchange_intervention と同じ扱い）。
 */
#include <string.h>
#include "q88h_main_in_force.h"

static q88h_main_in_force_slot_t g_mif[Q88H_MAIN_IN_FORCE_SLOTS];

void retro_q88h_main_in_force_reset(void)
{
    memset(g_mif, 0, sizeof(g_mif));
}

int retro_q88h_main_in_force_configure(unsigned slot, unsigned port,
                                        unsigned bit, unsigned value)
{
    q88h_main_in_force_slot_t *s;
    if (slot >= Q88H_MAIN_IN_FORCE_SLOTS || port > 0xFF || bit > 7 || value > 1)
        return 0;
    s = &g_mif[slot];
    memset(s, 0, sizeof(*s));
    s->port = (uint8_t)port;
    s->bit = (uint8_t)bit;
    s->value = (uint8_t)value;
    s->enabled = 1;
    return 1;
}

int retro_q88h_main_in_force_stats(unsigned slot, uint32_t *matched,
                                    uint32_t *changed)
{
    if (slot >= Q88H_MAIN_IN_FORCE_SLOTS || !matched || !changed)
        return 0;
    *matched = g_mif[slot].matched;
    *changed = g_mif[slot].changed;
    return 1;
}

uint8_t q88h_main_in_force_process(uint8_t port, uint8_t value)
{
    unsigned i;
    for (i = 0; i < Q88H_MAIN_IN_FORCE_SLOTS; i++) {
        q88h_main_in_force_slot_t *s = &g_mif[i];
        uint8_t nv;
        if (!s->enabled || s->port != port)
            continue;
        s->matched++;
        nv = s->value ? (uint8_t)(value | (1u << s->bit))
                      : (uint8_t)(value & ~(1u << s->bit));
        if (nv != value)
            s->changed++;
        value = nv;
    }
    return value;
}
