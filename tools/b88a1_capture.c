/* 追補1。自作器具の境界だけを観測し、追加のポート値は真偽へ即時縮約する。 */
#include "drive.h"
#define retro_b88_instr b88_base_instr
#define retro_b88_finish b88_base_finish
#define b88_port b88_base_port
#include "b88_capture.c"
#undef retro_b88_instr
#undef retro_b88_finish
#undef b88_port

static unsigned a1_media, a1_media_ok, a1_prepare, a1_prepared, a1_entered;
static unsigned a1_input[8], a1_work, a1_work_after;
static unsigned a1_received, a1_received_match[8], a1_first_match[8];
static unsigned a1_fdc_count, a1_fdc_match[8], a1_f7_count, a1_f7_input = 1;
static unsigned a1_f7_last, a1_f7_return = 1;
static unsigned a1_pending;
static unsigned a1_sent;
static unsigned a1_configured, a1_prepare_pc, a1_prepared_pc, a1_start_pc, a1_return_pc;
static unsigned a1_sent_pc, a1_byte_pc, a1_input_hl;
static unsigned a1_env(const char *name) {
    const char *p = getenv(name);
    return p ? strtoul(p, NULL, 16) : 0;
}
static void a1_match(unsigned *dest, unsigned data) {
    unsigned i;
    for (i = 0; i < 8; ++i) dest[i] = (data == a1_input[i]);
}
void retro_b88_instr(int main_cpu, unsigned pc) {
    unsigned i;
    if (!a1_configured) {
        a1_configured = 1;
        a1_prepare_pc = a1_env("B88A1_PREPARE"); a1_prepared_pc = a1_env("B88A1_PREPARED");
        a1_start_pc = a1_env("B88_START"); a1_return_pc = a1_env("B88_RETURN");
        a1_sent_pc = a1_env("B88A1_COOP_SENT"); a1_byte_pc = a1_env("B88A1_COOP_BYTE");
        a1_input_hl = a1_env("B88A1_INPUT_HL");
        if (a1_input_hl < 0x4000 || a1_input_hl >= 0x8000) abort();
    }
    if (main_cpu && pc == a1_sent_pc && a1_entered && !b88_restarts) ++a1_sent;
    if (!main_cpu && pc == 0x7800 && !a1_media) {
        /* ローダが媒体を読み終え、自作プローブに入った時点で交換する。 */
        unsigned want1 = a1_env("B88A1_DISK1"), want2 = a1_env("B88A1_DISK2");
        a1_media = 1;
        if (want2) disk_insert(1, getenv("B88A1_MEDIA"), 0, 1);
        else disk_eject(1);
        if (!want1) disk_eject(0);
        a1_media_ok = (!!disk_image_exist(0) == want1 &&
                       !!disk_image_exist(1) == want2);
    }
    if (!main_cpu && pc == a1_prepare_pc) ++a1_prepare;
    if (!main_cpu && pc == a1_prepared_pc) ++a1_prepared;
    if (!main_cpu && a1_pending) {
        /* CALL/RST/JP を実行した次の命令境界。ROM 内部経路は保存しない。 */
        a1_pending = 0; ++a1_entered; main_ram[0xcffe] = 1;
    }
    if (!main_cpu && pc == a1_start_pc && !b88_starts) {
        a1_input[0] = z80sub_cpu.AF.B.h;
        a1_input[1] = z80sub_cpu.BC.B.h; a1_input[2] = z80sub_cpu.BC.B.l;
        a1_input[3] = z80sub_cpu.DE.B.h; a1_input[4] = z80sub_cpu.DE.B.l;
        a1_input[5] = z80sub_cpu.HL.B.h; a1_input[6] = z80sub_cpu.HL.B.l;
        /* HL は事前登録した自作 RAM ポインタに限定。 */
        a1_input[7] = sub_romram[a1_input_hl];
        a1_work = sub_romram[0x7f0c]; a1_pending = 1;
    }
    if (main_cpu && pc == a1_byte_pc && a1_entered && !b88_restarts) {
        unsigned matches[8];
        a1_match(matches, z80main_cpu.AF.B.h);
        for (i = 0; i < 8; ++i) {
            a1_received_match[i] += matches[i];
            if (!a1_received) a1_first_match[i] = matches[i];
        }
        ++a1_received;
    }
    if (!main_cpu && pc == a1_return_pc && b88_active) {
        a1_work_after = sub_romram[0x7f0c];
        a1_f7_return = (a1_f7_last == z80sub_cpu.AF.B.h);
        main_ram[0xcfff] = 1;
    }
    b88_base_instr(main_cpu, pc);
}
static void b88_port(int output, unsigned port, unsigned data) {
    if (b88_active && output) {
        if ((port & 255) == 0xfb && (fdc_status() & 0xc0) == 0x80) {
            if (!a1_fdc_count) a1_match(a1_fdc_match, data);
            ++a1_fdc_count;
        }
        if ((port & 255) == 0xf7) {
            ++a1_f7_count; a1_f7_last = data;
            a1_f7_input &= data == a1_input[0];
        }
    }
    b88_base_port(output, port, data);
}
static void a1_array(FILE *f, const unsigned *v) {
    unsigned i;
    fprintf(f, "[");
    for (i = 0; i < 8; ++i) fprintf(f, "%s%u", i ? "," : "", v[i]);
    fprintf(f, "]");
}
int retro_b88_finish(void) {
    unsigned matches[8], ok;
    FILE *f;
    if (!b88_base_finish()) return 0;
    f = fopen(getenv("B88A1_CAPTURE"), "w"); if (!f) return 0;
    fprintf(f, "{\"media\":%u,\"media_ok\":%u,\"prepare\":%u,\"prepared\":%u,\"entered\":%u,",
            a1_media, a1_media_ok, a1_prepare, a1_prepared, a1_entered);
    fprintf(f, "\"sent\":%u,\"received\":%u,\"received_match\":", a1_sent, a1_received);
    a1_array(f, a1_received_match);
    fprintf(f, ",\"first_match\":"); a1_array(f, a1_first_match);
    fprintf(f, ",\"fdc_count\":%u,\"fdc_match\":", a1_fdc_count); a1_array(f, a1_fdc_match);
    fprintf(f, ",\"f7_count\":%u,\"f7_input\":%u,\"f7_return\":%u,",
            a1_f7_count, a1_f7_input, a1_f7_return);
    fprintf(f, "\"work_same\":%u,\"work_plus\":%u,\"work_minus\":%u,\"work_match\":",
            a1_work == a1_work_after, ((a1_work + 1) & 255) == a1_work_after,
            ((a1_work - 1) & 255) == a1_work_after);
    a1_match(matches, a1_work_after); a1_array(f, matches);
    fprintf(f, "}\n");
    ok = !ferror(f); if (fclose(f)) ok = 0;
    return ok;
}
