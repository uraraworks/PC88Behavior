#include "q88h_sub_event.h"
#include <stdio.h>
static FILE *out;
static uint16_t origin;
static uint64_t fc;
static int valid, suppressed;
int retro_q88h_sub_event_open(const char *path) {
    out = fopen(path, "wb"); origin = 0; fc = 0; valid = suppressed = 0;
    if (!out) return 0;
    if (fwrite("Q88EVT1\n", 1, 8, out) != 8) { fclose(out); out = NULL; return 0; }
    return 1;
}
int retro_q88h_sub_event_close(void) {
    int ok;
    if (!out) return 0;
    ok = !ferror(out); if (fclose(out)) ok = 0;
    out = NULL; return ok;
}
int q88h_sub_event_enabled(void) { return out != NULL; }
void q88h_sub_event_instr(uint16_t pc) { if (out) { origin = pc; valid = 1; } }
void q88h_sub_event_suppress(int on) { suppressed = on; }
void q88h_sub_event_fc(void) { if (out) ++fc; }
void q88h_sub_event_record(char kind, uint16_t addr, uint8_t value) {
    unsigned char b[14]; unsigned i;
    if (!out || !valid || origin < 0x2000 || (kind == 'R' && suppressed)) return;
    b[0] = kind; b[1] = origin; b[2] = origin >> 8;
    b[3] = addr; b[4] = addr >> 8; b[5] = value;
    for (i = 0; i < 8; ++i) b[6+i] = (unsigned char)(fc >> (8*i));
    (void)fwrite(b, 1, sizeof b, out);
}
