/* 自作入力だけによる0030の状態機械・見出し記録検査。 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "b93_intervention.h"
static q88h_boundary_t bd;
static int step(unsigned pc, int cls, int main_rom, unsigned sp)
{
    return q88h_b93_instr(&bd, pc, cls, main_rom, sp, 0x9020);
}
static void check(const char *path, const char *yes, const char *no)
{
    char buf[8192]; size_t n;
    FILE *fp = fopen(path, "r"); assert(fp);
    n = fread(buf, 1, sizeof(buf)-1, fp); buf[n] = 0; fclose(fp);
    assert(strstr(buf, yes));
    if (no) assert(!strstr(buf, no));
}
int main(int argc, char **argv)
{
    unsigned i, values[] = {0,1,2,3,0x10,0x40,0x7f,0x80,0xff};
    assert(argc == 2);
    assert(retro_q88h_b93_version() == 2);
    assert(!retro_q88h_b93_open(argv[1], 0x8000, 1, 0));
    assert(!retro_q88h_b93_open(argv[1], 0x1000, 1, 256));
    for (i = 0; i < sizeof(values)/sizeof(values[0]); i++) {
        assert(retro_q88h_b93_open(argv[1], 0x1000, 1, values[i]));
        assert(!retro_q88h_b93_open(argv[1], 0x1000, 1, values[i]));
        bd.last_class = Q88H_BND_ROM;
        assert(!step(0x1000, Q88H_BND_ROM, 1, 0xfffe));
        bd.last_class = Q88H_BND_RAM;
        assert(!step(0x1000, Q88H_BND_RAM, 0, 0xfffe));
        assert(!step(0x1000, Q88H_BND_ROM, 0, 0xfffe));
        bd.int_pending = 1;
        assert(!step(0x1000, Q88H_BND_ROM, 1, 0xfffe));
        bd.int_pending = 0; bd.in_int = 1;
        assert(!step(0x1000, Q88H_BND_ROM, 1, 0xfffe));
        bd.in_int = 0;
        assert(!step(0x1001, Q88H_BND_ROM, 1, 0xfffe));
        assert(!step(0x1000, Q88H_BND_ROM, 1, 0xfffe));
        assert(!step(0x9080, Q88H_BND_RAM, 1, 0));
        assert(!step(0x9020, Q88H_BND_RAM, 1, 0xfffe));
        assert(step(0x9020, Q88H_BND_RAM, 0, 0) == 1);
        assert(q88h_b93_value() == values[i]);
        assert(!step(0x1000, Q88H_BND_ROM, 1, 0xfffe));
        assert(!step(0x9020, Q88H_BND_RAM, 0, 0));
        q88h_b93_fetch(0, 0x3e0d, Q88H_BND_ROM);
        q88h_b93_fetch(0, 0x3080, Q88H_BND_ROM);
        q88h_b93_fetch(1, 0x5000, Q88H_BND_RAM);
        q88h_b93_io(0, 1, 0x40, 0x9020);
        q88h_b93_io(0, 1, 0x40, 0x9020);
        retro_q88h_b93_frame(1);
        assert(retro_q88h_b93_close());
        check(argv[1], "exit 0 1\nintervention 1\n", "out ");
        check(argv[1], "frame 0 1 0 64 -1\n", NULL);
        check(argv[1], "end 2 1 1 1 2 0 0\n", NULL);
    }
    assert(retro_q88h_b93_open(argv[1], 0x1000, 0, 0));
    assert(!step(0x1000, Q88H_BND_ROM, 1, 0xaffe));
    assert(!step(0x9020, Q88H_BND_RAM, 0, 0xb000));
    assert(retro_q88h_b93_close());
    check(argv[1], "end 1 1 1 0 0 0 0\n", "intervention");
    assert(retro_q88h_b93_open(argv[1], 0x1000, 1, 0));
    assert(!step(0x1000, Q88H_BND_ROM, 1, 0xaffe));
    for (i = 0; i <= 30; i++) retro_q88h_b93_frame(i);
    assert(!step(0x9020, Q88H_BND_RAM, 0, 0xb000));
    assert(retro_q88h_b93_close());
    check(argv[1], "exit 30 0\n", "intervention");
    assert(retro_q88h_b93_open(argv[1], 0x1000, 1, 0));
    assert(retro_q88h_b93_close());
    check(argv[1], "end 1 0 0 0 0 0 0\n", "entry");
    puts("B93 パッチ0030: 帰還・一回限り・bit7入力・未到達・未帰還 PASS");
    return 0;
}
