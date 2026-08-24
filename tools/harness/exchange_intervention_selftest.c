#include <stdio.h>
#include "q88h_iolog.h"
#include "q88h_exchange_intervention.h"

static void send_run(unsigned n)
{
    unsigned i;
    for (i = 0; i < n; i++)
        (void)q88h_exchange_intervention_process(Q88H_IOLOG_OUT, 0xFD, 0x37F4, 0x20);
}

static unsigned receive_run(unsigned n)
{
    unsigned i, changed = 0;
    for (i = 0; i < n; i++) {
        uint8_t before = (uint8_t)i;
        uint8_t after = q88h_exchange_intervention_process(
            Q88H_IOLOG_IN, 0xFC, 0x3863, before);
        if (before != after) changed++;
    }
    return changed;
}

static int arm(unsigned mask)
{
    q88h_exchange_intervention_t *state;
    unsigned changed256, changed1;
    retro_q88h_exchange_intervention_reset();
    if ((mask & 1) && !retro_q88h_exchange_intervention_configure(
            0, 1, Q88H_XI_XOR_ALL, 1)) return 0;
    if ((mask & 2) && !retro_q88h_exchange_intervention_configure(
            (mask & 1) ? 1 : 0, 3, Q88H_XI_XOR_ALL, 1)) return 0;
    send_run(2); changed256 = receive_run(256);
    send_run(1); changed1 = receive_run(1);
    send_run(6);
    state = retro_q88h_exchange_intervention();
    if (changed256 != ((mask & 1) ? 256u : 0u) ||
        changed1 != ((mask & 2) ? 1u : 0u)) return 0;
    if (mask & 1) {
        if (!state->slot[0].matched_run || state->slot[0].matched_events != 256 ||
            state->slot[0].applied_events != 256 ||
            state->slot[0].changed_events != 256) return 0;
    }
    if (mask & 2) {
        unsigned slot = (mask & 1) ? 1 : 0;
        if (!state->slot[slot].matched_run || state->slot[slot].matched_events != 1 ||
            state->slot[slot].applied_events != 1 ||
            state->slot[slot].changed_events != 1) return 0;
    }
    return 1;
}

int main(void)
{
    unsigned mask;
    for (mask = 0; mask < 4; mask++) {
        if (!arm(mask)) {
            fprintf(stderr, "NG: arm mask=%u\n", mask);
            return 1;
        }
    }
    puts("OK: 対照/-3のみ/-1のみ/両方が各対象runだけへ効く");
    return 0;
}
