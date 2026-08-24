#include <stdio.h>
#include "q88h_iolog.h"
#include "q88h_exchange_intervention.h"
#include "q88h_sub_interrupt_intervention.h"

static void enter_run(int run)
{
    int i;
    retro_q88h_exchange_intervention_reset();
    for (i = 0; i <= run; i++) {
        uint8_t kind = (i & 1) ? Q88H_IOLOG_IN : Q88H_IOLOG_OUT;
        uint8_t port = (i & 1) ? 0xFC : 0xFD;
        uint16_t pc = (i & 1) ? 0x3863 : 0x37F4;
        (void)q88h_exchange_intervention_process(kind, port, pc, 0);
    }
}

int main(void)
{
    q88h_sub_interrupt_intervention_t *s;
    retro_q88h_sub_interrupt_intervention_reset();
    enter_run(3);
    if (q88h_sub_interrupt_intervention_before_ack()) return 1;

    retro_q88h_sub_interrupt_intervention_reset();
    if (!retro_q88h_sub_interrupt_intervention_configure(2, 3, Q88H_SII_SUPPRESS)) return 1;
    enter_run(3);
    if (!q88h_sub_interrupt_intervention_before_ack()) return 1;
    s = retro_q88h_sub_interrupt_intervention();
    if (s->matched_checks != 1 || s->suppressed_checks != 1) return 1;

    retro_q88h_sub_interrupt_intervention_reset();
    if (!retro_q88h_sub_interrupt_intervention_configure(2, 3, Q88H_SII_DELAY_ONE)) return 1;
    enter_run(3);
    if (!q88h_sub_interrupt_intervention_before_ack() ||
        q88h_sub_interrupt_intervention_before_ack()) return 1;
    q88h_sub_interrupt_intervention_ack_result(1);
    if (!q88h_sub_interrupt_intervention_before_ack()) return 1;
    s = retro_q88h_sub_interrupt_intervention();
    if (s->matched_checks != 3 || s->suppressed_checks != 2 ||
        s->accepted_in_window != 1) return 1;
    puts("OK: 無介入/suppress/delay-oneが指定交換run窓だけへ効く");
    return 0;
}
