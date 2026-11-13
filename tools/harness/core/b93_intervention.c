#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include "b93_intervention.h"

static FILE *logfile;
static unsigned target, value, frame, reached, active, returned, count;
static unsigned entry_sp, return_pc, entry_frame;
static int intervene;
static struct {
    int cls, poll;
    unsigned kind, port, pc, poll_pc;
    uint64_t run, inputs;
} cpu[2];
static unsigned hits[2];
static uint64_t totals[2], boundary_total;

int retro_q88h_b93_version(void) { return 2; }
int retro_q88h_b93_open(const char *path, unsigned entry, int enable, unsigned val)
{
    unsigned i;
    if (logfile || entry >= 0x8000 || val > 255 || (enable != 0 && enable != 1)) return 0;
    logfile = fopen(path, "w");
    if (!logfile) return 0;
    target = entry; value = val; intervene = enable;
    frame = reached = active = returned = count = 0;
    totals[0] = totals[1] = boundary_total = 0;
    memset(cpu, 0, sizeof(cpu)); memset(hits, 0, sizeof(hits));
    for (i = 0; i < 2; i++) { cpu[i].cls = Q88H_BND_NONE; cpu[i].poll = -1; }
    fprintf(logfile, "B93 2\n");
    return 1;
}
static void flush_io(unsigned c)
{
    if (!cpu[c].run) return;
    fprintf(logfile, "io %u %u %u %02X %04X %" PRIu64 "\n",
            frame, c, cpu[c].kind, cpu[c].port, cpu[c].pc, cpu[c].run);
    cpu[c].run = 0;
}
static void finish_frame(void)
{
    unsigned c;
    for (c = 0; c < 2; c++) flush_io(c);
    fprintf(logfile, "frame %u %d %d %d %d\n", frame, cpu[0].cls, cpu[1].cls,
            cpu[0].inputs >= 2 && cpu[0].poll >= 0 ? cpu[0].poll : -1,
            cpu[1].inputs >= 2 && cpu[1].poll >= 0 ? cpu[1].poll : -1);
    for (c = 0; c < 2; c++) { cpu[c].inputs = 0; cpu[c].poll = -1; }
}
void retro_q88h_b93_frame(uint32_t f)
{
    if (!logfile) return;
    if (f != frame) finish_frame();
    frame = f;
    if (active && frame - entry_frame >= 30) {
        fprintf(logfile, "exit %u 0\n", frame); active = 0;
    }
}
unsigned q88h_b93_value(void) { return value; }
int q88h_b93_instr(const q88h_boundary_t *bd, unsigned pc, int cls,
                   int main_rom, unsigned sp, unsigned top)
{
    if (!logfile) return 0;
    q88h_b93_fetch(0, pc, cls);
    /* B92b と同じ PC/SP 判定。戻り先の命令 fetch の前に書く。 */
    if (active && pc == return_pc && sp == ((entry_sp + 2) & 0xffff)) {
        active = 0; returned = 1;
        fprintf(logfile, "exit %u 1\n", frame);
        if (intervene) { count = 1; fprintf(logfile, "intervention 1\n"); return 1; }
    }
    if (reached || bd->int_pending || bd->in_int ||
        bd->last_class != Q88H_BND_RAM || cls != Q88H_BND_ROM || !main_rom || pc != target)
        return 0;
    reached = active = 1; entry_sp = sp; return_pc = top; entry_frame = frame;
    fprintf(logfile, "entry %u\n", frame);
    return 0;
}
void q88h_b93_fetch(unsigned c, unsigned pc, int cls)
{
    unsigned i;
    if (!logfile) return;
    cpu[c].cls = cls;
    if (c) return;
    for (i = 0; i < 2; i++) {
        unsigned addr = i ? 0x3080 : 0x3e0d;
        if (pc == addr && !hits[i]) {
            hits[i] = 1; fprintf(logfile, "hit %u %04X\n", frame, addr);
        }
    }
}
void q88h_b93_boundary(void) { if (logfile) boundary_total++; }
void q88h_b93_io(unsigned c, unsigned kind, unsigned port, unsigned pc)
{
    if (!logfile) return;
    totals[c]++;
    if (cpu[c].run && (cpu[c].kind != kind || cpu[c].port != port || cpu[c].pc != pc)) flush_io(c);
    cpu[c].kind = kind; cpu[c].port = port; cpu[c].pc = pc; cpu[c].run++;
    /* 同じフレームの I/O が同一 PC/port の IN のみなら待機候補。
       値や命令列から「待ち」を断定しない。OUT を含む場合は候補にしない。 */
    if (!kind || (cpu[c].inputs && (cpu[c].poll != (int)port || cpu[c].poll_pc != pc))) cpu[c].poll = -2;
    else if (!cpu[c].inputs && cpu[c].poll != -2) { cpu[c].poll = (int)port; cpu[c].poll_pc = pc; }
    cpu[c].inputs++;
}
int retro_q88h_b93_close(void)
{
    int failed;
    if (!logfile) return 0;
    if (active) { fprintf(logfile, "exit %u 0\n", frame); active = 0; }
    finish_frame();
    fprintf(logfile, "end %u %u %u %u %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",
            frame + 1, reached, returned, count, totals[0], totals[1], boundary_total);
    failed = ferror(logfile);
    if (fclose(logfile)) failed = 1;
    logfile = NULL;
    return !failed;
}
