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
} q88h_exchange_intervention_t;

#ifdef __cplusplus
extern "C" {
#endif

q88h_exchange_intervention_t *retro_q88h_exchange_intervention(void);
void retro_q88h_exchange_intervention_reset(void);
int retro_q88h_exchange_intervention_configure(unsigned slot, int32_t run_index,
                                                uint8_t mode, uint8_t value);
uint8_t q88h_exchange_intervention_process(uint8_t kind, uint8_t port,
                                           uint16_t pc, uint8_t value);

#ifdef __cplusplus
}
#endif
#endif
