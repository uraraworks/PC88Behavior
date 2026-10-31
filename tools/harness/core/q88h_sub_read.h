#ifndef Q88H_SUB_READ_H
#define Q88H_SUB_READ_H
#include <stdint.h>
enum { Q88H_SR_ROM, Q88H_SR_UNWRITTEN, Q88H_SR_ROM_WRITTEN, Q88H_SR_RAM_WRITTEN, Q88H_SR_CLASSES };
typedef struct {
    int enabled;
    uint8_t writer[65536];
    uint64_t counts[Q88H_SR_CLASSES][65536];
} q88h_sub_read_t;
q88h_sub_read_t *retro_q88h_sub_read(void);
void retro_q88h_sub_read_reset(void);
void retro_q88h_sub_read_set_enabled(int enabled);
void q88h_sub_read_instr(uint16_t pc);
void q88h_sub_read_data(uint16_t addr);
void q88h_sub_read_write(uint16_t addr);
void q88h_sub_read_suppress(int suppress);
#endif
