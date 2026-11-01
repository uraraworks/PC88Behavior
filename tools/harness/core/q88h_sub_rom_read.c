#include <string.h>
#include <stdint.h>
#include "q88h_sub_rom_read.h"
static q88h_sub_rom_read_t log_data;
static uint16_t origin;
static int valid, suppressed;
q88h_sub_rom_read_t *retro_q88h_sub_rom_read(void) { return &log_data; }
void retro_q88h_sub_rom_read_reset(void) {
    memset(&log_data, 0, sizeof(log_data));
    log_data.current_fc = UINT64_MAX; origin = 0; valid = suppressed = 0;
}
void retro_q88h_sub_rom_read_config(uint64_t from, uint64_t to) {
    log_data.from = from; log_data.to = to; log_data.enabled = 1;
}
void q88h_srr_fc(void) { if (log_data.enabled) log_data.current_fc = log_data.next_fc++; }
void q88h_srr_instr(uint16_t pc) { if (log_data.enabled) { origin = pc; valid = 1; } }
void q88h_srr_suppress(int n) { if (log_data.enabled) suppressed = n; }
void q88h_srr_write(uint16_t addr) {
    if (log_data.enabled && valid && !suppressed && (addr & 0x4000))
        log_data.writer[addr & 0x7fff] = origin < 0x2000 ? 1 : 2;
}
void q88h_srr_data(uint16_t addr) {
    q88h_srr_event *e;
    if (!log_data.enabled || !valid || suppressed || origin >= 0x2000 || addr < 0x4000 ||
        log_data.current_fc == UINT64_MAX || log_data.current_fc < log_data.from || log_data.current_fc > log_data.to) return;
    if (log_data.count == Q88H_SRR_CAPACITY) { log_data.dropped++; return; }
    e = &log_data.events[log_data.count++]; e->fc = log_data.current_fc;
    e->addr = addr; e->writer = log_data.writer[addr & 0x7fff];
}
