#include "q88h_main_event.h"
#include <stdio.h>
static FILE *out;
static uint16_t origin;
static uint32_t frame;
static int valid, suppressed;
int retro_q88h_main_event_open(const char *path) {
    out = fopen(path, "wb"); origin = 0; frame = 0; valid = suppressed = 0;
    if (!out) return 0;
    if (fwrite("Q88EVT1\n", 1, 8, out) != 8) { fclose(out); out = NULL; return 0; }
    return 1;
}
int retro_q88h_main_event_close(void) {
    int ok;
    if (!out) return 0;
    ok = !ferror(out); if (fclose(out)) ok = 0;
    out = NULL; return ok;
}
void retro_q88h_main_event_set_frame(uint32_t n) { frame = n; }
int q88h_main_event_enabled(void) { return out != NULL; }
void q88h_main_event_instr(uint16_t pc, int ram) { origin = pc; valid = ram; }
void q88h_main_event_suppress(int on) { suppressed = on; }
void q88h_main_event_record(char kind, uint16_t addr, uint8_t value) {
    unsigned char b[14]; unsigned i;
    if (!out || !valid || (kind == 'R' && suppressed)) return;
    b[0] = kind; b[1] = origin; b[2] = origin >> 8;
    b[3] = addr; b[4] = addr >> 8; b[5] = value;
    for (i = 0; i < 8; ++i) b[6+i] = i < 4 ? (unsigned char)(frame >> (8*i)) : 0;
    (void)fwrite(b, 1, sizeof b, out);
}
