/*
 * 値を保存・列挙せず、既知のmain交換PC群から方向runだけをオンライン再構成し、
 * 指定したsub→main runにだけ介入する。無指定時は値をそのまま返す。
 */
#include <string.h>
#include "q88h_iolog.h"
#include "q88h_exchange_intervention.h"

enum { DIR_MAIN_TO_SUB = 1, DIR_SUB_TO_MAIN = 2 };
static q88h_exchange_intervention_t g_xi;

q88h_exchange_intervention_t *retro_q88h_exchange_intervention(void)
{
    return &g_xi;
}

void retro_q88h_exchange_intervention_reset(void)
{
    unsigned i;
    memset(&g_xi, 0, sizeof(g_xi));
    g_xi.current_run = -1;
    g_xi.ready_handoff_run = -1;
    for (i = 0; i < Q88H_EXCHANGE_INTERVENTION_SLOTS; i++)
        g_xi.slot[i].run_index = -1;
}

int retro_q88h_exchange_ready_handoff_configure(int32_t run_index, int32_t mode)
{
    if (run_index < 1 ||
        (mode != Q88H_READY_HANDOFF_NOW &&
         mode != Q88H_READY_HANDOFF_DEFER_ONCE))
        return 0;
    g_xi.ready_handoff_run = run_index;
    g_xi.ready_handoff_mode = mode;
    g_xi.ready_handoff_configured = 1;
    return 1;
}

void q88h_exchange_ready_handoff_before_main_io(uint8_t kind, uint8_t port,
                                                uint16_t pc)
{
    /* RECV前のFE待機だけを対象にする。対象応答runの一つ前まで交換列を
     * 再構成できていることも要求し、同形の別窓へ漏らさない。 */
    if (!g_xi.ready_handoff_configured || g_xi.ready_handoff_action_count ||
        kind != Q88H_IOLOG_IN || port != 0xFE ||
        pc != 0x3853 ||
        g_xi.current_run != g_xi.ready_handoff_run - 1)
        return;
    g_xi.ready_handoff_matched_waits++;
    g_xi.ready_handoff_armed = 1;
}

int q88h_exchange_ready_handoff_on_pio_c_read(int main_side,
                                              int would_handoff)
{
    int action = Q88H_READY_PIO_NORMAL;
    if (!g_xi.ready_handoff_armed || !main_side ||
        g_xi.ready_handoff_action_count)
        return action;
    if (g_xi.ready_handoff_mode == Q88H_READY_HANDOFF_NOW) {
        /* 既に通常切替点なら追加操作は不要だが、この読出しを作用点として
         * 一度だけ確定する。 */
        action = would_handoff ? Q88H_READY_PIO_NORMAL
                               : Q88H_READY_PIO_FORCE_HANDOFF;
    } else if (g_xi.ready_handoff_mode == Q88H_READY_HANDOFF_DEFER_ONCE) {
        if (!would_handoff)
            return action;
        action = Q88H_READY_PIO_SUPPRESS_HANDOFF;
    }
    g_xi.ready_handoff_action = action;
    g_xi.ready_handoff_action_count++;
    return action;
}

int retro_q88h_exchange_intervention_configure(unsigned slot, int32_t run_index,
                                                uint8_t mode, uint8_t value)
{
    if (slot >= Q88H_EXCHANGE_INTERVENTION_SLOTS || run_index < 0 ||
        mode < Q88H_XI_XOR_ALL || mode > Q88H_XI_REPLACE_FIRST)
        return 0;
    g_xi.slot[slot].run_index = run_index;
    g_xi.slot[slot].mode = mode;
    g_xi.slot[slot].value = value;
    return 1;
}

static uint8_t classify(uint8_t kind, uint8_t port, uint16_t pc)
{
    if (kind == Q88H_IOLOG_OUT && port == 0xFD &&
        (pc == 0x37F4 || pc == 0x3811))
        return DIR_MAIN_TO_SUB;
    if (kind == Q88H_IOLOG_IN && port == 0xFC &&
        (pc == 0x3863 || pc == 0x3880 || pc == 0xC269))
        return DIR_SUB_TO_MAIN;
    return 0;
}

uint8_t q88h_exchange_intervention_process(uint8_t kind, uint8_t port,
                                           uint16_t pc, uint8_t value)
{
    uint8_t direction = classify(kind, port, pc);
    unsigned i;
    if (!direction) return value;
    if (!g_xi.have_direction || direction != g_xi.current_direction) {
        g_xi.current_run++;
        g_xi.position_in_run = 0;
        g_xi.current_direction = direction;
        g_xi.have_direction = 1;
    }
    if (direction == DIR_SUB_TO_MAIN) {
        for (i = 0; i < Q88H_EXCHANGE_INTERVENTION_SLOTS; i++) {
            q88h_exchange_intervention_slot_t *s = &g_xi.slot[i];
            int apply;
            if (s->run_index != g_xi.current_run) continue;
            s->matched_run = 1;
            s->matched_events++;
            apply = (s->mode == Q88H_XI_XOR_ALL || s->mode == Q88H_XI_REPLACE_ALL ||
                     ((s->mode == Q88H_XI_XOR_FIRST || s->mode == Q88H_XI_REPLACE_FIRST) &&
                      g_xi.position_in_run == 0) ||
                     (s->mode == Q88H_XI_XOR_TAIL && g_xi.position_in_run != 0));
            if (apply) {
                uint8_t changed = (s->mode == Q88H_XI_REPLACE_ALL ||
                                   s->mode == Q88H_XI_REPLACE_FIRST) ? s->value
                                                                    : (uint8_t)(value ^ s->value);
                s->applied_events++;
                if (changed != value) s->changed_events++;
                value = changed;
            }
        }
    }
    g_xi.position_in_run++;
    return value;
}
