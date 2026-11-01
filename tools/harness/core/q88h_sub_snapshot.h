#ifndef Q88H_SUB_SNAPSHOT_H
#define Q88H_SUB_SNAPSHOT_H
#include <stdint.h>
#define Q88H_SNAPSHOT_REGS 18
typedef struct {
    int enabled, captured;
    uint64_t target;
    uint8_t ram[16384], writer[16384];
    uint16_t regs[Q88H_SNAPSHOT_REGS];
} q88h_sub_snapshot_t;
q88h_sub_snapshot_t *retro_q88h_sub_snapshot(void);
void retro_q88h_sub_snapshot_config(uint64_t target);
void q88h_sub_snapshot_capture(void);
#endif
