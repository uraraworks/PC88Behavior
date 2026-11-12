/* B88 専用計測。OUT 内のコアコピーにだけ組み込む。
 * ROM の値・内部 PC・RAM 内容列はファイルへ出さない。
 * RAM の前後像はホストメモリだけに保持し、番地と変化回数へ縮約する。 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned b88_start_pc, b88_return_pc, b88_main_boot;
static unsigned b88_boots, b88_starts, b88_returns, b88_restarts;
static int b88_configured, b88_active, b88_ended;
static uint8_t b88_before[0x4000], b88_after[0x4000];
static uint64_t b88_changes[0x4000], b88_io[2][256], b88_fdc[32];
static uint16_t b88_regs[5];
static const char *b88_path;
static void b88_snapshot(uint8_t *dest) {
    /* サブ RAM 4000-7FFF のみ。ROM 読出しは存在しない。 */
    memcpy(dest, sub_romram + 0x4000, 0x4000);
}
static void b88_end(void) {
    if (b88_active) b88_snapshot(b88_after);
    b88_active = 0;
}
void retro_b88_instr(int main_cpu, unsigned pc) {
    if (!b88_configured) {
        b88_configured = 1;
        b88_path = getenv("B88_CAPTURE");
        if (!b88_path) return;
        b88_start_pc = strtoul(getenv("B88_START"), NULL, 16);
        b88_return_pc = strtoul(getenv("B88_RETURN"), NULL, 16);
        b88_main_boot = strtoul(getenv("B88_BOOT"), NULL, 16);
    }
    if (!b88_path) return;
    if (main_cpu) {
        if (pc == b88_main_boot && ++b88_boots > 1) {
            ++b88_restarts; b88_end();
        }
        return;
    }
    if (pc == 0 && b88_starts && !b88_ended) {
        ++b88_restarts; b88_end();
    }
    if (pc == 0x7800 && b88_starts && !b88_ended) {
        ++b88_restarts; b88_end();
    }
    if (pc == b88_start_pc) {
        ++b88_starts;
        if (b88_starts > 1) { ++b88_restarts; b88_end(); }
        else if (!b88_restarts) {
            b88_snapshot(b88_before); b88_active = 1;
        }
    }
    if (pc == b88_return_pc && b88_active) {
        ++b88_returns;
        b88_regs[0] = z80sub_cpu.SP.W; b88_regs[1] = z80sub_cpu.HL.W;
        b88_regs[2] = z80sub_cpu.DE.W; b88_regs[3] = z80sub_cpu.BC.W;
        b88_regs[4] = z80sub_cpu.AF.W;
        b88_end(); b88_ended = 1;
    }
}
static void b88_write(unsigned addr, unsigned data) {
    if (b88_active && (addr & 0x4000)) {
        addr &= 0x7fff;
        if (sub_romram[addr] != data) ++b88_changes[addr-0x4000];
    }
}
static void b88_port(int output, unsigned port, unsigned data) {
    if (!b88_active) return;
    ++b88_io[output][port & 255];
    /* MSR の RQM=1/DIO=0/CB=0 のときだけコマンド先頭。引数は数えない。 */
    if (output && port == 0xfb && (fdc_status() & 0xd0) == 0x80)
        ++b88_fdc[data & 31];
}
int retro_b88_finish(void) {
    unsigned i, j; FILE *f;
    if (!b88_path) return 0;
    b88_end();
    f = fopen(b88_path, "w"); if (!f) return 0;
    fprintf(f, "B88 1\nB %u\nS %u\nE %u\nR %u\n", b88_boots, b88_starts, b88_returns, b88_restarts);
    if (b88_returns) {
        /* 自作プローブの戻りレジスタ。OUT/raw のみに保存。 */
        fprintf(f, "V");
        for (i=0; i<5; ++i) fprintf(f, " %u", b88_regs[i]);
        fprintf(f, "\n");
    }
    for (j=0; j<2; ++j) for (i=0; i<256; ++i)
        if (b88_io[j][i]) fprintf(f, "I %u %02X %llu\n", j, i, (unsigned long long)b88_io[j][i]);
    for (i=0; i<32; ++i)
        if (b88_fdc[i]) fprintf(f, "C %u %llu\n", i, (unsigned long long)b88_fdc[i]);
    for (i=0; i<0x4000; ++i)
        if (b88_changes[i]) fprintf(f, "W %04X %llu %u\n", i+0x4000,
            (unsigned long long)b88_changes[i], b88_before[i] != b88_after[i]);
    fprintf(f, "END\n");
    i = !ferror(f); if (fclose(f)) i=0;
    return i;
}
/* main の値付き記録も自作器具の4地点に限定し、公式ROM内PCを保存しない。 */
int retro_b88_main_write(unsigned pc, unsigned addr) {
    const char *p = getenv("B88_CAPTURE");
    if (!p) return 1;
    return (pc == strtoul(getenv("B88_BOOT"), NULL, 16) && addr == 0xcff0)
        || (pc == strtoul(getenv("B88_DONE"), NULL, 16) && addr == 0xcff1)
        || (pc == strtoul(getenv("B88_FAIL"), NULL, 16) && addr == 0xcff2)
        || (pc == strtoul(getenv("B88_RECEIVE"), NULL, 16) && addr >= 0xcf00 && addr < 0xcf0c);
}
