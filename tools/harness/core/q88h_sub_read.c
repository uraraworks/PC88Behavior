#include <string.h>
#include "q88h_sub_read.h"
static q88h_sub_read_t log_data;
static uint16_t origin;
static int valid, suppressed;
q88h_sub_read_t *retro_q88h_sub_read(void) { return &log_data; }
void retro_q88h_sub_read_reset(void) { memset(&log_data, 0, sizeof(log_data)); origin = 0; valid = suppressed = 0; }
void retro_q88h_sub_read_set_enabled(int enabled) { log_data.enabled = !!enabled; }
void q88h_sub_read_instr(uint16_t pc) { origin = pc; valid = 1; }
void q88h_sub_read_suppress(int suppress) { suppressed = suppress; }
void q88h_sub_read_data(uint16_t addr)
{
    unsigned cls;
    if (!log_data.enabled || !valid || suppressed || origin < 0x2000) return;
    cls = addr < 0x2000 ? Q88H_SR_ROM : log_data.writer[addr & 0x7fff];
    if (addr >= 0x2000 && !cls) cls = Q88H_SR_UNWRITTEN;
    log_data.counts[cls][addr]++;
}
void q88h_sub_read_write(uint16_t addr)
{
    if (!log_data.enabled || !valid || suppressed || !(addr & 0x4000)) return;
    log_data.writer[addr & 0x7fff] = origin < 0x2000 ? Q88H_SR_ROM_WRITTEN : Q88H_SR_RAM_WRITTEN;
}
