/* B92: RAM→main ROM の最初の横断だけに介入。値を含む記録は外部専用。 */
#ifndef B92_INTERVENTION_H
#define B92_INTERVENTION_H
#include <stdint.h>
#include "q88h_boundary.h"
int retro_q88h_b92_open(const char *path, unsigned entry, int intervene,
                       unsigned address, unsigned value);
void retro_q88h_b92_frame(uint32_t frame);
int retro_q88h_b92_close(void);
unsigned q88h_b92_address(void);
unsigned q88h_b92_value(void);
/* 戻り値1なら呼び手が main_mem_write で一度だけ書く。 */
int q88h_b92_instr(const q88h_boundary_t *bd, unsigned pc, int cls,
                   int main_rom, unsigned sp, unsigned top, int writable,
                   unsigned dma, unsigned span);
void q88h_b92_out(unsigned port, unsigned value);
/* physical は main_ram の物理番地。それ以外は -1。 */
void q88h_b92_write(unsigned address, int physical);
void q88h_b92_display(unsigned dma, unsigned span);
#endif
