/* パッチ0029の状態機械を自作入力だけで検査する。 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "b92_intervention.h"
static q88h_boundary_t boundary;
q88h_boundary_t *retro_q88h_boundary(void) { return &boundary; }
static int step(unsigned pc, int cls, int main_rom, int writable)
{
    return q88h_b92_instr(&boundary, pc, cls, main_rom, 0xaffe, 0x9020,
                          writable, 0xf300, 120 * 25);
}
int main(int argc, char **argv)
{
    char buf[4096];
    FILE *fp;
    size_t n;
    assert(argc == 2);
    assert(!retro_q88h_b92_open(argv[1], 0x8000, 1, 0xe60e, 1));
    assert(retro_q88h_b92_open(argv[1], 0x1000, 1, 0xe60e, 1));
    boundary.last_class = Q88H_BND_ROM;
    assert(!step(0x1000, Q88H_BND_ROM, 1, 1));
    boundary.last_class = boundary.cur_class = Q88H_BND_RAM;
    assert(!step(0x1000, Q88H_BND_RAM, 0, 1));
    assert(!step(0x1000, Q88H_BND_ROM, 0, 1)); /* 拡張ROM */
    assert(!step(0x1001, Q88H_BND_ROM, 1, 1));
    boundary.int_pending = 1;
    assert(!step(0x1000, Q88H_BND_ROM, 1, 1));
    boundary.int_pending = 0;
    boundary.in_int = 1;
    assert(!step(0x1000, Q88H_BND_ROM, 1, 1));
    boundary.in_int = 0;
    q88h_b92_out(0x31, 0);
    q88h_b92_write(0xe6c2, 0xe6c2);
    assert(step(0x1000, Q88H_BND_ROM, 1, 1));
    assert(q88h_b92_address() == 0xe60e && q88h_b92_value() == 1);
    q88h_b92_out(0x40, 173);
    q88h_b92_write(0xf300, 0xf300);
    /* RAM への寄り道、同じ戻り番地でも SP が違う場合は継続。 */
    assert(!step(0x9080, Q88H_BND_RAM, 0, 1));
    assert(!step(0x9020, Q88H_BND_RAM, 0, 1));
    q88h_b92_out(0x41, 42);
    assert(!step(0x1003, Q88H_BND_ROM, 1, 1));
    retro_q88h_b92_frame(3);
    assert(!q88h_b92_instr(&boundary, 0x9020, Q88H_BND_RAM, 0,
                           0xb000, 0, 1, 0xf300, 3000));
    assert(!step(0x1000, Q88H_BND_ROM, 1, 1));
    assert(retro_q88h_b92_close());
    fp = fopen(argv[1], "r"); assert(fp);
    n = fread(buf, 1, sizeof(buf)-1, fp); buf[n] = 0; fclose(fp);
    assert(strstr(buf, "entry 0 1 1\nintervention 1\n"));
    assert(strstr(buf, "out 65 42\nexit 3 1 45056 62208 3000 1\n"));
    assert(strstr(buf, "end 3 1 1 0\n"));
    assert(retro_q88h_b92_open(argv[1], 0x1000, 1, 0xe60e, 1));
    assert(!step(0x1000, Q88H_BND_ROM, 1, 0)); /* VRAMは不可 */
    assert(!step(0x1000, Q88H_BND_ROM, 1, 1)); /* 再試行しない */
    assert(retro_q88h_b92_close());
    fp = fopen(argv[1], "r"); assert(fp);
    n = fread(buf, 1, sizeof(buf)-1, fp); buf[n] = 0; fclose(fp);
    assert(strstr(buf, "end 0 1 0 1\n"));
    assert(retro_q88h_b92_open(argv[1], 0x1000, 0, 0xe60e, 1));
    assert(!step(0x1000, Q88H_BND_ROM, 1, 1));
    assert(!step(0x9080, Q88H_BND_RAM, 0, 1));
    retro_q88h_b92_frame(29);
    q88h_b92_out(0x42, 1);
    retro_q88h_b92_frame(30);
    q88h_b92_out(0x43, 1);
    assert(retro_q88h_b92_close());
    fp = fopen(argv[1], "r"); assert(fp);
    n = fread(buf, 1, sizeof(buf)-1, fp); buf[n] = 0; fclose(fp);
    assert(strstr(buf, "out 66 1\nexit 30 0 -1 62208 3000 0\n"));
    assert(!strstr(buf, "out 67 1\n"));
    return 0;
}
