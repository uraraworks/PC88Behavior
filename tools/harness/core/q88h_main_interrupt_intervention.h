/* main側割り込み受理への測定用介入（m7lr）。
 *
 * sub側（q88h_sub_interrupt_intervention）と同じ形で、指定した交換run窓の間だけ
 * main CPU の割り込み受理を保留する。無指定時は常に許可し、交換値やROM本体は
 * 変更しない。窓は q88h_exchange_intervention の current_run で判定する。
 *
 * mode:
 *   suppress   窓の間、main の割り込み受理をすべて保留する（要求は取り下げない）
 *   delay-one  窓の間、受理の直前検査を1回だけ保留してから通す（受理ごとに再装填）
 */
#ifndef Q88H_MAIN_INTERRUPT_INTERVENTION_H_INCLUDED
#define Q88H_MAIN_INTERRUPT_INTERVENTION_H_INCLUDED

#include <stdint.h>

enum {
    Q88H_MII_NONE = 0,
    Q88H_MII_SUPPRESS,
    Q88H_MII_DELAY_ONE
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
} q88h_main_interrupt_intervention_t;

#ifdef __cplusplus
extern "C" {
#endif

q88h_main_interrupt_intervention_t *retro_q88h_main_interrupt_intervention(void);
void retro_q88h_main_interrupt_intervention_reset(void);
int retro_q88h_main_interrupt_intervention_configure(int32_t first_run,
                                                     int32_t last_run,
                                                     uint8_t mode);
int q88h_main_interrupt_intervention_before_ack(void);
void q88h_main_interrupt_intervention_ack_result(int accepted);

#ifdef __cplusplus
}
#endif

#endif
