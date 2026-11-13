#include <stdio.h>
#include "b92_intervention.h"

static FILE *logfile;
static unsigned target, address, value, frame, count, reached, active;
static unsigned entry_sp, return_pc, entry_frame, dma_base, dma_span;
static int intervene, invalid, seen31, seen_work;

int retro_q88h_b92_open(const char *path, unsigned entry, int enable,
                       unsigned addr, unsigned val)
{
    if (logfile || entry >= 0x8000 || addr < 0x8000 || addr > 0xffff || val > 255)
        return 0;
    logfile = fopen(path, "w");
    if (!logfile) return 0;
    target = entry; address = addr; value = val; intervene = enable;
    frame = count = reached = active = 0;
    invalid = seen31 = seen_work = 0;
    dma_base = dma_span = 0;
    fprintf(logfile, "B92 1\n");
    return 1;
}
void retro_q88h_b92_frame(uint32_t f)
{
    frame = f;
    if (active && frame - entry_frame >= 30) {
        fprintf(logfile, "exit %u 0 -1 %u %u 0\n", frame, dma_base, dma_span);
        active = 0;
    }
}
unsigned q88h_b92_address(void) { return address; }
unsigned q88h_b92_value(void) { return value; }
void q88h_b92_display(unsigned dma, unsigned span)
{
    if (active) { dma_base = dma; dma_span = span; }
}
int q88h_b92_instr(const q88h_boundary_t *bd, unsigned pc, int cls,
                   int main_rom, unsigned sp, unsigned top, int writable,
                   unsigned dma, unsigned span)
{
    if (!logfile) return 0;
    if (active && pc == return_pc && sp == ((entry_sp + 2) & 0xffff)) {
        fprintf(logfile, "exit %u 1 %u %u %u 1\n", frame, sp, dma_base, dma_span);
        active = 0;
    }
    if (reached || bd->int_pending || bd->in_int ||
        bd->last_class != Q88H_BND_RAM || cls != Q88H_BND_ROM ||
        !main_rom || pc != target) return 0;
    reached = active = 1; entry_sp = sp; return_pc = top; entry_frame = frame;
    dma_base = dma; dma_span = span;
    fprintf(logfile, "entry %u %d %d\n", frame, seen31, seen_work);
    if (!intervene) return 0;
    if (!writable) { invalid = 1; return 0; }
    count = 1;
    fprintf(logfile, "intervention 1\n");
    return 1;
}
void q88h_b92_out(unsigned port, unsigned val)
{
    if (!logfile) return;
    if (!reached && port == 0x31 && retro_q88h_boundary()->cur_class == Q88H_BND_RAM)
        { seen31 = 1; seen_work = 0; }
    if (active) fprintf(logfile, "out %u %u\n", port, val);
}
void q88h_b92_write(unsigned addr, int physical)
{
    if (!logfile) return;
    if (!reached && addr == 0xe6c2 && physical == 0xe6c2 &&
        retro_q88h_boundary()->cur_class == Q88H_BND_RAM && seen31) seen_work = 1;
    if (active && physical >= 0) fprintf(logfile, "write %u\n", (unsigned)physical);
}
int retro_q88h_b92_close(void)
{
    int failed;
    if (!logfile) return 0;
    if (active) fprintf(logfile, "exit %u 0 -1 %u %u 0\n", frame, dma_base, dma_span);
    fprintf(logfile, "end %u %u %u %d\n", frame, reached, count, invalid);
    failed = ferror(logfile);
    if (fclose(logfile)) failed = 1;
    logfile = NULL;
    return !failed;
}
