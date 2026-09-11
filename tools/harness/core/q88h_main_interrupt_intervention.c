/* 無指定時は常に許可する。交換値やROM本体は変更しない（m7lr）。
 * 形は q88h_sub_interrupt_intervention.c と同じで、対象CPUだけが違う。 */
#include <string.h>
#include "q88h_exchange_intervention.h"
#include "q88h_main_interrupt_intervention.h"

static q88h_main_interrupt_intervention_t g_mii;

q88h_main_interrupt_intervention_t *retro_q88h_main_interrupt_intervention(void)
{
    return &g_mii;
}

void retro_q88h_main_interrupt_intervention_reset(void)
{
    memset(&g_mii, 0, sizeof(g_mii));
    g_mii.first_run = g_mii.last_run = -1;
}

int retro_q88h_main_interrupt_intervention_configure(int32_t first_run,
                                                     int32_t last_run,
                                                     uint8_t mode)
{
    if (first_run < 0 || last_run < first_run ||
        mode < Q88H_MII_SUPPRESS || mode > Q88H_MII_DELAY_ONE)
        return 0;
    g_mii.first_run = first_run;
    g_mii.last_run = last_run;
    g_mii.mode = mode;
    g_mii.configured = 1;
    return 1;
}

static int active(void)
{
    q88h_exchange_intervention_t *xi;
    if (!g_mii.configured) return 0;
    xi = retro_q88h_exchange_intervention();
    return xi->have_direction && xi->current_run >= g_mii.first_run &&
           xi->current_run <= g_mii.last_run;
}

int q88h_main_interrupt_intervention_before_ack(void)
{
    if (!active()) {
        g_mii.delay_pending = 0;
        return 0;
    }
    g_mii.matched_checks++;
    if (g_mii.mode == Q88H_MII_SUPPRESS) {
        g_mii.suppressed_checks++;
        return 1;
    }
    if (!g_mii.delay_pending) {
        g_mii.delay_pending = 1;
        g_mii.suppressed_checks++;
        return 1;
    }
    return 0;
}

void q88h_main_interrupt_intervention_ack_result(int accepted)
{
    if (!active()) return;
    if (accepted) g_mii.accepted_in_window++;
    g_mii.delay_pending = 0;
}
