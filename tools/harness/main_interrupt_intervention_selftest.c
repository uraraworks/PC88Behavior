#include <stdio.h>
#include "q88h_iolog.h"
#include "q88h_exchange_intervention.h"
#include "q88h_main_interrupt_intervention.h"
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
    q88h_main_interrupt_intervention_t *m;
    /* 無介入: 何も保留しない */
    retro_q88h_main_interrupt_intervention_reset();
    retro_q88h_sub_interrupt_intervention_reset();
    enter_run(3);
    if (q88h_main_interrupt_intervention_before_ack()) return 1;

    /* 窓の外: 設定しても窓に入るまでは保留しない（陰性対照） */
    retro_q88h_main_interrupt_intervention_reset();
    if (!retro_q88h_main_interrupt_intervention_configure(5, 6, Q88H_MII_SUPPRESS)) return 1;
    enter_run(3);
    if (q88h_main_interrupt_intervention_before_ack()) return 1;
    m = retro_q88h_main_interrupt_intervention();
    if (m->matched_checks != 0) return 1;

    /* 窓の後ろ: 窓を過ぎたrunでは保留しない（上限の陰性対照） */
    retro_q88h_main_interrupt_intervention_reset();
    if (!retro_q88h_main_interrupt_intervention_configure(1, 2, Q88H_MII_SUPPRESS)) return 1;
    enter_run(3);
    if (q88h_main_interrupt_intervention_before_ack()) return 1;
    m = retro_q88h_main_interrupt_intervention();
    if (m->matched_checks != 0) return 1;

    /* suppress: 窓の中では毎回保留する */
    retro_q88h_main_interrupt_intervention_reset();
    if (!retro_q88h_main_interrupt_intervention_configure(2, 3, Q88H_MII_SUPPRESS)) return 1;
    enter_run(3);
    if (!q88h_main_interrupt_intervention_before_ack()) return 1;
    if (!q88h_main_interrupt_intervention_before_ack()) return 1;
    m = retro_q88h_main_interrupt_intervention();
    if (m->matched_checks != 2 || m->suppressed_checks != 2) return 1;

    /* delay-one: 1回保留して次は通す。受理のたびに再装填 */
    retro_q88h_main_interrupt_intervention_reset();
    if (!retro_q88h_main_interrupt_intervention_configure(2, 3, Q88H_MII_DELAY_ONE)) return 1;
    enter_run(3);
    if (!q88h_main_interrupt_intervention_before_ack() ||
        q88h_main_interrupt_intervention_before_ack()) return 1;
    q88h_main_interrupt_intervention_ack_result(1);
    if (!q88h_main_interrupt_intervention_before_ack()) return 1;
    m = retro_q88h_main_interrupt_intervention();
    if (m->matched_checks != 3 || m->suppressed_checks != 2 ||
        m->accepted_in_window != 1) return 1;

    /* main側の介入はsub側の状態に触れない（取り違えの陰性対照） */
    if (retro_q88h_sub_interrupt_intervention()->matched_checks != 0 ||
        q88h_sub_interrupt_intervention_before_ack()) return 1;

    /* 不正な設定は拒否する */
    retro_q88h_main_interrupt_intervention_reset();
    if (retro_q88h_main_interrupt_intervention_configure(3, 2, Q88H_MII_SUPPRESS) ||
        retro_q88h_main_interrupt_intervention_configure(-1, 2, Q88H_MII_SUPPRESS) ||
        retro_q88h_main_interrupt_intervention_configure(1, 2, Q88H_MII_NONE)) return 1;

    puts("OK: main割り込み介入の無介入/窓外/suppress/delay-one/sub非干渉/不正設定拒否");
    return 0;
}
