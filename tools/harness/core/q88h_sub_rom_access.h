#ifndef Q88H_SUB_ROM_ACCESS_H
#define Q88H_SUB_ROM_ACCESS_H
#include <stdint.h>
#ifndef Q88H_SRA_CAPACITY
#define Q88H_SRA_CAPACITY (1u << 20)
#endif
typedef struct { uint64_t fc; uint16_t addr; char kind; } q88h_sra_event;
typedef struct { int enabled; uint64_t from, to, next_fc, current_fc, dropped; uint32_t count; q88h_sra_event events[Q88H_SRA_CAPACITY]; } q88h_sub_rom_access_t;
q88h_sub_rom_access_t *retro_q88h_sub_rom_access(void);
void retro_q88h_sub_rom_access_reset(void);
void retro_q88h_sub_rom_access_config(uint64_t, uint64_t);
void q88h_sra_fc(void);
void q88h_sra_instr(uint16_t);
void q88h_sra_suppress(int);
void q88h_sra_record(char, uint16_t);
#endif
