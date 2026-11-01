#include "q88h_sub_reg.h"
static FILE *out;
static int last = -1;
static uint16_t origin;
int retro_q88h_sub_reg_open(const char *path) {
    out = fopen(path, "wb"); last = -1;
    return out && fputs("Q88REG1\n", out) >= 0;
}
int retro_q88h_sub_reg_close(void) {
    int ok;
    if (!out) return 0;
    ok = fputs("END\n", out) >= 0 && !ferror(out);
    if (fclose(out)) ok = 0;
    out = NULL; return ok;
}
int q88h_sub_reg_enabled(void) { return out != NULL; }
void q88h_sub_reg_instr(uint16_t pc) {
    int cls = pc >= 0x2000;
    if (!out) return;
    origin = pc;
    if (last == 0 && cls) q88h_sub_reg_capture('C', pc);
    last = cls;
}
void q88h_sub_reg_fc(void) { if (out) q88h_sub_reg_capture('F', 0); }
void q88h_sub_reg_opcode(int opcode) {
    if (out && origin >= 0x2000 && (opcode == 0x5f || opcode == 0x57))
        fprintf(out, "O %c %04X\n", opcode == 0x5f ? 'R' : 'I', origin);
}
/* 呼び出し側で ferror と fclose を検査する。 */
FILE *q88h_sub_reg_file(void) { return out; }
