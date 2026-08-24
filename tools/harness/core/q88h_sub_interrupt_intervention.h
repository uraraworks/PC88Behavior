/* sub割り込み受理を交換run窓内だけ変える、実測専用の使い捨てフック。 */
#ifndef Q88H_SUB_INTERRUPT_INTERVENTION_H_INCLUDED
#define Q88H_SUB_INTERRUPT_INTERVENTION_H_INCLUDED

#include <stdint.h>

enum {
    Q88H_SII_NONE = 0,
    Q88H_SII_SUPPRESS,
    Q88H_SII_DELAY_ONE
};

typedef struct {
    int32_t first_run;
    int32_t last_run;
    uint32_t matched_checks;
    uint32_t suppressed_checks;
    uint32_t accepted_in_window;
    uint8_t mode;
    uint8_t delay_pending;
    uint8_t configured;
    uint8_t pad;
} q88h_sub_interrupt_intervention_t;

#ifdef __cplusplus
extern "C" {
#endif

q88h_sub_interrupt_intervention_t *retro_q88h_sub_interrupt_intervention(void);
void retro_q88h_sub_interrupt_intervention_reset(void);
int retro_q88h_sub_interrupt_intervention_configure(int32_t first_run,
                                                    int32_t last_run,
                                                    uint8_t mode);
int q88h_sub_interrupt_intervention_before_ack(void);
void q88h_sub_interrupt_intervention_ack_result(int accepted);

#ifdef __cplusplus
}
#endif
#endif
