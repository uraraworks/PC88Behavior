#ifndef Q88H_SUB_ROM_READ_H
#define Q88H_SUB_ROM_READ_H
#include <stdint.h>
#ifndef Q88H_SRR_CAPACITY
#define Q88H_SRR_CAPACITY (1u << 20)
#endif
typedef struct { uint64_t fc; uint16_t addr; uint8_t writer; } q88h_srr_event;
typedef struct {
    int enabled;
    uint64_t from, to, next_fc, current_fc, dropped;
    uint32_t count;
    uint8_t writer[32768];
    q88h_srr_event events[Q88H_SRR_CAPACITY];
} q88h_sub_rom_read_t;
q88h_sub_rom_read_t *retro_q88h_sub_rom_read(void);
void retro_q88h_sub_rom_read_reset(void);
void retro_q88h_sub_rom_read_config(uint64_t from, uint64_t to);
void q88h_srr_fc(void);
void q88h_srr_instr(uint16_t pc);
void q88h_srr_suppress(int suppress);
void q88h_srr_data(uint16_t addr);
void q88h_srr_write(uint16_t addr);
#endif
