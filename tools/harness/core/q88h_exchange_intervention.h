/* main⇔sub交換runを位置指定で介入する、実測専用の使い捨てフック。 */
#ifndef Q88H_EXCHANGE_INTERVENTION_H_INCLUDED
#define Q88H_EXCHANGE_INTERVENTION_H_INCLUDED

#include <stdint.h>

#define Q88H_EXCHANGE_INTERVENTION_SLOTS 64

enum {
    Q88H_XI_NONE = 0,
    Q88H_XI_XOR_ALL,
    Q88H_XI_XOR_FIRST,
    Q88H_XI_XOR_TAIL,
    Q88H_XI_REPLACE_ALL,
    Q88H_XI_REPLACE_FIRST
};

enum {
    Q88H_READY_HANDOFF_NONE = 0,
    Q88H_READY_HANDOFF_NOW,
    Q88H_READY_HANDOFF_DEFER_ONCE
};

enum {
    Q88H_READY_PIO_NORMAL = 0,
    Q88H_READY_PIO_FORCE_HANDOFF,
    Q88H_READY_PIO_SUPPRESS_HANDOFF
};

typedef struct {
    int32_t run_index;
    uint32_t matched_events;
    uint32_t applied_events;
    uint32_t changed_events;
    uint8_t mode;
    uint8_t value;
    uint8_t matched_run;
    uint8_t pad;
} q88h_exchange_intervention_slot_t;

typedef struct {
    int32_t current_run;
    uint32_t position_in_run;
    uint8_t current_direction;
    uint8_t have_direction;
    uint8_t pad[2];
    q88h_exchange_intervention_slot_t slot[Q88H_EXCHANGE_INTERVENTION_SLOTS];
    int32_t ready_handoff_run;
    int32_t ready_handoff_mode;
    int32_t ready_handoff_action;
    uint32_t ready_handoff_matched_waits;
    uint32_t ready_handoff_action_count;
    uint8_t ready_handoff_configured;
    uint8_t ready_handoff_armed;
    uint8_t pad_ready[2];
} q88h_exchange_intervention_t;

#ifdef __cplusplus
extern "C" {
#endif

q88h_exchange_intervention_t *retro_q88h_exchange_intervention(void);
void retro_q88h_exchange_intervention_reset(void);
int retro_q88h_exchange_intervention_configure(unsigned slot, int32_t run_index,
                                                uint8_t mode, uint8_t value);
int retro_q88h_exchange_ready_handoff_configure(int32_t run_index, int32_t mode);
/* 対象応答直前のmain待機に入ったことをPIO層へ伝える。 */
void q88h_exchange_ready_handoff_before_main_io(uint8_t kind, uint8_t port,
                                                uint16_t pc);
/* PIO Cが既定でCPUを切り替える箇所から呼び、実際の切替だけへ介入する。 */
int q88h_exchange_ready_handoff_on_pio_c_read(int main_side,
                                              int would_handoff);
uint8_t q88h_exchange_intervention_process(uint8_t kind, uint8_t port,
                                           uint16_t pc, uint8_t value);

#ifdef __cplusplus
}
#endif
#endif
