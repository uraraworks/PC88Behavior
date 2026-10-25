/* main CPU の IN の返り値の1ビットを強制する、実測専用の使い捨てフック。
 * 既定（未設定）では何もしない。sub CPU の IN には効かない。 */
#ifndef Q88H_MAIN_IN_FORCE_H_INCLUDED
#define Q88H_MAIN_IN_FORCE_H_INCLUDED

#include <stdint.h>

#define Q88H_MAIN_IN_FORCE_SLOTS 8

typedef struct {
    uint32_t matched;   /* 該当ポートの IN 回数 */
    uint32_t changed;   /* 強制で実際に値が変わった回数 */
    uint8_t port;
    uint8_t bit;
    uint8_t value;
    uint8_t enabled;
} q88h_main_in_force_slot_t;

#ifdef __cplusplus
extern "C" {
#endif

void retro_q88h_main_in_force_reset(void);
int retro_q88h_main_in_force_configure(unsigned slot, unsigned port,
                                        unsigned bit, unsigned value);
int retro_q88h_main_in_force_stats(unsigned slot, uint32_t *matched,
                                    uint32_t *changed);
/* main_io_in の返り値に強制を適用して返す。 */
uint8_t q88h_main_in_force_process(uint8_t port, uint8_t value);

#ifdef __cplusplus
}
#endif
#endif
