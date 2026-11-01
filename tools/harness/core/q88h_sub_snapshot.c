#include <string.h>
#include "q88h_sub_snapshot.h"
static q88h_sub_snapshot_t snapshot;
q88h_sub_snapshot_t *retro_q88h_sub_snapshot(void) { return &snapshot; }
void retro_q88h_sub_snapshot_config(uint64_t target) {
    memset(&snapshot, 0, sizeof(snapshot));
    snapshot.enabled = 1; snapshot.target = target;
}
