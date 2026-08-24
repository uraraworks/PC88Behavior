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
    /* 応答準備介入は対象run直前のRECV前でだけarmし、実際にcpu_timing=0を
     * 支配するPIO C handoffへ一度だけ作用しなければならない。 */
    retro_q88h_exchange_intervention_reset();
    if (!retro_q88h_exchange_ready_handoff_configure(
            3, Q88H_READY_HANDOFF_NOW)) return 1;
    send_run(2); (void)receive_run(1); send_run(1);
    q88h_exchange_ready_handoff_before_main_io(
        Q88H_IOLOG_IN, 0xFE, 0x3853);
    if (q88h_exchange_ready_handoff_on_pio_c_read(1, 0) !=
            Q88H_READY_PIO_FORCE_HANDOFF ||
        q88h_exchange_ready_handoff_on_pio_c_read(1, 0) !=
            Q88H_READY_PIO_NORMAL ||
        retro_q88h_exchange_intervention()->ready_handoff_action_count != 1) {
        fprintf(stderr, "NG: 即時PIO handoff介入が対象で一度だけ発火しない\n");
        return 1;
    }

    retro_q88h_exchange_intervention_reset();
    if (!retro_q88h_exchange_ready_handoff_configure(
            3, Q88H_READY_HANDOFF_DEFER_ONCE)) return 1;
    send_run(2); (void)receive_run(1); send_run(1);
    q88h_exchange_ready_handoff_before_main_io(
        Q88H_IOLOG_IN, 0xFE, 0x3853);
    if (q88h_exchange_ready_handoff_on_pio_c_read(1, 0) !=
            Q88H_READY_PIO_NORMAL ||
        q88h_exchange_ready_handoff_on_pio_c_read(1, 1) !=
            Q88H_READY_PIO_SUPPRESS_HANDOFF ||
        retro_q88h_exchange_intervention()->ready_handoff_action !=
            Q88H_READY_PIO_SUPPRESS_HANDOFF ||
        retro_q88h_exchange_intervention()->ready_handoff_action_count != 1) {
        fprintf(stderr, "NG: PIO handoff一回抑止が実際の切替点だけへ効かない\n");
        return 1;
    }
    puts("OK: 対照/-3のみ/-1のみ/両方が各対象runだけへ効く");
    puts("OK: 応答準備介入は実支配点のPIO handoffへ即時/一回抑止で作用");
    return 0;
}
