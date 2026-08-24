/* 無指定時は常に許可する。交換値やROM本体は変更しない。 */
#include <string.h>
#include "q88h_exchange_intervention.h"
#include "q88h_sub_interrupt_intervention.h"

static q88h_sub_interrupt_intervention_t g_sii;

q88h_sub_interrupt_intervention_t *retro_q88h_sub_interrupt_intervention(void)
{
    return &g_sii;
}

void retro_q88h_sub_interrupt_intervention_reset(void)
{
    memset(&g_sii, 0, sizeof(g_sii));
    g_sii.first_run = g_sii.last_run = -1;
}

int retro_q88h_sub_interrupt_intervention_configure(int32_t first_run,
                                                    int32_t last_run,
                                                    uint8_t mode)
{
    if (first_run < 0 || last_run < first_run ||
        mode < Q88H_SII_SUPPRESS || mode > Q88H_SII_DELAY_ONE)
        return 0;
    g_sii.first_run = first_run;
    g_sii.last_run = last_run;
    g_sii.mode = mode;
    g_sii.configured = 1;
    return 1;
}

static int active(void)
{
    q88h_exchange_intervention_t *xi;
    if (!g_sii.configured) return 0;
    xi = retro_q88h_exchange_intervention();
    return xi->have_direction && xi->current_run >= g_sii.first_run &&
           xi->current_run <= g_sii.last_run;
}

int q88h_sub_interrupt_intervention_before_ack(void)
{
    if (!active()) {
        g_sii.delay_pending = 0;
        return 0;
    }
    g_sii.matched_checks++;
    if (g_sii.mode == Q88H_SII_SUPPRESS) {
        g_sii.suppressed_checks++;
        return 1;
    }
    if (!g_sii.delay_pending) {
        g_sii.delay_pending = 1;
        g_sii.suppressed_checks++;
        return 1;
    }
    return 0;
}

void q88h_sub_interrupt_intervention_ack_result(int accepted)
{
    if (!active()) return;
    if (accepted) g_sii.accepted_in_window++;
    g_sii.delay_pending = 0;
}
