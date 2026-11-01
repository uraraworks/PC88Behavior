#include <string.h>
#include "q88h_sub_rom_access.h"
static q88h_sub_rom_access_t log_data;
static uint16_t origin;
static int valid, suppressed;
q88h_sub_rom_access_t *retro_q88h_sub_rom_access(void) { return &log_data; }
void retro_q88h_sub_rom_access_reset(void) { memset(&log_data, 0, sizeof log_data); log_data.current_fc = UINT64_MAX; origin = 0; valid = suppressed = 0; }
void retro_q88h_sub_rom_access_config(uint64_t from, uint64_t to) { log_data.from = from; log_data.to = to; log_data.enabled = 1; }
void q88h_sra_fc(void) { if (log_data.enabled) log_data.current_fc = log_data.next_fc++; }
void q88h_sra_instr(uint16_t pc) { if (log_data.enabled) { origin = pc; valid = 1; } }
void q88h_sra_suppress(int on) { if (log_data.enabled) suppressed = on; }
void q88h_sra_record(char kind, uint16_t addr) {
 q88h_sra_event *e;
 if (!log_data.enabled || !valid || suppressed || origin >= 0x2000 || log_data.current_fc == UINT64_MAX || log_data.current_fc < log_data.from || log_data.current_fc > log_data.to) return;
 if (log_data.count == Q88H_SRA_CAPACITY) { ++log_data.dropped; return; }
 e = &log_data.events[log_data.count++]; e->fc = log_data.current_fc; e->addr = addr; e->kind = kind;
}
